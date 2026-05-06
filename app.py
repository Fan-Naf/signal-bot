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

ALLOWED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LINKUSDT",
    "AVAXUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "FETUSDT"
}

# =========================
# STATE (FIXED)
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
# LOGGING + ROTATION
# =========================
LOG_FILE = "trades_log.json"

def log_trade(data):
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 5_000_000:
        os.rename(LOG_FILE, "trades_log_old.json")

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

# =========================
# MARKET DATA
# =========================
def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        d = r.json()
        return int(d["data"][0]["value"]), d["data"][0]["value_classification"]
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
    return "LOW"

# =========================
# POSITION SIZE (FIXED)
# =========================
def calculate_position_size(balance, risk_percent, entry, stop):
    risk_amount = balance * (risk_percent / 100)
    risk_per_unit = abs(entry - stop)
    if risk_per_unit == 0:
        return 0

    size = risk_amount / risk_per_unit

    # округление
    step = 0.001
    return round(size / step) * step

# =========================
# WEBHOOK
# =========================
@app.route('/webhook', methods=['POST'])
def webhook():

    # SECURITY
    if WEBHOOK_SECRET:
        secret = request.headers.get('X-Webhook-Secret') or request.args.get('secret')
        if secret != WEBHOOK_SECRET:
            abort(403)

    data = request.json
    if not data:
        return "no data"

    try:
        symbol = data.get("symbol", "").replace(".P", "").upper()
        price = safe_float(data.get("price"))
        signal = data.get("signal", "").upper()
        atr = safe_float(data.get("atr"))

        atr_percent = safe_float(data.get("atr_percent"))
        ema_distance = safe_float(data.get("ema_distance"))
        range_position = safe_float(data.get("range_position"))

        if symbol not in ALLOWED_SYMBOLS:
            return "skip symbol"
        if price <= 0 or atr <= 0 or signal not in ["LONG", "SHORT"]:
            return "invalid data"

        if is_cooldown(symbol):
            return "cooldown active"

        # FILTERS
        if atr_percent < 0.004:
            return "skip - low volatility"
        if ema_distance < 0.003:
            return "skip - weak trend"

        if signal == "SHORT" and range_position < 0.2:
            return "short at bottom"
        if signal == "LONG" and range_position > 0.8:
            return "long at top"

        # SCORING
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

        rating = "A+ 🔥" if score >= 80 else "B ⚙️" if score >= 60 else "C ⚠️"

        # STOP + TP
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

        size = calculate_position_size(DEPOSIT, RISK_PERCENT, entry, stop)

        fg_value, fg_label = get_fear_greed()
        fg_text = f"\n🧠 Рынок: {fg_value} ({fg_label})" if fg_value else ""

        rr1 = abs(tp1 - entry) / abs(entry - stop)
        rr2 = abs(tp2 - entry) / abs(entry - stop)

        # LOG
        log_trade({
            "time": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "signal": signal,
            "score": score,
            "confidence": confidence
        })

        icon = "🟢" if signal == "LONG" else "🔴"

        text = f"""
📊 СИГНАЛ — {symbol}

{icon} {signal}
📊 Рейтинг: {score}/100 ({rating})
🧠 Решение: {decision}
📡 Фаза: {get_market_phase(atr_percent, ema_distance)}
📊 Confidence: {confidence}{fg_text}

🎯 Вход: {entry:.6f}
🛑 Стоп: {stop:.6f}
⚖️ RR: {rr1:.2f} / {rr2:.2f}

TP1: {tp1:.6f}
TP2: {tp2:.6f}

💰 Риск: ${DEPOSIT * (RISK_PERCENT / 100):.2f}
📦 Объём: {size:.4f}
        """.strip()

        send_telegram(text)
        return "ok"

    except Exception as e:
        print("Error:", e)
        return "error", 500


@app.route('/')
def home():
    return "Bot v1.2 FINAL PRO running 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)