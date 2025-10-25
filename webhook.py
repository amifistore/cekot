#!/usr/bin/env python3
"""
Enhanced Webhook Handler untuk KhfyPay - FULL INTEGRATION dengan LOGGING DETAIL
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

def log_webhook_detailed(source, message, data=None, status="INFO"):
    """Log webhook activity dengan detail lengkap"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    log_entry = {
        "timestamp": timestamp,
        "source": source,
        "status": status,
        "message": message,
        "data": data,
        "ip_address": request.remote_addr if request else "N/A"
    }
    
    # Log ke file JSON format
    with open("webhook_detailed.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    # Log ke file raw untuk debugging
    with open("webhook_raw.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{status}] {source}: {message}\n")
        if data:
            f.write(f"DATA: {json.dumps(data, ensure_ascii=False)}\n")
        f.write("-" * 80 + "\n")
    
    # Juga log ke console
    print(f"🔔 [{timestamp}] {source}: {message}")

def log_webhook_request():
    """Log semua detail request yang masuk"""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        client_ip = request.remote_addr
        method = request.method
        url = request.url
        headers = dict(request.headers)
        
        # Get request data
        content_type = request.content_type or ""
        raw_data = request.get_data(as_text=True)
        
        request_info = {
            "timestamp": timestamp,
            "client_ip": client_ip,
            "method": method,
            "url": url,
            "content_type": content_type,
            "headers": headers,
            "raw_data": raw_data,
            "args": dict(request.args),
            "form": dict(request.form)
        }
        
        # Log request details
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

def log_webhook_parsing(original_message, parsed_data, success=True):
    """Log hasil parsing webhook message"""
    status = "SUCCESS" if success else "FAILED"
    log_webhook_detailed(
        "MESSAGE_PARSING",
        f"Parsing {status}",
        {
            "original_message": original_message,
            "parsed_data": parsed_data,
            "success": success
        },
        "INFO" if success else "WARNING"
    )

def log_webhook_processing(reffid, action, details, success=True):
    """Log proses update order dari webhook"""
    status = "SUCCESS" if success else "FAILED"
    log_webhook_detailed(
        "ORDER_PROCESSING",
        f"Order {reffid} - {action} - {status}",
        {
            "reffid": reffid,
            "action": action,
            "details": details,
            "success": success,
            "processing_time": datetime.now().isoformat()
        },
        "INFO" if success else "ERROR"
    )

def log_webhook_response(response_data, status_code=200):
    """Log response yang dikirim kembali ke provider"""
    log_webhook_detailed(
        "RESPONSE_SENT",
        f"Response sent with status {status_code}",
        {
            "response_data": response_data,
            "status_code": status_code,
            "response_time": datetime.now().isoformat()
        },
        "INFO"
    )

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
                log_webhook_detailed(
                    "SN_EXTRACTION",
                    f"SN extracted from keterangan",
                    {
                        "keterangan": keterangan,
                        "sn_found": sn,
                        "pattern_used": pattern
                    },
                    "INFO"
                )
                return sn
    
    log_webhook_detailed(
        "SN_EXTRACTION",
        "No SN found in keterangan",
        {"keterangan": keterangan},
        "WARNING"
    )
    return None

def get_order_by_provider_id(reffid):
    """Get order by provider order ID"""
    try:
        # Use database function instead of raw SQL
        order = database.get_order_by_provider_id(reffid)
        
        if order:
            log_webhook_detailed(
                "ORDER_LOOKUP",
                f"Order found for reffid: {reffid}",
                {
                    "reffid": reffid,
                    "order_id": order['id'],
                    "user_id": order['user_id'],
                    "product_name": order['product_name'],
                    "current_status": order['status']
                },
                "INFO"
            )
        else:
            log_webhook_detailed(
                "ORDER_LOOKUP",
                f"Order NOT found for reffid: {reffid}",
                {"reffid": reffid},
                "ERROR"
            )
            
        return order
    except Exception as e:
        log_webhook_detailed(
            "ORDER_LOOKUP",
            f"Error looking up order: {e}",
            {"reffid": reffid, "error": str(e)},
            "ERROR"
        )
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
            log_webhook_processing(
                reffid, 
                "ORDER_NOT_FOUND", 
                {"status_received": status, "internal_status": internal_status},
                False
            )
            return False
        
        order_id = order['id']
        user_id = order['user_id']
        price = order['price']
        current_status = order['status']
        
        # Skip if status is already the same
        if current_status == internal_status:
            log_webhook_processing(
                reffid,
                "STATUS_UNCHANGED",
                {
                    "current_status": current_status,
                    "new_status": internal_status,
                    "reason": "Status already same"
                },
                True
            )
            return order
        
        # Update order status using database function
        success = database.update_order_status(
            order_id=order_id,
            status=internal_status,
            sn=sn,
            note=keterangan
        )
        
        if not success:
            log_webhook_processing(
                reffid,
                "DATABASE_UPDATE_FAILED",
                {
                    "order_id": order_id,
                    "new_status": internal_status,
                    "sn": sn
                },
                False
            )
            return False
        
        # Log status change
        log_webhook_processing(
            reffid,
            "STATUS_UPDATED",
            {
                "order_id": order_id,
                "user_id": user_id,
                "old_status": current_status,
                "new_status": internal_status,
                "sn_provided": sn,
                "keterangan": keterangan,
                "price": price
            },
            True
        )
        
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
                log_webhook_processing(
                    reffid,
                    "REFUND_PROCESSED",
                    {
                        "user_id": user_id,
                        "refund_amount": price,
                        "reason": "Order failed"
                    },
                    True
                )
            except Exception as refund_error:
                log_webhook_processing(
                    reffid,
                    "REFUND_FAILED",
                    {
                        "error": str(refund_error),
                        "refund_amount": price
                    },
                    False
                )
        
        # Update product stock if order completed
        if internal_status == 'completed' and current_status != 'completed':
            try:
                product_code = order['product_code']
                # Update stock using database function
                database.update_product(
                    product_code,
                    stock=database.get_product(product_code).get('stock', 0) - 1
                )
                log_webhook_processing(
                    reffid,
                    "STOCK_UPDATED",
                    {
                        "product_code": product_code,
                        "stock_decreased": 1
                    },
                    True
                )
            except Exception as stock_error:
                log_webhook_processing(
                    reffid,
                    "STOCK_UPDATE_FAILED",
                    {
                        "product_code": product_code,
                        "error": str(stock_error)
                    },
                    False
                )
        
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
        log_webhook_processing(
            reffid,
            "UPDATE_ERROR",
            {
                "error": str(e),
                "status_received": status,
                "keterangan": keterangan
            },
            False
        )
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
        
        log_webhook_detailed(
            "NOTIFICATION_SENT",
            f"Notification sent to user {user_id}",
            {
                "user_id": user_id,
                "provider_id": provider_id,
                "status": status,
                "has_sn": bool(sn)
            },
            "INFO"
        )
        
    except Exception as e:
        log_webhook_detailed(
            "NOTIFICATION_FAILED",
            f"Failed to send notification: {e}",
            {
                "user_id": order_data.get('user_id'),
                "provider_id": order_data.get('provider_order_id'),
                "error": str(e)
            },
            "ERROR"
        )

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    """Main webhook endpoint untuk KhfyPay"""
    # Log semua detail request yang masuk
    request_info = log_webhook_request()
    
    raw_input = request.get_data(as_text=True)
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
                else:
                    # Log seluruh JSON jika format tidak standar
                    log_webhook_detailed(
                        "JSON_PARSE",
                        "Non-standard JSON format received",
                        {"raw_json": json_data},
                        "INFO"
                    )
        except Exception as e:
            log_webhook_detailed(
                "JSON_PARSE_ERROR",
                f"Failed to parse JSON: {e}",
                {"raw_input": raw_input},
                "WARNING"
            )
    
    if not message:
        message = request.args.get("message") or request.form.get("message") or request.form.get("data")
    
    if not message or message.strip() == "":
        log_webhook_detailed(
            "EMPTY_MESSAGE",
            "Empty message received from provider",
            {
                "raw_input": raw_input,
                "request_info": request_info
            },
            "WARNING"
        )
        response = {"ok": False, "error": "message kosong"}
        log_webhook_response(response, 400)
        return jsonify(response), 400

    log_webhook_detailed(
        "MESSAGE_RECEIVED",
        "Message received from provider",
        {
            "message_length": len(message),
            "message_preview": message[:200] + "..." if len(message) > 200 else message,
            "content_type": request.content_type
        },
        "INFO"
    )

    # Parse KhfyPay message menggunakan pattern resmi
    match = re.search(KHFYPAY_PATTERN, message, re.IGNORECASE | re.DOTALL)
    
    if not match:
        log_webhook_parsing(
            message,
            None,
            False
        )
        response = {"ok": False, "error": "format tidak dikenali"}
        log_webhook_response(response, 400)
        return jsonify(response), 400

    parsed_data = match.groupdict()
    reffid = parsed_data['reffid']
    status_text = parsed_data['status_text']
    keterangan = parsed_data.get('keterangan', '').strip()
    status_code = parsed_data.get('status_code', -1)
    trxid = parsed_data.get('trxid')
    produk = parsed_data.get('produk')
    tujuan = parsed_data.get('tujuan')

    # Log parsing success
    log_webhook_parsing(
        message,
        parsed_data,
        True
    )

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
            success_message = f"Successfully updated order: {reffid} -> {order_data['status']}"
            log_webhook_detailed(
                "PROCESSING_COMPLETE",
                success_message,
                {
                    "reffid": reffid,
                    "final_status": order_data['status'],
                    "has_sn": bool(sn),
                    "user_id": order_data['user_id']
                },
                "INFO"
            )
            
            # Send notification asynchronously
            if bot_application:
                asyncio.create_task(send_order_notification(order_data))
            else:
                log_webhook_detailed(
                    "BOT_UNAVAILABLE",
                    "Bot application not available for notifications",
                    {"reffid": reffid},
                    "WARNING"
                )
                
            response = {
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
            }
            log_webhook_response(response, 200)
            return jsonify(response)
        else:
            error_message = f"Failed to update order status: {reffid}"
            log_webhook_detailed(
                "PROCESSING_FAILED",
                error_message,
                {"reffid": reffid, "status_received": status_text},
                "ERROR"
            )
            response = {"ok": False, "error": "gagal update status"}
            log_webhook_response(response, 500)
            return jsonify(response), 500
            
    except Exception as e:
        error_message = f"Error processing webhook: {e}"
        log_webhook_detailed(
            "PROCESSING_ERROR",
            error_message,
            {
                "reffid": reffid,
                "error": str(e),
                "traceback": traceback.format_exc()
            },
            "ERROR"
        )
        response = {"ok": False, "error": str(e)}
        log_webhook_response(response, 500)
        return jsonify(response), 500

@app.route("/webhook/khfypay", methods=["POST", "GET"])
def khfypay_webhook():
    """Alias untuk KhfyPay webhook"""
    return webhook()

@app.route("/webhook/logs", methods=["GET"])
def get_webhook_logs():
    """Endpoint untuk melihat log webhook terbaru"""
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
        
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/webhook/status", methods=["GET"])
def webhook_status():
    """Endpoint untuk mengecek status webhook"""
    try:
        # Count today's webhook activities
        today = datetime.now().strftime('%Y-%m-%d')
        today_count = 0
        success_count = 0
        error_count = 0
        
        try:
            with open("webhook_detailed.log", "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        if log_entry.get('timestamp', '').startswith(today):
                            today_count += 1
                            if log_entry.get('status') == 'ERROR':
                                error_count += 1
                            elif 'SUCCESS' in log_entry.get('message', ''):
                                success_count += 1
                    except:
                        continue
        except FileNotFoundError:
            pass
        
        return jsonify({
            "status": "running",
            "service": "khfypay-webhook",
            "version": "2.0-enhanced",
            "today_stats": {
                "total_webhooks": today_count,
                "successful": success_count,
                "errors": error_count
            },
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "service": "khfypay-webhook",
        "version": "2.0-enhanced",
        "logging": "enabled"
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
        print(f"📍 Logs Monitor: http://{host}:{port}/webhook/logs")
        print(f"📍 Status Check: http://{host}:{port}/webhook/status")
        print(f"📝 Detailed logging ENABLED")
        print(f"📁 Log files: webhook_detailed.log, webhook_raw.log")
        print("=" * 60)
        
        app.run(host=host, port=port, debug=False)
    except Exception as e:
        logger.error(f"❌ Failed to start webhook server: {e}")

if __name__ == "__main__":
    start_webhook_server()
