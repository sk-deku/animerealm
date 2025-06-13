# main.py
import asyncio
import logging
import sys
import os
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode

from dotenv import load_dotenv

# Import for the aiohttp web server health check
from aiohttp import web


# Configure basic logging as early as possible with stdout for container logs
logging.basicConfig(
    level=logging.INFO, # Set initial level to INFO or DEBUG for more detail
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S', # More standard timestamp format
    handlers=[
        logging.StreamHandler(sys.stdout) # Crucially, log to stdout for Koyeb container logs
    ]
)
# Set specific log levels for noisy libraries. Can lower these if trying to debug *their* behavior.
logging.getLogger("pyrogram").setLevel(logging.WARNING) # Suppress lower-level pyrogram logs
logging.getLogger("pymongo").setLevel(logging.WARNING) # Suppress lower-level pymongo logs
logging.getLogger("aiohttp").setLevel(logging.WARNING) # Suppress lower-level aiohttp logs
logging.getLogger("motor").setLevel(logging.WARNING)   # Suppress lower-level motor logs


main_logger = logging.getLogger(__name__) # Logger for this file

# --- Step 1: Load Environment Variables ---
main_logger.info("--- Step 1: Loading Environment Variables ---")
try:
    load_dotenv()
    main_logger.info("Environment variables loaded.")
except Exception as e:
    main_logger.critical(f"FATAL: Failed to load environment variables from .env file: {e}", exc_info=True)
    sys.exit(1) # Exit critically if config loading fails

# --- Step 2: Configuration & Validation ---
main_logger.info("--- Step 2: Loading and Validating Configuration ---")
try:
    # Load essential configuration
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    MONGO_URI = os.getenv("MONGO_URI")

    main_logger.info("Attempting to validate critical ENV variables.")
    # Validate essential environment variables immediately
    if not BOT_TOKEN:
        main_logger.critical("VALIDATION FAILED: BOT_TOKEN environment variable not set!"); sys.exit(1);
    main_logger.debug("BOT_TOKEN is set.")

    if not API_ID or not API_HASH:
         main_logger.critical("VALIDATION FAILED: API_ID and API_HASH environment variables are required for Pyrogram! Get them from https://my.telegram.org."); sys.exit(1);
    main_logger.debug("API_ID and API_HASH are set.")

    if not MONGO_URI:
        main_logger.critical("VALIDATION FAILED: MONGO_URI environment variable not set! Database connection is required."); sys.exit(1);
    main_logger.debug("MONGO_URI is set.")

    main_logger.info("Critical ENV variables validated successfully.")

    # Load other crucial, but not strictly exit-on-fail here, configs with checks
    ADMIN_IDS_STR = os.getenv("ADMIN_IDS", ""); ADMIN_IDS = [];
    main_logger.info(f"Attempting to parse ADMIN_IDS string: '{ADMIN_IDS_STR}'")
    if ADMIN_IDS_STR:
        try:
            ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()];
            if not ADMIN_IDS:
                 main_logger.warning("ADMIN_IDS string was not empty but parsed into an empty list. No admins defined.")
            else:
                 main_logger.info(f"Parsed ADMIN_IDS: {ADMIN_IDS}");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid format for ADMIN_IDS: {e}. Must be comma-separated integers."); sys.exit(1);
    else: main_logger.warning("ADMIN_IDS environment variable is not set. No admin users defined.");

    OWNER_ID_STR = os.getenv("OWNER_ID"); OWNER_ID = None;
    main_logger.info(f"Attempting to parse OWNER_ID string: '{OWNER_ID_STR}'")
    if OWNER_ID_STR:
        try: OWNER_ID = int(OWNER_ID_STR.strip()); main_logger.info(f"Parsed OWNER_ID: {OWNER_ID}");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid format for OWNER_ID: {e}. Must be a single integer."); sys.exit(1);
        if OWNER_ID is not None and OWNER_ID not in ADMIN_IDS and ADMIN_IDS: # Only warn if OWNER_ID is parsed AND ADMIN_IDS is not empty
             main_logger.warning(f"OWNER_ID ({OWNER_ID}) is not included in ADMIN_IDS. OWNER_ID may not have full admin access.")
    else: main_logger.warning("OWNER_ID environment variable is not set.");


    LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID"); LOG_CHANNEL_ID = None;
    main_logger.info(f"Attempting to parse LOG_CHANNEL_ID string: '{LOG_CHANNEL_ID_STR}'")
    if LOG_CHANNEL_ID_STR:
        try:
             LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR.strip()); main_logger.info(f"Parsed LOG_CHANNEL_ID: {LOG_CHANNEL_ID}");
             # Try to add file handler here using this ID, though it's less relevant for Koyeb std
             try: # Add File Handler for logging to bot.log
                  log_file_handler = logging.FileHandler("bot.log"); # Creates bot.log file in workdir
                  log_file_handler.setFormatter(logging.Formatter("[%(asctime)s - %(levelname)s] - %(name)s - %(message)s", datefmt='%Y-%m-%d %H:%M:%S'));
                  logging.getLogger().addHandler(log_file_handler);
                  main_logger.info(f"Configured logging to bot.log file (Local/Container persistence depends on deployment).");
             except Exception as e: main_logger.error(f"Failed to configure file logging: {e}", exc_info=True);
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid format for LOG_CHANNEL_ID: {e}. Must be an integer."); sys.exit(1);
    else: main_logger.info("LOG_CHANNEL_ID is not set.");

    FILE_STORAGE_CHANNEL_ID_STR = os.getenv("FILE_STORAGE_CHANNEL_ID"); FILE_STORAGE_CHANNEL_ID = None;
    main_logger.info(f"Attempting to parse FILE_STORAGE_CHANNEL_ID string: '{FILE_STORAGE_CHANNEL_ID_STR}'")
    if FILE_STORAGE_CHANNEL_ID_STR:
        try: FILE_STORAGE_CHANNEL_ID = int(FILE_STORAGE_CHANNEL_ID_STR.strip()); main_logger.info(f"Parsed FILE_STORAGE_CHANNEL_ID: {FILE_STORAGE_CHANNEL_ID}. File handling ENABLED.");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid format for FILE_STORAGE_CHANNEL_ID: {e}. Must be an integer."); sys.exit(1);
    else: main_logger.critical("VALIDATION FAILED: FILE_STORAGE_CHANNEL_ID is NOT set. File handling features WILL NOT work correctly. Exiting."); sys.exit(1);

    main_logger.info("Configuration loading and basic validation completed.")

    # Placeholder version config - better to load from a file or git tag if needed for display
    class AppConfig: # Temporary class to hold configs until loaded from config.py inside async main
        __version__ = "N/A_Init" # Version for early logging


