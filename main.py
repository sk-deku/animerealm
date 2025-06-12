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
    filters
)
from telegram.constants import ParseMode

from aiohttp import web # For the health check server

from configs import settings
from configs import strings

# from database.mongo_db import db as anidb # Import your DB instance if used directly in main/post_init

from bot import core_handlers, admin_cmds, user_cmds, \
                anime_browser, anime_search, anime_requests, \
                content_manager, downloads, watchlist, token_system, \
                callback_handlers

logger = logging.getLogger(__name__)

# --- Simplified Health Check Server ---
async def simple_health_check_handler(request: web.Request) -> web.Response:
    """Always returns a 200 OK status for health checks."""
    logger.debug(f"Health check request received at {request.path}")
    return web.json_response({
        "status": "ok",
        "message": "Anime Realm Bot http endpoint is active."
    }, status=200)

async def start_simple_health_check_server(app_runner_instance: web.AppRunner) -> None:
    """Sets up and starts the simple aiohttp server."""
    await app_runner_instance.setup()
    site = web.TCPSite(app_runner_instance, settings.HEALTH_CHECK_HOST, settings.HEALTH_CHECK_PORT)
    try:
        await site.start()
        logger.info(f"🚀 Simple health check server started on http://{settings.HEALTH_CHECK_HOST}:{settings.HEALTH_CHECK_PORT}")
        while True:
            await asyncio.sleep(3600) # Keep task alive
    except asyncio.CancelledError:
        logger.info("Simple health check server task cancelled. Shutting down site...")
    except Exception as e:
        logger.error(f"Simple health check server error: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up simple health check server site...")
        await app_runner_instance.cleanup()
        logger.info("✅ Simple health check server site cleanup complete.")


# --- Main Bot Application Setup ---
async def post_init(application: Application):
    """Post-initialization tasks, like setting bot commands and scheduling jobs."""
    # No need for global ptb_application_instance if health check is simple
    logger.info("PTB Application post_init called.")

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
    admin_only_commands = [
        BotCommand("manage_content", "🛠️ Manage anime content"),
        BotCommand("grant_premium", "👑 Grant premium to user"),
        BotCommand("revoke_premium", "🚫 Revoke premium from user"),
        BotCommand("add_tokens", "🪙 Add tokens to user"),
        BotCommand("remove_tokens", "➖ Remove tokens from user"),
        BotCommand("broadcast", "📣 Broadcast message to users"),
        BotCommand("user_info", "ℹ️ Get user details"),
        BotCommand("bot_stats", "📊 View bot statistics"),
        BotCommand("cancel_cm", "❌ Cancel Content Management"),
    ]

    try:
        await application.bot.set_my_commands(general_commands)
        logger.info("General bot commands set globally.")
        if settings.ADMIN_IDS:
            full_admin_command_list = general_commands + admin_only_commands
            for admin_id in settings.ADMIN_IDS:
                try:
                    await application.bot.set_my_commands(full_admin_command_list, scope={"type": "chat", "chat_id": admin_id})
                except Exception as e_admin_scope:
                    logger.error(f"Failed to set scoped commands for admin {admin_id}: {e_admin_scope}")
            logger.info(f"Admin-specific commands scoped for {len(settings.ADMIN_IDS)} admin(s).")
    except Exception as e:
        logger.error(f"Error setting bot commands during post_init: {e}", exc_info=True)

    if application.job_queue:
        application.job_queue.run_repeating(
            core_handlers.check_expired_premiums_job,
            interval=timedelta(hours=1),
            first=timedelta(seconds=10),
            name="check_expired_premiums"
        )
        logger.info("Periodic job 'check_expired_premiums' scheduled.")
    else:
        logger.warning("Job Queue not available. Periodic tasks will not run.")


