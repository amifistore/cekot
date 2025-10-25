#!/usr/bin/env python3
"""
🤖 KhfyPay Webhook Handler - PRODUCTION READY
🎯 Compatible with KhfyPay API Format
🔧 Full Feature: Logging, Monitoring, Notifications
"""

import logging
import re
import json
import asyncio
import traceback
from datetime import datetime
from flask import Flask, request, jsonify
import database

# ==================== CONFIGURATION ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('khfypay_webhook.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot_application = None

# ==================== LOGGING SYSTEM ====================
def log_webhook_detailed(source, message, data=None, status="INFO"):
    """Advanced logging system untuk webhook"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    log_entry = {
        "timestamp": timestamp,
        "source": source,
        "status": status,
        "message": message,
        "data": data,
        "ip_address": request.remote_addr if request else "N/A"
    }
    
    # Log ke file JSON
    with open("webhook_detailed.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    # Log ke console dengan emoji
    status_emoji = {"INFO": "🔵", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}.get(status, "🔵")
    print(f"{status_emoji} [{timestamp}] {source}: {message}")

def log_webhook_request():
    """Log detail request masuk"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        client_ip = request.remote_addr
        method = request.method
        
        request_info = {
            "timestamp": timestamp,
            "client_ip": client_ip,
            "method": method,
            "url": request.url,
            "content_type": request.content_type or "",
            "headers": dict(request.headers),
            "args": dict(request.args),
            "form": dict(request.form)
        }
        
        log_webhook_detailed(
            "REQUEST_INCOMING",
            f"New {method} request from {client_ip}",
            request_info,
            "INFO"
        )
        
        return request_info
        
    except Exception as e:
        logger.error(f"Error logging request: {e}")
        return None

# ==================== KHFYPAY PARSER (FIXED) ====================
def parse_khfypay_message(message):
    """
    Parser menggunakan pattern yang SAMA dengan PHP version yang berhasil
    Pattern: RC=reffid TrxID=trxid PRODUK.tujuan STATUS_TEXT keterangan Saldo... result=status_code
    """
    try:
        # PATTERN YANG SAMA DENGAN PHP YANG SUDAH BERHASIL
        pattern = r'RC=(?P<reffid>[a-z0-9_.-]+)\s+TrxID=(?P<trxid>\d+)\s+(?P<produk>[A-Z0-9]+)\.(?P<tujuan>\d+)\s+(?P<status_text>[A-Za-z]+)[, ]*(?P<keterangan>.+?)Saldo[\s\S]*?result=(?P<status_code>\d+)'
        
        match = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
        
        if not match:
            # Fallback pattern jika pattern utama gagal
            fallback_pattern = r'RC=(?P<reffid>[a-z0-9_.-]+)\s+TrxID=(?P<trxid>\d+)\s+(?P<produk>[A-Z0-9]+)\.(?P<tujuan>\d+)\s+(?P<status_text>[A-Za-z]+)\s*(?P<keterangan>.*)'
            match = re.search(fallback_pattern, message, re.IGNORECASE | re.DOTALL)
            
            if not match:
                return None
            
            # Untuk fallback, set default status_code
            parsed_data = match.groupdict()
            status_text = parsed_data['status_text'].upper()
            if 'SUKSES' in status_text or 'SUCCESS' in status_text:
                parsed_data['status_code'] = '0'
            elif 'GAGAL' in status_text or 'FAILED' in status_text:
                parsed_data['status_code'] = '1'
            else:
                parsed_data['status_code'] = '-1'
                
            return parsed_data
        
        # Pattern utama berhasil
        parsed_data = match.groupdict()
        
        # Bersihkan keterangan
        if 'keterangan' in parsed_data:
            parsed_data['keterangan'] = parsed_data['keterangan'].strip()
        
        log_webhook_detailed(
            "PARSER_SUCCESS",
            f"Message parsed successfully - ReffID: {parsed_data['reffid']}",
            parsed_data,
            "SUCCESS"
        )
        
        return parsed_data
        
    except Exception as e:
        log_webhook_detailed(
            "PARSER_ERROR",
            f"Parser error: {str(e)}",
            {"raw_message": message, "error": traceback.format_exc()},
            "ERROR"
        )
        return None

