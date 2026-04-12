import requests
from bs4 import BeautifulSoup
import time
import json
import os
import re

BOT_TOKEN = os.environ.get("BOT_TOKEN", "AAFK1waCKiLv72SErBuf4iK0sduSahJONZo")
CHAT_ID = os.environ.get("CHAT_ID", "8617551433")

URL = "https://huntskin.com/Liveoffersfinal/Live.php"
SEEN_FILE = "seen_offers.json"
CHECK_INTERVAL = 60


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=data, timeout=10)
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")


def scrape_offers():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(URL, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        all_text = soup.get_text(separator="|||")

        usernames = re.findall(r'username\s*\|\|\|([^\|]+)', all_text, re.IGNORECASE)
        points = re.findall(r'Points\s*\|\|\|([^\|]+)', all_text, re.IGNORECASE)
        types = re.findall(r'type([^\|]{5,100})', all_text, re.IGNORECASE)

        offers = []
        for i in range(len(usernames)):
            offers.append({
                "username": usernames[i].strip() if i < len(usernames) else "Unknown",
                "points": points[i].strip() if i < len(points) else "?",
                "type": types[i].strip()[:100] if i < len(types) else "?"
            })

        print(f"Found {len(offers)} offers")
        return offers
    except Exception as e:
        print(f"Scrape error: {e}")
        return []


def make_key(offer):
    return f"{offer.get('username','')}_{offer.get('points','')}_{offer.get('type','')[:30]}"


def main():
    print("✅ Huntskin Notifier চালু হয়েছে...")
    send_telegram("✅ <b>Huntskin Notifier চালু হয়েছে!</b>\nনতুন Live Offer আসলে এখানে নোটিফিকেশন পাবে।")

    seen = load_seen()

    while True:
        print(f"🔍 চেক করছি... {time.strftime('%H:%M:%S')}")
        offers = scrape_offers()

        new_count = 0
        for offer in offers:
            key = make_key(offer)
            if key not in seen:
                seen.add(key)
                new_count += 1
                msg = (
                    f"🔔 <b>নতুন Live Offer!</b>\n\n"
                    f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                    f"💰 <b>Points:</b> {offer.get('points', 'N/A')}\n"
                    f"📋 <b>Type:</b> {offer.get('type', 'N/A')}\n"
                    f"🔗 <a href='{URL}'>Live দেখো</a>"
                )
                send_telegram(msg)
                print(f"📨 পাঠানো: {offer.get('username')}")

        if new_count == 0:
            print("নতুন offer নেই।")

        save_seen(seen)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
