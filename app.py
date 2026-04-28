from flask import Flask, request
import requests
import time

app = Flask(__name__)

TOKEN = "8613876101:AAEbC4ldoDdDOREv6-pxxZ5d-Qqv6usQ3P4"
CHAT_ID = "7086903720"

# глобальные переменные
last_signal_time = 0
last_signal_type = None

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
    global last_signal_time, last_signal_type

    data = request.json

    symbol = data.get("symbol", "UNKNOWN")
    price = float(data.get("price", 0))
    signal = data.get("signal", "N/A")

    current_time = time.time()

    # =========================
    # 🚫 АНТИ-КОНФЛИКТ (LONG vs SHORT)
    # =========================
    if last_signal_type is not None:
        if signal != last_signal_type:
            if current_time - last_signal_time < 120:  # 2 минуты
                return "conflict ignored"

    # =========================
    # ⏱ АНТИ-СПАМ (5 минут)
    # =========================
    cooldown_seconds = 300

    if current_time - last_signal_time < cooldown_seconds:
        return "cooldown"

    # =========================
    # 📏 ФИЛЬТР ДВИЖЕНИЯ
    # =========================
    if price == 0:
        return "no price"

    min_move = 0.003  # 0.3%
    if abs(price * min_move) < 0.0001:
        return "no volatility"

    # =========================
    # 🧠 ОЦЕНКА СИГНАЛА
    # =========================
    score = 0

    if signal in ["LONG", "SHORT"]:
        score += 1

    # простая проверка движения
    if price > 0:
        score += 1

    # защита от "перекупленности"
    overextended = False

    if signal == "LONG" and price > price * 1.02:
        overextended = True

    if signal == "SHORT" and price < price * 0.98:
        overextended = True

    if not overextended:
        score += 1

    if score == 3:
        grade = "A+ (сильный вход)"
    elif score == 2:
        grade = "B (норм)"
    else:
        grade = "C (рискованный)"

    if score < 2:
        return "weak signal"

    # =========================
    # 💪 СИЛА СИГНАЛА
    # =========================
    strength = "STRONG" if signal in ["LONG", "SHORT"] else "WEAK"

    # =========================
    # 🎯 ВХОД / СТОП / ТЕЙКИ
    # =========================
    entry = price

    max_stop_distance = price * 0.05  # максимум 5%

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
Оценка: {grade}

🎯 Вход: {entry:.5f}
🛑 Стоп: {stop:.5f} (≤5%)

🎯 Тейки:
TP1: {tp1:.5f}
TP2: {tp2:.5f}

💰 Риск: ${risk_amount}
📦 Объём: {position_size:.2f}
"""

    # отправка в Telegram
    logo_url = get_coin_logo(symbol)

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={
        "chat_id": CHAT_ID,
        "text": f"{logo_url}\n{text}"
    }
)

    # обновляем состояние
    last_signal_time = current_time
    last_signal_type = signal

    return "ok"


@app.route('/')
def home():
    return "Bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
