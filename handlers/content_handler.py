# handlers/content_handler.py
import logging
from typing import Union
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
from datetime import datetime, timezone
import config
from strings import (
    MANAGE_CONTENT_TITLE, MANAGE_CONTENT_OPTIONS,
    BUTTON_ADD_NEW_ANIME, BUTTON_EDIT_ANIME, BUTTON_VIEW_ALL_ANIME, BUTTON_HOME,
    ADD_ANIME_NAME_PROMPT, ADD_ANIME_NAME_SEARCH_RESULTS, BUTTON_ADD_AS_NEW_ANIME,
    BUTTON_CANCEL, ACTION_CANCELLED, ERROR_OCCURRED, BUTTON_BACK,
    ADD_ANIME_POSTER_PROMPT, ADD_ANIME_SYNOPSIS_PROMPT, ADD_ANIME_SEASONS_PROMPT,
    ADD_ANIME_GENRES_PROMPT, BUTTON_METADATA_DONE_SELECTING,
    ADD_ANIME_YEAR_PROMPT, ADD_ANIME_STATUS_PROMPT,

    MANAGE_SEASONS_TITLE, SEASON_MANAGEMENT_OPTIONS, BUTTON_ADD_NEW_SEASON,
    BUTTON_REMOVE_SEASON, BUTTON_MANAGE_EPISODES, BUTTON_BACK_TO_ANIME_LIST,
    ADD_SEASON_EPISODES_PROMPT, EPISODES_CREATED_SUCCESS,

    MANAGE_EPISODES_TITLE, EPISODE_OPTIONS_NO_FILES, EPISODE_OPTIONS_WITH_RELEASE_DATE,
    EPISODE_OPTIONS_WITH_FILES, BUTTON_ADD_EPISODE_FILE, BUTTON_ADD_RELEASE_DATE,
    BUTTON_REMOVE_EPISODE, PROMPT_RELEASE_DATE, RELEASE_DATE_SET_SUCCESS, INVALID_DATE_FORMAT,

    ADD_FILE_PROMPT, ADD_FILE_METADATA_PROMPT_BUTTONS, PROMPT_AUDIO_LANGUAGES_BUTTONS,
    PROMPT_SUBTITLE_LANGUAGES_BUTTONS, BUTTON_ADD_OTHER_VERSION, BUTTON_NEXT_EPISODE,
    BUTTON_DELETE_FILE_VERSION, FILE_ADDED_SUCCESS, FILE_DELETED_SUCCESS,
    BUTTON_DONE, BUTTON_SELECT, BUTTON_UNSELECT # Generic multi-select button states

)

from database.mongo_db import MongoDB, get_user_state, set_user_state, clear_user_state
from database.models import UserState, Anime, Season, Episode, FileVersion, PyObjectId
from handlers.common_handlers import get_user, create_main_menu_keyboard

# Fuzzy search library
from fuzzywuzzy import process

# Configure logger for content handlers
content_logger = logging.getLogger(__name__)

# --- States for Content Management Process ---
# These will be stored in the user_states collection
# Handler Name: "content_management"
class ContentState:
    AWAITING_ANIME_NAME = "awaiting_anime_name"
    AWAITING_POSTER = "awaiting_poster"
    AWAITING_SYNOPSIS = "awaiting_synopsis"
    AWAITING_SEASONS_COUNT = "awaiting_seasons_count"    
    # SELECTING_SEARCH_RESULT = "selecting_search_result" # This is handled within AWAITING_ANIME_NAME processing now
    SELECTING_GENRES = "selecting_genres"
    AWAITING_RELEASE_YEAR = "awaiting_release_year"
    SELECTING_STATUS = "selecting_status"
    MANAGING_ANIME_MENU = "managing_anime_menu" # Main menu for a specific anime
    MANAGING_SEASONS_LIST = "managing_seasons_list" # Displaying seasons of an anime
    MANAGING_EPISODES_LIST = "managing_episodes_list" # Displaying episodes of a season
    EDITING_SYNOPSIS = "editing_synopsis"
    EDITING_POSTER = "editing_poster"
    EDITING_NAME = "editing_name"
    EDITING_RELEASE_YEAR = "editing_release_year"
    MANAGING_EPISODE_MENU = "managing_episode_menu" # Options for a specific episode
    AWAITING_RELEASE_DATE_INPUT = "awaiting_release_date_input" # Waiting for date string
    UPLOADING_FILE = "uploading_file" # Waiting for episode file
    SELECTING_METADATA_QUALITY = "selecting_metadata_quality" # Multi-step via callbacks
    SELECTING_METADATA_AUDIO = "selecting_metadata_audio"   # Multi-step via callbacks
    SELECTING_METADATA_SUBTITLES = "selecting_metadata_subtitles"# Multi-step via callbacks
    

# --- Entry Point for Content Management ---

