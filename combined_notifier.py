import requests
import socketio
import hashlib
import json
import os
import re
import time
import threading
from bs4 import BeautifulSoup

# ========== CONFIG ==========
BOT_TOKEN  = os.environ.get("BOT_TOKEN",  "8617551433:AAFK1waCKiLv72SErBuf4iK0sduSahJONZo")
CHAT_ID    = os.environ.get("CHAT_ID",    "6881373105")
MIN_POINTS = float(os.environ.get("MIN_POINTS", "200"))

SEEN_FILE = "seen_offers.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

seen = set()
seen_lock = threading.Lock()

# ========== SEEN ==========
def load_seen():
    global seen
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            seen = set(json.load(f))

def save_seen():
    with seen_lock:
        with open(SEEN_FILE, "w") as f:
            json.dump(list(seen), f)

def make_key(*parts):
    return hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()

# ========== TELEGRAM ==========
def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"[TG] {e}")

# ========== HUNTSKIN ==========
def scrape_huntskin():
    try:
        res = requests.get(
            "https://huntskin.com/Liveoffersfinal/Live.php",
            headers=HEADERS, timeout=15
        )
        soup = BeautifulSoup(res.text, "html.parser")
        for row in soup.find_all("tr"):
            u = row.find("td", attrs={"data-label": "username"})
            p = row.find("td", attrs={"data-label": "Points"})
            t = row.find("td", attrs={"data-label": "type"})
            if not (u and p):
                continue
            username   = u.get_text(strip=True)
            pts_str    = p.get_text(strip=True)
            offer_type = t.get_text(strip=True) if t else "?"
            pts_val    = float(re.sub(r"[^\d.]", "", pts_str) or "0")
            if pts_val < MIN_POINTS:
                continue
            key = make_key("hs", username, pts_str, offer_type)
            if key in seen:
                continue
            seen.add(key)
            save_seen()
            send(
                f"🔴 <b>Huntskin!</b>\n"
                f"👤 <b>User:</b> {username}\n"
                f"💰 <b>Points:</b> {pts_str}\n"
                f"📋 <b>Offer:</b> {offer_type[:100]}"
            )
            print(f"[Huntskin] {username} - {pts_str}")
    except Exception as e:
        print(f"[Huntskin] {e}")

def huntskin_loop():
    while True:
        scrape_huntskin()
        time.sleep(60)

