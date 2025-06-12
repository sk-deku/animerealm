# bot/commands.py
import logging
from telegram import BotCommand
from telegram.ext import Application
from configs import settings # To get ADMIN_IDS

logger = logging.getLogger(__name__)

async def set_bot_commands(application: Application):
    """
    Sets the bot commands for general users and admins.
    """
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
        BotCommand("cancel_cm", "❌ Cancel Content Management"),
    ]

    try:
        # Set general commands for the default scope (all users)
        await application.bot.set_my_commands(general_commands)
        logger.info("General bot commands set globally.")

        # Set scoped commands for each admin ID
        # Admins will see general_commands + admin_only_commands
        if settings.ADMIN_IDS:
            full_admin_command_list = general_commands + admin_only_commands
            for admin_id in settings.ADMIN_IDS:
                try:
                    # Setting commands for a specific private chat with the admin
                    await application.bot.set_my_commands(
                        full_admin_command_list,
                        scope={"type": "chat", "chat_id": admin_id}
                    )
                except Exception as e_admin_scope:
                    logger.error(f"Failed to set scoped commands for admin {admin_id}: {e_admin_scope}")
            logger.info(f"Admin-specific commands scoped for {len(settings.ADMIN_IDS)} admin(s).")
        else:
            logger.warning("No ADMIN_IDS configured in settings. Admin commands will not be specially scoped.")

    except Exception as e:
        logger.error(f"Error setting bot commands: {e}", exc_info=True)