# This handler initiates the content management process.
# It's accessible via a command or potentially a button for admins.
# For now, assume an admin command. Admin access check required.
@Client.on_message(filters.command("manage_content") & filters.private)
async def manage_content_command(client: Client, message: Message):
    """Handles the /manage_content command, displays admin content menu."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await message.reply_text("🚫 You are not authorized to use this command.", parse_mode=config.PARSE_MODE)
        return

    content_logger.info(f"Admin user {user_id} entered content management.")

    # Check and clear any previous state if it exists (e.g., user didn't cancel properly)
    # We don't want leftover states interfering. A timeout mechanism on states would be better.
    # For simplicity now, entering /manage_content *always* starts fresh state for THIS menu.
    # If they were in a deeper content state, we *might* want to allow them to resume.
    # For now, we assume starting /manage_content resets the *entry* state.
    # Deep state resuming needs more complex state data (e.g., storing anime_id being edited).

    # Set the user state for the content management *menu*
    await set_user_state(user_id, "content_management", "main_menu") # State indicates admin is in main CM menu

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(BUTTON_ADD_NEW_ANIME, callback_data="content_add_new_anime")],
        [InlineKeyboardButton(BUTTON_EDIT_ANIME, callback_data="content_edit_anime")],
        [InlineKeyboardButton(BUTTON_VIEW_ALL_ANIME, callback_data="content_view_all")],
        [InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home")], # Back to main bot menu
    ])

    try:
        await message.reply_text(
            f"**{MANAGE_CONTENT_TITLE}**\n\n{MANAGE_CONTENT_OPTIONS}",
            reply_markup=reply_markup,
            parse_mode=config.PARSE_MODE,
            disable_web_page_preview=True
        )
    except Exception as e:
        content_logger.error(f"Failed to send manage content menu to admin {user_id}: {e}")
        await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)

# --- Handling Main Menu Button Callbacks ---

@Client.on_callback_query(filters.regex("^content_") & filters.private)
async def content_menu_callbacks(client: Client, callback_query: CallbackQuery):
    """Handles callbacks from the main content management menu."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return # Stop execution

    content_logger.info(f"Admin user {user_id} clicked callback: {data}")

    # Acknowledge the callback query immediately
    try:
        await callback_query.answer()
    except Exception:
        content_logger.warning(f"Failed to answer callback query: {data} from admin {user_id}")


    # Check the user's state to ensure they are in the content management flow or starting one
    # For now, simple check, but can refine if deeper states should resume.
    user_state = await get_user_state(user_id)
    # We expect state "content_management:main_menu" if they are properly interacting with the menu.
    # If state is missing or wrong, maybe re-send the menu or inform admin.
    if user_state is None or user_state.handler != "content_management" or user_state.step != "main_menu":
         content_logger.warning(f"Admin {user_id} clicked {data} but state is {user_state}. Re-sending menu.")
         await callback_query.message.reply_text("🔄 Invalid state or action. Resetting...", parse_mode=config.PARSE_MODE)
         await manage_content_command(client, callback_query.message) # Resend the main menu
         return # Stop here

    # --- Process Callback Data ---

    if data == "content_add_new_anime":
        # Move to the state of awaiting anime name input for adding
        await set_user_state(user_id, "content_management", ContentState.AWAITING_ANIME_NAME)

        # Prompt the admin for the anime name
        prompt_text = ADD_ANIME_NAME_PROMPT.format()
        reply_markup = InlineKeyboardMarkup([
             [InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")] # Add a cancel button
        ])

        try:
            await callback_query.message.edit_text(
                prompt_text,
                reply_markup=reply_markup,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=True
            )
        except Exception as e:
            content_logger.error(f"Failed to edit message for awaiting anime name prompt for admin {user_id}: {e}")
            # If edit fails, send as new message
            await client.send_message(
                 chat_id=chat_id,
                 text=prompt_text,
                 reply_markup=reply_markup,
                 parse_mode=config.PARSE_MODE,
                 disable_web_page_preview=True
             )

    elif data == "content_edit_anime":
        # This requires searching for existing anime first.
        # Reuse the state AWAITING_ANIME_NAME, but differentiate its purpose using data
        await set_user_state(user_id, "content_management", ContentState.AWAITING_ANIME_NAME, data={"purpose": "edit"})

        prompt_text = ADD_ANIME_NAME_PROMPT.format() # Use the same prompt initially
        reply_markup = InlineKeyboardMarkup([
             [InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]
        ])
        try:
            await callback_query.message.edit_text(
                prompt_text,
                reply_markup=reply_markup,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=True
            )
        except Exception as e:
             content_logger.error(f"Failed to edit message for awaiting anime name prompt (edit) for admin {user_id}: {e}")
             await client.send_message(
                 chat_id=chat_id,
                 text=prompt_text,
                 reply_markup=reply_markup,
                 parse_mode=config.PARSE_MODE,
                 disable_web_page_preview=True
             )


    elif data == "content_view_all":
        # Implementation to list all anime for admins
        # This might need pagination and buttons to select an anime for editing.
        await callback_query.message.reply_text("Feature: View All Anime (Under Construction)", parse_mode=config.PARSE_MODE) # Placeholder
        # Stay in the content_management:main_menu state for now
        pass # Placeholder


    elif data == "content_cancel":
        # Handles the cancel button within the content management flow
        await clear_user_state(user_id)
        await callback_query.message.edit_text(
            ACTION_CANCELLED,
            parse_mode=config.PARSE_MODE
            # No keyboard needed after cancelling
        )
        content_logger.info(f"Admin user {user_id} cancelled content management input.")


    # Note: The common_handlers.py file will now route text input received
    # while user_state.handler is "content_management" to the content handler's
    # text processing function. We need to build that function next.


# --- Handling Text Input When in Content Management State ---
# Update handle_content_input to include logic for new states

async def handle_content_input(client: Client, message: Message, user_state: UserState):
    """
    Handles text input from an admin user currently in the content_management state.
    Called by common_handlers.handle_plain_text_input.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    input_text = message.text.strip()
    current_step = user_state.step

    content_logger.debug(f"Handling content input for user {user_id} at step: {current_step} with text: '{input_text[:50]}...'")

    # Route based on the current step
    if current_step == ContentState.AWAITING_ANIME_NAME:
         await handle_awaiting_anime_name_input(client, message, user_state) # Handles search and routing to add/edit path

    # --- New/Expanded Steps Expecting Text Input ---
    elif current_step == ContentState.AWAITING_SYNOPSIS:
         await handle_awaiting_synopsis_input(client, message, user_state, input_text)
    elif current_step == ContentState.AWAITING_SEASONS_COUNT:
         await handle_awaiting_seasons_count_input(client, message, user_state, input_text)
    elif current_step == ContentState.AWAITING_RELEASE_YEAR:
         await handle_awaiting_release_year_input(client, message, user_state, input_text)

    # States for EDITING via Text Input (Re-using AWAITING logic with different context)
    elif current_step == ContentState.EDITING_NAME:
         await handle_editing_name_input(client, message, user_state, input_text)
    elif current_step == ContentState.EDITING_SYNOPSIS:
         await handle_editing_synopsis_input(client, message, user_state, input_text)
    elif current_step == ContentState.EDITING_RELEASE_YEAR:
         await handle_editing_release_year_input(client, message, user_state, input_text)
    elif current_step == ContentState.AWAITING_RELEASE_DATE_INPUT:
         await handle_awaiting_release_date_input(client, message, user_state, input_text)


    # --- States Expecting File Input (Routed from handle_file_input in common_handlers) ---
    # handle_awaiting_poster and handle_episode_file_upload are called by common_handlers
    # We don't need elif branches for those here as this only handles *text*.

    # --- Callback-Based States ---
    # SELECTING_GENRES, SELECTING_STATUS, SELECTING_METADATA_QUALITY,
    # SELECTING_METADATA_AUDIO, SELECTING_METADATA_SUBTITLES
    # These states process BUTTON CLICKS via dedicated @Client.on_callback_query handlers,
    # so their input logic isn't here in handle_content_input (which is text only).

    else:
        # Received unexpected text input for the current state
        content_logger.warning(f"Admin {user_id} sent unexpected text input while in content management state {user_state.step}: '{input_text[:50]}...'")
        await message.reply_text("🤔 That wasn't the input I was expecting for this step. Please send the requested information, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)


# --- Update Handle File Input to Route New States ---
# This is defined in common_handlers.py but we need to know its routing logic here.
# handle_file_input in common_handlers will call specific content_handler async functions:
# If state is AWAITING_POSTER and message.photo exists -> call handle_awaiting_poster(client, message, user_state)
# If state is UPLOADING_FILE and message.document or message.video exists -> call handle_episode_file_upload(client, message, user_state, file_details)

async def handle_awaiting_poster(client: Client, message: Message, user_state: UserState):
     """Handles admin input when in the AWAITING_POSTER state (expects photo). Called from common_handlers."""
     user_id = message.from_user.id
     chat_id = message.chat.id

     # Assumes check for message.photo is done in common_handlers
     file_id = message.photo[-1].file_id # Get highest quality version file_id
     anime_name = user_state.data.get("new_anime_name", "Anime Name Unknown")

     content_logger.info(f"Admin {user_id} provided poster photo ({file_id}) for '{anime_name}' in AWAITING_POSTER.")

     # Store the poster_file_id in state data
     user_state.data["poster_file_id"] = file_id
     # We can also store file_unique_id, file_size etc from message.photo here if needed
     # user_state.data["poster_unique_id"] = message.photo[-1].file_unique_id
     # user_state.data["poster_size"] = message.photo[-1].file_size

     # Move to the next step: AWAITING_SYNOPSIS
     await set_user_state(user_id, "content_management", ContentState.AWAITING_SYNOPSIS, data=user_state.data)

     # Prompt for synopsis
     await prompt_for_synopsis(client, chat_id, anime_name)

     # Optional: Reply to the photo message
     try:
          await message.reply_text("🖼️ Poster received! Now send the **__Synopsis__** for this anime.", parse_mode=config.PARSE_MODE)
     except Exception as e:
          content_logger.warning(f"Failed to reply after poster input for admin {user_id}: {e}")


async def handle_episode_file_upload(client: Client, message: Message, user_state: UserState):
     """Handles admin file upload when in the UPLOADING_FILE state. Called from common_handlers."""
     user_id = message.from_user.id
     chat_id = message.chat.id

     # Assumes check for message.document or message.video is done in common_handlers
     file = message.document if message.document else message.video
     file_id = file.file_id
     file_unique_id = file.file_unique_id
     file_name = file.file_name or f"episode_file_{file_id[:8]}" # Generate name if missing
     file_size_bytes = file.file_size
     mime_type = file.mime_type

     # Get necessary context from state data
     anime_id_str = user_state.data.get("anime_id") # The anime this file belongs to
     season_number = user_state.data.get("season_number") # The season number
     episode_number = user_state.data.get("episode_number") # The episode number
     anime_name = user_state.data.get("anime_name", "Anime Name Unknown")

     if not anime_id_str or season_number is None or episode_number is None:
          # State data is missing critical information, something went wrong
          content_logger.error(f"Admin {user_id} uploaded episode file in UPLOADING_FILE state but missing required state data (anime_id, season, episode). State: {user_state.data}")
          await message.reply_text("💔 Critical Error: State data missing for episode file upload. Process cancelled.", parse_mode=config.PARSE_MODE)
          await clear_user_state(user_id) # Clear broken state
          return

     content_logger.info(f"Admin {user_id} provided episode file ({file_id}, {file_size_bytes} bytes) for {anime_name} S{season_number}E{episode_number} in UPLOADING_FILE.")

     # Store temporary file details in state data before proceeding to metadata selection
     user_state.data["temp_upload"] = {
         "file_id": file_id,
         "file_unique_id": file_unique_id,
         "file_name": file_name,
         "file_size_bytes": file_size_bytes,
         "mime_type": mime_type, # Useful for debugging
     }
     # Need to persist the anime/season/episode context through state updates

     # Move to the next step: SELECTING_METADATA_QUALITY (First step of metadata collection)
     await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_QUALITY, data=user_state.data)

     # Prompt the admin for quality selection
     await prompt_for_metadata_quality(client, chat_id)

     # Optional confirmation reply
     try:
         # Edit the original file message caption? Or send a new message. New is simpler.
          await message.reply_text(f"💾 File received for Episode {episode_number:02d}! Now select the **__Quality/Resolution__**.", parse_mode=config.PARSE_MODE)
     except Exception as e:
          content_logger.warning(f"Failed to reply after file upload for admin {user_id}: {e}")


# --- Update Handle Plain Text Input with new routing for editing specific fields ---
# Logic is now centralized in the content_handler itself: handle_content_input above


# --- New Handlers for Editing Specific Anime Fields (from display_anime_management_menu callbacks) ---
# These handlers transition to specific text-input states

@Client.on_callback_query(filters.regex("^content_edit_name\|.*") & filters.private)
async def content_edit_name_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Edit Name button."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_edit_name|<anime_id>

    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    await callback_query.answer()

    # Check state and parse anime_id
    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         await callback_query.message.reply_text("🔄 Invalid state for editing name.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id)
         return # Cannot edit name if not managing an anime

    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        # Ensure state data also holds the correct anime_id - cross-check is good
        if user_state.data.get("anime_id") != anime_id_str:
            content_logger.warning(f"Admin {user_id} state anime_id {user_state.data.get('anime_id')} doesn't match callback anime_id {anime_id_str} for editing name.")
            # Decide how to handle mismatch: maybe clear state or trust callback?
            # Trusting callback for the action but checking state for process context
            user_state.data["anime_id"] = anime_id_str # Update state data to match callback
            # Should refetch anime details based on ID if we only store ID in state

        # Transition to the state waiting for the new name
        await set_user_state(user_id, "content_management", ContentState.EDITING_NAME, data=user_state.data) # Keep existing data

        # Prompt admin for new name
        prompt_text = ADD_ANIME_NAME_PROMPT.replace("new anime", "anime").format(anime_name="") # Re-use prompt but modify text
        prompt_text = "✏️ Send the **__New Name__** for this anime:" # Specific prompt
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]])

        await callback_query.message.edit_text(
            prompt_text,
            reply_markup=reply_markup,
            parse_mode=config.PARSE_MODE
        )

    except Exception as e:
        content_logger.error(f"Error handling content_edit_name callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


# Helper to handle text input when editing name
async def handle_editing_name_input(client: Client, message: Message, user_state: UserState, new_name: str):
    """Handles admin text input when in the EDITING_NAME state."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_id_str = user_state.data.get("anime_id")

    if not anime_id_str:
        content_logger.error(f"Admin {user_id} sent new anime name but missing anime_id in state data.")
        await message.reply_text("💔 Error: Anime ID missing from state. Please try editing again from the management menu.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)
        return

    # Find the anime in DB
    try:
         anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)})
         if not anime_doc:
             content_logger.error(f"Anime ID {anime_id_str} not found when admin {user_id} tried to edit name.")
             await message.reply_text("💔 Error: Anime not found. Please try editing again from the management menu.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id)
             return

         # Update the name
         update_result = await MongoDB.anime_collection().update_one(
             {"_id": ObjectId(anime_id_str)},
             {"$set": {"name": new_name, "last_updated_at": datetime.now(timezone.utc)}}
         )

         if update_result.modified_count > 0:
             content_logger.info(f"Admin {user_id} successfully updated name of anime {anime_id_str} to '{new_name}'.")
             # Return to the anime management menu for this anime
             # Need to re-fetch the anime document to display the updated info in the menu
             updated_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)})
             if updated_anime_doc:
                  updated_anime = Anime(**updated_anime_doc)
                  # Clear editing state and set state to managing this anime
                  await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": anime_id_str, "anime_name": new_name}) # Update name in state data
                  await message.reply_text(f"✅ Name updated to **__{new_name}__**!", parse_mode=config.PARSE_MODE)
                  await display_anime_management_menu(client, message, updated_anime)
             else:
                 content_logger.error(f"Failed to retrieve anime {anime_id_str} after name update for admin {user_id}.")
                 await message.reply_text(f"✅ Name updated to **__{new_name}__**, but failed to load the management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id) # Clear state as cannot display menu
                 # await manage_content_command(client, message) # Optionally go back to main CM menu
         else:
             # Modified count is 0 - likely same name was entered.
             content_logger.info(f"Admin {user_id} tried to update name of anime {anime_id_str} but name was same ('{new_name}').")
             await message.reply_text("✅ Name is already **__{new_name}__**. No changes made.", parse_mode=config.PARSE_MODE)
             # State is still EDITING_NAME, needs explicit cancel or back?
             # Or route them back to the managing menu directly? Let's route back.
             # Re-fetch the anime document to display the menu
             current_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)})
             if current_anime_doc:
                 current_anime = Anime(**current_anime_doc)
                 await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": anime_id_str, "anime_name": current_anime.name})
                 await display_anime_management_menu(client, message, current_anime)
             else:
                  content_logger.error(f"Failed to retrieve anime {anime_id_str} to display menu after no-change name edit for admin {user_id}.")
                  await message.reply_text("🔄 No change made. Failed to load the management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                  await clear_user_state(user_id)


    except Exception as e:
         content_logger.error(f"Error updating anime name {anime_id_str} to '{new_name}' for admin {user_id}: {e}")
         await message.reply_text("💔 Error updating anime name.", parse_mode=config.PARSE_MODE)
         # State is EDITING_NAME, needs cancel or retry


# Implement similar pattern for content_edit_synopsis, content_edit_poster, content_edit_year, content_edit_status, content_edit_seasons_count

# Callback for editing synopsis
@Client.on_callback_query(filters.regex("^content_edit_synopsis\|.*") & filters.private)
async def content_edit_synopsis_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    # ... (Admin check and state check) ...
    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer()
    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         await callback_query.message.reply_text("🔄 Invalid state for editing synopsis.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return
    try:
        anime_id_str = callback_query.data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        # ... (Ensure anime_id matches state or update state) ...
        user_state.data["anime_id"] = anime_id_str # Ensure anime_id is in state data
        await set_user_state(user_id, "content_management", ContentState.EDITING_SYNOPSIS, data=user_state.data)
        prompt_text = ADD_ANIME_SYNOPSIS_PROMPT.replace("for '{anime_name}'", "").format(anime_name="") # Modify prompt slightly
        prompt_text = "📝 Send the **__New Synopsis__** for this anime:"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]])
        await callback_query.message.edit_text(prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
    except Exception as e: content_logger.error(f"Error handling edit synopsis callback {user_id}: {e}"); await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)

