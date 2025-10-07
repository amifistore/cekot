from telegram.ext import Application, CommandHandler
from topup_handler import topup_conv_handler
from order_handler import order_conv_handler
import database

def main():
    database.init_db()
    application = Application.builder().token("TOKEN_BOT_KAMU").build()

    application.add_handler(topup_conv_handler)
    application.add_handler(order_conv_handler)

    application.run_polling()

if __name__ == "__main__":
    main()
