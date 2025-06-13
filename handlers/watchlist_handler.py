# handlers/watchlist_handler.py
import logging
import asyncio # For potential delays or async database operations
from typing import Union, List, Dict, Any # Import type hints
from pyrogram import Client, filters # Import Pyrogram core and filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant # Specific errors
)
from bson import ObjectId # For working with MongoDB ObjectIds


import config # Import configuration constants
import strings # Import string constants

# Import database models and utilities
from database.mongo_db import MongoDB # Access MongoDB class instance methods
# Import necessary specific database helpers for user and anime
# We'll use the standard users_collection method from MongoDB
from database.mongo_db import get_user_state, set_user_state, clear_user_state # State management

# Import Pydantic models
from database.models import User, Anime # Import User and Anime models

# Import helpers from common_handlers or search_handler
from handlers.common_handlers import get_user, edit_or_send_message # Needed helpers
# May need to display anime details menu again, needs helper from search_handler
# from handlers.search_handler import display_user_anime_details_menu # Import if directly called


watchlist_logger = logging.getLogger(__name__)

# --- Watchlist States (Simple) ---
# handler: "watchlist"
class WatchlistState:
    VIEWING_LIST = "watchlist_viewing_list" # Displaying the user's watchlist menu
    # Note: Watchlist actions (add/remove) often happen while in other states
    # (e.g., browse_handler: viewing_anime_details). We don't need a dedicated
    # state *for the action itself*, just for viewing the watchlist list.


