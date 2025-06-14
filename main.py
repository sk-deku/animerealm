# main.py

# Use print() statements for absolute early stage logging before logging.basicConfig
print("DEBUG: --- Step 0.1: main.py script execution started. ---")

import asyncio
print("DEBUG: --- Step 0.2: Starting essential imports (asyncio, logging, sys, os, dotenv). ---")
import logging
import sys
import os

# --- No python-telegram-bot imports here ---
# The Runtime Error indicates imports related to telegram.ext were happening.


# Imports needed for environment variables and Pyrogram client
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode


# Flask/Gunicorn health check is handled by app.py via Procfile,
# This main.py (worker) does NOT need to know about Flask or aiohttp for health check server anymore.


# --- Step 1: Configure Logging ---
print("DEBUG: --- Step 1.1: Configuring logging. ---")
try:
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.getLogger("pyrogram").setLevel(logging.INFO)
    logging.getLogger("pymongo").setLevel(logging.INFO)
    logging.getLogger("motor").setLevel(logging.INFO)
    # If aiohttp is used elsewhere, silence its logs too if needed: logging.getLogger("aiohttp").setLevel(logging.INFO)

    main_logger = logging.getLogger(__name__)
    main_logger.info("Logging configured successfully. Standard output stream enabled.")
    print("DEBUG: --- Step 1.2: Logging configured. Switching to configured logger. ---")

except Exception as e:
    print(f"CRITICAL PRINT: FATAL: Failed to configure logging: {e}")
    sys.exit(1)


# Check 4: Environment variable loading start
main_logger.info("--- Step 2: Loading Environment Variables ---")
try:
    print("DEBUG: --- Step 2.1: Calling load_dotenv(). ---")
    load_dotenv()
    print("DEBUG: --- Step 2.2: load_dotenv() completed. ---")
    main_logger.info("Environment variables loaded from .env (if file exists).")
except Exception as e:
    main_logger.critical(f"FATAL: Failed to load environment variables from .env file: {e}", exc_info=True)
    sys.exit(1)


# --- Step 3: Configuration & Validation ---
main_logger.info("--- Step 3: Loading and Validating Configuration ---")
try:
    main_logger.debug("Attempting to retrieve critical ENV variables using os.getenv.")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    MONGO_URI = os.getenv("MONGO_URI")

    main_logger.info("Attempting to validate critical ENV variables.")
    if not BOT_TOKEN: main_logger.critical("VALIDATION FAILED: BOT_TOKEN not set! Ensure variable exists on Koyeb."); sys.exit(1); main_logger.info("Validation OK: BOT_TOKEN is set.");
    if not API_ID or not API_HASH: main_logger.critical("VALIDATION FAILED: API_ID or API_HASH not set! Required for Pyrogram."); sys.exit(1); main_logger.info("Validation OK: API_ID and API_HASH are set.");
    if not MONGO_URI: main_logger.critical("VALIDATION FAILED: MONGO_URI not set! Database connection required."); sys.exit(1); main_logger.info("Validation OK: MONGO_URI is set.");
    main_logger.info("Critical ENV variables loaded and validated successfully.")

    # --- Load Other Configs ---
    ADMIN_IDS_STR = os.getenv("ADMIN_IDS", ""); ADMIN_IDS = []; main_logger.info(f"Parsing ADMIN_IDS: '{ADMIN_IDS_STR}'");
    if ADMIN_IDS_STR:
        try: ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') 
            if admin_id.strip()]; 
            if not ADMIN_IDS: main_logger.warning("ADMIN_IDS parsed empty."); 
            else: main_logger.info(f"Parsed ADMIN_IDS: {ADMIN_IDS}");
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

    main_logger.info("Configuration loading and validation completed.")

except Exception as e:
     main_logger.critical(f"FATAL: An unexpected error occurred during configuration loading/validation: {e}", exc_info=True)
     sys.exit(1)

# Import config.py now that critical ENV is validated
try:
    main_logger.info("Importing config.py for other constants.")
    import config
    main_logger.info("config.py imported successfully. Version: %s", config.__version__);
except Exception as e: main_logger.critical(f"FATAL: Failed to import config.py: {e}", exc_info=True); sys.exit(1);

