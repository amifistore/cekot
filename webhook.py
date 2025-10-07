import config
from flask import Flask, request, jsonify
import sqlite3
import re
from datetime import datetime
import database

DB_PATH = "bot_topup.db"

app = Flask(__name__)

def log_error(msg):
    with open("webhook_raw.log", "a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    raw_input = request.get_data(as_text=True)
    log_error(raw_input)
    message = None

    if raw_input:
        try:
            json_data = request.get_json(force=True, silent=True)
            if json_data and "message" in json_data and isinstance(json_data["message"], str):
                message = json_data["message"]
        except Exception:
            pass
    if not message:
        message = request.args.get("message") or request.form.get("message")
    if not message or message.strip() == "":
        log_error("[WEBHOOK] message kosong")
        return jsonify({"ok": False, "error": "message kosong"}), 400

    pattern = r'RC=(?P<reffid>[a-z0-9_.-]+)\s+TrxID=(?P<trxid>\d+)\s+(?P<produk>[A-Z0-9]+)\.(?P<tujuan>\d+)\s+(?P<status_text>[A-Za-z]+)[, ]*(?P<keterangan>.+?)Saldo[\s\S]*?result=(?P<status_code>\d+)'
    m = re.search(pattern, message, re.I)
    if not m:
        log_error(f'[WEBHOOK] format tidak dikenali -> {message}')
        return jsonify({"ok": False, "error": "format tidak dikenali"}), 400

    trxid       = m.group('trxid')
    reffid      = m.group('reffid')
    produk      = m.group('produk')
    tujuan      = m.group('tujuan')
    status_text = m.group('status_text')
    keterangan  = m.group('keterangan').strip() if m.group('keterangan') else ''
    status_code = int(m.group('status_code'))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, harga, status_api, refund FROM riwayat_pembelian WHERE reff_id=? LIMIT 1", (reffid,))
    row = c.fetchone()
    if not row:
        log_error(f"[WEBHOOK] reff_id {reffid} tidak ditemukan di database!")
        conn.close()
        return jsonify({"ok": False, "error": "reffid tidak ditemukan"}), 400

    _id, username, harga, status_api, refund = row

    if status_code == 0:  # SUKSES
        c.execute("UPDATE riwayat_pembelian SET status_api='SUKSES', keterangan=?, waktu=? WHERE reff_id=?", (keterangan, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), reffid))
        log_error(f"[WEBHOOK] Status transaksi SUKSES - {reffid}")
    elif status_code == 1:  # GAGAL/FAILED
        if not refund:
            c.execute("UPDATE users SET saldo = saldo + ? WHERE username = ?", (harga, username))
            refund_val = 1
        else:
            refund_val = refund
        c.execute("UPDATE riwayat_pembelian SET status_api='GAGAL', keterangan=?, waktu=?, refund=? WHERE reff_id=?", (keterangan, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), refund_val, reffid))
        log_error(f"[WEBHOOK] Status transaksi GAGAL/REFUND - {reffid}")
    else:
        api = status_text.upper()
        c.execute("UPDATE riwayat_pembelian SET status_api=?, keterangan=?, waktu=? WHERE reff_id=?", (api, keterangan, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), reffid))
        log_error(f"[WEBHOOK] Status transaksi {api} - {reffid}")

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "parsed": {
            "trxid": trxid,
            "reffid": reffid,
            "produk": produk,
            "tujuan": tujuan,
            "status_text": status_text,
            "status_code": status_code,
            "keterangan": keterangan,
        }
    })

if __name__ == "__main__":
    app.run(port=8080, debug=True)
