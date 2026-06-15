import os
import json
import time
import requests
import threading
from flask import Flask, request, abort

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

DEPOSIT = float(os.getenv("DEPOSIT", 2000))
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 1))

STATE_FILE = "state.json"

WHITELIST = {
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
    "INJUSDT","AVAXUSDT","LINKUSDT","OPUSDT","ZECUSDT"
}

FUNDING_CACHE = {}

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

STATE = load_state()

def safe_float(x, default=0.0):
    try:
        return float(x)
    except:
        return default

def send_telegram(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=5
        )
    except Exception as e:
        print("Telegram error:", e)

def calculate_position_size(balance, risk_percent, entry, stop):
    risk_amount = balance * (risk_percent / 100)
    risk_per_unit = abs(entry - stop)

    if risk_per_unit < entry * 0.001:
        return 0

    return round(risk_amount / risk_per_unit, 3)

def parse_btc_trend(value):
    try:
        return "UP" if float(value) == 1 else "DOWN"
    except:
        return "UNKNOWN"

def get_funding(symbol):
    now = time.time()

    if symbol in FUNDING_CACHE:
        ts, val = FUNDING_CACHE[symbol]
        if now - ts < 120:
            return val

    try:
        url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
        r = requests.get(url, timeout=2).json()
        val = float(r.get("lastFundingRate", 0))
        FUNDING_CACHE[symbol] = (now, val)
        return val
    except:
        return 0


def process_signal(data):

    try:
        symbol = data.get("symbol", "").upper().replace("BINANCE:", "")

        if symbol not in WHITELIST:
            return

        price = safe_float(data.get("price"))
        signal = data.get("signal", "").upper()

        atr = safe_float(data.get("atr"))
        atr_percent = safe_float(data.get("atr_percent"))
        ema_distance = safe_float(data.get("ema_distance"))
        range_position = safe_float(data.get("range_position"))

        btc_trend = parse_btc_trend(data.get("btc_trend"))
        btc_strength = safe_float(data.get("btc_strength"))
        eth_trend = "UP" if data.get("eth_trend") == 1 else "DOWN"

        now = time.time()

        cluster = STATE.get("cluster", [])
        cluster = [t for t in cluster if now - t < 300]

        if len(cluster) >= 3:
            return

        cluster.append(now)
        STATE["cluster"] = cluster
        save_state(STATE)

        if atr == 0 or btc_trend == "UNKNOWN":
            return

        # SCORE
        score = 0

        score += 30 if ema_distance > 0.005 else 20 if ema_distance > 0.002 else 5
        score += 20 if 0.004 < atr_percent < 0.015 else 10 if atr_percent > 0.002 else 0
        score += 20 if 0.3 < range_position < 0.7 else 10 if 0.2 < range_position < 0.8 else 5
        score += 10

        if atr_percent > 0.02:
            score -= 10

        context = 0

        context += 10 if (signal == "LONG" and btc_trend == "UP") or (signal == "SHORT" and btc_trend == "DOWN") else -10
        context += 5 if (signal == "LONG" and eth_trend == "UP") or (signal == "SHORT" and eth_trend == "DOWN") else -5

        if btc_strength > 0.003:
            context += 5

        if btc_strength < 0.0015:
            context -= 10

        funding = get_funding(symbol)

        if funding > 0.01 and signal == "SHORT":
            context += 5
        elif funding < -0.01 and signal == "LONG":
            context += 5

        score += context

        # REGIME
        if btc_strength < 0.002:
            regime = "NEUTRAL"
        elif btc_trend == "UP":
            regime = "BULL"
        else:
            regime = "BEAR"

        if regime == "BULL":
            score += 10 if signal == "LONG" else 0
        elif regime == "BEAR":
            score += 10 if signal == "SHORT" else 0

        score = max(0, min(score, 100))

        if score < 60:
            return

        decision = "TRADE" if score >= 75 else "CAREFUL"

        # TP / SL
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

        if risk_distance / price < 0.002:
            return

        rr1 = abs(tp1 - price) / risk_distance if risk_distance else 0
        rr2 = abs(tp2 - price) / risk_distance if risk_distance else 0

        if rr1 < 1.3:
            return

        size = calculate_position_size(DEPOSIT, RISK_PERCENT, price, stop)

        icon = "🟢" if signal == "LONG" else "🔴"

        text = f"""
📊 СИГНАЛ — {symbol}

{icon} {signal}
📊 Рейтинг: {score}/100
🧠 Решение: {decision}

🌍 Режим: {regime}
📊 BTC: {btc_trend} | ETH: {eth_trend}
💸 Funding: {round(funding,5)}

📈 ATR: {round(atr, 4)}

🎯 Вход: {price}
🛑 Стоп: {round(stop, 6)}

⚖ RR: {round(rr1,2)} / {round(rr2,2)}

🎯 Тейки:
TP1: {round(tp1,6)}
TP2: {round(tp2,6)}

💰 Риск: ${round(DEPOSIT * RISK_PERCENT / 100, 2)}
📦 Объём: {size}
        """.strip()

        send_telegram(text)

    except Exception as e:
        print("PROCESS ERROR:", e)


@app.route('/webhook', methods=['POST'])
def webhook():

    if WEBHOOK_SECRET:
        if request.headers.get('X-Webhook-Secret') != WEBHOOK_SECRET:
            abort(403)

    data = request.json

    threading.Thread(target=process_signal, args=(data,)).start()

    return "ok"


@app.route('/')
def home():
    return "Bot v1.10 running 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)