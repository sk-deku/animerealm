# main.py

# Use print() statements for absolute early stage logging
print("DEBUG: --- Step 0.1: main.py script execution started. ---")

import asyncio
print("DEBUG: --- Step 0.2: Starting essential imports (asyncio, logging, sys, os, dotenv, aiohttp). ---")
import logging
import sys
import os

# Imports needed for environment variables and Pyrogram client
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid, ApiIdPublishedFlood, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.enums import ParseMode

# Import modules for integrated aiohttp web server health check
from aiohttp import web
from aiohttp.web import TCPSite, AppRunner, Application # Explicit imports for clarity


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
    sys.exit(1)


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
    logging.getLogger("aiohttp.web").setLevel(logging.INFO) # Set aiohttp web logs to INFO
    logging.getLogger("aiohttp.access").setLevel(logging.INFO) # Log incoming HTTP requests


    main_logger = logging.getLogger(__name__) # Get main logger for this file
    main_logger.info("Logging configured successfully. Standard output stream enabled.")
    print("DEBUG: --- Step 1.2: Logging configured. Switching to configured logger. ---")

except Exception as e:
    # If logging itself fails, use print as fallback
    print(f"CRITICAL PRINT: FATAL: Failed to configure logging: {e}")
    print("CRITICAL PRINT: Cannot proceed without logging setup. Exiting.")
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

    if OWNER_ID is not None and OWNER_ID not in ADMIN_IDS:
         if ADMIN_IDS_STR and not ADMIN_IDS: main_logger.warning("OWNER_ID set but ADMIN_IDS parsed empty list.");
         else: main_logger.warning(f"OWNER_ID ({OWNER_ID}) set but NOT IN ADMIN_IDS list ({ADMIN_IDS}). Owner might lack admin privileges.");


    LOG_CHANNEL_ID_STR = os.getenv("LOG_CHANNEL_ID");
    try: LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_STR.strip()); main_logger.debug(f"Parsed LOG_CHANNEL_ID from ENV.");
    except (ValueError, TypeError) as e: LOG_CHANNEL_ID = None; main_logger.info("LOG_CHANNEL_ID not set or invalid. Admin logs to stdout/stderr.");

    FILE_STORAGE_CHANNEL_ID_STR = os.getenv("FILE_STORAGE_CHANNEL_ID");
    try: FILE_STORAGE_CHANNEL_ID = int(FILE_STORAGE_CHANNEL_ID_STR.strip()); main_logger.debug(f"Parsed FILE_STORAGE_CHANNEL_ID from ENV.");
    except (ValueError, TypeError) as e: main_logger.critical(f"VALIDATION FAILED: FILE_STORAGE_CHANNEL_ID NOT set or invalid. File handling DISABLED."); sys.exit(1);

    main_logger.info("All critical configuration variables loaded and validated.")
    print("DEBUG: --- Step 3.1: Configuration validated. ---")

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
    from database.mongo_db import DB_NAME as DB_NAME_CONST # Access DB_NAME needed by init_database_async log
    from database.models import User # Example model import if needed early (or import within handlers)
    main_logger.info("Database modules imported successfully.")
    print("DEBUG: --- Step 3.2: DB modules imported successfully. ---")

except Exception as e:
    main_logger.critical(f"FATAL: Failed to import database modules: {e}", exc_info=True);
    sys.exit(1);


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
        workdir=".", # Session files go here (container /app)
        parse_mode=config.PARSE_MODE
    )
    main_logger.info("Pyrogram client instance created successfully. Client object available as 'bot'.")
    main_logger.info("Client name: '%s', Workdir: '%s'", bot.name, bot.workdir)
    print("DEBUG: --- Step 4.1: Pyrogram Client instance created. ---")

