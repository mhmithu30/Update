"""Telegram bot that turns on Two-Factor Authentication (2FA) for the email
accounts of a cPanel account, using cPanel's own UAPI (no browser automation).

For every mailbox the bot:
  1. opens a Webmail session   (UAPI Session::create_webmail_session_for_mail_user)
  2. asks cPanel for a secret  (UAPI TwoFactorAuth::generate_user_configuration)
  3. computes the 6-digit code from that secret (TOTP, RFC 6238)
  4. saves the configuration   (UAPI TwoFactorAuth::set_user_configuration)
  5. sends you the setup key + QR code so you can add it to an authenticator app

Needs cPanel 114 or newer with 2FA enabled by the host. Setup steps are in
CPANEL_2FA_SETUP.md.
"""
import base64
import csv
import hashlib
import hmac
import html
import io
import json
import os
import re
import struct
import sys
import time
from urllib.parse import quote

import qrcode
import requests

# ========== CONFIG ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Only these chats may use the bot (comma separated). Falls back to CHAT_ID.
ALLOWED_CHAT_IDS = {
    c.strip()
    for c in (os.environ.get("ALLOWED_CHAT_IDS") or os.environ.get("CHAT_ID", "")).split(",")
    if c.strip()
}
# Server hostname exactly as you open cPanel, without https:// or the port.
CPANEL_HOST = os.environ.get("CPANEL_HOST", "")
CPANEL_USER = os.environ.get("CPANEL_USER", "")
# cPanel -> Manage API Tokens. CPANEL_PASSWORD is used only if no token is set.
CPANEL_TOKEN = os.environ.get("CPANEL_TOKEN", "")
CPANEL_PASSWORD = os.environ.get("CPANEL_PASSWORD", "")
CPANEL_PORT = os.environ.get("CPANEL_PORT", "2083")
WEBMAIL_PORT = os.environ.get("WEBMAIL_PORT", "2096")
SECRETS_FILE = os.environ.get("SECRETS_FILE", "cpanel_2fa_secrets.json")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TG_LIMIT = 3900  # Telegram allows 4096 chars per message
HTTP_TIMEOUT = 30

HELP = (
    "🔐 <b>cPanel মেইল 2-Step বট</b>\n\n"
    "/mails — সব মেইলের তালিকা\n"
    "/status — কোন মেইলে 2-step চালু / বন্ধ\n"
    "/enable email — একটা মেইলে 2-step চালু করো\n"
    "/enableall — যেগুলোতে বন্ধ, সবগুলোতে চালু করো\n"
    "/code email — লগইনের জন্য এখনকার ৬ সংখ্যার কোড\n"
    "/disable email — একটা মেইলের 2-step বন্ধ করো\n"
    "/export — সব setup key CSV ফাইলে\n\n"
    "⚠️ প্রথমে <b>একটা</b> মেইলে /enable দিয়ে পরীক্ষা করুন, তারপর /enableall দিন।"
)


class CPanelError(Exception):
    """A cPanel call failed; the message is safe to show to the user."""


