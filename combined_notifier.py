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
HEADERS   = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

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
    try:
        res = requests.get("https://apucash.com", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        blocks = soup.find_all(lambda tag: tag.has_attr("wire:key") and
                               re.match(r"activity-\d+", tag.get("wire:key", "")))
        if not blocks:
            blocks = soup.find_all(class_=re.compile(r"activity-item|feed-item|offer-row"))

        for block in blocks:
            try:
                text = block.get_text(" ", strip=True)
                pts_match = re.search(r"(\d+(?:\.\d+)?)", text)
                if not pts_match:
                    continue
                pts_val = float(pts_match.group(1))
                if pts_val < MIN_POINTS:
                    continue
                user_el = (block.find(class_=re.compile(r"user|name")) or
                           block.find("a") or block.find("span"))
                username = user_el.get_text(strip=True) if user_el else "?"
                key = make_key("apu", username, pts_match.group(0), text[:30])
                if key in seen:
                    continue
                seen.add(key)
                save_seen()
                send(
                    f"🟢 <b>ApuCash!</b>\n"
                    f"👤 <b>User:</b> {username}\n"
                    f"💰 <b>Points:</b> {pts_match.group(0)}\n"
                    f"📋 <b>Info:</b> {text[:80]}"
                )
                print(f"[ApuCash] {username} - {pts_match.group(0)}")
            except Exception:
                pass
    except Exception as e:
        print(f"[ApuCash] {e}")

def apucash_loop():
    while True:
        scrape_apucash()
        time.sleep(60)

# ========== PAIDCASH ==========
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

        # সব সম্ভাব্য coin/points key চেক
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
