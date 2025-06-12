# main.py
import logging
import asyncio
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler, # Keep if you have MessageHandlers
    CallbackQueryHandler,
    ConversationHandler, # Keep if you have ConversationHandlers
    ContextTypes,
    Defaults,
    # PicklePersistence, # Optional
    filters # Keep if you use filters
)
from telegram.constants import ParseMode

from aiohttp import web # For the health check server

# Import configurations
from configs import settings # Assuming settings.py is in configs directory
from configs import strings  # Assuming strings.py is in configs directory

# Import database instance (ensure it's correctly initialized, especially for async if using Motor)
# from database.mongo_db import db as anidb # Example import

# Import bot handlers from the 'bot' package
from bot import core_handlers, admin_cmds, user_cmds, \
                anime_browser, anime_search, anime_requests, \
                content_manager, downloads, watchlist, token_system, \
                callback_handlers

# Configure logging
logger = logging.getLogger(__name__)

# --- Global Application Variable ---
ptb_application_instance: Application | None = None


# --- Health Check Server ---
async def health_check_handler(request: web.Request) -> web.Response:
    """Simple health check endpoint."""
    global ptb_application_instance
    bot_username = "Bot initializing..."
    bot_name = "Bot initializing..."
    status_code = 503 # Service Unavailable initially
    is_polling = False

    if ptb_application_instance and ptb_application_instance.bot:
        try:
            # Check if updater exists and is running as an indicator of readiness
            if ptb_application_instance.updater and ptb_application_instance.updater.running:
                is_polling = True # Indicates the bot is actively polling
                bot_info = await ptb_application_instance.bot.get_me()
                bot_username = bot_info.username
                bot_name = bot_info.first_name
                status_code = 200 # OK
                message = "Bot is running and polling."
            elif ptb_application_instance.initialized: # If initialized but not yet polling
                 bot_info = await ptb_application_instance.bot.get_me()
                 bot_username = bot_info.username
                 bot_name = bot_info.first_name
                 status_code = 202 # Accepted, but not fully active
                 message = "Bot is initialized but polling may not have started."
            else:
                message = "Bot application object exists but not fully initialized or polling."
                logger.warning(f"Health check: PTB application instance exists but not fully ready (updater running: {is_polling}).")
        except Exception as e:
            logger.error(f"Health check: Error getting bot info or checking status: {e}")
            status_code = 500 # Internal Server Error
            bot_username = "Error fetching bot info"
            bot_name = "Error fetching bot info"
            message = f"Error during health check: {str(e)}"
            
    return web.json_response({
        "status": "ok" if status_code == 200 else "pending_or_error",
        "bot_username": bot_username,
        "bot_name": bot_name,
        "is_polling": is_polling,
        "message": message
    }, status=status_code)

async def start_health_check_server(app_runner_instance: web.AppRunner) -> None:
    """Sets up and starts the aiohttp server."""
    await app_runner_instance.setup()
    site = web.TCPSite(app_runner_instance, settings.HEALTH_CHECK_HOST, settings.HEALTH_CHECK_PORT)
    try:
        await site.start()
        logger.info(f"🚀 Health check server started on http://{settings.HEALTH_CHECK_HOST}:{settings.HEALTH_CHECK_PORT}")
        # Keep this task running until it's cancelled
        while True:
            await asyncio.sleep(3600) # Sleep for a long time
    except asyncio.CancelledError:
        logger.info("Health check server task cancelled. Shutting down site...")
    except Exception as e:
        logger.error(f"Health check server error: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up health check server site...")
        # await site.stop() # This might not be needed if runner.cleanup handles it
        await app_runner_instance.cleanup()
        logger.info("✅ Health check server site cleanup complete.")


