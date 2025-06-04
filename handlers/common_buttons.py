from pyrogram import Client, filters
from pyrogram.types import CallbackQuery
from pyrogram.enums import ParseMode
import config
import strings
from utils.keyboard_utils import get_common_secondary_keyboard
from database.operations import (
    get_anime_count, get_episode_count_all_versions, get_distinct_file_count,
    get_total_users_count, get_premium_users_count, get_user
)
from database.connection import db as database_instance
from database.connection import db
from utils.logger import log_bot_event
from datetime import date
from pyrogram.errors import MessageNotModified, MediaCaptionTooLong # Add MediaCaptionTooLong
from utils.logger import LOGGER

@Client.on_callback_query(filters.regex(r"^all_commands$"))
async def all_commands_handler(client: Client, callback_query: CallbackQuery):
    text_to_send = strings.ALL_COMMANDS_TEXT
    reply_markup_to_send = get_common_secondary_keyboard()
    
    try:
        if callback_query.message.photo:
            await callback_query.edit_message_caption(
                caption=strings.ALL_COMMANDS_TEXT,
                reply_markup=get_common_secondary_keyboard(),
                parse_mode=ParseMode.HTML
            )
        else:
            await callback_query.edit_message_text(
                text=strings.ALL_COMMANDS_TEXT,
                reply_markup=get_common_secondary_keyboard(),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
    except MessageNotModified:
        pass
    except MediaCaptionTooLong:
        LOGGER.error("MEDIA_CAPTION_TOO_LONG in all_commands_handler. Sending as new message.")
        await callback_query.message.reply_text( # Send as new if caption too long
            text=strings.ALL_COMMANDS_TEXT,
            reply_markup=get_common_secondary_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        LOGGER.info(f"Error in all_commands_handler edit: {e}")
        # Fallback for other errors
        await callback_query.message.reply_text(
            text=strings.ALL_COMMANDS_TEXT,
            reply_markup=get_common_secondary_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    finally:
        await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^about_bot$"))
async def about_bot_handler(client: Client, callback_query: CallbackQuery):
    anime_count = await get_anime_count()
    episode_count_versions = await get_episode_count_all_versions()
    # distinct_files_count = await get_distinct_file_count() # This was complex, using total versions for now for file count
    db_stats_str = await database_instance.get_db_stats()
    total_users = await get_total_users_count()
    premium_users = await get_premium_users_count()

    about_text = strings.get_about_text(
        anime_count, episode_count_versions, episode_count_versions, # Using episode_count_versions for file_count too
        db_stats_str, total_users, premium_users
    )
    try:
        await callback_query.edit_message_text(
            text=about_text,
            reply_markup=get_common_secondary_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        await log_bot_event(client, f"Error in about_bot_handler edit: {e}")
        await callback_query.message.reply_text(
            text=about_text,
            reply_markup=get_common_secondary_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^my_stats$"))
@Client.on_message(filters.command("mystats")) # Allow command too
async def my_stats_handler(client: Client, message_or_callback_query):
    is_callback = isinstance(message_or_callback_query, CallbackQuery)
    if is_callback:
        user = message_or_callback_query.from_user
        message = message_or_callback_query.message
        await message_or_callback_query.answer()
    else:
        user = message_or_callback_query.from_user
        message = message_or_callback_query

    user_data = await get_user(user.id)
    if not user_data:
        await message.reply_text("Could not fetch your stats. Please /start the bot first.")
        return

    tokens = user_data.get('download_tokens', 0)
    is_premium_val = user_data.get('is_premium', False)
    is_premium_str = "✅ Active" if is_premium_val else "❌ Inactive"
    premium_details = ""
    if is_premium_val and user_data.get('premium_expiry_date'):
        premium_details = f"Expires on: {user_data['premium_expiry_date'].strftime('%Y-%m-%d %H:%M UTC')}"
    
    watchlist_count = len(user_data.get('watchlist', []))
    # To get requests_made, we need to query anime_requests collection (not done here for brevity)
    # For now, let's assume it's 0 or fetch it if critical.
    requests_made_count = await db.anime_requests.count_documents({'user_id': user.id})


    downloads_today = 0
    if user_data.get('last_download_date') == date.today():
        downloads_today = user_data.get('downloads_today', 0)
    
    download_limit_str = str(config.FREE_USER_DOWNLOAD_LIMIT_PER_DAY) if not is_premium_val else "Unlimited"

    join_date_str = user_data.get('join_date').strftime('%Y-%m-%d') if user_data.get('join_date') else "N/A"

    stats_text = strings.MY_STATS_TEXT.format(
        tokens=tokens,
        is_premium=is_premium_str,
        premium_details=premium_details,
        watchlist_count=watchlist_count,
        requests_made=requests_made_count,
        downloads_today=downloads_today,
        download_limit=download_limit_str,
        join_date=join_date_str
    )

    reply_markup = get_common_secondary_keyboard() if is_callback else None # No back for command
    
    if is_callback:
        try:
            await message.edit_text(stats_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except: # If edit fails, send new
             await message.reply_text(stats_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await message.reply_text(stats_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
