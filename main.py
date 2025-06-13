# main.py
# No aiohttp imports needed for health check
import asyncio
import logging
import sys
import os
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler

def run_bot():
    app = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

    async def start(update, context):
        await update.message.reply_text("Hello! I'm alive.")

    app.add_handler(CommandHandler("start", start))
    app.run_polling()
    

# --- Configure basic logging immediately (as before) ---
logging.basicConfig(
    level=logging.DEBUG, # Keep DEBUG level for detailed startup logs
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger("pyrogram").setLevel(logging.INFO)
logging.getLogger("pymongo").setLevel(logging.INFO)
# No aiohttp logs to silence now unless used elsewhere
logging.getLogger("motor").setLevel(logging.INFO)


main_logger = logging.getLogger(__name__)

# --- Step 1: Load Environment Variables ---
main_logger.info("--- Step 1: Loading Environment Variables ---")
try:
    load_dotenv()
    main_logger.info("Environment variables loaded.")
except Exception as e:
    main_logger.critical(f"FATAL: Failed to load environment variables from .env file: {e}", exc_info=True)
    sys.exit(1)


# --- Step 2: Configuration & Validation ---
main_logger.info("--- Step 2: Loading and Validating Configuration ---")
try:
    main_logger.debug("Attempting to retrieve critical ENV variables using os.getenv.")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    MONGO_URI = os.getenv("MONGO_URI")

    main_logger.info("Attempting to validate critical ENV variables.")
    if not BOT_TOKEN: main_logger.critical("VALIDATION FAILED: BOT_TOKEN not set!"); sys.exit(1); main_logger.info("Validation OK: BOT_TOKEN is set.");
    if not API_ID or not API_HASH: main_logger.critical("VALIDATION FAILED: API_ID or API_HASH not set! "); sys.exit(1); main_logger.info("Validation OK: API_ID and API_HASH are set.");
    if not MONGO_URI: main_logger.critical("VALIDATION FAILED: MONGO_URI not set!"); sys.exit(1); main_logger.info("Validation OK: MONGO_URI is set.");
    main_logger.info("Critical ENV variables loaded and validated successfully.")

    ADMIN_IDS_STR = os.getenv("ADMIN_IDS", ""); ADMIN_IDS = []; main_logger.info(f"Parsing ADMIN_IDS: '{ADMIN_IDS_STR}'");
    if ADMIN_IDS_STR:
        try:
            ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()]
            if not ADMIN_IDS:
                main_logger.warning("ADMIN_IDS parsed empty.")
            else:
                main_logger.info(f"Parsed ADMIN_IDS: {ADMIN_IDS}")
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid ADMIN_IDS format: {e}."); sys.exit(1);
    else: main_logger.info("ADMIN_IDS not set.");

    OWNER_ID_STR = os.getenv("OWNER_ID"); OWNER_ID = None; main_logger.info(f"Parsing OWNER_ID: '{OWNER_ID_STR}'");
    if OWNER_ID_STR:
        try: OWNER_ID = int(OWNER_ID_STR.strip()); main_logger.info(f"Parsed OWNER_ID: {OWNER_ID}");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid OWNER_ID format: {e}."); sys.exit(1);
        if OWNER_ID is not None and OWNER_ID not in ADMIN_IDS and ADMIN_IDS: main_logger.warning(f"OWNER_ID ({OWNER_ID}) is not in ADMIN_IDS. Owner might lack full admin privileges.");
    else: main_logger.info("OWNER_ID not set.");


    LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID"); LOG_CHANNEL_ID = None; main_logger.info(f"Parsing LOG_CHANNEL_ID: '{LOG_CHANNEL_ID_STR}'");
    if LOG_CHANNEL_ID_STR:
        try: LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR.strip()); main_logger.info(f"Parsed LOG_CHANNEL_ID: {LOG_CHANNEL_ID}");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid LOG_CHANNEL_ID: {e}."); sys.exit(1);
    else: main_logger.info("LOG_CHANNEL_ID is not set. Admin logs will only appear in stdout/stderr.");

    FILE_STORAGE_CHANNEL_ID_STR = os.getenv("FILE_STORAGE_CHANNEL_ID"); FILE_STORAGE_CHANNEL_ID = None; main_logger.info(f"Parsing FILE_STORAGE_CHANNEL_ID: '{FILE_STORAGE_CHANNEL_ID_STR}'");
    if FILE_STORAGE_CHANNEL_ID_STR:
        try: FILE_STORAGE_CHANNEL_ID = int(FILE_STORAGE_CHANNEL_ID_STR.strip()); main_logger.info(f"Parsed FILE_STORAGE_CHANNEL_ID: {FILE_STORAGE_CHANNEL_ID}. File handling ENABLED.");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid FILE_STORAGE_CHANNEL_ID: {e}."); sys.exit(1);
    else: main_logger.critical("VALIDATION FAILED: FILE_STORAGE_CHANNEL_ID NOT set. File handling features DISABLED."); sys.exit(1);

    main_logger.info("Configuration loading and basic validation completed.")

