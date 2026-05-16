import requests
from bs4 import BeautifulSoup
import time
import json
import os
import re
import hashlib

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8617551433:AAFK1waCKiLv72SErBuf4iK0sduSahJONZo")
CHAT_ID = os.environ.get("CHAT_ID", "6881373105")
MIN_COINS = int(os.environ.get("MIN_COINS", "20"))
CHECK_INTERVAL = 60
SEEN_FILE = "seen_paidcash.json"

SURVEY_BLOCK = ["theoremreach", "cpx research", "pollfish", "survey"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"TG error: {e}")

def scrape():
    offers = []
    try:
        res = requests.get("https://paidcash.co", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.find_all("div", class_="earning-feed-item")
        for item in items:
            try:
                title = item.find("p", class_="earning-feed-item-content-title")
                offerwall = title.get_text(strip=True) if title else ""
                if any(b in offerwall.lower() for b in SURVEY_BLOCK):
                    continue
                desc = item.find("p", class_="earning-feed-item-content-description")
                username = desc.get_text(strip=True) if desc else "?"
                pts_el = item.find("p", class_="earning-feed-item-reward-amount")
                pts_str = pts_el.get_text(strip=True) if pts_el else "0"
                pts_val = float(re.sub(r"[^\d.]", "", pts_str) or "0")
                if pts_val < MIN_COINS:
                    continue
                offers.append({
                    "offerwall": offerwall,
                    "username": username,
                    "points": pts_str,
                    "pts_val": pts_val
                })
            except:
                continue
    except Exception as e:
        print(f"Scrape error: {e}")
    return offers

def main():
    send_telegram("✅ <b>PaidCash Bot চালু!</b>\n🪙 Min coins: " + str(MIN_COINS))
    seen = load_seen()
    while True:
        offers = scrape()
        print(f"[{time.strftime('%H:%M:%S')}] Found: {len(offers)}")
        for o in offers:
            key = hashlib.md5(f"{o['offerwall']}_{o['username']}_{o['points']}".encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                send_telegram(
                    f"🪙 <b>PaidCash!</b>\n"
                    f"🏢 <b>Offerwall:</b> {o['offerwall']}\n"
                    f"👤 <b>User:</b> {o['username']}\n"
                    f"💰 <b>Coins:</b> {o['points']}"
                )
        save_seen(seen)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