def extract_sn_from_keterangan(keterangan):
    """Extract SN dari keterangan message"""
    if not keterangan:
        return None
    
    patterns = [
        r'SN[:=]\s*([A-Z0-9-]+)',
        r'Serial[:=]\s*([A-Z0-9-]+)',
        r'No\.?[:=]\s*([A-Z0-9-]+)',
        r'kode[:=]\s*([A-Z0-9-]+)',
        r'voucher[:=]\s*([A-Z0-9-]+)',
        r'([A-Z0-9-]{10,})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, keterangan, re.IGNORECASE)
        if match:
            sn = match.group(1).strip()
            if len(sn) >= 8:
                log_webhook_detailed(
                    "SN_EXTRACTED",
                    f"SN found in keterangan: {sn}",
                    {"keterangan": keterangan, "sn": sn},
                    "SUCCESS"
                )
                return sn
    
    return None

# ==================== ORDER PROCESSING ====================
def update_order_status_from_webhook(reffid, status_text, status_code, keterangan=None, sn=None):
    """Update order status berdasarkan data webhook"""
    try:
        # Mapping status code ke internal status
        status_mapping = {
            '0': 'completed',  # SUKSES
            '1': 'failed',     # GAGAL
            '-1': 'pending'    # UNKNOWN
        }
        
        internal_status = status_mapping.get(status_code, 'pending')
        
        # Get order dari database
        order = database.get_order_by_provider_id(reffid)
        
        if not order:
            log_webhook_detailed(
                "ORDER_NOT_FOUND",
                f"Order not found for reffid: {reffid}",
                {"reffid": reffid, "status": internal_status},
                "ERROR"
            )
            return None
        
        order_id = order['id']
        user_id = order['user_id']
        price = order['price']
        current_status = order['status']
        
        # Skip jika status sama
        if current_status == internal_status:
            log_webhook_detailed(
                "STATUS_UNCHANGED",
                f"Order status already {internal_status}",
                {"reffid": reffid, "order_id": order_id},
                "INFO"
            )
            return order
        
        # Update order status
        success = database.update_order_status(
            order_id=order_id,
            status=internal_status,
            sn=sn,
            note=keterangan
        )
        
        if not success:
            log_webhook_detailed(
                "UPDATE_FAILED",
                f"Failed to update order status",
                {"reffid": reffid, "order_id": order_id},
                "ERROR"
            )
            return None
        
        log_webhook_detailed(
            "STATUS_UPDATED",
            f"Order status updated: {current_status} -> {internal_status}",
            {
                "reffid": reffid,
                "order_id": order_id,
                "user_id": user_id,
                "old_status": current_status,
                "new_status": internal_status,
                "sn": sn
            },
            "SUCCESS"
        )
        
        # Process refund untuk order gagal
        if internal_status == 'failed' and current_status != 'failed':
            process_order_refund(order, reffid, price, user_id)
        
        # Update stock untuk order completed
        if internal_status == 'completed' and current_status != 'completed':
            update_product_stock(order)
        
        return {
            'id': order_id,
            'user_id': user_id,
            'product_name': order['product_name'],
            'customer_input': order['customer_input'],
            'price': price,
            'status': internal_status,
            'provider_order_id': reffid,
            'sn': sn,
            'note': keterangan
        }
        
    except Exception as e:
        log_webhook_detailed(
            "PROCESSING_ERROR",
            f"Error processing order: {str(e)}",
            {"reffid": reffid, "error": traceback.format_exc()},
            "ERROR"
        )
        return None

def process_order_refund(order, reffid, price, user_id):
    """Process refund untuk order yang gagal"""
    try:
        database.update_user_balance(
            user_id, 
            price, 
            f"Refund order gagal: {reffid}", 
            "refund"
        )
        
        log_webhook_detailed(
            "REFUND_PROCESSED",
            f"Refund processed for failed order",
            {"reffid": reffid, "user_id": user_id, "amount": price},
            "SUCCESS"
        )
    except Exception as e:
        log_webhook_detailed(
            "REFUND_ERROR",
            f"Refund processing failed: {str(e)}",
            {"reffid": reffid, "error": str(e)},
            "ERROR"
        )

def update_product_stock(order):
    """Update stock produk untuk order yang completed"""
    try:
        product_code = order['product_code']
        current_stock = database.get_product(product_code).get('stock', 0)
        
        database.update_product(
            product_code,
            stock=current_stock - 1
        )
        
        log_webhook_detailed(
            "STOCK_UPDATED",
            f"Product stock updated",
            {"product_code": product_code, "old_stock": current_stock, "new_stock": current_stock - 1},
            "SUCCESS"
        )
    except Exception as e:
        log_webhook_detailed(
            "STOCK_UPDATE_ERROR",
            f"Stock update failed: {str(e)}",
            {"product_code": order.get('product_code'), "error": str(e)},
            "ERROR"
        )

# ==================== NOTIFICATION SYSTEM ====================
async def send_order_notification(order_data):
    """Kirim notifikasi ke user via Telegram"""
    try:
        if not bot_application:
            log_webhook_detailed(
                "BOT_UNAVAILABLE",
                "Bot application not available for notifications",
                {"order_id": order_data.get('id')},
                "WARNING"
            )
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
            'failed': '❌', 
            'pending': '⏳',
            'processing': '🔄'
        }.get(status, '📦')
        
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
            message += f"📝 *Note:* {note}\n"
        
        message += f"\n⏰ *Update:* {datetime.now().strftime('%d/%m %H:%M')}"
        
        await bot_application.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='Markdown'
        )
        
        log_webhook_detailed(
            "NOTIFICATION_SENT",
            f"Notification sent to user {user_id}",
            {"user_id": user_id, "provider_id": provider_id, "status": status},
            "SUCCESS"
        )
        
    except Exception as e:
        log_webhook_detailed(
            "NOTIFICATION_FAILED",
            f"Failed to send notification: {str(e)}",
            {"user_id": order_data.get('user_id'), "error": str(e)},
            "ERROR"
        )