# --- Main Bot Application Setup ---
async def post_init(application: Application):
    """Post-initialization tasks, like setting bot commands and scheduling jobs."""
    global ptb_application_instance
    ptb_application_instance = application
    logger.info("PTB Application post_init called.")

    # General commands visible to all users
    general_commands = [
        BotCommand("start", "🌟 Start or restart the bot"),
        BotCommand("help", "❓ Get help and command list"),
        BotCommand("search", "🔍 Search for an anime"),
        BotCommand("browse", "📚 Browse anime by genre/status"),
        BotCommand("popular", "🔥 View popular anime"),
        BotCommand("latest", "🆕 See latest episode additions"),
        BotCommand("my_watchlist", "💖 Manage your watchlist"),
        BotCommand("profile", "👤 View your profile & tokens"),
        BotCommand("gen_tokens", "🔗 Generate referral link & earn!"),
        BotCommand("premium", "💎 View premium options"),
        BotCommand("cancel", "❌ Cancel current operation (if any)"),
    ]

    # Commands specifically for admin users
    admin_only_commands = [
        BotCommand("manage_content", "🛠️ Manage anime content"),
        BotCommand("grant_premium", "👑 Grant premium to user"),
        BotCommand("revoke_premium", "🚫 Revoke premium from user"),
        BotCommand("add_tokens", "🪙 Add tokens to user"),
        BotCommand("remove_tokens", "➖ Remove tokens from user"),
        BotCommand("broadcast", "📣 Broadcast message to users"),
        BotCommand("user_info", "ℹ️ Get user details"),
        BotCommand("bot_stats", "📊 View bot statistics"),
        BotCommand("cancel_cm", "❌ Cancel Content Management"), # Specific for CM conv
    ]

    try:
        await application.bot.set_my_commands(general_commands)
        logger.info("General bot commands set globally.")

        # Set scoped commands for each admin ID
        # This ensures admins see both general and admin-specific commands
        if settings.ADMIN_IDS:
            full_admin_command_list = general_commands + admin_only_commands
            for admin_id in settings.ADMIN_IDS:
                try:
                    await application.bot.set_my_commands(full_admin_command_list, scope={"type": "chat", "chat_id": admin_id})
                except Exception as e_admin_scope:
                    logger.error(f"Failed to set scoped commands for admin {admin_id}: {e_admin_scope}")
            logger.info(f"Admin-specific commands scoped for {len(settings.ADMIN_IDS)} admin(s).")
        else:
            logger.warning("No ADMIN_IDS configured. Admin commands will not be specially scoped.")

    except Exception as e:
        logger.error(f"Error setting bot commands during post_init: {e}", exc_info=True)

    # Schedule periodic jobs if JobQueue is available and configured
    if application.job_queue:
        application.job_queue.run_repeating(
            core_handlers.check_expired_premiums_job, # This job must be defined in core_handlers.py
            interval=timedelta(hours=1), # Check every hour
            first=timedelta(seconds=10), # Run 10 seconds after start-up
            name="check_expired_premiums"
        )
        logger.info("Periodic job 'check_expired_premiums' scheduled.")
    else:
        logger.warning("Job Queue not available in PTB application. Periodic tasks will not run.")


async def main_bot_loop():
    """Initializes, starts, and runs the PTB application's polling loop."""
    global ptb_application_instance
    logger.info("========================================")
    logger.info("🚀 Initializing Anime Realm Bot PTB Application...")
    logger.info(f"Version: 1.0.0 (Conceptual)")
    logger.info(f"Admin IDs: {settings.ADMIN_IDS}")
    logger.info(f"Debug Mode: {settings.DEBUG_MODE}")
    logger.info("========================================")

    bot_defaults = Defaults(parse_mode=settings.DEFAULT_PARSE_MODE, block=False)

    application = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .defaults(bot_defaults)
        .post_init(post_init) # Called after .build() and before .initialize()
        # .concurrent_updates(20) # Optional: handle more updates concurrently
        .build()
    )
    ptb_application_instance = application # Set global for health check early

    # --- Register All Handlers ---
    # Core Handlers
    application.add_handler(CommandHandler("start", core_handlers.start_command))
    application.add_handler(CommandHandler("help", core_handlers.help_command))
    application.add_handler(CommandHandler("cancel", core_handlers.cancel_command)) # Generic cancel
    application.add_error_handler(core_handlers.error_handler)

    # User Command Handlers
    application.add_handler(CommandHandler("profile", user_cmds.profile_command))
    application.add_handler(CommandHandler("premium", user_cmds.premium_info_command))
    application.add_handler(CommandHandler("gen_tokens", token_system.generate_and_show_token_link_command))

    # Anime Discovery Handlers
    application.add_handler(anime_search.get_search_conv_handler()) # Search conversation
    # Ensure /search [query] still works as direct entry
    application.add_handler(CommandHandler("search", anime_search.search_anime_command_entry, block=False))


    application.add_handler(CommandHandler("browse", anime_browser.browse_start_command))
    application.add_handler(CommandHandler("popular", anime_browser.popular_anime_command))
    application.add_handler(CommandHandler("latest", anime_browser.latest_anime_command))

    # Watchlist Handlers
    application.add_handler(CommandHandler("my_watchlist", watchlist.view_watchlist_command))
    application.add_handler(CommandHandler("view_watchlist", watchlist.view_watchlist_command)) # Alias or deep link target

    # Anime Request Handlers
    application.add_handler(CommandHandler("request", anime_requests.request_anime_command,
                                           filters=~filters.User(settings.ADMIN_IDS) & filters.ChatType.PRIVATE))

    # Admin Command Handlers
    admin_filter = filters.User(settings.ADMIN_IDS) & filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("grant_premium", admin_cmds.grant_premium_command, filters=admin_filter))
    application.add_handler(CommandHandler("revoke_premium", admin_cmds.revoke_premium_command, filters=admin_filter))
    application.add_handler(CommandHandler("add_tokens", admin_cmds.add_tokens_command, filters=admin_filter))
    application.add_handler(CommandHandler("remove_tokens", admin_cmds.remove_tokens_command, filters=admin_filter))
    application.add_handler(CommandHandler("user_info", admin_cmds.user_info_command, filters=admin_filter))
    application.add_handler(admin_cmds.get_broadcast_conv_handler()) # Broadcast conversation
    application.add_handler(CommandHandler("bot_stats", admin_cmds.bot_stats_command, filters=admin_filter))

    # Admin Content Management Conversation Handler
    application.add_handler(content_manager.get_manage_content_conv_handler())
    # Note: content_manager's ConversationHandler should define its own entry points like /manage_content with admin filters

    # General Callback Query Handler (must be one of the last handlers)
    application.add_handler(CallbackQueryHandler(callback_handlers.main_callback_handler))

    logger.info("All handlers registered.")

    # --- Start PTB Polling ---
    try:
        logger.info("PTB Application initializing...")
        await application.initialize() # Initializes handlers, updater, etc.
        logger.info("PTB Application starting updater and polling...")
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES, poll_interval=0.2, timeout=20, read_latency=5.0)
        # `start()` method starts dispatcher and job_queue if used, called by initialize already in effect.
        # For polling, explicitly calling updater.start_polling is needed.
        logger.info("✅ PTB Polling started successfully and bot is running.")
        
        # Keep this coroutine alive as updater runs in its own thread/tasks managed by PTB
        while True:
            await asyncio.sleep(3600) # Or some other mechanism to keep alive if needed, or await updater.idle()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot received stop signal (KeyboardInterrupt/SystemExit).")
    except Exception as e:
        logger.critical(f"CRITICAL - Unhandled exception during PTB main_bot_loop: {e}", exc_info=True)
    finally:
        logger.info("Initiating PTB application shutdown...")
        if application.updater and application.updater.running:
            logger.info("Stopping PTB updater polling...")
            await application.updater.stop()
            logger.info("PTB updater polling stopped.")
        # application.stop() is for webhook, for polling, updater.stop() is key
        logger.info("Shutting down PTB application...")
        await application.shutdown() # Cleans up handlers, job_queue, etc.
        logger.info("✅ PTB Application shutdown complete.")


