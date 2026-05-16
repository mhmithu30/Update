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
MIN_POINTS = int(os.environ.get("MIN_POINTS", "400"))
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
    """ApuCash - শুধু 400+ পয়েন্টস দেখাবে"""
    try:
        print("🔍 ApuCash চেক করা হচ্ছে...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        res = requests.get(APUCASH_URL, headers=headers, timeout=15)
        
        if res.status_code != 200:
            print(f"⚠️ ApuCash HTTP {res.status_code}")
            return []
        
        offers = []
        text = res.text
        
        # প্যাটার্ন 1: username + points
        pattern1 = r'([A-Za-z0-9_]{3,25}).*?(\d+(?:\.\d+)?)\s*(?:points?|coins?)'
        matches1 = re.findall(pattern1, text, re.I)
        
        for username, points in matches1:
            points_val = float(points)
            if points_val >= 400 and points_val > 0 and len(username) > 2:
                offers.append({
                    "site": "apucash",
                    "username": username,
                    "points": f"{points_val} points",
                    "points_val": points_val,
                    "offer_name": "Offer Completed",
                    "time": "Just now"
                })
                print(f"  ✓ {username} - {points_val} points (400+)")
        
        # প্যাটার্ন 2: ডলার সাইন সহ
        pattern2 = r'([A-Za-z0-9_]{3,25}).*?[\$](\d+(?:\.\d+)?)'
        matches2 = re.findall(pattern2, text, re.I)
        
        for username, points in matches2:
            dollar_val = float(points)
            points_val = dollar_val * 100
            already_added = any(o['username'] == username for o in offers)
            if not already_added and points_val >= 400 and points_val > 0:
                offers.append({
                    "site": "apucash",
                    "username": username,
                    "points": f"${dollar_val} (approx {points_val:.0f} points)",
                    "points_val": points_val,
                    "offer_name": "Offer Completed",
                    "time": "Just now"
                })
                print(f"  ✓ {username} - ${dollar_val} ({points_val:.0f} points)")
        
        filtered_offers = [o for o in offers if o['points_val'] >= 400]
        print(f"✅ ApuCash: {len(filtered_offers)} টি অফার (400+ points)")
        return filtered_offers
        
    except Exception as e:
        print(f"❌ ApuCash error: {e}")
        return []

def scrape_cashlyearn():
    """CashlyEarn স্ক্র্যাপার"""
    try:
        print("🔍 CashlyEarn চেক করা হচ্ছে...")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(CASHLYEARN_URL, headers=headers, timeout=15)
        
        if res.status_code != 200:
            print(f"⚠️ CashlyEarn HTTP {res.status_code}")
            return []
        
        soup = BeautifulSoup(res.text, "html.parser")
        offers = []
        
        # বিভিন্ন ক্লাস খোঁজা
        items = soup.find_all("div", class_=re.compile(r"offer|activity|earning|feed", re.I))
        
        for item in items[:30]:
            try:
                # ইউজারনেম খোঁজা
                username_elem = item.find(["a", "span", "div"], class_=re.compile(r"user|name|username", re.I))
                username = username_elem.get_text(strip=True) if username_elem else "?"
                
                # পয়েন্টস খোঁজা
                points_elem = item.find(["span", "div", "b"], class_=re.compile(r"points|amount|reward", re.I))
                if points_elem:
                    points_text = points_elem.get_text(strip=True)
                    points_val = float(re.sub(r'[^\d.]', '', points_text)) if re.search(r'\d+', points_text) else 0
                    
                    if points_val >= MIN_POINTS and points_val > 0:
                        offers.append({
                            "site": "cashlyearn",
                            "username": username[:30],
                            "points": points_text,
                            "points_val": points_val,
                            "offer_name": "Activity"
                        })
                        print(f"  ✓ {username} - {points_text}")
            except:
                continue
        
        print(f"✅ CashlyEarn: {len(offers)} টি অফার")
        return offers
    except Exception as e:
        print(f"❌ CashlyEarn error: {e}")
        return []

def scrape_paidcash():
    """PaidCash স্ক্র্যাপার - সম্পূর্ণ আপডেটেড ভার্সন"""
    try:
        print("🔍 PaidCash চেক করা হচ্ছে...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
        
        response = requests.get(PAIDCASH_URL, headers=headers, timeout=20)
        
        if response.status_code != 200:
            print(f"⚠️ PaidCash HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        offers = []
        
        # পদ্ধতি 1: earning-feed-item ক্লাস
        items = soup.find_all("div", class_="earning-feed-item")
        
        # পদ্ধতি 2: অন্যান্য সম্ভাব্য ক্লাস
        if not items:
            items = soup.find_all("div", class_=re.compile(r"(feed-item|offer-item|activity-item)", re.I))
        
        # পদ্ধতি 3: সরাসরি টেক্সট পার্সিং (Regex)
        if not items:
            print("  HTML পার্সিং fail, Regex পদ্ধতি ব্যবহার করা হচ্ছে...")
            text = response.text
            
            # প্যাটার্ন সমূহ
            patterns = [
                r'([A-Za-z0-9_@]{3,25})\s+(?:earned|got|received)\s+(\d+)\s+(?:points?|coins?)\s+(?:from|on)\s+([A-Za-z\s]+?)(?:\s|$|\.)',
                r'([A-Za-z0-9_@]{3,25}).*?(\d+)\s+points?.*?(?:offerwall|wall)\s+([A-Za-z\s]+?)(?:\s|$)',
                r'\$(\d+(?:\.\d+)?)\s+(?:earned|got).*?([A-Za-z0-9_@]{3,25}).*?(?:from|on)\s+([A-Za-z\s]+?)(?:\s|$)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.I)
                for match in matches:
                    try:
                        if len(match) == 3:
                            if match[0].replace('.', '').isdigit() or match[0].startswith('$'):
                                points_val = float(match[0].replace('$', '')) if match[0].replace('$', '').replace('.', '').isdigit() else 0
                                username = match[1]
                                offerwall = match[2]
                            else:
                                username = match[0]
                                points_val = float(match[1]) if match[1].isdigit() else 0
                                offerwall = match[2]
                            
                            if points_val >= PAIDCASH_MIN_POINTS and points_val > 0:
                                is_survey = any(keyword in offerwall.lower() for keyword in SURVEY_WALLS_BLOCKLIST)
                                if not is_survey:
                                    offers.append({
                                        "site": "paidcash",
                                        "username": username[:40],
                                        "points": f"{points_val} points",
                                        "points_val": points_val,
                                        "offerwall": offerwall.strip()[:50],
                                        "offer_name": offerwall.strip()[:50]
                                    })
                                    print(f"  ✓ Regex: {username} - {points_val} points")
                    except:
                        continue
        
        # পদ্ধতি 4: earning-feed-item থেকে ডাটা নেওয়া
        for item in items:
            try:
                title_elem = item.find("p", class_="earning-feed-item-content-title")
                offerwall = title_elem.get_text(strip=True).lower() if title_elem else ""
                
                is_survey_wall = any(keyword in offerwall for keyword in SURVEY_WALLS_BLOCKLIST)
                if is_survey_wall:
                    continue
                
                desc_elem = item.find("p", class_="earning-feed-item-content-description")
                username = desc_elem.get_text(strip=True) if desc_elem else "?"
                
                points_elem = item.find("p", class_="earning-feed-item-reward-amount")
                points_str = points_elem.get_text(strip=True) if points_elem else "0"
                points_val = float(re.sub(r'[^\d.]', '', points_str)) if points_str else 0
                
                if points_val >= PAIDCASH_MIN_POINTS and points_val > 0:
                    offer_name = title_elem.get_text(strip=True) if title_elem else "?"
                    
                    offers.append({
                        "site": "paidcash",
                        "offerwall": title_elem.get_text(strip=True) if title_elem else "?",
                        "username": username,
                        "offer_name": offer_name,
                        "points": points_str,
                        "points_val": points_val,
                        "is_public": True
                    })
                    print(f"  ✓ HTML: {username} - {points_str} ({offerwall[:30]})")
            except:
                continue
        
        # ডুপ্লিকেট রিমুভ
        unique_offers = []
        seen = set()
        for offer in offers:
            key = f"{offer.get('username', '')}_{offer.get('points_val', 0)}"
            if key not in seen:
                seen.add(key)
                unique_offers.append(offer)
        
        print(f"✅ PaidCash: {len(unique_offers)} টি অফার (min {PAIDCASH_MIN_POINTS} points)")
        return unique_offers
        
    except Exception as e:
        print(f"❌ PaidCash error: {e}")
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
        raw = f"pc_{offer.get('username', '')}_{offer.get('offerwall', '')}_{offer.get('points_val', 0)}"
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
    print("✅ Live Offer Notifier চালু হয়েছে...")
    print("🎯 মনিটরিং সাইট সমূহ:")
    print("  🔴 Huntskin")
    print("  🟢 ApuCash (400+ points)")
    print("  🔵 CashlyEarn")
    print("  🟠 SplitDrop ($3+)")
    print("  🪙 PaidCash (200+ coins)")
    print("="*60)
    
    send_telegram(
        "✅ <b>Live Offer Notifier চালু হয়েছে!</b>\n\n"
        "🎯 মনিটরিং:\n"
        "🔴 Huntskin\n"
        "🟢 ApuCash <b>(শুধু 400+ পয়েন্টস)</b>\n"
        "🔵 CashlyEarn\n"
        "🟠 SplitDrop (min $3)\n"
        "🪙 PaidCash (min 200 coins)\n\n"
        f"💰 ApuCash মিনিমাম: <b>400 পয়েন্টস</b>\n"
        f"💰 SplitDrop মিনিমাম: ${SPLITDROP_MIN}\n"
        f"🪙 PaidCash মিনিমাম: {PAIDCASH_MIN_POINTS} coins"
    )

    seen = load_seen()
    print(f"📚 লোড করা হয়েছে {len(seen)} টি পুরাতন অফার")
    
    while True:
        try:
            print(f"\n🔍 চেক করছি... {time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # সব সাইট থেকে অফার সংগ্রহ
            all_offers = []
            all_offers += scrape_huntskin()
            all_offers += scrape_apucash()
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
                            f"🟢 <b>ApuCash Activity! (400+ points)</b>\n\n"
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
                        print(f"📨 নোটিফিকেশন পাঠানো হয়েছে: [{site}] {offer.get('username', offer.get('offer_name', '?'))} - {offer.get('points', '?')}")
                    else:
                        print(f"❌ নোটিফিকেশন পাঠাতে ব্যর্থ: {offer.get('username', '?')}")
                    
                    time.sleep(0.5)  # স্প্যাম এভয়েড

            if new_count == 0:
                print("📭 কোনো নতুন অফার পাওয়া যায়নি")
            else:
                print(f"✨ {new_count} টি নতুন অফার পাওয়া গেছে এবং নোটিফিকেশন পাঠানো হয়েছে")

            save_seen(seen)
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n🛑 বন্ধ করা হচ্ছে...")
            send_telegram("🛑 Live Offer Notifier বন্ধ করা হয়েছে।")
            break
        except Exception as e:
            print(f"❌ মেইন লুপে এরর: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
