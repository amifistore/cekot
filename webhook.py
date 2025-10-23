#!/usr/bin/env python3
"""
Enhanced Webhook Handler untuk KhfyPay - FULL INTEGRATION
"""

import logging
import re
import json
import asyncio
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
import database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('khfypay_webhook.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = "bot_database.db"
app = Flask(__name__)
bot_application = None

def set_bot_application(app):
    """Set bot application for sending notifications"""
    global bot_application
    bot_application = app

def log_webhook(msg):
    """Log webhook activity"""
    with open("webhook_raw.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")

# KhfyPay specific regex pattern (sesuai dokumentasi)
KHFYPAY_PATTERN = r'RC=(?P<reffid>[a-f0-9-]+)\s+TrxID=(?P<trxid>\d+)\s+(?P<produk>[A-Z0-9]+)\.(?P<tujuan>\d+)\s+(?P<status_text>[A-Za-z]+)\s*(?P<keterangan>.+?)(?:\s+Saldo[\s\S]*?)?(?:\bresult=(?P<status_code>\d+))?\s*>?$'

def extract_sn_from_keterangan(keterangan):
    """Extract SN from keterangan message"""
    if not keterangan:
        return None
    
    # Pattern untuk mencari SN
    patterns = [
        r'SN[:=]\s*([A-Z0-9-]+)',
        r'Serial[:=]\s*([A-Z0-9-]+)',
        r'No\.?[:=]\s*([A-Z0-9-]+)',
        r'kode[:=]\s*([A-Z0-9-]+)',
        r'voucher[:=]\s*([A-Z0-9-]+)',
        r'([A-Z0-9-]{10,})'  # Generic pattern for alphanumeric codes
    ]
    
    for pattern in patterns:
        match = re.search(pattern, keterangan, re.IGNORECASE)
        if match:
            sn = match.group(1).strip()
            if len(sn) >= 8:  # Minimum length for SN
                return sn
    
    return None

def get_order_by_provider_id(reffid):
    """Get order by provider order ID"""
    try:
        # Use database function instead of raw SQL
        return database.get_order_by_provider_id(reffid)
    except Exception as e:
        logger.error(f"Error getting order by provider ID: {e}")
        return None

def update_order_status_from_webhook(reffid, status, keterangan=None, sn=None):
    """Update order status based on webhook data - ENHANCED VERSION"""
    try:
        # Map webhook status to internal status
        status_mapping = {
            'SUKSES': 'completed',
            'GAGAL': 'failed',
            'PENDING': 'pending',
            'PROSES': 'processing',
            'REFUND': 'refunded',
            'SUCCESS': 'completed',
            'FAILED': 'failed',
            'PROCCESS': 'processing'
        }
        
        internal_status = status_mapping.get(status.upper(), status.lower())
        
        # Get current order status using database function
        order = database.get_order_by_provider_id(reffid)
        
        if not order:
            logger.error(f"Order not found for reffid: {reffid}")
            return False
        
        order_id = order['id']
        user_id = order['user_id']
        price = order['price']
        current_status = order['status']
        
        # Skip if status is already the same
        if current_status == internal_status:
            logger.info(f"Order {reffid} status already {internal_status}, skipping update")
            return order
        
        # Update order status using database function
        success = database.update_order_status(
            order_id=order_id,
            status=internal_status,
            sn=sn,
            note=keterangan
        )
        
        if not success:
            logger.error(f"Failed to update order status for {reffid}")
            return False
        
        # If order failed and needs refund, process refund
        if internal_status == 'failed' and current_status != 'failed':
            try:
                # Refund user balance using database function
                database.update_user_balance(
                    user_id, 
                    price, 
                    f"Refund order gagal via webhook: {reffid}", 
                    "refund"
                )
                logger.info(f"Refund processed for order {reffid}: user {user_id} amount {price}")
            except Exception as refund_error:
                logger.error(f"Error processing refund: {refund_error}")
        
        # Update product stock if order completed
        if internal_status == 'completed' and current_status != 'completed':
            try:
                product_code = order['product_code']
                # Update stock using database function
                database.update_product(
                    product_code,
                    stock=database.get_product(product_code).get('stock', 0) - 1
                )
                logger.info(f"Stock updated for product {product_code}")
            except Exception as stock_error:
                logger.error(f"Error updating stock: {stock_error}")
        
        logger.info(f"✅ Order status updated via webhook: {reffid} -> {internal_status}")
        
        # Return updated order data for notification
        return {
            'id': order_id,
            'user_id': user_id,
            'product_name': order['product_name'],
            'product_code': order['product_code'],
            'customer_input': order['customer_input'],
            'price': price,
            'status': internal_status,
            'provider_order_id': reffid,
            'sn': sn,
            'note': keterangan
        }
        
    except Exception as e:
        logger.error(f"❌ Error updating order status from webhook: {e}")
        return False

async def send_order_notification(order_data):
    """Send order status update notification to user"""
    try:
        if not bot_application:
            logger.error("Bot application not set for sending notifications")
            return
        
        user_id = order_data['user_id']
        product_name = order_data['product_name']
        target = order_data['customer_input']
        price = order_data['price']
        status = order_data['status']
        provider_id = order_data['provider_order_id']
        sn = order_data.get('sn')
        note = order_data.get('note')
        
        status_emoji = {
            'completed': '✅',
            'pending': '⏳', 
            'failed': '❌',
            'processing': '🔄',
            'refunded': '💸',
            'partial': '⚠️'
        }.get(status, '❓')
        
        message = (
            f"{status_emoji} *UPDATE STATUS ORDER - KHFYPAY*\n\n"
            f"📦 *Produk:* {product_name}\n"
            f"📮 *Tujuan:* `{target}`\n"
            f"💰 *Harga:* Rp {price:,}\n"
            f"🆔 *Ref ID:* `{provider_id}`\n"
            f"📊 *Status:* {status.upper()}\n"
        )
        
        if sn:
            message += f"🔢 *SN:* `{sn}`\n"
        if note:
            message += f"📝 *Keterangan:* {note}\n"
        
        message += f"\n⏰ *Update:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await bot_application.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='Markdown'
        )
        
        logger.info(f"📢 Webhook notification sent to user {user_id} for order {provider_id}")
        
    except Exception as e:
        logger.error(f"❌ Error sending webhook notification: {e}")

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    """Main webhook endpoint untuk KhfyPay"""
    raw_input = request.get_data(as_text=True)
    log_webhook(f"RAW: {raw_input}")
    
    message = None

    # Try to extract message from different formats
    if raw_input:
        try:
            json_data = request.get_json(force=True, silent=True)
            if json_data:
                if "message" in json_data and isinstance(json_data["message"], str):
                    message = json_data["message"]
                elif "data" in json_data and isinstance(json_data["data"], str):
                    message = json_data["data"]
        except Exception as e:
            logger.warning(f"Failed to parse JSON: {e}")
    
    if not message:
        message = request.args.get("message") or request.form.get("message") or request.form.get("data")
    
    if not message or message.strip() == "":
        log_webhook("[WEBHOOK] message kosong")
        return jsonify({"ok": False, "error": "message kosong"}), 400

    logger.info(f"Processing KhfyPay webhook message: {message}")

    # Parse KhfyPay message menggunakan pattern resmi
    match = re.search(KHFYPAY_PATTERN, message, re.IGNORECASE | re.DOTALL)
    
    if not match:
        log_webhook(f'[WEBHOOK] format tidak dikenali -> {message}')
        return jsonify({"ok": False, "error": "format tidak dikenali"}), 400

    parsed_data = match.groupdict()
    reffid = parsed_data['reffid']
    status_text = parsed_data['status_text']
    keterangan = parsed_data.get('keterangan', '').strip()
    status_code = parsed_data.get('status_code', -1)
    trxid = parsed_data.get('trxid')
    produk = parsed_data.get('produk')
    tujuan = parsed_data.get('tujuan')

    logger.info(f"Parsed KhfyPay webhook: reffid={reffid}, status={status_text}, keterangan={keterangan}")

    # Extract SN from keterangan
    sn = extract_sn_from_keterangan(keterangan)
    
    # Update order status
    try:
        order_data = update_order_status_from_webhook(
            reffid=reffid,
            status=status_text,
            keterangan=keterangan,
            sn=sn
        )
        
        if order_data:
            logger.info(f"✅ Successfully updated order status: {reffid} -> {order_data['status']}")
            
            # Send notification asynchronously
            if bot_application:
                asyncio.create_task(send_order_notification(order_data))
            else:
                logger.warning("Bot application not available for sending notifications")
                
            return jsonify({
                "ok": True,
                "message": "Webhook processed successfully",
                "data": {
                    "reffid": reffid,
                    "status": order_data['status'],
                    "sn": sn,
                    "trxid": trxid,
                    "produk": produk,
                    "tujuan": tujuan,
                    "keterangan": keterangan
                }
            })
        else:
            logger.error(f"❌ Failed to update order status: {reffid}")
            return jsonify({"ok": False, "error": "gagal update status"}), 500
            
    except Exception as e:
        logger.error(f"❌ Error updating order status: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/webhook/khfypay", methods=["POST", "GET"])
