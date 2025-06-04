from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import (
    UserNotParticipant, ChatAdminRequired, UserIsBlocked,
    AuthKeyUnregistered, Forbidden, BadRequest, MessageNotModified # Added MessageNotModified
)
from bson import ObjectId
import config
import strings
from utils.keyboard_utils import (
    get_admin_panel_main_keyboard, get_admin_confirm_keyboard, get_skip_cancel_keyboard,
    get_admin_status_keyboard, get_admin_genre_selection_keyboard, get_admin_audio_type_keyboard,
    get_admin_manage_premium_keyboard,
    get_admin_bot_config_menu_keyboard, get_request_management_keyboard, get_single_request_management_keyboard,
)
from utils.custom_filters import admin_filter, owner_filter
from utils.logger import LOGGER, log_admin_action, log_bot_event, log_file_event, log_request_event # Import LOGGER
from database.operations import (
    add_anime, get_anime_by_id, find_anime_by_title, update_anime_metadata, delete_anime_series,
    add_season, get_season_by_id, get_season_by_anime_and_number,
    add_episode, get_episode_by_id, delete_episode_file,
    get_user, get_user_by_username, grant_premium, revoke_premium, get_premium_users,
    set_bot_setting, get_bot_setting,
    get_pending_anime_requests, update_anime_request_status, # Removed get_anime_request_by_id if not used directly here
    get_total_users_count, get_premium_users_count, get_anime_count, get_episode_count_all_versions, get_total_downloads_recorded
)
from database.connection import db as database_instance
from database.connection import db
from datetime import datetime, timedelta, timezone
import asyncio
import re # For regex flags 

# --- MAIN ADMIN PANEL ---

@Client.on_callback_query(filters.regex(r"^admin_panel_main$") & admin_filter)
async def admin_panel_main_cb(client: Client, callback_query: CallbackQuery):
    try:
        await callback_query.edit_message_text(
            strings.ADMIN_PANEL_TEXT,
            reply_markup=get_admin_panel_main_keyboard()
        )
    except: # If message is photo etc.
        await callback_query.message.reply_text(
            strings.ADMIN_PANEL_TEXT,
            reply_markup=get_admin_panel_main_keyboard()
        )
    await callback_query.answer()

# Delete All From MDB----------------------------
DELETE_ALL_CONFIRMATION_TEXT_1 = """⚠️⚠️⚠️ **EXTREME DANGER ZONE** ⚠️⚠️⚠️

You are about to delete **ALL DATA** from the bot's database:
- All Users
- All Anime Series
- All Seasons
- All Episodes & File IDs
- All Access Tokens
- All Anime Requests
- All User Activity Logs
- All Bot Settings (except those hardcoded or in .env)

This action is **IRREVERSIBLE** and will effectively reset the bot to a blank state.

Are you absolutely, positively sure you want to proceed?
Type `YES I AM ABSOLUTELY SURE` to proceed to the final confirmation.
Any other reply or command will cancel this operation.
"""

DELETE_ALL_CONFIRMATION_TEXT_2 = """🚨🚨🚨 **FINAL WARNING** 🚨🚨🚨

You have confirmed the first step. This is your **LAST CHANCE** to cancel.

If you proceed, all data associated with the MongoDB URI configured for this bot (`{mongo_uri_display}`) will be **PERMANENTLY DELETED**.

To confirm deletion, please type the following exact phrase:
`DELETE ALL MY BOT DATA NOW - {random_code}`

The random code for this session is: **{random_code}**
Any other reply will cancel this operation.
"""

# --- Admin State Management (Simple in-memory, for multi-step ops) ---
admin_tasks_data = {} # user_id: {'task': 'add_anime', 'step': 'title', 'data': {}}

# Helper to clear admin task data
def clear_admin_task(user_id):
    if user_id in admin_tasks_data:
        LOGGER.info(f"ADMIN_TASK_CLEAR: Clearing task for user {user_id}. Was: {admin_tasks_data.get(user_id)}")
        del admin_tasks_data[user_id]
    else:
        LOGGER.info(f"ADMIN_TASK_CLEAR: No task to clear for user {user_id}.")


