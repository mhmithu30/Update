import os
import re
import json
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ============================================================
# CONFIG — Railway environment variables থেকে নেওয়া হবে
# ============================================================
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
CHAT_ID     = os.environ.get("CHAT_ID", "")
MIN_POINTS  = float(os.environ.get("MIN_POINTS", "101"))
SPLITDROP_MIN = float(os.environ.get("SPLITDROP_MIN_USD", "0.101"))
PAIDCASH_MIN  = float(os.environ.get("PAIDCASH_MIN_POINTS", "200"))

SEEN_FILE   = "seen_all_offers.json"
CHECK_INTERVAL = 60  # seconds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ============================================================
# SEEN OFFERS — duplicate prevention
# ============================================================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def make_key(*parts):
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
        if not r.ok:
            print(f"[TG Error] {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[TG Exception] {e}")

# ============================================================
# HUNTSKIN
# ============================================================
def scrape_huntskin():
    offers = []
    try:
        r = requests.get("https://huntskin.com", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.find_all("tr")
        for row in rows:
            try:
                user_td  = row.find("td", attrs={"data-label": "Username"})
                type_td  = row.find("td", attrs={"data-label": "Type"})
                pts_td   = row.find("td", attrs={"data-label": "Points"})
                if not (user_td and type_td and pts_td):
                    continue
                username = user_td.get_text(strip=True)
                offer    = type_td.get_text(strip=True)
                pts_text = pts_td.get_text(strip=True)
                pts_val  = float(re.sub(r"[^\d.]", "", pts_text) or "0")
                if pts_val >= MIN_POINTS:
                    offers.append({
                        "site": "Huntskin",
                        "username": username,
                        "offer": offer,
                        "points": pts_val,
                        "points_str": pts_text,
                    })
            except Exception:
                pass
    except Exception as e:
        print(f"[Huntskin] Error: {e}")
    return offers

# ============================================================
# APUCASH — Public Activity Feed (Livewire-aware fix)
# ============================================================
def scrape_apucash():
    """
    ApuCash uses Laravel Livewire. The public homepage loads activity
    via Livewire wire:key='activity-XX' divs. We try the homepage first,
    then fallback to /activity endpoint if available.
    """
    offers = []
    urls_to_try = [
        "https://apucash.com",
        "https://apucash.com/activity",
        "https://apucash.com/offers",
    ]

    html = None
    for url in urls_to_try:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.ok and len(r.text) > 500:
                html = r.text
                break
        except Exception as e:
            print(f"[ApuCash] Failed {url}: {e}")

    if not html:
        print("[ApuCash] Could not fetch any page")
        return offers

    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: wire:key="activity-XX" blocks
    activity_blocks = soup.find_all(
        lambda tag: tag.has_attr("wire:key") and
        re.match(r"activity-\d+", tag.get("wire:key", ""))
    )

    for block in activity_blocks:
        try:
            # username
            user_el = (
                block.find(class_="username") or
                block.find(class_="user-name") or
                block.find("a", href=re.compile(r"/user/")) or
                block.find("span", class_=re.compile(r"user"))
            )
            username = user_el.get_text(strip=True) if user_el else "?"

            # offer/activity name
            offer_el = (
                block.find(class_="offer-name") or
                block.find(class_="activity-name") or
                block.find("h5") or
                block.find("h6") or
                block.find("p", class_=re.compile(r"title|name"))
            )
            offer = offer_el.get_text(strip=True) if offer_el else "?"

            # points
            pts_el = (
                block.find(class_=re.compile(r"point|coin|reward|amount")) or
                block.find("span", class_=re.compile(r"pts|coins"))
            )
            pts_text = pts_el.get_text(strip=True) if pts_el else "0"
            pts_val  = float(re.sub(r"[^\d.]", "", pts_text) or "0")

            if pts_val >= MIN_POINTS:
                offers.append({
                    "site": "ApuCash",
                    "username": username,
                    "offer": offer,
                    "points": pts_val,
                    "points_str": pts_text,
                })
        except Exception:
            pass

    # Strategy 2: generic activity/feed rows (fallback)
    if not offers:
        feed_items = (
            soup.find_all(class_=re.compile(r"activity-item|feed-item|offer-row|earn-item")) or
            soup.find_all("li", class_=re.compile(r"activity|offer"))
        )
        for item in feed_items:
            try:
                texts = [t.get_text(strip=True) for t in item.find_all(True) if t.get_text(strip=True)]
                username = texts[0] if texts else "?"
                offer    = texts[1] if len(texts) > 1 else "?"
                pts_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:pts|points|coins)?", item.get_text())
                pts_val = float(pts_match.group(1)) if pts_match else 0
                pts_text = pts_match.group(0) if pts_match else "0"
                if pts_val >= MIN_POINTS:
                    offers.append({
                        "site": "ApuCash",
                        "username": username,
                        "offer": offer,
                        "points": pts_val,
                        "points_str": pts_text,
                    })
            except Exception:
                pass

    print(f"[ApuCash] Found {len(offers)} offers (public only)")
    return offers

