from telegram import Update
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, CallbackContext, filters
import requests
import base64
from io import BytesIO
import database

ASK_TOPUP_NOMINAL = 1
QRIS_STATIS = "00020101021126610014COM.GO-JEK.WWW01189360091434506469550210G4506469550303UMI51440014ID.CO.QRIS.WWW0215ID10243341364120303UMI5204569753033605802ID5923Amifi Store, Kmb, TLGSR6009BONDOWOSO61056827262070703A01630431E8"

def topup_start(update: Update, context: CallbackContext):
    update.message.reply_text("Masukkan nominal top up (angka saja, contoh: 10000):")
    return ASK_TOPUP_NOMINAL

def topup_nominal(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    nominal = update.message.text.strip()
    if not nominal.isdigit() or int(nominal) <= 0:
        update.message.reply_text("Nominal harus berupa angka dan lebih dari 0. Silakan masukkan lagi.")
        return ASK_TOPUP_NOMINAL

    payload = {
        "amount": nominal,
        "qris_statis": QRIS_STATIS
    }
    try:
        resp = requests.post("https://qrisku.my.id/api", json=payload, timeout=15)
        result = resp.json()
        if result.get("status") == "success" and "qris_base64" in result:
            qris_base64 = result["qris_base64"]
            qris_bytes = base64.b64decode(qris_base64)
            bio = BytesIO(qris_bytes)
            bio.name = 'qris.png'
            database.create_topup_request(user_id, int(nominal), qris_base64)
            update.message.reply_text(
                f"QRIS untuk top up Rp {nominal} siap! Silakan scan dan lakukan pembayaran. Setelah admin konfirmasi, saldo kamu akan bertambah."
            )
            update.message.reply_photo(photo=bio)
        else:
            update.message.reply_text(f"Gagal generate QRIS: {result.get('message')}")
    except Exception as e:
        update.message.reply_text(f"Error generate QRIS: {e}")
    return ConversationHandler.END

def topup_cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Proses top up dibatalkan.")
    return ConversationHandler.END

topup_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('topup', topup_start)],
    states={
        ASK_TOPUP_NOMINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, topup_nominal)]
    },
    fallbacks=[CommandHandler('cancel', topup_cancel)]
)