# --- Callbacks from Anime Details Menu (Add/Remove Watchlist) ---
# Catches callbacks: watchlist_add|<anime_id>
# Catches callbacks: watchlist_remove|<anime_id>
@Client.on_callback_query(filters.regex(f"^watchlist_(add|remove){config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_watchlist_add_remove_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # The anime details message
    data = callback_query.data # watchlist_add|<anime_id> or watchlist_remove|<anime_id>


    try:
        # Parse action type ('add' or 'remove') and anime ID from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for watchlist action.")
        action_type = parts[0].split('_')[1] # 'add' or 'remove'
        anime_id_str = parts[1] # The anime ID string

        # Ensure anime ID string is a valid ObjectId format
        try:
             anime_id_obj = ObjectId(anime_id_str) # Convert string to ObjectId for DB interaction
        except Exception:
             raise ValueError("Invalid anime ID format in callback data.")

    except ValueError as e:
        watchlist_logger.warning(f"User {user_id} invalid watchlist callback data: {data}: {e}")
        await client.answer_callback_query(message.id, "🚫 Invalid watchlist data.", show_alert=False)
        return


    # Get user document (required to modify watchlist)
    user = await MongoDB.users_collection().find_one({"user_id": user_id})
    if user is None:
         # User not found in DB. Should not happen normally if /start works.
        watchlist_logger.error(f"User {user_id} not found in DB during watchlist {action_type} action for anime {anime_id_str}.")
        await client.answer_callback_query(message.id, strings.DB_ERROR, show_alert=True)
        return


    # Check user's current watchlist before attempting modification
    current_watchlist_ids = user.get("watchlist", []) # Get watchlist as a list, default to empty list

    success = False
    # Database update operation
    update_result = None
    feedback_message_text = strings.ERROR_OCCURRED # Default feedback


    try:
        if action_type == 'add':
            # Add anime ID to watchlist IF it's not already there
            if anime_id_obj not in current_watchlist_ids:
                 # Use $push to append the new anime ID (ObjectId) to the 'watchlist' array
                 update_result = await MongoDB.users_collection().update_one(
                      {"user_id": user_id}, # Filter for the user
                      {"$push": {"watchlist": anime_id_obj}} # Add ObjectId to watchlist array
                  )
                 # Check if document was matched and modified (means it was found and added)
                 if update_result.matched_count > 0 and update_result.modified_count > 0:
                      success = True
                      feedback_message_text = strings.ANIME_ADDED_TO_WATCHLIST.format(anime_title="The Anime") # Needs anime name. Fetch after update?

                 elif update_result.matched_count > 0:
                     # Matched user but not modified - likely already in watchlist.
                     success = True # Action succeeded conceptually
                     feedback_message_text = f"✅ This anime is already in your watchlist."

                 # If matched_count is 0, user doc not found? (Should not happen if get_user/find_one above succeeded).

            else:
                # Anime already in watchlist (based on initial fetch check)
                success = True
                feedback_message_text = f"✅ This anime is already in your watchlist." # Replicate message


        elif action_type == 'remove':
             # Remove anime ID from watchlist IF it's in the list
             if anime_id_obj in current_watchlist_ids:
                  # Use $pull to remove the anime ID (ObjectId) from the 'watchlist' array
                 update_result = await MongoDB.users_collection().update_one(
                      {"user_id": user_id}, # Filter for the user
                      {"$pull": {"watchlist": anime_id_obj}} # Remove ObjectId from watchlist array
                  )
                 # Check if document was matched and modified (means it was found and removed)
                 if update_result.matched_count > 0 and update_result.modified_count > 0:
                      success = True
                      feedback_message_text = strings.ANIME_REMOVED_FROM_WATCHLIST.format(anime_title="The Anime") # Needs anime name

                 elif update_result.matched_count > 0:
                     # Matched user but not modified - likely not in watchlist.
                     success = True # Action succeeded conceptually (removed nothing = it's gone)
                     feedback_message_text = f"✅ This anime was not in your watchlist (or is now removed)." # Be clear

             else:
                 # Anime not in watchlist (based on initial fetch check)
                 success = True
                 feedback_message_text = f"✅ This anime was not in your watchlist (or is now removed)."


        # --- If Database Update Was Attempted (Add/Remove cases) ---
        if update_result: # Only proceed with success/failure messaging if DB was touched
             if success:
                 # Fetch anime name to format the feedback message. Get updated user document for new watchlist size if needed.
                 anime = await MongoDB.anime_collection().find_one({"_id": anime_id_obj}, {"name": 1}) # Fetch only name
                 anime_name = anime.get("name", "The Anime") if anime else "The Anime" # Default name

                 # Format the success message using the actual anime name
                 if action_type == 'add': feedback_message_text = strings.ANIME_ADDED_TO_WATCHLIST.format(anime_title=anime_name)
                 elif action_type == 'remove': feedback_message_text = strings.ANIME_REMOVED_FROM_WATCHLIST.format(anime_title=anime_name)


                 # --- Redisplay Anime Details Menu with Updated Watchlist Button ---
                 # Fetch the full anime document again
                 anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if anime:
                     # Message contains old button state. Re-render it.
                     # Keep the same state (viewing_anime_details)
                     # Display the menu using the shared helper
                     # Needs user object to correctly show the NEW watchlist button state. Re-fetch user.
                     updated_user = await MongoDB.users_collection().find_one({"user_id": user_id}) # Get user after update
                     await edit_or_send_message(
                         client, chat_id, message_id, feedback_message_text, disable_web_page_preview=True # Edit message with just confirmation
                     )
                     # Display menu as new message (safer than complex edit, although edits for just markup preferred)
                     # For complex menu, redisplaying helper that handles buttons is better.
                     # Re-call display_user_anime_details_menu
                     # This function expects Message as first argument (for chat/msg id and type check). Use original CallbackQuery's message.
                     await display_user_anime_details_menu(client, callback_query.message, anime)


                 else:
                     # Anime disappeared after trying to modify its watchlist status.
                     watchlist_logger.error(f"Anime {anime_id_str} disappeared after watchlist {action_type} by user {user_id}. Failed to display menu.")
                     # Display just the feedback message and maybe go back to main menu
                     await edit_or_send_message(client, chat_id, message_id, feedback_message_text + "\n\n💔 Failed to reload Anime Details.", disable_web_page_preview=True)
                     # Go back to main menu implicitly? User can click HOME button which is usually present.


             else: # DB Update failed (e.g., matched user but no modification happened for unexpected reason)
                  watchlist_logger.error(f"DB update for user {user_id} watchlist {action_type} for anime {anime_id_str} failed or modified 0 docs. Update result: {update_result}")
                  # Fallback feedback
                  if action_type == 'add': feedback_message_text = "⚠️ Failed to add anime to watchlist."
                  elif action_type == 'remove': feedback_message_text = "⚠️ Failed to remove anime from watchlist."
                  await client.answer_callback_query(message.id, feedback_message_text, show_alert=True) # Alert user

        else:
             # No DB update attempted (already in watchlist, etc). Just acknowledge callback.
             await client.answer_callback_query(message.id, feedback_message_text, show_alert=False) # Toast (success) or Alert (failure)

             # If it was add/remove on already in list, re-display menu might be confusing, as buttons are same.
             # Best is just answer callback, leave menu as is.
             pass


    except Exception as e:
        # Generic error during handling callback
        watchlist_logger.error(f"FATAL error handling watchlist {action_type} callback {data} for user {user_id}: {e}", exc_info=True)
        # Clear state? User is probably not in a state *specific* to watchlist action itself.
        # User might be in browse/search list state. Clearing state is disruptive. Just log error.
        try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True)
        except Exception: pass
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)