# ============================================================
# CASHLYEARN — Livewire POST API
# ============================================================
def scrape_cashlyearn():
    offers = []
    try:
        # Try public activity page
        r = requests.get("https://cashlyearn.com", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        # Look for any livewire component ID
        component = soup.find(attrs={"wire:id": True})
        if not component:
            print("[CashlyEarn] No Livewire component found")
            return offers

        wire_id = component["wire:id"]
        fingerprint = {"id": wire_id, "name": "activity-feed", "locale": "en"}

        livewire_url = "https://cashlyearn.com/livewire/message/activity-feed"
        payload = {
            "fingerprint": fingerprint,
            "serverMemo": {},
            "updates": [{"type": "callMethod", "payload": {"id": "x", "method": "loadMore"}}]
        }
        lr = requests.post(livewire_url, json=payload, headers={
            **HEADERS,
            "X-Livewire": "true",
            "Content-Type": "application/json",
        }, timeout=15)

        if lr.ok:
            data = lr.json()
            html = data.get("effects", {}).get("html", "")
            soup2 = BeautifulSoup(html, "html.parser")
            rows = soup2.find_all(class_=re.compile(r"activity|offer|earn"))
            for row in rows:
                try:
                    text = row.get_text(" ", strip=True)
                    pts_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:pts|points|coins)?", text)
                    pts_val = float(pts_match.group(1)) if pts_match else 0
                    if pts_val >= MIN_POINTS:
                        offers.append({
                            "site": "CashlyEarn",
                            "username": "—",
                            "offer": text[:60],
                            "points": pts_val,
                            "points_str": pts_match.group(0) if pts_match else "0",
                        })
                except Exception:
                    pass
    except Exception as e:
        print(f"[CashlyEarn] Error: {e}")
    return offers

# ============================================================
# SPLITDROP
# ============================================================
def scrape_splitdrop():
    offers = []
    try:
        r = requests.get("https://splitdrop.com", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        rows = soup.find_all(class_=re.compile(r"winner|drop|reward|activity"))
        for row in rows:
            try:
                text = row.get_text(" ", strip=True)
                usd_match = re.search(r"\$(\d+(?:\.\d+)?)", text)
                if not usd_match:
                    continue
                usd_val = float(usd_match.group(1))
                if usd_val >= SPLITDROP_MIN:
                    user_el = row.find(class_=re.compile(r"user|name")) or row.find("a")
                    username = user_el.get_text(strip=True) if user_el else "?"
                    offers.append({
                        "site": "SplitDrop",
                        "username": username,
                        "offer": text[:60],
                        "points": usd_val,
                        "points_str": f"${usd_val}",
                    })
            except Exception:
                pass
    except Exception as e:
        print(f"[SplitDrop] Error: {e}")
    return offers

# ============================================================
# PAIDCASH
# ============================================================
SURVEY_BLOCKLIST = {"theoremreach", "cpx research", "pollfish", "theorem", "cpx"}

def scrape_paidcash():
    offers = []
    try:
        r = requests.get("https://paidcash.co", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        items = soup.find_all(class_=re.compile(r"earning-feed|activity|offer"))
        for item in items:
            try:
                text = item.get_text(" ", strip=True).lower()
                if any(b in text for b in SURVEY_BLOCKLIST):
                    continue
                coins_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:coins?|pts|points)?", text)
                coins = float(coins_match.group(1)) if coins_match else 0
                if coins >= PAIDCASH_MIN:
                    offers.append({
                        "site": "PaidCash",
                        "username": "—",
                        "offer": item.get_text(" ", strip=True)[:60],
                        "points": coins,
                        "points_str": f"{int(coins)} coins",
                    })
            except Exception:
                pass
    except Exception as e:
        print(f"[PaidCash] Error: {e}")
    return offers

# ============================================================
# FORMAT MESSAGES
# ============================================================
SITE_EMOJI = {
    "Huntskin":   "🔴",
    "ApuCash":    "🟢",
    "CashlyEarn": "🔵",
    "SplitDrop":  "🟠",
    "PaidCash":   "🪙",
}

def format_offer(o: dict) -> str:
    emoji = SITE_EMOJI.get(o["site"], "💰")
    return (
        f"{emoji} <b>{o['site']}</b>\n"
        f"👤 <b>{o['username']}</b>\n"
        f"🎯 {o['offer']}\n"
        f"💎 <b>{o['points_str']}</b>\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT_TOKEN বা CHAT_ID set করা নেই!")
        return

    seen = load_seen()
    send_telegram("✅ <b>Earning Monitor Bot চালু হয়েছে!</b>\n\nSites: Huntskin, ApuCash, CashlyEarn, SplitDrop, PaidCash")
    print("Bot started. Monitoring...")

    scrapers = [
        scrape_huntskin,
        scrape_apucash,
        scrape_cashlyearn,
        scrape_splitdrop,
        scrape_paidcash,
    ]

    while True:
        all_offers = []
        for scraper in scrapers:
            try:
                all_offers.extend(scraper())
            except Exception as e:
                print(f"[Main] Scraper error: {e}")

        new_count = 0
        for offer in all_offers:
            key = make_key(offer["site"], offer["username"], offer["offer"], offer["points_str"])
            if key not in seen:
                seen.add(key)
                msg = format_offer(offer)
                send_telegram(msg)
                print(f"[NEW] {offer['site']} — {offer['username']} — {offer['points_str']}")
                new_count += 1
                time.sleep(1)  # rate limit

        if new_count > 0:
            save_seen(seen)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checked. New: {new_count}. Total seen: {len(seen)}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