# Import database functions and models now
try:
    main_logger.info("Importing database functions and models.")
    from database.mongo_db import init_db, MongoDB
    from database.models import User # Example model import if needed early (otherwise import in handlers)
    main_logger.info("Database modules imported successfully.")
    print("DEBUG: --- Step 3.1: DB modules imported successfully. ---")

except Exception as e:
    main_logger.critical(f"FATAL: Failed to import database modules: {e}", exc_info=True);
    print(f"CRITICAL PRINT: FATAL: Failed to import database modules: {e}"); # Fallback print
    sys.exit(1);


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
        plugins=dict(root="handlers"), # Pyrogram will look for handlers/__init__.py
        workdir=".", # Session files go here (container /app)
        parse_mode=config.PARSE_MODE
    )
    main_logger.info("Pyrogram client instance created successfully.")
    main_logger.info("Client name: '%s', Workdir: '%s'", bot.name, bot.workdir)
    print("DEBUG: --- Step 4.1: Pyrogram Client instance created. ---")

except (ApiIdInvalid, ApiIdPublishedFlood): main_logger.critical("FATAL PYROGRAM INIT FAILED: API_ID/API_HASH invalid or public.", exc_info=True); sys.exit(1);
except AuthKeyUnregistered: main_logger.critical("FATAL PYROGRAM INIT FAILED: Session key invalid. Delete session file (/app/anime_realm_bot.session).", exc_info=True); sys.exit(1);
except Exception as e: main_logger.critical(f"FATAL PYROGRAM INIT FAILED: Unexpected error: {e}", exc_info=True); sys.exit(1);


# --- Step 5: Database Initialization (Async function called within async main) ---
async def init_database_async():
    main_logger.info("--- Step 5: Async Database Initialization Started ---")
    try:
        # MONGO_URI is already loaded and validated in sync code
        main_logger.info(f"Calling database.mongo_db.init_db with MONGO_URI (redacted) and DB_NAME='{config.DB_NAME}'.");
        await init_db(MONGO_URI) # init_db connects and indexes. Raises exceptions on failure.
        main_logger.info("Database initialization completed successfully (connection established, indexing done).")
        print("DEBUG: --- Step 5.1: Async Database Initialization AWAIT Reported Success. ---")

    except Exception as e:
         main_logger.critical(f"FATAL DB INIT FAILED IN ASYNC: An error occurred during database initialization: {e}", exc_info=True);
         # Allow exception to propagate to the caller task (main_async_tasks).
         raise # Re-raise the exception


