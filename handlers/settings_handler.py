from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode
import config
import strings
from utils.keyboard_utils import get_settings_keyboard, get_quality_settings_keyboard, get_audio_settings_keyboard
from database.operations import get_user, update_user_setting

# Main Settings Menu
@Client.on_message(filters.command("settings"))
@Client.on_callback_query(filters.regex(r"^user_settings$"))
async def user_settings_handler(client: Client, message_or_cb):
    is_cb = isinstance(message_or_cb, CallbackQuery)
    user_id = message_or_cb.from_user.id
    message_to_reply = message_or_cb.message if is_cb else message_or_cb

    user_data = await get_user(user_id)
    if not user_data: # Should exist from /start
        await message_to_reply.reply_text("Please /start the bot first to access settings.")
        if is_cb: await message_or_cb.answer()
        return

    user_settings = user_data.get('settings', {}) # Get sub-document
    # Ensure defaults if settings sub-doc is missing fields (can happen if user doc was created before settings field)
    user_settings.setdefault('preferred_quality', '720p')
    user_settings.setdefault('preferred_audio', 'SUB')
    user_settings.setdefault('watchlist_notifications', True)
    
    text = strings.SETTINGS_TEXT
    reply_markup = get_settings_keyboard(user_settings)
    
    if is_cb:
        await message_or_cb.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        await message_or_cb.answer()
    else:
        await message_or_cb.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# --- Quality Setting ---
@Client.on_callback_query(filters.regex(r"^settings_quality$"))
async def settings_quality_picker_handler(client: Client, cb: CallbackQuery):
    user_data = await get_user(cb.from_user.id)
    current_quality = user_data.get('settings', {}).get('preferred_quality', '720p')
    
    await cb.edit_message_text(
        strings.PREF_QUALITY_TEXT,
        reply_markup=get_quality_settings_keyboard(current_quality)
    )
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^set_quality:(.+)$"))
async def set_quality_handler(client: Client, cb: CallbackQuery):
    new_quality = cb.matches[0].group(1).replace('_',' ')
    await update_user_setting(cb.from_user.id, 'preferred_quality', new_quality)
    
    await cb.answer(strings.SETTING_UPDATED, show_alert=False)
    # Go back to main settings view
    await user_settings_handler(client, cb) # Re-call to refresh the main settings view


# --- Audio Setting ---
@Client.on_callback_query(filters.regex(r"^settings_audio$"))
async def settings_audio_picker_handler(client: Client, cb: CallbackQuery):
    user_data = await get_user(cb.from_user.id)
    current_audio = user_data.get('settings', {}).get('preferred_audio', 'SUB')
    
    await cb.edit_message_text(
        strings.PREF_AUDIO_TEXT,
        reply_markup=get_audio_settings_keyboard(current_audio)
    )
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^set_audio:(\w+)$"))
async def set_audio_handler(client: Client, cb: CallbackQuery):
    new_audio = cb.matches[0].group(1)
    await update_user_setting(cb.from_user.id, 'preferred_audio', new_audio)
    
    await cb.answer(strings.SETTING_UPDATED, show_alert=False)
    await user_settings_handler(client, cb) # Refresh main settings


# --- Watchlist Notifications Toggle ---
@Client.on_callback_query(filters.regex(r"^settings_toggle_notif$"))
async def settings_toggle_notif_handler(client: Client, cb: CallbackQuery):
    user_data = await get_user(cb.from_user.id)
    current_notif_status = user_data.get('settings', {}).get('watchlist_notifications', True)
    new_notif_status = not current_notif_status # Toggle
    
    await update_user_setting(cb.from_user.id, 'watchlist_notifications', new_notif_status)
    
    await cb.answer(strings.SETTING_UPDATED + f" Notifications now {'ON' if new_notif_status else 'OFF'}", show_alert=False)
    await user_settings_handler(client, cb) # Refresh main settings
