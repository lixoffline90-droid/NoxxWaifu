import logging
import os

from pyrogram import Client
from telegram.ext import Application
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.FileHandler("log.txt"), logging.StreamHandler()],
    level=logging.INFO,
)

logging.getLogger("apscheduler").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrate_limiter").setLevel(logging.ERROR)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

from NoxxNetwork.config import Development as Config


# ────────────────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────────────────
api_id = Config.api_id
api_hash = Config.api_hash
TOKEN = Config.TOKEN
GROUP_ID = Config.GROUP_ID
CHARA_CHANNEL_ID = Config.CHARA_CHANNEL_ID
mongo_url = Config.mongo_url
PHOTO_URL = Config.PHOTO_URL
SUPPORT_CHAT = Config.SUPPORT_CHAT
UPDATE_CHAT = Config.UPDATE_CHAT
BOT_USERNAME = Config.BOT_USERNAME
sudo_users = Config.sudo_users
OWNER_ID = Config.OWNER_ID

# Main group ID (used by /ball, /spawn)
MAIN_CHAT_ID = int(os.getenv("MAIN_CHAT_ID", "-1004450386900"))

# Private support/harem group (force-join)
PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID", "-1004450386900"))
HAREM_SUPPORT_CHAT = os.getenv("HAREM_SUPPORT_CHAT", "https://t.me/+A3bmzLTMu5sxMWVh")


# ────────────────────────────────────────────────────────────
# PTB Application
# ────────────────────────────────────────────────────────────
application = Application.builder().token(TOKEN).build()


# ────────────────────────────────────────────────────────────
# Pyrogram client — rich UI only
#  • in_memory=True → no session file, always fresh auth
#  • no_updates=True → no dispatcher / no getUpdates
# ────────────────────────────────────────────────────────────
RICH_TOKEN = os.getenv("RICH_TOKEN") or TOKEN

try:
    Waifuu = Client(
        "NoxxNetwork",
        api_id=api_id,
        api_hash=api_hash,
        bot_token=RICH_TOKEN,
        no_updates=True,
        in_memory=True,
    )
except Exception as _e:
    LOGGER.warning(f"[__init__] Waifuu client init failed: {_e}")
    Waifuu = None


# ────────────────────────────────────────────────────────────
# MongoDB
# ────────────────────────────────────────────────────────────
lol = AsyncIOMotorClient(mongo_url)
db = lol['Character_catcher']

# Main collections
collection = db['anime_characters_lol']
user_totals_collection = db['user_totals_lmaoooo']
user_collection = db["user_collection_lmaoooo"]
group_user_totals_collection = db['group_user_totalsssssss']
top_global_groups_collection = db['top_global_groups']
pm_users = db['total_pm_users']

# Feature collections (auto-created on first use)
user_coins = db['user_coins']
harem_modes = db['harem_modes']
harem_styles = db['harem_styles']
join_requests = db['join_requests']
banned_users = db['banned_users']
banned_groups = db['banned_groups']
redeem_codes = db['redeem_codes']
rarity_spawn_config = db['rarity_spawn_config']
rarity_settings = db['rarity_settings']

# Marketplace collections
marketplace_listings = db['marketplace_listings']
marketplace_transactions = db['marketplace_transactions']
marketplace_locks = db['marketplace_locks']
marketplace_stats = db['marketplace_stats']


# ────────────────────────────────────────────────────────────
# Startup log
# ────────────────────────────────────────────────────────────
LOGGER.info("NoxxNetwork __init__ loaded")
LOGGER.info(f"  MAIN_CHAT_ID: {MAIN_CHAT_ID}")
LOGGER.info(f"  PRIVATE_GROUP_ID: {PRIVATE_GROUP_ID}")
LOGGER.info(f"  Waifuu (Pyrogram): {'OK' if Waifuu else 'DISABLED'}")
LOGGER.info(f"  RICH_TOKEN: {'custom' if os.getenv('RICH_TOKEN') else 'using main TOKEN'}")