# ========== TOTP (RFC 6238: SHA-1, 6 digits, 30 seconds) ==========
def totp(secret, now=None):
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = struct.pack(">Q", int((time.time() if now is None else now) // 30))
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1000000:06d}"


def wait_for_fresh_window(min_left=5):
    """Avoid sending a code that expires while the request is on its way."""
    left = 30 - time.time() % 30
    if left < min_left:
        time.sleep(left + 0.5)


# ========== CPANEL ==========
def cpanel_base():
    return f"https://{CPANEL_HOST}:{CPANEL_PORT}"


def webmail_base(host):
    return f"https://{host}:{WEBMAIL_PORT}"


def _request(session, method, url, **kwargs):
    try:
        return session.request(method, url, timeout=HTTP_TIMEOUT, **kwargs)
    except requests.exceptions.SSLError:
        raise CPanelError("SSL সার্টিফিকেট মেলেনি — CPANEL_HOST-এ সার্ভারের আসল hostname দিন।")
    except requests.RequestException as e:
        raise CPanelError(f"সার্ভারে সংযোগ হয়নি ({type(e).__name__})।")


def _uapi_data(res, what):
    """Return the `data` part of a UAPI reply, or raise with cPanel's own error."""
    if res.status_code in (401, 403):
        raise CPanelError(f"{what}: cPanel লগইন/অনুমতি প্রত্যাখ্যান করেছে (HTTP {res.status_code})।")
    try:
        body = res.json()
    except ValueError:
        raise CPanelError(f"{what}: সার্ভার JSON দেয়নি (HTTP {res.status_code})।")
    result = body.get("result", body) if isinstance(body, dict) else {}
    if not isinstance(result, dict) or not result.get("status"):
        errors = (result.get("errors") if isinstance(result, dict) else None) or ["অজানা error"]
        raise CPanelError(f"{what}: " + "; ".join(str(e) for e in errors))
    return result.get("data")


def cpanel_call(module, func, **params):
    """Call UAPI as the cPanel account owner."""
    if CPANEL_TOKEN:
        kwargs = {"headers": {"Authorization": f"cpanel {CPANEL_USER}:{CPANEL_TOKEN}"}}
    else:
        kwargs = {"auth": (CPANEL_USER, CPANEL_PASSWORD)}
    res = _request(
        requests, "GET", f"{cpanel_base()}/execute/{module}/{func}", params=params, **kwargs
    )
    return _uapi_data(res, f"{module}::{func}")


def list_mailboxes():
    data = cpanel_call("Email", "list_pops", skip_main=1) or []
    emails = {str(item.get("email") or "").lower() for item in data}
    return sorted(e for e in emails if EMAIL_RE.match(e))


class Webmail:
    """A Webmail session for one mailbox, opened by the cPanel account owner."""

    def __init__(self, email):
        login, domain = email.rsplit("@", 1)
        data = cpanel_call(
            "Session", "create_webmail_session_for_mail_user", login=login, domain=domain
        ) or {}
        if not data.get("token") or not data.get("session"):
            raise CPanelError("Webmail session তৈরি হয়নি।")
        self.base = webmail_base(data.get("hostname") or CPANEL_HOST) + data["token"]
        self.http = requests.Session()
        res = _request(self.http, "POST", f"{self.base}/login", data={"session": data["session"]})
        if res.status_code >= 400:
            raise CPanelError(f"Webmail লগইন হয়নি (HTTP {res.status_code})।")

    def call(self, func, **params):
        res = _request(
            self.http, "GET", f"{self.base}/execute/TwoFactorAuth/{func}", params=params
        )
        return _uapi_data(res, f"TwoFactorAuth::{func}") or {}

    def is_enabled(self):
        return bool(int(self.call("get_user_configuration").get("is_enabled") or 0))


# ========== SECRETS STORE ==========
def load_secrets():
    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE) as f:
            return json.load(f)
    return {}


def save_secret(email, secret, otpauth, enabled):
    secrets = load_secrets()
    secrets[email] = {
        "secret": secret,
        "otpauth": otpauth,
        "enabled": enabled,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    tmp = SECRETS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(secrets, f, indent=2)
    os.replace(tmp, SECRETS_FILE)


def forget_secret(email):
    secrets = load_secrets()
    if secrets.pop(email, None) is not None:
        with open(SECRETS_FILE, "w") as f:
            json.dump(secrets, f, indent=2)


# ========== 2FA ACTIONS ==========
def enable_2fa(email):
    """Turn 2FA on for one mailbox. Returns (state, secret, otpauth)."""
    webmail = Webmail(email)
    if webmail.is_enabled():
        return "already", None, None
    config = webmail.call("generate_user_configuration")
    secret = config.get("secret")
    if not secret:
        raise CPanelError("cPanel কোনো secret দেয়নি।")
    otpauth = config.get("otpauth_str") or (
        f"otpauth://totp/{quote(email)}?secret={secret}&issuer={quote(CPANEL_HOST)}"
    )
    # Store the key before switching 2FA on, so it can never be lost.
    save_secret(email, secret, otpauth, enabled=False)
    wait_for_fresh_window()
    webmail.call("set_user_configuration", secret=secret, tfa_token=totp(secret))
    save_secret(email, secret, otpauth, enabled=True)
    return "enabled", secret, otpauth


def disable_2fa(email):
    webmail = Webmail(email)
    if not webmail.is_enabled():
        return False
    webmail.call("remove_user_configuration")
    forget_secret(email)
    return True


# ========== TELEGRAM ==========
def tg(method, timeout=20, **kwargs):
    res = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", timeout=timeout, **kwargs
    )
    return res.json()


