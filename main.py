# main.py

# Use print() statements for absolute early stage logging before logging.basicConfig
# Check 1: Script execution started
print("DEBUG: --- Step 0.1: main.py script execution started. ---")

import asyncio
# Check 2: Initial imports start
print("DEBUG: --- Step 0.2: Starting essential imports (asyncio, logging, sys, os, dotenv, aiohttp). ---")
import logging
import sys
import os

from dotenv import load_dotenv

# Import for the aiohttp web server health check
from aiohttp import web

# Import database functions and config constants here, but log their usage below
# import config # Import config here to use its constants later
# from database.mongo_db import init_db, MongoDB # Import DB here to use later
# from database.models import User # Import Models


# --- Step 1: Configure Logging ---
# Check 3: Logging setup start
print("DEBUG: --- Step 1.1: Configuring logging. ---")
try:
    # Set up basic logging to stdout
    logging.basicConfig(
        level=logging.DEBUG, # Set initial level to DEBUG to capture everything early
        format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S', # Consistent timestamp
        handlers=[
            logging.StreamHandler(sys.stdout) # CRITICAL: Log to stdout for container logs
        ]
    )
    # Set specific log levels for noisy libraries AFTER the root config
    logging.getLogger("pyrogram").setLevel(logging.INFO) # Set pyrogram to INFO initially, less verbose than DEBUG
    logging.getLogger("pymongo").setLevel(logging.INFO) # Set pymongo to INFO
    logging.getLogger("aiohttp").setLevel(logging.INFO) # Set aiohttp client/server logs to INFO
    logging.getLogger("motor").setLevel(logging.INFO)   # Set motor logs to INFO


    main_logger = logging.getLogger(__name__) # Get main logger for this file
    main_logger.info("Logging configured successfully. Standard output stream enabled.")
    print("DEBUG: --- Step 1.2: Logging configured. Switching to configured logger. ---")

except Exception as e:
    # If logging itself fails, use print as fallback
    print(f"CRITICAL PRINT: FATAL: Failed to configure logging: {e}")
    print("CRITICAL PRINT: Cannot proceed without logging setup. Exiting.")
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
    print(f"CRITICAL PRINT: FATAL: Failed to load environment variables: {e}") # Fallback print
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
    # Validate essential environment variables immediately
    if not BOT_TOKEN: main_logger.critical("VALIDATION FAILED: BOT_TOKEN not set! Ensure variable exists on Koyeb."); sys.exit(1);
    main_logger.info("Validation OK: BOT_TOKEN is set.");

    if not API_ID or not API_HASH:
         main_logger.critical("VALIDATION FAILED: API_ID or API_HASH not set! Required for Pyrogram. Ensure both exist on Koyeb."); sys.exit(1);
    main_logger.info("Validation OK: API_ID and API_HASH are set.");

    if not MONGO_URI:
        main_logger.critical("VALIDATION FAILED: MONGO_URI not set! Database connection required. Ensure variable exists on Koyeb and connection string is valid."); sys.exit(1);
    main_logger.info("Validation OK: MONGO_URI is set.");

    main_logger.info("Critical ENV variables loaded and validated successfully.")

    # Load other crucial, but not strictly exit-on-fail here, configs with checks
    ADMIN_IDS_STR = os.getenv("ADMIN_IDS", ""); ADMIN_IDS = [];
    main_logger.info(f"Attempting to parse ADMIN_IDS: '{ADMIN_IDS_STR}'");
    if ADMIN_IDS_STR:
        try:
            ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()];
            if not ADMIN_IDS: main_logger.warning("ADMIN_IDS parsed empty.");
            else: main_logger.info(f"Parsed ADMIN_IDS: {ADMIN_IDS}");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid ADMIN_IDS format: {e}. Must be comma-separated integers."); sys.exit(1);
    else: main_logger.info("ADMIN_IDS not set.");

    OWNER_ID_STR = os.getenv("OWNER_ID"); OWNER_ID = None;
    main_logger.info(f"Attempting to parse OWNER_ID: '{OWNER_ID_STR}'");
    if OWNER_ID_STR:
        try: OWNER_ID = int(OWNER_ID_STR.strip()); main_logger.info(f"Parsed OWNER_ID: {OWNER_ID}");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid OWNER_ID format: {e}. Must be a single integer."); sys.exit(1);
        if OWNER_ID is not None and OWNER_ID not in ADMIN_IDS and ADMIN_IDS:
             main_logger.warning(f"OWNER_ID ({OWNER_ID}) is not in ADMIN_IDS. Owner might lack full admin privileges depending on handler checks.");
    else: main_logger.info("OWNER_ID not set.");


    LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID"); LOG_CHANNEL_ID = None;
    main_logger.info(f"Attempting to parse LOG_CHANNEL_ID: '{LOG_CHANNEL_ID_STR}'");
    if LOG_CHANNEL_ID_STR:
        try: LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR.strip()); main_logger.info(f"Parsed LOG_CHANNEL_ID: {LOG_CHANNEL_ID}");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid LOG_CHANNEL_ID: {e}. Must be an integer."); sys.exit(1);
    else: main_logger.info("LOG_CHANNEL_ID is not set. Admin logs will only appear in stdout/file.");

    FILE_STORAGE_CHANNEL_ID_STR = os.getenv("FILE_STORAGE_CHANNEL_ID"); FILE_STORAGE_CHANNEL_ID = None;
    main_logger.info(f"Attempting to parse FILE_STORAGE_CHANNEL_ID: '{FILE_STORAGE_CHANNEL_ID_STR}'");
    if FILE_STORAGE_CHANNEL_ID_STR:
        try: FILE_STORAGE_CHANNEL_ID = int(FILE_STORAGE_CHANNEL_ID_STR.strip()); main_logger.info(f"Parsed FILE_STORAGE_CHANNEL_ID: {FILE_STORAGE_CHANNEL_ID}. File handling ENABLED.");
        except ValueError as e: main_logger.critical(f"VALIDATION FAILED: Invalid FILE_STORAGE_CHANNEL_ID: {e}. Must be an integer."); sys.exit(1);
    else: main_logger.critical("VALIDATION FAILED: FILE_STORAGE_CHANNEL_ID NOT set. File handling features DISABLED."); sys.exit(1);


    main_logger.info("All critical configuration variables loaded and validated.")