except (ApiIdInvalid, ApiIdPublishedFlood): main_logger.critical("FATAL PYROGRAM INIT FAILED: API_ID/API_HASH invalid or public.", exc_info=True); sys.exit(1);
except AuthKeyUnregistered: main_logger.critical("FATAL PYROGRAM INIT FAILED: Session key invalid. Delete session file (/app/anime_realm_bot.session).", exc_info=True); sys.exit(1);
except Exception as e: main_logger.critical(f"FATAL PYROGRAM INIT FAILED: Unexpected error: {e}", exc_info=True); sys.exit(1);


# --- Step 5: Database Initialization (Async function) ---
async def init_database_async():
    main_logger.info("--- Step 5: Async Database Initialization Started ---")
    try:
        main_logger.info(f"Calling database.mongo_db.init_db to connect and index for DB '{config.DB_NAME}'. MONGO_URI (redacted).");
        await init_db(MONGO_URI) # init_db handles connecting and indexing. Raises exceptions on failure.
        main_logger.info("Database initialization completed successfully (connection established, indexing done).")
        print("DEBUG: --- Step 5.1: Async Database Initialization AWAIT Reported Success. ---")

    except Exception as e:
         main_logger.critical(f"FATAL DB INIT FAILED IN ASYNC: An error occurred during database initialization: {e}", exc_info=True);
         raise # Re-raise the exception


# --- Step 6: Integrated Health Check Web Server (Async) ---
# Async handler for the health check endpoint
async def healthz_handler(request):
    main_logger.debug("Received health check request on /healthz.");
    # Check status of core services (DB, Telegram connection)
    db_connected = False
    tg_connected = False

    try:
         # Check DB connection status
         if MongoDB._client and MongoDB._client.topology_description.has_known_members:
              db_connected = True
              main_logger.debug("Health check: MongoDB connection is up.")
         else: main_logger.debug("Health check: MongoDB connection not ready/failed.");
    except Exception: main_logger.debug("Health check: Could not check MongoDB status."); pass

    try:
         # Check Pyrogram client connection status
         if bot.is_connected:
              tg_connected = True
              main_logger.debug("Health check: Pyrogram client is connected to Telegram.")
         else: main_logger.debug("Health check: Pyrogram client not connected to Telegram.");
    except Exception: main_logger.debug("Health check: Could not check Pyrogram status."); pass


    # Health check returns 200 OK if BOTH DB and TG are connected for robust health.
    # If DB OR TG is down, return 503 Service Unavailable.
    if db_connected and tg_connected:
         main_logger.debug("Health check returning 200 OK (DB & TG connected).")
         return web.Response(text="OK", status=200) # Respond with OK text

    else:
        # Respond with Service Unavailable status code (503) if not fully healthy
        status_details = []
        if not db_connected: status_details.append("DB Down")
        if not tg_connected: status_details.append("TG Down")
        message = "Service Unavailable (" + ", ".join(status_details) + ")"
        main_logger.warning(f"Health check returning 503 Service Unavailable. Status: {message}")
        return web.Response(text=message, status=503) # More informative 503


# Async function to set up and start the aiohttp web server
# This function needs to be run as a separate task.
async def start_health_server_task(port: int):
    main_logger.info(f"Attempting to set up health check web server on 0.0.0.0:{port}...")
    try:
        # Create a web application instance
        app = Application() # Use Application from aiohttp.web explicitly
        # Add route for the health check endpoint
        app.router.add_get('/healthz', healthz_handler) # Use the healthz_handler

        # Create an AppRunner to manage the application lifecycle
        runner = AppRunner(app)
        main_logger.debug("Setting up AppRunner...")
        await runner.setup() # Set up the runner

        # Create and start the TCP site listener
        main_logger.debug("Creating TCP site listener binding to 0.0.0.0.")
        site = TCPSite(runner, '0.0.0.0', port)

        main_logger.info(f"Starting health check TCP site listener on port {port}.")
        await site.start() # This starts the listener in the background. It doesn't block.
        main_logger.info(f"Health check server listener successfully started on 0.0.0.0:{port}/healthz. Ready for requests.")
        print(f"DEBUG: --- Step 6.1: Health check server STARTED LISTENING on port {port}. ---")

        # The runner and site are managed by asyncio. Future(). Main execution needs to keep the loop running.
        # This async function itself should run indefinitely if successful startup.
        # Add an infinite loop await *inside* this task so it doesn't just exit after starting site.
        main_logger.info("Health server task running. Entering infinite await within task.")
        await asyncio.Future() # Keep THIS task alive indefinitely

    except OSError as e:
         main_logger.critical(f"FATAL HEALTH CHECK SERVER FAILED TO START TASK (OSError): Could not bind to port {port}. Is another process using it? {e}", exc_info=True);
         # Re-raise the exception so it can be caught by the task creation / gather in run_app_async.
         raise # Re-raise to signal failure


    except Exception as e:
         main_logger.critical(f"FATAL HEALTH CHECK SERVER FAILED TO START TASK: An unexpected error occurred during setup or runtime: {e}", exc_info=True);
         raise # Re-raise to signal failure