def _tg_safe(method, **kwargs):
    try:
        res = tg(method, **kwargs)
        if not res.get("ok"):
            print(f"[TG] {method} failed: {res.get('description')}")
        return bool(res.get("ok"))
    except requests.RequestException as e:
        # Never print the exception itself: its URL contains the bot token.
        print(f"[TG] {method} error: {type(e).__name__}")
        return False


def send(chat_id, text):
    """Send HTML text, split on line boundaries to fit Telegram's size limit."""
    chunk = ""
    for line in text.split("\n"):
        if chunk and len(chunk) + len(line) + 1 > TG_LIMIT:
            _tg_safe("sendMessage", json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"})
            chunk = ""
        chunk = f"{chunk}\n{line}" if chunk else line
    if chunk:
        _tg_safe("sendMessage", json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"})


def key_text(email, secret):
    return (
        f"✅ <b>2-step চালু হয়েছে</b>\n"
        f"📧 <code>{html.escape(email)}</code>\n"
        f"🔑 Setup key: <code>{html.escape(secret)}</code>\n"
        "QR স্ক্যান করে বা key লিখে authenticator অ্যাপে যোগ করুন। "
        "এই key হারালে মেইলে ঢোকা যাবে না।"
    )


def send_key(chat_id, email, secret, otpauth):
    """Send the setup key with its QR code; fall back to text if the photo fails."""
    image = io.BytesIO()
    qrcode.make(otpauth).save(image, format="PNG")
    sent = _tg_safe(
        "sendPhoto",
        timeout=60,
        data={"chat_id": chat_id, "caption": key_text(email, secret), "parse_mode": "HTML"},
        files={"photo": ("qr.png", image.getvalue(), "image/png")},
    )
    if not sent:
        send(chat_id, key_text(email, secret))


def export_csv():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "setup_key", "otpauth", "enabled", "updated"])
    for email, item in sorted(load_secrets().items()):
        writer.writerow(
            [email, item["secret"], item["otpauth"], item["enabled"], item["updated"]]
        )
    return buf.getvalue().encode("utf-8")


# ========== COMMANDS ==========
def cmd_mails(chat_id):
    emails = list_mailboxes()
    lines = [f"📬 <b>মোট {len(emails)}টা মেইল</b>"]
    lines += [f"• <code>{html.escape(e)}</code>" for e in emails]
    send(chat_id, "\n".join(lines))


def cmd_status(chat_id):
    emails = list_mailboxes()
    send(chat_id, f"⏳ {len(emails)}টা মেইল পরীক্ষা করছি…")
    lines, on = [], 0
    for email in emails:
        try:
            enabled = Webmail(email).is_enabled()
            on += enabled
            mark = "✅" if enabled else "❌"
        except CPanelError as e:
            mark = f"⚠️ {html.escape(str(e))} —"
        lines.append(f"{mark} <code>{html.escape(email)}</code>")
    header = f"📊 <b>2-step চালু {on} / {len(emails)}</b>"
    send(chat_id, "\n".join([header] + lines))


def enable_and_report(chat_id, email):
    """Returns 'enabled', 'already' or 'failed'."""
    try:
        state, secret, otpauth = enable_2fa(email)
    except CPanelError as e:
        send(chat_id, f"❌ <code>{html.escape(email)}</code> — {html.escape(str(e))}")
        return "failed"
    if state == "already":
        send(chat_id, f"ℹ️ <code>{html.escape(email)}</code> — আগে থেকেই চালু।")
    else:
        send_key(chat_id, email, secret, otpauth)
    return state


