from telegram.ext import Updater, CommandHandler
from topup_handler import topup_conv_handler
from order_handler import order_conv_handler
import database

def main():
    database.init_db()
    updater = Updater("TOKEN_BOT_KAMU", use_context=True)
    dp = updater.dispatcher

    dp.add_handler(topup_conv_handler)
    dp.add_handler(order_conv_handler)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
