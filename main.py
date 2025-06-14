# main.py

# Use print() statements for absolute early stage logging before logging.basicConfig
# Check 1: Script execution started
print("DEBUG: --- Step 0.1: main.py script execution started. ---")

import asyncio
print("DEBUG: --- Step 0.2: Starting essential imports (asyncio, logging, sys, os, dotenv). ---")
import logging
import sys
import os

# --- No imports related to Flask, gunicorn, or aiohttp for health check server here ---
# Health check server runs in a separate process defined by Procfile using app.py.


# Imports needed for environment variables and Pyrogram client
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode


# Import modules needed within async context later
# Import config and database modules here (sync imports are fine early)
try:
    print("DEBUG: --- Step 0.3: Importing config and database modules (sync). ---")
    import config
    from database.mongo_db import init_db, MongoDB
    from database.models import User # Example model import if needed early (or import within handlers)
    print("DEBUG: --- Step 0.4: Config and DB modules imported successfully. ---")
except Exception as e:
    print(f"CRITICAL PRINT: FATAL: Failed to import config or database modules early: {e}")
    sys.exit(1) # Exit critically if essential modules fail to import


# --- Step 1: Configure Logging ---
print("DEBUG: --- Step 1.1: Configuring logging. ---")
try:
    logging.basicConfig(
        level=logging.DEBUG, # Keep DEBUG level for detailed startup logs on Koyeb
        format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout) # CRITICAL: Log to stdout for container logs
        ]
    )
    # Set specific log levels for noisy libraries AFTER the root config
    logging.getLogger("pyrogram").setLevel(logging.INFO) # Set pyrogram to INFO initially
    logging.getLogger("pymongo").setLevel(logging.INFO) # Set pymongo to INFO
    logging.getLogger("motor").setLevel(logging.INFO)   # Set motor logs to INFO
    # If aiohttp is used ELSEWHERE (not for health check server), silence its logs if needed:
    logging.getLogger("aiohttp").setLevel(logging.WARNING) # Keep at warning if it's used elsewhere


    main_logger = logging.getLogger(__name__) # Get main logger for this file
    main_logger.info("Logging configured successfully. Standard output stream enabled.")
    print("DEBUG: --- Step 1.2: Logging configured. Switching to configured logger. ---")

except Exception as e:
    # If logging itself fails, use print as fallback
    print(f"CRITICAL PRINT: FATAL: Failed to configure logging: {e}")
    sys.exit(1)


# Check 4: Environment variable loading start (Using main_logger now)
main_logger.info("--- Step 2: Loading Environment Variables ---")
try:
    main_logger.debug("Calling load_dotenv().")
    load_dotenv()
    main_logger.debug("load_dotenv() completed.")
    main_logger.info("Environment variables loaded from .env (if file exists).")
except Exception as e:
    main_logger.critical(f"FATAL: Failed to load environment variables from .env file: {e}", exc_info=True)
    sys.exit(1)


# --- Step 3: Configuration & Validation ---
main_logger.info("--- Step 3: Loading and Validating Configuration ---")
try:
    main_logger.debug("Retrieving critical ENV variables using os.getenv.")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    MONGO_URI = os.getenv("MONGO_URI")

    main_logger.info("Validating critical ENV variables.")
    if not BOT_TOKEN: main_logger.critical("VALIDATION FAILED: BOT_TOKEN not set! Ensure variable exists."); sys.exit(1);
    main_logger.info("Validation OK: BOT_TOKEN is set.");

    if not API_ID or not API_HASH:
         main_logger.critical("VALIDATION FAILED: API_ID or API_HASH not set! Required for Pyrogram."); sys.exit(1);
    main_logger.info("Validation OK: API_ID and API_HASH are set.");

    if not MONGO_URI:
        main_logger.critical("VALIDATION FAILED: MONGO_URI not set! Database connection required."); sys.exit(1);
    main_logger.info("Validation OK: MONGO_URI is set.");

    main_logger.info("Critical ENV variables loaded and validated successfully.")

    # --- Load Other Configs (can access config module directly now) ---
    ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "");
    try: ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()]; main_logger.debug(f"Parsed ADMIN_IDS from ENV.");
    except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid ADMIN_IDS format: {e}."); sys.exit(1);

    OWNER_ID_STR = os.getenv("OWNER_ID");
    try: OWNER_ID = int(OWNER_ID_STR.strip()); main_logger.debug(f"Parsed OWNER_ID from ENV.");
    except (ValueError, TypeError) as e: OWNER_ID = None; main_logger.warning(f"OWNER_ID not set or invalid: {OWNER_ID_STR}. Error: {e}. Owner-only commands disabled.");

    # Cross-check OWNER_ID against ADMIN_IDS (log warning only)
    if OWNER_ID is not None and OWNER_ID not in ADMIN_IDS:
        # Log warning if OWNER_ID is set but not in ADMIN_IDS list parsed from ENV
        # Also handle case where ADMIN_IDS_STR was set but parsed to empty list
         if ADMIN_IDS_STR and not ADMIN_IDS: main_logger.warning("OWNER_ID set but ADMIN_IDS parsed empty list.");
         else: main_logger.warning(f"OWNER_ID ({OWNER_ID}) set but NOT IN ADMIN_IDS list ({ADMIN_IDS}). Owner might lack admin privileges.");


    LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID");
    try: LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR.strip()); main_logger.debug(f"Parsed LOG_CHANNEL_ID from ENV.");
    except (ValueError, TypeError) as e: LOG_CHANNEL_ID = None; main_logger.info("LOG_CHANNEL_ID not set or invalid. Admin logs to stdout only.");

    FILE_STORAGE_CHANNEL_ID_STR = os.getenv("FILE_STORAGE_CHANNEL_ID");
    try: FILE_STORAGE_CHANNEL_ID = int(FILE_STORAGE_CHANNEL_ID_STR.strip()); main_logger.debug(f"Parsed FILE_STORAGE_CHANNEL_ID from ENV.");
    except (ValueError, TypeError) as e: main_logger.critical(f"VALIDATION FAILED: FILE_STORAGE_CHANNEL_ID NOT set or invalid. File handling DISABLED."); sys.exit(1);

    main_logger.info("All critical configuration variables loaded and validated.")
    print("DEBUG: --- Step 3.1: Configuration validated. ---")