def cmd_enableall(chat_id):
    emails = list_mailboxes()
    send(chat_id, f"⏳ {len(emails)}টা মেইলে কাজ শুরু…")
    counts = {"enabled": 0, "already": 0, "failed": 0}
    for email in emails:
        counts[enable_and_report(chat_id, email)] += 1
    send(
        chat_id,
        f"🏁 <b>শেষ</b>\n✅ নতুন চালু: {counts['enabled']}\n"
        f"ℹ️ আগে থেকেই চালু: {counts['already']}\n❌ ব্যর্থ: {counts['failed']}",
    )


def cmd_code(chat_id, email):
    item = load_secrets().get(email)
    if not item:
        send(chat_id, f"ℹ️ <code>{html.escape(email)}</code>-এর key বটে সেভ নেই।")
        return
    left = int(30 - time.time() % 30)
    send(
        chat_id,
        f"🔢 <code>{totp(item['secret'])}</code> — <code>{html.escape(email)}</code>\n"
        f"⏱ আর {left} সেকেন্ড চলবে",
    )


def cmd_disable(chat_id, email):
    if disable_2fa(email):
        send(chat_id, f"🔓 <code>{html.escape(email)}</code> — 2-step বন্ধ করা হয়েছে।")
    else:
        send(chat_id, f"ℹ️ <code>{html.escape(email)}</code> — 2-step চালু ছিল না।")


def cmd_export(chat_id):
    if not load_secrets():
        send(chat_id, "ℹ️ এখনো কোনো key সেভ হয়নি।")
        return
    _tg_safe(
        "sendDocument",
        timeout=60,
        data={"chat_id": chat_id, "caption": "সব setup key — নিরাপদ জায়গায় রাখুন"},
        files={"document": ("cpanel_2fa_keys.csv", export_csv(), "text/csv")},
    )


def handle_command(chat_id, text):
    parts = text.split()
    command = parts[0].split("@")[0].lower()
    arg = text.split(None, 1)[1].strip().lower() if len(parts) > 1 else ""

    if command in ("/start", "/help"):
        send(chat_id, HELP)
        return
    no_arg = {"/mails": cmd_mails, "/status": cmd_status, "/enableall": cmd_enableall, "/export": cmd_export}
    with_email = {"/enable": enable_and_report, "/code": cmd_code, "/disable": cmd_disable}
    try:
        if command in no_arg:
            no_arg[command](chat_id)
        elif command in with_email:
            if not EMAIL_RE.match(arg):
                send(chat_id, f"ব্যবহার: <code>{command} name@yourdomain.com</code>")
            else:
                with_email[command](chat_id, arg)
        else:
            send(chat_id, "অজানা কমান্ড। /help দেখুন।")
    except CPanelError as e:
        send(chat_id, f"❌ {html.escape(str(e))}")
    except Exception as e:  # keep the bot alive whatever happens
        print(f"[Bot] {command}: {type(e).__name__}: {e}")
        send(chat_id, f"❌ সমস্যা হয়েছে: {html.escape(type(e).__name__)}")


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


# ========== MAIN ==========
def check_config():
    missing = [
        name
        for name, value in (
            ("BOT_TOKEN", BOT_TOKEN),
            ("ALLOWED_CHAT_IDS", ALLOWED_CHAT_IDS),
            ("CPANEL_HOST", CPANEL_HOST),
            ("CPANEL_USER", CPANEL_USER),
            ("CPANEL_TOKEN (or CPANEL_PASSWORD)", CPANEL_TOKEN or CPANEL_PASSWORD),
        )
        if not value
    ]
    if missing:
        sys.exit("Missing config: " + ", ".join(missing))


def skip_backlog():
    """Drop commands sent while the bot was offline (e.g. an old /enableall)."""
    try:
        results = tg("getUpdates", json={"offset": -1, "timeout": 0}).get("result") or []
        return results[-1]["update_id"] + 1 if results else None
    except requests.RequestException as e:
        print(f"[TG] getUpdates error: {type(e).__name__}")
        return None


def main():
    check_config()
    offset = skip_backlog()
    for chat_id in ALLOWED_CHAT_IDS:
        send(chat_id, "✅ <b>cPanel 2-Step বট চালু!</b>\n/help লিখে কমান্ড দেখুন।")
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


if __name__ == "__main__":
    main()
