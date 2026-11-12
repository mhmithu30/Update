"""Telegram bot for tracking 2-Step Verification (2SV) on a Google Workspace domain.

Google has no API that turns 2SV ON for a user: every user has to enroll with
their own phone / authenticator, and the admin enforces it from the Admin
console. This bot covers what the official Admin SDK does allow:

  * who has / has not enrolled in 2SV (isEnrolledIn2Sv, isEnforcedIn2Sv)
  * backup verification codes for a user (list / regenerate)
  * a periodic report of users that still have 2SV off

Setup steps are in WORKSPACE_2SV_SETUP.md.
"""
import csv
import html
import io
import json
import os
import re
import sys
import time

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ========== CONFIG ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Only these chats may use the bot (comma separated). Falls back to CHAT_ID.
ALLOWED_CHAT_IDS = {
    c.strip()
    for c in (os.environ.get("ALLOWED_CHAT_IDS") or os.environ.get("CHAT_ID", "")).split(",")
    if c.strip()
}
# A Workspace admin the service account impersonates (domain-wide delegation).
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
# Service account key: either the JSON itself, or a path to the key file.
SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON", "")
SERVICE_ACCOUNT_FILE = os.environ.get("SERVICE_ACCOUNT_FILE", "service_account.json")
# 0 = no automatic report.
REPORT_INTERVAL_HOURS = float(os.environ.get("REPORT_INTERVAL_HOURS", "0"))

SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/admin.directory.user.security",
]
USER_FIELDS = (
    "primaryEmail,name/fullName,isAdmin,isEnrolledIn2Sv,isEnforcedIn2Sv,"
    "suspended,archived,orgUnitPath,lastLoginTime"
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TG_LIMIT = 3900  # Telegram allows 4096 chars per message

HELP = (
    "🔐 <b>Workspace 2-Step বট</b>\n\n"
    "/status — কতজনের 2-step চালু / বন্ধ\n"
    "/pending — যাদের 2-step এখনো বন্ধ\n"
    "/check email — একটা মেইলের অবস্থা\n"
    "/codes email — বর্তমান backup code দেখাও\n"
    "/newcodes email — নতুন ১০টা backup code বানাও (পুরনোগুলো বাতিল হবে)\n"
    "/export — সব ইউজারের তালিকা CSV ফাইলে\n\n"
    "ℹ️ Google কোনো API দিয়ে অন্যের হয়ে 2-step চালু করতে দেয় না — "
    "Admin console থেকে enforce করতে হয়, তারপর প্রতিটা ইউজার নিজে চালু করে।"
)


# ========== TELEGRAM ==========
def tg(method, timeout=20, **kwargs):
    res = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", timeout=timeout, **kwargs
    )
    return res.json()


def send(chat_id, text):
    """Send HTML text, split on line boundaries to fit Telegram's size limit."""
    chunk = ""
    for line in text.split("\n"):
        if chunk and len(chunk) + len(line) + 1 > TG_LIMIT:
            _send_chunk(chat_id, chunk)
            chunk = ""
        chunk = f"{chunk}\n{line}" if chunk else line
    if chunk:
        _send_chunk(chat_id, chunk)


def _send_chunk(chat_id, text):
    try:
        res = tg("sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
        if not res.get("ok"):
            print(f"[TG] sendMessage failed: {res.get('description')}")
    except requests.RequestException as e:
        # Never print the exception itself: its URL contains the bot token.
        print(f"[TG] sendMessage error: {type(e).__name__}")


def send_file(chat_id, filename, content, caption=""):
    try:
        res = tg(
            "sendDocument",
            timeout=60,
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (filename, content, "text/csv")},
        )
        if not res.get("ok"):
            print(f"[TG] sendDocument failed: {res.get('description')}")
    except requests.RequestException as e:
        print(f"[TG] sendDocument error: {type(e).__name__}")


# ========== GOOGLE ==========
_service = None


def get_service():
    global _service
    if _service is None:
        if SERVICE_ACCOUNT_JSON:
            info = json.loads(SERVICE_ACCOUNT_JSON)
        else:
            with open(SERVICE_ACCOUNT_FILE) as f:
                info = json.load(f)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES, subject=ADMIN_EMAIL
        )
        _service = build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    return _service


