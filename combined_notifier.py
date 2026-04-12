import requests
from bs4 import BeautifulSoup
import time
import json
import os
import re

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8617551433:AAFK1waCKiLv72SErBuf4iK0sduSahJONZo")
CHAT_ID = os.environ.get("CHAT_ID", "6881373105")

HUNTSKIN_URL = "https://huntskin.com/Liveoffersfinal/Live.php"
APUCASH_URL = "https://apucash.com"
SEEN_FILE = "seen_all_offers.json"
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
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def scrape_huntskin():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(HUNTSKIN_URL, headers=headers, timeout=15)
        print(f"Huntskin: {res.status_code}, len: {len(res.text)}")

        soup = BeautifulSoup(res.text, "html.parser")
        offers = []

        cards = soup.find_all("div", class_=re.compile(r"card|offer|item|row", re.I))
        if not cards:
            cards = soup.find_all("div")

        for card in cards:
            text = card.get_text(separator=" | ").strip()
            if "username" in text.lower() and "points" in text.lower():
                username_match = re.search(r'username\s*[|:]\s*(\S+)', text, re.I)
                points_match = re.search(r'points\s*[|:]\s*([\d.]+)', text, re.I)
                type_match = re.search(r'type\s*[|:]?\s*(.+?)(?:\s*\||\s*IP:|$)', text, re.I)

                if username_match:
                    offer = {
                        "site": "huntskin",
                        "username": username_match.group(1).strip(),
                        "points": points_match.group(1).strip() if points_match else "?",
                        "type": type_match.group(1).strip()[:80] if type_match else "?"
                    }
                    if offer not in offers:
                        offers.append(offer)

        print(f"Huntskin offers: {len(offers)}")
        return offers
    except Exception as e:
        print(f"Huntskin error: {e}")
        return []


def scrape_apucash():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(APUCASH_URL, headers=headers, timeout=15)
        print(f"Apucash: {res.status_code}, len: {len(res.text)}")

        soup = BeautifulSoup(res.text, "html.parser")
        offers = []

        # ticker/scrolling banner খোঁজা
        ticker_items = soup.find_all(class_=re.compile(r'ticker|scroll|live|activity|notification|feed|marquee|banner|recent|win', re.I))

        print(f"Apucash ticker items: {len(ticker_items)}")

        for item in ticker_items:
            text = item.get_text(separator=" ").strip()
            if text and len(text) > 3:
                parts = text.split()
                offer = {
                    "site": "apucash",
                    "raw": text[:100],
                    "username": parts[-2] if len(parts) >= 2 else "?",
                    "points": parts[-1] if parts else "?"
                }
                offers.append(offer)

        # যদি না পাওয়া যায়
        if not offers:
            # সব span/div এ username-like pattern খোঁজা
            all_elements = soup.find_all(["span", "div", "p"])
            for el in all_elements:
                text = el.get_text().strip()
                if re.search(r'\d+🪙|\d+\s*coins|\d+\s*points', text, re.I):
                    offer = {
                        "site": "apucash",
                        "raw": text[:100],
                        "username": "unknown",
                        "points": text[:50]
                    }
                    offers.append(offer)

        print(f"Apucash offers: {len(offers)}")
        return offers
    except Exception as e:
        print(f"Apucash error: {e}")
        return []


def make_key(offer):
    return f"{offer.get('site','')}_{offer.get('username','')}_{offer.get('points','')}_{offer.get('raw','')[:20]}"


def main():
    print("✅ Combined Notifier চালু হয়েছে...")
    send_telegram(
        "✅ <b>Live Offer Notifier চালু হয়েছে!</b>\n\n"
        "🎯 Monitoring:\n"
        "• Huntskin Live Offers\n"
        "• ApuCash Live Offers\n\n"
        "নতুন offer আসলে সাথে সাথে জানাবো!"
    )

    seen = load_seen()

    while True:
        print(f"\n🔍 চেক করছি... {time.strftime('%H:%M:%S')}")

        # দুটো সাইট চেক
        all_offers = scrape_huntskin() + scrape_apucash()

        new_count = 0
        for offer in all_offers:
            key = make_key(offer)
            if key not in seen:
                seen.add(key)
                new_count += 1

                site = offer.get('site', '')
                if site == "huntskin":
                    msg = (
                        f"🔔 <b>Huntskin নতুন Offer!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', 'N/A')}\n"
                        f"📋 <b>Type:</b> {offer.get('type', 'N/A')}\n"
                        f"🔗 <a href='{HUNTSKIN_URL}'>Huntskin দেখো</a>"
                    )
                else:
                    msg = (
                        f"🟢 <b>ApuCash নতুন Offer Complete!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', 'N/A')}\n"
                        f"📋 <b>Info:</b> {offer.get('raw', 'N/A')}\n"
                        f"🔗 <a href='{APUCASH_URL}'>ApuCash দেখো</a>"
                    )

                send_telegram(msg)
                print(f"📨 পাঠানো [{site}]: {offer.get('username')}")

        if new_count == 0:
            print("নতুন offer নেই।")

        save_seen(seen)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
