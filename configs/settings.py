import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# --- Core Bot Settings ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.error("CRITICAL: BOT_TOKEN not found in environment variables!")
    # For a real deployment, you might raise an error or exit
    # For now, we'll let it proceed so other configs can be seen, but the bot won't start.

ADMIN_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "").split(',') if admin_id]
if not ADMIN_IDS:
    logging.warning("WARNING: ADMIN_IDS not found or empty in environment variables. No admin users will be configured.")

BOT_USERNAME = os.getenv("BOT_USERNAME") # e.g., "MyAnimeRealmBot" - used for generating t.me links
if not BOT_USERNAME:
    logging.warning("WARNING: BOT_USERNAME not found. Referral links might not work correctly.")


# --- Channel IDs ---
REQUEST_CHANNEL_ID = os.getenv("REQUEST_CHANNEL_ID")
if REQUEST_CHANNEL_ID:
    try:
        REQUEST_CHANNEL_ID = int(REQUEST_CHANNEL_ID)
    except ValueError:
        logging.error("CRITICAL: REQUEST_CHANNEL_ID is not a valid integer!")
        REQUEST_CHANNEL_ID = None
else:
    logging.warning("WARNING: REQUEST_CHANNEL_ID not set. Anime request forwarding will not work.")

USER_LOGS_CHANNEL_ID = os.getenv("USER_LOGS_CHANNEL_ID")
if USER_LOGS_CHANNEL_ID:
    try:
        USER_LOGS_CHANNEL_ID = int(USER_LOGS_CHANNEL_ID)
    except ValueError:
        logging.error("CRITICAL: USER_LOGS_CHANNEL_ID is not a valid integer!")
        USER_LOGS_CHANNEL_ID = None
else:
    logging.warning("WARNING: USER_LOGS_CHANNEL_ID not set. User activity logging will not work.")

# --- Database Settings ---
DATABASE_URL = os.getenv("DATABASE_URL") # MongoDB Connection URI
if not DATABASE_URL:
    logging.error("CRITICAL: DATABASE_URL not found for MongoDB connection!")

DATABASE_NAME = os.getenv("DATABASE_NAME", "AnimeRealmBotDB")

# --- Content Configuration ---
AVAILABLE_GENRES = [
    "Action", "Adventure", "Avant Garde", "Boys Love", "Cars", "Comedy", "Drama",
    "Demons", "Ecchi", "Fantasy", "Game", "Girls Love", "Gourmet", "Harem",
    "Historical", "Horror", "Isekai", "Josei", "Kids", "Magic", "Martial Arts",
    "Mecha", "Military", "Music", "Mystery", "Parody", "Police", "Psychological",
    "Romance", "Reverse Harem", "Samurai", "School", "Sci-Fi", "Seinen", "Shoujo",
    "Shoujo Ai", "Shounen", "Shounen Ai", "Slice of Life", "Space", "Sports",
    "Super Power", "Supernatural", "Suspense", "Thriller", "Vampire", "Work Life"
]
AVAILABLE_STATUSES = ["Ongoing", "Completed", "Movie", "OVA", "Special", "Not Yet Aired"]
SUPPORTED_AUDIO_LANGUAGES = ["Japanese", "English", "Hindi", "Other"] # Customize as needed
SUPPORTED_SUB_LANGUAGES = ["English", "Spanish", "Portuguese", "French", "German", "Italian", "Russian", "Arabic", "Hindi", "None"]
SUPPORTED_RESOLUTIONS = ["360p", "480p", "720p", "1080p", "BD", "4K"] # BD often implies best available Blu-ray rip

PREMIUM_ONLY_RESOLUTIONS = ["1080p", "BD", "4K"] # Resolutions only premium users can download

