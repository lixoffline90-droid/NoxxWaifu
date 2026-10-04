import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _get_int(key, default=None):
    """Safely fetch an int env var, returning `default` on missing/invalid."""
    value = os.getenv(key)
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_list(key):
    """Return a clean list from a comma-separated env var (never None)."""
    value = os.getenv(key) or ""
    return [item.strip() for item in value.split(",") if item.strip()]


class Config(object):
    LOGGER = True

    OWNER_ID = _get_int("OWNER_ID")
    sudo_users = _get_list("SUDO_USERS")
    GROUP_ID = _get_int("GROUP_ID")
    TOKEN = os.getenv("TOKEN")
    mongo_url = os.getenv("MONGO_URL")
    PHOTO_URL = _get_list("PHOTO_URL")
    SUPPORT_CHAT = os.getenv("SUPPORT_CHAT")
    UPDATE_CHAT = os.getenv("UPDATE_CHAT")
    BOT_USERNAME = os.getenv("BOT_USERNAME")
    CHARA_CHANNEL_ID = _get_int("CHARA_CHANNEL_ID")
    api_id = _get_int("API_ID")
    api_hash = os.getenv("API_HASH")


class Production(Config):
    LOGGER = True


class Development(Config):
    LOGGER = True