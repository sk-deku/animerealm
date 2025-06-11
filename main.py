# main.py
import logging
import asyncio
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    Defaults,
    PicklePersistence,
    filters
)
from telegram.constants import ParseMode

from aiohttp import web

from configs import settings, strings
from database.mongo_db import db as anidb

from bot import core_handlers, admin_cmds, user_cmds, \
                anime_browser, anime_search, anime_requests, \
                content_manager, downloads, watchlist, token_system, \
                callback_handlers

logger = logging.getLogger(__name__)

# --- Global Application Variable ---
# This is for the health check server to access the bot application.
# It will be set in the main() function before starting polling.
ptb_application_instance: Application | None = None


# --- Health Check Server ---
async def health_check_handler(request: web.Request) -> web.Response:
    """Simple health check endpoint."""
    global ptb_application_instance
    bot_username = "Bot not fully initialized"
    bot_name = "Bot not fully initialized"
    status_code = 503 # Service Unavailable initially

    if ptb_application_instance and ptb_application_instance.bot:
        try:
            # A light check, like get_me(), or just check if initialized
            if ptb_application_instance.initialized:
                bot_info = await ptb_application_instance.bot.get_me()
                bot_username = bot_info.username
                bot_name = bot_info.first_name
                status_code = 200 # OK
            else:
                logger.warning("Health check: PTB application not initialized yet.")
        except Exception as e:
            logger.error(f"Health check: Error getting bot info: {e}")
            status_code = 500 # Internal Server Error
            bot_username = "Error fetching bot info"
            bot_name = "Error fetching bot info"
            
    return web.json_response({
        "status": "ok" if status_code == 200 else "error",
        "bot_username": bot_username,
        "bot_name": bot_name,
        "message": "Bot is running" if status_code == 200 else "Bot status check failed or pending initialization"
    }, status=status_code)

async def start_health_check_server(app_runner_instance: web.AppRunner) -> None:
    """Starts the aiohttp server."""
    await app_runner_instance.setup()
    site = web.TCPSite(app_runner_instance, settings.HEALTH_CHECK_HOST, settings.HEALTH_CHECK_PORT)
    logger.info(f"🚀 Health check server starting on http://{settings.HEALTH_CHECK_HOST}:{settings.HEALTH_CHECK_PORT}")
    await site.start()
    logger.info("✅ Health check server started.")


# --- Main Bot Application Setup ---
async def post_init(application: Application):
    global ptb_application_instance
    ptb_application_instance = application # Set the global instance once initialized

    commands = [
        BotCommand("start", "🌟 Start or restart the bot"),
        BotCommand("help", "❓ Get help and command list"),
        BotCommand("search", "🔍 Search for an anime"),
        BotCommand("browse", "📚 Browse anime by genre/status"),
        BotCommand("popular", "🔥 View popular anime"),
        BotCommand("latest", "🆕 See latest episode additions"),
        BotCommand("my_watchlist", "💖 Manage your watchlist"),
        BotCommand("profile", "👤 View your profile & tokens"),
        BotCommand("gen_tokens", "🔗 Generate referral link & earn!"), # Updated
        BotCommand("premium", "💎 View premium options"),
        BotCommand("cancel", "❌ Cancel current operation"),
    ]
    admin_commands_list = [ # Renamed to avoid conflict with built-in commands
        BotCommand("manage_content", "🛠️ Manage anime content (Admin)"),
        BotCommand("grant_premium", "👑 Grant premium (Admin)"),
        BotCommand("revoke_premium", "🚫 Revoke premium (Admin)"),
        BotCommand("add_tokens", "🪙 Add tokens to user (Admin)"),
        BotCommand("remove_tokens", "➖ Remove tokens from user (Admin)"),
        BotCommand("broadcast", "📣 Broadcast message (Admin)"),
        BotCommand("user_info", "ℹ️ Get user details (Admin)"),
        BotCommand("bot_stats", "📊 View bot statistics (Admin)"),
        BotCommand("cancel_cm", "❌ Cancel Content Mngmt (Admin)"), # Specific CM cancel
    ]
    try:
        # Set general commands visible to all
        await application.bot.set_my_commands(commands)
        logger.info("General bot commands set.")
        # Set specific commands for admins (will override global for admins)
        for admin_id in settings.ADMIN_IDS:
            await application.bot.set_my_commands(commands + admin_commands_list, scope={"type": "chat", "chat_id": admin_id})
        logger.info("Admin-specific bot commands set for admin users.")
    except Exception as e:
        logger.error(f"Error setting bot commands: {e}", exc_info=True)


    if application.job_queue:
        application.job_queue.run_repeating(
            core_handlers.check_expired_premiums_job,
            interval=3600, first=10
        )
        logger.info("Periodic job for checking expired premiums scheduled.")
    else:
        logger.warning("Job Queue not available in PTB application. Periodic tasks will not run.")


