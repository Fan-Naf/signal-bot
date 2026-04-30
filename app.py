from flask import Flask, request
import requests

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

# =========================
# TELEGRAM
# =========================
def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text}
    )

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

        # =========================
        # ФИЛЬТРЫ
        # =========================
        if symbol not in ALLOWED_SYMBOLS:
            return "skip symbol"

        if price <= 0 or atr <= 0:
            return "invalid data"

        if atr_percent < 0.002:
            return "low volatility"

        if signal == "SHORT" and range_position < 0.2:
            return "short at bottom"

        if signal == "LONG" and range_position > 0.8:
            return "long at top"

        # =========================
        # РЕЙТИНГ
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

        # позиция в диапазоне
        if 0.3 < range_position < 0.7:
            score += 20
        elif 0.2 < range_position < 0.8:
            score += 10
        else:
            score += 5

        # бонус за структуру
        score += 10

        # штраф за перегрев
        if atr_percent > 0.02:
            score -= 10

        score = max(0, min(score, 100))

        # рейтинг
        if score >= 80:
            rating = "A+ 🔥"
        elif score >= 60:
            rating = "B ⚙️"
        elif score >= 40:
            rating = "C ⚠️"
        else:
            rating = "D ❌"

        # =========================
        # СТОП (АДАПТИВНЫЙ)
        # =========================
        if score >= 80:
            stop_distance = atr * 2      # даём рынку дышать
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
        # РИСК-МЕНЕДЖМЕНТ
        # =========================
        risk_amount = DEPOSIT * (RISK_PERCENT / 100)
        position_size = risk_amount / risk_distance

        # =========================
        # ATR КОММЕНТАРИЙ
        # =========================
        if atr_percent < 0.003:
            atr_comment = "низкая волатильность"
        elif atr_percent < 0.01:
            atr_comment = "нормальная волатильность"
        else:
            atr_comment = "высокая волатильность"

        # =========================
        # СООБЩЕНИЕ
        # =========================
        icon = "🟢" if signal == "LONG" else "🔴"

        text = f"""
📊 СИГНАЛ — {symbol}

{icon} {signal}
📊 Рейтинг: {score}/100 ({rating})

📈 ATR: {atr:.6f}
({atr_comment})

🎯 Вход: {entry:.6f}
🛑 Стоп: {stop:.6f}

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
    return "Bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
