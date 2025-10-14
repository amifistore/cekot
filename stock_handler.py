import requests
from telegram import Update
from telegram.ext import CallbackContext
from utils import format_stock_akrab
from markup import reply_main_menu

PROVIDER_STOCK_URL = "https://panel.khfy-store.com/api_v3/cek_stock_akrab"

def stock_akrab_callback(update: Update, context: CallbackContext):
    query = update.callback_query if hasattr(update, "callback_query") and update.callback_query else None
    user_id = None
    if query:
        user_id = query.from_user.id
        query.answer()
    else:
        user_id = update.effective_user.id if update.effective_user else None

    try:
        resp = requests.get(PROVIDER_STOCK_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        msg = format_stock_akrab(data)
    except Exception as e:
        msg = f"<b>❌ Gagal mengambil data stok dari provider:</b>\n{str(e)}"

    # Gunakan reply_main_menu agar user bisa memilih menu lain setelah cek stok
    markup = reply_main_menu(user_id)
    if query:
        query.edit_message_text(
            msg,
            parse_mode="HTML",
            reply_markup=markup
        )
    else:
        update.message.reply_text(
            msg,
            parse_mode="HTML",
            reply_markup=markup
        )
