import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# --- Logging Configuration (Setup early to catch all messages) ---
LOG_LEVEL_ENV = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_ENV, logging.INFO)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=LOG_LEVEL,
    handlers=[
        logging.StreamHandler() # Output to console
    ]
)
# Suppress noisy library logs if necessary
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)

# --- Core Bot Settings ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "").split(',') if admin_id]
BOT_USERNAME = os.getenv("BOT_USERNAME") # e.g., "MyAnimeRealmBot" - used for t.me links
DEFAULT_PARSE_MODE = "HTML"
DEBUG_MODE = os.getenv("DEBUG_MODE", "True").lower() == "true"

# --- Health Check Server ---
HEALTH_CHECK_PORT = int(os.getenv("PORT", 8080)) # Koyeb typically sets PORT env var
HEALTH_CHECK_HOST = "0.0.0.0"

# --- Database Settings ---
DATABASE_URL = os.getenv("DATABASE_URL") # MongoDB Connection URI
DATABASE_NAME = os.getenv("DATABASE_NAME", "AnimeRealmBotDB")

# --- Channel IDs ---
REQUEST_CHANNEL_ID = os.getenv("REQUEST_CHANNEL_ID")
USER_LOGS_CHANNEL_ID = os.getenv("USER_LOGS_CHANNEL_ID")

# --- Link Shortener Configuration (Linkshortify Example) ---
SHORTENER_API_URL = "https://linkshortify.com/api" # Base API URL for your shortener
SHORTENER_API_KEY = os.getenv("SHORTENER_API_KEY") # Your specific API key for the shortener service
# Note: If your shortener requires a different API structure, you'll adjust how this is used in `token_system.py`

# --- Content Configuration ---
AVAILABLE_GENRES = [
    "Action ⚔️", "Adventure 🗺️", "Avant Garde 🎨", "Boys Love 👨‍❤️‍👨", "Cars 🚗",
    "Comedy 😂", "Drama 🎭", "Demons 👹", "Ecchi 👀", "Fantasy 🧙", "Game 🎮",
    "Girls Love 👩‍❤️‍👩", "Gourmet 🍜", "Harem 💕", "Historical 🏯", "Horror 🧟",
    "Isekai ➡️🌍", "Josei 👠", "Kids 🧸", "Magic ✨", "Martial Arts 🥋",
    "Mecha 🤖", "Military 🎖️", "Music 🎵", "Mystery ❓", "Parody 🤪", "Police 👮",
    "Psychological 🧠", "Romance ❤️", "Reverse Harem 💞", "Samurai 🗡️", "School 🎓",
    "Sci-Fi 🚀", "Seinen 👔", "Shoujo 🌸", "Shoujo Ai 🌸👩‍❤️‍👩", "Shounen 🔥",
    "Shounen Ai 🔥👨‍❤️‍👨", "Slice of Life 🍰", "Space 🌌", "Sports 🏆",
    "Super Power 💪", "Supernatural 👻", "Suspense 😨", "Thriller 🔪",
    "Vampire 🧛", "Work Life 💼"
]
AVAILABLE_STATUSES = [
    "Ongoing ▶️", "Completed ✅", "Movie 🎬", "OVA 📼", "Special ⭐", "Not Yet Aired ⏳"
]
SUPPORTED_AUDIO_LANGUAGES = ["Japanese 🇯🇵", "English 🇬🇧", "Hindi 🇮🇳", "Other 🌐"]
SUPPORTED_SUB_LANGUAGES = [
    "English 🇬🇧", "Spanish 🇪🇸", "Portuguese 🇵🇹", "French 🇫🇷", "German 🇩🇪",
    "Italian 🇮🇹", "Russian 🇷🇺", "Arabic 🇸🇦", "Hindi 🇮🇳", "None 😶"
]
SUPPORTED_RESOLUTIONS = ["360p", "480p", "720p", "1080p", "BD 💎", "4K ✨"]
PREMIUM_ONLY_RESOLUTIONS = ["1080p", "BD 💎", "4K ✨"]
ANIME_POSTER_PLACEHOLDER_URL = os.getenv("ANIME_POSTER_PLACEHOLDER_URL", "https://via.placeholder.com/200x300.png?text=🖼️+No+Poster")

