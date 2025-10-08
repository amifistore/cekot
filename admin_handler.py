from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
import logging
import re
from datetime import datetime
from database import database

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_admin(user) -> bool:
    """Check if user is admin"""
    try:
        if not user:
            return False
            
        # Ganti dengan logic admin check yang sesuai
        admin_ids = [123456789, 987654321]  # Example admin IDs - GANTI DENGAN ID ADMIN ANDA
        return user.id in admin_ids
        
    except Exception as e:
        logger.error(f"Error in is_admin: {e}")
        return False

async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Helper function to check admin and send message if not"""
    if not is_admin(update.effective_user):
        if update.message:
            await update.message.reply_text("❌ Hanya admin yang bisa menggunakan perintah ini.")
        elif update.callback_query:
            await update.callback_query.answer("❌ Hanya admin yang bisa menggunakan fitur ini.", show_alert=True)
        return False
    return True

async def topup_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display topup requests with filtering options"""
    try:
        # Admin verification
        if not await admin_check(update, context):
            return

        # Parse status filter with validation
        status_filter = 'pending'
        if context.args:
            status_filter = context.args[0].lower()
        
        valid_statuses = ['pending', 'approved', 'rejected', 'all']
        if status_filter not in valid_statuses:
            status_filter = 'pending'
            if update.message:
                await update.message.reply_text(
                    "⚠️ Status filter tidak valid. Menggunakan default: `pending`\n"
                    "Status yang valid: `pending`, `approved`, `rejected`, `all`",
                    parse_mode='Markdown'
                )

        # Fetch data from database
        requests = database.get_topup_requests(status_filter)

        if not requests:
            if update.message:
                await update.message.reply_text(
                    f"📭 Tidak ada permintaan topup dengan status: `{status_filter}`",
                    parse_mode='Markdown'
                )
            return

        # Build message and keyboard
        message_parts = []
        keyboard = []
        
        # Header
        message_parts.extend([
            "💳 **DAFTAR PERMINTAAN TOPUP**",
            "",
            f"📊 **Status Filter:** `{status_filter}`",
            f"📈 **Total:** {len(requests)} permintaan",
            ""
        ])

        # Request details
        for req in requests:
            try:
                # Safely unpack with validation
                if len(req) < 11:
                    continue
                    
                (req_id, user_id, base_amount, unique_amount, unique_digits, 
                 proof_image, status, created_at, updated_at, username, full_name) = req
                
                # Format user display name
                user_display = full_name or username or f"User {user_id}"
                user_display = user_display.replace('*', '').replace('_', '').replace('`', '')  # Sanitize for Markdown
                
                # Status emoji
                status_emojis = {
                    'pending': '⏳',
                    'approved': '✅', 
                    'rejected': '❌'
                }
                status_emoji = status_emojis.get(status, '📄')
                
                # Format amounts with thousand separators
                try:
                    base_amount_str = f"Rp {base_amount:,}"
                    unique_amount_str = f"Rp {unique_amount:,}"
                except:
                    base_amount_str = f"Rp {base_amount}"
                    unique_amount_str = f"Rp {unique_amount}"
                
                # Format unique digits to 3 digits
                unique_digits_str = f"{unique_digits:03d}"
                
                # Format timestamp
                if isinstance(created_at, str):
                    time_str = created_at
                else:
                    time_str = created_at.strftime("%d-%m-%Y %H:%M") if hasattr(created_at, 'strftime') else str(created_at)

                # Build request info
                message_parts.extend([
                    f"{status_emoji} **ID:** `{req_id}`",
                    f"👤 **User:** {user_display}",
                    f"💰 **Nominal:** {base_amount_str}",
                    f"🔢 **Kode Unik:** {unique_digits_str}",
                    f"💵 **Total Transfer:** {unique_amount_str}",
                    f"🕒 **Waktu:** {time_str}",
                    f"📊 **Status:** {status}",
                    ""
                ])

                # Add appropriate buttons based on status
                if status == 'pending':
                    keyboard.append([
                        InlineKeyboardButton(f"✅ Approve {req_id}", callback_data=f"approve_topup:{req_id}"),
                        InlineKeyboardButton(f"❌ Reject {req_id}", callback_data=f"reject_topup:{req_id}")
                    ])
                else:
                    keyboard.append([
                        InlineKeyboardButton(f"📋 Detail {req_id}", callback_data=f"view_topup:{req_id}"),
                        InlineKeyboardButton(f"🔄 Reset {req_id}", callback_data=f"reset_topup:{req_id}")
                    ])

            except (ValueError, TypeError, IndexError) as e:
                logger.error(f"Error processing request data: {e}, Data: {req}")
                continue

        # Add filter buttons
        filter_buttons = []
        for status in ['pending', 'approved', 'rejected', 'all']:
            emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌',
                'all': '📋'
            }.get(status, '📄')
            
            filter_buttons.append(
                InlineKeyboardButton(f"{emoji} {status.title()}", 
                                   callback_data=f"topup_filter:{status}")
            )
        
        # Add filter buttons in two rows for better layout
        keyboard.append(filter_buttons[:2])  # First row: pending, approved
        keyboard.append(filter_buttons[2:])  # Second row: rejected, all

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Join message parts and send
        message_text = "\n".join(message_parts)
        
        # Truncate message if too long (Telegram limit is 4096 characters)
        if len(message_text) > 4096:
            message_text = message_text[:4000] + "\n\n⚠️ **Pesan terlalu panjang, beberapa data mungkin tidak ditampilkan**"

        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text, 
                reply_markup=reply_markup, 
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                message_text, 
                reply_markup=reply_markup, 
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"Error in topup_list: {e}")
        error_msg = "❌ Terjadi kesalahan saat menampilkan daftar topup. Silakan coba lagi."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def approve_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approve topup callback"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Admin verification
        if not await admin_check(update, context):
            return

        request_id = int(query.data.split(":")[1])
        
        if database.approve_topup(request_id):
            # Update the message to show approved status
            await query.edit_message_text(
                f"✅ Topup request `#{request_id}` berhasil diapprove!",
                parse_mode='Markdown'
            )
            
            # Optionally send notification to user
            # You can implement this if you have user chat_id stored
        else:
            await query.edit_message_text(
                f"❌ Gagal approve topup request `#{request_id}`",
                parse_mode='Markdown'
            )
    except ValueError:
        await query.edit_message_text("❌ Format request ID tidak valid.")
    except Exception as e:
        logger.error(f"Error in approve_topup_callback: {e}")
        await query.edit_message_text("❌ Terjadi kesalahan saat approve topup.")