# --- Step 7: Main async Application Function (Orchestrates all tasks) ---
async def run_app_async():
    main_logger.info("--- Step 7: Main async Application Orchestration Started ---")
    print("DEBUG: --- Step 7.0: Inside run_app_async orchestration. ---")

    main_logger.info("Creating tasks for critical services (DB Init, Bot Start, Health Server).")

    # 7.1: Create Tasks for Core Services
    # Database Initialization Task (Connects and indexes)
    main_logger.debug("About to create Database Initialization task.")
    db_init_task = asyncio.create_task(init_database_async())
    print("DEBUG: --- Step 7.0.1: DB init task created. ---")
    main_logger.info("Database initialization task scheduled.")

    # Pyrogram Bot Start Task (Connects to TG and starts polling)
    main_logger.debug("About to create Pyrogram bot start task.")
    bot_start_task = asyncio.create_task(bot.start()) # Use the Pyrogram Client instance 'bot'
    print("DEBUG: --- Step 7.0.2: Pyrogram bot start task created. ---")
    main_logger.info("Pyrogram bot start task scheduled.")

    # Integrated Health Check Server Task (Starts the aiohttp listener)
    main_logger.debug("About to create Health Check Server task.")
    HEALTH_CHECK_PORT = 8080 # Or load from config if needed
    health_server_task = asyncio.create_task(start_health_server_task(HEALTH_CHECK_PORT))
    print(f"DEBUG: --- Step 7.0.3: Health check server task created for port {HEALTH_CHECK_PORT}. ---")
    main_logger.info(f"Health check server task scheduled for port {HEALTH_CHECK_PORT}.");

    main_logger.info("All core startup tasks are scheduled concurrently. Awaiting their initial successful startup.")
    print("DEBUG: --- Step 7.0.4: All startup tasks scheduled. About to await initial readiness. ---")

    # --- Substep 7.1: Wait for Critical Services to Report Ready ---
    # Await the tasks responsible for critical services initialization.
    # Use asyncio.gather to wait for all of them.
    # Use return_exceptions=True in gather to see ALL task exceptions, but also need to fail fast.
    # Simpler approach: Wait for them one by one *or* use gather and then check exceptions after it finishes.
    # Let's use gather and check after to log all initial failures if multiple occurred.

    startup_tasks = [db_init_task, bot_start_task, health_server_task]
    main_logger.info("Awaiting completion of initial startup tasks: db_init_task, bot_start_task, health_server_task.")
    print("DEBUG: --- Step 7.1.1: Inside await asyncio.gather for startup tasks. ---")

    try:
        # Run tasks concurrently and wait for them all to complete.
        # If any task raises an exception, gather will raise an exception *after all tasks are done*.
        # If return_exceptions=True is used, exceptions are returned in the results list instead of raised.
        # Let's let gather raise for simplicity in handling the first failure.
        startup_results = await asyncio.gather(*startup_tasks) # Await completion of all tasks. This will block.
        main_logger.info("All essential startup tasks (DB, Bot, Health) completed successfully.")
        print("DEBUG: --- Step 7.1.2: Startup tasks AWAITED SUCCESSFULLY. ---")

        # Double-check Pyrogram connection status after its task is complete
        if not bot.is_connected:
             main_logger.critical("FATAL STARTUP ISSUE: Pyrogram client task completed, but bot.is_connected is FALSE. Bot will not function.", exc_info=True);
             print("CRITICAL PRINT: FATAL STARTUP ISSUE: bot.is_connected is FALSE after start task.");
             sys.exit(1); # Exit critically

        main_logger.info("All critical services successfully initialized and reported ready.")
        print("DEBUG: --- Step 7.2: All Critical Services Reported Ready. Bot Worker Operational. ---")


    except Exception as e:
        # This block is reached if any task awaited by gather failed.
        main_logger.critical(f"FATAL STARTUP FAILURE: One or more essential service tasks failed during initial startup: {e}", exc_info=True);
        print(f"CRITICAL PRINT: FATAL STARTUP FAILURE DURING INITIAL GATHER: {e}");

        # At least one task failed. Cancel the others (if not done/cancelled already) and exit.
        main_logger.warning("Attempting to cancel any pending startup tasks due to fatal failure.");
        if not db_init_task.done(): db_init_task.cancel();
        if not bot_start_task.done(): bot_start_task.cancel();
        if not health_server_task.done(): health_server_task.cancel();

        # Wait for cancelled tasks to clear. Use return_exceptions for this final cleanup.
        try: await asyncio.gather(db_init_task, bot_start_task, health_server_task, return_exceptions=True);
        except Exception: pass # Ignore errors during final cleanup await

        # Essential services failed. The application cannot proceed. Exit critically.
        sys.exit(1);


    # --- Substep 7.2: Post-Startup Actions ---
    # These actions run only if ALL tasks in the gather block completed successfully.
    main_logger.info("Application setup complete. The core tasks are running concurrently.")
    main_logger.info("Database connection: Confirmed.")
    main_logger.info("Pyrogram client: Running and connected.")
    main_logger.info("Health check server: Running and listening on configured port/path.")


    # Report bot startup to the log channel (if configured and bot is connected)
    if LOG_CHANNEL_ID is not None and bot.is_connected:
         main_logger.info(f"Configured LOG_CHANNEL_ID is {LOG_CHANNEL_ID}. Scheduling startup notification task.")
         asyncio.create_task(send_startup_notification(bot))
         main_logger.info("Startup notification task scheduled.")
    elif LOG_CHANNEL_ID is None:
        main_logger.info("LOG_CHANNEL_ID is NOT set. Skipping startup notification to channel.");


    # --- Substep 7.3: Keep Event Loop Running Indefinitely ---
    # This is where the application waits for incoming Pyrogram updates while keeping other tasks alive.
    main_logger.info("Application fully operational. Entering infinite await to keep event loop running for incoming Telegram updates and background tasks (like health server).")
    print("DEBUG: --- Step 7.3: Entering Infinite Loop Await (asyncio.Future()). ---")

    # Awaiting a future that never completes keeps the event loop running indefinitely.
    # It won't proceed past this line unless the Future is cancelled or completed externally.
    await asyncio.Future() # Blocks the main task here


