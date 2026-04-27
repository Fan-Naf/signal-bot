from flask import Flask, request
import requests
import time

app = Flask(__name__)

TOKEN = "8613876101:AAEbC4ldoDdDOREv6-pxxZ5d-Qqv6usQ3P4"
CHAT_ID = "7086903720"

# анти-спам (глобальная переменная)
last_signal_time = 0

@app.route('/webhook', methods=['POST'])
def webhook():
    global last_signal_time

    data = request.json

    symbol = data.get("symbol", "UNKNOWN")
    price = float(data.get("price", 0))
    signal = data.get("signal", "N/A")

    # =========================
    # ⏱ АНТИ-СПАМ (5 минут)
    # =========================
    cooldown_seconds = 300
    current_time = time.time()

    if current_time - last_signal_time < cooldown_seconds:
        return "cooldown"

    # =========================
    # 📏 ФИЛЬТР ДВИЖЕНИЯ
    # =========================
    min_move = 0.003  # 0.3%

    if price == 0:
        return "no price"

    if abs(price * min_move) < 0.0001:
        return "no volatility"

    # =========================
    # 📉 ФИЛЬТР ТРЕНДА (заглушка)
    # =========================
    trend = "UP" if signal == "LONG" else "DOWN"

    if signal == "LONG" and trend != "UP":
        return "wrong trend"

    if signal == "SHORT" and trend != "DOWN":
        return "wrong trend"

    # =========================
    # 💪 СИЛА СИГНАЛА
    # =========================
    strength = "MEDIUM"

    if signal in ["LONG", "SHORT"]:
        strength = "STRONG"

    # =========================
    # 🎯 ВХОД / СТОП / ТЕЙКИ
    # =========================
    entry = price

    max_stop_distance = price * 0.05  # 5%

    if signal == "LONG":
        structure_stop = price * 0.97
        stop = max(structure_stop, price - max_stop_distance)

    elif signal == "SHORT":
        structure_stop = price * 1.03
        stop = min(structure_stop, price + max_stop_distance)

    else:
        return "no signal"

    risk_distance = abs(price - stop)

    if risk_distance <= 0:
        return "bad risk"

    # тейки (RR)
    if signal == "LONG":
        tp1 = price + risk_distance * 1.5
        tp2 = price + risk_distance * 2.5
    else:
        tp1 = price - risk_distance * 1.5
        tp2 = price - risk_distance * 2.5

    # =========================
    # 💰 РИСК-МЕНЕДЖМЕНТ
    # =========================
    deposit = 2000
    risk_percent = 1

    risk_amount = deposit * (risk_percent / 100)
    position_size = risk_amount / risk_distance

    # =========================
    # 🧾 СООБЩЕНИЕ
    # =========================
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

    # отправка в Telegram
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )

    # обновляем время сигнала
    last_signal_time = current_time

    return "ok"


@app.route('/')
def home():
    return "Bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
