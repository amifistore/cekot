import config
from telegram.ext import Application, CommandHandler
from topup_handler import topup_conv_handler
from order_handler import order_conv_handler
from admin_handler import (
    admin_menu_handler, updateproduk_handler, listproduk_handler,
    topup_confirm_handler, cek_user_handler, jadikan_admin_handler
)
from broadcast_handler import broadcast_handler
from riwayat_handler import riwayat_trx
import database

async def start(update, context):
    user = update.message.from_user
    database.get_or_create_user(str(user.id), user.username, user.full_name)
    await update.message.reply_text(
        "Selamat datang di Bot Top Up & Order!\n/menu untuk lihat menu utama."
    )

async def menu(update, context):
    await update.message.reply_text(
        "/topup - Isi saldo via QRIS\n"
        "/order - Order produk digital\n"
        "/riwayat_trx - Lihat riwayat transaksi\n"
        "/saldo - Cek saldo\n"
        "/admin - Menu admin\n"
        "/broadcast - Broadcast pesan admin\n"
        "/cancel - Batalkan proses"
    )

async def saldo(update, context):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = database.get_user_saldo(user_id)
    await update.message.reply_text(f"Saldo kamu: Rp {saldo}")

def main():
    database.init_db()
    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("saldo", saldo))
    application.add_handler(CommandHandler("riwayat_trx", riwayat_trx))

    application.add_handler(topup_conv_handler)
    application.add_handler(order_conv_handler)

    application.add_handler(admin_menu_handler)
    application.add_handler(updateproduk_handler)
    application.add_handler(listproduk_handler)
    application.add_handler(topup_confirm_handler)
    application.add_handler(cek_user_handler)
    application.add_handler(jadikan_admin_handler)
    application.add_handler(broadcast_handler)

    application.run_polling()

if __name__ == "__main__":
    main()
