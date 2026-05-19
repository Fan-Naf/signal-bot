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
# POSITION SIZE
# =========================
def calculate_position_size(balance, risk_percent, entry, stop):
    risk_amount = balance * (risk_percent / 100)
    risk_per_unit = abs(entry - stop)

    if risk_per_unit == 0:
        return 0

    return round(risk_amount / risk_per_unit, 3)

# =========================
# BTC PARSER
# =========================
def parse_btc_trend(value):
    try:
        v = float(value)
        if v == 1:
            return "UP"
        elif v == -1:
            return "DOWN"
    except:
        pass
    return "UNKNOWN"

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
        fg_value = data.get("fear_greed")

        btc_trend = parse_btc_trend(data.get("btc_trend"))
        btc_strength = safe_float(data.get("btc_strength"))
        eth_trend = "UP" if data.get("eth_trend") == 1 else "DOWN"

        now = time.time()

        # =========================
        # CLUSTER FILTER
        # =========================
        cluster = STATE.get("cluster", [])
        cluster = [t for t in cluster if now - t < 300]

        if len(cluster) >= 3:
            return "skip - cluster"

        cluster.append(now)
        STATE["cluster"] = cluster
        save_state(STATE)

        # =========================
        # VALIDATION
        # =========================
        if atr == 0:
            return "skip - bad atr"

        if btc_trend == "UNKNOWN":
            return "skip - no btc"

        # =========================
        # BASE SCORE
        # =========================
        score = 0

        score += 30 if ema_distance > 0.005 else 20 if ema_distance > 0.002 else 5
        score += 20 if 0.004 < atr_percent < 0.015 else 10 if atr_percent > 0.002 else 0
        score += 20 if 0.3 < range_position < 0.7 else 10 if 0.2 < range_position < 0.8 else 5
        score += 10

        if atr_percent > 0.02:
            score -= 10

        # =========================
        # CONTEXT v1.5
        # =========================
        context = 0

        context += 10 if (signal == "LONG" and btc_trend == "UP") or (signal == "SHORT" and btc_trend == "DOWN") else -10
        context += 10 if (signal == "LONG" and eth_trend == "UP") or (signal == "SHORT" and eth_trend == "DOWN") else -10

        if btc_strength > 0.003:
            context += 5

        score += context

        # =========================
        # MARKET REGIME v1.6
        # =========================
        if btc_strength < 0.002:
            regime = "NEUTRAL"
        elif btc_trend == "UP":
            regime = "BULL"
        else:
            regime = "BEAR"

        if regime == "BULL":
            score += 10 if signal == "LONG" else -10
        elif regime == "BEAR":
            score += 10 if signal == "SHORT" else -10
        else:
            score -= 10

        score = max(0, min(score, 100))

        if score < 65:
            return "skip - weak"

        decision = "TRADE" if score >= 75 else "CAREFUL"

        # =========================
        # TP / SL
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

        risk_distance = abs(price - stop)
        rr1 = abs(tp1 - price) / risk_distance if risk_distance else 0
        rr2 = abs(tp2 - price) / risk_distance if risk_distance else 0

        size = calculate_position_size(DEPOSIT, RISK_PERCENT, price, stop)

        # =========================
        # MESSAGE
        # =========================
        text = f"""
📊 СИГНАЛ — {symbol}

{signal}
📊 Score: {score}
🧠 Decision: {decision}
🌍 Regime: {regime}

📊 BTC: {btc_trend} | ETH: {eth_trend}

🎯 Entry: {price}
🛑 Stop: {round(stop, 6)}

⚖ RR: {round(rr1,2)} / {round(rr2,2)}

🎯 TP1: {round(tp1,6)}
🎯 TP2: {round(tp2,6)}

💰 Risk: ${round(DEPOSIT * RISK_PERCENT / 100, 2)}
📦 Size: {size}
        """.strip()

        send_telegram(text)

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error", 500


@app.route('/')
def home():
    return "Bot v1.6.1 running 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)