from flask import Flask, request
import requests
import time

app = Flask(__name__)

TOKEN = "8613876101:AAEbC4ldoDdDOREv6-pxxZ5d-Qqv6usQ3P4"
CHAT_ID = "7086903720"

# =========================
# НАСТРОЙКИ
# =========================
DEPOSIT = 2000
RISK_PERCENT = 1

ALLOWED_SYMBOLS = {
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT",
    "LINKUSDT","AVAXUSDT","ARBUSDT","OPUSDT",
    "INJUSDT","FETUSDT"
}

# анти-дубли сигналов
LAST_SIGNAL_TIME = {}
COOLDOWN_SECONDS = 60 * 60 * 6  # 6 часов

# =========================
# TELEGRAM
# =========================
def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )

# =========================
# FEAR & GREED API
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

# =========================
# WEBHOOK
# =========================
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    try:
        # =========================
        # ДАННЫЕ
        # =========================
        symbol = data.get("symbol", "").replace(".P", "")
        price = float(data.get("price", 0))
        signal = data.get("signal", "")
        atr = float(data.get("atr", 0))

        range_high = float(data.get("range_high", price))
        range_low = float(data.get("range_low", price))

        atr_percent = float(data.get("atr_percent", 0))
        ema_distance = float(data.get("ema_distance", 0))
        range_position = float(data.get("range_position", 0))

        now = time.time()

        # =========================
        # ФИЛЬТРЫ
        # =========================
        if symbol not in ALLOWED_SYMBOLS:
            return "skip symbol"

        if price <= 0 or atr <= 0:
            return "invalid data"

        # анти-дубли сигналов
        if symbol in LAST_SIGNAL_TIME:
            if now - LAST_SIGNAL_TIME[symbol] < COOLDOWN_SECONDS:
                return "cooldown active"

        # =========================
        # 🧠 ФИЛЬТР ФАЗЫ РЫНКА
        # =========================
        if atr_percent < 0.004:
            return "skip - low volatility"

        if ema_distance < 0.003:
            return "skip - weak trend"

        # диапазон
        if signal == "SHORT" and range_position < 0.2:
            return "short at bottom"

        if signal == "LONG" and range_position > 0.8:
            return "long at top"

        # =========================
        # 📊 РЕЙТИНГ
        # =========================
        score = 0

        # тренд
        if ema_distance > 0.005:
            score += 30
        elif ema_distance > 0.002:
            score += 20
        else:
            score += 5

        # волатильность
        if 0.004 < atr_percent < 0.015:
            score += 20
        elif atr_percent > 0.002:
            score += 10

        # позиция
        if 0.3 < range_position < 0.7:
            score += 20
        elif 0.2 < range_position < 0.8:
            score += 10
        else:
            score += 5

        score += 10

        if atr_percent > 0.02:
            score -= 10

        score = max(0, min(score, 100))

        # =========================
        # 🧠 DECISION LAYER
        # =========================
        if score >= 75:
            decision = "TRADE"
        elif score >= 60:
            decision = "CAREFUL"
        else:
            return "skip - weak signal"

        # =========================
        # ГРЕЙД
        # =========================
        if score >= 80:
            rating = "A+ 🔥"
        elif score >= 60:
            rating = "B ⚙️"
        elif score >= 40:
            rating = "C ⚠️"
        else:
            rating = "D ❌"

        # =========================
        # СТОП
        # =========================
        if score >= 80:
            stop_distance = atr * 2.2  # увеличен
        else:
            stop_distance = atr * 1.5

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

        if risk_distance <= 0:
            return "invalid risk"

        # =========================
        # РИСК
        # =========================
        risk_amount = DEPOSIT * (RISK_PERCENT / 100)
        position_size = risk_amount / risk_distance

        # =========================
        # FEAR & GREED
        # =========================
        fg_value, fg_label = get_fear_greed()

        fg_text = ""
        if fg_value is not None:
            fg_text = f"\n🧠 Рынок: {fg_value} ({fg_label})"

            if fg_value > 75:
                fg_text += "\n⚠️ Перегретый рынок"
            elif fg_value < 25:
                fg_text += "\n⚠️ Паника на рынке"

        # =========================
        # RR
        # =========================
        rr1 = abs(tp1 - entry) / risk_distance
        rr2 = abs(tp2 - entry) / risk_distance

        # =========================
        # СОХРАНЯЕМ СИГНАЛ
        # =========================
        LAST_SIGNAL_TIME[symbol] = now

        # =========================
        # СООБЩЕНИЕ
        # =========================
        icon = "🟢" if signal == "LONG" else "🔴"

        text = f"""
📊 СИГНАЛ — {symbol}

{icon} {signal}
📊 Рейтинг: {score}/100 ({rating})
🧠 Решение: {decision}
{fg_text}

📈 ATR: {atr:.6f}

🎯 Вход: {entry:.6f}
🛑 Стоп: {stop:.6f}

⚖️ RR: {rr1:.2f} / {rr2:.2f}

🎯 Тейки:
TP1: {tp1:.6f}
TP2: {tp2:.6f}

💰 Риск: ${risk_amount:.2f}
📦 Объём: {position_size:.4f}
"""

        send_telegram(text)

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error"


@app.route('/')
def home():
    return "Bot v1.1 is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
