# main.py
import asyncio
import logging
import sys

from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode

from database.mongo_db import init_db
from config import MONGO_URI # Ensure MONGO_URI is imported or passed correctly

from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler("bot.log"), # Log to file
        logging.StreamHandler()         # Log to console
    ]
)

# Pyrogram often logs too much for lower levels, silence libraries
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)


# --- Configuration ---
# These should ideally come from config.py or .env
# For now, load directly from .env using os.getenv
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(','))) if os.getenv("ADMIN_IDS") else []
OWNER_ID = int(os.getenv("OWNER_ID")) if os.getenv("OWNER_ID") else None # Single owner ID

# Optional config
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID")) if os.getenv("LOG_CHANNEL_ID") else None
FILE_STORAGE_CHANNEL_ID = int(os.getenv("FILE_STORAGE_CHANNEL_ID")) if os.getenv("FILE_STORAGE_CHANNEL_ID") else None

# --- Bot Initialization ---
# Pass storage = :memory: if you don't want session files on disk
# Using the token bot API ensures it's a bot, not a user account
try:
    bot = Client(
        name="anime_realm_bot", # Session name
        api_id=os.getenv("API_ID"), # Get from .env
        api_hash=os.getenv("API_HASH"), # Get from .env
        bot_token=BOT_TOKEN,
        plugins=dict(root="handlers"), # Load handlers from the 'handlers' directory
        workdir="." # Pyrogram session files will be created here
    )
except (ApiIdInvalid, ApiIdPublishedFlood):
    logging.critical("Your API_ID/API_HASH are invalid or come from a public repository. Get valid API credentials from https://my.telegram.org.")
    sys.exit(1)
except AuthKeyUnregistered:
     logging.critical("Your Pyrogram session key is invalid or has expired.")
     sys.exit(1)

# --- Database Initialization ---
# This function now calls the init_db from the database module
async def init_database():
    logging.info("Initializing database connection...")
    # Here we would import and call database connection and setup functions

    if not MONGO_URI:
         logging.critical("MONGO_URI environment variable is not set! Cannot connect to database.")
         # We might raise an error here that sys.exit in main handles
         # For now, logging critical and continuing might be okay if other parts can run, but risky.
         # Better to halt startup if DB is essential.
         sys.exit(1) # Halt startup if database connection is critical

    try:
        await init_db(MONGO_URI) # Call the async function to connect and set up indices
    except Exception as e:
         logging.critical(f"Database initialization failed: {e}")
         sys.exit(1) # Halt startup if database initialization fails

# --- Event Loop and Bot Start ---
async def main():
    logging.info("Starting bot...")

    # Initialize database connection and structure
    await init_database()

    # Check essential config
    if not BOT_TOKEN:
        logging.critical("BOT_TOKEN environment variable not set!")
        sys.exit(1)
    if not MONGO_URI:
        logging.critical("MONGO_URI environment variable not set!")
        sys.exit(1)
    # It's good to also check API_ID and API_HASH in .env
    if not os.getenv("API_ID") or not os.getenv("API_HASH"):
         logging.critical("API_ID and API_HASH environment variables are required for Pyrogram!")
         sys.exit(1)
    # Log required channels for admin features if they aren't set
    if not LOG_CHANNEL_ID:
         logging.warning("LOG_CHANNEL_ID not set. Admin logs will only appear in console/file.")
    if not FILE_STORAGE_CHANNEL_ID:
        logging.critical("FILE_STORAGE_CHANNEL_ID not set. File handling will NOT work correctly.")
        sys.exit(1)

    logging.info("Connecting to Telegram servers...")
    await bot.start()
    logging.info("Bot has connected to Telegram!")

    # Basic health check start logging
    logging.info("Health check server is managed by Procfile on port 8080.")
    # The http.server started by Procfile release will handle this.
    # In a more complex setup, you might integrate a tiny web server here.


    # Keep the bot running until terminated
    logging.info("Bot is now running and listening for updates.")
    await asyncio.Future() # Keeps the event loop running indefinitely

if __name__ == "__main__":
    # asyncio.run() is generally preferred for modern async apps
    asyncio.run(main())
