# main.py
import asyncio
import logging
import sys
import os
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode # Keep ParseMode import for Client init

from dotenv import load_dotenv

# Configure basic logging immediately
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout) # Always log to console
    ]
)
# Set specific log levels for noisy libraries early
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("motor").setLevel(logging.WARNING) # Add motor for async driver


main_logger = logging.getLogger(__name__) # Logger for this file

# Load environment variables from .env file as early as possible
load_dotenv()

# --- Configuration ---
# Load critical configuration from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
MONGO_URI = os.getenv("MONGO_URI")

# Validate essential environment variables immediately
if not BOT_TOKEN:
    main_logger.critical("BOT_TOKEN environment variable not set!")
    sys.exit(1)
if not API_ID or not API_HASH:
     main_logger.critical("API_ID and API_HASH environment variables are required for Pyrogram! Get them from https://my.telegram.org.")
     sys.exit(1)
if not MONGO_URI:
    main_logger.critical("MONGO_URI environment variable not set! Database connection is required.")
    sys.exit(1)


# Admin IDs (comma separated)
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if ADMIN_IDS_STR:
    try:
        ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()]
        if not ADMIN_IDS: raise ValueError("ADMIN_IDS is empty after parsing")
    except ValueError as e:
        main_logger.critical(f"Invalid format for ADMIN_IDS environment variable: {e}. Must be comma-separated integers.")
        sys.exit(1)
else:
     main_logger.warning("ADMIN_IDS environment variable is not set. No admin users defined.")


# Owner ID (single)
OWNER_ID_STR = os.getenv("OWNER_ID")
OWNER_ID = None
if OWNER_ID_STR:
    try:
        OWNER_ID = int(OWNER_ID_STR.strip())
    except ValueError as e:
        main_logger.critical(f"Invalid format for OWNER_ID environment variable: {e}. Must be a single integer.")
        sys.exit(1)
    if OWNER_ID not in ADMIN_IDS:
        main_logger.warning(f"OWNER_ID ({OWNER_ID}) is not included in ADMIN_IDS. OWNER_ID may not have full admin access depending on handler logic.")


# Telegram Channel IDs for logs and file storage (Bot must be admin)
# Handle potentially unset optional channel IDs gracefully, but check FILE_STORAGE_CHANNEL_ID
LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID")
LOG_CHANNEL_ID = None
if LOG_CHANNEL_ID_STR:
    try:
         LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR.strip())
         # Add File Handler with LOG_CHANNEL_ID after getting its value
         try:
              log_channel_handler = logging.FileHandler("bot.log")
              log_channel_handler.setFormatter(logging.Formatter("[%(asctime)s - %(levelname)s] - %(name)s - %(message)s", datefmt='%H:%M:%S'))
              logging.getLogger().addHandler(log_channel_handler) # Add handler to root logger
              main_logger.info(f"Logging to bot.log file.")
         except Exception as e:
              main_logger.error(f"Failed to configure file logging: {e}")
              # Continue without file logging
    except ValueError as e:
        main_logger.critical(f"Invalid format for LOG_CHANNEL_ID environment variable: {e}. Must be an integer.")
        sys.exit(1)


FILE_STORAGE_CHANNEL_ID_STR = os.getenv("FILE_STORAGE_CHANNEL_ID")
FILE_STORAGE_CHANNEL_ID = None
if FILE_STORAGE_CHANNEL_ID_STR:
    try:
         FILE_STORAGE_CHANNEL_ID = int(FILE_STORAGE_CHANNEL_ID_STR.strip())
         main_logger.info(f"FILE_STORAGE_CHANNEL_ID is set to {FILE_STORAGE_CHANNEL_ID}.")
    except ValueError as e:
        main_logger.critical(f"Invalid format for FILE_STORAGE_CHANNEL_ID environment variable: {e}. Must be an integer.")
        sys.exit(1)
else:
    main_logger.critical("FILE_STORAGE_CHANNEL_ID environment variable is NOT set. File handling features WILL NOT work correctly.")
    sys.exit(1)

# Other configuration variables are now imported in relevant files from config.py


