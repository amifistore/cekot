import config
from apscheduler.schedulers.background import BackgroundScheduler
import sqlite3, requests
from telegram import Bot
import database
import asyncio

DB_PATH = "bot_database.db"
bot = Bot(config.BOT_TOKEN)

async def check_pending_orders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, reff_id FROM riwayat_pembelian WHERE status_api='PROSES'")
    rows = c.fetchall()
    for order_id, username, reff_id in rows:
        api_url = f"https://panel.khfy-store.com/api_v2/status?reff_id={reff_id}&api_key={config.API_KEY_PROVIDER}"
        try:
            resp = requests.get(api_url, timeout=15)
            if resp.ok:
                result = resp.json()
                status = str(result.get('status', 'PROSES')).upper()
                msg = result.get('msg', '')
                if status in ['SUKSES', 'SUCCESS', 'GAGAL', 'FAILED']:
                    c.execute("UPDATE riwayat_pembelian SET status_api=?, keterangan=? WHERE id=?", (status, msg, order_id))
                    telegram_id = database.get_telegram_id_by_username(username)
                    if telegram_id:
                        await bot.send_message(chat_id=telegram_id, text=f"Order kamu dengan reff_id {reff_id} status: {status}\n{msg}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def schedule_auto_update():
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run(check_pending_orders()), 'interval', minutes=5)
    scheduler.start()
