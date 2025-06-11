# bot/downloads.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from bson import ObjectId # If anime_id needs conversion, though usually passed as string

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance
from .core_handlers import check_user_or_add

logger = logging.getLogger(__name__)

# --- Download Callback Handler ---
async def handle_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the callback when a user clicks a download button for a specific file version.
    Callback data format: "dl_{anime_id_str}_{season_num}_{episode_num}_{version_index_in_db_array}"
    """
    query = update.callback_query
    await query.answer(text=f"{strings.EMOJI_LOADING} Preparing your file...") # Quick ack

    user = update.effective_user
    callback_data = query.data

    user_db_doc = await check_user_or_add(update, context)
    if not user_db_doc:
        await query.edit_message_text(text=strings.GENERAL_ERROR + " (User check failed)",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        return

    is_premium_user = user_db_doc.get("premium_status", False)
    current_tokens = user_db_doc.get("download_tokens", 0)
    token_cost_per_download = 1 # Assuming 1 token per file, can be made configurable

    try:
        parts = callback_data.split("_")
        action_prefix = parts[0] # "dl"
        anime_id_str = parts[1]
        season_num = int(parts[2])
        episode_num = int(parts[3])
        version_idx_in_db = int(parts[4]) # Index of the version in the episode's versions array
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid download callback data format: {callback_data} - Error: {e}")
        await query.edit_message_text(text=f"{strings.EMOJI_ERROR} Invalid download link. Please try again from the episode list.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        return

    # Fetch anime details to get the file version info
    anime_doc = await anidb.get_anime_by_id_str(anime_id_str)
    if not anime_doc:
        await query.edit_message_text(text=f"{strings.EMOJI_ERROR} Anime details not found. It might have been removed.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        return

    # Find the specific episode and version
    selected_version_doc = None
    selected_episode_doc = None # For file caption later
    for s_doc in anime_doc.get("seasons", []):
        if s_doc.get("season_number") == season_num:
            for ep_doc in s_doc.get("episodes", []):
                if ep_doc.get("episode_number") == episode_num:
                    selected_episode_doc = ep_doc # Found the episode
                    if ep_doc.get("versions") and len(ep_doc.get("versions")) > version_idx_in_db:
                        selected_version_doc = ep_doc["versions"][version_idx_in_db]
                    break
            break
    
    if not selected_version_doc:
        logger.error(f"Could not find version index {version_idx_in_db} for anime {anime_id_str} S{season_num}E{episode_num}")
        await query.edit_message_text(text=f"{strings.EMOJI_ERROR} File version not found. It might have been updated or removed. Please try again from the episode list.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        return

    file_id_to_send = selected_version_doc.get("file_id")
    file_type = selected_version_doc.get("file_type", "document") # Default to document
    resolution = selected_version_doc.get("resolution")

    if not file_id_to_send:
        logger.error(f"No file_id found in selected version doc: {selected_version_doc}")
        await query.edit_message_text(text=f"{strings.EMOJI_ERROR} File ID missing for this version. Please contact admin.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        return

    # --- Permission Checks ---
    # 1. Premium resolution check for free users
    if not is_premium_user and resolution in settings.PREMIUM_ONLY_RESOLUTIONS:
        premium_note = strings.PREMIUM_RESOLUTION_NOTE_FREE_USER # From strings.py
        await query.edit_message_text(
            text=f"{strings.EMOJI_PREMIUM} This resolution (<b>{resolution}</b>) is for Premium users only.\n{premium_note}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(strings.BTN_PREMIUM, callback_data="core_premium_info")],
                [InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Versions", callback_data=f"viewvers_{anime_id_str}_{season_num}_{episode_num}")]
            ]),
            parse_mode=ParseMode.HTML
        )
        return

    # 2. Token check for non-premium users
    if not is_premium_user:
        if current_tokens < token_cost_per_download:
            await query.edit_message_text(
                text=strings.NOT_ENOUGH_TOKENS.format(required_tokens=token_cost_per_download, current_tokens=current_tokens) +
                     f"\n\nEarn more tokens via /gen_tokens or go /premium for unlimited downloads!",
                reply_markup=InlineKeyboardMarkup([
                     [InlineKeyboardButton(strings.BTN_GET_TOKENS, callback_data="core_get_tokens_info")],
                     [InlineKeyboardButton(strings.BTN_PREMIUM, callback_data="core_premium_info")],
                     [InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Versions", callback_data=f"viewvers_{anime_id_str}_{season_num}_{episode_num}")]
                ]),
                parse_mode=ParseMode.HTML
            )
            return
    
    # --- Proceed with sending file ---
    # Delete the "Select Version" message before sending the file to reduce clutter
    try:
        await query.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete 'select version' message before sending file: {e}")

    # Send a "preparing" message as file sending can take time
    status_message_sent_to_user = await context.bot.send_message(
        chat_id=user.id,
        text=strings.FILE_TRANSFER_START.format(
            anime_title=anime_doc.get("title_english", "N/A"),
            s_num=season_num,
            ep_num=f"{episode_num:02d}"
        ),
        parse_mode=ParseMode.HTML
    )
    
    file_caption = strings.FILE_DETAILS_CAPTION.format(
        title_english=anime_doc.get("title_english", "N/A"),
        season_num=season_num,
        episode_num=f"{episode_num:02d}", # Assuming episode_num is integer
        # episode_title=selected_episode_doc.get("episode_title", ""), # if titles are stored
        resolution=resolution,
        audio_lang=selected_version_doc.get("audio_language", "N/A"),
        sub_lang=selected_version_doc.get("subtitle_language", "N/A"),
        file_size_mb=round(selected_version_doc.get("file_size_bytes", 0) / (1024*1024), 1),
        BOT_USERNAME=settings.BOT_USERNAME
    )

    try:
        if file_type == "video":
            await context.bot.send_video(
                chat_id=user.id,
                video=file_id_to_send,
                caption=file_caption,
                parse_mode=ParseMode.HTML
                # Add other video parameters like duration, width, height if available and needed
            )
        else: # Default to document
            await context.bot.send_document(
                chat_id=user.id,
                document=file_id_to_send,
                caption=file_caption,
                parse_mode=ParseMode.HTML
            )
        
        # --- Post-download actions ---
        # 1. Deduct tokens if not premium
        if not is_premium_user:
            await anidb.update_user_tokens(user.id, -token_cost_per_download)
            logger.info(f"Deducted {token_cost_per_download} token(s) from user {user.id} for download.")
            # No need to explicitly notify user of token deduction here, implicitly done by download

        # 2. Increment anime download count
        await anidb.increment_anime_download_count(anime_id_str)

        # 3. Log download event (e.g., to USER_LOGS_CHANNEL_ID)
        if settings.USER_LOGS_CHANNEL_ID:
            log_msg = strings.LOG_DOWNLOAD_COMPLETED.format(
                user_id=user.id, user_first_name=user.first_name,
                anime_title=anime_doc.get("title_english", "N/A"),
                season_num=season_num, episode_num=f"{episode_num:02d}",
                version_details=f"{resolution}, {selected_version_doc.get('audio_language', '')}, {selected_version_doc.get('subtitle_language', '')}"
            )
            try:
                await context.bot.send_message(settings.USER_LOGS_CHANNEL_ID, log_msg, parse_mode=ParseMode.HTML)
            except Exception as log_e:
                 logger.error(f"Failed to send download log to channel: {log_e}")
        
        # Optionally, log to a separate download_logs collection in DB for detailed analytics
        # await anidb.log_user_download(user.id, anime_id_str, file_id_to_send)

    except Exception as e:
        logger.error(f"Error sending file {file_id_to_send} (type: {file_type}) to user {user.id}: {e}", exc_info=True)
        # Notify user of failure
        await context.bot.send_message(
            chat_id=user.id,
            text=strings.FILE_TRANSFER_ERROR + f"\n\nIf this persists, please screenshot this and report to an admin regarding: Anime ID <code>{anime_id_str}</code>, S{season_num}E{episode_num}, VersionIdx {version_idx_in_db}.",
            parse_mode=ParseMode.HTML
        )
    finally:
        # Delete the "Preparing your file..." status message
        if status_message_sent_to_user:
            try:
                await context.bot.delete_message(chat_id=user.id, message_id=status_message_sent_to_user.message_id)
            except Exception as del_e:
                logger.debug(f"Could not delete status message: {del_e}")