# Helper task to send startup notification message to log channel
async def send_startup_notification(client: Client):
     main_logger.debug("send_startup_notification task started.");
     try:
         # Add a short delay before sending? To give TG API a moment. Optional.
         await asyncio.sleep(1); # Example delay


         if not client.me: # Get bot identity (should be available after client.start())
             main_logger.warning("Client.me is None in notification task. Attempting client.get_me().")
             try: bot_user = await client.get_me(); main_logger.debug(f"Fetched bot user: @{bot_user.username} (ID: {bot_user.id})");
             except Exception as e: main_logger.error(f"Failed to fetch client.me in notification task: {e}", exc_info=True); bot_username = "UnknownBotUsername"; bot_id = "UnknownBotId";
             else: bot_username = bot_user.username; bot_id = bot_user.id;
         else: bot_username = client.me.username; bot_id = client.me.id;


         from config import __version__ # Import version
         startup_message = f"🤖 AnimeRealm Bot v{__version__} (Worker) started successfully!"
         startup_message += f"\n👤 Bot: @{bot_username} (ID: {bot_id})"
         startup_message += f"\n📚 Source commit/tag: {os.getenv('KOYEB_GIT_TAG', os.getenv('KOYEB_GIT_COMMIT_ID', 'N/A'))}" # Include commit hash from Koyeb ENV vars

         # Include expected health check info, assume default port 8080
         HEALTH_CHECK_PORT_ASSUMED = 8080 # Health check runs on this assumed port on health-server process
         startup_message += f"\n🩺 Health check endpoint expected on 'health-server' process on port {HEALTH_CHECK_PORT_ASSUMED}/healthz"

         startup_message += f"\n\n⏳ Ready to process Telegram updates."

         # Final check of log channel ID and client connection before sending message
         if LOG_CHANNEL_ID is None or not client.is_connected:
              main_logger.warning("Cannot send startup notification to log channel. LOG_CHANNEL_ID is None or client is not connected.");
              main_logger.info(f"Startup message content not sent to channel: '{startup_message[:200]}...'."); # Log message content that wasn't sent
              return # Task finishes


         # Send the message
         main_logger.info(f"Attempting to send startup message to log channel {LOG_CHANNEL_ID}. Preview: '{startup_message[:100]}...'.");
         await client.send_message(int(LOG_CHANNEL_ID), startup_message, parse_mode=config.PARSE_MODE);
         main_logger.info(f"Startup notification successfully sent to log channel {int(LOG_CHANNEL_ID)}.");


     except Exception as e:
          main_logger.critical(f"FATAL ERROR IN STARTUP NOTIFICATION TASK: An unexpected exception occurred during message sending: {e}", exc_info=True);
          # Log error, task completes.