def khfypay_webhook():
    """Alias untuk KhfyPay webhook"""
    return webhook()

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "service": "khfypay-webhook",
        "version": "2.0"
    })

@app.route("/order/<reffid>", methods=["GET"])
def get_order_status(reffid):
    """Get order status by reffid"""
    try:
        order_data = get_order_by_provider_id(reffid)
        
        if not order_data:
            return jsonify({"error": "Order not found"}), 404
            
        return jsonify({
            "reffid": reffid,
            "product_name": order_data['product_name'],
            "target": order_data['customer_input'],
            "price": order_data['price'],
            "status": order_data['status'],
            "sn": order_data.get('sn'),
            "note": order_data.get('note'),
            "last_updated": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting order status: {e}")
        return jsonify({"error": str(e)}), 500

def start_webhook_server(host="0.0.0.0", port=8080):
    """Start webhook server"""
    try:
        print(f"🌐 Starting KhfyPay Webhook Server on {host}:{port}")
        print(f"📍 Webhook URL: http://{host}:{port}/webhook")
        print(f"📍 Health Check: http://{host}:{port}/health")
        app.run(host=host, port=port, debug=False)
    except Exception as e:
        logger.error(f"❌ Failed to start webhook server: {e}")

if __name__ == "__main__":
    start_webhook_server()