# --- Watchlist Viewing Handler (Callback from Profile) ---
# Catches callbacks: profile_watchlist_menu
@Client.on_callback_query(filters.regex("^profile_watchlist_menu$") & filters.private)
async def view_watchlist_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # The profile message
    data = callback_query.data

    try: await client.answer_callback_query(message.id, "Loading watchlist...")
    except Exception: watchlist_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")

    user = await MongoDB.users_collection().find_one({"user_id": user_id}, {"watchlist": 1}) # Fetch only watchlist for efficiency
    if user is None:
        watchlist_logger.error(f"User {user_id} not found in DB during view watchlist.")
        await edit_or_send_message(client, chat_id, message_id, strings.DB_ERROR, disable_web_page_preview=True)
        return


    user_state = await MongoDB.get_user_state(user_id)
    # Ensure state is updated/correct when entering this view.
    # Coming from profile, state was potentially 'browse', etc., or 'profile_menu'.
    await MongoDB.set_user_state(user_id, "watchlist", WatchlistState.VIEWING_LIST, data={})


    # Get the list of Anime ObjectIds from the user's watchlist
    watchlist_anime_ids_obj = user.get("watchlist", []) # This is already a list of ObjectIds/PyObjectIds due to schema/validation


    menu_text = strings.WATCHLIST_TITLE + "\n\n"
    buttons = []

    if not watchlist_anime_ids_obj:
         menu_text += strings.WATCHLIST_EMPTY
         # No buttons for specific anime if list is empty

    else:
         # Fetch details for the anime in the watchlist (just name for the list)
         # Use $in operator to fetch multiple documents by _id.
         try:
             # Need to fetch projection needed for list display. Sort?
             # Default sort by name A-Z.
             watchlist_anime_docs = await MongoDB.anime_collection().find(
                 {"_id": {"$in": watchlist_anime_ids_obj}},
                 {"name": 1, "_id": 1} # Project name and ID
              ).sort("name", 1).to_list(None) # Get all in list (assume watchlist isn't massive)

             if not watchlist_anime_docs:
                 # Watchlist had IDs, but no matching anime documents found? Data inconsistency.
                 menu_text += "⚠️ Your watchlist seems to contain entries for anime that no longer exist."
                 watchlist_logger.warning(f"User {user_id} watchlist contains IDs ({watchlist_anime_ids_obj}) but no matching anime docs found.")
             else:
                 # Display watchlist anime list with buttons
                 for anime_doc in watchlist_anime_docs:
                      anime_name = anime_doc.get("name", "Unnamed Anime")
                      anime_id_str = str(anime_doc["_id"])

                      # Button label: "Anime Name"
                      button_label = f"🎬 {anime_name}"

                      # Callback: browse_select_anime|<anime_id> (Clicking leads to Anime Details - reusing browse logic)
                      # State transition: watchlist_handler:VIEWING_LIST -> browse_handler:viewing_anime_details (with source_handler='watchlist' in data?)
                      buttons.append([InlineKeyboardButton(button_label, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")]) # Re-use logic to view details


         except Exception as e:
             watchlist_logger.error(f"Failed to fetch anime documents for user {user_id} watchlist: {e}", exc_info=True)
             menu_text += "💔 Error loading watchlist content."
             # Buttons remain empty


    # Add Navigation buttons: Notification Settings, Back to Profile, Back to Main Menu
    buttons.append([InlineKeyboardButton(strings.BUTTON_NOTIFICATION_SETTINGS.format(status="View/Edit"), callback_data="profile_notification_settings_menu")]) # Link to settings
    buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="menu_profile")]) # Back to Profile
    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])


    reply_markup = InlineKeyboardMarkup(buttons)

    # Edit the profile message to display the watchlist menu
    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)

    # State is WatchlistState.VIEWING_LIST, stays until user selects anime, changes settings, or navigates back/home.