except Exception as e:
     main_logger.critical(f"FATAL: An unexpected error occurred during configuration validation: {e}", exc_info=True)
     print(f"CRITICAL PRINT: FATAL error during configuration validation: {e}")
     sys.exit(1)

# At this point, config.py and DB modules are imported successfully.
# Critical environment variables are validated and sys.exit(1) on failure would have stopped the script.

# --- Step 4: Pyrogram Client Initialization ---
main_logger.info("--- Step 4: Initializing Pyrogram Client ---")
try:
    main_logger.info(f"Pyrogram client configuration using API_ID='{API_ID}', API_HASH='{API_HASH[:4]}...', BOT_TOKEN is set.");
    main_logger.info("Configuring plugins from root 'handlers', workdir '.'");
    bot = Client(
        name="anime_realm_bot",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=dict(root="handlers"),
        workdir=".",
        parse_mode=config.PARSE_MODE
    )
    main_logger.info("Pyrogram client instance created successfully. Client object available as 'bot'.")
    main_logger.info("Client name: '%s', Workdir: '%s'", bot.name, bot.workdir)
    print("DEBUG: --- Step 4.1: Pyrogram Client instance created. ---")

except (ApiIdInvalid, ApiIdPublishedFlood): main_logger.critical("FATAL PYROGRAM INIT FAILED: API_ID/API_HASH invalid or public.", exc_info=True); sys.exit(1);
except AuthKeyUnregistered: main_logger.critical("FATAL PYROGRAM INIT FAILED: Session key invalid. Delete session file (/app/anime_realm_bot.session).", exc_info=True); sys.exit(1);
except Exception as e: main_logger.critical(f"FATAL PYROGRAM INIT FAILED: Unexpected error: {e}", exc_info=True); sys.exit(1);


# --- Step 5: Database Initialization (Async function called within async main) ---
# This is an async function and will be awaited within the main async execution block (run_app_async).
async def init_database_async():
    main_logger.info("--- Step 5: Async Database Initialization Started ---")
    try:
        # Use the validated MONGO_URI and config.DB_NAME
        main_logger.info(f"Calling database.mongo_db.init_db to connect and index for DB '{config.DB_NAME}'. MONGO_URI (redacted).");
        await init_db(MONGO_URI) # init_db handles connection and indexing. It raises exceptions on failure.
        main_logger.info("Database initialization completed successfully (connection established, indexing done).")
        print("DEBUG: --- Step 5.1: Async Database Initialization AWAIT Reported Success. ---")

    except Exception as e:
         # Catch any error from init_db (includes connection/operation failures and general exceptions)
         main_logger.critical(f"FATAL DB INIT FAILED IN ASYNC: An error occurred during database initialization: {e}", exc_info=True);
         # Propagate the exception to the caller task (run_app_async).
         raise # Re-raise the exception


