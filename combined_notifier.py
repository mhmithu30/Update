import requests
from bs4 import BeautifulSoup
import time
import json
import os
import re
import hashlib

# ========== এনভায়রনমেন্ট ভেরিয়েবল ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8617551433:AAFK1waCKiLv72SErBuf4iK0sduSahJONZo")
CHAT_ID = os.environ.get("CHAT_ID", "6881373105")
MIN_POINTS = int(os.environ.get("MIN_POINTS", "0"))
SPLITDROP_MIN = float(os.environ.get("SPLITDROP_MIN", "3.00"))
PAIDCASH_MIN_POINTS = int(os.environ.get("PAIDCASH_MIN_POINTS", "200"))

# ========== ওয়েবসাইট লিংক ==========
HUNTSKIN_URL = "https://huntskin.com/Liveoffersfinal/Live.php"
APUCASH_URL = "https://apucash.com"
CASHLYEARN_URL = "https://cashlyearn.com"
SPLITDROP_URL = "https://splitdrop.com/offers"
PAIDCASH_URL = "https://paidcash.co"

SEEN_FILE = "seen_all_offers.json"
CHECK_INTERVAL = 60

# Survey Walls ব্লকলিস্ট (PaidCash-এর জন্য)
SURVEY_WALLS_BLOCKLIST = [
    "theoremreach", "cpx research", "pollfish", "survey", "surveys"
]

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
        soup = BeautifulSoup(res.text, "html.parser")
        offers = []
        rows = soup.find_all("tr")
        for row in rows:
            username_td = row.find("td", attrs={"data-label": "username"})
            points_td = row.find("td", attrs={"data-label": "Points"})
            type_td = row.find("td", attrs={"data-label": "type"})
            if username_td and points_td:
                username = username_td.get_text(strip=True)
                points_str = points_td.get_text(strip=True)
                offer_type = type_td.get_text(strip=True) if type_td else "?"
                try:
                    points_val = float(points_str)
                except:
                    points_val = 0
                if username and points_val >= MIN_POINTS:
                    offers.append({
                        "site": "huntskin",
                        "username": username,
                        "points": points_str,
                        "points_val": points_val,
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
        soup = BeautifulSoup(res.text, "html.parser")
        offers = []

        # পাবলিক প্রোফাইল
        public_cards = soup.find_all("div", class_=re.compile(r"activity-item|offer-item"))
        for card in public_cards:
            try:
                username_elem = card.find("a", class_=re.compile(r"username"))
                username = username_elem.get_text(strip=True) if username_elem else "?"
                points_elem = card.find("span", class_=re.compile(r"points|amount"))
                points_str = points_elem.get_text(strip=True) if points_elem else "0"
                points_val = float(re.sub(r'[^\d.]', '', points_str))
                offerwall_elem = card.find("span", class_=re.compile(r"offerwall|wall"))
                offerwall = offerwall_elem.get_text(strip=True) if offerwall_elem else "?"
                offer_name_elem = card.find("span", class_=re.compile(r"offer-title|title"))
                offer_name = offer_name_elem.get_text(strip=True) if offer_name_elem else "?"
                time_elem = card.find("span", class_=re.compile(r"time|ago"))
                time_ago = time_elem.get_text(strip=True) if time_elem else "?"
                
                if points_val >= MIN_POINTS:
                    offers.append({
                        "site": "apucash",
                        "username": username,
                        "points": points_str,
                        "points_val": points_val,
                        "offerwall": offerwall,
                        "offer_name": offer_name,
                        "time": time_ago,
                        "is_public": True
                    })
            except:
                continue

        # প্রাইভেট প্রোফাইল
        private_blocks = soup.find_all("div", attrs={"wire:key": re.compile(r"^offer-\d+$")})
        for block in private_blocks:
            try:
                h6 = block.find("h6")
                activity = h6.get_text(strip=True) if h6 else "?"
                p_hd = block.find("p", class_="hd")
                username = p_hd.get_text(strip=True) if p_hd else "?"
                amount_div = block.find("div", class_="offer-amount")
                points = amount_div.get_text(strip=True) if amount_div else "?"
                points_val = float(re.sub(r'[^\d.]', '', points)) if points else 0
                
                if points_val >= MIN_POINTS:
                    offers.append({
                        "site": "apucash",
                        "username": username,
                        "points": points,
                        "points_val": points_val,
                        "activity": activity,
                        "is_public": False
                    })
            except:
                continue

        print(f"ApuCash offers: {len(offers)}")
        return offers
    except Exception as e:
        print(f"Apucash error: {e}")
        return []

def scrape_paidcash():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(PAIDCASH_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        offers = []
        
        items = soup.find_all("div", class_="earning-feed-item")
        
        for item in items:
            try:
                title_elem = item.find("p", class_="earning-feed-item-content-title")
                offerwall = title_elem.get_text(strip=True).lower() if title_elem else ""
                
                # Survey Walls বাদ দেওয়া
                is_survey_wall = any(keyword in offerwall for keyword in SURVEY_WALLS_BLOCKLIST)
                if is_survey_wall:
                    continue
                
                desc_elem = item.find("p", class_="earning-feed-item-content-description")
                username = desc_elem.get_text(strip=True) if desc_elem else "?"
                
                points_elem = item.find("p", class_="earning-feed-item-reward-amount")
                points_str = points_elem.get_text(strip=True) if points_elem else "0"
                points_val = float(re.sub(r'[^\d.]', '', points_str)) if points_str else 0
                
                # PaidCash-এর জন্য ২০০ পয়েন্টস ফিল্টার
                if points_val < PAIDCASH_MIN_POINTS:
                    continue
                
                # Offer Name খোঁজা
                offer_name = "?"
                parent = item.find_parent("div", class_=re.compile(r"earnFeed-item|feed-item"))
                if parent:
                    offer_name = parent.get("data-offer-name", "")
                
                offers.append({
                    "site": "paidcash",
                    "offerwall": title_elem.get_text(strip=True) if title_elem else "?",
                    "username": username,
                    "offer_name": offer_name,
                    "points": points_str,
                    "points_val": points_val,
                    "is_public": True
                })
            except:
                continue
        
        print(f"Paidcash offers (min {PAIDCASH_MIN_POINTS} pts): {len(offers)}")
        return offers
    except Exception as e:
        print(f"Paidcash error: {e}")
        return []

def scrape_splitdrop():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(SPLITDROP_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        offers = []
        
        cards = soup.find_all("div", class_=re.compile(r"offer-card|card"))
        for card in cards:
            try:
                title_elem = card.find("h3") or card.find("h4") or card.find("div", class_=re.compile(r"title"))
                reward_elem = card.find("span", class_=re.compile(r"reward|points|amount"))
                
                if not title_elem or not reward_elem:
                    continue
                
                offer_name = title_elem.get_text(strip=True)
                reward_text = reward_elem.get_text(strip=True)
                reward_val = float(re.sub(r'[^0-9.]', '', reward_text))
                
                if reward_val >= SPLITDROP_MIN:
                    offers.append({
                        "site": "splitdrop",
                        "offer_name": offer_name,
                        "points": f"${reward_val:.2f}",
                        "points_val": reward_val
                    })
            except:
                continue
        
        print(f"Splitdrop offers (>=${SPLITDROP_MIN}): {len(offers)}")
        return offers
    except Exception as e:
        print(f"Splitdrop error: {e}")
        return []

def scrape_cashlyearn():
    """আপনার আগের cashlyearn ফাংশন এখানে বসান"""
    return []

def make_key(offer):
    site = offer.get('site', '')
    if site == "apucash":
        if offer.get('is_public'):
            raw = f"{offer['username']}_{offer.get('offer_name', '')}_{offer['points']}"
        else:
            raw = f"apu_private_{offer.get('username', '')}_{offer.get('activity', '')}_{offer['points']}"
        return "apu_" + hashlib.md5(raw.encode()).hexdigest()[:12]
    elif site == "paidcash":
        raw = f"pc_{offer['offerwall']}_{offer['username']}_{offer['points']}"
        return "pc_" + hashlib.md5(raw.encode()).hexdigest()[:10]
    elif site == "splitdrop":
        raw = f"sd_{offer['offer_name']}_{offer['points']}"
        return "sd_" + hashlib.md5(raw.encode()).hexdigest()[:10]
    else:
        raw = f"{offer.get('username', offer.get('offer_name', ''))}_{offer.get('points', '')}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

def main():
    print("✅ Combined Notifier চালু হয়েছে...")
    send_telegram(
        "✅ <b>Live Offer Notifier চালু হয়েছে!</b>\n\n"
        "🎯 Monitoring:\n"
        "🔴 Huntskin\n"
        "🟢 ApuCash (Public+Private)\n"
        "🔵 CashlyEarn\n"
        "🟠 SplitDrop (min $3)\n"
        "🪙 PaidCash (min 200 coins, Offer Walls only)\n\n"
        f"{'⚡ Min Points Filter: ' + str(MIN_POINTS) if MIN_POINTS > 0 else '✅ সব offers দেখাবে'}\n"
        f"💰 SplitDrop minimum: ${SPLITDROP_MIN}\n"
        f"🪙 PaidCash minimum: {PAIDCASH_MIN_POINTS} coins"
    )

    seen = load_seen()
    while True:
        print(f"\n🔍 চেক করছি... {time.strftime('%H:%M:%S')}")
        all_offers = (scrape_huntskin() + scrape_apucash() + scrape_cashlyearn() + 
                      scrape_splitdrop() + scrape_paidcash())

        new_count = 0
        for offer in all_offers:
            key = make_key(offer)
            if key not in seen:
                seen.add(key)
                new_count += 1
                site = offer.get('site', '')
                
                if site == "apucash" and offer.get('is_public'):
                    msg = (
                        f"🟢 <b>ApuCash Activity! (Public)</b>\n\n"
                        f"👤 <b>Username:</b> {offer['username']}\n"
                        f"💰 <b>Points:</b> {offer['points']}\n"
                        f"🏢 <b>Offerwall:</b> {offer.get('offerwall', '?')}\n"
                        f"📋 <b>Offer:</b> {offer.get('offer_name', '?')}\n"
                        f"⏱ <b>Time:</b> {offer.get('time', '?')}"
                    )
                elif site == "apucash":
                    msg = (
                        f"🟢 <b>ApuCash Activity! (Private)</b>\n\n"
                        f"👤 <b>Username:</b> {offer['username']}\n"
                        f"💰 <b>Points:</b> {offer['points']}\n"
                        f"📋 <b>Activity:</b> {offer.get('activity', '?')}"
                    )
                elif site == "paidcash":
                    msg = (
                        f"🪙 <b>PaidCash Activity!</b>\n\n"
                        f"🏢 <b>Offerwall:</b> {offer.get('offerwall', '?')}\n"
                        f"👤 <b>Username:</b> {offer.get('username', '?')}\n"
                        f"📋 <b>Offer:</b> {offer.get('offer_name', '?')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', '?')}"
                    )
                elif site == "splitdrop":
                    msg = (
                        f"🟠 <b>SplitDrop (${SPLITDROP_MIN}+ Offer)</b>\n\n"
                        f"📋 <b>Offer:</b> {offer['offer_name']}\n"
                        f"💰 <b>Reward:</b> {offer['points']}"
                    )
                elif site == "huntskin":
                    msg = (
                        f"🔴 <b>Huntskin নতুন Offer!</b>\n\n"
                        f"👤 <b>Username:</b> {offer['username']}\n"
                        f"💰 <b>Points:</b> {offer['points']}\n"
                        f"📋 <b>Type:</b> {offer['type']}"
                    )
                else:  # cashlyearn
                    msg = (
                        f"🔵 <b>CashlyEarn Activity!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Reward:</b> {offer.get('points', 'N/A')}"
                    )

                send_telegram(msg)
                print(f"📨 [{site}] {offer.get('username', offer.get('offer_name', '?'))} - {offer.get('points', '?')}")

        if new_count == 0:
            print("নতুন offer নেই।")

        save_seen(seen)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
