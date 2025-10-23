#!/usr/bin/env python3
"""
Auto Status Checker untuk KhfyPay - REAL-TIME UPDATES
"""

import asyncio
import logging
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
import database
import config

logger = logging.getLogger(__name__)

class KhfyPayStatusChecker:
    def __init__(self, application, check_interval=120):  # Check every 2 minutes
        self.application = application
        self.check_interval = check_interval
        self.is_running = False
        self.api_key = getattr(config, 'KHFYPAY_API_KEY', '')
        self.base_url = "https://panel.khfy-store.com/api_v2"
    
    async def start(self):
        """Start auto status checker"""
        self.is_running = True
        logger.info("🔄 KhfyPay Auto Status Checker started")
        
        while self.is_running:
            try:
                await self.check_pending_orders()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"❌ Error in KhfyPay status checker: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def stop(self):
        """Stop auto status checker"""
        self.is_running = False
        logger.info("🛑 KhfyPay Auto Status Checker stopped")
    
    async def check_pending_orders(self):
        """Check status semua order yang masih pending/processing"""
        try:
            # Get orders yang masih dalam proses (last 24 hours)
            orders = self.get_processing_orders(24)
            
            if not orders:
                return
            
            logger.info(f"🔍 Checking {len(orders)} pending orders from KhfyPay...")
            
            # Check status untuk setiap order
            for order in orders:
                if order.get('provider_order_id'):
                    await self.check_single_order(order)
                    
        except Exception as e:
            logger.error(f"❌ Error checking pending orders: {e}")
    
    def get_processing_orders(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get orders that are still processing"""
        try:
            # Use database function to get processing orders
            all_orders = database.get_all_processing_orders(hours)
            return all_orders
        except Exception as e:
            logger.error(f"❌ Error getting processing orders: {e}")
            return []
    
    async def check_single_order(self, order: Dict[str, Any]):
        """Check status individual order dari KhfyPay"""
        try:
            provider_order_id = order['provider_order_id']
            
            # Check status from KhfyPay API
            status_data = await self.check_khfypay_status(provider_order_id)
            
            if status_data and status_data.get('status') != order['status']:
                # Status berubah, update database
                await self.update_order_status(order, status_data)
                
        except Exception as e:
            logger.error(f"❌ Error checking order {order['id']}: {e}")
    
    async def check_khfypay_status(self, ref_id: str) -> Dict[str, Any]:
        """Check order status from KhfyPay API"""
        try:
            if not self.api_key:
                logger.error("KhfyPay API key not configured")
                return None
            
            url = f"{self.base_url}/history"
            params = {
                "api_key": self.api_key,
                "refid": ref_id
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result
                    else:
                        logger.error(f"KhfyPay API error: {response.status}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.error(f"⏰ Timeout checking KhfyPay status for {ref_id}")
            return None
        except Exception as e:
            logger.error(f"❌ Error checking KhfyPay status: {e}")
            return None
    
    async def update_order_status(self, order: Dict[str, Any], status_data: Dict[str, Any]):
        """Update order status berdasarkan data dari KhfyPay"""
        try:
            order_id = order['id']
            new_status = status_data.get('data', {}).get('status', order['status'])
            sn = status_data.get('data', {}).get('sn')
            note = status_data.get('message', 'Auto-check from KhfyPay')
            
            # Skip if status is the same
            if new_status == order['status']:
                return
            
            # Update order status using database function
            success = database.update_order_status(
                order_id=order_id,
                status=new_status,
                sn=sn,
                note=note
            )
            
            if success:
                logger.info(f"✅ Order {order_id} auto-updated to: {new_status}")
                
                # Send notification to user
                await self.send_status_notification(order, new_status, sn, note)
                
                # Process refund if failed
                if new_status == 'failed':
                    await self.process_auto_refund(order)
            else:
                logger.error(f"❌ Failed to auto-update order {order_id}")
                
        except Exception as e:
            logger.error(f"❌ Error updating order status: {e}")
    
    async def process_auto_refund(self, order: Dict[str, Any]):
        """Process automatic refund for failed orders"""
        try:
            user_id = order['user_id']
            amount = order['price']
            
            # Refund user balance
            success = database.update_user_balance(
                user_id,
                amount,
                f"Auto-refund for failed order {order['id']}",
                "refund"
            )
            
            if success:
                logger.info(f"💰 Auto-refund processed for order {order['id']}: {amount} to user {user_id}")
            else:
                logger.error(f"❌ Failed to process auto-refund for order {order['id']}")
                
        except Exception as e:
            logger.error(f"❌ Error processing auto-refund: {e}")
    
    async def send_status_notification(self, order: Dict[str, Any], new_status: str, sn: str = None, note: str = ""):
        """Kirim notifikasi status update ke user"""
        try:
            user_id = order['user_id']
            
            status_emoji = {
                'completed': '✅',
                'pending': '⏳', 
                'failed': '❌',
                'processing': '🔄',
                'refunded': '💸'
            }.get(new_status, '❓')
            
            message = (
                f"{status_emoji} *KHFYPAY AUTO-UPDATE*\n\n"
                f"📦 *Produk:* {order['product_name']}\n"
                f"📮 *Tujuan:* `{order['customer_input']}`\n"
                f"💰 *Harga:* Rp {order['price']:,}\n"
                f"🆔 *Ref ID:* `{order['provider_order_id']}`\n"
                f"📊 *Status:* {new_status.upper()}\n"
            )
            
            if sn:
                message += f"🔢 *SN:* `{sn}`\n"
            if note:
                message += f"📝 *Keterangan:* {note}\n"
            
            message += f"\n⏰ *Update:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            await self.application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"📢 Auto-notification sent to user {user_id} for order {order['id']}")
            
        except Exception as e:
            logger.error(f"❌ Error sending auto-notification: {e}")

# Global instance
_status_checker = None

def start_auto_status_checker(application, check_interval=120):
    """Start auto status checker service"""
    global _status_checker
    if _status_checker is None:
        _status_checker = KhfyPayStatusChecker(application, check_interval)
    
    import threading
    def run_checker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_status_checker.start())
    
    checker_thread = threading.Thread(target=run_checker, daemon=True)
    checker_thread.start()
    logger.info("🚀 KhfyPay Auto Status Checker service started")
    
    return _status_checker

def stop_auto_status_checker():
    """Stop auto status checker service"""
    global _status_checker
    if _status_checker:
        _status_checker.stop()
        _status_checker = None
        logger.info("🛑 KhfyPay Auto Status Checker service stopped")
