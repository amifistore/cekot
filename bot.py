import config
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from topup_handler import topup_conv_handler
from order_handler import order_conv_handler
from admin_handler import (
    admin_menu_handler, updateproduk_handler, listproduk_handler,
    topup_list_handler, cek_user_handler, jadikan_admin_handler,
    admin_callback_handler, topup_callback_handler, edit_produk_conv_handler
)
from broadcast_handler import broadcast_handler
from riwayat_handler import riwayat_trx
import database

async def start(update, context):
    user = update.message.from_user
    database.get_or_create_user(str(user.id), user.username, user.full_name)
    await update.message.reply_text(
        "🤖 **Selamat datang di Bot Top Up & Order!**\n\n"
        "✨ **Fitur Utama:**\n"
        "• 💳 Topup saldo via QRIS\n"
        "• 📦 Order produk digital\n"
        "• 📊 Cek riwayat transaksi\n"
        "• 👑 Menu admin (untuk admin)\n\n"
        "📝 **Gunakan /menu untuk lihat semua command**",
        parse_mode='Markdown'
    )

async def menu(update, context):
    user = update.message.from_user
    
    # Basic menu untuk semua user
    menu_text = (
        "📋 **MENU UTAMA**\n\n"
        "🛒 **Transaksi:**\n"
        "`/topup` - Isi saldo via QRIS\n"
        "`/order` - Order produk digital\n"
        "`/saldo` - Cek saldo Anda\n"
        "`/riwayat_trx` - Lihat riwayat transaksi\n\n"
        "ℹ️ **Lainnya:**\n"
        "`/menu` - Tampilkan menu ini\n"
        "`/cancel` - Batalkan proses sedang berjalan"
    )
    
    # Tambahkan menu admin jika user adalah admin
    if str(user.id) in config.ADMIN_TELEGRAM_IDS:
        menu_text += (
            "\n\n👑 **Menu Admin:**\n"
            "`/admin` - Menu admin panel\n"
            "`/updateproduk` - Update produk dari provider\n"
            "`/listproduk` - List produk aktif\n"
            "`/edit_produk` - Edit harga & deskripsi produk\n"
            "`/topup_list` - Kelola permintaan topup\n"
            "`/cek_user <username>` - Cek info user\n"
            "`/jadikan_admin <id>` - Tambah admin baru\n"
            "`/broadcast <pesan>` - Broadcast ke semua user"
        )
    
    await update.message.reply_text(menu_text, parse_mode='Markdown')

async def saldo(update, context):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    saldo = database.get_user_saldo(user_id)
    
    await update.message.reply_text(
        f"💰 **INFO SALDO**\n\n"
        f"👤 **User:** {user.full_name}\n"
        f"🔖 **Username:** @{user.username or 'Tidak ada'}\n"
        f"💳 **Saldo:** Rp {saldo:,.0f}\n\n"
        f"Gunakan `/topup` untuk mengisi saldo",
        parse_mode='Markdown'
    )

async def cancel(update, context):
    await update.message.reply_text(
        "❌ **Operasi dibatalkan.**\n\n"
        "Gunakan /menu untuk melihat daftar command.",
        parse_mode='Markdown'
    )

async def error_handler(update, context):
    """Handle errors in the telegram bot."""
    print(f"Error: {context.error}")
    
    try:
        if update and update.message:
            await update.message.reply_text(
                "❌ **Terjadi kesalahan sistem.**\n\n"
                "Silakan coba lagi atau hubungi admin.",
                parse_mode='Markdown'
            )
    except:
        pass

def main():
    """Main function to run the bot."""
    print("🤖 Starting Telegram Bot...")
    
    # Initialize database
    database.init_db()
    print("✅ Database initialized")
    
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).build()
    print("✅ Application created")
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # ====================
    # BASIC COMMAND HANDLERS
    # ====================
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("saldo", saldo))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("riwayat_trx", riwayat_trx))
    
    # ====================
    # CONVERSATION HANDLERS
    # ====================
    application.add_handler(topup_conv_handler)          # Topup system
    application.add_handler(order_conv_handler)          # Order system
    application.add_handler(edit_produk_conv_handler)    # Edit produk system
    
    # ====================
    # ADMIN COMMAND HANDLERS
    # ====================
    application.add_handler(admin_menu_handler)          # /admin
    application.add_handler(updateproduk_handler)        # /updateproduk
    application.add_handler(listproduk_handler)          # /listproduk
    application.add_handler(topup_list_handler)          # /topup_list
    application.add_handler(cek_user_handler)            # /cek_user
    application.add_handler(jadikan_admin_handler)       # /jadikan_admin
    application.add_handler(broadcast_handler)           # /broadcast
    
    # ====================
    # CALLBACK QUERY HANDLERS
    # ====================
    application.add_handler(admin_callback_handler)      # Admin menu callbacks
    application.add_handler(topup_callback_handler)      # Topup management callbacks
    
    print("✅ All handlers registered")
    print("🚀 Bot is running...")
    
    # Start the bot - FIX: Remove Update.ALL_TYPES parameter
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