async def amain_orchestrator(): # Main async entry point to orchestrate tasks
    """Orchestrates the bot and health check server."""
    # Setup for aiohttp server
    aiohttp_app = web.Application()
    aiohttp_app.router.add_get("/healthz", health_check_handler) # Koyeb might prefer /healthz
    aiohttp_app.router.add_get("/", health_check_handler)       # Root for simple check
    runner = web.AppRunner(aiohttp_app)

    # Create tasks for the bot and the health server
    # The health server task will set up and run indefinitely (or until cancelled)
    health_server_task = asyncio.create_task(start_health_check_server(runner))
    
    # The bot task will also run indefinitely until interrupted or an unhandled error
    bot_task = asyncio.create_task(main_bot_loop())

    try:
        # Wait for either task to complete (which means one might have errored or been stopped)
        # or for an external interruption like KeyboardInterrupt.
        done, pending = await asyncio.wait(
            [bot_task, health_server_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending: # Cancel any tasks that are still pending
            logger.info(f"Cancelling pending task: {task.get_name()}")
            task.cancel()
            try: await task # Allow task to process cancellation
            except asyncio.CancelledError: logger.info(f"Task {task.get_name()} successfully cancelled.")
            except Exception as e_task_cancel: logger.error(f"Error during cancellation of task {task.get_name()}: {e_task_cancel}")
        
        for task in done: # Check if any completed task had an exception
            if task.exception():
                logger.error(f"Task {task.get_name()} completed with an exception: {task.exception()}", exc_info=task.exception())

    except KeyboardInterrupt:
        logger.info("Main orchestrator received KeyboardInterrupt. Signaling tasks to stop.")
    except SystemExit as e:
        logger.info(f"Main orchestrator received SystemExit: {e}")
    except Exception as e: # Catch-all for orchestrator level errors
        logger.critical(f"CRITICAL - Unhandled exception in main orchestrator: {e}", exc_info=True)
    finally:
        logger.info("Main orchestrator: Final cleanup initiated...")
        # Ensure tasks are given a chance to clean up after cancellation signal
        all_tasks = [bot_task, health_server_task]
        for task in all_tasks:
            if not task.done(): # If not already done (e.g., completed or cancelled from asyncio.wait)
                if not task.cancelled(): task.cancel()
                try: await task
                except asyncio.CancelledError: pass # Expected
                except Exception as e: logger.error(f"Error ensuring task {task.get_name()} is finished: {e}")
        
        logger.info("Ensuring aiohttp runner is cleaned (might be redundant if start_health_check_server handles it).")
        # await runner.cleanup() # Cleanup is now in start_health_check_server's finally
        
        logger.info("👋 Main orchestrator shutdown complete.")


if __name__ == "__main__":
    # Basic logging setup for initial messages before settings might be fully loaded by PTB
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO # Can be overridden by LOG_LEVEL from settings later
    )
    logger.info("Script execution started.")
    try:
        asyncio.run(amain_orchestrator())
    except RuntimeError as e:
        if "event loop is already running" in str(e).lower():
            logger.critical(f"Asyncio event loop conflict at highest level (asyncio.run): {e}")
        else:
            logger.critical(f"CRITICAL - Top-level Runtime error: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"CRITICAL - Unhandled top-level exception: {e}", exc_info=True)
    finally:
        logger.info("Script execution finished.")
