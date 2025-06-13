# config.py
from pyrogram.enums import ParseMode

# --- Core Bot Configuration ---
# The ParseMode to use for sending messages. HTML is good for bold, italics, blockquote.
PARSE_MODE = ParseMode.HTML

# --- Admin Configuration (loaded from .env via main.py, but referenced here for structure) ---
# ADMIN_IDS and OWNER_ID are loaded in main.py from .env
# LOG_CHANNEL_ID and FILE_STORAGE_CHANNEL_ID are loaded in main.py from .env

# --- Database Configuration ---
# MONGO_URI is loaded in main.py from .env
DB_NAME = "AnimeRealmDB" # The name of your MongoDB database

# --- Telegram API Limits and Defaults ---
# Maximum number of items per pagination page (e.g., anime list, episodes list)
PAGE_SIZE = 15
# Timeout for certain operations (e.g., waiting for admin input in manage_content)
# INPUT_TIMEOUT_SECONDS = 120 # Example timeout, might be needed in specific handlers

# --- User & Download Configuration ---
# Initial tokens given to a user upon /start
START_TOKENS = 5
# Number of tokens awarded per successful token link redemption
TOKENS_PER_REDEEM = 1 # Can be overridden by .env, but good default

# --- Token Link Configuration ---
# URL Shortener configuration - Load from .env for sensitive info, provide structure here
SHORTENER_API_URL = os.getenv("SHORTENER_SITE_URL") # e.g., "api.example.com"
SHORTENER_API_KEY = os.getenv("SHORTENER_API_KEY") # e.g., "YOUR_API_KEY"
SHORTENER_ENDPOINT = "https://{shortener_api_url}/api?api={api_key}&url={long_url}"

# Pattern for the redeem link URL - Use a placeholder for the token
REDEEM_LINK_PATTERN_TELEGRAM = "https://t.me/{bot_username}?start={token}"

# Expiry time for generated token links in hours
TOKEN_LINK_EXPIRY_HOURS = 1 # Can be overridden by .env, but good default
HOW_TO_EARN_TUTORIAL_LINK = None 

# --- Premium Configuration ---
# Dictionary defining premium plans: {plan_id: {details}}
PREMIUM_PLANS = {
    "basic_monthly": {
        "name": "🌟 Basic Premium (Monthly)",
        "price": 5, # Example price (currency not handled by bot directly)
        "duration_days": 30,
        "features": ["✅ Unlimited Downloads", "✅ Anime Request", "✅ Priority Support"],
        "description": "Enjoy unlimited downloads and other benefits!",
        "button_text": "Activate Monthly 💎",
        "payment_info": "Contact admin or use payment link: ..." # Placeholder
    },
    "pro_yearly": {
        "name": "✨ Pro Premium (Yearly)",
        "price": 50, # Example price
        "duration_days": 365,
        "features": ["✅ All Basic Features", "✅ Higher Priority Requests", "✅ Early Access to New Features (if any)"],
        "description": "Go Pro for a full year of uninterrupted anime downloads!",
        "button_text": "Go Pro Yearly 🔥",
        "payment_info": "Contact admin for Pro plan details: ..." # Placeholder
    }
    # Add more plans as needed
}
# Button text for requesting premium information if /premium command is just an info page
GET_PREMIUM_INFO_BUTTON = "Tell me more about Premium! ✨"


# --- Admin Content Management Configuration ---
# Placeholder image URL/Telegraph link if an anime has no poster
DEFAULT_POSTER_TELEGRAPH_LINK = "https://telegra.ph/file/example_default_image.jpg" # **Replace with a real link!**
# Time limit for admin responses during content addition flow (in seconds)
ADMIN_INPUT_TIMEOUT_SECONDS = 300 # 5 minutes to provide input

# --- Content Display Configuration ---
# Number of items to show in Latest/Popular lists
LATEST_COUNT = 15
POPULAR_COUNT = 10
LEADERBOARD_COUNT = 10

# Genres (Editable by admins or define a starting list)
INITIAL_GENRES = [
    "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror", "Mecha",
    "Music", "Mystery", "Psychological", "Romance", "Sci-Fi", "Slice of Life",
    "Sports", "Supernatural", "Thriller"
]
# Anime Statuses
ANIME_STATUSES = ["Ongoing", "Completed", "Movie", "OVA"]

# --- Welcome Message Configuration ---
# Telegraph link for the welcome image. **Replace with your image link!**
WELCOME_IMAGE_TELEGRAPH_LINK = "https://telegra.ph/file/your_welcome_image_here.jpg" # **Replace with a real link!**
# Button labels for the main menu - Referencing strings.py is better, but quick list here
MAIN_MENU_BUTTONS = {
    "search": "🔍 Search Anime",
    "browse": "📚 Browse All",
    "profile": "👤 My Profile",
    "tokens": "🪙 Earn Tokens",
    "premium": "🌟 Premium",
    "help": "❓ Help"
}

# --- File Sending Configuration ---
# Chunk size for sending large files (bytes) - Default 10MB chunk
# Consider adjusting based on server resources and Telegram limits
FILE_CHUNK_SIZE = 10 * 1024 * 1024

# --- Advanced/Thresholds ---
# Fuzzywuzzy confidence score threshold for search results (0-100)
FUZZYWUZZY_THRESHOLD = 70

# --- Callback Data Separator ---
# Separator used in callback data strings. Use something unlikely to appear in actual data.
CALLBACK_DATA_SEPARATOR = "|"

# --- Bot Owner Specifics ---
# Commands only accessible by the OWNER_ID
OWNER_COMMANDS = ["/delete_all_data"]

# --- Default Notification Settings ---
# What types of notifications users get by default
DEFAULT_NOTIFICATION_SETTINGS = {
    "new_episode": True,
    "new_version": True,
    "release_date_updated": False # Maybe notify about date changes too?
}