except Exception as e:
     main_logger.critical(f"FATAL: An unexpected error occurred during configuration validation: {e}", exc_info=True)
     sys.exit(1)

# Note: Full configuration will be imported from config.py inside main() async function later

# --- Step 3: Pyrogram Client Initialization ---
main_logger.info("--- Step 3: Initializing Pyrogram Client ---")
try:
    main_logger.info(f"Pyrogram client configuration: api_id={API_ID}, bot_token is set.")
    bot = Client(
        name="anime_realm_bot", # Session name, determines session file name (anime_realm_bot.session)
        api_id=int(API_ID), # API_ID loaded and validated
        api_hash=API_HASH, # API_HASH loaded and validated
        bot_token=BOT_TOKEN, # BOT_TOKEN loaded and validated
        plugins=dict(root="handlers"), # Load handlers from the 'handlers' directory relative to the script
        workdir=".", # Pyrogram session files and bot.log will be created in the container's working directory /app
        parse_mode=ParseMode.HTML # Set HTML ParseMode globally for convenience
    )
    main_logger.info("Pyrogram client instance created successfully.")

except (ApiIdInvalid, ApiIdPublishedFlood): main_logger.critical("PYROGRAM INIT FAILED: Your API_ID/API_HASH are invalid or come from a public repository. Get valid API credentials from https://my.telegram.org.", exc_info=True); sys.exit(1);
except AuthKeyUnregistered: main_logger.critical("PYROGRAM INIT FAILED: Your Pyrogram session key is invalid or has expired. Delete the session file (e.g., /app/anime_realm_bot.session in container) and try again.", exc_info=True); sys.exit(1);
except Exception as e: main_logger.critical(f"FATAL PYROGRAM INIT FAILED: An unexpected error occurred during client initialization: {e}", exc_info=True); sys.exit(1);