# --- Step 8: Application Entry Point Execution (__main__ block) ---
# This block defines what happens when the script is run.
if __name__ == "__main__":
    print("DEBUG: --- Step 8.1: __main__ block executed. ---")
    main_logger.info("Application initiation point reached (__main__ block).")
    print("DEBUG: --- Step 8.2: Entering asyncio.run block to start the async main function. ---")

    try:
        # asyncio.run executes the specified async function and manages the event loop.
        # It runs the async function until it completes. run_app_async has infinite Future, so it runs indefinitely.
        asyncio.run(run_app_async());
        # This line should not be reached unless asyncio.run exits (e.g., loop is stopped).
        main_logger.info("asyncio.run(run_app_async()) completed without uncaught exceptions.");


    except KeyboardInterrupt:
         # Handle Ctrl+C signal for local development shutdown.
         main_logger.info("Application received KeyboardInterrupt. Initiating graceful shutdown.");
         # asyncio.run typically handles basic cleanup of tasks and loop close here.

    except SystemExit as e:
         # Catch SystemExit exceptions (from explicit sys.exit() calls).
         if e.code == 0: main_logger.info("Application exited cleanly via SystemExit (status code 0).");
         else: main_logger.critical(f"Application exited due to SystemExit with non-zero code {e.code}. Check logs for the specific FATAL message.", exc_info=True);

    except Exception as e:
         # Catch any exception that was *not* caught and handled within the async parts
         # and propagates out of the asyncio.run block. This indicates an uncaught error.
         main_logger.critical(f"Application terminated due to uncaught exception outside asyncio execution: {e}", exc_info=True);

    finally:
         print("DEBUG: --- Step 7.3: Exiting __main__ block. ---")
         main_logger.info("Application process is terminating.");
