from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode
from bson import ObjectId
import config
import strings
from utils.keyboard_utils import get_download_confirmation_keyboard, noop_keyboard
from database.operations import (
    get_user, get_episode_by_id, get_anime_by_id, update_user_tokens, can_download_today, record_download,
    increment_anime_download_count, increment_episode_download_count
)
from utils.logger import log_bot_event
from utils.logger import log_bot_event, LOGGER

# When user clicks an episode version from the list (e.g., "1080p SUB")
@Client.on_callback_query(filters.regex(r"^dl_epver:(\w+)$"))
async def download_episode_version_prompt_cb(client: Client, cb: CallbackQuery):
    episode_version_id_str = cb.matches[0].group(1)
    user_id = cb.from_user.id
    
    user_data = await get_user(user_id)
    if not user_data: # Should not happen
        await cb.answer("User data not found. Please /start again.", show_alert=True)
        return

    if not user_data['is_premium']:
        # Check daily download limit for free users
        if not await can_download_today(user_id):
            await cb.answer(strings.DOWNLOAD_DAILY_LIMIT_REACHED.format(limit=config.FREE_USER_DOWNLOAD_LIMIT_PER_DAY), show_alert=True)
            return

        # Check token balance
        user_tokens = user_data.get('download_tokens', 0)
        if user_tokens < 1: # Assuming 1 token per download
            await cb.answer(strings.TOKEN_NEEDED_FOR_DOWNLOAD.format(tokens_needed=1, user_tokens=user_tokens), show_alert=True)
            return
        
        # Show confirmation for token usage
        await cb.edit_message_text(
            strings.DOWNLOAD_CONFIRMATION.format(user_tokens=user_tokens),
            reply_markup=get_download_confirmation_keyboard(episode_version_id_str)
        )
        await cb.answer()
    else:
        # Premium user, proceed to download directly
        await cb.answer("Premium User: Preparing download...")
        await process_file_download(client, user_id, cb.message.chat.id, episode_version_id_str)
        # Edit the message to show download started, or clear buttons
        try:
            episode = await get_episode_by_id(episode_version_id_str)
            ep_name = episode.get('episode_title', f"Episode {episode.get('episode_number','N/A')}") if episode else "Selected Episode"
            await cb.edit_message_text(
                strings.DOWNLOAD_STARTED.format(file_name=ep_name), 
                reply_markup=noop_keyboard() # Or back button
            )
        except Exception as e:
            await log_bot_event(client, f"Error editing message after premium dl start: {e}")

# User confirms download (for free users after token check)
@Client.on_callback_query(filters.regex(r"^dl_confirm_yes:(\w+)$"))
async def download_confirm_yes_cb(client: Client, cb: CallbackQuery):
    episode_version_id_str = cb.matches[0].group(1)
    user_id = cb.from_user.id

    user_data = await get_user(user_id) # Re-fetch for safety
    if not user_data or user_data['is_premium']: # Should be free user here
        await cb.answer("Invalid state for token download.", show_alert=True); return

    if not await can_download_today(user_id): # Double check limit
        await cb.answer(strings.DOWNLOAD_DAILY_LIMIT_REACHED.format(limit=config.FREE_USER_DOWNLOAD_LIMIT_PER_DAY), show_alert=True)
        return

    user_tokens = user_data.get('download_tokens', 0)
    if user_tokens < 1:
        await cb.answer(strings.TOKEN_NEEDED_FOR_DOWNLOAD.format(tokens_needed=1, user_tokens=user_tokens), show_alert=True)
        return
        
    await update_user_tokens(user_id, -1) # Deduct token
    await cb.answer("Token used. Preparing download...")
    
    # Edit the message (important: this happens BEFORE file sending)
    episode = await get_episode_by_id(episode_version_id_str)
    ep_name = episode.get('episode_title', f"Episode {episode.get('episode_number','N/A')}") if episode else "Selected Episode"
    try:
        await cb.edit_message_text(strings.DOWNLOAD_STARTED.format(file_name=ep_name), reply_markup=noop_keyboard())
    except Exception as e:
        await log_bot_event(client, f"Error editing msg after token confirm dl: {e}")

    await process_file_download(client, user_id, cb.message.chat.id, episode_version_id_str)