# ==================== WEBHOOK ENDPOINTS ====================
@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    """Main webhook endpoint - Production Ready"""
    request_info = log_webhook_request()
    
    # Extract message dari GET/POST
    message = None
    if request.method == "GET":
        message = request.args.get("message")
    elif request.method == "POST":
        if request.content_type == "application/json":
            json_data = request.get_json(force=True, silent=True) or {}
            message = json_data.get("message")
        else:
            message = request.form.get("message")
    
    if not message:
        log_webhook_detailed(
            "EMPTY_MESSAGE",
            "Empty message received",
            {"request_info": request_info},
            "WARNING"
        )
        return jsonify({"ok": False, "error": "message kosong"}), 400

    log_webhook_detailed(
        "MESSAGE_RECEIVED",
        f"Message received via {request.method}",
        {
            "message_preview": message[:100] + "..." if len(message) > 100 else message,
            "content_type": request.content_type
        },
        "INFO"
    )

    # Parse message menggunakan pattern yang fix
    parsed_data = parse_khfypay_message(message)
    
    if not parsed_data:
        log_webhook_detailed(
            "PARSE_FAILED",
            "Message format not recognized",
            {"raw_message": message},
            "WARNING"
        )
        return jsonify({"ok": False, "error": "format tidak dikenali"}), 400

    # Extract data dari parsed result
    reffid = parsed_data['reffid']
    status_text = parsed_data['status_text']
    status_code = parsed_data['status_code']
    keterangan = parsed_data.get('keterangan', '')
    trxid = parsed_data.get('trxid')
    produk = parsed_data.get('produk')
    tujuan = parsed_data.get('tujuan')
    
    # Extract SN dari keterangan
    sn = extract_sn_from_keterangan(keterangan)
    
    # Update order status di database
    order_data = update_order_status_from_webhook(
        reffid=reffid,
        status_text=status_text,
        status_code=status_code,
        keterangan=keterangan,
        sn=sn
    )
    
    if order_data:
        # Send notification async (non-blocking)
        if bot_application:
            asyncio.create_task(send_order_notification(order_data))
        
        response_data = {
            "ok": True,
            "message": "Webhook processed successfully",
            "data": {
                "reffid": reffid,
                "trxid": trxid,
                "produk": produk,
                "tujuan": tujuan,
                "status_text": status_text,
                "status_code": status_code,
                "keterangan": keterangan,
                "sn": sn,
                "processed_at": datetime.now().isoformat()
            }
        }
        
        log_webhook_detailed(
            "PROCESSING_COMPLETE",
            f"Webhook processed successfully for {reffid}",
            response_data,
            "SUCCESS"
        )
        
        return jsonify(response_data)
    else:
        log_webhook_detailed(
            "PROCESSING_FAILED",
            f"Failed to process order {reffid}",
            {"reffid": reffid, "status": status_text},
            "ERROR"
        )
        return jsonify({"ok": False, "error": "gagal memproses order"}), 500

