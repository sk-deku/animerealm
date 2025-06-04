import os
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

# Basic Bot Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")

# Database Configuration
MONGO_URI = os.environ.get("MONGO_URI")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "AnimeRealm")

# Bot Specifics
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Anime_Realm_Bot") # Fallback if not in .env
BOT_IMAGE_URL = os.environ.get("BOT_IMAGE_URL", "https://via.placeholder.com/640x360.png?text=AnimeFireTamil") # Default placeholder
SUPPORT_LINK = os.environ.get("SUPPORT_LINK", "https://t.me/telegram")
UPDATES_LINK = os.environ.get("UPDATES_LINK", "https://t.me/telegram")

# Shortener Configuration
SHORTENER_API_URL = os.environ.get("SHORTENER_API_URL")
SHORTENER_API_KEY = os.environ.get("SHORTENER_API_KEY")

# Logging Channel IDs (Store as integers)
def get_channel_id(env_var):
    val = os.environ.get(env_var)
    return int(val) if val and val.strip() else None # Ensure empty strings become None

REQUEST_LOG_CHANNEL_ID = get_channel_id("REQUEST_LOG_CHANNEL_ID")
FILE_LOG_CHANNEL_ID = get_channel_id("FILE_LOG_CHANNEL_ID")
BOT_LOG_CHANNEL_ID = get_channel_id("BOT_LOG_CHANNEL_ID")

# Admin Configuration
ADMIN_USER_IDS_STR = os.environ.get("ADMIN_USER_IDS", "1775977570")
ADMIN_USER_IDS = [int(admin_id.strip()) for admin_id in ADMIN_USER_IDS_STR.split(',') if admin_id.strip()]

# Owner Configuration
OWNER_ID_STR = os.environ.get("OWNER_ID")
OWNER_ID = int(OWNER_ID_STR) if OWNER_ID_STR and OWNER_ID_STR.isdigit() else None

if OWNER_ID is None:
    LOGGER.warning("OWNER_ID is not set in .env. Destructive commands like /delete_all will be disabled.")
    
# Token System
TOKENS_PER_BYPASS = int(os.environ.get("TOKENS_PER_BYPASS", 5))
TOKEN_EXPIRY_HOURS = int(os.environ.get("TOKEN_EXPIRY_HOURS", 1))
FREE_USER_DOWNLOAD_LIMIT_PER_DAY = int(os.environ.get("FREE_USER_DOWNLOAD_LIMIT_PER_DAY", 10)) # New

# Creator Info (for About message)
CREATOR_NAME = "𓊈ᴅᴇᴋᴜ𓊉"
CREATOR_USERNAME = "sk_deku_bot" # Without @

# Pagination
ITEMS_PER_PAGE = 10 # For lists of anime, episodes etc.

# Supported Genres (Example - admins will choose from these)
SUPPORTED_GENRES = [
    "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror",
    "Magic", "Mecha", "Music", "Mystery", "Psychological", "Romance",
    "Sci-Fi", "Slice of Life", "Sports", "Supernatural", "Thriller"
]
SUPPORTED_STATUS = ["Ongoing", "Completed", "Upcoming", "Cancelled"]
SUPPORTED_AUDIO_TYPES = ["E SUB", "TAMIL DUB", "E DUB + SUB"] # Sub, Dub, Raw etc.

# Ensure critical variables are set
critical_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "API_ID": API_ID,
    "API_HASH": API_HASH,
    "MONGO_URI": MONGO_URI,
    "SHORTENER_API_URL": SHORTENER_API_URL,
    "SHORTENER_API_KEY": SHORTENER_API_KEY,
    "ADMIN_USER_IDS": ADMIN_USER_IDS, # Make sure at least one admin is set
}

missing_vars = [name for name, var in critical_vars.items() if not var] # Check if empty or None
if missing_vars:
    logging.error(f"Missing critical environment variables or configuration: {', '.join(missing_vars)}")
    raise ValueError(f"Missing critical environment variables or configuration: {', '.join(missing_vars)}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)
