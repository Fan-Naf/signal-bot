from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = "8613876101:AAEbC4ldoDdDOREv6-pxxZ5d-Qqv6usQ3P4"
CHAT_ID = "7086903720"


def get_coin_logo(symbol):
    symbol = symbol.replace("USDT", "").lower()

    mapping = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "sol": "solana",
        "bnb": "binancecoin"
    }

    coin_id = mapping.get(symbol, symbol)

    return f"https://assets.coingecko.com/coins/images/1/large/{coin_id}.png"


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    symbol = data.get("symbol", "UNKNOWN")

    try:
        price = float(data.get("price", 0))
    except:
        return "invalid price"

    signal = data.get("signal", "N/A")

    # фильтр сигнала
    if signal == "LONG":
        signal_emoji = "🟢"
    elif signal == "SHORT":
        signal_emoji = "🔴"
    else:
        return "no signal"

    strength = "STRONG"

    # === ЛОГИКА ===
    entry = price
    max_stop_distance = price * 0.05

    if signal == "LONG":
        structure_stop = price * 0.97
        stop = max(structure_stop, price - max_stop_distance)

    elif signal == "SHORT":
        structure_stop = price * 1.03
        stop = min(structure_stop, price + max_stop_distance)

    risk_distance = abs(price - stop)

    if risk_distance <= 0:
        return "error"

    # тейки
    if signal == "LONG":
        tp1 = price + risk_distance * 1.5
        tp2 = price + risk_distance * 2.5
    else:
        tp1 = price - risk_distance * 1.5
        tp2 = price - risk_distance * 2.5

    # риск
    deposit = 2000
    risk_percent = 1
    risk_amount = deposit * (risk_percent / 100)

    position_size = risk_amount / risk_distance

    text = f"""
📊 СИГНАЛ

Пара: {symbol}
Тип: {signal_emoji} {signal}
Сила: {strength}
Оценка: A+ (сильный вход)

🎯 Вход: {entry:.5f}
🛑 Стоп: {stop:.5f} (≤5%)

🎯 Тейки:
TP1: {tp1:.5f}
TP2: {tp2:.5f}

💰 Риск: ${risk_amount}
📦 Объём: {position_size:.2f}
"""

    logo_url = get_coin_logo(symbol)

    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": f"{logo_url}\n{text}",
            "disable_web_page_preview": False
        }
    )

    return "ok"


@app.route('/')
def home():
    return "Bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
