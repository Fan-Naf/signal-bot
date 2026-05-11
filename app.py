import os
import json
import time
import requests
from flask import Flask, request, abort
from datetime import datetime

app = Flask(__name__)

# =========================
# ENV
# =========================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

DEPOSIT = float(os.getenv("DEPOSIT", 2000))
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 1))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_HOURS", 6)) * 3600

# =========================
# STATE
# =========================
STATE_FILE = "state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

STATE = load_state()

def is_cooldown(symbol):
    now = time.time()
    last = STATE.get(symbol, 0)
    if now - last < COOLDOWN_SECONDS:
        return True
    STATE[symbol] = now
    save_state(STATE)
    return False

# =========================
# SAFE
# =========================
def safe_float(x, default=0.0):
    try:
        return float(x)
    except:
        return default

# =========================
# TELEGRAM
# =========================
def send_telegram(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

# =========================
# LOGGING
# =========================
LOG_FILE = "trades_log.json"

def log_trade(data):
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 5_000_000:
        os.rename(LOG_FILE, "trades_log_old.json")

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

# =========================
# BTC TREND (NEW)
# =========================
def get_btc_trend():
    try:
        r = requests.get("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=50")
        data = r.json()

        closes = [float(c[4]) for c in data]

        ema50 = sum(closes[-50:]) / 50
        last = closes[-1]

        if last > ema50:
            return "UP"
        else:
            return "DOWN"

    except:
        return "UNKNOWN"

# =========================
# POSITION SIZE
# =========================
def calculate_position_size(balance, risk_percent, entry, stop):
    risk_amount = balance * (risk_percent / 100)
    risk_per_unit = abs(entry - stop)

    if risk_per_unit == 0:
        return 0

    size = risk_amount / risk_per_unit
    step = 0.001
    return round(size / step) * step

# =========================
# WEBHOOK
# =========================
@app.route('/webhook', methods=['POST'])
def webhook():

    if WEBHOOK_SECRET:
        secret = request.headers.get('X-Webhook-Secret') or request.args.get('secret')
        if secret != WEBHOOK_SECRET:
            abort(403)

    data = request.json

    try:
        symbol = data.get("symbol", "").upper()
        price = safe_float(data.get("price"))
        signal = data.get("signal", "").upper()

        atr = safe_float(data.get("atr"))
        atr_percent = safe_float(data.get("atr_percent"))
        ema_distance = safe_float(data.get("ema_distance"))
        range_position = safe_float(data.get("range_position"))

        if is_cooldown(symbol):
            return "cooldown active"

        # =========================
        # BTC FILTER
        # =========================
        btc_trend = get_btc_trend()
        btc_penalty = 0

        if signal == "LONG" and btc_trend == "DOWN":
            btc_penalty = -10
        elif signal == "SHORT" and btc_trend == "UP":
            btc_penalty = -10

        # =========================
        # SCORING (ORIGINAL + BTC)
        # =========================
        score = 0

        if ema_distance > 0.005: score += 30
        elif ema_distance > 0.002: score += 20
        else: score += 5

        if 0.004 < atr_percent < 0.015: score += 20
        elif atr_percent > 0.002: score += 10

        if 0.3 < range_position < 0.7: score += 20
        elif 0.2 < range_position < 0.8: score += 10
        else: score += 5

        score += 10
        if atr_percent > 0.02: score -= 10

        # BTC influence
        score += btc_penalty

        score = max(0, min(score, 100))

        if score < 60:
            return "skip - weak"

        decision = "TRADE" if score >= 75 else "CAREFUL"

        # =========================
        # STOPS + TP
        # =========================
        stop_distance = atr * (2.2 if score >= 80 else 1.5)

        if signal == "LONG":
            stop = price - stop_distance
            tp1 = price + stop_distance * 1.5
            tp2 = price + stop_distance * 2.5
        else:
            stop = price + stop_distance
            tp1 = price - stop_distance * 1.5
            tp2 = price - stop_distance * 2.5

        size = calculate_position_size(DEPOSIT, RISK_PERCENT, price, stop)

        # =========================
        # MESSAGE (UPDATED)
        # =========================
        text = f"""
📊 {symbol}

Signal: {signal}
BTC Trend: {btc_trend}

Score: {score}
Decision: {decision}

Entry: {price}
Stop: {round(stop, 4)}

TP1: {round(tp1, 4)} (закрыть 50%)
TP2: {round(tp2, 4)}

➡ После TP1:
- стоп в BE
- держим остаток

Size: {size}
        """.strip()

        send_telegram(text)

        # =========================
        # LOG
        # =========================
        log_trade({
            "time": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "signal": signal,
            "score": score,
            "btc_trend": btc_trend,
            "decision": decision
        })

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error", 500


@app.route('/')
def home():
    return "Bot v1.4 running 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)