async def main_bot_logic():
    """This function sets up and runs the PTB application."""
    global ptb_application_instance # To share with health check
    logger.info("========================================")
    logger.info("🚀 Initializing Anime Realm Bot PTB Application...")
    logger.info(f"Version: 1.0.0 (Conceptual)")
    logger.info(f"Admin IDs: {settings.ADMIN_IDS}")
    logger.info(f"Debug Mode: {settings.DEBUG_MODE}")
    logger.info("========================================")

    bot_defaults = Defaults(parse_mode=settings.DEFAULT_PARSE_MODE, block=False)

    # Create the Application (without context manager for run_polling here)
    application = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .defaults(bot_defaults)
        .post_init(post_init)
        # .concurrent_updates(True) # Can sometimes help with handling many updates
        .build()
    )
    ptb_application_instance = application # Set global early, post_init will re-set too

    # --- Register Handlers ---
    # Core Handlers
    application.add_handler(CommandHandler("start", core_handlers.start_command))
    application.add_handler(CommandHandler("help", core_handlers.help_command))
    # Make cancel more broadly available for admins; others usually cancel via inline buttons within conv.
    application.add_handler(CommandHandler("cancel", core_handlers.cancel_command))
    application.add_error_handler(core_handlers.error_handler)

    # User Command Handlers
    application.add_handler(CommandHandler("profile", user_cmds.profile_command))
    application.add_handler(CommandHandler("premium", user_cmds.premium_info_command))
    application.add_handler(CommandHandler("gen_tokens", token_system.generate_and_show_token_link_command)) # Updated name

    # Anime Discovery Handlers
    application.add_handler(anime_search.get_search_conv_handler())
    application.add_handler(CommandHandler("browse", anime_browser.browse_start_command))
    application.add_handler(CommandHandler("popular", anime_browser.popular_anime_command))
    application.add_handler(CommandHandler("latest", anime_browser.latest_anime_command))

    # Watchlist Handlers
    application.add_handler(CommandHandler("my_watchlist", watchlist.view_watchlist_command))
    application.add_handler(CommandHandler("view_watchlist", watchlist.view_watchlist_command))

    # Anime Request Handlers
    application.add_handler(CommandHandler("request", anime_requests.request_anime_command, filters=~filters.User(settings.ADMIN_IDS) & filters.ChatType.PRIVATE))

    # Admin Command Handlers (ensure filters are applied)
    admin_filter = filters.User(settings.ADMIN_IDS) & filters.ChatType.PRIVATE # Admins usually interact in DMs
    application.add_handler(CommandHandler("grant_premium", admin_cmds.grant_premium_command, filters=admin_filter))
    application.add_handler(CommandHandler("revoke_premium", admin_cmds.revoke_premium_command, filters=admin_filter))
    application.add_handler(CommandHandler("add_tokens", admin_cmds.add_tokens_command, filters=admin_filter))
    application.add_handler(CommandHandler("remove_tokens", admin_cmds.remove_tokens_command, filters=admin_filter))
    application.add_handler(CommandHandler("user_info", admin_cmds.user_info_command, filters=admin_filter))
    application.add_handler(admin_cmds.get_broadcast_conv_handler()) # Broadcast conv has its own entry/filters
    application.add_handler(CommandHandler("bot_stats", admin_cmds.bot_stats_command, filters=admin_filter))

    # Admin Content Management Conversation Handler
    # get_manage_content_conv_handler itself defines entry CommandHandler with filters
    application.add_handler(content_manager.get_manage_content_conv_handler())


    # General Callback Query Handler (ensure specific ConversationHandler callbacks are processed first or are distinct)
    application.add_handler(CallbackQueryHandler(callback_handlers.main_callback_handler))

    logger.info("🤖 Bot is starting to poll...")
    # Using run_polling() which is blocking in terms of its own loop management.
    # We are not awaiting it here, but will let it run until an error or SIGINT.
    # It will be started and stopped by the __main__ block's with application:
    try:
        # This needs to be run with "with application:" for proper startup/shutdown
        # of internal tasks. `await application.run_polling()` outside of the `with` block
        # can lead to issues if the loop is already being managed by `asyncio.run()`.
        # The recommended way with PTB for external loop management (like our aiohttp server)
        # is to start `initialize` and `start_polling` manually and handle `shutdown`.

        await application.initialize()  # Initialize handlers, etc.
        await application.start()       # Start PTB's internal tasks, but not yet start_polling.
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES, poll_interval=0.1) # Start the low-level polling.
        logger.info("✅ PTB Polling started successfully.")

        # Keep this coroutine alive, application runs in background tasks now
        while True:
            await asyncio.sleep(1) # Keep this alive or use some other method

    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot polling received stop signal (KeyboardInterrupt/SystemExit).")
    except Exception as e:
        logger.critical(f"CRITICAL - Unhandled exception during PTB polling setup or main loop: {e}", exc_info=True)
    finally:
        logger.info("Initiating PTB application shutdown sequence...")
        if application.updater and application.updater.running:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("✅ PTB Application shutdown complete.")