async def reject_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reject topup callback"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Admin verification
        if not await admin_check(update, context):
            return

        request_id = int(query.data.split(":")[1])
        
        if database.reject_topup(request_id, "Ditolak oleh admin melalui bot"):
            await query.edit_message_text(
                f"❌ Topup request `#{request_id}` telah ditolak!",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ Gagal menolak topup request `#{request_id}`",
                parse_mode='Markdown'
            )
    except ValueError:
        await query.edit_message_text("❌ Format request ID tidak valid.")
    except Exception as e:
        logger.error(f"Error in reject_topup_callback: {e}")
        await query.edit_message_text("❌ Terjadi kesalahan saat menolak topup.")

async def view_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle view topup details callback"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Admin verification
        if not await admin_check(update, context):
            return

        request_id = int(query.data.split(":")[1])
        request = database.get_topup_request(request_id)
        
        if not request:
            await query.edit_message_text("❌ Data topup tidak ditemukan.")
            return

        # Format detailed message
        message = f"""
🔍 **DETAIL TOPUP REQUEST**

📋 **ID:** `{request['id']}`
👤 **User ID:** `{request['user_id']}`
👥 **Username:** {request['username'] or 'Tidak ada'}
📛 **Nama Lengkap:** {request['full_name'] or 'Tidak ada'}

💰 **Nominal Base:** Rp {request['base_amount']:,}
🔢 **Kode Unik:** {request['unique_digits']:03d}
💵 **Total Transfer:** Rp {request['unique_amount']:,}

📊 **Status:** {request['status']}
📅 **Dibuat:** {request['created_at']}
🔄 **Diupdate:** {request['updated_at']}

📎 **Bukti Transfer:** {request['proof_image']}
📝 **Catatan Admin:** {request.get('admin_notes', 'Tidak ada')}
        """.strip()

        keyboard = [
            [InlineKeyboardButton("↩️ Kembali ke Daftar", callback_data="topup_filter:all")],
            [InlineKeyboardButton("🔄 Reset Status", callback_data=f"reset_topup:{request_id}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        
    except ValueError:
        await query.edit_message_text("❌ Format request ID tidak valid.")
    except Exception as e:
        logger.error(f"Error in view_topup_callback: {e}")
        await query.edit_message_text("❌ Terjadi kesalahan saat menampilkan detail topup.")

async def reset_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reset topup status callback"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Admin verification
        if not await admin_check(update, context):
            return

        request_id = int(query.data.split(":")[1])
        
        if database.update_topup_status(request_id, 'pending', 'Status direset oleh admin'):
            await query.edit_message_text(
                f"🔄 Topup request `#{request_id}` berhasil direset ke status pending!",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"❌ Gagal reset topup request `#{request_id}`",
                parse_mode='Markdown'
            )
    except ValueError:
        await query.edit_message_text("❌ Format request ID tidak valid.")
    except Exception as e:
        logger.error(f"Error in reset_topup_callback: {e}")
        await query.edit_message_text("❌ Terjadi kesalahan saat reset topup.")

async def topup_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle topup filter callback"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Admin verification
        if not await admin_check(update, context):
            return

        status_filter = query.data.split(":")[1]
        
        # Create a mock context with args for the filter
        class MockContext:
            def __init__(self, status):
                self.args = [status]
        
        mock_context = MockContext(status_filter)
        
        # Create a mock update with callback_query
        await topup_list(update, mock_context)
        
    except Exception as e:
        logger.error(f"Error in topup_filter_callback: {e}")
        await query.edit_message_text("❌ Terjadi kesalahan saat filter topup.")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display admin statistics"""
    try:
        # Admin verification
        if not await admin_check(update, context):
            return

        stats = database.get_topup_statistics()
        
        message = f"""
📊 **STATISTIK ADMIN**

📈 **Total Permintaan:**
⏳ Pending: {stats.get('pending_count', 0)}
✅ Approved: {stats.get('approved_count', 0)}
❌ Rejected: {stats.get('rejected_count', 0)}

💰 **Total Nominal:**
⏳ Pending: Rp {stats.get('pending_amount', 0):,}
✅ Approved: Rp {stats.get('approved_amount', 0):,}
❌ Rejected: Rp {stats.get('rejected_amount', 0):,}

📅 **Hari Ini:**
📥 Permintaan: {stats.get('today_count', 0)}
💰 Nominal: Rp {stats.get('today_amount', 0):,}

👥 **Total User:** {database.get_total_users_count()}
        """.strip()

        keyboard = [
            [InlineKeyboardButton("📋 Lihat Topup", callback_data="topup_filter:all")],
            [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_stats_refresh")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in admin_stats: {e}")
        error_msg = "❌ Terjadi kesalahan saat menampilkan statistik."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)

async def admin_stats_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh admin statistics"""
    await admin_stats(update, context)

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users"""
    try:
        # Admin verification
        if not await admin_check(update, context):
            return

        if not context.args:
            await update.message.reply_text(
                "❌ Format: /broadcast <pesan>\n"
                "Contoh: /broadcast Maintenance akan dilakukan pukul 23.00 WIB"
            )
            return

        message = " ".join(context.args)
        users = database.get_all_users()
        
        if not users:
            await update.message.reply_text("❌ Tidak ada user yang ditemukan.")
            return

        success_count = 0
        fail_count = 0
        
        # Send initial status
        status_msg = await update.message.reply_text(f"📤 Mengirim broadcast ke {len(users)} users...")
        
        # Here you would implement the actual broadcast logic
        # This is a placeholder - you need to implement get_all_users and send_message_to_user
        for user in users:
            try:
                # Implement your message sending logic here
                # await context.bot.send_message(chat_id=user['user_id'], text=message)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send to user {user['user_id']}: {e}")
                fail_count += 1
        
        await status_msg.edit_text(
            f"📊 **BROADCAST REPORT**\n\n"
            f"✅ Berhasil: {success_count}\n"
            f"❌ Gagal: {fail_count}\n"
            f"📝 Pesan: {message}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in broadcast_message: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan saat broadcast.")

# Add these helper functions to your database.py if needed
def get_total_users_count():
    """Get total users count - placeholder function"""
    # Implement this in your database.py
    return 0

def get_all_users():
    """Get all users - placeholder function"""
    # Implement this in your database.py
    return []

# Callback query handler
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback query handler for admin features"""
    query = update.callback_query
    callback_data = query.data
    
    try:
        if callback_data.startswith('approve_topup:'):
            await approve_topup_callback(update, context)
        elif callback_data.startswith('reject_topup:'):
            await reject_topup_callback(update, context)
        elif callback_data.startswith('view_topup:'):
            await view_topup_callback(update, context)
        elif callback_data.startswith('reset_topup:'):
            await reset_topup_callback(update, context)
        elif callback_data.startswith('topup_filter:'):
            await topup_filter_callback(update, context)
        elif callback_data == 'admin_stats_refresh':
            await admin_stats_refresh(update, context)
        else:
            await query.answer("❌ Perintah tidak dikenali.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in handle_admin_callback: {e}")
        await query.answer("❌ Terjadi kesalahan.", show_alert=True)

# Command handlers
async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin help"""
    try:
        if not await admin_check(update, context):
            return

        help_text = """
🛠 **ADMIN COMMANDS**

📋 **Topup Management:**
`/topup_list` - Lihat daftar permintaan topup
`/topup_list pending` - Filter by status
`/topup_list approved` - Filter by status
`/topup_list rejected` - Filter by status
`/topup_list all` - Semua status

📊 **Statistics:**
`/stats` - Lihat statistik

📢 **Broadcast:**
`/broadcast <pesan>` - Kirim pesan ke semua user

🆘 **Help:**
`/admin_help` - Tampilkan pesan bantuan ini
        """.strip()

        await update.message.reply_text(help_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in admin_help: {e}")
        await update.message.reply_text(help_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in admin_help: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan saat menampilkan help.")

# Register handlers function
def setup_admin_handlers(application):
    """Setup all admin handlers"""
    # Command handlers
    application.add_handler(CommandHandler("topup_list", topup_list))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("admin_help", admin_help))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^(approve_topup:|reject_topup:|view_topup:|reset_topup:|topup_filter:|admin_stats_refresh)"))

# Export the setup function
__all__ = ['setup_admin_handlers']