# --- Notification Settings Handler (Callback from Profile and Watchlist Menu) ---
# Catches callbacks: profile_notification_settings_menu

@Client.on_callback_query(filters.regex("^profile_notification_settings_menu$") & filters.private)
async def notification_settings_callback(client: Client, callback_query: CallbackQuery):
     user_id = callback_query.from_user.id
     chat_id = callback_query.message.chat.id
     message_id = callback_query.message.id
     data = callback_query.data

     try: await client.answer_callback_query(message.id, "Loading notification settings...")
     except Exception: watchlist_logger.warning(f"Failed to answer callback query {data} from user {user_id}")

     user = await MongoDB.users_collection().find_one({"user_id": user_id})
     if user is None:
         watchlist_logger.error(f"User {user_id} not found in DB during view notification settings.")
         await edit_or_send_message(client, chat_id, message_id, strings.DB_ERROR, disable_web_page_preview=True)
         return


     # User can access this from Profile menu OR Watchlist menu.
     # Ensure state is updated to viewing settings.
     # Previous state might be profile_handler default state or watchlist_handler:VIEWING_LIST
     await MongoDB.set_user_state(user_id, "watchlist", "viewing_notification_settings", data={}) # Simple state name


     # Get current settings from user doc, or use defaults
     current_settings = user.get("notification_settings", config.DEFAULT_NOTIFICATION_SETTINGS.copy()) # Ensure dictionary structure


     menu_text = strings.NOTIFICATION_SETTINGS_TITLE + "\n\n" + strings.NOTIFICATION_SETTINGS_PROMPT
     buttons = []

     # Create toggle buttons for each notification type from config
     # Need a consistent order. Use keys from default settings.
     # Keys: 'new_episode', 'new_version', 'release_date_updated'
     setting_keys = list(config.DEFAULT_NOTIFICATION_SETTINGS.keys()) # Consistent order


     for key in setting_keys:
         label = key.replace('_', ' ').title() # Convert 'new_episode' to 'New Episode'
         # Get button text from strings.py for specific keys
         string_key_button = f"BUTTON_NOTIFY_{key.upper()}_STATE"
         label_from_strings = getattr(strings, string_key_button, label) # Fallback to generated label

         # Check current state
         is_enabled = current_settings.get(key, config.DEFAULT_NOTIFICATION_SETTINGS.get(key, False)) # Get value or use defaults
         button_text = label_from_strings.format(state="✅ On" if is_enabled else "❌ Off")

         # Callback data: watchlist_toggle_notification|<setting_key>
         buttons.append([InlineKeyboardButton(button_text, callback_data=f"watchlist_toggle_notification{config.CALLBACK_DATA_SEPARATOR}{key}")])


     # Add Navigation buttons: Back to Profile, Back to Watchlist, Back to Main Menu, Save?
     # Back goes to Profile, then from Profile they can go to Watchlist list or Main Menu.
     buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="menu_profile")]) # Back to Profile Menu
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Main menu


     reply_markup = InlineKeyboardMarkup(buttons)

     # Edit message to display notification settings menu
     await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)

     # State is "watchlist":"viewing_notification_settings", stays until user interacts with buttons or navigates back.