# Helper to handle text input when editing synopsis
async def handle_editing_synopsis_input(client: Client, message: Message, user_state: UserState, new_synopsis: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_id_str = user_state.data.get("anime_id")
    # ... (Error handling if anime_id missing or anime not found, update DB using $set on synopsis field, handle modified_count, route back to MANAGEMENT_ANIME_MENU) ...
    if not anime_id_str: await message.reply_text("💔 Error: Anime ID missing from state. Try editing again.", parse_mode=config.PARSE_MODE); await clear_user_state(user_id); return
    try:
        # ... (Find anime doc) ...
        update_result = await MongoDB.anime_collection().update_one(
            {"_id": ObjectId(anime_id_str)},
            {"$set": {"synopsis": new_synopsis, "last_updated_at": datetime.now(timezone.utc)}}
        )
        # ... (Handle modified_count, log success/no change) ...
        if update_result.modified_count > 0:
             await message.reply_text("✅ Synopsis updated!", parse_mode=config.PARSE_MODE)
        else: await message.reply_text("✅ Synopsis is already the same. No changes.", parse_mode=config.PARSE_MODE)
        # ... (Fetch updated anime, transition state back, display menu, handle errors) ...
        updated_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)})
        if updated_anime_doc:
            updated_anime = Anime(**updated_anime_doc)
            await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": anime_id_str, "anime_name": updated_anime.name})
            await display_anime_management_menu(client, message, updated_anime)
        else: raise Exception("Failed to fetch after update")
    except Exception as e: content_logger.error(f"Error updating synopsis {anime_id_str} for admin {user_id}: {e}"); await message.reply_text("💔 Error updating synopsis.", parse_mode=config.PARSE_MODE)


