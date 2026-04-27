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

# риск
deposit = 2000
risk_percent = 1
risk_amount = deposit * (risk_percent / 100)

text = f"""
📊 СИГНАЛ

Пара: {symbol}
Тип: {signal}
Сила: {strength}

Цена: {price}

💰 Риск: ${risk_amount}

Проверь:
– уровень
– ретест
– объём
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