# Handle toggling notification settings
# Catches callbacks: watchlist_toggle_notification|<setting_key>
@Client.on_callback_query(filters.regex(f"^watchlist_toggle_notification{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def toggle_notification_setting_callback(client: Client, callback_query: CallbackQuery):
     user_id = callback_query.from_user.id
     chat_id = callback_query.message.chat.id
     message_id = callback_query.message.id
     data = callback_query.data

     # Acknowledge immediately
     try: await client.answer_callback_query(message.id)
     except Exception: watchlist_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")


     user_state = await MongoDB.get_user_state(user_id)
     # State should be "watchlist":"viewing_notification_settings"
     if not (user_state and user_state.handler == "watchlist" and user_state.step == "viewing_notification_settings"):
         watchlist_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking toggle notification {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for toggling notification setting. Please return to Notification Settings.", disable_web_page_preview=True)
         await MongoDB.clear_user_state(user_id); return
         # Re-display notification settings menu might be better - notification_settings_callback


     user = await MongoDB.users_collection().find_one({"user_id": user_id})
     if user is None:
         watchlist_logger.error(f"User {user_id} not found in DB during toggle notification setting {data}. DB Error.")
         await edit_or_send_message(client, chat_id, message_id, strings.DB_ERROR, disable_web_page_preview=True)
         # State remains Viewing Settings, user might retry.
         return


     try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for toggling setting.")
        setting_key = parts[1] # e.g., 'new_episode'


        # Validate setting key against allowed defaults
        if setting_key not in config.DEFAULT_NOTIFICATION_SETTINGS:
             watchlist_logger.warning(f"User {user_id} attempted to toggle non-preset notification setting: {setting_key}.")
             await client.answer_callback_query(message.id, "🚫 Invalid setting option.", show_alert=False)
             # State remains Viewing Settings.
             return


        # Get current settings (or defaults) and toggle the specified setting
        current_settings = user.get("notification_settings", config.DEFAULT_NOTIFICATION_SETTINGS.copy()) # Start with current settings or defaults


        is_enabled = current_settings.get(setting_key, config.DEFAULT_NOTIFICATION_SETTINGS.get(setting_key, False)) # Get current value or default default
        new_state = not is_enabled # Toggle state

        # Update the setting in the dictionary
        current_settings[setting_key] = new_state


        # --- Save the updated settings to the user document in database ---
        update_result = await MongoDB.users_collection().update_one(
            {"user_id": user_id},
            {"$set": {"notification_settings": current_settings}} # Overwrite the whole dictionary
        )


        if update_result.matched_count > 0 and update_result.modified_count > 0:
            watchlist_logger.info(f"User {user_id} toggled notification setting '{setting_key}' to {new_state}. Settings: {current_settings}")
            # No need to set state, remains Viewing Settings.
            # Recreate the notification settings keyboard to show updated button states.
            # Use notification_settings_callback to redisplay the menu - Pass message to edit.
            await notification_settings_callback(client, callback_query) # This callback handles fetching updated settings and re-displaying.
            # Needs callback_query object.

        elif update_result.matched_count > 0: # Modified count 0, state was already same
             watchlist_logger.info(f"User {user_id} toggled notification setting '{setting_key}', but state was already {is_enabled}. No update.")
             # Still call re-display to ensure consistency (although button won't change if it matched old state).
             await notification_settings_callback(client, callback_query)

        else: # User doc not found
             watchlist_logger.error(f"User {user_id} not found during notification setting toggle update.")
             await edit_or_send_message(client, chat_id, message_id, strings.DB_ERROR, disable_web_page_preview=True)
             # State remains Viewing Settings.

     except ValueError as e:
         watchlist_logger.warning(f"User {user_id} invalid setting key in toggle notification callback: {data}: {e}")
         await client.answer_callback_query(message.id, "🚫 Invalid setting key.", show_alert=False)
         # State remains Viewing Settings.

     except Exception as e:
         watchlist_logger.error(f"FATAL error handling toggle notification callback {data} for user {user_id}: {e}", exc_info=True)
         # Clear state if it was ViewingSettings on complex error.
         if user_state and user_state.handler == "watchlist" and user_state.step == "viewing_notification_settings":
             await MongoDB.clear_user_state(user_id) # Clear this specific state


         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)


# --- Notification Logic (Triggered by Admin Content Updates) ---

async def notify_watchlist_users_about_update(client: Client, anime_id: ObjectId, season_number: int, episode_number: int, update_type: str, update_details: Optional[Dict] = None):
    """
    Finds users who have the specified anime in their watchlist and are
    subscribed to notifications for the given update type, and sends them a message.
    This function should be called by content_handler.py when a relevant update occurs
    (e.g., after adding a new episode, adding a file version).
    """
    notification_logger = logging.getLogger("NotificationLogic")
    notification_logger.info(f"Initiating watchlist notification for anime ID {anime_id}, S{season_number}E{episode_number}, update type: {update_type}. Details: {update_details}")


    # Validate update type
    allowed_update_types = ["new_episode", "new_version", "release_date_updated"]
    if update_type not in allowed_update_types:
         notification_logger.error(f"Attempted to send watchlist notification with invalid update type: {update_type}. Aborting.")
         return


    try:
        # Find all users whose watchlist contains the specified anime_id
        # And whose notification_settings for the given update_type is True
        filter_query = {
            "watchlist": anime_id, # Find documents where watchlist array contains this ObjectId
            # Need to also filter based on nested notification_settings
            f"notification_settings.{update_type}": True # Example filter for nested key
        }

        # Project only user_id to send messages
        projection = {"user_id": 1}

        # Fetch users as a list of user_id documents
        users_to_notify_docs = await MongoDB.users_collection().find(filter_query, projection).to_list(None)

        if not users_to_notify_docs:
            notification_logger.info(f"No users found on watchlist for anime {anime_id} with '{update_type}' notifications enabled.")
            return # No one to notify

        notification_logger.info(f"Found {len(users_to_notify_docs)} users to notify about update for anime {anime_id}, type '{update_type}'.")

        # --- Construct the Notification Message ---
        # Needs context about the anime and episode/update. Fetch anime name.
        anime = await MongoDB.anime_collection().find_one({"_id": anime_id}, {"name": 1})
        anime_name = anime.get("name", "An Anime") if anime else "An Anime"

        message_text = ""
        reply_markup = None # Can add button to episode/version


        if update_type == "new_episode":
             # Fetch the specific episode document to get release date or other info
             filter_episode = {"_id": anime_id, "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}
             projection_episode = {"name":1, "seasons.$": 1} # Project matched season to get episode details
             anime_doc_episode = await MongoDB.anime_collection().find_one(filter_episode, projection_episode)
             episode_details_doc = None
             if anime_doc_episode and anime_doc_episode.get("seasons") and anime_doc_episode["seasons"][0] and anime_doc_episode["seasons"][0].get("episodes"):
                 episode_details_doc = anime_doc_episode["seasons"][0]["episodes"][0] # The episode doc itself


             # Link should go to Anime Details menu. Needs anime ID in callback.
             button_callback = f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{str(anime_id)}" # Link to view anime details menu

             # Or link directly to the episode versions list? More complex. Requires new state/handler entry point.
             # Callback: download_select_episode|<anime_id>|<season>|<ep>
             button_callback_direct_episode = f"download_select_episode{config.CALLBACK_DATA_SEPARATOR}{str(anime_id)}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}"


             # Construct message using string format
             message_text = strings.WATCHLIST_ADDED_NOTIFICATION.format(
                 anime_title=anime_name,
                 season_number=season_number,
                 episode_number=episode_number,
                 # Placeholder for anime_url needs to point to a place where they can click to see details in bot.
                 # Use a Telegram Deep Link back to bot with /start payload encoding anime ID? Or use callback button.
                 anime_url=f"https://t.me/{client.me.username}?start=view_anime_{str(anime_id)}" # Example deep link payload
                 # OR pass nothing, add button instead. Use BUTTON_SEE_DETAILS_OR_EPISODE
             )

             # Add a button to jump to the episode's version list directly (recommended)
             buttons = [[InlineKeyboardButton(f"🎬 View S{season_number}E{episode_number:02d}", callback_data=button_callback_direct_episode)]]
             # Maybe also button to just see anime details: [InlineKeyboardButton("Info", callback_data=button_callback)]
             buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Main menu always

             reply_markup = InlineKeyboardMarkup(buttons)


        elif update_type == "new_version":
             # Expecting update_details dict containing 'file_unique_id', maybe quality, audio, subs?
             if update_details is None or not update_details.get("file_unique_id"):
                 notification_logger.error(f"Missing file unique ID in details for new_version notification for {anime_id}/S{season_number}E{episode_number}. Details: {update_details}. Aborting notification.")
                 return # Cannot send notification if missing crucial info


             # Fetch details for the specific file version to include info in message.
             # Need to find the file version within the episode, or rely on details in update_details
             # Rely on update_details containing summary info for the notification message.
             version_summary = update_details.get("version_summary", "a new version") # e.g. "1080p (JP/EN Subs)"

             # Link directly to episode version list is best. Callback: download_select_episode|<anime_id>|<season>|<ep>
             button_callback_episode = f"download_select_episode{config.CALLBACK_DATA_SEPARATOR}{str(anime_id)}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}"

             message_text = strings.WATCHLIST_NEW_VERSION_NOTIFICATION.format(
                  anime_title=anime_name,
                  season_number=season_number,
                  episode_number=episode_number,
                  version_summary=version_summary,
                 # Anime_url needs to be link to details/bot.
                 anime_url=f"https://t.me/{client.me.username}?start=view_anime_{str(anime_id)}"
             )
             # Add a button to jump directly to episode versions list
             buttons = [[InlineKeyboardButton(f"📥 View Download Options", callback_data=button_callback_episode)]]
             buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])
             reply_markup = InlineKeyboardMarkup(buttons)


        elif update_type == "release_date_updated":
            # Notification for date update. Requires details like the date string.
            # Requires config DEFAULT_NOTIFICATION_SETTINGS.release_date_updated = True
            # Get formatted date from update_details?
             formatted_date = update_details.get("release_date", "An Updated Date")

            # Link directly to episode details. Callback: download_select_episode|<anime_id>|<season>|<ep>
             button_callback_episode = f"download_select_episode{config.CALLBACK_DATA_SEPARATOR}{str(anime_id)}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}"

             message_text = f"🔔 <b><u>Watchlist Update!</u></b> 🔔\n\nRelease date updated for <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b>."
             if formatted_date != "An Updated Date":
                 message_text += f"\n\nNew Estimated Release: <b>{formatted_date}</b>." # Add date if available

             message_text += f"\n\nCheck episode details: 👇"

             # Add a button to jump directly to episode management view (user version)
             buttons = [[InlineKeyboardButton(f"⏳ View Episode Details", callback_data=button_callback_episode)]]
             buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])
             reply_markup = InlineKeyboardMarkup(buttons)


        else:
             notification_logger.error(f"Notification message creation not implemented for update type: {update_type}")
             return # Cannot send message if type is not handled.


        # --- Send the Message to Each User ---
        # Iterate through the list of user document dictionaries and send the message to each user_id.
        for user_doc in users_to_notify_docs:
            user_id_to_notify = user_doc.get("user_id")
            if user_id_to_notify is None: continue # Skip if user_id is missing


            try:
                # Use client.send_message. Catch FloodWait, UserNotParticipant (user blocked bot).
                await client.send_message(
                     chat_id=user_id_to_notify, # Send to the user's private chat
                     text=message_text,
                     reply_markup=reply_markup,
                     parse_mode=config.PARSE_MODE,
                     disable_web_page_preview=True # Good for URLs, preventing big previews.
                 )
                notification_logger.debug(f"Sent '{update_type}' notification to user {user_id_to_notify} for anime {anime_id}.")

            except UserNotParticipant:
                notification_logger.info(f"User {user_id_to_notify} not participating or blocked bot. Cannot send notification for anime {anime_id}.")
                 # Consider removing user from watchlist automatically if this happens frequently? Optional.
            except FloodWait as e:
                 notification_logger.warning(f"FloodWait while sending notification to user {user_id_to_notify}. Retrying after {e.value}s for anime {anime_id}: {e}")
                 await asyncio.sleep(e.value)
                 # Retry sending to this user once? Or skip this user?
                 try: await client.send_message(chat_id=user_id_to_notify, text=message_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True)
                 except Exception as retry_e: notification_logger.error(f"Retry failed sending notification to {user_id_to_notify} for anime {anime_id}: {retry_e}", exc_info=True)
                 pass # Continue to next user even if retry failed

            except Exception as e:
                # Catch any other error during message sending
                notification_logger.error(f"Failed to send notification message to user {user_id_to_notify} for anime {anime_id}: {e}", exc_info=True)
                # Continue to the next user even if one send fails


    except Exception as e:
         notification_logger.critical(f"FATAL error during watchlist notification processing for anime {anime_id}: {e}", exc_info=True)
         # Don't raise exception here, notification is a background-like task.
         # Ensure critical logging triggers alerts for admins.
