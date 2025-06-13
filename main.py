# main.py
import asyncio
import logging
import sys
import os
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode # Keep ParseMode import for Client init

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
if ADMIN_IDS_STR:
    try: ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()]; if not ADMIN_IDS: raise ValueError("ADMIN_IDS is empty after parsing");
    except ValueError as e: main_logger.critical(f"Invalid format for ADMIN_IDS environment variable: {e}. Must be comma-separated integers."); sys.exit(1);
else: main_logger.warning("ADMIN_IDS environment variable is not set. No admin users defined.");

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
    try: FILE_STORAGE_CHANNEL_ID = int(FILE_STORAGE_CHANNEL_CHANNEL_ID_STR.strip()); main_logger.info(f"FILE_STORAGE_CHANNEL_ID is set to {FILE_STORAGE_CHANNEL_ID}.");
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


# --- Health Check Web Server ---

# Simple HTTP handler for the health check endpoint
async def healthz_handler(request):
    # Respond with a 200 OK and a simple body.
    # For a more robust check, you could ping the DB or Telegram API here.
    # For now, just respond immediately if the web server is running.
    return web.Response(text="ok", status=200)

# Async function to set up and start the aiohttp web server
async def start_health_server(port: int):
    main_logger.info(f"Starting health check web server on port {port}...")
    app = web.Application() # Create a web application
    # Add a route for the /healthz path
    app.router.add_get('/healthz', healthz_handler)
    # Run the web server using a runner
    runner = web.AppRunner(app)
    await runner.setup()
    # Use 0.0.0.0 to bind to all network interfaces within the container
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    main_logger.info(f"Health check server listening on 0.0.0.0:{port}")

    # The site.start() doesn't block. We need to keep it running.
    # It will run as long as the main event loop is running.
    # The await asyncio.Future() in main() will keep the loop running.


# --- Main Bot Start and Task Management ---
async def main():
    main_logger.info("Starting bot main process...")
    main_logger.info(">>> Calling init_database...")
    await init_database()
    main_logger.info("<<< init_database finished.") # Does this appear in logs?

    HEALTH_CHECK_PORT = 8080

    main_logger.info(f">>> Starting bot.start() task...")
    bot_task = asyncio.create_task(bot.start())
    main_logger.info(">>> Starting health server task...")
    health_task = asyncio.create_task(start_health_server(HEALTH_CHECK_PORT))
    main_logger.info("Tasks created. Awaiting bot task completion of initial startup...")

    await bot_task # Wait here until Pyrogram reports initial connection complete
    main_logger.info("<<< Bot.start() finished initial startup.") # Does this appear?
    main_logger.info("Bot is now running and listening for updates, health server task should be live.")
    main_logger.info(f">>> Health server expected at 0.0.0.0:{HEALTH_CHECK_PORT}/healthz") # Confirm expected port

    # Log if the health task finished early (it shouldn't with site.start())
    # Or just await the Future indefinitely.
    main_logger.info(">>> Awaiting asyncio.Future() to keep loop running indefinitely.")
    await asyncio.Future()

async def init_db(uri: str):
    main_logger.info(">>> init_db: Calling MongoDB.connect...")
    await MongoDB.connect(uri, DB_NAME)
    main_logger.info("<<< init_db: MongoDB.connect successful.") # Does this appear?
    main_logger.info(">>> init_db: Creating/Ensuring MongoDB indices...")
    # ... index creation logic ...
    main_logger.info("<<< init_db: MongoDB indices checked/created.") # Does this appear?

# Entry point of the script
if __name__ == "__main__":
    # Ensure version is defined for logging
    if not hasattr(config, '__version__'): config.__version__ = "N/A"

    main_logger.info("Application starting...")
    try:
        # Run the main asynchronous function
        asyncio.run(main())
    except KeyboardInterrupt:
         main_logger.info("Bot stopped manually via KeyboardInterrupt.");
    except SystemExit as e:
         # Catch sys.exit to log clean shutdown messages initiated by error handling
         if e.code == 0: main_logger.info("Application exited gracefully.");
         else: main_logger.critical(f"Application exited with code {e.code}.", exc_info=True);

    except Exception as e:
         # Catch any uncaught exceptions that escape the async loop or handlers
         main_logger.critical(f"Bot stopped due to unhandled exception in main loop: {e}", exc_info=True);
         # Attempt to close DB connection even on unhandled error - requires await in __main__ which asyncio.run doesn't handle after exception
         # A cleanup function registered with atexit or signal handling is better for graceful shutdown.
         # Example using atexit (sync, might block async cleanup) or signal handlers (more complex async):
         # from database.mongo_db import MongoDB
         # asyncio.run(MongoDB.close()) # Running sync run from async context might have issues

    # If a clean shutdown function existed, call it here.
    main_logger.info("Application exiting.")