@Client.on_message(filters.private & admin_filter & filters.text)
async def admin_text_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    LOGGER.info(f"ADMIN_TEXT_INPUT: User {user_id}, Text: '{message.text}'")
    if user_id not in admin_tasks_data:
        LOGGER.info(f"ADMIN_TEXT_INPUT: User {user_id} not in admin_tasks_data. Raising ContinuePropagation.")
        raise ContinuePropagation

    task_info = admin_tasks_data[user_id]
    task_type = task_info.get('task')
    current_step = task_info.get('step')
    LOGGER.info(f"ADMIN_TEXT_INPUT: User {user_id}, Task: {task_type}, Step: {current_step}, Data: {task_info.get('data')}")
    
    text = message.text.strip()
    if text.lower() == "/skip":
        LOGGER.info(f"ADMIN_TEXT_INPUT: User {user_id} sent /skip for step {current_step}")
        text = None # Represent skip as None
        

    # --- SET LOG CHANNEL ---
    if task_type == 'set_log_channel':
        LOGGER.info(f"ADMIN_TEXT_INPUT: In set_log_channel task, step: {current_step}")
        if current_step == 'channel_id':
            LOGGER.info(f"ADMIN_TEXT_INPUT: Matched set_log_channel:channel_id. Processing text: '{text}'")
            try:
                if not text: # Mandatory
                    await message.reply_text("Channel ID cannot be empty.", reply_markup=get_skip_cancel_keyboard("admin_config_log_channels"))
                    return
                channel_id = int(text)
                channel_type_to_set = task_info['data']['channel_type']
                LOGGER.info(f"ADMIN_TEXT_INPUT: Attempting to test and set channel ID {channel_id} for {channel_type_to_set}")
                
                await client.send_message(channel_id, f"📝 Test message from bot for {channel_type_to_set} logging setup.")
                LOGGER.info(f"ADMIN_TEXT_INPUT: Test message sent to {channel_id}.")

                await set_bot_setting(f"{channel_type_to_set}_channel_id", channel_id)
                setattr(config, f"{channel_type_to_set.upper()}_CHANNEL_ID", channel_id)
                LOGGER.info(f"ADMIN_TEXT_INPUT: DB and live config updated for {channel_type_to_set}.")
                
                await message.reply_text(f"✅ {channel_type_to_set.replace('_',' ').title()} channel ID set to {channel_id}. Test message sent.\n"
                                         "Note: Some config changes might need a bot restart to fully apply if read from `config.py` directly elsewhere.",
                                         reply_markup=get_admin_bot_config_menu_keyboard()) # Back to main config menu
                log_msg = f"Admin {message.from_user.id} set {channel_type_to_set}_channel_id to {channel_id}" # Use user ID for logging
                await log_admin_action(client, message.from_user.mention(style="html"), "Config Update", log_msg)
                clear_admin_task(user_id)
                LOGGER.info(f"ADMIN_TEXT_INPUT: Task set_log_channel completed for {user_id}.")
            except ValueError:
                LOGGER.warning(f"ADMIN_TEXT_INPUT: Invalid Channel ID '{text}'.")
                await message.reply_text("Invalid Channel ID. Must be a number (e.g., -100123456789). Try again.", reply_markup=get_skip_cancel_keyboard("admin_config_log_channels"))
            except Exception as e:
                LOGGER.error(f"ADMIN_TEXT_INPUT: Error setting channel ID for {task_info.get('data',{}).get('channel_type','N/A')}: {e}", exc_info=True)
                await message.reply_text(f"Error setting channel ID: {e}. Ensure bot is admin in the channel and the ID is correct. Try again.", reply_markup=get_skip_cancel_keyboard("admin_config_log_channels"))
        else:
            LOGGER.warning(f"ADMIN_TEXT_INPUT: Unhandled step '{current_step}' for task 'set_log_channel'")


    elif task_type == 'grant_premium':
        LOGGER.info(f"ADMIN_TEXT_INPUT: In grant_premium task, step: {current_step}")
        if current_step == 'user_identifier':
            LOGGER.info(f"ADMIN_TEXT_INPUT: Matched grant_premium:user_identifier. Processing '{text}'")
            try:
                if not text:
                    await message.reply_text("User identifier cannot be empty.", reply_markup=get_skip_cancel_keyboard("admin_grant_premium_cancel"))
                    return
                target_user = await get_user_by_username(text) or await get_user(int(text) if text.isdigit() else 0)
                if not target_user:
                    await message.reply_text(strings.USER_NOT_FOUND.format(identifier=text), reply_markup=get_skip_cancel_keyboard("admin_grant_premium_cancel"))
                    return
                task_info['data']['target_user_id'] = target_user['user_id']
                task_info['data']['target_user_mention'] = f"@{target_user['username']}" if target_user.get('username') else f"ID: {target_user['user_id']}"
                task_info['step'] = 'duration_days'
                await message.reply_text(f"Enter premium duration in <b>days</b> for {task_info['data']['target_user_mention']}:", parse_mode=ParseMode.HTML, reply_markup=get_skip_cancel_keyboard("admin_grant_premium_cancel"))
            except Exception as e:
                LOGGER.error(f"ADMIN_TEXT_INPUT: Error in grant_premium:user_identifier: {e}", exc_info=True)
                await message.reply_text(f"An error occurred: {e}. Try again.")

        elif current_step == 'duration_days':
            LOGGER.info(f"ADMIN_TEXT_INPUT: Matched grant_premium:duration_days. Processing '{text}'")
            try:
                if not text:
                    await message.reply_text("Duration cannot be empty.", reply_markup=get_skip_cancel_keyboard("admin_grant_premium_cancel"))
                    return
                days = int(text)
                if days <=0: raise ValueError("Days must be positive")
                task_info['data']['duration_days'] = days
                user_mention = task_info['data']['target_user_mention']
                task_info['step'] = 'confirm_grant'
                await message.reply_text(
                    f"Grant premium to {user_mention} for {days} days?",
                    reply_markup=get_admin_confirm_keyboard("admin_grant_premium_confirm", "admin_grant_premium_cancel")
                )
            except ValueError:
                await message.reply_text("Invalid number of days.", reply_markup=get_skip_cancel_keyboard("admin_grant_premium_cancel"))
            except Exception as e:
                LOGGER.error(f"ADMIN_TEXT_INPUT: Error in grant_premium:duration_days: {e}", exc_info=True)
                await message.reply_text(f"An error occurred: {e}. Try again.")
        else:
            LOGGER.warning(f"ADMIN_TEXT_INPUT: Unhandled step '{current_step}' for task 'grant_premium'")


    elif task_type == 'revoke_premium':
        LOGGER.info(f"ADMIN_TEXT_INPUT: In revoke_premium task, step: {current_step}")
        if current_step == 'user_identifier':
            LOGGER.info(f"ADMIN_TEXT_INPUT: Matched revoke_premium:user_identifier. Processing '{text}'")
            try:
                if not text:
                    await message.reply_text("User identifier cannot be empty.", reply_markup=get_skip_cancel_keyboard("admin_revoke_premium_cancel"))
                    return
                target_user = await get_user_by_username(text) or await get_user(int(text) if text.isdigit() else 0)
                if not target_user or not target_user.get('is_premium'):
                    await message.reply_text(strings.USER_NOT_FOUND.format(identifier=text) + " or user is not premium.", reply_markup=get_skip_cancel_keyboard("admin_revoke_premium_cancel"))
                    return
                task_info['data']['target_user_id'] = target_user['user_id']
                task_info['data']['target_user_mention'] = f"@{target_user['username']}" if target_user.get('username') else f"ID: {target_user['user_id']}"
                task_info['step'] = 'confirm_revoke'
                await message.reply_text(
                    f"Revoke premium from {task_info['data']['target_user_mention']}?",
                    reply_markup=get_admin_confirm_keyboard("admin_revoke_premium_confirm", "admin_revoke_premium_cancel")
                )
            except Exception as e:
                LOGGER.error(f"ADMIN_TEXT_INPUT: Error in revoke_premium:user_identifier: {e}", exc_info=True)
                await message.reply_text(f"An error occurred: {e}. Try again.")
        else:
            LOGGER.warning(f"ADMIN_TEXT_INPUT: Unhandled step '{current_step}' for task 'revoke_premium'")

    elif task_type == 'broadcast':
        LOGGER.info(f"ADMIN_TEXT_INPUT: In broadcast task, step: {current_step}")
        if current_step == 'message_text':
            LOGGER.info(f"ADMIN_TEXT_INPUT: Matched broadcast:message_text.")
            try:
                if not text: # Or message.text directly if formatting is important
                    await message.reply_text("Broadcast message cannot be empty.", reply_markup=get_skip_cancel_keyboard("admin_broadcast_cancel"))
                    return
                task_info['data']['broadcast_message'] = message.text # Use original message.text for formatting
                task_info['step'] = 'confirm_broadcast'
                await message.reply_text(
                    "<b>Confirm Broadcast Message:</b>\n\n" + message.text + "\n\nSend this to all users?",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_admin_confirm_keyboard("admin_broadcast_execute", "admin_broadcast_cancel"),
                    disable_web_page_preview=True
                )
            except Exception as e:
                LOGGER.error(f"ADMIN_TEXT_INPUT: Error in broadcast:message_text: {e}", exc_info=True)
                await message.reply_text(f"An error occurred: {e}. Try again.")
        else:
            LOGGER.warning(f"ADMIN_TEXT_INPUT: Unhandled step '{current_step}' for task 'broadcast'")

    elif task_type == 'delete_all_data':
        LOGGER.info(f"ADMIN_TEXT_INPUT: In delete_all_data task, step: {current_step}")
        if current_step == 'confirm_1':
            if text == "YES I AM ABSOLUTELY SURE":
                # Generate a random code for second confirmation
                import random
                import string
                random_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                task_info['data']['random_code'] = random_code
                task_info['step'] = 'confirm_2'
                
                # Obfuscate MongoDB URI for display
                mongo_uri_display = "mongodb://*****" # Basic obfuscation
                if config.MONGO_URI:
                    parts = config.MONGO_URI.split('@')
                    if len(parts) > 1:
                        mongo_uri_display = parts[0].split('//')[0] + "//*****@" + parts[1]
                    else:
                        mongo_uri_display = config.MONGO_URI[:15] + "*****"


                await message.reply_text(
                    DELETE_ALL_CONFIRMATION_TEXT_2.format(random_code=random_code, mongo_uri_display=mongo_uri_display),
                    parse_mode=ParseMode.MARKDOWN
                )
                await log_admin_action(client, message.from_user.mention(style="html"), "Passed /delete_all_data Confirmation 1", f"Random code: {random_code}")
            else:
                await message.reply_text("❌ First confirmation failed. Data deletion cancelled.")
                await log_admin_action(client, message.from_user.mention(style="html"), "Failed /delete_all_data Confirmation 1", "Operation cancelled.")
                clear_admin_task(user_id)
        
        elif current_step == 'confirm_2':
            random_code_expected = task_info['data'].get('random_code')
            expected_phrase = f"DELETE ALL MY BOT DATA NOW - {random_code_expected}"
            
            if text == expected_phrase:
                await message.reply_text("🚨 **DELETION IN PROGRESS...** This may take a moment. The bot might become unresponsive or restart after this.", parse_mode=ParseMode.MARKDOWN)
                await log_admin_action(client, message.from_user.mention(style="html"), "Executing /delete_all_data", "Final confirmation received.")
                
                # --- THE ACTUAL DELETION ---
                collections_to_delete = [
                    db.users, db.access_tokens, db.animes, db.seasons,
                    db.episodes, db.anime_requests, db.user_activity, db.bot_settings
                ]
                deleted_counts = {}
                errors_occurred = False

                for coll in collections_to_delete:
                    try:
                        LOGGER.warning(f"DELETING ALL DOCUMENTS FROM COLLECTION: {coll.name}")
                        result = await coll.delete_many({}) # Delete all documents
                        deleted_counts[coll.name] = result.deleted_count
                        LOGGER.warning(f"Deleted {result.deleted_count} documents from {coll.name}")
                        await asyncio.sleep(0.5) # Small pause
                    except Exception as e:
                        LOGGER.error(f"Error deleting from collection {coll.name}: {e}", exc_info=True)
                        deleted_counts[coll.name] = f"ERROR: {e}"
                        errors_occurred = True
                
                summary_message = "✅ **DATA DELETION COMPLETE!**\n\nSummary:\n"
                for name, count in deleted_counts.items():
                    summary_message += f"  - {name}: {count} deleted\n"
                
                if errors_occurred:
                    summary_message += "\n⚠️ Some errors occurred during deletion. Check bot logs for details."
                
                summary_message += "\n\nThe bot's database has been wiped. You may need to /start the bot again or restart it if it becomes unresponsive."
                
                await message.reply_text(summary_message, parse_mode=ParseMode.MARKDOWN)
                await log_admin_action(client, message.from_user.mention(style="html"), "Completed /delete_all_data", summary_message)
                clear_admin_task(user_id)

                # Optionally, you could try to gracefully stop the bot here or trigger a restart.
                # For now, it will continue running with an empty DB.
                # await client.stop() # This would stop the bot.

            else:
                await message.reply_text("❌ Final confirmation FAILED. Phrase did not match. Data deletion CANCELLED.")
                await log_admin_action(client, message.from_user.mention(style="html"), "Failed /delete_all_data Final Confirmation", "Operation cancelled.")
                clear_admin_task(user_id)
        else:
            LOGGER.warning(f"ADMIN_TEXT_INPUT: Unhandled step '{current_step}' for task 'delete_all_data'")
            clear_admin_task(user_id)
            await message.reply_text("Invalid step in deletion process. Operation cancelled.")
    
    else: # Unknown task_type
        LOGGER.error(f"ADMIN_TEXT_INPUT: Unknown task type '{task_type}' for user {user_id}. Clearing task.")
        clear_admin_task(user_id)
        await message.reply_text("An internal error occurred with the admin task. Please start over.")


