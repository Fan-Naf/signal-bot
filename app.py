import os
import json
import time
import requests
from flask import Flask, request, abort
from datetime import datetime

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

DEPOSIT = float(os.getenv("DEPOSIT", 2000))
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 1))

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
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

def calculate_position_size(balance, risk_percent, entry, stop):
    risk_amount = balance * (risk_percent / 100)
    risk_per_unit = abs(entry - stop)
    return round(risk_amount / risk_per_unit, 3) if risk_per_unit else 0

def parse_btc_trend(value):
    try:
        v = float(value)
        return "UP" if v == 1 else "DOWN"
    except:
        return "UNKNOWN"

def get_funding(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
        r = requests.get(url, timeout=5).json()
        return float(r.get("lastFundingRate", 0))
    except:
        return 0

@app.route('/webhook', methods=['POST'])
def webhook():

    if WEBHOOK_SECRET:
        secret = request.headers.get('X-Webhook-Secret')
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

        btc_trend = parse_btc_trend(data.get("btc_trend"))
        btc_strength = safe_float(data.get("btc_strength"))
        eth_trend = "UP" if data.get("eth_trend") == 1 else "DOWN"

        now = time.time()

        # =========================
        # CLUSTER FILTER (НЕ ТРОГАЕМ)
        # =========================
        cluster = STATE.get("cluster", [])
        cluster = [t for t in cluster if now - t < 300]

        if len(cluster) >= 3:
            return "skip - cluster"

        cluster.append(now)
        STATE["cluster"] = cluster
        save_state(STATE)

        # =========================
        # VALIDATION (НЕ ТРОГАЕМ)
        # =========================
        if atr == 0:
            return "skip - bad atr"

        if btc_trend == "UNKNOWN":
            return "skip - no btc"

        # =========================
        # BASE SCORE (НЕ ТРОГАЕМ)
        # =========================
        score = 0

        score += 30 if ema_distance > 0.005 else 20 if ema_distance > 0.002 else 5
        score += 20 if 0.004 < atr_percent < 0.015 else 10 if atr_percent > 0.002 else 0
        score += 20 if 0.3 < range_position < 0.7 else 10 if 0.2 < range_position < 0.8 else 5
        score += 10

        if atr_percent > 0.02:
            score -= 10

        # =========================
        # CONTEXT (ОСЛАБЛЕН)
        # =========================
        context = 0

        context += 10 if (signal == "LONG" and btc_trend == "UP") or (signal == "SHORT" and btc_trend == "DOWN") else -10

        # ETH (было ±7 → стало ±5)
        context += 5 if (signal == "LONG" and eth_trend == "UP") or (signal == "SHORT" and eth_trend == "DOWN") else -5

        if btc_strength > 0.003:
            context += 5

        # =========================
        # FUNDING (ТОЛЬКО БОНУС)
        # =========================
        funding = get_funding(symbol)

        if funding > 0.01 and signal == "SHORT":
            context += 5

        elif funding < -0.01 and signal == "LONG":
            context += 5

        score += context

        # =========================
        # MARKET REGIME (НЕ ШТРАФУЕТ)
        # =========================
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
        # NEUTRAL → 0

        score = max(0, min(score, 100))

        # =========================
        # ОСЛАБЛЕННЫЙ ПОРОГ
        # =========================
        if score < 55:
            return "skip - weak"

        decision = "TRADE" if score >= 75 else "CAREFUL"

        # =========================
        # TP / SL (НЕ ТРОГАЕМ)
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
        # VISUAL (НЕ ТРОГАЕМ)
        # =========================
        icon = "🟢" if signal == "LONG" else "🔴"

        if score >= 80:
            rating = "A+ 🔥"
            confidence = "HIGH"
        elif score >= 70:
            rating = "B"
            confidence = "MEDIUM"
        else:
            rating = "C"
            confidence = "LOW"

        phase = "STRONG TREND 🚀" if ema_distance > 0.005 else "TREND"

        text = f"""
📊 СИГНАЛ — {symbol}

{icon} {signal}
📊 Рейтинг: {score}/100 ({rating})
🧠 Решение: {decision}
🛰 Фаза: {phase}
📡 Confidence: {confidence}

🌍 Режим рынка: {regime}
📊 BTC: {btc_trend} | ETH: {eth_trend}
💸 Funding: {round(funding,5)}

📈 ATR: {round(atr, 2)}

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

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error", 500


@app.route('/')
def home():
    return "Bot v1.7 running 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)