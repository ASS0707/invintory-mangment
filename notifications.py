import os
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from app import app, db
from models import Client

# Telegram configuration from environment
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '7412914579:AAF50mrry-5VVp-C4Guvdml_j_TRSRIPWX0')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '1449909892')


def send_message(text):
    """Send a message via Telegram bot."""
    app.logger.info(f"Preparing Telegram message to chat {CHAT_ID}: {text}")
    if not BOT_TOKEN or not CHAT_ID:
        app.logger.warning("Telegram credentials not configured.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        app.logger.info("Sending Telegram message...")
        response = requests.post(url, data={"chat_id": CHAT_ID, "text": text})
        response.raise_for_status()
        app.logger.info("Telegram message sent successfully.")
    except Exception as e:
        app.logger.error(f"Failed to send Telegram message: {e}")


def weekly_report():
    """Compile outstanding balances and send weekly report."""
    clients = Client.query.all()
    lines = []
    total = 0.0
    for client in clients:
        bal = client.calculate_balance()
        if bal > 0:
            lines.append(f"{client.name}: {bal:.2f} ج.م")
            total += bal
    if not lines:
        message = "لا توجد مبالغ مستحقة هذا الأسبوع"
    else:
        message = "ملخص المستحقات الأسبوعية:\n" + "\n".join(lines) + f"\nالإجمالي: {total:.2f} ج.م"
    send_message(message)

# Schedule weekly job on Monday at 08:00
scheduler = BackgroundScheduler()
scheduler.add_job(weekly_report, 'cron', day_of_week='mon', hour=8, minute=0)
scheduler.start()