# --- Step 6: Async Application Main Function ---
# This is the main async function run by asyncio.run
async def run_app_async():
    main_logger.info("--- Step 6: Main async Application Execution Started ---")

    # Create async tasks for essential services that need to run concurrently
    main_logger.info("Creating tasks: Database Initialization and Pyrogram Bot Start.")

    # 6.1: Database Initialization Task
    # Create the task for DB initialization. It will run in parallel with bot.start() if awaited together or event loop is running.
    # Its completion signals DB is ready.
    db_init_task = asyncio.create_task(init_database_async())
    main_logger.info("Database initialization task scheduled.")

    # 6.2: Pyrogram Bot Start Task
    # Create the task for starting the Pyrogram client.
    # Its completion signals the bot is connected and polling started.
    main_logger.info("Pyrogram bot start task scheduled (await bot.start()).")
    bot_start_task = asyncio.create_task(bot.start()) # Naming it specifically confirms its purpose

    main_logger.info("Both core tasks (DB init, Bot start) are scheduled to run concurrently.")

    # --- Substep 6.1: Wait for Critical Services to Report Ready ---
    # Await the completion of both essential tasks. If either fails, gather will propagate the exception.
    main_logger.info("Awaiting completion of essential services startup (Database init task & Pyrogram bot task)...")
    try:
        # Use asyncio.gather to wait for both tasks. Exceptions will be propagated normally.
        # The main execution continues ONLY if both tasks complete without raising exceptions.
        await asyncio.gather(db_init_task, bot_start_task)
        main_logger.info("Both Database initialization task and Pyrogram bot start task completed successfully.")
        print("DEBUG: --- Step 6.1: DB init task and Bot start task AWAITED SUCCESSFULLY. ---")

        # Double-check if Pyrogram client is indeed connected after its task completes
        if not bot.is_connected:
             main_logger.warning("Pyrogram client task completed, but bot.is_connected is FALSE. Startup may be incomplete.", exc_info=True);
             # This state might cause later errors when trying to send messages. Decide criticality.
             # For now, proceed, but it's a red flag.


    except Exception as e:
         # This catches exceptions raised by either db_init_task or bot_start_task during their execution.
         main_logger.critical(f"FATAL STARTUP FAILURE: One or more essential service tasks failed during startup: {e}", exc_info=True);
         print(f"CRITICAL PRINT: FATAL STARTUP FAILURE IN ASYNC TASK AWAIT: {e}");

         # Attempt to cancel the *other* task if it might still be running.
         # check if task is done, pending, or cancelled.
         if not db_init_task.done(): db_init_task.cancel(); main_logger.warning("Attempting to cancel DB init task.");
         if not bot_start_task.done(): bot_start_task.cancel(); main_logger.warning("Attempting to cancel Bot start task.");


         # Allow cancellation and already finished tasks to clear gracefully
         # Use return_exceptions=True for gather here just in case cancel/gather has issues
         try: await asyncio.gather(db_init_task, bot_start_task, return_exceptions=True);
         except Exception: pass # Ignore any exceptions during the final await cleanup

         # Essential services failed. The bot cannot run. Exit critically.
         sys.exit(1);


    # --- Substep 6.2: Post-Startup Actions ---
    # These actions run only if DB init and Bot start tasks completed without exception.
    main_logger.info("All critical services reported ready (Database & Pyrogram connection confirmed). Application core is live and Pyrogram client is polling.")
    print(f"DEBUG: --- Step 6.2: All Critical Services Reported Ready. Bot Worker Operational. ---")


    # Report bot startup to the log channel (if configured)
    # Use a new task for this so sending message doesn't block the main loop Future.
    # Check LOG_CHANNEL_ID validity and bot connection state again.
    if LOG_CHANNEL_ID is not None and bot.is_connected:
         main_logger.info(f"Configured LOG_CHANNEL_ID is {LOG_CHANNEL_ID} and bot is connected. Attempting to send startup notification.")
         asyncio.create_task(send_startup_notification(bot)) # Pass the Pyrogram client instance to the async helper task
         main_logger.info("Startup notification task scheduled.")
    elif LOG_CHANNEL_ID is None:
        main_logger.info("LOG_CHANNEL_ID is NOT set. Skipping startup notification.");
    else: # LOG_CHANNEL_ID is set, but bot is_connected is False after startup?
        main_logger.warning("LOG_CHANNEL_ID set, but bot.is_connected is FALSE after startup task. Skipping startup notification channel send.", exc_info=True);


    # --- Substep 6.3: Keep Event Loop Running ---
    main_logger.info("Application setup complete. Keeping asyncio event loop running indefinitely for Pyrogram tasks (polling updates, handling messages/callbacks).")
    print(f"DEBUG: --- Step 6.3: Entering Infinite Loop Await (asyncio.Future()). ---")
    # Awaiting a future that never completes is the standard way to keep asyncio loop running indefinitely
    # This awaits all currently scheduled tasks implicitly.
    await asyncio.Future()


