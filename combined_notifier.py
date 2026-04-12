import requests
from bs4 import BeautifulSoup
import time
import json
import os
import re
import hashlib

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

        # HTML table এর প্রতিটা row খোঁজা
        rows = soup.find_all("tr")
        print(f"Huntskin rows found: {len(rows)}")

        for row in rows:
            # data-label দিয়ে td খোঁজা
            username_td = row.find("td", attrs={"data-label": "username"})
            points_td = row.find("td", attrs={"data-label": "Points"})
            type_td = row.find("td", attrs={"data-label": "type"})

            if username_td and points_td:
                username = username_td.get_text(strip=True)
                points = points_td.get_text(strip=True)
                offer_type = type_td.get_text(strip=True) if type_td else "?"

                if username:
                    offers.append({
                        "site": "huntskin",
                        "username": username,
                        "points": points,
                        "type": offer_type[:80]
                    })

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

        # wire:key="offer-XXXXXX" দিয়ে সব offer block খোঁজা
        offer_blocks = soup.find_all("div", attrs={"wire:key": re.compile(r"^offer-\d+$")})
        print(f"Apucash offer blocks: {len(offer_blocks)}")

        for block in offer_blocks:
            offer_id = block.get("wire:key", "")

            h6 = block.find("h6")
            offer_type = h6.get_text(strip=True) if h6 else "?"

            p_hd = block.find("p", class_="hd")
            if p_hd:
                username = p_hd.get_text(strip=True)
            else:
                img = block.find("img")
                username = img.get("alt", "?") if img else "?"

            amount_div = block.find("div", class_="offer-amount")
            points = amount_div.get_text(strip=True) if amount_div else "?"

            if offer_type.lower() == "apucash":
                activity = "💸 Cashout"
            elif "sign" in offer_type.lower():
                activity = "🎁 Sign. Bonus"
            elif "daily" in offer_type.lower():
                activity = "📅 Daily Task"
            elif "adtowall" in offer_type.lower():
                activity = "📢 Adtowall"
            else:
                activity = f"🎮 {offer_type}"

            offers.append({
                "site": "apucash",
                "offer_id": offer_id,
                "username": username,
                "type": offer_type,
                "activity": activity,
                "points": points
            })

        print(f"Apucash parsed: {len(offers)}")
        return offers
    except Exception as e:
        print(f"Apucash error: {e}")
        return []


def make_key(offer):
    if offer.get('site') == "apucash":
        return f"apu_{offer.get('offer_id', '')}"
    else:
        # huntskin এ unique key: username+points+type hash
        raw = f"{offer.get('username','')}_{offer.get('points','')}_{offer.get('type','')}"
        return "hunt_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def main():
    print("✅ Combined Notifier চালু হয়েছে...")
    send_telegram(
        "✅ <b>Live Offer Notifier চালু হয়েছে!</b>\n\n"
        "🎯 Monitoring:\n"
        "🔴 Huntskin Live Offers\n"
        "🟢 ApuCash Live Offers\n\n"
        "নতুন offer আসলে সাথে সাথে জানাবো!"
    )

    seen = load_seen()

    while True:
        print(f"\n🔍 চেক করছি... {time.strftime('%H:%M:%S')}")
        all_offers = scrape_huntskin() + scrape_apucash()

        new_count = 0
        for offer in all_offers:
            key = make_key(offer)
            if key not in seen:
                seen.add(key)
                new_count += 1

                if offer.get('site') == "huntskin":
                    msg = (
                        f"🔴 <b>Huntskin নতুন Offer!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', 'N/A')}\n"
                        f"📋 <b>Type:</b> {offer.get('type', 'N/A')}\n"
                        f"🔗 <a href='{HUNTSKIN_URL}'>Huntskin দেখো</a>"
                    )
                else:
                    msg = (
                        f"🟢 <b>ApuCash Activity!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', 'N/A')}\n"
                        f"📋 <b>Activity:</b> {offer.get('activity', 'N/A')}\n"
                        f"🔗 <a href='{APUCASH_URL}'>ApuCash দেখো</a>"
                    )

                send_telegram(msg)
                print(f"📨 [{offer.get('site')}] {offer.get('username')} - {offer.get('points')}")

        if new_count == 0:
            print("নতুন offer নেই।")

        save_seen(seen)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