except Exception as e:
     main_logger.critical(f"FATAL: An unexpected error occurred during configuration validation: {e}", exc_info=True)
     print(f"CRITICAL PRINT: FATAL error during configuration validation: {e}") # Fallback print
     sys.exit(1)

# Now that critical configs are validated, safely import config.py
# We use its values inside async main or by passing.
try:
    main_logger.info("Importing config.py for other constants.")
    import config # Use the 'config' module itself
    main_logger.info("config.py imported successfully.")
except Exception as e:
     main_logger.critical(f"FATAL: Failed to import config.py: {e}", exc_info=True)
     print(f"CRITICAL PRINT: FATAL: Failed to import config.py: {e}") # Fallback print
     sys.exit(1)


# --- Step 4: Pyrogram Client Initialization ---
main_logger.info("--- Step 4: Initializing Pyrogram Client ---")
try:
    main_logger.info(f"Pyrogram client configuration using API_ID='{API_ID}', API_HASH='{API_HASH[:4]}...'...")
    # Pyrogram session files will be created in the configured workdir "." which is /app in Docker
    bot = Client(
        name="anime_realm_bot",
        api_id=int(API_ID),
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=dict(root="handlers"), # Pyrogram will look for handlers/__init__.py
        workdir=".", # Session files go here
        parse_mode=config.PARSE_MODE # Use configured parse mode
    )
    main_logger.info("Pyrogram client instance created successfully.")
    main_logger.info("Client name: '%s', Workdir: '%s'", bot.name, bot.workdir)

except (ApiIdInvalid, ApiIdPublishedFlood): main_logger.critical("FATAL PYROGRAM INIT FAILED: API_ID/API_HASH invalid or public.", exc_info=True); sys.exit(1);
except AuthKeyUnregistered: main_logger.critical("FATAL PYROGRAM INIT FAILED: Session key invalid. Delete session file.", exc_info=True); sys.exit(1);
except Exception as e: main_logger.critical(f"FATAL PYROGRAM INIT FAILED: Unexpected error: {e}", exc_info=True); sys.exit(1);


