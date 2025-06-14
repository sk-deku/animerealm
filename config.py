# config.py
import os
from pyrogram.enums import ParseMode
from datetime import datetime # Needed for some default field values


DEBUG_MODE = "True"

# Define a simple version for logging
__version__ = "1.0.0"

# --- Core Bot Configuration ---
# The ParseMode to use for sending messages. HTML is good for bold, italics, blockquote.
PARSE_MODE = ParseMode.HTML

# --- Admin Configuration (Loaded in main.py from .env, referenced here) ---
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1775977570").split(','))) if os.getenv("ADMIN_IDS") else [] # Loaded in main
OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None # Loaded in main
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID")) if os.getenv("LOG_CHANNEL_ID") else None # Loaded in main
FILE_STORAGE_CHANNEL_ID = int(os.getenv("FILE_STORAGE_CHANNEL_ID")) if os.getenv("FILE_STORAGE_CHANNEL_ID") else None # Loaded in main

# Commands only accessible by the OWNER_ID
OWNER_COMMANDS = ["/delete_all_data"]


# --- Database Configuration ---
# MONGO_URI is loaded in main.py from .env
DB_NAME = "AnimeRealmDB" # The name of your MongoDB database
STATE_COLLECTION_NAME = "user_states" # Collection name for state management

# --- General Limits and Thresholds ---
# Maximum number of items per pagination page (e.g., anime list, episodes list)
PAGE_SIZE = int(os.getenv("PAGE_SIZE", 15)) # Load from env if available
# Time limit for certain *admin input* operations (in seconds)
ADMIN_INPUT_TIMEOUT_SECONDS = 300 # This requires specific handler/state timeout logic, define if implementing.


# --- User & Download Configuration ---
# Initial tokens given to a user upon /start
START_TOKENS = 5
# Number of tokens awarded per successful token link redemption
TOKENS_PER_REDEEM = int(os.getenv("TOKENS_PER_REDEEM", 5))


# --- Token Link Configuration ---
# URL Shortener configuration - Load from .env (Sensitive info)
# You MUST adapt the `shorten_url` function in `handlers/tokens_handler.py` to your chosen service
SHORTENER_API_URL = os.getenv("SHORTENER_SITE_URL")
SHORTENER_API_KEY = os.getenv("SHORTENER_API_KEY")
# API Endpoint template for the shortener (needs to be configured for YOUR API)
SHORTENER_ENDPOINT = os.getenv("SHORTENER_ENDPOINT")
# Pattern for the redeem link URL that the shortener *redirects to*
REDEEM_LINK_PATTERN_TELEGRAM = "https://t.me/{bot_username}?start={token}"
# Expiry time for generated token links in hours
TOKEN_LINK_EXPIRY_HOURS = int(os.getenv("TOKEN_LINK_EXPIRY_HOURS", 1))

# Optional: External link for "How to Earn Tokens" tutorial (Telegraph, YouTube, etc.)
HOW_TO_EARN_TUTORIAL_LINK = os.getenv("HOW_TO_EARN_TUTORIAL_LINK")


# --- Premium Configuration ---
# Dictionary defining premium plans: {plan_id: {details}}
PREMIUM_PLANS = {
    "basic_monthly": {
        "name": "Basic Premium (Monthly)",
        "price": "5 USD", # Display string for price, actual payment is external
        "duration_days": 30,
        "features": ["✅ Unlimited Downloads", "✅ Anime Request", "✅ Priority Support", "❌ Ad-Free"],
        "description": "Enjoy unlimited downloads and other benefits!",
        "button_text": "Activate Monthly 💎",
        "payment_info": "Contact admin or use payment link: ..." # Placeholder instructions/link
    },
    "pro_yearly": {
        "name": "Pro Premium (Yearly)",
        "price": "50 USD", # Display string for price
        "duration_days": 365,
        "features": ["✅ All Basic Features", "✅ Higher Priority Requests", "✨ Early Access to New Features", "🎉 Ad-Free"],
        "description": "Go Pro for a full year of uninterrupted anime downloads!",
        "button_text": "Go Pro Yearly 🔥",
        "payment_info": "Contact admin for Pro plan details: ..." # Placeholder instructions/link
    }
    # Add more plans as needed
}
# Button text for requesting premium information if /premium command is just an info page
# This is now just text content handled within strings.py
# GET_PREMIUM_INFO_BUTTON = "Tell me more about Premium! ✨"


# --- Request System Configuration ---
# Token cost for a FREE user to make an anime request (integer)
# PREMIUM users can request for free (cost = 0, handled by logic)
REQUEST_TOKEN_COST = int(os.getenv("REQUEST_TOKEN_COST", 5))

