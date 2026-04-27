from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = "8613876101:AAEbC4ldoDdDOREv6-pxxZ5d-Qqv6usQ3P4"
CHAT_ID = "7086903720"


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    symbol = data.get("symbol", "UNKNOWN")
    price = float(data.get("price", 0))
    signal = data.get("signal", "N/A")

    # сила сигнала
    strength = "MEDIUM"
    if signal == "LONG":
        strength = "STRONG"
    elif signal == "SHORT":
        strength = "STRONG"

    # ===== НОВАЯ ЛОГИКА =====

    entry = price

    # стоп (макс 5%)
    if signal == "LONG":
        structure_stop = price * 0.97
        max_stop = price * 0.95
        stop = max(structure_stop, max_stop)

    elif signal == "SHORT":
        structure_stop = price * 1.03
        max_stop = price * 1.05
        stop = min(structure_stop, max_stop)

    else:
        return "no signal"

    # расстояние до стопа
    risk_distance = abs(price - stop)

    if risk_distance <= 0:
        return "error"

    # тейки (через риск)
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

    # сообщение
    text = f"""
📊 СИГНАЛ

Пара: {symbol}
Тип: {signal}
Сила: {strength}

🎯 Вход: {entry:.5f}
🛑 Стоп: {stop:.5f} (≤5%)

🎯 Тейки:
TP1: {tp1:.5f}
TP2: {tp2:.5f}

💰 Риск: ${risk_amount}
📦 Объём: {position_size:.2f}
"""

    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )

    return "ok"


@app.route('/')
def home():
    return "Bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