# --- Step 5: Database Initialization ---
# This function is called within the async main task.
async def init_database():
    main_logger.info("--- Step 5: Database Initialization Started ---")
    try:
        main_logger.debug("Importing init_db and DB_NAME from database.mongo_db.")
        from database.mongo_db import init_db # init_db connects and indexes
        from database.mongo_db import DB_NAME as DB_NAME_CONST # Get DB_NAME from DB module/config

        # MONGO_URI is already loaded and validated

        main_logger.info(f"Initiating MongoDB initialization process. Calling init_db with MONGO_URI (redacted) and DB_NAME='{DB_NAME_CONST}'.")
        await init_db(MONGO_URI)
        main_logger.info("Database initialization completed successfully.")
        print("DEBUG: --- Step 5.1: Database Initialization Reported Success. ---")

    except ConnectionFailure as e:
        main_logger.critical(f"FATAL DB INIT FAILED: Could not connect to or initialize database. ConnectionFailure: {e}", exc_info=True);
        print(f"CRITICAL PRINT: FATAL DB INIT FAILED (ConnectionFailure): {e}");
        sys.exit(1); # Exit critically
    except OperationFailure as e:
         main_logger.critical(f"FATAL DB INIT FAILED: Database operation error during initialization. OperationFailure: {e}", exc_info=True);
         print(f"CRITICAL PRINT: FATAL DB INIT FAILED (OperationFailure): {e}");
         sys.exit(1);
    except Exception as e:
         main_logger.critical(f"FATAL DB INIT FAILED: An unexpected error occurred during database initialization: {e}", exc_info=True);
         print(f"CRITICAL PRINT: FATAL DB INIT FAILED (Unexpected): {e}");
         sys.exit(1);


# --- Step 6: Health Check Web Server Setup ---

# Simple async handler for the health check endpoint
async def healthz_handler(request):
    main_logger.debug("Received health check request on /healthz.");
    # Optional: Add checks for DB and Telegram connection here for more robust health indication
    db_connected = False # Placeholder
    tg_connected = False # Placeholder
    try:
         from database.mongo_db import MongoDB # Access MongoDB connection status if available
         if MongoDB._client and MongoDB._client.topology_description.has_known_members: # Basic check
              db_connected = True
              main_logger.debug("Health check: MongoDB connection is up.")
         else: main_logger.debug("Health check: MongoDB connection not ready/failed.")
    except Exception: main_logger.debug("Health check: Could not check MongoDB status."); pass # Ignore import or access errors

    try:
         if bot.is_connected: # Check Pyrogram client's internal connection status
              tg_connected = True
              main_logger.debug("Health check: Pyrogram client is connected to Telegram.")
         else: main_logger.debug("Health check: Pyrogram client not connected to Telegram.");
    except Exception: main_logger.debug("Health check: Could not check Pyrogram status."); pass # Ignore access errors


    # Respond with OK (200) if basic process is running and listener is up.
    # More robust: Check if BOTH db_connected and tg_connected are True? Or at least one?
    # For Koyeb basic check, usually just needs the listener to be alive.
    if db_connected and tg_connected:
         main_logger.debug("Health check returning 200 OK (DB & TG connected).")
         return web.Response(text="ok", status=200)
    elif db_connected or tg_connected:
        # Optionally indicate partial health? Or just respond 200 if main server task is running.
         main_logger.debug("Health check returning 200 OK (at least DB or TG connected).")
         return web.Response(text="ok", status=200) # Still consider healthy enough? Depends on requirements. Let's use this criteria.
    else:
        main_logger.debug("Health check returning 503 Service Unavailable (Neither DB nor TG connected).")
        return web.Response(text="Service Unavailable", status=503) # Indicate unhealthy


# Async function to set up and start the aiohttp web server
async def start_health_server(port: int):
    main_logger.info(f"Attempting to set up health check web server on 0.0.0.0:{port}...")
    app = web.Application() # Create a web application instance
    app.router.add_get('/healthz', healthz_handler) # Add route for /healthz

    runner = web.AppRunner(app) # Create an AppRunner to manage the application lifecycle
    try:
        main_logger.debug("Setting up AppRunner...")
        await runner.setup() # Set up runner with application handlers and loop
        main_logger.debug("AppRunner setup complete. Creating TCP site.")
        site = web.TCPSite(runner, '0.0.0.0', port) # Create TCP site binding to port on all interfaces

        main_logger.info("Starting TCP site listener...")
        await site.start() # Start the listener. This operation does NOT block indefinitely.
        main_logger.info(f"Health check server listener successfully started on 0.0.0.0:{port}. Path: /healthz. Ready for requests.")
        print(f"DEBUG: --- Step 6.1: Health check server STARTED LISTENING on port {port}. ---") # Debug print confirm listener

        # The site.start() starts background tasks (listener). We need the event loop to keep running.
        # Awaiting this function in main() needs it to somehow represent continuous running.
        # It's a task in main(). Its mere existence and event loop running is sufficient.


    except OSError as e:
         main_logger.critical(f"FATAL HEALTH CHECK SERVER FAILED TO START: Could not bind to port {port}. Is another process using it? {e}", exc_info=True);
         print(f"CRITICAL PRINT: FATAL HEALTH CHECK SERVER BIND FAILED on port {port}: {e}"); # Fallback print
         sys.exit(1); # Exit critically
    except Exception as e:
         main_logger.critical(f"FATAL HEALTH CHECK SERVER FAILED TO START: An unexpected error occurred during setup: {e}", exc_info=True);
         print(f"CRITICAL PRINT: FATAL HEALTH CHECK SERVER SETUP FAILED: {e}"); # Fallback print
         sys.exit(1);