# ========== APUCASH ==========
def scrape_apucash():
    urls_to_try = [
        "https://apucash.com",
        "https://apucash.com/activity",
        "https://apucash.com/offers",
    ]
    html = None
    for url in urls_to_try:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.ok and len(r.text) > 500:
                html = r.text
                break
        except Exception as e:
            print(f"[ApuCash] Failed {url}: {e}")

    if not html:
        print("[ApuCash] Could not fetch any page")
        return

    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: wire:key activity blocks
    activity_blocks = soup.find_all(
        lambda tag: tag.has_attr("wire:key") and
        re.match(r"activity-\d+", tag.get("wire:key", ""))
    )

    for block in activity_blocks:
        try:
            user_el = (
                block.find(class_="username") or
                block.find(class_="user-name") or
                block.find("a", href=re.compile(r"/user/")) or
                block.find("span", class_=re.compile(r"user"))
            )
            username = user_el.get_text(strip=True) if user_el else "?"

            offer_el = (
                block.find(class_="offer-name") or
                block.find(class_="activity-name") or
                block.find("h5") or
                block.find("h6") or
                block.find("p", class_=re.compile(r"title|name"))
            )
            offer = offer_el.get_text(strip=True) if offer_el else "?"

            pts_el = (
                block.find(class_=re.compile(r"point|coin|reward|amount")) or
                block.find("span", class_=re.compile(r"pts|coins"))
            )
            pts_text = pts_el.get_text(strip=True) if pts_el else "0"
            pts_val  = float(re.sub(r"[^\d.]", "", pts_text) or "0")

            if pts_val < MIN_POINTS:
                continue

            key = make_key("apu", username, offer, pts_text)
            if key in seen:
                continue
            seen.add(key)
            save_seen()
            send(
                f"🟢 <b>ApuCash!</b>\n"
                f"👤 <b>User:</b> {username}\n"
                f"🎯 <b>Offer:</b> {offer}\n"
                f"💰 <b>Points:</b> {pts_text}"
            )
            print(f"[ApuCash] {username} - {pts_text}")
        except Exception:
            pass

    # Strategy 2: fallback
    if not activity_blocks:
        feed_items = (
            soup.find_all(class_=re.compile(r"activity-item|feed-item|offer-row|earn-item")) or
            soup.find_all("li", class_=re.compile(r"activity|offer"))
        )
        for item in feed_items:
            try:
                texts = [t.get_text(strip=True) for t in item.find_all(True) if t.get_text(strip=True)]
                username = texts[0] if texts else "?"
                offer    = texts[1] if len(texts) > 1 else "?"
                pts_match = re.search(r"(\d+(?:\.\d+)?)", item.get_text())
                pts_val  = float(pts_match.group(1)) if pts_match else 0
                pts_text = pts_match.group(0) if pts_match else "0"
                if pts_val < MIN_POINTS:
                    continue
                key = make_key("apu", username, offer, pts_text)
                if key in seen:
                    continue
                seen.add(key)
                save_seen()
                send(
                    f"🟢 <b>ApuCash!</b>\n"
                    f"👤 <b>User:</b> {username}\n"
                    f"🎯 <b>Offer:</b> {offer}\n"
                    f"💰 <b>Points:</b> {pts_text}"
                )
                print(f"[ApuCash] {username} - {pts_text}")
            except Exception:
                pass

def apucash_loop():
    while True:
        scrape_apucash()
        time.sleep(60)

# ========== PAIDCASH (Socket.io) ==========
sio = socketio.Client(logger=False, engineio_logger=False)

@sio.event
def connect():
    print("[PaidCash] Connected!")

@sio.event
def disconnect():
    print("[PaidCash] Disconnected!")

@sio.on("activityFeed")
def on_activity(data):
    try:
        print(f"[DEBUG] {json.dumps(data)[:300]}")
        if not isinstance(data, dict):
            return
        coins = (data.get("coins") or data.get("points") or
                 data.get("amount") or data.get("reward") or 0)
        pts_val = float(re.sub(r"[^\d.]", "", str(coins)) or "0")
        if pts_val < MIN_POINTS:
            return
        offerwall = (data.get("offerwall") or data.get("wall") or
                     data.get("source") or data.get("provider") or "?")
        username  = (data.get("username") or data.get("user") or
                     data.get("name") or "?")
        key = make_key("pc", offerwall, username, pts_val)
        if key in seen:
            return
        seen.add(key)
        save_seen()
        send(
            f"🪙 <b>PaidCash!</b>\n"
            f"🏢 <b>Offerwall:</b> {offerwall}\n"
            f"👤 <b>User:</b> {username}\n"
            f"💰 <b>Coins:</b> {int(pts_val)}"
        )
        print(f"[PaidCash] {username} - {pts_val}")
    except Exception as e:
        print(f"[PaidCash] {e}")

def paidcash_loop():
    while True:
        try:
            sio.connect(
                "https://servers.faucetify.io",
                socketio_path="/socket.io/",
                transports=["websocket", "polling"]
            )
            sio.wait()
        except Exception as e:
            print(f"[PaidCash connect] {e}")
            time.sleep(10)

# ========== MAIN ==========
def main():
    load_seen()
    send(
        "✅ <b>Combined Bot চালু!</b>\n"
        "🔴 Huntskin\n"
        "🟢 ApuCash\n"
        "🪙 PaidCash\n"
        f"💎 Min Points: {int(MIN_POINTS)}"
    )
    threading.Thread(target=huntskin_loop, daemon=True).start()
    threading.Thread(target=apucash_loop, daemon=True).start()
    paidcash_loop()

if __name__ == "__main__":
    main()
