import requests
from bs4 import BeautifulSoup
import time
import json
import os
import re
import hashlib
from collections import Counter
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8617551433:AAFK1waCKiLv72SErBuf4iK0sduSahJONZo")
CHAT_ID = os.environ.get("CHAT_ID", "6881373105")
MIN_POINTS = float(os.environ.get("MIN_POINTS", "101"))
SPLITDROP_MIN_USD = float(os.environ.get("SPLITDROP_MIN_USD", "0.101"))

HUNTSKIN_URL = "https://huntskin.com/Liveoffersfinal/Live.php"
APUCASH_URL = "https://apucash.com"
CASHLYEARN_URL = "https://cashlyearn.com"
SPLITDROP_URL = "https://splitdrop.com"
SEEN_FILE = "seen_all_offers.json"
CHECK_INTERVAL = 60
SUMMARY_INTERVAL = 7200  # 2 ঘন্টা = 7200 সেকেন্ড

SPLITDROP_COOKIE = os.environ.get("SPLITDROP_COOKIE", "_ga=GA1.1.1559469763.1737379837; userDataCookey=%7B%22success%22%3Atrue%2C%22id%22%3A89411%2C%22message%22%3A%22User%20signed%20in%22%2C%22balance%22%3A%22%240%22%2C%22token%22%3A%22290111%7ClMJ7jeJ8dbupwIy80HMD3zVZyY5ocY6E9621Xs8L%22%2C%22email%22%3A%22heymithu007%40gmail.com%22%2C%22username%22%3A%22heymithu007%22%7D; _gcl_au=1.1.298454473.1773238041; _ga_9PSQ3Y953S=GS2.1.s1773324576$o12$g1$t1773325254$j60$l0$h0; deviceType=%22Windows%22; LaVisitorId_c3BsaXRkcm9wLmxhZGVzay5jb20v=wji9kzp8jwvi34e3o9gklg0mmntkxdla; users_profile=true; XSRF-TOKEN=eyJpdiI6IndxQXVEb3dnUFVUbzF2V3hxVGRQMVE9PSIsInZhbHVlIjoiNDhQMmNFK2kwcDFxWFNrRnhiV0p6a1VRREpoa3dEbWpidFhRTWlPbnVJVW5pOU1HemRHK3l5RWg0K2V6eWpIUGFVN3diR25USzN6WkFYODZTby8vS2N6S2FLWkdyYkZONFJuSktNRmMwU1d4MEw1TmJ6aG9WMkpETkZwRmJYTTVObGhMWVVwMU5VY2lMQ0p0WVdNaU9pSTBaRGt6TURNd09UaGxNek13T1dRd1pXUXdaR1kwTWpZeE5qSXhJaXd3T1RjNE1EQXdZbVJtT0RabE9EWmtPV0ZrTW1FM1lXSmtPV0ZsWkdZNE1EQXhOemMwWVRFek5UY3hNall3WkRreVpqbGtaRFE1T1dZMVlXUTJNREJoWXpRMllXWmpNV0ppWkdJM05tSmtPR0ZqTnpBNE5XWTVZV1ZtWmpFek9UZzJJaXdpSW4wPSIsIm1hYyI6IjQ4YzMwMzdlNzg0YjM2NGQxNWExYjcyOGZkMTliZjU0ZTNmNGE2OWNmMTQwZDE1NmMxNDMxNjFmMWExMDhkNGEiLCJ0YWciOiIifQ%3D%3D; laravel_session=eyJpdiI6IlRjVnhRQ0daUnpYZCt2V3l1UTZFNHc9PSIsInZhbHVlIjoibFVkb2ZPUURydWU2aWprdkUwb1pjVjVZYlBWVTVFcFNaZ3VUQ2lIbkpNQnJEdks0Vkw0eUttdTJYUS9SMDFQU2dYMzJ2UWthQ1BRMEZjVTlFeTlYRW5sMFErUkV3SXVBdSt2Y3RDODZFMVY3WjVjVVRKL05HdnM0SUdxU1RjQVMiLCJtYWMiOiI2OWRiMzYyYTljZGE5NmM3MDBlNzgwNjU5ZjI5YWMxNWQ5MmE0ZjU2MWViNWU0NWZlNTA1OTM5OTQ0OWFmNjQxIiwidGFnIjoiIn0%3D")

# 2 ঘন্টার counter
huntskin_counter = Counter()
apucash_counter = Counter()
last_summary_time = time.time()


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


def send_summary():
    now = datetime.now().strftime("%H:%M")
    two_hours_ago = datetime.fromtimestamp(last_summary_time).strftime("%H:%M")

    medals = ["🥇", "🥈", "🥉"]
    msg = f"📊 <b>Top Offers Report</b>\n<i>({two_hours_ago} - {now})</i>\n\n"

    # Huntskin top 3
    if huntskin_counter:
        msg += "🔴 <b>Huntskin:</b>\n"
        for i, (offer, count) in enumerate(huntskin_counter.most_common(3)):
            msg += f"{medals[i]} {offer[:40]} → {count} বার\n"
    else:
        msg += "🔴 <b>Huntskin:</b> কোনো offer নেই\n"

    msg += "\n"

    # ApuCash top 3
    if apucash_counter:
        msg += "🟢 <b>ApuCash:</b>\n"
        for i, (offer, count) in enumerate(apucash_counter.most_common(3)):
            msg += f"{medals[i]} {offer[:40]} → {count} বার\n"
    else:
        msg += "🟢 <b>ApuCash:</b> কোনো offer নেই\n"

    send_telegram(msg)
    print("📊 Summary পাঠানো হয়েছে")

    # Counter reset করা
    huntskin_counter.clear()
    apucash_counter.clear()


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