# --- Token & Referral System ---
DAILY_TOKEN_EARN_LIMIT_PER_USER = int(os.getenv("DAILY_TOKEN_EARN_LIMIT_PER_USER", 15)) # Tokens per day
TOKEN_LINK_ACTIVE_HOURS = int(os.getenv("TOKEN_LINK_ACTIVE_HOURS", 1)) # How long referral link itself is clickable to initiate claim
# ^ (Not to be confused with SHORTENER_LINK_EXPIRY_MINUTES if shortener offers temporary links)
# TOKEN_LINK_CLAIM_WINDOW_HOURS = int(os.getenv("TOKEN_LINK_CLAIM_WINDOW_HOURS", 1)) # How long a *clicked* (but not yet `/start`ed) link from shortener is valid for `start` command. Usually, this is managed by single-use token from DB.
TOKENS_AWARDED_PER_REFERRAL = int(os.getenv("TOKENS_AWARDED_PER_REFERRAL", 5)) # To the referrer
TOKENS_FOR_NEW_USER_VIA_REFERRAL = int(os.getenv("TOKENS_FOR_NEW_USER_VIA_REFERRAL", 3)) # To the new user using referral
TOKENS_FOR_NEW_USER_DIRECT_START = int(os.getenv("TOKENS_FOR_NEW_USER_DIRECT_START", 2)) # To new user via /start directly
FREE_USER_REQUEST_TOKEN_COST = int(os.getenv("FREE_USER_REQUEST_TOKEN_COST", 3))
HOW_TO_EARN_TOKENS_TUTORIAL_LINK = os.getenv("HOW_TO_EARN_TOKENS_TUTORIAL_LINK", "https://telegra.ph/How-To-Earn-Tokens-AnimeRealmBot-01-01")

# --- Premium Membership (INR based) ---
# Duration_days is the key now for the /grant_premium command
PREMIUM_PLANS_INR = {
    7: {"display_name": "✨ <b>Weekly Sparkle</b> ✨", "price_inr": 15, "savings_text": ""},
    30: {"display_name": "🌟 <b>Monthly Glow</b> 🌟", "price_inr": 50, "savings_text": "<i>(Save ₹10!)</i>"},
    90: {"display_name": "💎 <b>Quarterly Radiance</b> 💎", "price_inr": 125, "savings_text": "<i>(Save ₹25!)</i>"},
    # Add more: duration_days: {display_name, price_inr, savings_text}
}
CONTACT_ADMIN_USERNAME_FOR_PREMIUM = os.getenv("CONTACT_ADMIN_USERNAME_FOR_PREMIUM", "YourAdminContact") # e.g., "RealmAdminSupport" without @

# --- UI/UX & Miscellaneous ---
RESULTS_PER_PAGE_GENERAL = int(os.getenv("RESULTS_PER_PAGE_GENERAL", 5)) # For search, browse, watchlist etc.
ANIME_LIST_BUTTONS_PER_ROW = int(os.getenv("ANIME_LIST_BUTTONS_PER_ROW", 1)) # Typically 1 for anime title buttons
SEASON_LIST_BUTTONS_PER_ROW = int(os.getenv("SEASON_LIST_BUTTONS_PER_ROW", 2)) # E.g., S1, S2, S3
EPISODE_LIST_BUTTONS_PER_ROW = int(os.getenv("EPISODE_LIST_BUTTONS_PER_ROW", 4)) # E.g., E1-E4 on one row
MAX_WATCHLIST_ITEMS_FREE = int(os.getenv("MAX_WATCHLIST_ITEMS_FREE", 3))
MAX_WATCHLIST_ITEMS_PREMIUM = int(os.getenv("MAX_WATCHLIST_ITEMS_PREMIUM", 15))
GENRE_BUTTONS_PER_ROW = int(os.getenv("GENRE_BUTTONS_PER_ROW", 3)) # For selecting genres in admin/browse
PAGINATION_BUTTONS_PER_ROW = 2 # For "Previous", "Next"


# --- Validation and Error Checks for Critical Configs ---
essential_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "ADMIN_IDS": ADMIN_IDS, # Will be empty list if not set, check len() later if strict
    "BOT_USERNAME": BOT_USERNAME,
    "DATABASE_URL": DATABASE_URL,
    "SHORTENER_API_KEY": SHORTENER_API_KEY, # Add shortener API key to essentials
}

missing_essentials = [key for key, value in essential_vars.items() if not value]

if missing_essentials:
    logging.critical(f"FATAL: Essential environment variables are missing: {', '.join(missing_essentials)}. Bot cannot start.")
    exit(1)

if not ADMIN_IDS: # Specific check for admin IDs
    logging.warning("WARNING: ADMIN_IDS not found or empty. No admin users will be configured initially.")


# --- Dynamic Type Casting for Channel IDs ---
def cast_channel_id(env_var_name, value):
    if value:
        try:
            return int(value)
        except ValueError:
            logging.error(f"CRITICAL: {env_var_name} ('{value}') is not a valid integer! Feature might be disabled.")
            return None
    logging.warning(f"WARNING: {env_var_name} not set. Corresponding feature may be disabled.")
    return None

REQUEST_CHANNEL_ID = cast_channel_id("REQUEST_CHANNEL_ID", REQUEST_CHANNEL_ID)
USER_LOGS_CHANNEL_ID = cast_channel_id("USER_LOGS_CHANNEL_ID", USER_LOGS_CHANNEL_ID)

if DEBUG_MODE:
    logging.info("🛠️ DEBUG MODE IS ENABLED. Detailed logs may appear.")
logging.info("✅ Configuration loaded successfully.")