#======= MANAGE CONTENT ==========

@Client.on_callback_query(filters.regex("^admin_content_start$") & admin_filter)
async def admin_content_start_cb(client: Client, cb: CallbackQuery):
    user_id = cb.from_user.id
    admin_tasks_data[user_id] = {
        'flow': 'content_management',
        'action': None,
        'step': 'prompt_anime_name_for_episode_or_season', # Start by asking for anime name
        'current_anime_id': None, 'current_anime_title': None,
        'current_season_id': None, 'current_season_number': None,
        'current_episode_id': None,
        'data_buffer': {}
    }
    
    # Delete previous message if it's from this bot's interaction
    try:
        await cb.message.delete()
    except Exception as e:
        LOGGER.info(f"Could not delete previous message for admin_content_start_cb: {e}")

    await client.send_message( # Send new message as prompt
        chat_id=user_id,
        text="📚 **Content Management**\n\nEnter the name of the Anime you want to work with (to add/edit seasons or episodes):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add New Anime Series", callback_data="admin_new_anime_flow_start")],
                                           [InlineKeyboardButton("❌ Cancel", callback_data="admin_panel_main")]]) # Cancel back to admin panel
    )
    await cb.answer()


# Callback handler for /skip and general admin task cancellation
@Client.on_callback_query(filters.regex(r"^admin_input_skip$") & admin_filter)
async def admin_input_skip_cb(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in admin_tasks_data:
        await callback_query.answer("No active admin task found to skip from.", show_alert=True)
        return

    # Simulate sending a None text input to the handler
    # Create a dummy message object (simplified)
    class DummyMessage:
        def __init__(self, user, chat_id, text):
            self.from_user = user
            self.chat = type('Chat', (), {'id': chat_id})() # Simple chat object with id
            self.text = text
            self.reply_text = callback_query.message.reply_text # Use reply of original message
            # Add other methods if needed by handler, e.g. reply_photo
    
    dummy_msg = DummyMessage(callback_query.from_user, callback_query.message.chat.id, "/skip")
    await callback_query.answer("Skipping step...")
    await callback_query.message.delete() # Remove the prompt message with skip button
    await admin_text_input_handler(client, dummy_msg) # Manually call the handler

# Generic admin task cancel (from keyboards)
@Client.on_callback_query(filters.regex(r"_cancel$") & admin_filter) # e.g., admin_add_anime_cancel
async def admin_task_cancel_cb(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    task_name = callback_query.data.split('_cancel')[0].replace('admin_', '').replace('_', ' ').title()
    clear_admin_task(user_id)
    await callback_query.edit_message_text(
        f"❌ {task_name} operation cancelled.",
        reply_markup=get_admin_panel_main_keyboard() # Or specific menu
    )
    await callback_query.answer("Operation cancelled.")


# --- EDIT/DELETE CONTENT MENUS & PLACEHOLDERS ---
@Client.on_callback_query(filters.regex(r"^(admin_edit_content_menu|admin_delete_content_menu)$") & admin_filter)
async def admin_manage_content_menus_cb(client: Client, callback_query: CallbackQuery):
    menu_type = callback_query.data.split('_menu')[0] # admin_edit_content or admin_delete_content
    
    text = "✏️ Select content type to Edit:" if "edit" in menu_type else "🗑️ Select content type to Delete:"
    if "edit" in menu_type:
        kb = get_admin_edit_content_menu_keyboard()
    else:
        kb = get_admin_delete_content_menu_keyboard()

    await callback_query.edit_message_text(text, reply_markup=kb)
    await callback_query.answer()


# --- PREMIUM MANAGEMENT ---
@Client.on_callback_query(filters.regex(r"^admin_manage_premium_menu$") & admin_filter)
async def admin_manage_premium_menu_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.edit_message_text("👑 Premium User Management:", reply_markup=get_admin_manage_premium_keyboard())
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^admin_grant_premium_prompt_user$") & admin_filter)
async def admin_grant_premium_prompt_user_cb(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    admin_tasks_data[user_id] = {'task': 'grant_premium', 'step': 'user_identifier', 'data': {}}
    await callback_query.edit_message_text("Enter User ID or @Username to grant premium:", reply_markup=get_skip_cancel_keyboard("admin_grant_premium_cancel"))
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^admin_grant_premium_confirm$") & admin_filter)
async def admin_grant_premium_confirm_cb(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    task_info = admin_tasks_data[user_id]
    # ... (validation) ...
    target_user_id = task_info['data']['target_user_id']
    days = task_info['data']['duration_days']
    
    success, expiry_date = await grant_premium(target_user_id, days, user_id)
    if success:
        msg = strings.PREMIUM_GRANTED.format(user_mention=task_info['data']['target_user_mention'], days=days, expiry_date=expiry_date.strftime('%Y-%m-%d %H:%M UTC'))
        await log_admin_action(client, callback_query.from_user.mention(style="html"), "Grant Premium", msg)
        try: # Notify user
            await client.send_message(target_user_id, f"🎉 Congratulations! You have been granted Premium access for {days} days. Enjoy!")
        except Exception as e: LOGGER.warning(f"Could not notify user {target_user_id} about premium grant: {e}")
    else:
        msg = strings.OPERATION_FAILED + " Could not grant premium."
    await callback_query.edit_message_text(msg, reply_markup=get_admin_manage_premium_keyboard())
    clear_admin_task(user_id)
    await callback_query.answer()

# ... (Similar for revoke premium: prompt_user, confirm_revoke) ...
@Client.on_callback_query(filters.regex(r"^admin_revoke_premium_prompt_user$") & admin_filter)
async def admin_revoke_premium_prompt_user_cb(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    admin_tasks_data[user_id] = {'task': 'revoke_premium', 'step': 'user_identifier', 'data': {}}
    await callback_query.edit_message_text("Enter User ID or @Username to revoke premium from:", reply_markup=get_skip_cancel_keyboard("admin_revoke_premium_cancel"))
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^admin_revoke_premium_confirm$") & admin_filter)
async def admin_revoke_premium_confirm_cb(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    task_info = admin_tasks_data[user_id]
    # ... (validation) ...
    target_user_id = task_info['data']['target_user_id']
    
    success = await revoke_premium(target_user_id, user_id)
    if success:
        msg = strings.PREMIUM_REVOKED.format(user_mention=task_info['data']['target_user_mention'])
        await log_admin_action(client, callback_query.from_user.mention(style="html"), "Revoke Premium", msg)
        try: # Notify user
            await client.send_message(target_user_id, "ℹ️ Your Premium access has been revoked by an administrator.")
        except: pass
    else:
        msg = strings.OPERATION_FAILED + " Could not revoke premium (maybe not premium or user not found)."
    await callback_query.edit_message_text(msg, reply_markup=get_admin_manage_premium_keyboard())
    clear_admin_task(user_id)
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^admin_list_premium_users$") & admin_filter)
async def admin_list_premium_users_cb(client: Client, callback_query: CallbackQuery):
    prem_users = await get_premium_users()
    if not prem_users:
        await callback_query.answer("No premium users found.", show_alert=True)
        return

    text = "👑 **Premium Users List:**\n\n"
    for u in prem_users:
        mention = f"@{u['username']}" if u.get('username') else f"ID: {u['user_id']}"
        expiry = u['premium_expiry_date'].strftime('%Y-%m-%d') if u.get('premium_expiry_date') else 'N/A'
        text += f"  - {mention} (Expires: {expiry})\n"
    
    # This text can be long, consider sending as file or paginating if many users
    # For now, edit or send as new if too long
    try:
        await callback_query.edit_message_text(text, reply_markup=get_admin_manage_premium_keyboard(), parse_mode=ParseMode.HTML)
    except Exception: # If text too long for edit
        await callback_query.message.reply_text(text, reply_markup=get_admin_manage_premium_keyboard(), parse_mode=ParseMode.HTML)
    await callback_query.answer()

# --- BOT STATS ---
@Client.on_callback_query(filters.regex(r"^admin_bot_stats$") & admin_filter)
async def admin_bot_stats_cb(client: Client, callback_query: CallbackQuery):
    total_u = await get_total_users_count()
    prem_u = await get_premium_users_count()
    anime_c = await get_anime_count()
    episode_v_c = await get_episode_count_all_versions() # All versions
    # distinct_e_c = await get_distinct_file_count() # Unique episodes (harder to calc on fly)
    total_dl = await get_total_downloads_recorded() # from user_activity log
    db_s = await database_instance.get_db_stats()
    current_utc_time = datetime.now(timezone.utc) # Get current time as UTC aware
    uptime_delta = current_utc_time - client.start_time # client.start_time is already UTC aware
    uptime_str = str(uptime_delta).split('.')[0]

    stats_text = f"""📊 **Bot Statistics:**
<blockquote>
Total Users: {total_u}
Premium Users: {prem_u} ({prem_u/total_u*100 if total_u else 0:.1f}%)

Total Anime Series: {anime_c}
Total Episode Files (versions): {episode_v_c}
Total Downloads Logged: {total_dl}

Database Status: {db_s}
Bot Uptime: {uptime_str} (approx since last start)
</blockquote>
    """ # client.start_time needs to be set in bot.py
    await callback_query.edit_message_text(stats_text, reply_markup=get_admin_panel_main_keyboard(), parse_mode=ParseMode.HTML)
    await callback_query.answer()

# --- BROADCAST ---
@Client.on_callback_query(filters.regex(r"^admin_broadcast_prompt$") & admin_filter)
async def admin_broadcast_prompt_cb(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    admin_tasks_data[user_id] = {'task': 'broadcast', 'step': 'message_text', 'data': {}}
    await callback_query.edit_message_text(
        "Enter the message to broadcast to all users. Supports Markdown/HTML (ensure bot can parse it).",
        reply_markup=get_skip_cancel_keyboard("admin_broadcast_cancel") # a general cancel for now
    )
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^admin_broadcast_execute$") & admin_filter)
async def admin_broadcast_execute_cb(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    task_info = admin_tasks_data[user_id]
    # ... (validation) ...
    message_to_send = task_info['data']['broadcast_message']
    
    await callback_query.edit_message_text(strings.BROADCAST_STARTED)
    await callback_query.answer("Broadcast initiated...")
    
    all_users = await db.users.find({}, {'user_id': 1}).to_list(length=None)
    sent_count = 0
    failed_count = 0

    for user_doc in all_users:
        target_user_id = user_doc['user_id']
        # Inside admin_broadcast_execute_cb, the try-except block:
        try:
            await client.send_message(target_user_id, message_to_send, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            sent_count += 1
        except UserIsBlocked: # Specifically BotBlocked by the user
            failed_count += 1
            LOGGER.warning(f"Broadcast failed for user {target_user_id}: User has blocked the bot.")
        except AuthKeyUnregistered: # Often indicates user deactivated their account
            failed_count += 1
            LOGGER.warning(f"Broadcast failed for user {target_user_id}: User account deactivated (AuthKeyUnregistered).")
        except UserNotParticipant: # If sending to a group/channel where bot isn't or user isn't
             failed_count += 1
             LOGGER.warning(f"Broadcast failed for {target_user_id}: UserNotParticipant (might be a group/channel issue or user left).")
        except Forbidden as e: # A more general catch-all for permission issues
            failed_count += 1
            LOGGER.warning(f"Broadcast failed for user {target_user_id}: Forbidden - {e}")
        except Exception as e: # Other errors
            failed_count += 1
            LOGGER.error(f"Broadcast error for user {target_user_id}: {e}")
        await asyncio.sleep(0.1) # Avoid hitting TG rate limits too hard
        
    summary = strings.BROADCAST_SUMMARY.format(sent_count=sent_count, failed_count=failed_count)
    await callback_query.message.reply_text(summary, reply_markup=get_admin_panel_main_keyboard())
    await log_admin_action(client, callback_query.from_user.mention(style="html"), "Broadcast", summary + f"\nMessage: {message_to_send[:100]}...")
    clear_admin_task(user_id)


# --- BOT CONFIGURATION (Log Channels Example) ---
@Client.on_callback_query(filters.regex(r"^admin_bot_config_menu$") & admin_filter)
async def admin_bot_config_menu_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.edit_message_text("⚙️ Bot Configuration Options:", reply_markup=get_admin_bot_config_menu_keyboard())
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^admin_config_log_channels$") & admin_filter)
async def admin_config_log_channels_cb(client: Client, callback_query: CallbackQuery):
    # Display current settings and offer to change
    text = "📦 **Log Channel Configuration:**\n"
    channels = ['request_log', 'file_log', 'bot_log']
    kb_buttons = []
    for ch_type in channels:
        ch_id_key = f"{ch_type}_channel_id" # Key in bot_settings or config
        current_id = await get_bot_setting(ch_id_key) or getattr(config, f"{ch_type.upper()}_CHANNEL_ID", "Not Set")
        text += f"  - {ch_type.replace('_',' ').title()}: `{current_id}`\n"
        kb_buttons.append([InlineKeyboardButton(f"Set {ch_type.replace('_',' ').title()} Channel", callback_data=f"admin_set_log_channel_prompt:{ch_type}")])
    
    kb_buttons.append([InlineKeyboardButton("⬅️ Back to Bot Config", callback_data="admin_bot_config_menu")])
    try:
        await callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb_buttons), parse_mode=ParseMode.MARKDOWN)
    except MessageNotModified:
        pass
    except Exception as e:
        LOGGER.error(f"Error editing in admin_config_log_channels_cb: {e}")
    finally:
        await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^admin_set_log_channel_prompt:(.+)$") & admin_filter)
async def admin_set_log_channel_prompt_cb(client: Client, callback_query: CallbackQuery):
    channel_type_to_set = callback_query.matches[0].group(1)
    user_id = callback_query.from_user.id
    admin_tasks_data[user_id] = {
        'task': 'set_log_channel', 
        'step': 'channel_id', 
        'data': {'channel_type': channel_type_to_set}
    }
    await callback_query.edit_message_text(
        f"Enter the new <b>Channel ID</b> for <code>{channel_type_to_set}</code> logs (e.g., -100xxxxxxx).\n"
        "The bot must be an administrator in this channel.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_skip_cancel_keyboard("admin_config_log_channels") # Back to log channels menu
    )
    await callback_query.answer()

# TODO: Admin Config Token System similar to log channels
@Client.on_callback_query(filters.regex(r"^admin_config_token_system$") & admin_filter)
async def admin_config_token_system_cb(client: Client, callback_query: CallbackQuery):
    tokens_b = await get_bot_setting("tokens_per_bypass") or config.TOKENS_PER_BYPASS
    expiry_h = await get_bot_setting("token_expiry_hours") or config.TOKEN_EXPIRY_HOURS
    daily_l_dl = await get_bot_setting("free_user_download_limit_per_day") or config.FREE_USER_DOWNLOAD_LIMIT_PER_DAY

    # In a real scenario, you'd make these settable too.
    text = f"""💰 **Token System & Download Limits Config:**
<blockquote>
Tokens per Link Bypass: {tokens_b}
Token Link Expiry: {expiry_h} hours
Free User Daily Downloads: {daily_l_dl} episodes
</blockquote>
<i>(These are currently hardcoded or set via .env. A full admin edit for these requires more handlers.)</i>"""

    await callback_query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Bot Config", callback_data="admin_bot_config_menu")]]),
        parse_mode=ParseMode.HTML
    )
    await callback_query.answer()


# --- REQUEST MANAGEMENT ---
@Client.on_callback_query(filters.regex(r"^admin_manage_requests_page_(\d+)$") & admin_filter)
async def admin_manage_requests_cb(client: Client, callback_query: CallbackQuery):
    page = int(callback_query.matches[0].group(1))
    requests, total_reqs = await get_pending_anime_requests(page, config.ITEMS_PER_PAGE)
    
    if not requests and page == 1:
        await callback_query.edit_message_text(
            "No pending anime requests found.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_main")]])
        )
        await callback_query.answer()
        return

    kb = get_request_management_keyboard(requests, page, total_reqs, config.ITEMS_PER_PAGE)
    await callback_query.edit_message_text(
        strings.REQUEST_MANAGEMENT_TEXT,
        reply_markup=kb
    )
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^admin_view_request:(\w+)$") & admin_filter)
async def admin_view_single_request_cb(client: Client, callback_query: CallbackQuery):
    request_id_str = callback_query.matches[0].group(1)
    request_doc = await get_anime_request_by_id(request_id_str)

    if not request_doc:
        await callback_query.answer("Request not found.", show_alert=True)
        return

    user_req = await get_user(request_doc['user_id'])
    user_mention_req = user_req['username'] if user_req else f"ID: {request_doc['user_id']}"
    
    text = f"""📜 **Anime Request Details:**
<blockquote>
Request ID: `{str(request_doc['_id'])}`
User: {user_mention_req}
Anime Title: <b>{request_doc['anime_title_requested']}</b>
Language: {request_doc['language_requested']}
Status: <b>{request_doc['status'].upper()}</b>
Requested At: {request_doc['requested_at'].strftime('%Y-%m-%d %H:%M')} UTC
</blockquote>"""
    if request_doc.get('resolved_by_admin_id'):
        admin_resolver = await get_user(request_doc['resolved_by_admin_id'])
        resolver_mention = admin_resolver['username'] if admin_resolver else f"ID: {request_doc['resolved_by_admin_id']}"
        text += f"\nResolved By: {resolver_mention} at {request_doc['resolved_at'].strftime('%Y-%m-%d %H:%M')} UTC"
    if request_doc.get('admin_notes'):
        text += f"\nAdmin Notes: <i>{request_doc['admin_notes']}</i>"

    await callback_query.edit_message_text(text, reply_markup=get_single_request_management_keyboard(request_doc), parse_mode=ParseMode.HTML)
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^admin_req_status:(\w+):(.+)$") & admin_filter)
async def admin_update_request_status_cb(client: Client, callback_query: CallbackQuery):
    request_id_str = callback_query.matches[0].group(1)
    new_status = callback_query.matches[0].group(2)
    admin_id = callback_query.from_user.id
    
    request_doc = await get_anime_request_by_id(request_id_str)
    if not request_doc:
        await callback_query.answer("Request not found.", show_alert=True); return

    if request_doc['status'] == new_status:
        await callback_query.answer(f"Request is already '{new_status}'.", show_alert=True); return

    # For fulfilled/rejected, might want to prompt for admin notes
    admin_notes_text = f"Request for '{request_doc['anime_title_requested']}' marked as '{new_status}' by admin." # Default note

    updated = await update_anime_request_status(ObjectId(request_id_str), new_status, admin_id, admin_notes_text)

    if updated:
        await callback_query.answer(f"Request status updated to '{new_status}'.")
        log_msg = f"Request ID {request_id_str} ('{request_doc['anime_title_requested']}') status changed to {new_status}."
        await log_admin_action(client, callback_query.from_user.mention(style="html"), "Update Anime Request", log_msg)
        await log_request_event(client, log_msg + f" By: {callback_query.from_user.mention(style='html')}", parse_mode_enum=ParseMode.HTML)


        # Notify User (Important)
        user_to_notify = request_doc['user_id']
        user_data_notify = await get_user(user_to_notify)
        
        notif_text = ""
        if new_status == 'fulfilled':
            notif_text = strings.REQUEST_NOTIFICATION_ADDED.format(
                anime_title=request_doc['anime_title_requested'],
                language=request_doc['language_requested'],
                notes=admin_notes_text
            )
        elif new_status in ['rejected', 'unavailable']:
             notif_text = strings.REQUEST_NOTIFICATION_REJECTED.format(
                anime_title=request_doc['anime_title_requested'],
                language=request_doc['language_requested'],
                reason=f"Marked as '{new_status}' by admin.", # More specific reason needed from admin
                notes=admin_notes_text
            )
        
        if notif_text and user_data_notify: # Check if user exists
            try:
                await client.send_message(user_to_notify, notif_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                LOGGER.warning(f"Could not notify user {user_to_notify} about request update: {e}")

        # Refresh the view for admin
        await admin_view_single_request_cb(client, callback_query) # This re-fetches and edits message
    else:
        await callback_query.answer("Failed to update request status.", show_alert=True)

# Placeholder for unimplemented admin features
@Client.on_callback_query(filters.regex(r"^admin_placeholder$") & admin_filter)
async def admin_placeholder_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("This admin feature is not yet implemented.", show_alert=True)