async def process_file_download(client: Client, user_id: int, chat_id: int, episode_version_id_str: str):
    episode_version = await get_episode_by_id(episode_version_id_str)

    if not episode_version or not episode_version.get('file_id'):
        await client.send_message(chat_id, strings.FILE_NOT_FOUND_ON_TELEGRAM)
        await log_bot_event(client, f"File ID missing for episode_version_id {episode_version_id_str}")
        return

    file_id_to_send = episode_version['file_id']
    
    # Attempt to create a more descriptive file name for the user
    anime_title_for_filename = "Anime" # Default
    anime_doc_for_filename = await get_anime_by_id(episode_version['anime_id'])
    if anime_doc_for_filename:
        anime_title_for_filename = anime_doc_for_filename.get('title', 'Anime')

    file_name_display = (f"{anime_title_for_filename} - "
                         f"S{episode_version.get('season_number','S?')}E{episode_version.get('episode_number','E?')} - "
                         f"{episode_version.get('episode_title', '')} "
                         f"[{episode_version.get('quality','Q?')} {episode_version.get('audio_type','A?')}].mkv") # Default to .mkv or get from file info if stored

    caption_text = f"Downloaded: {file_name_display}\n\nEnjoy! @{config.BOT_USERNAME}"
    sent_successfully = False

    try:
        # Attempt 1: Send as video
        LOGGER.info(f"Attempting to send file_id {file_id_to_send} as VIDEO to user {user_id}")
        await client.send_video(
            chat_id=chat_id,
            video=file_id_to_send,
            caption=caption_text
        )
        sent_successfully = True
        LOGGER.info(f"Successfully sent file_id {file_id_to_send} as VIDEO to user {user_id}")

    except Exception as e_video: # Catch a broad exception first
        LOGGER.warning(f"Failed to send file_id {file_id_to_send} as VIDEO to user {user_id}. Error: {e_video}")
        # Check if the error message indicates it's a document
        if "document file id instead" in str(e_video).lower() or \
           (isinstance(e_video, BadRequest) and "FILE_ID_INVALID" in str(e_video).upper()): # Heuristic for wrong type
            
            LOGGER.info(f"Falling back to send file_id {file_id_to_send} as DOCUMENT for user {user_id}")
            try:
                # Attempt 2: Send as document
                await client.send_document(
                    chat_id=chat_id,
                    document=file_id_to_send,
                    caption=caption_text,
                    file_name=file_name_display # Helps user save with a good name
                )
                sent_successfully = True
                LOGGER.info(f"Successfully sent file_id {file_id_to_send} as DOCUMENT to user {user_id}")
            except Exception as e_document:
                LOGGER.error(f"Failed to send file_id {file_id_to_send} as DOCUMENT to user {user_id} after video attempt failed. Error: {e_document}", exc_info=True)
                await client.send_message(chat_id, strings.SOMETHING_WENT_WRONG + f"\nError: Could not send file. Admins notified.")
        else:
            # Different error while trying to send as video
            LOGGER.error(f"Unexpected error sending file_id {file_id_to_send} as VIDEO to user {user_id}: {e_video}", exc_info=True)
            await client.send_message(chat_id, strings.SOMETHING_WENT_WRONG + f"\nError: Could not send video. Admins notified.")

    if sent_successfully:
        try:
            await record_download(user_id, episode_version['anime_id'], episode_version['_id'])
            await increment_anime_download_count(episode_version['anime_id'])
            await increment_episode_download_count(episode_version['_id'])
            await log_bot_event(client, f"User {user_id} successfully downloaded episode file: {file_id_to_send} (EpVerID: {episode_version_id_str})")
        except Exception as e_log:
            LOGGER.error(f"Error recording download stats for user {user_id}, episode {episode_version_id_str}: {e_log}")
    else:
        # If sending failed completely, refund token if applicable
        user_data = await get_user(user_id)
        if user_data and not user_data.get('is_premium', False): # Was a token user
            try:
                await update_user_tokens(user_id, 1) # Refund 1 token
                await client.send_message(chat_id, "ℹ️ Your download token has been refunded due to a file sending error.")
                LOGGER.info(f"Refunded 1 token to user {user_id} due to file send failure for EpVerID: {episode_version_id_str}")
            except Exception as e_refund:
                LOGGER.error(f"CRITICAL: Failed to refund token to user {user_id} after file send error: {e_refund}")


@Client.on_callback_query(filters.regex(r"^dl_cancel:(\w+)$"))
async def download_cancel_cb(client: Client, cb: CallbackQuery):
    # episode_version_id_str = cb.matches[0].group(1) # Can be used for more specific context
    # Edit message back to version selection or episode list
    # This part is complex as it requires knowing the "previous state"
    await cb.edit_message_text(
        "Download cancelled. What would you like to do next?",
        # TODO: Add a relevant "back" button or main menu button
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]])
    )
    await cb.answer("Download cancelled.")
