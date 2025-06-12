# main.py
import asyncio
import logging
from telegram import Update # Only Update if used directly here
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    Defaults,
    filters
)
from telegram.constants import ParseMode

# Configuration and Strings
from configs import settings
from configs import strings # Not directly used here, but handlers will use it

# Bot command setup and Health Server
from bot import commands as bot_command_setter # Renamed for clarity
from health import start_health_server_runner, run_health_server_indefinitely

# Import all handler modules from the 'bot' package
from bot import core_handlers, admin_cmds, user_cmds, \
                anime_browser, anime_search, anime_requests, \
                content_manager, downloads, watchlist, token_system, \
                callback_handlers

# Configure basic logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO # Will be overridden by settings.LOG_LEVEL if defined and loaded
)
logger = logging.getLogger(__name__)


async def main_ptb_bot_loop(application: Application) -> None:
    """Initializes, starts, and runs the PTB application's polling loop."""
    try:
        logger.info("PTB Application: Initializing...")
        # post_init for commands is now separate for better modularity
        await application.initialize() # This calls post_init from ApplicationBuilder if one was set
                                     # We will call our command setter manually after initialize.

        logger.info("PTB Application: Setting bot commands via bot.commands module...")
        await bot_command_setter.set_bot_commands(application) # Call command setter

        # Schedule periodic jobs
        if application.job_queue:
            application.job_queue.run_repeating(
                core_handlers.check_expired_premiums_job,
                interval=3600, first=10, name="check_expired_premiums"
            )
            logger.info("Periodic job 'check_expired_premiums' scheduled.")
        else:
            logger.warning("Job Queue not available. Periodic tasks will not run.")


        logger.info("PTB Application: Starting updater and polling...")
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES, # Consider being more specific
            poll_interval=0.2,
            timeout=20,
            read_latency=5.0
        )
        logger.info("✅ PTB Polling started successfully. Bot is running.")
        await application.updater.idle() # Blocks until signaled to stop

    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot loop received stop signal (KeyboardInterrupt/SystemExit).")
    except Exception as e:
        logger.critical(f"CRITICAL - Unhandled exception in PTB main_bot_loop: {e}", exc_info=True)
    finally:
        logger.info("PTB Application: Initiating shutdown...")
        if application.updater and application.updater.running:
            logger.info("Stopping PTB updater polling...")
            await application.updater.stop()
            logger.info("PTB updater polling stopped.")
        
        logger.info("Shutting down PTB application object...")
        await application.shutdown()
        logger.info("✅ PTB Application shutdown complete.")


async def run_all_services():
    """Orchestrates the PTB bot and the aiohttp health check server."""
    if not settings.BOT_TOKEN: # Basic check from loaded settings
        logger.critical("CRITICAL: BOT_TOKEN not found in environment or settings. Bot cannot start.")
        return

    logger.info("========================================")
    logger.info("🚀 Starting Anime Realm Bot Orchestrator...")
    logger.info(f"Version: 1.0.0 (Conceptual)") # Add actual versioning if you adopt it
    logger.info(f"Admin IDs: {settings.ADMIN_IDS}")
    logger.info(f"Debug Mode: {settings.DEBUG_MODE}")
    logger.info("========================================")


    # Build PTB Application
    # Removed post_init from here as we call command setter manually now
    application = ApplicationBuilder().token(settings.BOT_TOKEN).defaults(
        Defaults(parse_mode=settings.DEFAULT_PARSE_MODE)
    ).build()

    # --- Register All PTB Handlers ---
    core_handlers.register_handlers(application) # Assume a function in each module to register its handlers
    user_cmds.register_handlers(application)
    token_system.register_handlers(application)
    anime_search.register_handlers(application)
    anime_browser.register_handlers(application)
    watchlist.register_handlers(application)
    anime_requests.register_handlers(application)
    downloads.register_handlers(application) # Likely used by callbacks, so register callback_handlers
    admin_cmds.register_handlers(application)
    content_manager.register_handlers(application)
    # Main callback handler should be general and usually last among callback handlers
    # if specific ConversationHandler callbacks are not handling everything.
    callback_handlers.register_handlers(application)
    logger.info("All PTB handlers registered.")


    # Create aiohttp AppRunner for the health server
    health_server_app_runner = await start_health_server_runner() # From health.py

    # Create asyncio tasks for each service
    # The health server task will set up and run indefinitely (or until cancelled)
    health_task = asyncio.create_task(
        run_health_server_indefinitely(health_server_app_runner),
        name="HealthServerTask"
    )
    
    # The bot task will also run indefinitely until interrupted or an unhandled error
    bot_task = asyncio.create_task(
        main_ptb_bot_loop(application),
        name="PTBBotTask"
    )

    # Wait for tasks to complete or handle interruptions
    done, pending = set(), {bot_task, health_task}
    try:
        if pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
    except KeyboardInterrupt:
        logger.info("Orchestrator: KeyboardInterrupt received. Stopping services...")
    except Exception as e:
        logger.error(f"Orchestrator: Unhandled exception while waiting on tasks: {e}", exc_info=True)
    finally:
        logger.info("Orchestrator: Initiating shutdown of all services...")
        for task in pending:
            if not task.done():
                logger.info(f"Cancelling still pending task: {task.get_name()}...")
                task.cancel()
        
        all_tasks_to_await = list(done) + list(pending)
        if all_tasks_to_await:
            results = await asyncio.gather(*all_tasks_to_await, return_exceptions=True)
            for i, result_or_exc in enumerate(results):
                task_name = all_tasks_to_await[i].get_name()
                if isinstance(result_or_exc, asyncio.CancelledError):
                    logger.info(f"Task {task_name} was successfully cancelled.")
                elif isinstance(result_or_exc, Exception):
                    logger.error(f"Task {task_name} resulted in an exception: {result_or_exc}", exc_info=result_or_exc)
                else:
                    logger.info(f"Task {task_name} finished cleanly.")
        logger.info("👋 Orchestrator shutdown complete.")


if __name__ == "__main__":
    # Ensure settings (which configures logging) is imported early if relying on its LOG_LEVEL
    # settings.py should ideally handle the basicConfig if LOG_LEVEL is set there.
    # If not, ensure basicConfig is called before first logger use.
    # Basic logging is already set at top-level import for initial messages.
    # `configs.settings` also calls `basicConfig`.
    logger.info("Script execution started (__main__).")
    try:
        asyncio.run(run_all_services())
    except RuntimeError as e_runtime:
        if "event loop is already running" in str(e_runtime).lower():
            logger.critical(f"Asyncio Event Loop Conflict: {e_runtime}. ")
        else:
            logger.critical(f"Top-level RuntimeError: {e_runtime}", exc_info=True)
    except Exception as e_global:
        logger.critical(f"Unhandled top-level exception: {e_global}", exc_info=True)
    finally:
        logger.info("Script execution finished (__main__).")
