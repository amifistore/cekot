# stok_handler.py - Stock Management Handler
import logging
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from database import db

logger = logging.getLogger(__name__)

def format_stock_akrab(data: Dict) -> str:
    """Format stock data for display"""
    try:
        if not data:
            return "📦 Stok tidak tersedia"
        
        status_icon = "🟢" if data.get('status') == 'active' else "🔴"
        stock_info = f"📦 {data['name']}\n"
        stock_info += f"💰 Harga: Rp {data['price']:,}\n"
        
        if data.get('description'):
            stock_info += f"📝 {data['description']}\n"
        
        stock_info += f"📊 Status: {status_icon} {data.get('status', 'unknown').title()}\n"
        
        if data.get('stock') is not None:
            stock_info += f"🔄 Stok: {data['stock']}\n"
        
        if data.get('category'):
            stock_info += f"📁 Kategori: {data['category']}\n"
        
        return stock_info
        
    except Exception as e:
        logger.error(f"Error formatting stock data: {e}")
        return "❌ Error memuat data stok"

async def stok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stok command - Show available products"""
    try:
        user_id = str(update.effective_user.id)
        
        # Get user data
        user = db.get_or_create_user(
            user_id,
            update.effective_user.username,
            update.effective_user.full_name
        )
        
        if user.get('is_banned'):
            await update.message.reply_text("❌ Akun Anda telah dibanned.")
            return
        
        # Get all active products
        products = db.get_active_products()
        
        if not products:
            await update.message.reply_text(
                "📦 Stok sedang kosong. Silakan coba lagi nanti."
            )
            return
        
        # Group products by category
        categories = {}
        for product in products:
            category = product.get('category', 'Umum')
            if category not in categories:
                categories[category] = []
            categories[category].append(product)
        
        # Create message with categorized products
        message = "📦 **DAFTAR PRODUK TERSEDIA**\n\n"
        
        for category, category_products in categories.items():
            message += f"📁 **{category.upper()}**\n"
            
            for product in category_products:
                status_icon = "🟢"
                if product.get('kosong'):
                    status_icon = "🔴"
                elif product.get('gangguan'):
                    status_icon = "🟡"
                
                message += f"{status_icon} {product['name']} - Rp {product['price']:,}\n"
            
            message += "\n"
        
        message += "💡 **Keterangan:**\n"
        message += "🟢 Tersedia • 🟡 Gangguan • 🔴 Kosong\n\n"
        message += "ℹ️ Gunakan /beli untuk memesan produk"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in stok_command: {e}")
        await update.message.reply_text("❌ Terjadi error saat mengambil data stok.")

async def stok_detail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stok_detail command - Show detailed stock information"""
    try:
        user_id = str(update.effective_user.id)
        
        # Get user data
        user = db.get_or_create_user(
            user_id,
            update.effective_user.username,
            update.effective_user.full_name
        )
        
        if user.get('is_banned'):
            await update.message.reply_text("❌ Akun Anda telah dibanned.")
            return
        
        # Get all active products
        products = db.get_active_products()
        
        if not products:
            await update.message.reply_text(
                "📦 Stok sedang kosong. Silakan coba lagi nanti."
            )
            return
        
        # Create detailed message
        message = "📊 **DETAIL STOK PRODUK**\n\n"
        
        total_products = len(products)
        available_products = len([p for p in products if not p.get('kosong') and not p.get('gangguan')])
        problem_products = len([p for p in products if p.get('gangguan')])
        empty_products = len([p for p in products if p.get('kosong')])
        
        message += f"📈 **Statistik Stok:**\n"
        message += f"• Total Produk: {total_products}\n"
        message += f"• Tersedia: {available_products}\n"
        message += f"• Gangguan: {problem_products}\n"
        message += f"• Kosong: {empty_products}\n\n"
        
        # Show products by category
        categories = {}
        for product in products:
            category = product.get('category', 'Umum')
            if category not in categories:
                categories[category] = []
            categories[category].append(product)
        
        for category, category_products in categories.items():
            message += f"📁 **{category.upper()}**\n"
            
            for product in category_products:
                status = "🟢 TERSEDIA"
                if product.get('kosong'):
                    status = "🔴 KOSONG"
                elif product.get('gangguan'):
                    status = "🟡 GANGGUAN"
                
                stock_info = f"Stok: {product.get('stock', 'N/A')}" if product.get('stock') is not None else "Stok: Unlimited"
                
                message += f"• {product['name']}\n"
                message += f"  💰 Rp {product['price']:,} | {status} | {stock_info}\n"
            
            message += "\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in stok_detail_command: {e}")
        await update.message.reply_text("❌ Terjadi error saat mengambil detail stok.")

def register_stok_handlers(application):
    """Register stock-related handlers"""
    application.add_handler(CommandHandler("stok", stok_command))
    application.add_handler(CommandHandler("stok_detail", stok_detail_command))
    
    logger.info("✅ Stock handlers registered successfully")
