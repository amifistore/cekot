import database
import sqlite3
from telegram import Update
from telegram.ext import ContextTypes

async def riwayat_trx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = database.get_or_create_user(str(user.id), user.username, user.full_name)
    conn = sqlite3.connect(database.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    username = row[0] if row else None
    if not username:
        await update.message.reply_text("User tidak ditemukan.")
        return

    c.execute("SELECT id, waktu, kode_produk, tujuan, harga, saldo_awal, status_api, keterangan FROM riwayat_pembelian WHERE username=? ORDER BY waktu DESC LIMIT 20", (username,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Belum ada transaksi.")
        return
    
    msg = "Riwayat Transaksi Terbaru:\n"
    for row in rows:
        trxid, waktu, kode, tujuan, harga, saldo_awal, status_api, ket = row
        status = status_api.upper()
        if status in ('SUKSES', 'SUCCESS'):
            statetxt = '✅ SUKSES'
        elif status in ('GAGAL', 'FAILED'):
            statetxt = '❌ GAGAL'
        else:
            statetxt = f'⏳ {status.capitalize()}'
        msg += (
            f"\nID: {trxid}\n"
            f"Waktu: {waktu}\n"
            f"Kode: {kode}\n"
            f"Tujuan: {tujuan}\n"
            f"Harga: Rp {harga:,}\n"
            f"Saldo Awal: Rp {saldo_awal:,}\n"
            f"Status: {statetxt}\n"
            f"Keterangan: {ket}\n"
            "--------------------"
        )
    await update.message.reply_text(msg)
