#!/usr/bin/env python3
"""
Bot Telegram - DEBUG VERSION
"""

import logging
import sys
import os
import asyncio
import traceback
from typing import Dict, Any

# Telegram Imports
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    MessageHandler,
    PicklePersistence
)

# Setup logging lebih detail
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,  # Ubah ke DEBUG untuk lebih detail
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

print("🚀 STARTING BOT - DEBUG MODE")

try:
    import config
    print("✅ Config imported")
except Exception as e:
    print(f"❌ Error importing config: {e}")
    sys.exit(1)

try:
    import database
    print("✅ Database imported")
    
    # Test database connection
    success = database.init_database()
    if success:
        print("✅ Database initialized successfully")
    else:
        print("❌ Database initialization failed")
        
except Exception as e:
    print(f"❌ Error with database: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test BOT_TOKEN
BOT_TOKEN = getattr(config, 'BOT_TOKEN', '')
if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    print("❌ BOT_TOKEN not set in config.py")
    sys.exit(1)
else:
    print(f"✅ BOT_TOKEN found: {BOT_TOKEN[:10]}...")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simple start handler untuk testing"""
    print(f"📨 Start command received from {update.message.from_user.id}")
    await update.message.reply_text(
        "🤖 Bot is working!\n"
        "This is a test message to verify the bot is running."
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    print(f"❌ Error: {context.error}")

def main():
    """Main function dengan lebih banyak debug info"""
    print("=" * 50)
    print("🤖 BOT STARTUP - DEBUG")
    print("=" * 50)
    
    try:
        # Create Application
        print("🔄 Creating application...")
        persistence = PicklePersistence(filepath="bot_persistence")
        application = Application.builder()\
            .token(BOT_TOKEN)\
            .persistence(persistence)\
            .build()
        print("✅ Application created")

        # Add simple handler untuk testing
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                             lambda update, context: update.message.reply_text("I'm alive!")))
        
        application.add_error_handler(error_handler)
        print("✅ Handlers registered")

        # Run bot
        print("🟢 Starting bot polling...")
        print("Bot should be online now!")
        print("Try sending /start to your bot")
        print("=" * 50)
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            timeout=30
        )
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