# --- Pyrogram Client Initialization ---
main_logger.info("Initializing Pyrogram client...")
try:
    bot = Client(
        name="anime_realm_bot", # Session name
        api_id=int(API_ID), # Ensure API_ID is integer
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=dict(root="handlers"), # Load handlers from the 'handlers' directory
        workdir=".", # Pyrogram session files will be created here
        # Enable the message/callback handling from both direct message and callback queries implicitly via handlers
        # Configure ParseMode globally if possible, or apply in each handler
        parse_mode=ParseMode.HTML # Set HTML ParseMode globally
    )
    main_logger.info("Pyrogram client created.")

except (ApiIdInvalid, ApiIdPublishedFlood):
    main_logger.critical("Your API_ID/API_HASH are invalid or come from a public repository. Get valid API credentials from https://my.telegram.org.")
    sys.exit(1)
except AuthKeyUnregistered:
     main_logger.critical("Your Pyrogram session key is invalid or has expired. Delete the session file and try again.")
     sys.exit(1)
except Exception as e:
    main_logger.critical(f"An unexpected error occurred during Pyrogram client initialization: {e}", exc_info=True)
    sys.exit(1)


# --- Database Initialization ---
async def init_database():
    main_logger.info("Initializing database connection and structure...")
    from database.mongo_db import init_db # Import the initialization function

    try:
        # Pass MONGO_URI to the init_db function
        await init_db(MONGO_URI)
        main_logger.info("Database initialized successfully.")
    except Exception as e:
         main_logger.critical(f"Database initialization failed: {e}", exc_info=True)
         # Since the bot cannot function without the database, exit critically
         sys.exit(1)


# --- Bot Start ---
async def main():
    main_logger.info("Starting bot...")

    # Initialize database connection and structure before starting the bot
    await init_database()

    # Ensure required channel IDs are accessible if necessary at startup
    # For simplicity, we assume the env vars are correct integer IDs
    # A more robust check would use client.get_chat() but that needs client to be started.
    # We checked existence of env vars above.

    main_logger.info("Connecting to Telegram servers and starting bot polling...")
    try:
        await bot.start()
        main_logger.info("Bot has successfully connected to Telegram and started polling!")
    except Exception as e:
         main_logger.critical(f"Failed to connect to Telegram and start polling: {e}", exc_info=True)
         # Maybe try to log this failure via Telegram if LOG_CHANNEL_ID is set and client somehow started?
         sys.exit(1)


    # Log that the bot is running and ready for updates
    main_logger.info("Bot is now running and listening for updates.")

    # Report bot startup to the log channel (if configured)
    if LOG_CHANNEL_ID and bot.is_connected:
         try:
             # Send a startup message
             startup_message = f"🤖 AnimeRealm Bot v{config.__version__} started successfully!"
             # Fetch basic bot info like username
             try:
                 bot_user = await bot.get_me()
                 startup_message += f"\n👤 Bot Username: @{bot_user.username}"
             except Exception:
                 main_logger.warning("Failed to fetch bot username on startup.")

             # Send to the log channel
             await bot.send_message(LOG_CHANNEL_ID, startup_message)
             main_logger.info(f"Sent startup message to log channel {LOG_CHANNEL_ID}")
         except Exception as e:
             main_logger.error(f"Failed to send startup message to log channel {LOG_CHANNEL_ID}: {e}")
             # Don't exit, continue running without log channel notification

    # The health check server managed by Procfile release runs separately on port 8080.
    # We only need to keep this asyncio event loop running for Pyrogram updates.
    main_logger.info("Health check server is assumed running by Procfile on port 8080.")


    # Keep the bot running until terminated
    await asyncio.Future() # Keeps the event loop running indefinitely until cancelled


if __name__ == "__main__":
    # Get config __version__ placeholder defined in config.py or handle it better
    if not hasattr(config, '__version__'):
        config.__version__ = "N/A" # Add a default version if not in config.py

    # Clean up the workdir on some signals if needed (more complex)
    # Or rely on Docker/Koyeb clean up.
    # basic atexit or signal handling could be added here.

    # Run the main async function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
         main_logger.info("Bot stopped manually via KeyboardInterrupt.")
         # You might want to close the MongoDB connection gracefully here
         from database.mongo_db import MongoDB
         asyncio.run(MongoDB.close())
    except Exception as e:
         main_logger.critical(f"Bot stopped due to unhandled exception in main loop: {e}", exc_info=True)
         # Attempt to close DB connection even on unhandled error
         from database.mongo_db import MongoDB
         try:
             asyncio.run(MongoDB.close())
         except Exception as db_close_e:
             main_logger.error(f"Failed to close DB connection during shutdown: {db_close_e}")
