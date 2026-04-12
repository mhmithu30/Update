import requests
from bs4 import BeautifulSoup
import time
import json
import os

# ==========================================
# তোমার নিজের Token আর Chat ID এখানে বসাও
# ==========================================
BOT_TOKEN = "AAFK1waCKiLv72SErBuf4iK0sduSahJONZo"
CHAT_ID = "8617551433"
# ==========================================

URL = "https://huntskin.com/Liveoffersfinal/Live.php"
SEEN_FILE = "seen_offers.json"
CHECK_INTERVAL = 60  # প্রতি ৬০ সেকেন্ডে চেক করবে


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
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


def fetch_offers():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(URL, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        offers = []
        cards = soup.find_all("div", class_="card") or soup.find_all("div", style=True)

        # সব text block খোঁজা
        blocks = soup.get_text(separator="\n").split("\n")
        blocks = [b.strip() for b in blocks if b.strip()]

        # username দিয়ে group করা
        current = {}
        for line in blocks:
            if line.startswith("username") or "username" in line.lower():
                if current:
                    offers.append(current.copy())
                current = {}
            if current is not None:
                if "username" in line.lower() and len(line) < 30:
                    continue
                if "points" in line.lower():
                    current["points"] = line
                elif "type" in line.lower():
                    current["type"] = line
                elif "offer wall" in line.lower():
                    current["offer_wall"] = line
                else:
                    current["username"] = line

        if current:
            offers.append(current)

        return offers
    except Exception as e:
        print(f"Fetch error: {e}")
        return []


def scrape_offers():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(URL, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        offers = []
        # সব card/row এর মতো div খোঁজা
        all_text = soup.get_text(separator="|||")
        
        # প্রতিটা offer এর unique key বানানো
        import re
        usernames = re.findall(r'username\s*\|\|\|([^\|]+)', all_text, re.IGNORECASE)
        points = re.findall(r'Points\s*\|\|\|([^\|]+)', all_text, re.IGNORECASE)
        types = re.findall(r'type([^\|]+)', all_text, re.IGNORECASE)
        
        for i in range(len(usernames)):
            offer = {
                "username": usernames[i].strip() if i < len(usernames) else "Unknown",
                "points": points[i].strip() if i < len(points) else "?",
                "type": types[i].strip()[:100] if i < len(types) else "?"
            }
            offers.append(offer)
        
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
                print(f"📨 পাঠানো হয়েছে: {offer.get('username')}")

        if new_count == 0:
            print("কোনো নতুন offer নেই।")

        save_seen(seen)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