# --- Token & Referral System ---
DAILY_TOKEN_EARN_LIMIT_PER_USER = int(os.getenv("DAILY_TOKEN_EARN_LIMIT_PER_USER", 100))
TOKEN_LINK_EXPIRY_HOURS = int(os.getenv("TOKEN_LINK_EXPIRY_HOURS", 24))
TOKENS_AWARDED_PER_REFERRAL = int(os.getenv("TOKENS_AWARDED_PER_REFERRAL", 10))
FREE_USER_REQUEST_TOKEN_COST = int(os.getenv("FREE_USER_REQUEST_TOKEN_COST", 5)) # Set to 0 if free requests cost no tokens
TOKENS_FOR_NEW_USER_VIA_REFERRAL = int(os.getenv("TOKENS_FOR_NEW_USER_VIA_REFERRAL", 5)) # Tokens given to the new user who joins via referral
TOKENS_FOR_NEW_USER_DIRECT_START = int(os.getenv("TOKENS_FOR_NEW_USER_DIRECT_START", 2)) # Tokens for new user starting bot directly

# --- Premium Membership (INR based) ---
# Format: "key": {"display_name": "...", "price_inr": ..., "duration_days": ..., "savings_text": "..."}
# The 'key' is not directly used for granting by duration, but can be for display or internal logic if needed.
PREMIUM_PLANS_INR = {
    "7_days": {"display_name": "✨ <b>Weekly Pass</b> ✨", "price_inr": 15 , "duration_days": 7, "savings_text": ""},
    "30_days": {"display_name": "🌟 <b>Monthly Pass</b> 🌟", "price_inr": 50, "duration_days": 30, "savings_text": "<i>(Save ₹10!)</i>"},
    "90_days": {"display_name": "💎 <b>Quarterly Pass</b> 💎", "price_inr": 120, "duration_days": 90, "savings_text": "<i>(Save ₹20%!)</i>"},
    # Add more plans if needed
}
CONTACT_ADMIN_USERNAME_FOR_PREMIUM = os.getenv("CONTACT_ADMIN_USERNAME_FOR_PREMIUM", "YourAdminContact") # e.g., "RealmAdminSupport" without @

# --- UI/UX & Miscellaneous ---
RESULTS_PER_PAGE = int(os.getenv("RESULTS_PER_PAGE", 5))
MAX_WATCHLIST_ITEMS_FREE = int(os.getenv("MAX_WATCHLIST_ITEMS_FREE", 10))
MAX_WATCHLIST_ITEMS_PREMIUM = int(os.getenv("MAX_WATCHLIST_ITEMS_PREMIUM", 100))
DEFAULT_PARSE_MODE = "HTML"
HOW_TO_EARN_TOKENS_TUTORIAL_LINK = os.getenv("HOW_TO_EARN_TOKENS_TUTORIAL_LINK", "https://telegra.ph/How-To-Earn-Tokens-AnimeRealmBot-01-01") # Example link
MAX_BUTTONS_PER_ROW = int(os.getenv("MAX_BUTTONS_PER_ROW", 3)) # For dynamic inline keyboards
ANIME_POSTER_PLACEHOLDER = os.getenv("ANIME_POSTER_PLACEHOLDER", "https://via.placeholder.com/200x300.png?text=No+Poster") # URL of a placeholder image

# --- Health Check Server ---
HEALTH_CHECK_PORT = int(os.getenv("PORT", 8080)) # Koyeb typically sets PORT env var for web services
HEALTH_CHECK_HOST = "0.0.0.0"

# --- Logging Configuration ---
LOG_LEVEL_ENV = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_ENV, logging.INFO)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=LOG_LEVEL,
    handlers=[
        logging.StreamHandler() # Output to console
        # You could add FileHandler here if needed
    ]
)
# Suppress noisy library logs if necessary
logging.getLogger("httpx").setLevel(logging.WARNING) # PTB uses httpx
logging.getLogger("telegram.ext").setLevel(logging.INFO) # Or higher if too verbose

# Ensure required variables for bot operation are present
if not BOT_TOKEN or not DATABASE_URL:
    logging.critical("FATAL: Essential environment variables (BOT_TOKEN, DATABASE_URL) are missing. Bot cannot start.")
    exit(1) # Exit if critical configs are missing

# Developer/Debug Mode
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"
if DEBUG_MODE:
    logging.info("DEBUG MODE IS ENABLED.")
