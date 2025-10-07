from telegram.ext import Updater, CommandHandler
from topup_handler import topup_conv_handler
from order_handler import order_conv_handler
import database

def main():
    database.init_db()
    updater = Updater("7976276575:AAE8-jSX-T5KlYDTbsYKGn1K3xd25WtY39Y", use_context=True)
    dp = updater.dispatcher

    dp.add_handler(topup_conv_handler)
    dp.add_handler(order_conv_handler)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
