import socketio
import requests
import hashlib
import json
import os
import re
import time

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8617551433:AAFK1waCKiLv72SErBuf4iK0sduSahJONZo")
CHAT_ID = os.environ.get("CHAT_ID", "6881373105")
MIN_COINS = int(os.environ.get("MIN_COINS", "20"))
SEEN_FILE = "seen_paidcash.json"

SURVEY_BLOCK = ["theoremreach", "cpx research", "pollfish", "survey"]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"TG error: {e}")

seen = load_seen()
sio = socketio.Client(logger=False, engineio_logger=False)

@sio.event
def connect():
    print("Connected!")
    send_telegram("✅ <b>PaidCash Bot চালু!</b>\n🪙 Min coins: " + str(MIN_COINS))

@sio.event
def disconnect():
    print("Disconnected!")

@sio.on("*")
def catch_all(event, data):
    print(f"[{event}] {str(data)[:200]}")
    try:
        text = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
        pts_match = re.search(r"(\d+(?:\.\d+)?)", text)
        pts_val = float(pts_match.group(1)) if pts_match else 0
        if pts_val < MIN_COINS:
            return

        offerwall = data.get("offerwall", data.get("wall", data.get("source", "?"))) if isinstance(data, dict) else "?"
        if any(b in str(offerwall).lower() for b in SURVEY_BLOCK):
            return

        username = data.get("username", data.get("user", "?")) if isinstance(data, dict) else "?"
        coins = data.get("coins", data.get("points", data.get("amount", pts_val))) if isinstance(data, dict) else pts_val

        key = hashlib.md5(f"{event}_{offerwall}_{username}_{coins}".encode()).hexdigest()
        if key in seen:
            return
        seen.add(key)
        save_seen(seen)

        send_telegram(
            f"🪙 <b>PaidCash!</b>\n"
            f"🎯 <b>Event:</b> {event}\n"
            f"🏢 <b>Offerwall:</b> {offerwall}\n"
            f"👤 <b>User:</b> {username}\n"
            f"💰 <b>Coins:</b> {coins}"
        )
    except Exception as e:
        print(f"Error: {e}")

def main():
    while True:
        try:
            sio.connect(
                "https://servers.faucetify.io",
                socketio_path="/socket.io/",
                transports=["websocket", "polling"]
            )
            sio.wait()
        except Exception as e:
            print(f"Connection error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
