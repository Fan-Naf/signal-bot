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
# LOG
# =========================
LOG_FILE = "trades_log.json"

def log_trade(data):
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 5_000_000:
        os.rename(LOG_FILE, "trades_log_old.json")

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

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
        eth_raw = data.get("eth_trend")
        eth_trend = "UP" if eth_raw == 1 else "DOWN"

        now = time.time()

        # =========================
        # PROTECTION: CLUSTER
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
        # BASE SCORING
        # =========================
        score = 0

        if ema_distance > 0.005:
            score += 30
        elif ema_distance > 0.002:
            score += 20
        else:
            score += 5

        if 0.004 < atr_percent < 0.015:
            score += 20
        elif atr_percent > 0.002:
            score += 10

        if 0.3 < range_position < 0.7:
            score += 20
        elif 0.2 < range_position < 0.8:
            score += 10
        else:
            score += 5

        score += 10

        if atr_percent > 0.02:
            score -= 10

        # =========================
        # CONTEXT v1.5
        # =========================
        context_score = 0

        context_score += 10 if (signal == "LONG" and btc_trend == "UP") or (signal == "SHORT" and btc_trend == "DOWN") else -10
        context_score += 10 if (signal == "LONG" and eth_trend == "UP") or (signal == "SHORT" and eth_trend == "DOWN") else -10

        if btc_strength > 0.003:
            context_score += 5

        score += context_score

        # =========================
        # MARKET REGIME v1.6
        # =========================
        regime = "NEUTRAL"

        if btc_trend == "UP" and btc_strength > 0.002:
            regime = "BULL"
        elif btc_trend == "DOWN" and btc_strength > 0.002:
            regime = "BEAR"

        if regime == "BULL":
            score += 10 if signal == "LONG" else -10
        elif regime == "BEAR":
            score += 10 if signal == "SHORT" else -10
        else:
            score -= 10

        # =========================
        # FINAL LIMIT
        # =========================
        score = max(0, min(score, 100))

        if score < 65:
            return "skip - weak"

        # =========================
        # MESSAGE
        # =========================
        text = f"""
📊 {symbol}

{signal}
Score: {score}
Regime: {regime}
BTC: {btc_trend}
ETH: {eth_trend}
        """.strip()

        send_telegram(text)

        log_trade({
            "time": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "signal": signal,
            "score": score,
            "regime": regime
        })

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error", 500


@app.route('/')
def home():
    return "Bot v1.6 running 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)