# main.py
import asyncio
import logging
import sys
import os
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode # Keep ParseMode import for Client init
#from flask import Flask
from dotenv import load_dotenv

# Import for the aiohttp web server health check
from aiohttp import web # Core web server components


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
logging.getLogger("aiohttp").setLevel(logging.WARNING) # Keep aiohttp logging level managed
logging.getLogger("motor").setLevel(logging.WARNING)


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
if not BOT_TOKEN: main_logger.critical("BOT_TOKEN environment variable not set!"); sys.exit(1);
if not API_ID or not API_HASH: main_logger.critical("API_ID and API_HASH environment variables are required for Pyrogram! Get them from https://my.telegram.org."); sys.exit(1);
if not MONGO_URI: main_logger.critical("MONGO_URI environment variable not set! Database connection is required."); sys.exit(1);

# Admin IDs (comma separated)
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", ""); ADMIN_IDS = [];

# Owner ID (single)
OWNER_ID_STR = os.getenv("OWNER_ID"); OWNER_ID = None;
if OWNER_ID_STR:
    try: OWNER_ID = int(OWNER_ID_STR.strip());
    except ValueError as e: main_logger.critical(f"Invalid format for OWNER_ID environment variable: {e}. Must be a single integer."); sys.exit(1);
    if OWNER_ID is not None and OWNER_ID not in ADMIN_IDS: main_logger.warning(f"OWNER_ID ({OWNER_ID}) is not included in ADMIN_IDS. OWNER_ID may not have full admin access depending on handler logic.");

# Telegram Channel IDs for logs and file storage (Bot must be admin)
LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID"); LOG_CHANNEL_ID = None;
if LOG_CHANNEL_ID_STR:
    try:
         LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR.strip());
         try: # Add File Handler to log. File will be created locally inside the container/deployment folder.
              log_file_handler = logging.FileHandler("bot.log");
              log_file_handler.setFormatter(logging.Formatter("[%(asctime)s - %(levelname)s] - %(name)s - %(message)s", datefmt='%H:%M:%S'));
              logging.getLogger().addHandler(log_file_handler);
              main_logger.info(f"Logging to bot.log file.");
         except Exception as e: main_logger.error(f"Failed to configure file logging: {e}", exc_info=True);
    except ValueError as e: main_logger.critical(f"Invalid format for LOG_CHANNEL_ID environment variable: {e}. Must be an integer."); sys.exit(1);


FILE_STORAGE_CHANNEL_ID_STR = os.getenv("FILE_STORAGE_CHANNEL_ID"); FILE_STORAGE_CHANNEL_ID = None;
if FILE_STORAGE_CHANNEL_ID_STR:
    try: FILE_STORAGE_CHANNEL_ID = int(FILE_STORAGE_CHANNEL_ID_STR.strip()); main_logger.info(f"FILE_STORAGE_CHANNEL_ID is set to {FILE_STORAGE_CHANNEL_ID}.");
    except ValueError as e: main_logger.critical(f"Invalid format for FILE_STORAGE_CHANNEL_ID environment variable: {e}. Must be an integer."); sys.exit(1);
else: main_logger.critical("FILE_STORAGE_CHANNEL_ID environment variable is NOT set. File handling features WILL NOT work correctly."); sys.exit(1);

# Other configuration variables are now imported in relevant files from config.py


# --- Pyrogram Client Initialization ---
main_logger.info("Initializing Pyrogram client...")
try:
    bot = Client(
        name="anime_realm_bot",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=dict(root="handlers"),
        workdir=".", # Session files location
        parse_mode=ParseMode.HTML
    )
    main_logger.info("Pyrogram client created.")

except (ApiIdInvalid, ApiIdPublishedFlood): main_logger.critical("Your API_ID/API_HASH are invalid or come from a public repository. Get valid API credentials from https://my.telegram.org."); sys.exit(1);
except AuthKeyUnregistered: main_logger.critical("Your Pyrogram session key is invalid or has expired. Delete the session file (e.g., anime_realm_bot.session) and try again."); sys.exit(1);
except Exception as e: main_logger.critical(f"An unexpected error occurred during Pyrogram client initialization: {e}", exc_info=True); sys.exit(1);


# --- Database Initialization ---
async def init_database():
    main_logger.info("Initializing database connection and structure...")
    from database.mongo_db import init_db
    try: await init_db(MONGO_URI); main_logger.info("Database initialized successfully.");
    except Exception as e: main_logger.critical(f"Database initialization failed: {e}", exc_info=True); sys.exit(1);


# --- Main Bot Start and Task Management ---
async def main():
    main_logger.info("Starting bot main process...")

    # Initialize database connection and structure before starting Pyrogram
    await init_database()

    # Define the port for the health check server (Koyeb expects 8080 by default)
    HEALTH_CHECK_PORT = 8080
    # Optionally, load the port from environment variables if needed:
    # HEALTH_CHECK_PORT = int(os.getenv("PORT", 8080))

    # Create asyncio tasks for the Pyrogram bot and the health check server
    bot_task = asyncio.create_task(bot.start())
    health_task = asyncio.create_task(start_health_server(HEALTH_CHECK_PORT))


    main_logger.info("Pyrogram bot and Health check server tasks created. Running concurrently.")

    # Report bot startup to the log channel (if configured) AFTER the bot is started and connected
    # The health check will pass once start_health_server is listening.
    # Log channel message should happen after bot.start() succeeds.
    # Wait briefly for bot to connect after bot.start() completes the startup phase.

    # Need to handle waiting for bot to be ready for sending messages after bot.start().
    # client.start() connects and starts polling. Is_connected property can check state.
    await bot_task # Wait for the bot's startup phase to complete the initial connection process


    main_logger.info("Pyrogram client reports started.")

    # Check bot connection and send startup message if configured
    if LOG_CHANNEL_ID and bot.is_connected:
         try:
             bot_user = await bot.get_me()
             startup_message = f"🤖 AnimeRealm Bot v{config.__version__} started successfully!"
             startup_message += f"\n👤 Bot Username: @{bot_user.username}"
             startup_message += f"\n🌐 Health check running on port {HEALTH_CHECK_PORT}/healthz"
             await client.send_message(LOG_CHANNEL_ID, startup_message)
             main_logger.info(f"Sent startup message to log channel {LOG_CHANNEL_ID}")
         except Exception as e: main_logger.error(f"Failed to send startup message to log channel {LOG_CHANNEL_ID}: {e}", exc_info=True);


    # The main task should now keep running, keeping the event loop alive.
    # asyncio.gather or just awaiting a Future indefinitely works.
    # Await the health_task indefinitely is fine as well since its start() call keeps it running.
    # Or simply let the asyncio event loop manage both tasks. Await an empty Future is simple.
    main_logger.info("Bot is now running and listening for updates, health server is live.")
    await asyncio.Future() # This will keep the main loop running until it's explicitly cancelled


#if __name__ == "__main__":
#    print("Starting bot...")
#    app.run() 