# --- Admin Content Management Configuration ---
# Placeholder image URL/Telegraph link if an anime has no poster (should be file_id now after upload)
# Store as Telegram file_id obtained after admin uploads. A default *fallback* link might be okay initially.
DEFAULT_POSTER_FILE_ID = None # Maybe set this in admin settings later? Or store a default photo via bot?
# Use a generic default image placeholder in strings/helpers
# DEFAULT_POSTER_TELEGRAPH_LINK = "https://telegra.ph/file/example_default_image.jpg"


# Preset options for selecting file metadata via buttons
QUALITY_PRESETS = [
    "1080p", "720p", "480p", "360p", "240p", "144p", "Best Available", "Unknown"
]

AUDIO_LANGUAGES_PRESETS = [
    "Japanese", "English", "Dual Audio (JP/EN)", "German", "Spanish", "French",
    "Italian", "Portuguese (Brazil)", "Hindi", "Korean", "Chinese", "Original", "None"
]

SUBTITLE_LANGUAGES_PRESETS = [
    "English", "Spanish", "French", "German", "Italian", "Portuguese (Brazil)", "Hindi",
    "Korean", "Chinese", "Arabic", "Vietnamese", "Bahasa Indonesia", "Thai", "Turkish",
    "Hebrew", "Greek", "None"
]

# Maximum number of buttons per row for these presets
MAX_BUTTONS_PER_ROW = int(os.getenv("MAX_BUTTONS_PER_ROW", 4))


# Initial list of genres (Editable by admins or define a starting list)
INITIAL_GENRES = [
    "🔫 Action", "🧭 Adventure", "😂 Comedy", "🎭 Drama", "🧚 Fantasy", "👻 Horror", "🤖 Mecha",
    "🎶 Music", "🕵️ Mystery", "🧠 Psychological", "💘 Romance", "🚀 Sci-Fi", "🍰 Slice of Life",
    "⚽ Sports", "✨ Supernatural", "🔪 Thriller", "🎓 School", "🏯 Historical", "🌌 Space",
    "👨‍👩‍👧 Family", "🎨 Art", "🧛 Vampire", "🗡️ Samurai", "💣 Military", "🌈 Isekai", 
    "😹 Parody", "📖 Josei", "👦 Shounen", "👧 Shoujo", "🧓 Seinen", "👶 Kids", "🏍️ Racing", 
    "🍳 Gourmet", "🔬 Sci-Fi Mystery", "📱 Cyberpunk"
]

ANIME_STATUSES = [
    "🌀 Ongoing", 
    "✅ Completed", 
    "🎬 Movie", 
    "📀 OVA", 
    "📺 TV Special", 
    "🎞️ ONA ", 
    "🔄 Upcoming", 
    "🗓️ Not Yet Aired", 
    "❌ Cancelled", 
    "🔁 Remake"
]



# --- Content Display Configuration (Discovery Lists) ---
# Number of items to show in Latest/Popular/Leaderboard lists
LATEST_COUNT = int(os.getenv("LATEST_COUNT", 15))
POPULAR_COUNT = int(os.getenv("POPULAR_COUNT", 10))
LEADERBOARD_COUNT = int(os.getenv("LEADERBOARD_COUNT", 10))


# --- Welcome Message Configuration ---
# Telegram file_id of the welcome image after uploading via bot
# This should be set by an admin command to upload a welcome image, then save the file_id here or in DB
WELCOME_IMAGE_FILE_ID = None # Default: No image. Admin needs to set this.
# A telegraph link fallback might be useful for initial setup if file_id is not set, but not ideal for persistence.
WELCOME_IMAGE_TELEGRAPH_LINK = os.getenv("WELCOME_IMAGE_TELEGRAPH_LINK") # Optional, loaded from .env if exists


# --- File Sending Configuration ---
# Chunk size for sending large files (bytes) - Default 10MB chunk
# Consider adjusting based on server resources and Telegram limits
FILE_CHUNK_SIZE = 10 * 1024 * 1024


# --- Search Configuration ---
# Fuzzywuzzy confidence score threshold for search results (0-100)
FUZZYWUZZY_THRESHOLD = int(os.getenv("FUZZYWUZZY_THRESHOLD", 70))


# --- Callback Data Separator ---
# Separator used in callback data strings. Use something unlikely to appear in actual data.
CALLBACK_DATA_SEPARATOR = "|"


# --- Default Notification Settings ---
# What types of notifications users get by default upon first /start
DEFAULT_NOTIFICATION_SETTINGS = {
    "new_episode": True, # Notify when a new episode is added for watched anime
    "new_version": True, # Notify when a new quality/language version is added for watched episode/anime
    "release_date_updated": False # Notify if only the release date is changed
}

# --- Owner/Admin Specific Text/Buttons (Could also be in strings.py) ---
# Specific message or acknowledgement for owner commands if needed.
#DELETE_ALL_DATA_CONFIRM_TEXT = "YES I AM SURE DELETE EVERYTHING" # Matches string in strings.py
