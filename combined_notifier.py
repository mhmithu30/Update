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
    """আপডেটেড ApuCash স্ক্র্যাপার - বাগ ফিক্স করা হয়েছে"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://apucash.com/",
            "Cache-Control": "no-cache"
        }
        
        print("Connecting to ApuCash...")
        res = requests.get(APUCASH_URL, headers=headers, timeout=20)
        print(f"ApuCash Status: {res.status_code}")
        
        if res.status_code != 200:
            print(f"ApuCash returned {res.status_code}")
            return []
        
        soup = BeautifulSoup(res.text, "html.parser")
        offers = []
        
        # পদ্ধতি 1: earning-feed-item ক্লাস
        items = soup.find_all("div", class_=re.compile(r"earning-feed-item|activity-item|offer-item|live-feed-item"))
        
        # পদ্ধতি 2: যদি উপরে না পায়, তাহলে সব div চেক করো
        if not items:
            print("Method 1 failed, trying Method 2...")
            all_divs = soup.find_all("div")
            items = [div for div in all_divs if div.find(text=re.compile(r"\$\d+|\d+\s*(?:points?|coins?)", re.I))]
        
        # পদ্ধতি 3: script ট্যাগে ডাটা খোঁজা
        if not items:
            print("Method 2 failed, trying Method 3...")
            scripts = soup.find_all("script")
            for script in scripts:
                if script.string and ('offers' in script.string or 'activities' in script.string):
                    try:
                        json_data = re.search(r'\{.*"offers".*\}', script.string, re.DOTALL)
                        if json_data:
                            print("Found JSON data in script")
                    except:
                        pass
        
        print(f"Found {len(items)} potential items on ApuCash")
        
        for item in items:
            try:
                # ইউজারনেম খোঁজা - বিভিন্ন সেলেক্টর চেক
                username = None
                username_patterns = [
                    ('a', {'class': re.compile(r'username|user-name|profile', re.I)}),
                    ('span', {'class': re.compile(r'username|user-name|name', re.I)}),
                    ('div', {'class': re.compile(r'username|user', re.I)}),
                    ('h6', {}),
                    ('p', {'class': re.compile(r'name|user', re.I)}),
                    ('strong', {})
                ]
                
                for tag, attrs in username_patterns:
                    elem = item.find(tag, attrs) if attrs else item.find(tag)
                    if elem and elem.get_text(strip=True):
                        username = elem.get_text(strip=True)
                        break
                
                if not username:
                    # টেক্সট থেকে ইউজারনেম বের করার চেষ্টা
                    text = item.get_text()
                    username_match = re.search(r'@?([A-Za-z0-9_]{3,20})', text)
                    if username_match:
                        username = username_match.group(1)
                    else:
                        continue  # এই আইটেম স্কিপ
                
                # পয়েন্টস খোঁজা
                points_val = 0
                points_str = None
                
                points_patterns = [
                    ('span', {'class': re.compile(r'points|amount|reward|coin', re.I)}),
                    ('div', {'class': re.compile(r'points|amount|reward', re.I)}),
                    ('p', {'class': re.compile(r'points', re.I)}),
                    ('b', {}),
                    ('strong', {})
                ]
                
                for tag, attrs in points_patterns:
                    elem = item.find(tag, attrs) if attrs else item.find(tag)
                    if elem:
                        text = elem.get_text(strip=True)
                        # বিভিন্ন ফরম্যাটে পয়েন্টস বের করা
                        match = re.search(r'[\$€£]?(\d+(?:\.\d+)?)\s*(?:points?|coins?|pts?)', text, re.I)
                        if not match:
                            match = re.search(r'(\d+(?:\.\d+)?)\s*\$', text)
                        if not match:
                            match = re.search(r'(\d+(?:\.\d+)?)', text)
                        
                        if match:
                            points_val = float(match.group(1))
                            points_str = match.group(0)
                            break
                
                if points_val == 0:
                    # পুরো টেক্সট থেকে খোঁজা
                    text = item.get_text()
                    match = re.search(r'[\$€£]?(\d+(?:\.\d+)?)\s*(?:points?|coins?)', text, re.I)
                    if match:
                        points_val = float(match.group(1))
                        points_str = match.group(0)
                    else:
                        match = re.search(r'(\d+(?:\.\d+)?)\s*\$', text)
                        if match:
                            points_val = float(match.group(1))
                            points_str = f"${points_val}"
                
                # মিনিমাম পয়েন্টস চেক
                if points_val >= MIN_POINTS and points_val > 0:
                    # অফার নেম খোঁজা
                    offer_name = "Activity"
                    title_elem = item.find(['h3', 'h4', 'h5', 'div', 'span'], 
                                          class_=re.compile(r'title|offer|name|description', re.I))
                    if title_elem:
                        offer_name = title_elem.get_text(strip=True)[:60]
                    else:
                        # প্রথম লাইনটি নাও
                        lines = item.get_text().strip().split('\n')
                        if lines and len(lines[0]) > 5:
                            offer_name = lines[0][:60]
                    
                    # সময় খোঁজা (যদি থাকে)
                    time_ago = ""
                    time_elem = item.find('span', class_=re.compile(r'time|ago|date', re.I))
                    if time_elem:
                        time_ago = time_elem.get_text(strip=True)
                    
                    offers.append({
                        "site": "apucash",
                        "username": username[:30],
                        "points": points_str or f"{points_val} points",
                        "points_val": points_val,
                        "offer_name": offer_name,
                        "time": time_ago,
                        "is_public": True
                    })
                    
                    print(f"✓ Found: {username} - {points_str}")
                    
            except Exception as e:
                continue
        
        print(f"ApuCash total offers found: {len(offers)}")
        return offers
        
    except requests.exceptions.Timeout:
        print("ApuCash timeout - site is slow")
        return []
    except requests.exceptions.ConnectionError:
        print("ApuCash connection error - site may be down")
        return []
    except Exception as e:
        print(f"ApuCash critical error: {type(e).__name__}: {e}")
        return []

def scrape_cashlyearn():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(CASHLYEARN_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        offers = []
        
        # CashlyEarn এর স্ট্রাকচার অনুযায়ী সেলেক্টর
        items = soup.find_all("div", class_=re.compile(r"offer|activity|earning", re.I))
        
        for item in items[:30]:  # লিমিট ৩০
            try:
                # ইউজারনেম
                username_elem = item.find(["a", "span", "div"], class_=re.compile(r"user|name", re.I))
                username = username_elem.get_text(strip=True) if username_elem else "Unknown"
                
                # পয়েন্টস
                points_elem = item.find(["span", "div", "b"], class_=re.compile(r"points|amount|reward", re.I))
                if points_elem:
                    points_text = points_elem.get_text(strip=True)
                    points_val = float(re.sub(r'[^\d.]', '', points_text)) if re.search(r'\d+', points_text) else 0
                    
                    if points_val >= MIN_POINTS and points_val > 0:
                        offers.append({
                            "site": "cashlyearn",
                            "username": username[:30],
                            "points": points_text,
                            "points_val": points_val
                        })
            except:
                continue
        
        print(f"CashlyEarn offers: {len(offers)}")
        return offers
    except Exception as e:
        print(f"CashlyEarn error: {e}")
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
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
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

def make_key(offer):
    site = offer.get('site', '')
    if site == "apucash":
        raw = f"apu_{offer.get('username', '')}_{offer.get('offer_name', '')}_{offer.get('points_val', 0)}"
        return "apu_" + hashlib.md5(raw.encode()).hexdigest()[:12]
    elif site == "paidcash":
        raw = f"pc_{offer.get('offerwall', '')}_{offer.get('username', '')}_{offer.get('points_val', 0)}"
        return "pc_" + hashlib.md5(raw.encode()).hexdigest()[:10]
    elif site == "splitdrop":
        raw = f"sd_{offer.get('offer_name', '')}_{offer.get('points_val', 0)}"
        return "sd_" + hashlib.md5(raw.encode()).hexdigest()[:10]
    elif site == "huntskin":
        raw = f"hs_{offer.get('username', '')}_{offer.get('points_val', 0)}"
        return "hs_" + hashlib.md5(raw.encode()).hexdigest()[:10]
    elif site == "cashlyearn":
        raw = f"ce_{offer.get('username', '')}_{offer.get('points_val', 0)}"
        return "ce_" + hashlib.md5(raw.encode()).hexdigest()[:10]
    else:
        raw = f"{offer.get('username', offer.get('offer_name', ''))}_{offer.get('points_val', 0)}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

def main():
    print("="*60)
    print("✅ Combined Offer Notifier চালু হয়েছে...")
    print("="*60)
    
    # বট টোকেন চেক
    if BOT_TOKEN == "8617551433:AAFK1waCKiLv72SErBuf4iK0sduSahJONZo":
        print("⚠️ Notice: You're using the old bot token. It may be expired.")
        print("⚠️ If notifications don't work, create a new bot from @BotFather")
    
    send_telegram(
        "✅ <b>Live Offer Notifier চালু হয়েছে!</b>\n\n"
        "🎯 Monitoring:\n"
        "🔴 Huntskin\n"
        "🟢 ApuCash (আপডেটেড - বাগ ফিক্স করা হয়েছে)\n"
        "🔵 CashlyEarn\n"
        "🟠 SplitDrop (min $3)\n"
        "🪙 PaidCash (min 200 coins)\n\n"
        f"{'⚡ Min Points Filter: ' + str(MIN_POINTS) if MIN_POINTS > 0 else '✅ সব offers দেখাবে'}\n"
        f"💰 SplitDrop minimum: ${SPLITDROP_MIN}\n"
        f"🪙 PaidCash minimum: {PAIDCASH_MIN_POINTS} coins"
    )

    seen = load_seen()
    print(f"📚 Loaded {len(seen)} seen offers")
    
    while True:
        print(f"\n🔍 Checking at {time.strftime('%H:%M:%S')}")
        
        # সব সাইট থেকে অফার সংগ্রহ
        all_offers = []
        all_offers += scrape_huntskin()
        all_offers += scrape_apucash()  # আপডেটেড ভার্সন
        all_offers += scrape_cashlyearn()
        all_offers += scrape_splitdrop()
        all_offers += scrape_paidcash()

        new_count = 0
        for offer in all_offers:
            key = make_key(offer)
            if key not in seen:
                seen.add(key)
                new_count += 1
                site = offer.get('site', '')
                
                if site == "apucash":
                    msg = (
                        f"🟢 <b>ApuCash Activity!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', '?')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', '?')}\n"
                        f"📋 <b>Offer:</b> {offer.get('offer_name', '?')}\n"
                        f"⏱ <b>Time:</b> {offer.get('time', 'Just now')}"
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
                        f"📋 <b>Offer:</b> {offer.get('offer_name', '?')}\n"
                        f"💰 <b>Reward:</b> {offer.get('points', '?')}"
                    )
                elif site == "huntskin":
                    msg = (
                        f"🔴 <b>Huntskin New Offer!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', '?')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', '?')}\n"
                        f"📋 <b>Type:</b> {offer.get('type', '?')}"
                    )
                else:  # cashlyearn
                    msg = (
                        f"🔵 <b>CashlyEarn Activity!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', '?')}\n"
                        f"💰 <b>Reward:</b> {offer.get('points', '?')}"
                    )

                if send_telegram(msg):
                    print(f"📨 Sent: [{site}] {offer.get('username', offer.get('offer_name', '?'))} - {offer.get('points', '?')}")
                else:
                    print(f"❌ Failed to send: {offer.get('username', '?')}")
                
                time.sleep(0.5)  # স্প্যাম এভয়েড

        if new_count == 0:
            print("📭 No new offers found")

        save_seen(seen)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
