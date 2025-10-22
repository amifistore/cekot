#!/usr/bin/env python3
"""
Webhook Handler untuk Real-time Order Updates - SYNC VERSION
"""

import logging
import re
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
import database
import asyncio

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('webhook.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = "bot_database.db"
app = Flask(__name__)

# Global variable untuk bot application
bot_application = None

def set_bot_application(app):
    """Set bot application for sending notifications"""
    global bot_application
    bot_application = app

def log_webhook(msg):
    """Log webhook activity"""
    with open("webhook_raw.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")

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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT id, user_id, product_name, customer_input, price, status, 
                   provider_order_id, sn, note, status_refund
            FROM orders 
            WHERE provider_order_id = ?
        """, (reffid,))
        
        order = c.fetchone()
        conn.close()
        
        if order:
            return {
                'id': order[0],
                'user_id': order[1],
                'product_name': order[2],
                'customer_input': order[3],
                'price': order[4],
                'status': order[5],
                'provider_order_id': order[6],
                'sn': order[7],
                'note': order[8],
                'status_refund': order[9]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting order by provider ID: {e}")
        return None

def update_order_status_from_webhook(reffid, status, keterangan=None, sn=None):
    """Update order status based on webhook data - FIXED VERSION"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
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
        
        # Get current order status
        c.execute("""
            SELECT id, user_id, product_name, customer_input, price, status, 
                   status_refund, sn, note
            FROM orders WHERE provider_order_id = ?
        """, (reffid,))
        
        current_order = c.fetchone()
        
        if not current_order:
            logger.error(f"Order not found for reffid: {reffid}")
            conn.close()
            return False
        
        order_id, user_id, product_name, target, price, current_status, current_refund, current_sn, current_note = current_order
        
        # Skip if status is already the same
        if current_status == internal_status:
            logger.info(f"Order {reffid} status already {internal_status}, skipping update")
            conn.close()
            return {
                'id': order_id,
                'user_id': user_id,
                'product_name': product_name,
                'customer_input': target,
                'price': price,
                'status': internal_status,
                'provider_order_id': reffid,
                'sn': sn or current_sn,
                'note': keterangan or current_note
            }
        
        # Update order status
        update_query = """
            UPDATE orders 
            SET status = ?, updated_at = ?, note = COALESCE(?, note)
            WHERE provider_order_id = ?
        """
        update_params = [internal_status, datetime.now(), keterangan, reffid]
        
        if sn:
            update_query = """
                UPDATE orders 
                SET status = ?, updated_at = ?, note = COALESCE(?, note), sn = ?
                WHERE provider_order_id = ?
            """
            update_params = [internal_status, datetime.now(), keterangan, sn, reffid]
        
        c.execute(update_query, update_params)
        
        # If order failed and needs refund, process refund
        if internal_status == 'failed' and current_refund == 0:
            # Refund user balance using database function
            try:
                database.update_user_balance(user_id, price, f"Refund order gagal: {reffid}", "refund")
                # Mark as refunded
                c.execute("UPDATE orders SET status_refund = 1 WHERE provider_order_id = ?", (reffid,))
                logger.info(f"Refund processed for order {reffid}: user {user_id} amount {price}")
            except Exception as refund_error:
                logger.error(f"Error processing refund: {refund_error}")
        
        conn.commit()
        conn.close()
        
        logger.info(f"Order status updated: {reffid} -> {internal_status}")
        
        # Return updated order data for notification
        return {
            'id': order_id,
            'user_id': user_id,
            'product_name': product_name,
            'customer_input': target,
            'price': price,
            'status': internal_status,
            'provider_order_id': reffid,
            'sn': sn or current_sn,
            'note': keterangan or current_note
        }
        
    except Exception as e:
        logger.error(f"Error updating order status from webhook: {e}")
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
            f"{status_emoji} *UPDATE STATUS ORDER*\n\n"
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
        
        logger.info(f"Notification sent to user {user_id} for order {provider_id}")
        
    except Exception as e:
        logger.error(f"Error sending order notification: {e}")

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    """Main webhook endpoint"""
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

    logger.info(f"Processing webhook message: {message}")

    # Multiple patterns untuk parsing message dari provider
    patterns = [
        r'RC=(?P<reffid>[a-z0-9_.-]+)\s+TrxID=(?P<trxid>\d+)\s+(?P<produk>[A-Z0-9]+)\.(?P<tujuan>\d+)\s+(?P<status_text>[A-Za-z]+)[, ]*(?P<keterangan>.+?)Saldo[\s\S]*?result=(?P<status_code>\d+)',
        r'ReffID[=:]?\s*(?P<reffid>[a-z0-9_.-]+).*?Status[=:]?\s*(?P<status_text>[A-Za-z]+).*?Keterangan[=:]?\s*(?P<keterangan>[^\.]+)',
        r'reff_id[=:]?\s*(?P<reffid>[a-z0-9_.-]+).*?status[=:]?\s*(?P<status_text>[A-Za-z]+)',
        r'RC=(?P<reffid>[a-f0-9-]+)\s+TrxID=(?P<trxid>\d+)\s+(?P<produk>[A-Z0-9]+)\.(?P<tujuan>\d+)\s+(?P<status_text>[A-Za-z]+)\s*(?P<keterangan>.+?)(?:\s+Saldo[\s\S]*?)?(?:\bresult=(?P<status_code>\d+))?\s*>?$'
    ]
    
    parsed_data = None
    for pattern in patterns:
        m = re.search(pattern, message, re.I | re.DOTALL)
        if m:
            parsed_data = m.groupdict()
            break
    
    if not parsed_data or 'reffid' not in parsed_data or 'status_text' not in parsed_data:
        log_webhook(f'[WEBHOOK] format tidak dikenali -> {message}')
        return jsonify({"ok": False, "error": "format tidak dikenali"}), 400

    reffid = parsed_data['reffid']
    status_text = parsed_data['status_text']
    keterangan = parsed_data.get('keterangan', '').strip()
    status_code = parsed_data.get('status_code', -1)

    logger.info(f"Parsed webhook: reffid={reffid}, status={status_text}, keterangan={keterangan}")

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
            logger.info(f"Successfully updated order status: {reffid} -> {order_data['status']}")
            
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
                    "keterangan": keterangan
                }
            })
        else:
            logger.error(f"Failed to update order status: {reffid}")
            return jsonify({"ok": False, "error": "gagal update status"}), 500
            
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "service": "khfypay-webhook"
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
            "sn": order_data['sn'],
            "note": order_data['note'],
            "last_updated": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting order status: {e}")
        return jsonify({"error": str(e)}), 500

def start_webhook_server(host="0.0.0.0", port=8080):
    """Start webhook server"""
    try:
        print(f"🌐 Starting webhook server on {host}:{port}")
        app.run(host=host, port=port, debug=False)
    except Exception as e:
        logger.error(f"Failed to start webhook server: {e}")

if __name__ == "__main__":
    start_webhook_server()