except Exception as e:
     main_logger.critical(f"FATAL: An unexpected error occurred during configuration validation: {e}", exc_info=True)
     sys.exit(1)


# Import config.py now that critical ENV is validated
try:
    main_logger.info("Importing config.py for other constants.")
    import config
    main_logger.info("config.py imported successfully. Version: %s", config.__version__);
except Exception as e: main_logger.critical(f"FATAL: Failed to import config.py: {e}", exc_info=True); sys.exit(1);

# Now import database functions/models after config is loaded and validated (they depend on config for DB_NAME)
try:
    main_logger.info("Importing database functions and models.")
    from database.mongo_db import init_db, MongoDB # init_db connects and indexes, MongoDB provides client/collection access
    from database.models import User # Import models needed for early operations or typing
    main_logger.info("Database modules imported successfully.")
except Exception as e:
    main_logger.critical(f"FATAL: Failed to import database modules: {e}", exc_info=True); sys.exit(1);


# --- Step 4: Pyrogram Client Initialization ---
main_logger.info("--- Step 4: Initializing Pyrogram Client ---")
try:
    main_logger.info(f"Pyrogram client configuration using API_ID='{API_ID}', API_HASH='{API_HASH[:4]}...', BOT_TOKEN is set.")
    # Pyrogram session files will be created in the configured workdir "." which is /app in Docker
    bot = Client(
        name="anime_realm_bot",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=dict(root="handlers"),
        workdir=".", # Session files go here
        parse_mode=config.PARSE_MODE
    )
    main_logger.info("Pyrogram client instance created successfully.")
    main_logger.info("Client name: '%s', Workdir: '%s'", bot.name, bot.workdir)


except (ApiIdInvalid, ApiIdPublishedFlood): main_logger.critical("FATAL PYROGRAM INIT FAILED: API_ID/API_HASH invalid or public.", exc_info=True); sys.exit(1);
except AuthKeyUnregistered: main_logger.critical("FATAL PYROGRAM INIT FAILED: Session key invalid. Delete session file (/app/anime_realm_bot.session).", exc_info=True); sys.exit(1);
except Exception as e: main_logger.critical(f"FATAL PYROGRAM INIT FAILED: Unexpected error: {e}", exc_info=True); sys.exit(1);


# --- Step 5: Database Initialization (Async, needs async context) ---
async def init_database_async():
    main_logger.info("--- Step 5: Async Database Initialization Started ---")
    try:
        main_logger.info("Calling database.mongo_db.init_db to connect and index.")
        await init_db(MONGO_URI) # init_db handles connecting and indexing. Raises exceptions on failure.
        main_logger.info("Database initialization completed successfully (connection established, indexing done).")
        # Print confirm specifically that init_db call finished inside async function
        print("DEBUG: --- Step 5.1: Async Database Initialization AWAIT Reported Success. ---")


    except Exception as e:
         # Catch any error from init_db (includes connection/operation failures and general exceptions)
         main_logger.critical(f"FATAL DB INIT FAILED IN ASYNC: An error occurred during database initialization: {e}", exc_info=True);
         print(f"CRITICAL PRINT: FATAL DB INIT FAILED (Async): {e}");
         # Do NOT sys.exit() directly inside async function or within task run by asyncio.create_task.
         # Let the exception propagate to the task or caller, or set an event/flag.
         # Raise the exception so asyncio can propagate it.
         raise # Re-raise the exception