# --- Step 4: Database Initialization ---
# init_db is an async function and needs to be called within an async context.
async def init_database():
    main_logger.info("--- Step 4: Database Initialization Started ---")
    # Import the database initialization function and DB_NAME constant within async context or higher scope
    from database.mongo_db import init_db # init_db handles connecting and indexing
    # MONGO_URI is already loaded and validated

    try:
        main_logger.info(f"Initiating MongoDB initialization process. Calling init_db with MONGO_URI (redacted) and DB_NAME='{config.DB_NAME}'.") # Use config.DB_NAME
        await init_db(MONGO_URI) # init_db handles connection and index creation
        main_logger.info("Database initialization completed successfully.")
    except ConnectionFailure as e:
        # init_db re-raises ConnectionFailure from MongoDB.connect
         main_logger.critical(f"FATAL DB INIT FAILED: Could not connect to or initialize database. ConnectionFailure: {e}", exc_info=True); sys.exit(1);
    except OperationFailure as e:
         # init_db re-raises OperationFailure from MongoDB.connect or indexing
         main_logger.critical(f"FATAL DB INIT FAILED: Database operation error during initialization. OperationFailure: {e}", exc_info=True); sys.exit(1);
    except Exception as e:
         # Catch any other errors during init_db process
         main_logger.critical(f"FATAL DB INIT FAILED: An unexpected error occurred during database initialization: {e}", exc_info=True); sys.exit(1);


# --- Step 5: Health Check Web Server Setup ---

# Simple async handler for the health check endpoint
async def healthz_handler(request):
    # This indicates that the web server itself is running within the bot's process.
    # A more comprehensive check might verify DB connection or Telegram API connection status.
    # For Koyeb's basic check, this is usually sufficient.
    return web.Response(text="ok", status=200)

# Async function to set up and start the aiohttp web server
async def start_health_server(port: int):
    main_logger.info(f"Attempting to start health check web server on 0.0.0.0:{port}...")
    app = web.Application() # Create a web application
    app.router.add_get('/healthz', healthz_handler) # Add route for /healthz GET requests

    # Configure and start the web server site
    runner = web.AppRunner(app)
    try:
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port) # Bind to all network interfaces
        await site.start()
        main_logger.info(f"Health check server listening successfully on 0.0.0.0:{port}/healthz.")
        # Note: The site.start() operation itself doesn't block. It starts background tasks.
        # The runner and site need the event loop to keep running to stay alive.
        # The asyncio.Future() in main() will keep the main loop running.

    except OSError as e:
         # Catch common errors like 'address already in use' if port is busy
         main_logger.critical(f"FATAL HEALTH CHECK SERVER FAILED TO START: Could not bind to port {port}. Is another process using it? {e}", exc_info=True); sys.exit(1);
    except Exception as e:
         main_logger.critical(f"FATAL HEALTH CHECK SERVER FAILED TO START: An unexpected error occurred during setup: {e}", exc_info=True); sys.exit(1);