def scrape_splitdrop():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"{SPLITDROP_URL}/offers",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": SPLITDROP_COOKIE
        }
        res = requests.get(f"{SPLITDROP_URL}/recentEarners", headers=headers, timeout=15)
        print(f"Splitdrop: {res.status_code}, len: {len(res.text)}")
        soup = BeautifulSoup(res.text, "html.parser")
        offers = []
        user_divs = soup.find_all("div", class_="user-detail")
        for div in user_divs:
            onclick = div.get("onclick", "")
            user_id_match = re.search(r'showMiniProfile\((\d+)\)', onclick)
            user_id = user_id_match.group(1) if user_id_match else "?"
            h5 = div.find("h5")
            provider = h5.get_text(strip=True) if h5 else "?"
            p = div.find("p", class_="text-grey")
            username = p.get_text(strip=True) if p else "?"
            money_div = div.find("div", class_="user-detail-money")
            if money_div:
                full_text = money_div.get_text(strip=True)
                amount_str = full_text.replace("$", "").replace(" ", "").strip()
                try:
                    amount_val = float(amount_str)
                except:
                    amount_val = 0
            else:
                amount_str = "?"
                amount_val = 0
            if username and amount_val >= SPLITDROP_MIN_USD:
                offers.append({
                    "site": "splitdrop",
                    "offer_id": f"sd_{user_id}_{amount_str}_{provider}",
                    "username": username,
                    "provider": provider,
                    "amount": f"${amount_str}",
                    "amount_val": amount_val
                })
        print(f"Splitdrop offers: {len(offers)}")
        return offers
    except Exception as e:
        print(f"Splitdrop error: {e}")
        return []


def make_key(offer):
    site = offer.get('site', '')
    if site == "apucash":
        return f"apu_{offer.get('offer_id', '')}"
    elif site == "cashlyearn":
        return f"cly_{offer.get('offer_id', '')}"
    elif site == "splitdrop":
        raw = offer.get('offer_id', '')
        return "sd_" + hashlib.md5(raw.encode()).hexdigest()[:12]
    else:
        raw = f"{offer.get('username','')}_{offer.get('points','')}_{offer.get('type','')}"
        return "hunt_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def main():
    global last_summary_time

    print("✅ Combined Notifier চালু হয়েছে...")
    send_telegram(
        "✅ <b>Live Offer Notifier চালু হয়েছে!</b>\n\n"
        "🎯 Monitoring:\n"
        "🔴 Huntskin\n"
        "🟢 ApuCash\n"
        "🔵 CashlyEarn\n"
        "🟡 SplitDrop\n\n"
        f"⚡ Min Points: {int(MIN_POINTS)} | Min $: ${SPLITDROP_MIN_USD}\n"
        "📊 প্রতি ২ ঘন্টায় Top 3 Summary আসবে"
    )

    seen = load_seen()
    last_summary_time = time.time()

    while True:
        print(f"\n🔍 চেক করছি... {time.strftime('%H:%M:%S')}")
        all_offers = scrape_huntskin() + scrape_apucash() + scrape_cashlyearn() + scrape_splitdrop()

        new_count = 0
        for offer in all_offers:
            key = make_key(offer)
            if key not in seen:
                seen.add(key)
                new_count += 1

                site = offer.get('site', '')

                # Counter update করা
                if site == "huntskin":
                    offer_name = offer.get('type', '?')
                    # Offer name clean করা (adtowall: Offername: Snakzy → Snakzy)
                    clean_name = re.sub(r'^.*?Offername:\s*', '', offer_name, flags=re.I).strip()
                    clean_name = re.sub(r'\s*\.\s*IP:.*$', '', clean_name).strip()
                    if not clean_name:
                        clean_name = offer_name[:40]
                    huntskin_counter[clean_name] += 1

                elif site == "apucash":
                    apucash_counter[offer.get('type', '?')] += 1

                # Telegram notification
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
                elif site == "cashlyearn":
                    msg = (
                        f"🔵 <b>CashlyEarn Activity!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💰 <b>Reward:</b> {offer.get('points', 'N/A')}\n"
                        f"📋 <b>Activity:</b> {offer.get('activity', 'N/A')}\n"
                        f"🎯 <b>Offer:</b> {offer.get('type', 'N/A')[:50]}"
                    )
                else:
                    msg = (
                        f"🟡 <b>SplitDrop নতুন Earning!</b>\n\n"
                        f"👤 <b>Username:</b> {offer.get('username', 'N/A')}\n"
                        f"💵 <b>Amount:</b> {offer.get('amount', 'N/A')}\n"
                        f"📋 <b>Provider:</b> {offer.get('provider', 'N/A')}"
                    )

                send_telegram(msg)
                print(f"📨 [{site}] {offer.get('username')} - {offer.get('amount', offer.get('points', '?'))}")

        if new_count == 0:
            print("নতুন offer নেই।")

        # ২ ঘন্টা হলে summary পাঠাও
        if time.time() - last_summary_time >= SUMMARY_INTERVAL:
            send_summary()
            last_summary_time = time.time()

        save_seen(seen)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
