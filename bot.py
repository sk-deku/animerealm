import logging
import asyncio # For health check server
from aiohttp import web # For health check server
from pyrogram import Client, idle
import config
from database.connection import db as mongodb_instance # Ensure DB connection is tried at start
from database.operations import check_and_revoke_expired_premiums # For scheduled task
from utils.logger import log_bot_event
from datetime import datetime, timezone # For UTC aware start_time
import os

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOGGER = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING) # Quiet aiohttp access logs


# --- Health Check Endpoint for Koyeb ---
async def health_check_handler(request):
    # You can add more checks here, e.g., database connectivity
    # db_ok = await mongodb_instance.test_connection()
    # if db_ok:
    #    return web.Response(text="OK", content_type="text/plain")
    # else:
    #    return web.Response(text="ERROR - DB Connection Failed", status=503, content_type="text/plain")
    return web.Response(text="OK", content_type="text/plain")

async def start_health_check_server(app_client: Client): # Pass client for context if needed later
    app_web = web.Application()
    app_web.router.add_get('/healthz', health_check_handler) # Common path for health checks
    
    # Use PORT from environment if Koyeb sets it, otherwise default to 8080
    port = int(os.environ.get("PORT", 8080))
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    try:
        await site.start()
        LOGGER.info(f"Health check server started on port {port}")
    except OSError as e: # Handle "address already in use" gracefully
        LOGGER.error(f"Could not start health check server on port {port}: {e}. Bot will continue without it.")
        # Optionally, you might want to try another port or simply log and proceed.


# --- Scheduled Tasks ---
async def scheduled_tasks_runner(app_client: Client):
    while True:
        await asyncio.sleep(3600) # Run every hour (3600 seconds)
        try:
            LOGGER.info("Running scheduled task: Checking for expired premiums...")
            revoked_count = await check_and_revoke_expired_premiums()
            if revoked_count > 0:
                await log_bot_event(app_client, f"System revoked {revoked_count} expired premium subscriptions.")
            LOGGER.info(f"Scheduled task finished. Revoked {revoked_count} premiums.")
        except Exception as e:
            LOGGER.error(f"Error in scheduled_tasks_runner: {e}", exc_info=True)


# --- Pyrogram Bot Class ---
class Bot(Client):
    def __init__(self):
        super().__init__(
            name="AnimeFireTamilBot", # Session name
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            plugins={"root": "handlers"} # Auto-load handlers
        )
        self.start_time = datetime.now(timezone.utc) # Store bot start time

    async def start(self):
        await super().start()
        # Test DB connection
        if not await mongodb_instance.test_connection():
            LOGGER.critical("MongoDB connection failed. Bot functionality will be SEVERELY impacted. Exiting.")
            # For critical DB failure, it's often best to stop.
            # exit(1) # Uncomment if you want it to exit on DB fail
        else:
            LOGGER.info("MongoDB connection test successful during bot start.")
        
        me = await self.get_me()
        # Update config.BOT_USERNAME with the actual username after successful start
        if me and me.username:
            config.BOT_USERNAME = me.username 
        else:
            LOGGER.warning("Could not fetch bot username. Deep links might not work as expected.")
            # config.BOT_USERNAME will remain as per .env if this fails

        log_startup_msg = f"Bot @{config.BOT_USERNAME} (ID: {me.id if me else 'N/A'}) started successfully!"
        LOGGER.info(log_startup_msg)
        await log_bot_event(self, log_startup_msg) # Log to channel if configured

        # Start the health check server
        asyncio.create_task(start_health_check_server(self))
        # Start scheduled tasks
        asyncio.create_task(scheduled_tasks_runner(self))


    async def stop(self):
        await super().stop()
        log_shutdown_msg = "Bot stopped."
        LOGGER.info(log_shutdown_msg)
        # No need to use log_bot_event here for shutdown usually, as client might be disconnecting

if __name__ == "__main__":
    if not all([config.BOT_TOKEN, config.API_ID, config.API_HASH, config.MONGO_URI]):
        LOGGER.critical("One or more critical environment variables are missing in config. Exiting.")
    else:
        app = Bot()
        try:
            # Using app.run() correctly handles startup and graceful shutdown with idle()
            app.run() 
        except Exception as e:
            LOGGER.critical(f"Bot run failed globally: {e}", exc_info=True)
        finally:
            LOGGER.info("Bot process finished or exited.")
