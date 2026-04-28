from flask import Flask, request
import requests

app = Flask(__name__)

# === ТВОИ ДАННЫЕ ===
TOKEN = "8613876101:AAEbC4ldoDdDOREv6-pxxZ5d-Qqv6usQ3P4"
CHAT_ID = "7086903720"


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json

    # =========================
    # ПОЛУЧЕНИЕ ДАННЫХ ИЗ TV
    # =========================
    symbol = data.get("symbol", "UNKNOWN")
    price = float(data.get("price", 0))
    signal = data.get("signal", "N/A")
    atr = float(data.get("atr", 0))

    # =========================
    # БАЗОВАЯ ЛОГИКА
    # =========================
    entry = price

    # ATR СТОП
    atr_mult = 1.5
    stop_distance = atr * atr_mult

    if signal == "LONG":
        stop = price - stop_distance
    elif signal == "SHORT":
        stop = price + stop_distance
    else:
        return "no signal"

    # =========================
    # RISK / TP
    # =========================
    risk_distance = abs(price - stop)

    if signal == "LONG":
        tp1 = price + risk_distance * 1.5
        tp2 = price + risk_distance * 2.5
    else:
        tp1 = price - risk_distance * 1.5
        tp2 = price - risk_distance * 2.5

    # =========================
    # ОЦЕНКА СИГНАЛА (A / B / C)
    # =========================

    # ATR в процентах от цены
    atr_percent = atr / price if price > 0 else 0

    # базовая оценка
    grade = "B"
    comment = "средний вход"

    # 🟢 A+ (идеальные условия)
    if 0.004 < atr_percent < 0.012 and risk_distance < price * 0.02:
        grade = "A+"
        comment = "сильный вход"

    # 🟡 B (норм)
    elif 0.002 < atr_percent <= 0.02:
        grade = "B"
        comment = "нормальный рынок"

    # 🔴 C (плохо)
    else:
        grade = "C"
        comment = "лучше пропустить"
    
    # =========================
    # ATR АНАЛИЗ
    # =========================
    if atr < price * 0.003:
        atr_comment = "низкая волатильность (вялый рынок)"
    elif atr < price * 0.01:
        atr_comment = "нормальная волатильность"
    else:
        atr_comment = "высокая волатильность (осторожно)"

    # =========================
    # РИСК-МЕНЕДЖМЕНТ
    # =========================
    deposit = 2000
    risk_percent = 1

    risk_amount = deposit * (risk_percent / 100)

    if risk_distance > 0:
        position_size = risk_amount / risk_distance
    else:
        position_size = 0

    # =========================
    # СИГНАЛ (ТЕКСТ)
    # =========================
    direction_icon = "🟢" if signal == "LONG" else "🔴"

    text = f"""
📊 СИГНАЛ — {symbol}

{direction_icon} {signal} | STRONG
A+ (ATR модель)

📈 ATR: {atr:.2f}
({atr_comment})

🎯 Вход: {entry:.2f}
🛑 Стоп: {stop:.2f}

🎯 Тейки:
TP1: {tp1:.2f}
TP2: {tp2:.2f}

💰 Риск: ${risk_amount:.2f}
📦 Объём: {position_size:.4f}
"""

    # =========================
    # ОТПРАВКА В TELEGRAM
    # =========================
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": text
        }
    )

    return "ok"


@app.route('/')
def home():
    return "Bot is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