# Similar logic for content_edit_poster callback and handle_editing_poster (uses file input handling from common_handlers)
@Client.on_callback_query(filters.regex("^content_edit_poster\|.*") & filters.private)
async def content_edit_poster_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    # ... (Admin check, state check, get anime_id from callback/state) ...
    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer()
    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         await callback_query.message.reply_text("🔄 Invalid state for editing poster.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return
    try:
         anime_id_str = callback_query.data.split(config.CALLBACK_DATA_SEPARATOR)[1]
         user_state.data["anime_id"] = anime_id_str # Ensure in state
         # Set state to AWAITING_POSTER (reuse), but add context that this is an edit
         await set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={**user_state.data, "purpose": "edit"}) # Merge existing data + purpose

         prompt_text = ADD_ANIME_POSTER_PROMPT.replace("for '{anime_name}'", "").format(anime_name="") # Modify prompt
         prompt_text = "🖼️ Send the **__New Poster Image__** for this anime:"
         reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]])
         await callback_query.message.edit_text(prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
    except Exception as e: content_logger.error(f"Error handling edit poster callback {user_id}: {e}"); await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)

# Helper handled by handle_file_input when state is AWAITING_POSTER (already defined)
# def handle_awaiting_poster(client, message, user_state): ... (logic will need to check user_state.data.get("purpose") to differentiate ADD vs EDIT flow end)

# The AWAITING_POSTER logic needs to check user_state.data for the "purpose".
# If purpose is "add", it moves to AWAITING_SYNOPSIS (as implemented).
# If purpose is "edit", it needs to update the EXISTING anime's poster_file_id in the DB
# and then route back to the MANAGEMENT_ANIME_MENU for that anime.
async def handle_awaiting_poster(client: Client, message: Message, user_state: UserState):
     """Handles admin input when in the AWAITING_POSTER state (expects photo). Called from common_handlers."""
     user_id = message.from_user.id
     chat_id = message.chat.id
     anime_id_str = user_state.data.get("anime_id") # Needed for edit purpose
     anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")) # Get name for logging/messages

     if message.photo:
          file_id = message.photo[-1].file_id
          purpose = user_state.data.get("purpose", "add") # Get the purpose

          content_logger.info(f"Admin {user_id} provided poster photo ({file_id}) for '{anime_name}' in AWAITING_POSTER (Purpose: {purpose}).")

          if purpose == "add":
              # Already handled above: store poster_file_id, set state to AWAITING_SYNOPSIS, prompt for synopsis
              user_state.data["poster_file_id"] = file_id
              await set_user_state(user_id, "content_management", ContentState.AWAITING_SYNOPSIS, data=user_state.data)
              await prompt_for_synopsis(client, chat_id, anime_name)
              try: await message.reply_text("🖼️ Poster received! Now send the **__Synopsis__**.", parse_mode=config.PARSE_MODE);
              except Exception: pass

          elif purpose == "edit":
              # Update the EXISTING anime's poster
              if not anime_id_str:
                 content_logger.error(f"Admin {user_id} in EDIT purpose AWAITING_POSTER state but missing anime_id.")
                 await message.reply_text("💔 Error: Anime ID missing. Cannot update poster.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id)
                 return

              try:
                  update_result = await MongoDB.anime_collection().update_one(
                      {"_id": ObjectId(anime_id_str)},
                      {"$set": {"poster_file_id": file_id, "last_updated_at": datetime.now(timezone.utc)}}
                  )
                  if update_result.modified_count > 0:
                       content_logger.info(f"Admin {user_id} updated poster for anime {anime_id_str}.")
                       await message.reply_text("✅ Poster updated!", parse_mode=config.PARSE_MODE)
                       # Fetch updated anime and return to management menu
                       updated_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)})
                       if updated_anime_doc:
                           updated_anime = Anime(**updated_anime_doc)
                           # Clear the AWAITING_POSTER state, set state back to managing
                           await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": anime_id_str, "anime_name": updated_anime.name}) # Update state name
                           await display_anime_management_menu(client, message, updated_anime)
                       else: raise Exception("Failed to fetch after poster update")
                  else:
                      content_logger.warning(f"Admin {user_id} updated poster for {anime_id_str} but modified_count was 0.")
                      await message.reply_text("✅ Poster appears unchanged. No update needed.", parse_mode=config.PARSE_MODE)
                      # Return to managing menu even if no change
                      current_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)})
                      if current_anime_doc:
                           current_anime = Anime(**current_anime_doc)
                           await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": anime_id_str, "anime_name": current_anime.name})
                           await display_anime_management_menu(client, message, current_anime)
                      else: raise Exception("Failed to fetch after no-change poster edit")


              except Exception as e:
                   content_logger.error(f"Error updating poster for anime {anime_id_str} by admin {user_id}: {e}")
                   await message.reply_text("💔 Error updating poster.", parse_mode=config.PARSE_MODE)
                   # State is AWAITING_POSTER with purpose: edit. Needs cancel or retry photo.


          else:
              # Purpose in state data is not "add" or "edit", something is wrong.
               content_logger.warning(f"Admin {user_id} sent poster in AWAITING_POSTER with invalid purpose: {purpose}.")
               await message.reply_text("🤷 Unexpected action. Your process was cancelled.", parse_mode=config.PARSE_MODE)
               await clear_user_state(user_id)


     else:
         # Received non-photo input when expecting a poster (handled in handle_file_input in common_handlers)
         pass


