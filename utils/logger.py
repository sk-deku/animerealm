from pyrogram import Client
from pyrogram.enums import ParseMode # <--- IMPORT IT
import config
import logging

LOGGER = logging.getLogger(__name__)

async def log_to_channel(client: Client, channel_id: int | None, message: str, parse_mode_enum=None): # Changed arg name for clarity
    if channel_id:
        try:
            await client.send_message(
                chat_id=channel_id, 
                text=message, 
                disable_web_page_preview=True,
                parse_mode=parse_mode_enum # Use the passed enum
            )
        except Exception as e:
            LOGGER.error(f"Failed to log to channel {channel_id}: {e}")
    else:
        LOGGER.info(f"Log (channel not set): {message}")


async def log_bot_event(client: Client, message: str, parse_mode_enum=None): # Changed arg name
    LOGGER.info(message)
    await log_to_channel(client, config.BOT_LOG_CHANNEL_ID, f"**BOT LOG:**\n{message}", parse_mode_enum=parse_mode_enum)

async def log_request_event(client: Client, message: str, parse_mode_enum=None): # Changed arg name
    LOGGER.info(f"Request Event: {message}")
    await log_to_channel(client, config.REQUEST_LOG_CHANNEL_ID, f"**REQUEST EVENT:**\n{message}", parse_mode_enum=parse_mode_enum)

async def log_file_event(client: Client, message: str, parse_mode_enum=None): # Changed arg name
    LOGGER.info(f"File Event: {message}")
    await log_to_channel(client, config.FILE_LOG_CHANNEL_ID, f"**FILE EVENT:**\n{message}", parse_mode_enum=parse_mode_enum)

async def log_admin_action(client: Client, admin_user_mention: str, action: str, details: str = ""):
    log_msg = f"🔑 **ADMIN ACTION** by {admin_user_mention}:\n**Action:** {action}\n**Details:** {details if details else 'N/A'}"
    LOGGER.info(log_msg)
    # When calling, ensure admin_user_mention is already HTML formatted or pass ParseMode.HTML
    await log_to_channel(client, config.BOT_LOG_CHANNEL_ID, log_msg, parse_mode_enum=ParseMode.HTML)