async def amain(): # Main async orchestrator
    # Setup for aiohttp server
    aiohttp_app = web.Application()
    aiohttp_app.router.add_get("/healthz", health_check_handler)
    aiohttp_app.router.add_get("/", health_check_handler)
    runner = web.AppRunner(aiohttp_app)

    # Create tasks for the bot and the health server
    bot_task = asyncio.create_task(main_bot_logic())
    health_server_setup_task = asyncio.create_task(start_health_check_server(runner))

    try:
        # Wait for both tasks. If one fails, it will raise its exception here.
        # Usually, bot_task will run "forever" (until KeyboardInterrupt or other stop).
        # Health server setup should complete quickly.
        await health_server_setup_task # Ensure server is at least attempted to start
        logger.info("Health server setup awaited. Bot task will continue to run.")
        await bot_task # This will now effectively block here until bot_task finishes/errors.

    except KeyboardInterrupt:
        logger.info("Main orchestrator received KeyboardInterrupt.")
    except SystemExit as e:
        logger.info(f"Main orchestrator received SystemExit: {e}")
    except Exception as e:
        logger.critical(f"CRITICAL - Unhandled exception in main orchestrator: {e}", exc_info=True)
    finally:
        logger.info("Main orchestrator: Initiating final cleanup...")
        if bot_task and not bot_task.done():
            bot_task.cancel()
            try: await bot_task
            except asyncio.CancelledError: logger.info("Bot task successfully cancelled.")
            except Exception as e_bt: logger.error(f"Error during bot task cancellation: {e_bt}")

        logger.info("Cleaning up aiohttp runner...")
        await runner.cleanup() # Cleanup aiohttp server
        logger.info("aiohttp runner cleanup complete.")
        logger.info("👋 Main orchestrator shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except RuntimeError as e: # Catch specific loop errors if asyncio.run itself fails early
        if "Cannot run an event loop while another is running" in str(e) or "This event loop is already running" in str(e):
            logger.critical(f"Asyncio event loop conflict detected at highest level: {e}")
        else:
            logger.critical(f"CRITICAL - Runtime error in __main__: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"CRITICAL - Unhandled exception in __main__ execution block: {e}", exc_info=True)
