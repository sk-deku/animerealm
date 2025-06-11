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
    PicklePersistence, # Optional: for persisting bot/user/chat data across restarts
    filters
)
from telegram.constants import ParseMode

from aiohttp import web # For the health check server

# Import configurations
from configs import settings
from configs import strings

# Import database instance (or functions if not using a class singleton)
from database.mongo_db import db as anidb # Assuming mongo_db.py defines 'db' as the Database instance

# Import bot handlers from the 'bot' package
from bot import core_handlers, admin_cmds, user_cmds, \
                anime_browser, anime_search, anime_requests, \
                content_manager, downloads, watchlist, token_system, \
                callback_handlers

# Configure logging
logger = logging.getLogger(__name__)

# --- Health Check Server ---
async def health_check_handler(request):
    """Simple health check endpoint."""
    bot_info = await application.bot.get_me()
    return web.json_response({
        "status": "ok",
        "bot_username": bot_info.username,
        "bot_name": bot_info.first_name
    }, status=200)

async def run_health_check_server():
    app = web.Application()
    app.router.add_get("/healthz", health_check_handler) # Common health check path
    app.router.add_get("/", health_check_handler)      # Root path for basic check

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.HEALTH_CHECK_HOST, settings.HEALTH_CHECK_PORT)
    logger.info(f"🚀 Health check server starting on http://{settings.HEALTH_CHECK_HOST}:{settings.HEALTH_CHECK_PORT}")
    await site.start()
    # Keep the server running in the background
    # This will run indefinitely until the main bot task is cancelled
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep for a long time, server runs via asyncio tasks
    except asyncio.CancelledError:
        logger.info("Health check server shutting down...")
        await runner.cleanup()
        logger.info("Health check server stopped.")


# --- Main Bot Application Setup ---
async def post_init(application: Application):
    """Post-initialization tasks, like setting bot commands."""
    commands = [
        BotCommand("start", "🌟 Start or restart the bot"),
        BotCommand("help", "❓ Get help and command list"),
        BotCommand("search", "🔍 Search for an anime"),
        BotCommand("browse", "📚 Browse anime by genre/status"),
        BotCommand("popular", "🔥 View popular anime"),
        BotCommand("latest", "🆕 See latest episode additions"),
        BotCommand("my_watchlist", "💖 Manage your watchlist"),
        BotCommand("profile", "👤 View your profile & tokens"),
        BotCommand("gen_tokens", "🔗 Generate link and Earn Tokens"),
        BotCommand("premium", "💎 View premium options"),
        BotCommand("cancel", "❌ Cancel current operation"),
    ]
    admin_commands = [
        BotCommand("manage_content", "🛠️ Manage anime content (Admin)"),
        BotCommand("grant_premium", "👑 Grant premium (Admin)"),
        BotCommand("revoke_premium", "🚫 Revoke premium (Admin)"),
        BotCommand("add_tokens", "🪙 Add tokens to user (Admin)"),
        BotCommand("remove_tokens", "➖ Remove tokens from user (Admin)"),
        BotCommand("broadcast", "📣 Broadcast message (Admin)"),
        BotCommand("user_info", "ℹ️ Get user details (Admin)"),
        BotCommand("bot_stats", "📊 View bot statistics (Admin)"),
    ]
    # For now, setting general commands for all.
    # Scoped commands (per user/admin) can be set too but are more complex.
    await application.bot.set_my_commands(commands + admin_commands)
    logger.info("Bot commands set successfully.")

    # Start periodic tasks (like checking expired premiums) if using JobQueue
    if application.job_queue:
        # Example: Check for expired premiums every hour
        application.job_queue.run_repeating(
            core_handlers.check_expired_premiums_job,
            interval=3600, # 1 hour
            first=10 # Run 10 seconds after start
        )
        logger.info("Periodic job for checking expired premiums scheduled.")


application: Application | None = None # Global for health check access, not ideal but simple