# --- Step 6: Main Application Tasks and Execution ---
async def main():
    main_logger.info("--- Step 6: Starting Main Application Tasks ---")

    # --- Substep 6.1: Database Initialization ---
    # Call the database initialization async function
    await init_database() # Handles connection and indexing. Exits if fails.
    main_logger.info("Database initialization confirmed.")


    # Define the port for the health check server (Koyeb default is 8080)
    HEALTH_CHECK_PORT = 8080
    # You could load this from env if config.py defines it, e.g.: from config import HEALTH_CHECK_PORT_CFG ... HEALTH_CHECK_PORT = HEALTH_CHECK_PORT_CFG

    # --- Substep 6.2: Create and Schedule Async Tasks ---
    main_logger.info("Creating and scheduling Pyrogram bot and Health Check server tasks.")
    # Schedule the Pyrogram bot start task
    bot_task = asyncio.create_task(bot.start())
    main_logger.info("Pyrogram bot start task created.")

    # Schedule the health check web server start task
    health_task = asyncio.create_task(start_health_server(HEALTH_CHECK_PORT))
    main_logger.info(f"Health check server task created for port {HEALTH_CHECK_PORT}.")

    main_logger.info("Both main application tasks are scheduled in the asyncio event loop.")

    # --- Substep 6.3: Wait for Critical Services to Report Ready ---
    # Wait for the Pyrogram bot to connect to Telegram successfully.
    # bot.start() completes the initial connection phase.
    main_logger.info("Awaiting Pyrogram client's initial connection to Telegram (await bot_task)...")
    # If bot.start() raises an error during initial connection, bot_task.exception() would return it, or the task state changes.
    # Awaiting the task itself waits for its completion (including successful exit or exception).
    try:
         await bot_task # This will block until the client has started or failed to start.
         main_logger.info("Pyrogram client has successfully started its event loop.")

         # A small pause might be needed if client connection is not *immediately* ready after task finishes.
         # However, pyrogram.Client.start() is designed to mean it *is* ready for updates.
         # Optional: Verify connection state if possible and if needed for health logic
         # if not bot.is_connected: main_logger.warning("Pyrogram client task completed but is_connected is False?"); # Rare


    except Exception as e:
         # Catch exceptions specifically from bot.start() task failure.
         main_logger.critical(f"FATAL: Pyrogram bot task failed during startup: {e}", exc_info=True)
         # Bot failed to start, the application cannot proceed. Exit.
         # The health server *might* still be running if its startup didn't fail, but the app is broken.
         # Exit process gracefully.
         # Ensure health task is cancelled before exiting, if still running.
         health_task.cancel()
         try: await health_task # Allow cancellation to finish
         except (asyncio.CancelledError, Exception): pass # Handle exceptions during cancellation


         sys.exit(1) # Exit critically


    # --- Substep 6.4: Post-Startup Actions ---
    main_logger.info("All critical services reported ready (Database, Pyrogram). Application core is live.")

    # Report bot startup to the log channel (if configured)
    # Bot must be connected (`bot.is_connected` should be True) to send messages.
    if LOG_CHANNEL_ID and bot.is_connected:
         main_logger.info(f"Attempting to send startup message to log channel {LOG_CHANNEL_ID}.")
         try:
             from config import __version__ as app_version # Import app version from config
             bot_user = await client.get_me() # Use client instance from outer scope (the global 'bot')
             startup_message = f"🤖 AnimeRealm Bot v{app_version} started successfully!"
             startup_message += f"\n👤 Bot Username: @{bot_user.username}"
             startup_message += f"\n🌐 Health check live on 0.0.0.0:{HEALTH_CHECK_PORT}/healthz"

             await client.send_message(LOG_CHANNEL_ID, startup_message) # Send using the running client
             main_logger.info(f"Startup message sent to log channel {LOG_CHANNEL_ID}.")

         except Exception as e:
              # Failure to send to log channel is usually non-critical
              main_logger.error(f"Failed to send startup message to log channel {LOG_CHANNEL_ID}: {e}", exc_info=True);
              # Application continues even if this message failed.


    # --- Substep 6.5: Keep Event Loop Running ---
    main_logger.info("Application setup complete. Keeping asyncio event loop running indefinitely for tasks.")
    main_logger.info("This process will run until explicitly terminated (e.g., by Koyeb scaling down or stopping the service).")
    # Keep the bot and health server tasks running by awaiting a future that never completes
    await asyncio.Future() # Blocks here until the Future is done/cancelled (which it won't be automatically)


# --- Step 7: Application Entry Point Execution ---
# This block ensures the async main() function is run when the script starts.
if __name__ == "__main__":
    main_logger.info("Script initiated directly. Entering asyncio run block.")
    try:
        # asyncio.run() is the entry point for running async applications
        asyncio.run(main())
        main_logger.info("asyncio.run(main()) completed.") # This line might not be reached on abrupt exits

    except KeyboardInterrupt:
         main_logger.info("Application received KeyboardInterrupt. Shutting down gracefully.");
         # asyncio.run() handles basic cleanup on KeyboardInterrupt, cancelling tasks etc.
         # You could add specific cleanup logic (like closing DB) using signal handlers.
         # Example Signal Handling for Cleanup (requires careful async management):
         # async def cleanup(): await MongoDB.close(); print("DB Closed.");
         # import signal; asyncio.get_event_loop().add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(cleanup()));


    except SystemExit as e:
         # Catch sys.exit exceptions initiated by critical error handling inside main()
         if e.code == 0: main_logger.info("Application exited with status code 0 (graceful SystemExit).");
         else: main_logger.critical(f"Application exited with non-zero status code {e.code} (SystemExit).", exc_info=True);


    except Exception as e:
         # Catch any uncaught exceptions that somehow escape the main() async flow
         main_logger.critical(f"Application terminated due to uncaught exception outside main(): {e}", exc_info=True);


    finally:
         main_logger.info("Application process finished.")
         # Note: Final resource cleanup (like DB closing) on crash or SystemExit requires signal handling setup or similar robust cleanup.
         # Simple finally block logs process finish, but doesn't guarantee async cleanup completed.