# Helper task to send startup notification message to log channel
# This runs as a separate asyncio task.
async def send_startup_notification(client: Client):
     main_logger.debug("send_startup_notification task started.")
     try:
         # Optional: Add a small delay. Sometimes client reports connected slightly before fully ready for messages.
         # await asyncio.sleep(0.5) # Small delay example


         if not client.me: # Check if bot identity is available (usually after client.start())
             main_logger.warning("Client.me not available in notification task. Fetching self...")
             # Try to fetch bot identity using the client
             try:
                  bot_user = await client.get_me() # Use client passed into task
                  main_logger.debug(f"Fetched bot user: @{bot_user.username} (ID: {bot_user.id})");
             except Exception as e:
                  main_logger.error(f"Failed to fetch client.me in notification task: {e}", exc_info=True);
                  bot_username = "UnknownBotUsername" # Fallback names
                  bot_id = "UnknownBotId"
             else: # If fetching succeeded, use the fetched data
                   bot_username = bot_user.username
                   bot_id = bot_user.id
         else: # Client.me was already populated
              bot_username = client.me.username
              bot_id = client.me.id


         # Use config version and names
         from config import __version__
         # Build the startup message content
         startup_message = f"🤖 AnimeRealm Bot v{__version__} (Worker) started successfully!"
         startup_message += f"\n👤 Bot: @{bot_username} (ID: {bot_id})"
         startup_message += f"\n📚 Bot source commit/tag: {os.getenv('KOYEB_GIT_TAG', os.getenv('KOYEB_GIT_COMMIT_ID', 'N/A'))}" # Include commit hash from Koyeb ENV vars

         # Mention the health check endpoint, using assumed default port 8080
         HEALTH_CHECK_PORT_ASSUMED = 8080
         startup_message += f"\n🩺 Health check endpoint: 'health-server' process on port {HEALTH_CHECK_PORT_ASSUMED}/healthz"
         startup_message += f"\n\n⏳ Ready to process Telegram updates."


         # Final check of log channel ID and client connection before sending
         if LOG_CHANNEL_ID is None or not client.is_connected:
              main_logger.warning("Cannot send startup notification to log channel. LOG_CHANNEL_ID is None or client is not connected.")
              # Log the full message content if cannot send to channel
              main_logger.info(f"Startup message content: '{startup_message[:200]}...'")
              return # Cannot send


         # Send the message using the client
         main_logger.info(f"Attempting to send startup message to log channel {LOG_CHANNEL_ID}. Preview: '{startup_message[:100]}...'.");
         # Need to cast channel ID to int as environment variable gives string
         await client.send_message(int(LOG_CHANNEL_ID), startup_message, parse_mode=config.PARSE_MODE);
         main_logger.info(f"Startup notification successfully sent to log channel {LOG_CHANNEL_ID}.");


     except Exception as e:
          main_logger.critical(f"FATAL ERROR IN STARTUP NOTIFICATION TASK: An unexpected exception occurred: {e}", exc_info=True);
          # This task failing doesn't stop the bot, but log critical error.


# --- Step 7: Application Entry Point Execution (__main__ block) ---
# This block determines what happens when the script is executed directly.
if __name__ == "__main__":
    print("DEBUG: --- Step 7.1: __main__ block executed. ---")
    main_logger.info("Application initiation point (__main__ block) reached.")
    print("DEBUG: --- Step 7.2: Entering asyncio.run block to start the async main function. ---")

    try:
        # Use asyncio.run to execute the top-level async function run_app_async.
        # asyncio.run manages the event loop and schedules the initial tasks.
        asyncio.run(run_app_async());
        # This line is reached only if run_app_async completes without uncaught exceptions.
        # This is unlikely with an infinite await asyncio.Future().
        main_logger.info("asyncio.run(run_app_async()) completed without exceptions.")

    except KeyboardInterrupt:
         # Catch Ctrl+C signal for graceful shutdown on development environments.
         main_logger.info("Application received KeyboardInterrupt (Ctrl+C). Initiating graceful shutdown.");
         # asyncio.run usually handles task cancellation and loop closure here.


    except SystemExit as e:
         # Catch explicit SystemExit calls from inside the application (e.g., from FATAL sys.exit()).
         if e.code == 0: main_logger.info("Application exited cleanly via SystemExit (status code 0).");
         else: main_logger.critical(f"Application exited due to SystemExit with code {e.code}. Check logs for the specific FATAL message.", exc_info=True);

    except Exception as e:
         # Catch any uncaught exception that escapes the asyncio.run block (rare if errors handled within async).
         main_logger.critical(f"Application terminated due to uncaught exception outside asyncio execution: {e}", exc_info=True);

    finally:
         # Final block executed before the process finishes.
         print("DEBUG: --- Step 7.3: Exiting __main__ block. ---")
         main_logger.info("Application process is terminating.");


# Note on graceful shutdown for production:
# For production environments like Koyeb, which send SIGTERM to shut down instances,
# more robust shutdown handling is often required. This involves catching signals
# (like SIGTERM) and triggering the cancellation of the asyncio Future that keeps the loop alive.
# When asyncio.Future() is cancelled, run_until_complete (which asyncio.run() uses internally) finishes,
# allowing cleanup code to run. This is an advanced topic involving signal handlers,
# and interactions between Python's threading and the asyncio event loop.
# Basic template might involve: signal.signal(signal.SIGTERM, lambda *args: asyncio.get_event_loop().stop())
# and registering a cleanup coroutine before the final await asyncio.Future().