# --- Step 6: Async Application Main Function ---
# This is the main async function that orchestrates the core tasks.
async def run_app_async():
    main_logger.info("--- Step 6: Main async Application Tasks Execution Started ---")
    print("DEBUG: --- Step 6.0: Inside run_app_async. ---")

    main_logger.info("Creating concurrent tasks: Database Initialization and Pyrogram Bot Start.")

    # 6.1: Database Initialization Task
    # Create the task for DB initialization. It will run in parallel.
    main_logger.debug("About to create DB init task.")
    db_init_task = asyncio.create_task(init_database_async())
    print("DEBUG: --- Step 6.0.1: DB init task created. ---")
    main_logger.info("Database initialization task scheduled.")

    # 6.2: Pyrogram Bot Start Task
    # Create the task for starting the Pyrogram client.
    main_logger.debug("About to create Pyrogram bot start task.")
    bot_start_task = asyncio.create_task(bot.start()) # Client object 'bot' is available from Step 4.
    print("DEBUG: --- Step 6.0.2: Pyrogram bot start task created. ---")
    main_logger.info("Pyrogram bot start task scheduled.")

    main_logger.info("Both core tasks are scheduled. Preparing to await their completion.")
    print("DEBUG: --- Step 6.0.3: About to await DB init and Bot start tasks. ---")


    # --- Substep 6.1: Wait for Critical Services to Report Ready ---
    # Wait for both db_init_task and bot_start_task. Essential for bot functionality.
    try:
         main_logger.info("Awaiting completion of essential tasks: db_init_task and bot_start_task.")
         # Await both tasks. If any task fails (raises exception), asyncio.gather will propagate the *first* exception raised.
         # No return_exceptions=True here as failure of either is fatal.
         await asyncio.gather(db_init_task, bot_start_task)
         main_logger.info("Both Database initialization and Pyrogram bot start tasks completed successfully.")
         print("DEBUG: --- Step 6.1: DB init task and Bot start task AWAITED SUCCESSFULLY. ---")

         # Double-check connection status after startup tasks complete (extra safety)
         if not bot.is_connected:
              # This indicates a problem even though the task finished without raising directly.
              main_logger.critical("FATAL STARTUP ISSUE: Pyrogram client start task completed, but bot.is_connected is FALSE. Bot is not truly connected/polling.", exc_info=True);
              print("CRITICAL PRINT: FATAL STARTUP ISSUE: bot.is_connected is FALSE after start task completion.");
              # Decide criticality. Usually means polling failed internally.
              sys.exit(1); # Exit critically

         main_logger.info("Pyrogram client connection confirmed after start task completion.")


    except Exception as e:
         # This catches exceptions raised by *either* db_init_task or bot_start_task during their execution or during the await gather.
         main_logger.critical(f"FATAL STARTUP FAILURE: One or more essential service tasks failed during startup await: {e}", exc_info=True);
         print(f"CRITICAL PRINT: FATAL STARTUP FAILURE DURING TASK AWAIT: {e}"); # Fallback print

         # Attempt to cancel any pending task (though both should be done/failed by now if gather returned)
         if not db_init_task.done(): db_init_task.cancel(); main_logger.warning("Cancelling DB init task.");
         if not bot_start_task.done(): bot_start_task.cancel(); main_logger.warning("Cancelling Bot start task.");

         # Allow cancellation and already done tasks to clear gracefully before exiting
         try: await asyncio.gather(db_init_task, bot_start_task, return_exceptions=True); # Use return_exceptions just for this final await clean
         except Exception: pass # Ignore exceptions during final cleanup await


         sys.exit(1); # Exit critically as essential services failed


    # Note: The Flask/Gunicorn health-server is a separate process defined in Procfile and
    # runs independently of this 'worker' process's async loop.
    # This 'worker' process does NOT start or await the health-server process task here.
    # The health check depends on Koyeb successfully running the 'health-server' process.


    # --- Substep 6.2: Post-Startup Actions ---
    # These actions run only if the await gather completed successfully.
    main_logger.info("Application setup complete. All critical services are ready (Database init & Pyrogram connection confirmed). Application core is live and Pyrogram client is polling.")
    print("DEBUG: --- Step 6.2: Post-startup actions start. ---")

    # Report bot startup to the log channel (if configured and bot is connected)
    # This is a non-blocking task and should not cause main execution to hang.
    if LOG_CHANNEL_ID is not None and bot.is_connected:
         main_logger.info(f"Configured LOG_CHANNEL_ID is {LOG_CHANNEL_ID}. Scheduling startup notification task.")
         asyncio.create_task(send_startup_notification(bot)) # Pass the client instance
         main_logger.info("Startup notification task scheduled.")
    elif LOG_CHANNEL_ID is None:
        main_logger.info("LOG_CHANNEL_ID is NOT set. Skipping startup notification to channel.");
    # else: Log if client is not connected already happens in await task error section

    main_logger.info("All necessary startup procedures finished.")
    main_logger.info("Entering infinite loop to keep this worker process's asyncio event loop running for Pyrogram updates.")
    print("DEBUG: --- Step 6.3: Entering Infinite Loop Await (asyncio.Future()). ---")
    # Awaiting a future that never completes keeps the event loop running indefinitely
    # This prevents the 'main_async_tasks' function from finishing and the script from exiting.
    await asyncio.Future() # This line effectively blocks here


