from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = "8613876101:AAEbC4ldoDdDOREv6-pxxZ5d-Qqv6usQ3P4"
CHAT_ID = "7086903720"

# =========================
# SETTINGS
# =========================
DEPOSIT = 2000
RISK_PERCENT = 1

# минимальный ATR (в абсолюте) и в %
MIN_ATR_ABS = 0.01
MIN_ATR_PCT = 0.002   # 0.2%

# диапазон (lookback) для фильтра уровней
RANGE_LOOKBACK = 50
EDGE_ZONE = 0.2       # 20% от диапазона считаем "у края"

# whitelist монет (без .P и экзотики)
ALLOWED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "LINKUSDT", "AVAXUSDT", "ARBUSDT", "OPUSDT",
    "INJUSDT", "FETUSDT"
}

# =========================
# HELPERS
# =========================
def normalize_symbol(sym: str) -> str:
    # убираем суффиксы типа .P
    return sym.replace(".P", "").upper()

def get_coin_logo(symbol: str):
    s = symbol.replace("USDT", "").lower()
    mapping = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "sol": "solana",
        "bnb": "binancecoin",
        "link": "chainlink",
        "avax": "avalanche-2",
        "arb": "arbitrum",
        "op": "optimism",
        "inj": "injective-protocol",
        "fet": "fetch-ai",
    }
    coin_id = mapping.get(s, s)
    return f"https://assets.coingecko.com/coins/images/1/large/{coin_id}.png"

def send_telegram(text: str):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )

# =========================
# ROUTES
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}

    symbol_raw = data.get("symbol", "UNKNOWN")
    symbol = normalize_symbol(symbol_raw)

    price = float(data.get("price", 0))
    signal = data.get("signal", "N/A")
    atr = float(data.get("atr", 0))

    # Доп. данные из Pine (если добавим)
    range_high = float(data.get("range_high", price))
    range_low = float(data.get("range_low", price))

    # =========================
    # 1. WHITELIST
    # =========================
    if symbol not in ALLOWED_SYMBOLS:
        return "skip: not allowed symbol"

    # =========================
    # 2. ATR FILTER
    # =========================
    atr_pct = atr / price if price > 0 else 0

    if atr < MIN_ATR_ABS or atr_pct < MIN_ATR_PCT:
        return "skip: low volatility"

    # =========================
    # 3. RANGE FILTER (уровни)
    # =========================
    range_size = max(range_high - range_low, 0.0000001)
    pos_in_range = (price - range_low) / range_size

    # у края диапазона
    near_bottom = pos_in_range <= EDGE_ZONE
    near_top = pos_in_range >= (1 - EDGE_ZONE)

    # блокируем "не туда"
    if signal == "SHORT" and near_bottom:
        return "skip: short at bottom"
    if signal == "LONG" and near_top:
        return "skip: long at top"

    # =========================
    # 4. ENTRY / STOP (ATR)
    # =========================
    entry = price

    # адаптивный стоп
    stop_distance = atr * 1.5

    if signal == "LONG":
        stop = entry - stop_distance
    else:
        stop = entry + stop_distance

    risk_distance = abs(entry - stop)
    if risk_distance <= 0:
        return "skip: invalid risk"

    # =========================
    # 5. TAKE PROFIT (RR)
    # =========================
    if signal == "LONG":
        tp1 = entry + risk_distance * 1.5
        tp2 = entry + risk_distance * 2.5
    else:
        tp1 = entry - risk_distance * 1.5
        tp2 = entry - risk_distance * 2.5

    # =========================
    # 6. POSITION SIZE
    # =========================
    risk_amount = DEPOSIT * (RISK_PERCENT / 100)
    position_size = risk_amount / risk_distance

    # =========================
    # 7. ATR COMMENT
    # =========================
    if atr_pct < 0.003:
        atr_comment = "низкая волатильность"
    elif atr_pct < 0.01:
        atr_comment = "нормальная волатильность"
    else:
        atr_comment = "высокая волатильность"

    # =========================
    # 8. SIGNAL GRADE
    # =========================
    grade = "B"
    comment = "нормальный вход"

    if 0.004 < atr_pct < 0.012 and risk_distance < price * 0.02:
        grade = "A+"
        comment = "сильный вход"
    elif atr_pct > 0.02:
        grade = "C"
        comment = "слишком волатильно"

    # =========================
    # 9. MESSAGE
    # =========================
    direction_icon = "🟢" if signal == "LONG" else "🔴"

    text = f"""
📊 СИГНАЛ — {symbol}

{direction_icon} {signal} | STRONG
Оценка: {grade} ({comment})

📈 ATR: {atr:.4f}
({atr_comment})

🎯 Вход: {entry:.4f}
🛑 Стоп: {stop:.4f}

🎯 Тейки:
TP1: {tp1:.4f}
TP2: {tp2:.4f}

💰 Риск: ${risk_amount:.2f}
📦 Объём: {position_size:.4f}
"""

    send_telegram(text)
    return "ok"


@app.route("/")
def home():
    return "Bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
