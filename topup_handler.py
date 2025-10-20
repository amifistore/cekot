import aiohttp
import logging

logger = logging.getLogger(__name__)

QRIS_API_URL = "https://qrisku.my.id/api"   # endpoint resmi
QRIS_STATIS = "00020101021126610014COM.GO-JEK.WWW01189360091434506469550210G4506469550303UMI51440014ID.CO.QRIS.WWW0215ID10243341364120303UMI5204569753033605802ID5923Amifi Store, Kmb, TLGSR6009BONDOWOSO61056827262070703A01630431E8"

async def generate_qris_payment(amount: int):
    """
    Fungsi untuk generate QRIS dinamis berbentuk base64.
    :param amount: nominal dalam satuan rupiah (int)
    :return: (qris_base64, None, error_message)
    """
    payload = {
        "amount": str(amount),
        "qris_statis": QRIS_STATIS
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(QRIS_API_URL, json=payload, headers=headers, timeout=15) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"QRIS API Error {response.status}: {error_text}")
                    return None, None, f"HTTP {response.status}: {error_text}"

                data = await response.json()
                if data.get("status") == "success":
                    return data.get("qris_base64"), None, None
                else:
                    msg = data.get("message", "Gagal generate QRIS")
                    logger.warning(f"QRIS API responded error: {msg}")
                    return None, None, msg

    except Exception as e:
        logger.error(f"Exception saat generate QRIS: {e}")
        return None, None, str(e)
      
