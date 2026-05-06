from flask import Flask, request, abort
import requests
import time
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Загружаем настройки из .env
load_dotenv()

app = Flask(__name__)

# =========================
# НАСТРОЙКИ
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

DEPOSIT = float(os.getenv("DEPOSIT", 2000))
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 1))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_HOURS", 6)) * 3600

ALLOWED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LINKUSDT",
    "AVAXUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "FETUSDT"
}

LAST_SIGNAL_TIME = {}

# =========================
# TELEGRAM
# =========================
def send_telegram(text):
    print("👉 SEND TELEGRAM CALLED")
    print("TOKEN:", TELEGRAM_TOKEN)
    print("CHAT_ID:", TELEGRAM_CHAT_ID)

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10
        )
        print("Telegram response:", response.text)
    except Exception as e:
        print(f"Telegram error: {e}")

# =========================
# LOGGING
# =========================
def log_trade(data):
    try:
        with open("trades_log.json", "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Log error: {e}")

# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================
def get_fear_greed():
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        response = requests.get(url, timeout=5)
        data = response.json()
        value = int(data["data"][0]["value"])
        classification = data["data"][0]["value_classification"]
        return value, classification
    except:
        return None, "no data"

def get_market_phase(atr_percent, ema_distance):
    if atr_percent < 0.004:
        return "FLAT ❄️"
    if ema_distance > 0.005:
        return "STRONG TREND 🚀"
    if ema_distance > 0.003:
        return "TREND 📈"
    return "WEAK ⚠️"

def get_confidence(score):
    if score >= 80:
        return "HIGH"
    elif score >= 60:
        return "MEDIUM"
    else:
        return "LOW"

# =========================
# WEBHOOK
# =========================
@app.route('/webhook', methods=['POST'])
def webhook():
    # Защита от посторонних
    if WEBHOOK_SECRET:
        secret = request.headers.get('X-Webhook-Secret') or request.args.get('secret')
        if secret != WEBHOOK_SECRET:
            abort(403)

    data = request.json
    if not data:
        return "no data"

    try:
        symbol = data.get("symbol", "").replace(".P", "").upper()
        price = float(data.get("price", 0))
        signal = data.get("signal", "").upper()
        atr = float(data.get("atr", 0))

        atr_percent = float(data.get("atr_percent", 0))
        ema_distance = float(data.get("ema_distance", 0))
        range_position = float(data.get("range_position", 0))

        now = time.time()

        if symbol not in ALLOWED_SYMBOLS:
            return "skip symbol"
        if price <= 0 or atr <= 0 or signal not in ["LONG", "SHORT"]:
            return "invalid data"

        if symbol in LAST_SIGNAL_TIME and now - LAST_SIGNAL_TIME[symbol] < COOLDOWN_SECONDS:
            return "cooldown active"

        market_phase = get_market_phase(atr_percent, ema_distance)

        if atr_percent < 0.004:
            return "skip - low volatility"
        if ema_distance < 0.003:
            return "skip - weak trend"

        if signal == "SHORT" and range_position < 0.2:
            return "short at bottom"
        if signal == "LONG" and range_position > 0.8:
            return "long at top"

        # Scoring
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
        score = max(0, min(score, 100))

        if score < 60:
            return "skip - weak signal"

        decision = "TRADE" if score >= 75 else "CAREFUL"
        confidence = get_confidence(score)

        if score >= 80:
            rating = "A+ 🔥"
        elif score >= 60:
            rating = "B ⚙️"
        else:
            rating = "C ⚠️"

        # Stop & Take Profit
        stop_distance = atr * (2.2 if score >= 80 else 1.5)
        entry = price

        if signal == "LONG":
            stop = entry - stop_distance
            tp1 = entry + stop_distance * 1.5
            tp2 = entry + stop_distance * 2.5
        else:
            stop = entry + stop_distance
            tp1 = entry - stop_distance * 1.5
            tp2 = entry - stop_distance * 2.5

        risk_distance = abs(entry - stop)
        risk_amount = DEPOSIT * (RISK_PERCENT / 100)
        position_size = risk_amount / risk_distance

        fg_value, fg_label = get_fear_greed()
        fg_text = f"\n🧠 Рынок: {fg_value} ({fg_label})" if fg_value is not None else ""

        rr1 = abs(tp1 - entry) / risk_distance
        rr2 = abs(tp2 - entry) / risk_distance

        LAST_SIGNAL_TIME[symbol] = now

        log_trade({
            "time": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "atr_percent": atr_percent,
            "ema_distance": ema_distance
        })

        icon = "🟢" if signal == "LONG" else "🔴"

        text = f"""
📊 СИГНАЛ — {symbol}

{icon} {signal}
📊 Рейтинг: {score}/100 ({rating})
🧠 Решение: {decision}
📡 Фаза: {market_phase}
📊 Confidence: {confidence}{fg_text}

🎯 Вход: {entry:.6f}
🛑 Стоп: {stop:.6f}
⚖️ RR: {rr1:.2f} / {rr2:.2f}

TP1: {tp1:.6f}
TP2: {tp2:.6f}

💰 Риск: ${risk_amount:.2f}
📦 Объём: {position_size:.4f}
        """.strip()

        send_telegram(text)
        return "ok"

    except Exception as e:
        print("Error:", e)
        return "error", 500


@app.route('/')
def home():
    return "Bot v1.2 is running ✅"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)