def fetch_users():
    users, page_token = [], None
    while True:
        res = (
            get_service()
            .users()
            .list(
                customer="my_customer",
                maxResults=500,
                orderBy="email",
                pageToken=page_token,
                fields=f"nextPageToken,users({USER_FIELDS})",
            )
            .execute()
        )
        users.extend(res.get("users", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            return users


def is_active(user):
    return not user.get("suspended") and not user.get("archived")


def pending_users(users):
    """Active users that have not enrolled in 2SV yet."""
    return [u for u in users if is_active(u) and not u.get("isEnrolledIn2Sv")]


def fetch_codes(email):
    res = get_service().verificationCodes().list(userKey=email).execute()
    return [str(i["verificationCode"]) for i in res.get("items", []) if i.get("verificationCode")]


def google_error_text(err):
    """Turn a Google API failure into a short Bengali explanation."""
    if isinstance(err, HttpError):
        status = err.resp.status
        if status == 404:
            return "❌ এই মেইলটা ডোমেইনে পাওয়া যায়নি।"
        if status in (401, 403):
            return (
                "❌ Google অনুমতি দেয়নি। Domain-wide delegation-এ দুটো scope দেওয়া আছে কিনা "
                "এবং ADMIN_EMAIL একজন admin কিনা দেখুন।"
            )
        return f"❌ Google API error ({status}): {html.escape(str(err.reason))}"
    return f"❌ সমস্যা হয়েছে: {html.escape(type(err).__name__)} — {html.escape(str(err)[:300])}"


# ========== COMMANDS ==========
def status_text(users):
    active = [u for u in users if is_active(u)]
    enrolled = [u for u in active if u.get("isEnrolledIn2Sv")]
    enforced = [u for u in active if u.get("isEnforcedIn2Sv")]
    return (
        "📊 <b>2-Step অবস্থা</b>\n"
        f"👥 মোট ইউজার: {len(users)} (সক্রিয় {len(active)})\n"
        f"✅ 2-step চালু: {len(enrolled)}\n"
        f"❌ 2-step বন্ধ: {len(active) - len(enrolled)}\n"
        f"🔒 Enforce করা: {len(enforced)}\n"
        f"⏸ Suspended/Archived: {len(users) - len(active)}"
    )


def pending_text(users):
    pending = pending_users(users)
    if not pending:
        return "✅ সব সক্রিয় ইউজারের 2-step চালু আছে।"
    lines = [f"❌ <b>2-step বন্ধ ({len(pending)} জন)</b>"]
    for u in pending:
        tag = " 👑 admin" if u.get("isAdmin") else ""
        lines.append(f"• <code>{html.escape(u.get('primaryEmail', '?'))}</code>{tag}")
    return "\n".join(lines)


def check_text(user):
    def yes_no(value):
        return "✅ হ্যাঁ" if value else "❌ না"

    last_login = user.get("lastLoginTime", "")
    if not last_login or last_login.startswith("1970"):
        last_login = "কখনো লগইন করেনি"
    return (
        f"👤 <b>{html.escape(user.get('name', {}).get('fullName', '?'))}</b>\n"
        f"📧 <code>{html.escape(user.get('primaryEmail', '?'))}</code>\n"
        f"🔐 2-step চালু: {yes_no(user.get('isEnrolledIn2Sv'))}\n"
        f"🔒 Enforce করা: {yes_no(user.get('isEnforcedIn2Sv'))}\n"
        f"⏸ Suspended: {yes_no(user.get('suspended'))}\n"
        f"📁 Org unit: {html.escape(user.get('orgUnitPath', '/'))}\n"
        f"🕒 শেষ লগইন: {html.escape(last_login)}"
    )


def codes_text(email, codes, fresh=False):
    if not codes:
        return (
            f"ℹ️ <code>{html.escape(email)}</code>-এর কোনো backup code নেই। "
            "বানাতে /newcodes ব্যবহার করুন।"
        )
    title = "নতুন backup code" if fresh else "Backup code"
    lines = [f"🔑 <b>{title}</b> — <code>{html.escape(email)}</code>"]
    lines += [f"<code>{html.escape(c)}</code>" for c in codes]
    lines.append("⚠️ প্রতিটা কোড একবারই চলে। কাজ শেষে এই মেসেজ মুছে ফেলুন।")
    return "\n".join(lines)


def export_csv(users):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["email", "name", "2sv_enrolled", "2sv_enforced", "admin", "suspended", "org_unit", "last_login"]
    )
    for u in users:
        writer.writerow(
            [
                u.get("primaryEmail", ""),
                u.get("name", {}).get("fullName", ""),
                bool(u.get("isEnrolledIn2Sv")),
                bool(u.get("isEnforcedIn2Sv")),
                bool(u.get("isAdmin")),
                bool(u.get("suspended") or u.get("archived")),
                u.get("orgUnitPath", ""),
                u.get("lastLoginTime", ""),
            ]
        )
    # utf-8-sig so Excel opens non-ASCII names correctly
    return buf.getvalue().encode("utf-8-sig")


def handle_command(chat_id, text):
    parts = text.split()
    command = parts[0].split("@")[0].lower()
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if command in ("/start", "/help"):
        send(chat_id, HELP)
        return
    if command not in ("/status", "/pending", "/check", "/codes", "/newcodes", "/export"):
        send(chat_id, "অজানা কমান্ড। /help দেখুন।")
        return
    if command in ("/check", "/codes", "/newcodes") and not EMAIL_RE.match(arg):
        send(chat_id, f"ব্যবহার: <code>{command} user@yourdomain.com</code>")
        return

    try:
        if command == "/status":
            send(chat_id, status_text(fetch_users()))
        elif command == "/pending":
            send(chat_id, pending_text(fetch_users()))
        elif command == "/check":
            user = get_service().users().get(userKey=arg, fields=USER_FIELDS).execute()
            send(chat_id, check_text(user))
        elif command == "/codes":
            send(chat_id, codes_text(arg, fetch_codes(arg)))
        elif command == "/newcodes":
            get_service().verificationCodes().generate(userKey=arg).execute()
            send(chat_id, codes_text(arg, fetch_codes(arg), fresh=True))
        elif command == "/export":
            users = fetch_users()
            send_file(chat_id, "workspace_2sv.csv", export_csv(users), f"মোট {len(users)} ইউজার")
    except Exception as e:  # keep the bot alive whatever Google returns
        print(f"[Google] {command}: {type(e).__name__}: {e}")
        send(chat_id, google_error_text(e))


def handle_update(update):
    msg = update.get("message") or {}
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return
    if chat_id not in ALLOWED_CHAT_IDS:
        print(f"[TG] ignored command from unauthorised chat {chat_id}")
        return
    handle_command(chat_id, text)


def send_report():
    try:
        users = fetch_users()
        text = "🗓 <b>নিয়মিত রিপোর্ট</b>\n" + status_text(users) + "\n\n" + pending_text(users)
    except Exception as e:
        print(f"[Report] {type(e).__name__}: {e}")
        text = google_error_text(e)
    for chat_id in ALLOWED_CHAT_IDS:
        send(chat_id, text)


# ========== MAIN ==========
def check_config():
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not ALLOWED_CHAT_IDS:
        missing.append("ALLOWED_CHAT_IDS")
    if not ADMIN_EMAIL:
        missing.append("ADMIN_EMAIL")
    if not SERVICE_ACCOUNT_JSON and not os.path.exists(SERVICE_ACCOUNT_FILE):
        missing.append("SERVICE_ACCOUNT_JSON (or SERVICE_ACCOUNT_FILE)")
    if missing:
        sys.exit("Missing config: " + ", ".join(missing))


def skip_backlog():
    """Drop commands sent while the bot was offline (e.g. an old /newcodes)."""
    try:
        res = tg("getUpdates", json={"offset": -1, "timeout": 0})
        results = res.get("result") or []
        return results[-1]["update_id"] + 1 if results else None
    except requests.RequestException as e:
        print(f"[TG] getUpdates error: {type(e).__name__}")
        return None


def main():
    check_config()
    offset = skip_backlog()
    interval = REPORT_INTERVAL_HOURS * 3600
    next_report = time.time() + interval if interval > 0 else None
    for chat_id in ALLOWED_CHAT_IDS:
        send(chat_id, "✅ <b>Workspace 2-Step বট চালু!</b>\n/help লিখে কমান্ড দেখুন।")
    print("[Bot] running")

    while True:
        try:
            res = tg(
                "getUpdates",
                timeout=40,
                json={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
            )
        except requests.RequestException as e:
            print(f"[TG] getUpdates error: {type(e).__name__}")
            time.sleep(5)
            continue
        if not res.get("ok"):
            print(f"[TG] getUpdates failed: {res.get('description')}")
            time.sleep(10)
            continue
        for update in res.get("result", []):
            offset = update["update_id"] + 1
            handle_update(update)
        if next_report and time.time() >= next_report:
            send_report()
            next_report = time.time() + interval


if __name__ == "__main__":
    main()