# Similarly handle other edit field callbacks (genres, year, status, seasons count - requires specific logic for each)

# Callbacks for editing Genres/Status reuse the SELECTING_GENRES/STATUS states but check state data for context ({purpose: "edit", anime_id: ...})
# The Done callbacks for genres/status will then proceed differently if purpose is "edit" -
# they will save the selection to the EXISTING anime doc instead of creating a new one,
# and then return to the MANAGEMENT_ANIME_MENU for that anime.

# content_genres_done_callback and content_select_status_callback will need modification:
# Add anime_id to the data dict when entering the SELECTING state for editing
# Check purpose in callback: if "add", proceed as currently implemented (create new anime)
# If "edit", get anime_id from state.data, update genres/status array/field in the DB for that anime,
# fetch updated anime, clear state, display MANAGEMENT_ANIME_MENU.

# --- Seasons and Episode Management (starting from display_anime_management_menu) ---
# Callback: content_manage_seasons|<anime_id>

@Client.on_callback_query(filters.regex("^content_manage_seasons\|.*") & filters.private)
async def content_manage_seasons_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Manage Seasons/Episodes button for an anime."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_manage_seasons|<anime_id>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Loading seasons...")

    user_state = await get_user_state(user_id)
    # We expect state MANAGING_ANIME_MENU when clicking this, or previous states in CM flow.
    # Could also be direct from editing anime after creation.
    # Simplest check: Must be in *any* content management state? Or specifically managing an anime?
    # Let's require being in the managing flow, maybe even MANAGING_ANIME_MENU state
    if not (user_state and user_state.handler == "content_management"):
        await callback_query.message.reply_text("🔄 Invalid state. Please navigate from the main content menu.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id) # Clear incorrect state
        await manage_content_command(client, callback_query.message) # Offer to start fresh
        return

    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        # Update state to confirm managing seasons for this anime
        await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data={"anime_id": anime_id_str, "anime_name": user_state.data.get("anime_name", "Anime")}) # Keep name or fetch

        # Fetch anime details (specifically seasons array)
        anime_doc = await MongoDB.anime_collection().find_one(
             {"_id": ObjectId(anime_id_str)},
             {"seasons": 1, "name": 1} # Project only seasons and name for efficiency
         )
        if not anime_doc:
            content_logger.error(f"Admin {user_id} managing seasons for non-existent anime ID: {anime_id_str}")
            await callback_query.message.edit_text("💔 Error: Anime not found for season management.", parse_mode=config.PARSE_MODE)
            await clear_user_state(user_id); return # Cannot manage seasons if anime gone

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        seasons = anime_doc.get("seasons", [])

        # Sort seasons numerically before displaying
        seasons.sort(key=lambda s: s.get("season_number", 0))


        menu_text = f"📺 __**Manage Seasons for**__ **__{anime_name}__** 🛠️\n\n"
        if not seasons:
             menu_text += "No seasons added yet.\n\n"
        else:
            menu_text += "👇 Select a season to manage episodes or use options below:\n\n"

        buttons = []
        # Add buttons for each existing season
        for season in seasons:
            season_number = season.get("season_number")
            # Callback: content_select_season|<anime_id>|<season_number>
            if season_number is not None:
                 buttons.append([InlineKeyboardButton(f"📺 Season {season_number}", callback_data=f"content_select_season|{anime_id_str}|{season_number}")])

        # Add option to add a new season (need to figure out next sequential number or let admin specify?)
        # Let's auto-suggest the next season number
        next_season_number = (seasons[-1].get("season_number", 0) if seasons else 0) + 1
        buttons.append([InlineKeyboardButton(BUTTON_ADD_NEW_SEASON, callback_data=f"content_add_new_season|{anime_id_str}|{next_season_number}")])
        # Maybe allow admin to specify any number? Simpler flow: always add next in sequence

        # Add Remove Season button (requires admin to select which season to remove)
        # This needs another step/state: content_remove_season_select|<anime_id>
        if seasons:
             # Buttons to remove seasons - can be placed in a separate 'Remove Season' flow
             # Or as an option leading to a list of seasons with remove buttons
             pass # Will implement a separate flow for removing

        # Back buttons
        # content_view_all doesn't exist yet, link to manage_content_command start? Or implement view_all first.
        buttons.append([InlineKeyboardButton(BUTTON_BACK_TO_ANIME_LIST, callback_data="content_view_all_temp")]) # Needs fixing
        buttons.append([InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home")])


        reply_markup = InlineKeyboardMarkup(buttons)

        try:
             await callback_query.message.edit_text(
                  menu_text,
                  reply_markup=reply_markup,
                  parse_mode=config.PARSE_MODE,
                  disable_web_page_preview=True
             )
        except Exception as e:
             content_logger.error(f"Failed to display seasons management menu for anime {anime_id_str} by admin {user_id}: {e}")
             await client.send_message(chat_id, "💔 Error displaying seasons menu.", parse_mode=config.PARSE_MODE)


    except Exception as e:
         content_logger.error(f"Error handling content_manage_seasons callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id)


# Callback: content_add_new_season|<anime_id>|<next_season_number>

@Client.on_callback_query(filters.regex("^content_add_new_season\|.*\|.*") & filters.private)
async def content_add_new_season_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Add New Season button."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_add_new_season|<anime_id>|<season_number_to_add>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer()

    user_state = await get_user_state(user_id)
    # State should be MANAGING_SEASONS_LIST
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_SEASONS_LIST):
         await callback_query.message.reply_text("🔄 Invalid state for adding season.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3:
             raise ValueError("Invalid callback data format for adding season.")
        anime_id_str = parts[1]
        season_to_add = int(parts[2])

        # Check if a season with this number already exists? Best handled before button generation.
        # For simple flow, we append to the array and assume button gives next available.

        # Create the new Season model
        new_season = Season(season_number=season_to_add, episodes=[]) # Start with empty episodes

        # Add the new season to the anime's seasons array in the database
        # Use $push operator to append to the array
        update_result = await MongoDB.anime_collection().update_one(
            {"_id": ObjectId(anime_id_str)},
            {"$push": {"seasons": new_season.dict()}} # Add the season document
            # No $set:{last_updated_at} needed with $push, handles modification date? Check docs.
        )

        if update_result.modified_count > 0:
            content_logger.info(f"Admin {user_id} added Season {season_to_add} to anime {anime_id_str}.")
            await callback_query.message.reply_text(f"✅ Added Season **__{season_to_add}__** to this anime!\n\n🔢 Now send the **__Total Number of Episodes__** for Season **__{season_to_add}__**.", parse_mode=config.PARSE_MODE)

            # Transition to the state where we await the episode count for this new season
            await set_user_state(
                 user_id,
                 "content_management",
                 ContentState.AWAITING_SEASONS_COUNT, # Reusing this state, need to add context for episode count for a specific season
                 data={**user_state.data, "managing_season_number": season_to_add, "purpose": "set_episode_count"}
            )

            # Edit the season management menu message to remove the "Add New Season" option (as we just added it)
            # or better, just send a new message for the input. Keep the menu there for navigation.
            # Let's send a new prompt message.
            prompt_text = ADD_SEASON_EPISODES_PROMPT.format(season_number=season_to_add, anime_name=user_state.data.get("anime_name", "Anime"))
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]]) # Cancel only
            await client.send_message(chat_id, prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)


        else:
            content_logger.warning(f"Admin {user_id} clicked add season {season_to_add} for {anime_id_str} but modified_count was 0.")
            await callback_query.message.reply_text("⚠️ Failed to add the new season. Maybe it already exists?", parse_mode=config.PARSE_MODE)
            # Stay in the seasons list state


    except ValueError:
         await callback_query.message.reply_text("🚫 Invalid season number data in callback.", parse_mode=config.PARSE_MODE)
         # State remains the same, could re-send menu

    except Exception as e:
        content_logger.error(f"Error handling content_add_new_season callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


# Update handle_content_input to handle AWAITING_SEASONS_COUNT input for episode count for a season
async def handle_awaiting_seasons_count_input(client: Client, message: Message, user_state: UserState, count_text: str):
    """Handles admin text input when in the AWAITING_SEASONS_COUNT state."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_name = user_state.data.get("anime_name", "Anime") # Get anime name from state data
    purpose = user_state.data.get("purpose", "initial_total") # Check purpose

    content_logger.info(f"Admin {user_id} provided count input: {count_text} for '{anime_name}' with purpose '{purpose}'.")

    try:
        count_value = int(count_text)
        if count_value < 0:
             raise ValueError("Negative count not allowed")

        if purpose == "initial_total":
            # This is for setting the *total seasons declared* during ADD NEW ANIME flow (Original logic)
            # This should remain in content_select_status_callback handling after prompt_for_release_year
            # Wait, my state diagram is confusing. Let's adjust.

            # Correct State Flow:
            # ADD NEW ANIME: AWAITING_ANIME_NAME -> AWAITING_POSTER -> AWAITING_SYNOPSIS -> AWAITING_SEASONS_COUNT (TOTAL SEASONS INPUT) -> SELECTING_GENRES -> AWAITING_RELEASE_YEAR -> SELECTING_STATUS -> (Save Anime) -> MANAGING_ANIME_MENU

            # ADD EPISODES FOR A SEASON: MANAGING_SEASONS_LIST -> content_add_new_season callback -> AWAITING_EPISODE_COUNT_FOR_SEASON (New State!) -> (Handle Input, Add Episodes to DB Array) -> MANAGING_SEASONS_LIST

            # Let's rename AWAITING_SEASONS_COUNT to clarify and create a new state

            raise NotImplementedError("Redefining state flow.") # Temporarily disable old logic
            # The old logic for handling total seasons count during initial add should now be handled by a state specific to *that* step
            # This state should primarily be for SETTING EPISODE COUNT for a specific season


        elif purpose == "set_episode_count":
             # This input is for setting the episode count for a specific season number
             anime_id_str = user_state.data.get("anime_id")
             season_number = user_state.data.get("managing_season_number")

             if not anime_id_str or season_number is None:
                  content_logger.error(f"Admin {user_id} sent episode count in 'set_episode_count' state but missing anime/season ID. State: {user_state.data}")
                  await message.reply_text("💔 Error: State data missing for episode count input. Process cancelled.", parse_mode=config.PARSE_MODE)
                  await clear_user_state(user_id)
                  return

             content_logger.info(f"Admin {user_id} provided episode count ({count_value}) for {anime_name} Season {season_number}.")

             # Find the specific season array element and add episode documents to it
             # Need to use $set to update a nested array element and potentially create subdocuments.
             # Or use $push for each episode? $push is better for arrays.
             # We need to ensure the season exists before adding episodes.
             # Let's find the anime, then find the season by number.

             try:
                  anime_doc = await MongoDB.anime_collection().find_one(
                       {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}, # Filter for the anime and check season exists
                       {"seasons.$": 1} # Project only the matching season for verification if needed (less useful for updates)
                  )

                  if not anime_doc:
                       content_logger.error(f"Admin {user_id} sent episode count for non-existent anime/season {anime_id_str}/S{season_number}")
                       await message.reply_text("💔 Error: Anime or season not found. Cannot add episodes.", parse_mode=config.PARSEMode)
                       await clear_user_state(user_id); return


                  # Create episode documents (starting from EP01)
                  episode_docs_to_add = []
                  for i in range(1, count_value + 1):
                       episode_docs_to_add.append(Episode(episode_number=i).dict()) # Create Episode Pydantic model then convert to dict


                  # Update the seasons array: Find the correct season element and SET its 'episodes' field
                  # Using $set with positional operator $.
                  update_result = await MongoDB.anime_collection().update_one(
                      {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number},
                      {
                           "$set": {"seasons.$.episode_count_declared": count_value, "seasons.$.episodes": episode_docs_to_add},
                           "$set": {"last_updated_at": datetime.now(timezone.utc)} # Update top-level modified date
                      }
                      # NOTE: $set can overwrite. If admin specifies episode count again,
                      # this will DELETE existing episode entries for this season.
                      # Is this the desired behavior? If not, need $push + manual indexing/checking
                      # based on whether episode exists. Simpler for now is overwrite.
                  )


                  if update_result.modified_count > 0:
                      content_logger.info(f"Admin {user_id} set episode count {count_value} for anime {anime_id_str} Season {season_number}. Created episode placeholders.")
                      await message.reply_text(EPISODES_CREATED_SUCCESS.format(episode_count=count_value, season_number=season_number), parse_mode=config.PARSE_MODE)

                      # After setting episode count, transition back to the seasons list menu for this anime
                      await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data={"anime_id": anime_id_str, "anime_name": user_state.data.get("anime_name", "Anime")})

                      # Redisplay the seasons menu (might need to fetch updated anime doc?)
                      updated_anime_doc = await MongoDB.anime_collection().find_one(
                           {"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1}
                      )
                      if updated_anime_doc:
                          updated_anime_doc["seasons"].sort(key=lambda s: s.get("season_number", 0)) # Sort
                          # Need to re-build the seasons management menu display logic here or call a helper
                          # display_seasons_management_menu(client, message, updated_anime_doc)
                          # For simplicity, let's re-call the original season display handler which will fetch and display:
                          await content_manage_seasons_callback(client, callback_query=type('obj', (object,), {'from_user': type('obj', (object,), {'id': user_id}), 'message': message, 'data': f'content_manage_seasons|{anime_id_str}', 'answer': lambda text='', show_alert=False: asyncio.Future()})()) # Mocking callback query

                      else:
                          content_logger.error(f"Failed to fetch anime {anime_id_str} after setting episode count for admin {user_id}.")
                          await message.reply_text("💔 Set episode count, but failed to reload season menu.", parse_mode=config.PARSE_MODE)


                  else:
                      content_logger.warning(f"Admin {user_id} set episode count {count_value} for anime {anime_id_str} Season {season_number} but modified_count was 0.")
                      await message.reply_text("⚠️ Episode count update modified 0 documents. Season might not exist or same count entered?", parse_mode=config.PARSE_MODE)
                      # Stay in the 'set_episode_count' state, admin might try again
                      # Or reset state? Reset seems safer.
                      await clear_user_state(user_id)


             except Exception as e:
                 content_logger.error(f"Error setting episode count for anime {anime_id_str} Season {season_number} by admin {user_id}: {e}")
                 await message.reply_text("💔 Error saving episode count.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id)


    except ValueError:
        # Input was not a valid non-negative integer
        await message.reply_text("🚫 Please send a valid **__number__** for the total number of episodes, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        # State remains the same


# --- Handlers for Selecting a Season from the Seasons List ---
# Callback: content_select_season|<anime_id>|<season_number>

@Client.on_callback_query(filters.regex("^content_select_season\|.*\|.*") & filters.private)
async def content_select_season_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting a season from the seasons list to manage episodes."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_select_season|<anime_id>|<season_number>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Loading episodes...")

    user_state = await get_user_state(user_id)
    # State should be MANAGING_SEASONS_LIST
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_SEASONS_LIST):
         await callback_query.message.reply_text("🔄 Invalid state for selecting season.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3:
             raise ValueError("Invalid callback data format for selecting season.")
        anime_id_str = parts[1]
        season_number = int(parts[2])

        # Find the anime and the specific season to get its episodes
        anime_doc = await MongoDB.anime_collection().find_one(
             {"_id": ObjectId(anime_id_str)},
             {"name": 1, "seasons": {"$elemMatch": {"season_number": season_number}}} # Project matching season
         )

        if not anime_doc or not anime_doc.get("seasons"): # anime_doc.get("seasons") will be a list with one element if found
             content_logger.error(f"Admin {user_id} selected non-existent anime/season for editing episodes: {anime_id_str}/S{season_number}")
             await callback_query.message.edit_text("💔 Error: Anime or season not found for episode management.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        # Access the episode list from the found season element
        season_data = anime_doc["seasons"][0] # $elemMatch ensures it's a list with the matching element
        episodes = season_data.get("episodes", [])

        # Sort episodes numerically
        episodes.sort(key=lambda e: e.get("episode_number", 0))


        # --- Transition to Managing Episodes List State ---
        await set_user_state(
             user_id,
             "content_management",
             ContentState.MANAGING_EPISODES_LIST,
             data={**user_state.data, "anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_name} # Add season context to state
         )

        # Display episode list for the selected season
        await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_name, season_number, episodes)


    except ValueError:
        await callback_query.message.reply_text("🚫 Invalid season number data in callback.", parse_mode=config.PARSE_MODE)
        # Stay in the seasons list state

    except Exception as e:
         content_logger.error(f"Error handling content_select_season callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id)


async def display_episodes_management_list(client: Client, message: Message, anime_id_str: str, anime_name: str, season_number: int, episodes: List[Dict]):
    """Displays the list of episodes for a season to the admin with management options."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    menu_text = MANAGE_EPISODES_TITLE.format(anime_name=anime_name, season_number=season_number) + "\n\n"

    buttons = []
    if not episodes:
        menu_text += "No episodes added for this season.\n\n"
         # Add an option to manually add an episode number? Or only via setting count?
         # Let's assume adding episode placeholders is done by setting count.

    # Add buttons for each existing episode
    for episode in episodes:
         ep_number = episode.get("episode_number")
         # Button text indicates episode number and presence of files/release date
         ep_label = f"🎬 EP{ep_number:02d}"
         if episode.get("files"): # Check if files array is non-empty
             ep_label += " ✅ Files"
         elif episode.get("release_date"):
             # Format date nicely, ensure it's datetime object
             release_date = episode.get("release_date")
             if isinstance(release_date, datetime):
                 # Adjust formatting string based on your preference (e.g., YYYY-MM-DD, MM/DD)
                  formatted_date = release_date.strftime('%Y-%m-%d')
                  ep_label += f" ⏳ {formatted_date}"
             else: # Should be datetime from Pydantic model/DB read, but fallback
                   ep_label += " ⏳ (Date)"
         else:
              ep_label += " ❓ No Files/Date" # Based on string format

         # Callback: content_manage_episode|<anime_id>|<season_number>|<episode_number>
         if ep_number is not None:
             buttons.append([InlineKeyboardButton(ep_label, callback_data=f"content_manage_episode|{anime_id_str}|{season_number}|{ep_number}")])

    # Back button to seasons list
    buttons.append([InlineKeyboardButton(BUTTON_BACK, callback_data=f"content_manage_seasons|{anime_id_str}")]) # Go back to seasons list

    # Back button to main content menu
    buttons.append([InlineKeyboardButton(BUTTON_HOME, callback_data="content_management_main_menu")]) # Back to start of CM?

    reply_markup = InlineKeyboardMarkup(buttons)

    try:
         await message.edit_text(
              menu_text,
              reply_markup=reply_markup,
              parse_mode=config.PARSE_MODE,
              disable_web_page_preview=True
         )
    except Exception as e:
         content_logger.error(f"Failed to display episodes management list for anime {anime_id_str} S{season_number} by admin {user_id}: {e}")
         await client.send_message(chat_id, "💔 Error displaying episodes list.", parse_mode=config.PARSE_MODE)


# --- Handlers for Selecting an Episode from the Episodes List ---
# Callback: content_manage_episode|<anime_id>|<season_number>|<episode_number>

@Client.on_callback_query(filters.regex("^content_manage_episode\|.*\|.*\|.*") & filters.private)
async def content_manage_episode_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting a specific episode to manage files/release date."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_manage_episode|<anime_id>|<season_number>|<episode_number>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Loading episode details...")

    user_state = await get_user_state(user_id)
    # State should be MANAGING_EPISODES_LIST
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODES_LIST):
         await callback_query.message.reply_text("🔄 Invalid state for selecting episode.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4:
             raise ValueError("Invalid callback data format for managing episode.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        # Find the specific anime, season, and episode to get its details (especially files/release date)
        # Use $filter with $elemMatch for nested array elements (complex query)
        # Easier to find the anime, then iterate seasons to find season, then iterate episodes to find episode
        # Or, update seasons to contain episode_ids? Or make episodes a top-level collection with parent refs?
        # Let's stick with nested for now and use projection/elemMatch for efficiency where possible.
        # Finding just the specific episode object might be best.

        anime_doc = await MongoDB.anime_collection().find_one(
             {"_id": ObjectId(anime_id_str)},
             {"name": 1, "seasons": {"$elemMatch": {"season_number": season_number}}}
        )

        if not anime_doc or not anime_doc.get("seasons"):
             content_logger.error(f"Admin {user_id} selected non-existent anime/season for episode management: {anime_id_str}/S{season_number}")
             await callback_query.message.edit_text("💔 Error: Anime or season not found for episode management.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        season_data = anime_doc["seasons"][0]
        episodes = season_data.get("episodes", [])

        # Find the specific episode in the episodes list
        current_episode = next((ep for ep in episodes if ep.get("episode_number") == episode_number), None)

        if not current_episode:
             content_logger.error(f"Admin {user_id} selected non-existent episode for management: {anime_id_str}/S{season_number}E{episode_number}")
             await callback_query.message.edit_text("💔 Error: Episode not found for management.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return

        # --- Transition to Managing Episode Menu State ---
        # Store anime, season, episode context in state
        await set_user_state(
             user_id,
             "content_management",
             ContentState.MANAGING_EPISODE_MENU,
             data={
                 "anime_id": anime_id_str,
                 "season_number": season_number,
                 "episode_number": episode_number,
                 "anime_name": anime_name,
                 # Optional: Store file versions and release date in state data? No, re-fetch from DB.
             }
         )

        # Display episode management options
        await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, current_episode)


    except ValueError:
        await callback_query.message.reply_text("🚫 Invalid episode number data in callback.", parse_mode=config.PARSE_MODE)
        # Stay in episodes list state? Or re-display list? Re-display.
        # This requires fetching anime and seasons again.

    except Exception as e:
         content_logger.error(f"Error handling content_manage_episode callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id)


async def display_episode_management_menu(client: Client, message: Message, anime_name: str, season_number: int, episode_number: int, episode_data: Dict):
     """Displays options for managing a specific episode (files, release date, delete)."""
     user_id = message.from_user.id # Needed for logging
     chat_id = message.chat.id

     menu_text = ""
     buttons = []
     files = episode_data.get("files", [])
     release_date = episode_data.get("release_date")

     if files:
         menu_text = f"🛠️ __**Manage Versions for**__ **__{anime_name}__** - S{season_number}E{episode_number:02d} 🛠️\n\n"
         menu_text += f"📥 __**Available Versions**__:\n"
         # List existing file versions
         for i, file_ver in enumerate(files):
              menu_text += f"  {i+1}. {file_ver.get('quality_resolution', 'Unknown')} ({file_ver.get('file_size_bytes', 0) / (1024*1024):.2f} MB) {', '.join(file_ver.get('audio_languages', []))} / {', '.join(file_ver.get('subtitle_languages', []))}\n"

         # Add button to add another version, go to next episode, delete versions
         buttons = [
             # content_add_file_version|<anime_id>|<season>|<ep> - needs anime/season/ep id in state
             [InlineKeyboardButton(BUTTON_ADD_OTHER_VERSION.format(episode_number=episode_number), callback_data=f"content_add_file_version|{user_state.data.get('anime_id')}|{season_number}|{episode_number}")],
             # Need to determine the next episode number programmatically for the NEXT button
             # Requires checking the episodes array structure for this season in DB
             [InlineKeyboardButton(BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode|{user_state.data.get('anime_id')}|{season_number}|{episode_number + 1}")], # Assuming sequential episodes
              # Callback for deleting files (will need a sub-menu to select file to delete)
             [InlineKeyboardButton("🗑️ Delete File Version(s)", callback_data=f"content_delete_file_version_menu|{user_state.data.get('anime_id')}|{season_number}|{episode_number}")],
         ]
     elif isinstance(release_date, datetime): # Has a release date but no files
          formatted_date = release_date.strftime('%Y-%m-%d')
          menu_text = f"🛠️ __**Manage**__ **__{anime_name}__** - S{season_number}E{episode_number:02d} 🛠️\n\n"
          menu_text += EPISODE_OPTIONS_WITH_RELEASE_DATE.format(release_date=formatted_date) + "\n\n"
          # Options: Add file (removes release date), go to next episode, remove episode
          buttons = [
             [InlineKeyboardButton(BUTTON_ADD_EPISODE_FILE, callback_data=f"content_add_file_version|{user_state.data.get('anime_id')}|{season_number}|{episode_number}")],
             [InlineKeyboardButton(BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode|{user_state.data.get('anime_id')}|{season_number}|{episode_number + 1}")],
             [InlineKeyboardButton(BUTTON_REMOVE_EPISODE.format(episode_number=episode_number), callback_data=f"content_remove_episode|{user_state.data.get('anime_id')}|{season_number}|{episode_number}")],
          ]
     else: # No files and no release date
         menu_text = f"🛠️ __**Manage**__ **__{anime_name}__** - S{season_number}E{episode_number:02d} 🛠️\n\n"
         menu_text += "❓ No files or release date set yet for this episode.\n\n" # Reuses general string structure
         # Options: Add file, Add release date, go to next episode, remove episode
         buttons = [
             [InlineKeyboardButton(BUTTON_ADD_EPISODE_FILE, callback_data=f"content_add_file_version|{user_state.data.get('anime_id')}|{season_number}|{episode_number}")],
             [InlineKeyboardButton(BUTTON_ADD_RELEASE_DATE, callback_data=f"content_add_release_date|{user_state.data.get('anime_id')}|{season_number}|{episode_number}")],
             [InlineKeyboardButton(BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode|{user_state.data.get('anime_id')}|{season_number}|{episode_number + 1}")],
             [InlineKeyboardButton(BUTTON_REMOVE_EPISODE.format(episode_number=episode_number), callback_data=f"content_remove_episode|{user_state.data.get('anime_id')}|{season_number}|{episode_number}")],
         ]

     # Add back button to episode list and home button
     buttons.append([InlineKeyboardButton(BUTTON_BACK, callback_data=f"content_select_season|{user_state.data.get('anime_id')}|{season_number}")]) # Back to episodes list
     buttons.append([InlineKeyboardButton(BUTTON_HOME, callback_data="content_management_main_menu")]) # Back to start of CM?


     reply_markup = InlineKeyboardMarkup(buttons)

     try:
         await message.edit_text(
             menu_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True
         )
     except Exception as e:
         content_logger.error(f"Failed to display episode management menu for {anime_name} S{season_number}E{episode_number} by admin {user_id}: {e}")
         await client.send_message(chat_id, "💔 Error displaying episode management menu.", parse_mode=config.PARSE_MODE)