async def main():
    global application
    logger.info("========================================")
    logger.info("🚀 Starting Anime Realm Bot...")
    logger.info(f"Version: 1.0.0 (Conceptual)") # Add a version if you have one
    logger.info(f"Admin IDs: {settings.ADMIN_IDS}")
    logger.info(f"Debug Mode: {settings.DEBUG_MODE}")
    logger.info("========================================")


    # --- Persistence (Optional) ---
    # persistence = PicklePersistence(filepath="anime_realm_bot_persistence")
    # Using PicklePersistence can store user_data, chat_data, bot_data.
    # Be careful with sensitive info if you use it. For DB-centric bots, it's often less needed.

    # --- Defaults ---
    # Set default parse mode for all messages sent by the bot
    bot_defaults = Defaults(parse_mode=settings.DEFAULT_PARSE_MODE, block=False) # block=False for non-blocking sends

    application = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .defaults(bot_defaults)
        .post_init(post_init) # For setting commands etc. after bot is ready
        # .persistence(persistence) # Uncomment to enable persistence
        .build()
    )

    # --- Core Handlers ---
    application.add_handler(CommandHandler("start", core_handlers.start_command))
    application.add_handler(CommandHandler("help", core_handlers.help_command))
    application.add_handler(CommandHandler("cancel", core_handlers.cancel_command, filters=filters.User(settings.ADMIN_IDS) | filters.COMMAND)) # Allow admin always, others via /cancel
    application.add_error_handler(core_handlers.error_handler)


    # --- User Command Handlers ---
    application.add_handler(CommandHandler("profile", user_cmds.profile_command))
    application.add_handler(CommandHandler("premium", user_cmds.premium_info_command))
    application.add_handler(CommandHandler("gen_tokens", token_system.generate_and_show_token_link_command)) # User generates link


    # --- Anime Discovery Handlers ---
    # Search can be a Conversation or direct command + message
    application.add_handler(anime_search.get_search_conv_handler()) # Conversation for search
    application.add_handler(CommandHandler("search", anime_search.search_anime_command_entry)) # Direct /search [query] entry

    application.add_handler(CommandHandler("browse", anime_browser.browse_start_command))
    application.add_handler(CommandHandler("popular", anime_browser.popular_anime_command))
    application.add_handler(CommandHandler("latest", anime_browser.latest_anime_command))


    # --- Watchlist Handlers ---
    application.add_handler(CommandHandler("my_watchlist", watchlist.view_watchlist_command))
    application.add_handler(CommandHandler("view_watchlist", watchlist.view_watchlist_command)) # if linked from /profile via ?start=


    # --- Download Handlers (will likely be triggered by Callbacks from episode lists) ---
    # No direct command, but download logic in downloads.py will be used by callbacks.


    # --- Anime Request Handlers ---
    application.add_handler(CommandHandler("request", anime_requests.request_anime_command, filters=~filters.User(settings.ADMIN_IDS))) # For non-admins
    # Free user request (triggered by callback from search no results) is handled in callbacks

    # --- Admin Command Handlers ---
    application.add_handler(CommandHandler("grant_premium", admin_cmds.grant_premium_command, filters=filters.User(settings.ADMIN_IDS)))
    application.add_handler(CommandHandler("revoke_premium", admin_cmds.revoke_premium_command, filters=filters.User(settings.ADMIN_IDS)))
    application.add_handler(CommandHandler("add_tokens", admin_cmds.add_tokens_command, filters=filters.User(settings.ADMIN_IDS)))
    application.add_handler(CommandHandler("remove_tokens", admin_cmds.remove_tokens_command, filters=filters.User(settings.ADMIN_IDS)))
    application.add_handler(CommandHandler("user_info", admin_cmds.user_info_command, filters=filters.User(settings.ADMIN_IDS)))
    application.add_handler(CommandHandler("broadcast", admin_cmds.broadcast_start_command, filters=filters.User(settings.ADMIN_IDS))) # Start of broadcast conversation
    application.add_handler(CommandHandler("bot_stats", admin_cmds.bot_stats_command, filters=filters.User(settings.ADMIN_IDS)))


    # --- Admin Content Management Conversation Handler ---
    application.add_handler(content_manager.get_manage_content_conv_handler())
    # Entry point for content management (could be a command or callback from an admin panel)
    application.add_handler(CommandHandler("manage_content", content_manager.manage_content_start, filters=filters.User(settings.ADMIN_IDS)))


    # --- General Callback Query Handler (MUST be last among CallbackQueryHandlers or very generic) ---
    # Specific callbacks for complex flows (like conversations) should be part of those handlers.
    # This one handles generic buttons like pagination, back buttons, simple actions.
    application.add_handler(CallbackQueryHandler(callback_handlers.main_callback_handler))

    # --- Message Handler (Optional - for direct text input like search after /search, if not using Conversation)
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, core_handlers.handle_text_message))


    # --- Run the bot and the health check server concurrently ---
    health_server_task = asyncio.create_task(run_health_check_server())

    logger.info("🤖 Bot is polling...")
    # Run the bot until the user presses Ctrl-C
    try:
        await application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"An unexpected error occurred in application.run_polling: {e}", exc_info=True)
    finally:
        logger.info("Initiating shutdown sequence...")
        # Cancel the health server task explicitly
        if health_server_task and not health_server_task.done():
            health_server_task.cancel()
            try:
                await health_server_task # Wait for it to clean up
            except asyncio.CancelledError:
                logger.info("Health server task successfully cancelled.")
        # PTB application cleanup is handled internally by run_polling's context manager

        # Close MongoDB client if you initialized it in a way that needs explicit closing
        # (The current `mongo_db.py` creates a global client that persists; explicit close good for cleanup scripts)
        # if anidb.client:
        #     logger.info("Closing MongoDB connection...")
        #     anidb.client.close()
        #     logger.info("MongoDB connection closed.")
        logger.info("👋 Bot shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit as e:
        logger.critical(f"System exit called: {e}")
    except Exception as e:
        logger.critical(f"CRITICAL - Unhandled exception in main execution block: {e}", exc_info=True)
