import os
import json
from dotenv import load_dotenv

# Load environment variables from the .env file at the root of the project
# If running in a different environment (like Docker), these will be picked up directly
load_dotenv()

# === Essential Configurations ===

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Error: BOT_TOKEN environment variable not set.")

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("Error: MONGO_URI environment variable not set.")

# Admin User IDs: convert comma-separated string to a list of integers
ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in os.getenv("ADMIN_IDS", "").split(',')
    if admin_id.strip() # Avoid adding empty strings from trailing commas
]
if not ADMIN_IDS:
    print("Warning: ADMIN_IDS environment variable not set or is empty. No admins configured.")

# === Optional Configurations with Default Values ===

# Token System Settings
TOKEN_REDEEM_AMOUNT = int(os.getenv("TOKEN_REDEEM_AMOUNT", "1"))
DAILY_TOKEN_EARN_LIMIT = int(os.getenv("DAILY_TOKEN_EARN_LIMIT", "5"))
TOKEN_EXPIRY_HOURS = int(os.getenv("TOKEN_EXPIRY_HOURS", "72")) # 72 hours = 3 days
TOKEN_EXPIRY_SECONDS = TOKEN_EXPIRY_HOURS * 3600

# User Interface Settings
WELCOME_IMAGE_URL = os.getenv("WELCOME_IMAGE_URL", "") # URL for the welcome message image

# URL Shortener Settings
SHORTENER_API_URL = os.getenv("SHORTENER_API_URL", "") # API endpoint URL for shortening service
SHORTENER_API_KEY = os.getenv("SHORTENER_API_KEY", "") # API key for shortening service
SHORTENER_SITE_URL = os.getenv("SHORTENER_SITE_URL", "") # Base URL for constructed shortened links

# Premium Plans Configuration
# Load premium plan names from env, then define more details here.
# This is a basic structure; you might want to define more comprehensive plan
# details directly as a dictionary within this file or load from a JSON file.
_premium_plan_names_str = os.getenv("PREMIUM_PLAN_NAMES", "Basic Premium")
PREMIUM_PLAN_NAMES = [plan.strip() for plan in _premium_plan_names_str.split(',') if plan.strip()]
PREMIUM_PLANS = {
    plan_name: {
        "name": plan_name,
        "price": f"Ask Admin about {plan_name}", # Placeholder: Customize price info
        "features": ["Unlimited Downloads", "Priority Support", "Early Access to New Features (placeholder)"], # Placeholder features
        # You can add more attributes like duration, trial period, etc.
    }
    for plan_name in PREMIUM_PLAN_NAMES
}
# Example usage: print(PREMIUM_PLANS["Basic Premium"]["features"])


# === Other Bot Settings ===

# Database Configuration
DATABASE_NAME = os.getenv("DATABASE_NAME", "AnimeRealmDB") # Default database name if not set

# Search Settings
FUZZY_SEARCH_CUTOFF = int(os.getenv("FUZZY_SEARCH_CUTOFF", "60"))
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "10"))

# Content Discovery Settings
LATEST_ADDITIONS_LIMIT = int(os.getenv("LATEST_ADDITIONS_LIMIT", "10"))
LEADERBOARD_LIMIT = int(os.getenv("LEADERBOARD_LIMIT", "10"))


# === Global Constants (Add more as needed) ===

# Max file size Telegram can handle for bots (approx 20MB or 50MB depending on API updates/limits, often set conservatively)
# Check official Telegram Bot API documentation for precise limits
MAX_TELEGRAM_FILESIZE = 50 * 1024 * 1024 # Example: 50MB (convert to bytes)

# Timeout for token links (re-using TOKEN_EXPIRY_SECONDS, but defining as a constant too for clarity)
TOKEN_LINK_TIMEOUT_SECONDS = TOKEN_EXPIRY_SECONDS


# --- Message Templates (Can also be in strings.py) ---
# Storing essential templates here for immediate access after config loads

# Basic HTML formatting example for Telegram messages
HTML_FORMATTING = """
Use <b>Bold Text</b> for **Bold Text**.
Use <i>Italic Text</i> for *Italic Text*.
Use <s>Strikethrough</s> for ~~Strikethrough~~.
Use <u>Underline</u> for __Underline__.
Use <span class="tg-spoiler"></span> for ||Spoiler Text||.
Use <code>Inline Code</code> for `Inline Code`.
Use <pre></pre> for pre-formatted code blocks.
Use <pre><code class="language-python">...</code></pre> for pre-formatted code with language.
Use <a href="URL">Link Text</a> for [Link Text](URL).
Use <blockquote>Block Quote</blockquote> for blockquotes.
""" # Add more HTML formatting options if needed

START_MESSAGE_TEMPLATE = """
👋 **Welcome to AnimeRealm,** `{user_mention}`! 🎉

Your ultimate companion for finding and downloading your favorite anime. Browse our extensive library, search for specific titles, manage your watchlist, and earn tokens to download files.

*Your Current Tokens: `{user_tokens}`* 💎
{premium_status_message}

Select an option from the buttons below or use commands like `/profile` or `/help`.

✨ Let's dive into the world of anime! ✨
"""

HELP_MESSAGE_TEXT = """
📖 **AnimeRealm Help Guide** 📖

Here are the commands you can use:

•   `/start` - Get the welcome message and main menu buttons.
•   `/profile` - View your token balance, premium status, and watchlist.
•   `/help` - Display this help guide.
•   `/gen_token` - Generate a unique link to earn download tokens.
•   `/request` - Request anime titles. (Premium users get priority or direct request options)

**Browsing & Searching:**
Use the inline buttons from the start message or `/start` to browse categories and initiate searches. Use fuzzy search by typing the anime name.

**Token System:**
Download one file per token. Earn tokens by sharing and using the special links generated by `/gen_token`. Token links expire after *{token_expiry_hours} hours* or one use. Max earnings are *{daily_token_limit} tokens per day*.

**Premium:**
{premium_details_summary}
Check out `/premium` for details and pricing.

If you need further assistance, please contact an admin: {admin_contact_info}.
"""

# Placeholder function to generate a summary of premium benefits for HELP message
def generate_premium_details_summary():
    summary = "⭐ Premium users enjoy unlimited downloads!"
    # You can expand this to list features from PREMIUM_PLANS
    if PREMIUM_PLANS:
        summary += "\nPlans:"
        for plan_name, details in PREMIUM_PLANS.items():
             summary += f"\n - {plan_name}: {', '.join(details.get('features', ['No specific features listed']))}"
             # Optionally add price if defined: f"({details.get('price', 'Price unknown')})"
    return summary


# Placeholder for Admin contact information (e.g., a link to an admin group or username)
ADMIN_CONTACT_INFO = "@YourAdminUsername" # Replace with actual contact info


# Example of how messages with placeholders will be used
# To use START_MESSAGE_TEMPLATE:
# message_text = START_MESSAGE_TEMPLATE.format(
#    user_mention=f'<a href="tg://user?id={user_id}">{first_name}</a>', # For HTML linking
#    user_tokens=user_data.get('tokens', 0),
#    premium_status_message="✨ You are a **Premium** User! ✨" if user_data.get('is_premium') else ""
# )
# Use parse_mode='HTML' when sending the message
