# health.py
import asyncio
import logging
from aiohttp import web
from configs import settings # To get port and host

logger = logging.getLogger(__name__)

# --- Global reference to the PTB Application instance ---
# This can be set from main.py after the Application is built.
# It allows the health check to potentially provide more info about the bot.
# For a truly "fake" health check that just passes, this isn't strictly needed
# but is good for a slightly more informative one.
ptb_application_for_health: web.Application | None = None # Use web.Application to store ref from aiohttp app context
                                                           # Or pass PTB application differently if needed.

async def health_check_endpoint(request: web.Request) -> web.Response:
    """
    Simple health check endpoint.
    For Koyeb, this needs to return a 2xx status code to be considered healthy.
    """
    bot_username = "Bot initializing..."
    bot_name = "Bot initializing..."
    is_polling = False
    status_code = 200 # Assume OK for a fake pass, but can be made smarter
    message = "Health check nominally OK. Bot status may vary."

    # Access the PTB application instance if set in the aiohttp app's context
    # This example doesn't do that for simplicity of "fake" health check.
    # If you wanted to integrate it, main.py would pass the PTB app instance
    # to this server, perhaps via the aiohttp application's context.
    # For now, it's truly fake and always passes if server is up.

    logger.debug(f"Health check request received from {request.remote} - Responding OK")
    return web.json_response({
        "status": "ok",
        "bot_username": bot_username, # Static for fake check
        "bot_name": bot_name,         # Static for fake check
        "is_polling": is_polling,       # Static for fake check
        "message": message
    }, status=status_code)


async def start_health_server_runner() -> web.AppRunner:
    """Creates and returns the aiohttp AppRunner."""
    aiohttp_app = web.Application()
    aiohttp_app.router.add_get("/", health_check_endpoint)
    aiohttp_app.router.add_get("/healthz", health_check_endpoint) # Common path
    
    # If you want to share PTB app instance with health check handlers:
    # aiohttp_app['ptb_app'] = some_global_ptb_app_instance # Set by main.py

    runner = web.AppRunner(aiohttp_app)
    await runner.setup()
    return runner

async def run_health_server_indefinitely(runner: web.AppRunner):
    """Starts the site and keeps the server task running."""
    site = web.TCPSite(runner, settings.HEALTH_CHECK_HOST, settings.HEALTH_CHECK_PORT)
    try:
        await site.start()
        logger.info(f"🚀 Fake Health Check Server running on http://{settings.HEALTH_CHECK_HOST}:{settings.HEALTH_CHECK_PORT}")
        while True:
            await asyncio.sleep(3600) # Keep alive
    except asyncio.CancelledError:
        logger.info("Health server task cancelled. Shutting down site...")
    except Exception as e:
        logger.error(f"Health server runtime error: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up health server resources...")
        # Site stop might be handled by runner.cleanup, but doesn't hurt to try if reference exists
        # await site.stop() # This might cause issues if called before runner.cleanup if site not stored broadly
        await runner.cleanup()
        logger.info("✅ Health server cleanup complete.")