# --- Step 7: Main Application Tasks Execution ---
# This is the main async function run by asyncio.run
async def main():
    main_logger.info("--- Step 7: Main Application async Execution Started ---")

    # Define the port for the health check server (Koyeb default is 8080)
    HEALTH_CHECK_PORT = 8080 # Can load from config/env if defined there

    # Create asyncio tasks for the Pyrogram bot and the health check server.
    # Use asyncio.create_task to schedule them to run concurrently.
    main_logger.info("Creating concurrent tasks: Pyrogram bot start and Health check server start.")
    bot_task = asyncio.create_task(bot.start())
    main_logger.info("Pyrogram bot task scheduled.")

    health_task = asyncio.create_task(start_health_server(HEALTH_CHECK_PORT))
    main_logger.info(f"Health check server task scheduled for port {HEALTH_CHECK_PORT}.");

    main_logger.info("Both core application tasks are scheduled in the event loop.")


    # --- Substep 7.1: Initiate Database Connection (Concurrent with Bot Start) ---
    # It's efficient to start DB connection *after* client instance creation but *before* awaiting client.start(),
    # as client.start() does more than just connect (starts polling).
    # Place the DB init task creation here as well. It can run in parallel.
    db_init_task = asyncio.create_task(init_database()) # This task handles DB connect/indexing. It will exit if fails.
    main_logger.info("Database initialization task scheduled concurrently.")

    # --- Substep 7.2: Wait for Critical Services to Report Ready ---
    # The bot must be connected to Telegram to receive/send updates.
    # The database must be initialized for most bot functions.
    # The health check server must be listening for Koyeb to report healthy.

    main_logger.info("Awaiting essential services startup (Database & Pyrogram connection)...")
    # Await both db_init_task and bot_task. If either fails (raises exception), asyncio.gather will report it.
    # We need to wait for *completion* (success or fail) to know if they are 'ready'.
    # Use asyncio.shield to prevent cancellation if main loop gets cancelled? Unlikely for startup.
    # Use asyncio.gather to wait for multiple tasks. return_exceptions=True means gather won't stop on first task error.

    # Let's first await bot task specifically, as it has specific exceptions caught earlier.
    # Then ensure db task also finished.
    try:
         # Await the bot task completion (it runs bot.start() internally)
         # This means Pyrogram's initial connection setup has finished, and it's *trying* to poll.
         main_logger.info("Awaiting Pyrogram client task to report initial readiness.")
         await bot_task
         main_logger.info("Pyrogram client task completed successfully (client.start() done). Client status: is_connected=%s", bot.is_connected);

         # Ensure database init task also finished successfully
         main_logger.info("Awaiting database initialization task completion.")
         await db_init_task # This will raise if init_database failed.
         main_logger.info("Database initialization task completed successfully.")

         # Health task is also running. Awaiting it here would block, not what we want.


    except Exception as e:
         # Catch exceptions from *either* bot_task or db_init_task failure
         main_logger.critical(f"FATAL STARTUP FAILURE: Essential service task failed: {e}", exc_info=True);

         # Attempt to cancel the other running tasks before exiting.
         # Check if task is still pending before cancelling.
         if not bot_task.done(): bot_task.cancel();
         if not db_init_task.done(): db_init_task.cancel();
         if not health_task.done(): health_task.cancel();
         main_logger.warning("Cancelled other startup tasks due to failure.")

         # Allow cancelled tasks to finish cancelling
         try: await asyncio.gather(bot_task, db_init_task, health_task, return_exceptions=True);
         except Exception: pass # Ignore exceptions during final awaited gather

         sys.exit(1); # Exit critically

    # --- Substep 7.3: Post-Startup Actions ---
    main_logger.info("All critical services are reported ready (Database & Pyrogram connection confirmed, Health check listener should be active).")
    print(f"DEBUG: --- Step 7.3: All Critical Services Reported Ready. Bot Should Be Live. ---")


    # Report bot startup to the log channel (if configured)
    # Use a new task for this so it doesn't block the main loop startup flow.
    # But it should only happen AFTER the client reports connected (which awaiting bot_task achieves).
    if LOG_CHANNEL_ID and bot.is_connected:
         main_logger.info(f"Configured LOG_CHANNEL_ID is {LOG_CHANNEL_ID} and bot is connected. Attempting to send startup notification.")
         asyncio.create_task(send_startup_notification(client)) # Client is the global 'bot' instance
    else:
        if LOG_CHANNEL_ID: main_logger.warning("LOG_CHANNEL_ID set but bot.is_connected is FALSE. Skipping startup notification to channel.");
        else: main_logger.info("LOG_CHANNEL_ID is NOT set. Skipping startup notification.");


    # --- Substep 7.4: Keep Event Loop Running ---
    main_logger.info("Application setup complete. Keeping asyncio event loop running indefinitely for all scheduled tasks (Bot, Health Server, etc.).")
    print(f"DEBUG: --- Step 7.4: Entering Infinite Loop Await. ---")
    # Keep the bot and health server tasks running by awaiting a future that never completes.
    await asyncio.Future() # This line will block the main function indefinitely.


