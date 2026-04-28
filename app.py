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
    atr = float(data.get("atr", 0))

    if atr == 0:
        return "no atr"

    # --- тип сигнала ---
    signal_emoji = "🟢" if signal == "LONG" else "🔴"
    strength = "STRONG"

    # --- ATR интерпретация ---
    if atr < price * 0.003:
        atr_comment = "низкая волатильность"
    elif atr < price * 0.007:
        atr_comment = "нормальная волатильность"
    else:
        atr_comment = "высокая волатильность"

    # --- ATR логика ---
    entry = price

    stop_distance = atr * 1.5
    tp1_distance = atr * 2
    tp2_distance = atr * 3

    if signal == "LONG":
        stop = entry - stop_distance
        tp1 = entry + tp1_distance
        tp2 = entry + tp2_distance
    else:
        stop = entry + stop_distance
        tp1 = entry - tp1_distance
        tp2 = entry - tp2_distance

    # --- риск ---
    deposit = 2000
    risk_percent = 1

    risk_amount = deposit * (risk_percent / 100)
    position_size = risk_amount / stop_distance

    # --- текст ---
    text = f"""
📊 СИГНАЛ — {symbol}

{signal_emoji} {signal} | {strength}
A+ (ATR модель)

📈 ATR: {atr:.2f} ({atr_comment})

🎯 Вход: {entry:.2f}
🛑 Стоп: {stop:.2f}

🎯 Тейки:
TP1: {tp1:.2f}
TP2: {tp2:.2f}

💰 Риск: ${risk_amount:.2f}
📦 Объём: {position_size:.4f}
"""

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