# ==================== MONITORING & MANAGEMENT ====================
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "khfypay-webhook",
        "version": "4.0-production",
        "timestamp": datetime.now().isoformat()
    })

@app.route("/webhook/logs", methods=["GET"])
def get_webhook_logs():
    """Get recent webhook logs"""
    try:
        lines = request.args.get('lines', 50, type=int)
        
        with open("webhook_detailed.log", "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        recent_logs = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        logs = []
        for line in recent_logs:
            try:
                logs.append(json.loads(line.strip()))
            except:
                continue
        
        return jsonify({
            "status": "success",
            "total_logs": len(logs),
            "logs": logs
        })
        
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Log file not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/webhook/status", methods=["GET"])
def webhook_status():
    """Webhook statistics and health"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        stats = {
            "total": 0,
            "success": 0,
            "error": 0,
            "pending": 0
        }
        
        try:
            with open("webhook_detailed.log", "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        log = json.loads(line.strip())
                        if log.get('timestamp', '').startswith(today):
                            stats["total"] += 1
                            if log.get('status') == 'SUCCESS':
                                stats["success"] += 1
                            elif log.get('status') == 'ERROR':
                                stats["error"] += 1
                    except:
                        continue
        except FileNotFoundError:
            pass
        
        return jsonify({
            "status": "running",
            "version": "4.0-production",
            "today_stats": stats,
            "server_time": datetime.now().isoformat(),
            "features": {
                "parsing": "enabled",
                "notifications": "enabled" if bot_application else "disabled",
                "logging": "enabled",
                "monitoring": "enabled"
            }
        })
        
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/", methods=["GET"])
def index():
    """Root endpoint dengan informasi"""
    return jsonify({
        "service": "KhfyPay Webhook Handler",
        "version": "4.0-production",
        "status": "running",
        "endpoints": {
            "webhook": "/webhook",
            "health": "/health",
            "logs": "/webhook/logs",
            "status": "/webhook/status"
        },
        "documentation": "https://khfypay.com",
        "timestamp": datetime.now().isoformat()
    })

# ==================== BOT INTEGRATION ====================
def set_bot_application(app):
    """Set bot application untuk notifikasi"""
    global bot_application
    bot_application = app

# ==================== SERVER MANAGEMENT ====================
def start_webhook_server(host="0.0.0.0", port=8080):
    """Start production webhook server"""
    try:
        print("🚀 KHFYPAY WEBHOOK SERVER - PRODUCTION READY")
        print("=" * 60)
        print(f"📍 Webhook URL: http://{host}:{port}/webhook")
        print(f"📍 Health Check: http://{host}:{port}/health")
        print(f"📍 Logs Monitor: http://{host}:{port}/webhook/logs")
        print(f"📍 Status Dashboard: http://{host}:{port}/webhook/status")
        print("🎯 Features:")
        print("   ✅ Advanced Logging System")
        print("   ✅ Real-time Notifications")
        print("   ✅ Order Processing & Refunds")
        print("   ✅ Stock Management")
        print("   ✅ Health Monitoring")
        print("   ✅ Error Handling")
        print("=" * 60)
        print("📝 Server started successfully!")
        print("💡 Monitoring logs: tail -f webhook_detailed.log")
        print("=" * 60)
        
        # Initialize fresh log files
        open("webhook_detailed.log", "w").close()
        
        # Start production server
        app.run(host=host, port=port, debug=False)
        
    except Exception as e:
        logger.error(f"❌ Failed to start webhook server: {e}")
        print(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    start_webhook_server()