# Helper task to send startup notification message to log channel
async def send_startup_notification(client: Client):
     try:
         # Add a short delay? Sometimes connection is ready, but not fully authenticated for sending immediately?
         # asyncio.sleep(1) # Optional small delay

         main_logger.debug(f"Executing send_startup_notification task for client {client.me.id if client.me else 'N/A'}.")
         from config import __version__ as app_version # Import version again if not global


         bot_user = await client.get_me()
         startup_message = f"🤖 AnimeRealm Bot v{app_version} started successfully!"
         startup_message += f"\n👤 Bot Username: @{bot_user.username}"
         # Retrieve HEALTH_CHECK_PORT value. Access config module directly.
         HEALTH_CHECK_PORT_ACCESS = 8080 # Assume default or use a method to get it
         # Can't easily get port from health_task/site without exposing runner. Use assumed/config value.
         startup_message += f"\n🌐 Health check live on port {HEALTH_CHECK_PORT_ACCESS}/healthz"


         # Ensure LOG_CHANNEL_ID is valid int from main() scope or re-fetch.
         main_logger.debug(f"Sending startup message to LOG_CHANNEL_ID: {LOG_CHANNEL_ID}.")
         await client.send_message(LOG_CHANNEL_ID, startup_message, parse_mode=config.PARSE_MODE);
         main_logger.info(f"Startup notification successfully sent to log channel {LOG_CHANNEL_ID}.");


     except Exception as e:
          main_logger.critical(f"FATAL ERROR IN STARTUP NOTIFICATION TASK: Failed to send startup message to log channel {LOG_CHANNEL_ID}: {e}", exc_info=True);
          # This task finishing does not stop the application, just logs the failure.


# --- Step 8: Application Entry Point Execution (If script run directly) ---
if __name__ == "__main__":
    print("DEBUG: --- Step 8.1: __main__ block executed. ---")
    # Get app version from config before starting
    try:
         # Check if config has version, fallback if not
         if not hasattr(config, '__version__'):
             class AppConfig: __version__ = "N/A_ConfigMissing" # Define temp config if import failed
             app_version_final = AppConfig.__version__
         else:
             app_version_final = config.__version__
         print(f"DEBUG: Application version for logging: {app_version_final}")
    except Exception: print("DEBUG: Failed to determine app version for initial print.");

    main_logger.info("Application initiation point reached.")
    print("DEBUG: --- Step 8.2: Entering asyncio.run block. ---")

    try:
        # Run the main asynchronous function 'main'. This blocks until 'main' finishes.
        asyncio.run(main());
        main_logger.info("asyncio.run(main()) completed without exceptions.")

    except KeyboardInterrupt:
         main_logger.info("Application received KeyboardInterrupt. Initiating shutdown.");
         # asyncio.run() handles cancellation of tasks and loop close on Ctrl+C

    except SystemExit as e:
         # Catch SystemExit exceptions from within main or sub-functions.
         # This happens when sys.exit() is called intentionally (e.g., on config validation failure).
         if e.code == 0: main_logger.info("Application exited cleanly (status code 0).");
         else: main_logger.critical(f"Application exited due to SystemExit with code {e.code}. Check logs for cause.", exc_info=True);

    except Exception as e:
         # Catch any unexpected exception that propagates out of asyncio.run.
         main_logger.critical(f"Application terminated due to unhandled exception outside async execution: {e}", exc_info=True);


    finally:
         print("DEBUG: --- Step 8.3: Exiting __main__ block. ---")
         main_logger.info("Application process is terminating.");

# Note: Graceful shutdown (e.g., closing DB connection when SIGTERM received)
# requires more advanced signal handling setup using asyncio loop methods,
# which are complex to set up correctly within the __main__ block and across libraries.
# For production, ensure the process terminates cleanly on SIGTERM (Koyeb sends this).
# Pyrogram/Motor *might* handle this to some degree if allowed time before forced kill.