async def main_bot_loop():
    """Initializes, starts, and runs the PTB application's polling loop."""
    logger.info("========================================")
    logger.info("🚀 Initializing Anime Realm Bot PTB Application...")
    # ... (logging other settings as before) ...
    logger.info("========================================")

    bot_defaults = Defaults(parse_mode=settings.DEFAULT_PARSE_MODE, block=False)
    application = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .defaults(bot_defaults)
        .post_init(post_init)
        .build()
    )

    # --- Register All Handlers (same as previous full main.py) ---
    application.add_handler(CommandHandler("start", core_handlers.start_command))
    application.add_handler(CommandHandler("help", core_handlers.help_command))
    application.add_handler(CommandHandler("cancel", core_handlers.cancel_command))
    application.add_error_handler(core_handlers.error_handler)
    application.add_handler(CommandHandler("profile", user_cmds.profile_command))
    application.add_handler(CommandHandler("premium", user_cmds.premium_info_command))
    application.add_handler(CommandHandler("gen_tokens", token_system.generate_and_show_token_link_command))
    application.add_handler(anime_search.get_search_conv_handler())
    application.add_handler(CommandHandler("search", anime_search.search_anime_command_entry, block=False))
    application.add_handler(CommandHandler("browse", anime_browser.browse_start_command))
    application.add_handler(CommandHandler("popular", anime_browser.popular_anime_command))
    application.add_handler(CommandHandler("latest", anime_browser.latest_anime_command))
    application.add_handler(CommandHandler("my_watchlist", watchlist.view_watchlist_command))
    application.add_handler(CommandHandler("view_watchlist", watchlist.view_watchlist_command))
    application.add_handler(CommandHandler("request", anime_requests.request_anime_command,
                                           filters=~filters.User(settings.ADMIN_IDS) & filters.ChatType.PRIVATE))
    admin_filter = filters.User(settings.ADMIN_IDS) & filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("grant_premium", admin_cmds.grant_premium_command, filters=admin_filter))
    application.add_handler(CommandHandler("revoke_premium", admin_cmds.revoke_premium_command, filters=admin_filter))
    application.add_handler(CommandHandler("add_tokens", admin_cmds.add_tokens_command, filters=admin_filter))
    application.add_handler(CommandHandler("remove_tokens", admin_cmds.remove_tokens_command, filters=admin_filter))
    application.add_handler(CommandHandler("user_info", admin_cmds.user_info_command, filters=admin_filter))
    application.add_handler(admin_cmds.get_broadcast_conv_handler())
    application.add_handler(CommandHandler("bot_stats", admin_cmds.bot_stats_command, filters=admin_filter))
    application.add_handler(content_manager.get_manage_content_conv_handler())
    application.add_handler(CallbackQueryHandler(callback_handlers.main_callback_handler))
    logger.info("All handlers registered.")

    # --- Start PTB Polling ---
    try:
        logger.info("PTB Application initializing...")
        await application.initialize()
        logger.info("PTB Application starting updater and polling...")
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES, poll_interval=0.2, timeout=20, read_latency=5.0)
        logger.info("✅ PTB Polling started successfully and bot is running.")
        while True:
            await asyncio.sleep(3600) # Keep this loop alive
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
        logger.info("Shutting down PTB application...")
        await application.shutdown()
        logger.info("✅ PTB Application shutdown complete.")


async def amain_orchestrator():
    """Orchestrates the bot and the simple health check server."""
    aiohttp_app = web.Application()
    aiohttp_app.router.add_get("/healthz", simple_health_check_handler)
    aiohttp_app.router.add_get("/", simple_health_check_handler)
    runner = web.AppRunner(aiohttp_app)

    health_server_task = asyncio.create_task(start_simple_health_check_server(runner))
    bot_task = asyncio.create_task(main_bot_loop())

    try:
        done, pending = await asyncio.wait(
            [bot_task, health_server_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            logger.info(f"Cancelling pending task from orchestrator: {task.get_name()}")
            task.cancel()
            try: await task
            except asyncio.CancelledError: logger.info(f"Task {task.get_name()} (orchestrator cancel) successfully cancelled.")
            except Exception as e_task_cancel: logger.error(f"Error during cancellation of {task.get_name()}: {e_task_cancel}")
        for task in done:
            if task.exception():
                logger.error(f"Task {task.get_name()} completed with exception: {task.exception()}", exc_info=task.exception())
    except KeyboardInterrupt:
        logger.info("Main orchestrator (simple health check) received KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"CRITICAL - Unhandled exception in main orchestrator (simple health check): {e}", exc_info=True)
    finally:
        logger.info("Main orchestrator (simple health check): Final cleanup initiated...")
        all_tasks = [bot_task, health_server_task]
        for task in all_tasks:
            if not task.done():
                if not task.cancelled(): task.cancel()
                try: await task
                except asyncio.CancelledError: pass
                except Exception as e: logger.error(f"Error ensuring task {task.get_name()} is finished in orchestrator: {e}")
        logger.info("👋 Main orchestrator (simple health check) shutdown complete.")


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO # Initial log level
    )
    logger.info("Script execution started (simple health check variant).")
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