# Helper task to send startup notification message to log channel
# This runs as a separate asyncio task. It does not impact main execution flow.
async def send_startup_notification(client: Client):
     main_logger.debug("send_startup_notification task started.");
     try:
         # Optional small delay. Give Telegram servers a moment after initial connect reports done.
         await asyncio.sleep(0.2);

         # Check if client is still connected right before sending.
         if not client.is_connected:
              main_logger.warning(f"Client not connected in send_startup_notification task for channel {LOG_CHANNEL_ID}. Skipping send.");
              # This task simply finishes without error if not connected.
              return


         # Get bot identity using the client instance
         if client.me is None: # .me should be populated after start(), but defensive check
             main_logger.warning("Client.me is None in notification task. Attempting client.get_me().")
             try: bot_user = await client.get_me(); main_logger.debug(f"Fetched bot user for notification: @{bot_user.username} (ID: {bot_user.id})");
             except Exception as e: main_logger.error(f"Failed to fetch client.me in notification task: {e}", exc_info=True); bot_username = "UnknownBotUsername"; bot_id = "UnknownBotId";
             else: bot_username = bot_user.username; bot_id = bot_user.id;
         else: bot_username = client.me.username; bot_id = client.me.id; # Use client.me directly


         from config import __version__ # Import version from config
         startup_message = f"🤖 AnimeRealm Bot v{__version__} (Worker) started successfully!"
         startup_message += f"\n👤 Bot: @{bot_username} (ID: {bot_id})"
         startup_message += f"\n📚 Source commit/tag: {os.getenv('KOYEB_GIT_TAG', os.getenv('KOYEB_GIT_COMMIT_ID', 'N/A'))}" # Include commit hash from Koyeb ENV vars


         # Include expected health check info, assume default port 8080
         HEALTH_CHECK_PORT_ASSUMED = 8080
         startup_message += f"\n🩺 Health check endpoint expected on 'health-server' process on port {HEALTH_CHECK_PORT_ASSUMED}/healthz"

         startup_message += f"\n\n⏳ Ready to process Telegram updates."

         # Final check of log channel ID before sending. Should be non-None from main's check.
         if LOG_CHANNEL_ID is None: main_logger.warning("LOG_CHANNEL_ID is None. Cannot send startup notification message content: %s", startup_message[:200]); return; # Safety return


         main_logger.info(f"Attempting to send startup message to log channel {LOG_CHANNEL_ID}. Preview: '{startup_message[:100]}...'.");
         await client.send_message(int(LOG_CHANNEL_ID), startup_message, parse_mode=config.PARSE_MODE);
         main_logger.info(f"Startup notification successfully sent to log channel {int(LOG_CHANNEL_ID)}.");


     except Exception as e:
          # Log any error during message sending in this task (e.g., network issues, Telegram errors).
          main_logger.critical(f"FATAL ERROR IN STARTUP NOTIFICATION TASK: An unexpected exception occurred during message sending: {e}", exc_info=True);
          # Task completes. Main bot process is unaffected.


# --- Step 7: Application Entry Point Execution (__main__ block) ---
# This block defines what runs when the main.py script is executed.
if __name__ == "__main__":
    print("DEBUG: --- Step 7.1: __main__ block executed. ---")
    main_logger.info("Application initiation point reached (__main__ block).")
    print("DEBUG: --- Step 7.2: Entering asyncio.run block to start the async main function. ---")

    try:
        # asyncio.run is the main entry point for running the async application.
        # It starts the asyncio event loop and runs the specified async function (run_app_async) until it completes.
        # With 'await asyncio.Future()' in run_app_async, the loop runs indefinitely.
        asyncio.run(run_app_async());
        # This line should not be reached in normal operation unless the script receives SIGINT/SIGTERM.
        main_logger.info("asyncio.run(run_app_async()) completed without uncaught exceptions.");

    except KeyboardInterrupt:
         # Handle Ctrl+C on local dev
         main_logger.info("Application received KeyboardInterrupt. Shutting down gracefully.");

    except SystemExit as e:
         # Catch sys.exit() calls.
         if e.code == 0: main_logger.info("Application exited cleanly via SystemExit (status code 0).");
         else: main_logger.critical(f"Application exited due to SystemExit with non-zero code {e.code}. Check logs for the specific FATAL message.", exc_info=True);

    except Exception as e:
         # Catch any unexpected exceptions that escape the asyncio.run context.
         # This would indicate a major issue outside of structured error handling.
         main_logger.critical(f"Application terminated due to uncaught exception outside async execution: {e}", exc_info=True);

    finally:
         print("DEBUG: --- Step 7.3: Exiting __main__ block. ---")
         main_logger.info("Application process is terminating.");