# --- Step 6: Main Application Tasks and Execution ---
# This is the main async function run by asyncio.run
async def main_async_tasks():
    main_logger.info("--- Step 6: Main async Application Tasks Execution Started ---")

    # Create tasks for Database Initialization and Pyrogram Bot Start.
    # Run them concurrently.
    main_logger.info("Creating tasks: Database Initialization and Pyrogram Bot Start.")
    db_init_task = asyncio.create_task(init_database_async())
    main_logger.info("Database initialization task scheduled.")

    bot_task = asyncio.create_task(bot.start())
    main_logger.info("Pyrogram bot start task scheduled.")

    main_logger.info("Both core tasks (DB init, Bot start) are scheduled to run concurrently.")


    # --- Substep 6.1: Wait for Critical Services to Report Ready ---
    # Wait for BOTH the database initialization AND the Pyrogram client start tasks to complete.
    # Use asyncio.gather to wait for both. return_exceptions=True to see *all* failures, not just the first.
    # However, for fatal startup, failing fast on first critical service failure is desired.
    # Let exceptions propagate normally for faster failure notification.

    main_logger.info("Awaiting completion of essential services startup (Database init & Pyrogram connection)...")
    try:
         # Wait for both tasks to complete. If either task fails (raises exception), gather will raise that exception.
         await asyncio.gather(db_init_task, bot_task)
         main_logger.info("Both Database initialization and Pyrogram bot tasks completed successfully.")
         print(f"DEBUG: --- Step 6.1: DB and Bot tasks AWAITED SUCCESSFULLY. ---")


    except Exception as e:
         # This exception comes from whichever task failed first or the first to fail after others completed.
         main_logger.critical(f"FATAL STARTUP FAILURE: One or more essential service tasks failed: {e}", exc_info=True);
         print(f"CRITICAL PRINT: FATAL STARTUP FAILURE IN ASYNC TASK AWAIT: {e}");

         # Attempt to cancel the *other* task if it's still pending or not completed, just in case.
         if not db_init_task.done(): db_init_task.cancel();
         if not bot_task.done(): bot_task.cancel();

         # Re-await with return_exceptions to ensure exceptions during cancellation or already done tasks are caught.
         try: await asyncio.gather(db_init_task, bot_task, return_exceptions=True);
         except Exception: pass # Ignore exceptions during final cleanup await


         # Note: The health check server task is *not* created or managed here.
         # Its process is expected to be run separately by Procfile/Koyeb.
         # It should not be running within THIS async event loop.


         sys.exit(1); # Exit critically


    # --- Substep 6.2: Post-Startup Actions ---
    main_logger.info("All critical services reported ready. Application core is live and Pyrogram client is polling.")
    print(f"DEBUG: --- Step 6.2: All Critical Services Reported Ready. Bot Worker Should Be Operational. ---")


    # Report bot startup to the log channel (if configured)
    if LOG_CHANNEL_ID is not None and bot.is_connected:
         main_logger.info(f"Configured LOG_CHANNEL_ID is {LOG_CHANNEL_ID} and bot is connected. Attempting to send startup notification.")
         asyncio.create_task(send_startup_notification(bot)) # Pass the Pyrogram client instance


    # --- Substep 6.3: Keep Event Loop Running ---
    main_logger.info("Application setup complete. The asyncio event loop will continue running to process Pyrogram updates.")
    main_logger.info("The 'health-server' process (running Flask/Gunicorn) should be monitored separately by Koyeb.")
    main_logger.info("This 'worker' process will run until explicitly terminated.")

    # Keep the asyncio event loop running indefinitely for Pyrogram tasks.
    # This task will block here until the event loop is stopped externally.
    await asyncio.Future()


