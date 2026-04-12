import requests
from bs4 import BeautifulSoup
import time
import json
import os
import re
import hashlib

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8617551433:AAFK1waCKiLv72SErBuf4iK0sduSahJONZo")
CHAT_ID = os.environ.get("CHAT_ID", "6881373105")
MIN_POINTS = int(os.environ.get("MIN_POINTS", "100"))  # 100 এর নিচে show করবে না

HUNTSKIN_URL = "https://huntskin.com/Liveoffersfinal/Live.php"
APUCASH_URL = "https://apucash.com"
CASHLYEARN_URL = "https://cashlyearn.com"
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
        print(f"Apucash: {res.status_code}, len: {len(res.text)}")

        soup = BeautifulSoup(res.text, "html.parser")
        offers = []
        offer_blocks = soup.find_all("div", attrs={"wire:key": re.compile(r"^offer-\d+$")})

        for block in offer_blocks:
            offer_id = block.get("wire:key", "")
            h6 = block.find("h6")
            offer_type = h6.get_text(strip=True) if h6 else "?"
            p_hd = block.find("p", class_="hd")
            username = p_hd.get_text(strip=True) if p_hd else (block.find("img") or {}).get("alt", "?")
            amount_div = block.find("div", class_="offer-amount")
            points = amount_div.get_text(strip=True) if amount_div else "?"

            try:
                points_val = float(re.sub(r'[^\d.]', '', points))
            except:
                points_val = 0

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

            if points_val >= MIN_POINTS:
                offers.append({
                    "site": "apucash",
                    "offer_id": offer_id,
                    "username": username,
                    "type": offer_type,
                    "activity": activity,
                    "points": points,
                    "points_val": points_val
                })

        print(f"Apucash parsed: {len(offers)}")
        return offers
    except Exception as e:
        print(f"Apucash error: {e}")
        return []


def get_cashlyearn_token():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(f"{CASHLYEARN_URL}/earn", headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        csrf = soup.find("meta", attrs={"name": "csrf-token"})
        csrf_token = csrf.get("content", "") if csrf else ""

        live_component = soup.find("div", attrs={"wire:id": True, "x-intersect": True})
        if live_component:
            snapshot_str = live_component.get("wire:snapshot", "")
            wire_id = live_component.get("wire:id", "")
            return csrf_token, wire_id, snapshot_str

        return csrf_token, "", ""
    except Exception as e:
        print(f"Cashlyearn token error: {e}")
        return "", "", ""


def scrape_cashlyearn():
    try:
        csrf_token, wire_id, snapshot_str = get_cashlyearn_token()
        if not csrf_token or not wire_id:
            print("Cashlyearn: token not found")
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "X-CSRF-TOKEN": csrf_token,
            "X-Livewire": "true",
            "Referer": f"{CASHLYEARN_URL}/earn",
            "Origin": CASHLYEARN_URL
        }

        payload = {
            "_token": csrf_token,
            "components": [{
                "snapshot": snapshot_str,
                "updates": {},
                "calls": [{"path": "", "method": "__lazyLoad", "params": ["eyJkYXRhIjp7ImZvck1vdW50IjpbW10seyJzIjoiYXJyIn1dfSwibWVtbyI6eyJpZCI6IkRvMUptSml2UHNSTGRtcm1wZzZyIiwibmFtZSI6Il9fbW91bnRQYXJhbXNDb250YWluZXIifSwiY2hlY2tzdW0iOiI0ZWRjNzQ0ZTVkYmM5MjU4NWNjYjRjNTE5NDViZDIzMWU5ZDYwYzkyOGZiZjM3OGI1NTUzYTdjZTk2MTIxZDNlIn0="]}]
            }]
        }

        res = requests.post(f"{CASHLYEARN_URL}/livewire/update", headers=headers, json=payload, timeout=15)
        print(f"Cashlyearn: {res.status_code}, len: {len(res.text)}")

        if res.status_code != 200:
            return []

        data = res.json()
        offers = []

        for component in data.get("components", []):
            snap_data = component.get("snapshot", {})
            if isinstance(snap_data, str):
                try:
                    snap_data = json.loads(snap_data)
                except:
                    snap_data = {}

            live_leads = snap_data.get("data", {}).get("liveLeads", [])
            if isinstance(live_leads, list) and live_leads:
                for lead in live_leads:
                    if not isinstance(lead, dict):
                        continue

                    lead_id = lead.get("id", "")
                    user = lead.get("user", "?")
                    provider = lead.get("provider", "?")
                    offer_name = lead.get("offer_name", "?")
                    reward = lead.get("reward", 0)
                    is_cashout = lead.get("is_cashout", False)

                    try:
                        reward_val = float(str(reward))
                    except:
                        reward_val = 0

                    if reward_val >= MIN_POINTS:
                        activity = "💸 Cashout" if is_cashout else f"🎮 {provider}"
                        offers.append({
                            "site": "cashlyearn",
                            "offer_id": f"cly_{lead_id}",
                            "username": user,
                            "type": offer_name,
                            "activity": activity,
                            "points": str(reward),
                            "points_val": reward_val
                        })

        print(f"Cashlyearn offers: {len(offers)}")
        return offers
    except Exception as e:
        print(f"Cashlyearn error: {e}")
        return []


def make_key(offer):
    site = offer.get('site', '')
    if site == "apucash":
        return f"apu_{offer.get('offer_id', '')}"
    elif site == "cashlyearn":
        return f"cly_{offer.get('offer_id', '')}"
    else:
        raw = f"{offer.get('username','')}_{offer.get('points','')}_{offer.get('type','')}"
        return "hunt_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def main():
    print("✅ Combined Notifier চালু হয়েছে...")
    send_telegram(
        "✅ <b>Live Offer Notifier চালু হয়েছে!</b>\n\n"
        "🎯 Monitoring:\n"
        "🔴 Huntskin\n"
        "🟢 ApuCash\n"
        "🔵 CashlyEarn\n\n"
        f"⚡ Min Points: {MIN_POINTS}"
    )

    seen = load_seen()

    while True:
        print(f"\n🔍 চেক করছি... {time.strftime('%H:%M:%S')}")
        all_offers = scrape_huntskin() + scrape_apucash() + scrape_cashlyearn()

        new_count = 0
        for offer in all_offers:
            key = make_key(offer)
            if key not in seen:
                seen.add(key)
                new_count += 1

                site = offer.get('site', '')
                if site == "huntskin":
                    msg = (
                        f"🔴 <b>Huntskin নতুন Offer!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', 'N/A')}\n"
                        f"📋 <b>Type:</b> {offer.get('type', 'N/A')}"
                    )
                elif site == "apucash":
                    msg = (
                        f"🟢 <b>ApuCash Activity!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Points:</b> {offer.get('points', 'N/A')}\n"
                        f"📋 <b>Activity:</b> {offer.get('activity', 'N/A')}"
                    )
                else:
                    msg = (
                        f"🔵 <b>CashlyEarn Activity!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Reward:</b> {offer.get('points', 'N/A')}\n"
                        f"📋 <b>Activity:</b> {offer.get('activity', 'N/A')}\n"
                        f"🎯 <b>Offer:</b> {offer.get('type', 'N/A')[:50]}"
                    )

                send_telegram(msg)
                print(f"📨 [{site}] {offer.get('username')} - {offer.get('points')}")

        if new_count == 0:
            print("নতুন offer নেই।")

        save_seen(seen)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
