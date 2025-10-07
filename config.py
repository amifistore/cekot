import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

config = load_config()

BOT_TOKEN = config.get("BOT_TOKEN", "")
API_KEY_PROVIDER = config.get("API_KEY_PROVIDER", "")
QRIS_STATIS = config.get("QRIS_STATIS", "")
ADMIN_TELEGRAM_IDS = set(str(i) for i in config.get("ADMIN_TELEGRAM_IDS", []))