# Helper task to send startup notification message to log channel
async def send_startup_notification(client: Client):
     try:
         main_logger.debug(f"Executing send_startup_notification task.");

         # Need client.me information, which is available after client.start() succeeds.
         if not client.me:
             main_logger.warning("Client.me not available during startup notification task. Skipping detailed user info.")
             bot_username = "UnknownBotUsername"
             bot_id = "UnknownBotId"
         else:
              bot_username = client.me.username
              bot_id = client.me.id


         from config import __version__ # Import version from config


         startup_message = f"🤖 AnimeRealm Bot v{__version__} (Worker) started successfully!"
         startup_message += f"\n👤 Bot: @{bot_username} (ID: {bot_id})"
         # Mention the expected health check server location for context (Optional)
         startup_message += f"\n🩺 Health check endpoint should be available via 'health-server' process on port 8080 /healthz"


         # Ensure LOG_CHANNEL_ID is valid int and connection is up.
         if LOG_CHANNEL_ID is None:
             main_logger.warning("LOG_CHANNEL_ID is None in send_startup_notification task. Cannot send.")
             return
         if not client.is_connected:
             main_logger.warning(f"Client not connected in send_startup_notification task for channel {LOG_CHANNEL_ID}. Skipping send.");
             return


         main_logger.info(f"Attempting to send startup message to LOG_CHANNEL_ID: {LOG_CHANNEL_ID}. Message preview: '{startup_message[:100]}...'.");
         await client.send_message(int(LOG_CHANNEL_ID), startup_message, parse_mode=config.PARSE_MODE);
         main_logger.info(f"Startup notification successfully sent to log channel {LOG_CHANNEL_ID}.");


     except Exception as e:
          main_logger.critical(f"FATAL ERROR IN STARTUP NOTIFICATION TASK: Failed to send startup message to log channel {LOG_CHANNEL_ID}: {e}", exc_info=True);
          # Log failure but task completes without affecting main bot loop.


# --- Step 7: Application Entry Point Execution (If script run directly) ---
# This block ensures the async main_async_tasks() function is run when the script starts.
if __name__ == "__main__":
    print("DEBUG: --- Step 7.1: __main__ block executed. ---")
    main_logger.info("Application initiation point reached (__main__ block).")
    print("DEBUG: --- Step 7.2: Entering asyncio.run block to start async tasks. ---")

    try:
        # asyncio.run() is the standard entry point for running a top-level async function.
        # It manages the event loop, task scheduling, and graceful shutdown on signals (like Ctrl+C).
        asyncio.run(main_async_tasks());
        main_logger.info("asyncio.run(main_async_tasks()) completed without exceptions."); # This line might not be reached on abrupt exits

    except KeyboardInterrupt:
         main_logger.info("Application received KeyboardInterrupt. Shutting down gracefully.");
         # asyncio.run handles basic task cancellation on SIGINT (Ctrl+C).
         # More complex cleanup (DB close) requires signal handlers on the loop itself.


    except SystemExit as e:
         # Catch SystemExit exceptions initiated by critical error handling (sys.exit).
         if e.code == 0: main_logger.info("Application exited cleanly (status code 0).");
         else: main_logger.critical(f"Application exited due to SystemExit with code {e.code}. Check logs for cause.", exc_info=True);

    except Exception as e:
         # Catch any unexpected exception that propagates out of the asyncio.run block.
         main_logger.critical(f"Application terminated due to uncaught exception outside async execution: {e}", exc_info=True);

    finally:
         print("DEBUG: --- Step 7.3: Exiting __main__ block. ---")
         main_logger.info("Application process finished.");
         # Ensure logs are flushed before process exits if needed (basicConfig to stdout helps this).
