# handlers/content_handler.py

import logging
import asyncio # Needed for FloodWait and delays
from typing import Union, List, Dict, Any, Tuple # Added Tuple for return types
from datetime import datetime, timezone # Import timezone aware datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    Document, Video, Photo # Import specific media types
)
from pyrogram.errors import FloodWait, MessageNotModified

# Import config and strings - Ensure all necessary strings/configs are imported
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

# Import database models and utilities
from database.mongo_db import MongoDB, get_user_state, set_user_state, clear_user_state
from database.models import UserState, Anime, Season, Episode, FileVersion, PyObjectId

# Import necessary helpers from common_handlers
from handlers.common_handlers import get_user # For potential user checks
from database.mongo_db import model_to_mongo_dict # To easily convert Pydantic to dict
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

@Client.on_callback_query(filters.regex("^content_add_new_season\|.*\|.*") & filters.private)
async def content_add_new_season_callback(client: Client, callback_query: CallbackQuery):
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
        if len(parts) != 3: raise ValueError("Invalid callback data format for adding season.")
        anime_id_str = parts[1]
        season_to_add = int(parts[2])

        # Add the season to the database
        new_season_dict = Season(season_number=season_to_add).dict() # Create season dict

        update_result = await MongoDB.anime_collection().update_one(
            {"_id": ObjectId(anime_id_str)},
            {"$push": {"seasons": new_season_dict}}
        )

        if update_result.modified_count > 0:
            content_logger.info(f"Admin {user_id} added Season {season_to_add} to anime {anime_id_str}.")
            # Edit the season list message to show the new season
            await callback_query.message.edit_text(f"✅ Added Season **__{season_to_add}__** to this anime!", parse_mode=config.PARSE_MODE)

            # Transition to the state where we await the episode count for this new season
            # NEW STATE: AWAITING_EPISODE_COUNT_FOR_SEASON
            await set_user_state(
                 user_id,
                 "content_management",
                 ContentState.AWAITING_SEASONS_COUNT, # Still using AWAITING_SEASONS_COUNT, but clarified its *purpose* in the input handler logic
                 data={**user_state.data, "managing_season_number": season_to_add, "purpose": "set_episode_count"}
            )

            # Send the prompt for episode count input
            anime_name = user_state.data.get("anime_name", "Anime") # Get name from state
            prompt_text = ADD_SEASON_EPISODES_PROMPT.format(season_number=season_to_add, anime_name=anime_name)
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]])
            await client.send_message(chat_id, prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)

        else:
            content_logger.warning(f"Admin {user_id} clicked add season {season_to_add} for {anime_id_str} but modified_count was 0.")
            await callback_query.message.reply_text("⚠️ Failed to add the new season. Maybe it already exists?", parse_mode=config.PARSE_MODE)
            # Stay in the seasons list state


    except ValueError: await callback_query.message.reply_text("🚫 Invalid season number data.", parse_mode=config.PARSE_MODE)
    except Exception as e: content_logger.error(f"Error handling content_add_new_season callback {user_id}: {e}"); await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)

# Updated handle_awaiting_seasons_count_input - focuses only on 'set_episode_count' purpose now
async def handle_awaiting_seasons_count_input(client: Client, message: Message, user_state: UserState, count_text: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    # Anime name should be in state data now
    anime_name = user_state.data.get("anime_name", "Anime")
    purpose = user_state.data.get("purpose") # MUST have a purpose here

    if purpose == "set_episode_count":
         # This input is for setting the episode count for a specific season number
         anime_id_str = user_state.data.get("anime_id")
         season_number = user_state.data.get("managing_season_number")

         if not anime_id_str or season_number is None:
              content_logger.error(f"Admin {user_id} sent episode count but missing anime/season ID in state data. State: {user_state.data}")
              await message.reply_text("💔 Error: State data missing for episode count. Process cancelled.", parse_mode=config.PARSE_MODE)
              await clear_user_state(user_id); return

         content_logger.info(f"Admin {user_id} provided episode count input for {anime_name} Season {season_number}.")

         try:
             count_value = int(count_text)
             if count_value < 0: raise ValueError("Negative count not allowed")

             # Create episode documents (starting from EP01)
             episode_docs_to_add = []
             for i in range(1, count_value + 1):
                 episode_docs_to_add.append(Episode(episode_number=i).dict()) # Create Pydantic then dict


             # Update the seasons array: Find the correct season element and SET its 'episodes' field and declared count
             update_result = await MongoDB.anime_collection().update_one(
                 {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number},
                 {
                     "$set": {
                         "seasons.$.episode_count_declared": count_value,
                         "seasons.$.episodes": episode_docs_to_add,
                         "last_updated_at": datetime.now(timezone.utc) # Update top-level modified date
                         }
                 }
             )

             if update_result.modified_count > 0:
                 content_logger.info(f"Admin {user_id} set episode count {count_value} for anime {anime_id_str} Season {season_number}.")
                 await message.reply_text(EPISODES_CREATED_SUCCESS.format(episode_count=count_value, season_number=season_number), parse_mode=config.PARSE_MODE)

                 # After setting episode count, transition back to the seasons list menu for this anime
                 # Preserve anime_id and anime_name in state data, remove managing_season_number and purpose
                 updated_state_data = {k: v for k, v in user_state.data.items() if k not in ["managing_season_number", "purpose"]}
                 await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data=updated_state_data)

                 # Redisplay the seasons menu
                 # Re-fetch anime and seasons to ensure menu is updated
                 updated_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})
                 if updated_anime_doc:
                      # Mocking callback query is tricky. Easier to implement display_seasons_management_menu directly
                      await display_seasons_management_menu(client, message, updated_anime_doc) # New helper needed
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} after setting episode count for admin {user_id}.")
                      await message.reply_text("💔 Set episode count, but failed to reload season menu.", parse_mode=config.PARSE_MODE)


             else:
                 content_logger.warning(f"Admin {user_id} set episode count {count_value} for {anime_id_str} S{season_number} but modified_count was 0. Same count entered?")
                 await message.reply_text("⚠️ Episode count update modified 0 documents. Same count entered? No changes made.", parse_mode=config.PARSE_MODE)
                 # State is still AWAITING_SEASONS_COUNT with purpose, user can send count again or cancel


         except ValueError:
             await message.reply_text("🚫 Please send a valid **__number__** for the total number of episodes, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
             # State remains the same


    else:
        # This state (AWAITING_SEASONS_COUNT) received text without 'set_episode_count' purpose
        # This should only be for the initial ADD NEW flow, which we are removing from here.
        # Log this as an unexpected input if this handler is reached in a context other than setting episode count.
        content_logger.warning(f"Admin {user_id} sent text input to AWAITING_SEASONS_COUNT state with unexpected purpose: {purpose}.")
        await message.reply_text("🤔 Unexpected input for this step. Please provide the episode count.", parse_mode=config.PARSE_MODE)
        # State remains the same

# --- Helper to display the updated Seasons Management List ---
async def display_seasons_management_menu(client: Client, message: Message, anime_doc_with_seasons: Dict):
     """Displays the list of seasons for an anime, expects a document with 'seasons' and 'name' projected."""
     user_id = message.from_user.id
     chat_id = message.chat.id

     anime_id_str = str(anime_doc_with_seasons["_id"]) # Assume _id is in the doc
     anime_name = anime_doc_with_seasons.get("name", "Anime Name Unknown")
     seasons = anime_doc_with_seasons.get("seasons", [])
     seasons.sort(key=lambda s: s.get("season_number", 0)) # Ensure sorting


     menu_text = f"📺 __**Manage Seasons for**__ **__{anime_name}__** 🛠️\n\n"
     if not seasons:
          menu_text += "No seasons added yet.\n\n"
     else:
         menu_text += "👇 Select a season to manage episodes or use options below:\n\n"

     buttons = []
     for season in seasons:
         season_number = season.get("season_number")
         ep_count = season.get("episode_count_declared", 0)
         button_label = f"📺 Season {season_number}"
         if ep_count > 0:
              button_label += f" ({ep_count} Episodes)" # Show declared count if > 0

         if season_number is not None:
             buttons.append([InlineKeyboardButton(button_label, callback_data=f"content_select_season|{anime_id_str}|{season_number}")])

     # Add options: Add New Season, Remove Season
     next_season_number = (seasons[-1].get("season_number", 0) if seasons else 0) + 1
     buttons.append([InlineKeyboardButton(BUTTON_ADD_NEW_SEASON, callback_data=f"content_add_new_season|{anime_id_str}|{next_season_number}")])
     if seasons: # Only show remove option if there are seasons
          buttons.append([InlineKeyboardButton("🗑️ Remove a Season", callback_data=f"content_remove_season_select|{anime_id_str}")])


     # Back buttons
     buttons.append([InlineKeyboardButton(BUTTON_BACK_TO_ANIME_LIST, callback_data=f"content_edit_existing|{anime_id_str}")]) # Go back to editing THIS anime
     buttons.append([InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home")])


     reply_markup = InlineKeyboardMarkup(buttons)

     try:
         # We are typically called from a place that requires editing a message (e.g. after adding season)
         # But could also be called when returning from episode list
         await message.edit_text(
              menu_text,
              reply_markup=reply_markup,
              parse_mode=config.PARSE_MODE,
              disable_web_page_preview=True
         )
     except Exception as e:
          content_logger.error(f"Failed to display seasons management menu (helper) for anime {anime_id_str} by admin {user_id}: {e}")
          await client.send_message(chat_id, "💔 Error displaying seasons menu.", parse_mode=config.PARSE_MODE)

@Client.on_callback_query(filters.regex("^content_manage_seasons\|.*") & filters.private)
async def content_manage_seasons_callback(client: Client, callback_query: CallbackQuery):
    # ... (Admin check, state check, answer callback) ...
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_manage_seasons|<anime_id>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Loading seasons...")

    user_state = await get_user_state(user_id)
    # Should be in some content management state when here
    if not (user_state and user_state.handler == "content_management"): # Relax state check slightly
        await callback_query.message.reply_text("🔄 Invalid state. Please navigate from the main content menu.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return
    # Update state to specifically MANAGING_SEASONS_LIST now that we are definitely showing it
    await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data={**user_state.data, "anime_id": data.split(config.CALLBACK_DATA_SEPARATOR)[1]}) # Ensure anime_id in state


    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]

        # Fetch anime details (seasons array)
        anime_doc = await MongoDB.anime_collection().find_one(
             {"_id": ObjectId(anime_id_str)},
             {"seasons": 1, "name": 1}
         )
        if not anime_doc:
            content_logger.error(f"Admin {user_id} managing seasons for non-existent anime ID: {anime_id_str}")
            await callback_query.message.edit_text("💔 Error: Anime not found for season management.", parse_mode=config.PARSE_MODE)
            await clear_user_state(user_id); return

        # Display the seasons menu using the helper function
        await display_seasons_management_menu(client, callback_query.message, anime_doc)

    except Exception as e:
         content_logger.error(f"Error handling content_manage_seasons callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id)


# --- Implement Remove Season Workflow (Needs a sub-menu/state) ---
# Callback: content_remove_season_select|<anime_id>

@Client.on_callback_query(filters.regex("^content_remove_season_select\|.*") & filters.private)
async def content_remove_season_select_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking to remove a season, displays seasons to select."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_remove_season_select|<anime_id>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Select season to remove...")

    user_state = await get_user_state(user_id)
    # State should be MANAGING_SEASONS_LIST
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_SEASONS_LIST):
         await callback_query.message.reply_text("🔄 Invalid state for removing season.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return

    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]

        # Fetch anime seasons
        anime_doc = await MongoDB.anime_collection().find_one(
             {"_id": ObjectId(anime_id_str)},
             {"seasons": 1, "name": 1}
         )
        if not anime_doc:
            content_logger.error(f"Admin {user_id} removing season for non-existent anime ID: {anime_id_str}")
            await callback_query.message.edit_text("💔 Error: Anime not found for season removal.", parse_mode=config.PARSE_MODE)
            await clear_user_state(user_id); return

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        seasons = anime_doc.get("seasons", [])
        seasons.sort(key=lambda s: s.get("season_number", 0))

        if not seasons:
            await callback_query.message.edit_text("🤔 No seasons to remove.", parse_mode=config.PARSE_MODE)
            # Stay in MANAGING_SEASONS_LIST, keep displaying the current seasons menu (which has no remove button now)
            return

        # --- Transition to Selecting Season to Remove State ---
        # Not strictly a new state needed if the response uses callbacks, but clarifies intent.
        # Let's set state to MANAGING_SEASONS_LIST but change message.

        menu_text = f"🗑️ __**Remove Season from**__ **__{anime_name}__** 🗑️\n\n👇 Select the season you want to **__permanently remove__**: (This will delete all episodes/files in that season!)\n\n"

        buttons = []
        for season in seasons:
             season_number = season.get("season_number")
             if season_number is not None:
                 # Callback: content_confirm_remove_season|<anime_id>|<season_number>
                 buttons.append([InlineKeyboardButton(f"❌ Remove Season {season_number}", callback_data=f"content_confirm_remove_season|{anime_id_str}|{season_number}")])

        # Add Back button to season list
        buttons.append([InlineKeyboardButton(BUTTON_BACK, callback_data=f"content_manage_seasons|{anime_id_str}")])
        buttons.append([InlineKeyboardButton(BUTTON_HOME, callback_data="content_management_main_menu")])
        reply_markup = InlineKeyboardMarkup(buttons)

        await callback_query.message.edit_text(
             menu_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
        )


    except Exception as e:
         content_logger.error(f"Error handling content_remove_season_select callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id)


# Callback: content_confirm_remove_season|<anime_id>|<season_number>

@Client.on_callback_query(filters.regex("^content_confirm_remove_season\|.*\|.*") & filters.private)
async def content_confirm_remove_season_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin confirming removing a season."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_confirm_remove_season|<anime_id>|<season_number>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Removing season...")

    user_state = await get_user_state(user_id)
    # State should be MANAGING_SEASONS_LIST (implicitly via the selection menu)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_SEASONS_LIST):
         await callback_query.message.reply_text("🔄 Invalid state for confirming season removal.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3:
             raise ValueError("Invalid callback data format for removing season.")
        anime_id_str = parts[1]
        season_number_to_remove = int(parts[2])

        # Use $pull operator to remove an element from the seasons array based on its number
        update_result = await MongoDB.anime_collection().update_one(
            {"_id": ObjectId(anime_id_str)},
            {"$pull": {"seasons": {"season_number": season_number_to_remove}}}
            # Update last_updated_at? Or use write concern to ensure sync?
        )

        if update_result.modified_count > 0:
            content_logger.info(f"Admin {user_id} removed Season {season_number_to_remove} from anime {anime_id_str}.")
            await callback_query.message.edit_text(f"✅ Permanently removed Season **__{season_number_to_remove}__** from this anime.", parse_mode=config.PARSE_MODE)

            # Return to the updated seasons list menu
            # Re-fetch anime seasons
            updated_anime_doc = await MongoDB.anime_collection().find_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"seasons": 1, "name": 1}
             )
            if updated_anime_doc:
                 await display_seasons_management_menu(client, callback_query.message, updated_anime_doc)
            else:
                 content_logger.error(f"Failed to fetch anime {anime_id_str} after season removal for admin {user_id}. Cannot display menu.")
                 await callback_query.message.reply_text("💔 Removed season, but failed to reload season menu.", parse_mode=config.PARSE_MODE)

        else:
             content_logger.warning(f"Admin {user_id} clicked remove season {season_number_to_remove} for {anime_id_str} but modified_count was 0. Already removed?")
             await callback_query.message.edit_text(f"⚠️ Season **__{season_number_to_remove}__** was not found or already removed.", parse_mode=config.PARSE_MODE)
             # Stay in the seasons removal selection state or go back? Let's go back to the season list menu.
             updated_anime_doc = await MongoDB.anime_collection().find_one(
                  {"_id": ObjectId(anime_id_str)},
                  {"seasons": 1, "name": 1}
              )
             if updated_anime_doc:
                  await display_seasons_management_menu(client, callback_query.message, updated_anime_doc)
             else:
                   content_logger.error(f"Failed to fetch anime {anime_id_str} after failed season removal attempt for admin {user_id}.")
                   await callback_query.message.reply_text("💔 Season not found. Failed to reload season menu.", parse_mode=config.PARSE_MODE)


    except ValueError:
        await callback_query.message.reply_text("🚫 Invalid season number data in callback.", parse_mode=config.PARSE_MODE)
        # Stay in selection state? No, refresh list.
        # Need to refetch anime and display season removal selection menu again

    except Exception as e:
        content_logger.error(f"Error handling content_confirm_remove_season callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)

@Client.on_callback_query(filters.regex("^content_remove_episode\|.*\|.*\|.*") & filters.private)
async def content_remove_episode_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin confirming removing an episode."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_remove_episode|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Removing episode...")

    user_state = await get_user_state(user_id)
    # State should be MANAGING_EPISODE_MENU (the options menu for the episode)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODE_MENU):
         await callback_query.message.reply_text("🔄 Invalid state for removing episode.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for removing episode.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        # Use $pull operator within $set to remove an element from the nested episodes array
        # Requires matching both the anime and the specific season in the filter
        update_result = await MongoDB.anime_collection().update_one(
             {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number},
             {"$pull": {"seasons.$.episodes": {"episode_number": episode_number}}}
        )

        if update_result.modified_count > 0:
            content_logger.info(f"Admin {user_id} removed episode {episode_number} from anime {anime_id_str} S{season_number}.")
            await callback_query.message.edit_text(f"✅ Permanently removed Episode **__{episode_number:02d}__**.", parse_mode=config.PARSE_MODE)

            # Return to the updated episodes list menu for this season
            # Need to re-fetch episodes for the season and re-display.
            anime_doc = await MongoDB.anime_collection().find_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"name": 1, "seasons": {"$elemMatch": {"season_number": season_number}}}
             )
            if anime_doc and anime_doc.get("seasons"):
                 anime_name = anime_doc.get("name", "Anime Name Unknown")
                 season_data = anime_doc["seasons"][0]
                 episodes = season_data.get("episodes", [])
                 episodes.sort(key=lambda e: e.get("episode_number", 0)) # Sort
                 # Clear the MANAGING_EPISODE_MENU state
                 # Keep anime_id, season_number, anime_name in state, set step to MANAGING_EPISODES_LIST
                 await set_user_state(
                      user_id,
                      "content_management",
                      ContentState.MANAGING_EPISODES_LIST,
                      data={k: v for k,v in user_state.data.items() if k not in ["episode_number", "temp_upload", "temp_metadata", "selected_audio_languages", "selected_subtitle_languages"]}
                  )

                 await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_name, season_number, episodes)
            else:
                content_logger.error(f"Failed to fetch anime/season after episode removal for admin {user_id}: {anime_id_str}/S{season_number}.")
                await callback_query.message.reply_text("💔 Removed episode, but failed to reload episodes list.", parse_mode=config.PARSE_MODE)


        else:
            content_logger.warning(f"Admin {user_id} clicked remove episode {episode_number} for {anime_id_str} S{season_number} but modified_count was 0. Already removed?")
            await callback_query.message.edit_text(f"⚠️ Episode **__{episode_number:02d}__** was not found or already removed.", parse_mode=config.PARSE_MODE)
            # Re-display the current episode management menu as no change was made. Needs refetch.
            anime_doc = await MongoDB.anime_collection().find_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"name": 1, "seasons": {"$elemMatch": {"season_number": season_number}}}
            )
            if anime_doc and anime_doc.get("seasons"):
                anime_name = anime_doc.get("name", "Anime Name Unknown")
                season_data = anime_doc["seasons"][0]
                episodes = season_data.get("episodes", [])
                current_episode = next((ep for ep in episodes if ep.get("episode_number") == episode_number), None)
                if current_episode:
                    # State should still be MANAGING_EPISODE_MENU, need to set it here if error handling altered it
                    # Assuming state wasn't cleared, just need to re-display.
                    await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, current_episode)
                else: # Episode *was* somehow removed between clicks
                     content_logger.warning(f"Admin {user_id} failed removing ep {episode_number} because it's now gone.")
                     # Need to reload episodes list view. Mock callback or call display function.
                     anime_doc_seasons_only = await MongoDB.anime_collection().find_one( # Fetch only seasons and name
                          {"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1}
                      )
                     if anime_doc_seasons_only:
                         seasons_list_data = anime_doc_seasons_only.get("seasons", [])
                         seasons_list_data.sort(key=lambda s: s.get("season_number", 0)) # Sort
                         # Set state back to episodes list management for this season
                         await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODES_LIST, data={"anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_doc_seasons_only.get("name", "Anime Name Unknown")})

                         # Re-fetch episode list specifically for this season to pass to display
                         anime_doc_episodes_only = await MongoDB.anime_collection().find_one(
                              {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number},
                              {"seasons.$": 1}
                         )
                         if anime_doc_episodes_only and anime_doc_episodes_only.get("seasons"):
                             episodes = anime_doc_episodes_only["seasons"][0].get("episodes", [])
                             episodes.sort(key=lambda e: e.get("episode_number", 0)) # Sort
                             await display_episodes_management_list(client, callback_query.message, anime_doc_seasons_only.get("name", "Anime Name Unknown"), season_number, episodes)
                         else:
                             content_logger.error(f"Admin {user_id} failed fetching episode list after failed ep remove.")
                             await callback_query.message.reply_text("💔 Failed to reload episodes list.", parse_mode=config.PARSE_MODE)

                     else: # Cannot even fetch the anime anymore
                           content_logger.error(f"Admin {user_id} failed fetching anime after failed ep remove attempt: {anime_id_str}")
                           await callback_query.message.reply_text("💔 Anime not found.", parse_mode=config.PARSE_MODE)
                           await clear_user_state(user_id)


    except ValueError:
        await callback_query.message.reply_text("🚫 Invalid episode number data in callback.", parse_mode=config.PARSE_MODE)
        # Stay in episode menu state

    except Exception as e:
         content_logger.error(f"Error handling content_remove_episode callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         # Stay in episode menu state? Or clear state? Clear might be safer.
         await clear_user_state(user_id)


# Callback: content_go_next_episode|<anime_id>|<season_number>|<next_episode_number>
# Logic: Find the next episode number, load its management menu (or redirect if it doesn't exist)
@Client.on_callback_query(filters.regex("^content_go_next_episode\|.*\|.*\|.*") & filters.private)
async def content_go_next_episode_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking 'Next Episode' button."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_go_next_episode|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Going to next episode...")

    user_state = await get_user_state(user_id)
    # State should be MANAGING_EPISODE_MENU or UPLOADING_FILE/SELECTING_METADATA after adding a version
    # Simplest: If in a CM state, allow navigation, but ensure state is updated correctly.
    if not (user_state and user_state.handler == "content_management"):
         await callback_query.message.reply_text("🔄 Invalid state for going to next episode.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for next episode.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        next_episode_number = int(parts[3]) # This is the TARGET episode number

        # Find the anime, season, and the target episode
        anime_doc = await MongoDB.anime_collection().find_one(
             {"_id": ObjectId(anime_id_str)},
             {"name": 1, "seasons": {"$elemMatch": {"season_number": season_number}}}
        )

        if not anime_doc or not anime_doc.get("seasons"):
             content_logger.error(f"Admin {user_id} going to next ep, but anime/season not found: {anime_id_str}/S{season_number}")
             await callback_query.message.edit_text("💔 Error: Anime or season not found.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        season_data = anime_doc["seasons"][0]
        episodes = season_data.get("episodes", [])

        # Find the specific target episode
        target_episode = next((ep for ep in episodes if ep.get("episode_number") == next_episode_number), None)

        if target_episode:
             content_logger.info(f"Admin {user_id} going to next episode: {anime_name} S{season_number}E{next_episode_number}")

             # --- Transition to Managing Episode Menu State for the Next Episode ---
             await set_user_state(
                  user_id,
                  "content_management",
                  ContentState.MANAGING_EPISODE_MENU, # Set to managing the *next* episode
                  data={
                      "anime_id": anime_id_str,
                      "season_number": season_number,
                      "episode_number": next_episode_number,
                      "anime_name": anime_name,
                      # Remove temp file data if any from previous step
                      "temp_upload": None,
                      "temp_metadata": None,
                      "selected_audio_languages": None,
                      "selected_subtitle_languages": None
                  }
              )

             # Display management options for the next episode
             await display_episode_management_menu(client, callback_query.message, anime_name, season_number, next_episode_number, target_episode)

        else:
             # Target episode number does not exist (e.g., it's the last episode + 1)
             content_logger.info(f"Admin {user_id} attempted to go to next episode E{next_episode_number} which does not exist for {anime_name} S{season_number}.")
             await callback_query.message.edit_text(f"🎬 You've reached the end of Season **__{season_number}__**'s episodes.", parse_mode=config.PARSE_MODE)
             # After reaching the end, route back to the episodes list for this season
             # Needs to fetch the episodes list to pass to the display function.
             anime_doc_episodes_only = await MongoDB.anime_collection().find_one(
                   {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number},
                   {"seasons.$": 1, "name": 1}
             )
             if anime_doc_episodes_only and anime_doc_episodes_only.get("seasons"):
                  episodes_list = anime_doc_episodes_only["seasons"][0].get("episodes", [])
                  episodes_list.sort(key=lambda e: e.get("episode_number", 0)) # Sort
                  # Set state back to episodes list management for this season
                  await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODES_LIST, data={"anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_doc_episodes_only.get("name", "Anime Name Unknown")})

                  await display_episodes_management_list(client, callback_query.message, anime_doc_episodes_only.get("name", "Anime Name Unknown"), season_number, episodes_list)
             else:
                  content_logger.error(f"Admin {user_id} failed fetching episode list after going past last ep.")
                  await callback_query.message.reply_text("💔 Failed to reload episodes list.", parse_mode=config.PARSE_MODE)



    except ValueError:
        await callback_query.message.reply_text("🚫 Invalid episode number data in callback.", parse_mode=config.PARSE_MODE)
        # Stay in episode menu state

    except Exception as e:
         content_logger.error(f"Error handling content_go_next_episode callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         # Stay in episode menu state? Clear state? Clear seems safer if complex error.
         await clear_user_state(user_id)

# Callback: content_add_release_date|<anime_id>|<season_number>|<episode_number>
@Client.on_callback_query(filters.regex("^content_add_release_date\|.*\|.*\|.*") & filters.private)
async def content_add_release_date_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Add Release Date for an episode."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_add_release_date|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer()

    user_state = await get_user_state(user_id)
    # State should be MANAGING_EPISODE_MENU
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODE_MENU):
         await callback_query.message.reply_text("🔄 Invalid state for adding release date.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for release date.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        anime_name = user_state.data.get("anime_name", "Anime") # Get name from state
        # Check state data matches callback data as a safety
        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for add release date: {user_state.data} vs callback {data}")
             # Update state data to match callback for robustness? Or treat as error? Let's update state data.
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number})
             await set_user_state(user_id, "content_management", user_state.step, data=user_state.data)


        # Transition to the state waiting for the release date input
        await set_user_state(user_id, "content_management", ContentState.AWAITING_RELEASE_DATE_INPUT, data=user_state.data) # Keep episode context

        # Prompt admin for release date
        prompt_text = PROMPT_RELEASE_DATE.format(episode_number=episode_number, anime_name=anime_name)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]])

        await callback_query.message.edit_text(
            prompt_text,
            reply_markup=reply_markup,
            parse_mode=config.PARSE_MODE
        )

    except Exception as e:
        content_logger.error(f"Error handling content_add_release_date callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)


# Handle text input when in AWAITING_RELEASE_DATE_INPUT state
async def handle_awaiting_release_date_input(client: Client, message: Message, user_state: UserState, date_text: str):
    """Handles admin text input when in the AWAITING_RELEASE_DATE_INPUT state (expects date string)."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_id_str = user_state.data.get("anime_id")
    season_number = user_state.data.get("season_number")
    episode_number = user_state.data.get("episode_number")
    anime_name = user_state.data.get("anime_name", "Anime")


    if not all([anime_id_str, season_number is not None, episode_number is not None]):
        content_logger.error(f"Admin {user_id} sent date input but missing required state data.")
        await message.reply_text("💔 Error: State data missing for release date input. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return


    content_logger.info(f"Admin {user_id} provided release date input '{date_text}' for {anime_name} S{season_number}E{episode_number}.")

    # Validate and parse the date string (expects DD/MM/YYYY)
    try:
        # Need to import datetime again or ensure it's globally available (already is)
        # Use strptime to parse the string into a datetime object
        release_date_obj = datetime.strptime(date_text, '%d/%m/%Y').replace(tzinfo=timezone.utc) # Assume input is UTC or handle timezones

        # Update the specific episode document in the DB to set the release_date and remove 'files' array (if any)
        # Using $set on a nested array element and $unset to remove 'files'
        update_result = await MongoDB.anime_collection().update_one(
             {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}, # Filter to the exact episode using multiple levels
             {
                  "$set": {
                       "seasons.$.episodes.$.release_date": release_date_obj, # Positional operators
                       "last_updated_at": datetime.now(timezone.utc) # Update top-level
                  },
                  "$unset": {"seasons.$.episodes.$.files": ""} # Remove the files array
             }
             # Using positional operator with multiple levels ($[]) requires MongoDB version >= 3.6 and specific index considerations
             # Simpler approach for nested array updates might involve finding, modifying in memory, then saving the parent document,
             # BUT this can lead to race conditions if multiple admins edit same doc.
             # The $[] positional operator is generally better if the schema supports it.
             # The $ pull could also be used to remove files: {$pull: {"seasons.$.episodes.$.files": { "$exists": True } } } -- pull removes *elements*, not sets field to null. $unset is correct for removing field.
        )

        if update_result.modified_count > 0:
            content_logger.info(f"Admin {user_id} set release date for {anime_id_str}/S{season_number}E{episode_number}.")
            await message.reply_text(RELEASE_DATE_SET_SUCCESS.format(episode_number=episode_number, release_date=date_text), parse_mode=config.PARSE_MODE)

            # Return to the episode management menu for this episode (which will now show the date)
            # Need to re-fetch episode data
            anime_doc = await MongoDB.anime_collection().find_one( # Fetch the specific episode's context
                 {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number},
                 {"name": 1, "seasons.episode_number": 1, "seasons.$": 1} # Project useful fields, incl the matching season
            )

            if anime_doc and anime_doc.get("seasons"):
                 anime_name = anime_doc.get("name", "Anime Name Unknown")
                 season_data = anime_doc["seasons"][0] # The matching season
                 episodes = season_data.get("episodes", []) # The episodes *list* of the matching season
                 # Find the updated episode in the list (should be the one just updated)
                 updated_episode = next((ep for ep in episodes if ep.get("episode_number") == episode_number), None)

                 if updated_episode:
                     # Clear the AWAITING_RELEASE_DATE_INPUT state
                     updated_state_data = {k: v for k, v in user_state.data.items() if k != "temp_input"} # Clean state data
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODE_MENU, data=updated_state_data) # Back to episode menu state

                     await display_episode_management_menu(client, message, anime_name, season_number, episode_number, updated_episode)
                 else: raise Exception("Updated episode not found in refetch.")

            else:
                content_logger.error(f"Failed to fetch anime/season/episode after setting release date for admin {user_id}.")
                await message.reply_text("💔 Set release date, but failed to reload episode menu.", parse_mode=config.PARSE_MODE)


        else:
             # Modified count is 0 - season/episode not found by update query? Or same date entered?
             content_logger.warning(f"Admin {user_id} set release date for {anime_id_str}/S{season_number}E{episode_number} but modified_count was 0.")
             await message.reply_text("⚠️ Release date update modified 0 documents. Episode not found or same date entered? No changes made.", parse_mode=config.PARSE_MODE)
             # State is still AWAITING_RELEASE_DATE_INPUT, can re-enter date or cancel


    except ValueError:
        # Invalid date format
        await message.reply_text(INVALID_DATE_FORMAT, parse_mode=config.PARSE_MODE)
        # State remains AWAITING_RELEASE_DATE_INPUT, user needs to try again

    except Exception as e:
         content_logger.error(f"Error handling release date input for admin {user_id}: {e}")
         await message.reply_text("💔 Error saving release date.", parse_mode=config.PARSE_MODE)
         # State is AWAITING_RELEASE_DATE_INPUT, maybe clear state on complex errors?
         await clear_user_state(user_id)

# Callback: content_add_file_version|<anime_id>|<season_number>|<episode_number>
@Client.on_callback_query(filters.regex("^content_add_file_version\|.*\|.*\|.*") & filters.private)
async def content_add_file_version_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Add File Version for an episode."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_add_file_version|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer()

    user_state = await get_user_state(user_id)
    # State should be MANAGING_EPISODE_MENU or perhaps UPLOADING_FILE if they cancel and retry add file
    # Allow from episode menu or re-entry? Require episode menu for cleaner flow.
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODE_MENU):
         await callback_query.message.reply_text("🔄 Invalid state for adding file version.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for add file version.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        # Check state data matches callback for robustness
        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for add file version: {user_state.data} vs callback {data}")
             # Update state data to match callback data
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number})
             await set_user_state(user_id, "content_management", user_state.step, data=user_state.data)


        anime_name = user_state.data.get("anime_name", "Anime") # Get name from state

        # Transition to the state waiting for the file upload
        await set_user_state(user_id, "content_management", ContentState.UPLOADING_FILE, data=user_state.data) # Keep episode context

        # Prompt admin to upload the file
        prompt_text = ADD_FILE_PROMPT.format(episode_number=episode_number, season_number=season_number, anime_name=anime_name)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]])

        await callback_query.message.edit_text(
            prompt_text,
            reply_markup=reply_markup,
            parse_mode=config.PARSE_MODE
        )

    except Exception as e:
        content_logger.error(f"Error handling content_add_file_version callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)

# handle_episode_file_upload is called by common_handlers when file received in UPLOADING_FILE state.
# It stores temp file data in state.data and transitions to SELECTING_METADATA_QUALITY state.


# --- Metadata Selection Callbacks & Input Handling ---
# This is a complex multi-step flow using callbacks for selection and potentially text for manual entry.

# This callback handler builds the Quality selection keyboard.
# State: SELECTING_METADATA_QUALITY (triggered by handle_episode_file_upload)
async def prompt_for_metadata_quality(client: Client, chat_id: int):
    """Sends the prompt and buttons for admin to select file quality."""
    prompt_text = ADD_FILE_METADATA_PROMPT_BUTTONS.format()
    qualities = config.QUALITY_PRESETS # Use presets

    buttons = []
    for quality in qualities:
         # Callback data: content_select_quality|<quality_value>
         buttons.append(InlineKeyboardButton(quality, callback_data=f"content_select_quality|{quality}"))

    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
    # Add Cancel button
    keyboard_rows.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send quality prompt to chat {chat_id}: {e}")

# Handler for Quality selection callback
@Client.on_callback_query(filters.regex("^content_select_quality\|.*") & filters.private)
async def content_select_quality_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting file quality via buttons."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # content_select_quality|<quality_value>

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer() # Acknowledge

    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_QUALITY
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_QUALITY):
         await callback_query.message.reply_text("🔄 Invalid state for selecting quality.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for selecting quality.")
        selected_quality = parts[1]

        # Validate against presets (optional, admin might type later)
        # if selected_quality not in config.QUALITY_PRESETS:
        #      await callback_query.message.reply_text("🚫 Invalid quality selected.", parse_mode=config.PARSE_MODE); return

        # Store selected quality in temporary metadata state data
        # Use a separate nested dict for temp metadata being collected
        temp_metadata = user_state.data.get("temp_metadata", {})
        temp_metadata["quality_resolution"] = selected_quality
        user_state.data["temp_metadata"] = temp_metadata

        # Move to the next step: SELECTING_METADATA_AUDIO
        await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_AUDIO, data=user_state.data)

        # Prompt for Audio Languages selection (Callback-based, multi-select)
        await prompt_for_metadata_audio(client, chat_id, []) # Start with empty selection

        # Edit the previous message to confirm quality and prompt for audio
        try:
             await callback_query.message.edit_text(
                 f"💎 Quality selected: **__{selected_quality}__**.\n\n{PROMPT_AUDIO_LANGUAGES_BUTTONS}",
                 parse_mode=config.PARSE_MODE,
                 disable_web_page_preview=True
             )
        except Exception as e:
              content_logger.warning(f"Failed to edit message after quality select for admin {user_id}: {e}")
              await client.send_message(chat_id, f"💎 Quality selected: **__{selected_quality}__**.\n\n{PROMPT_AUDIO_LANGUAGES_BUTTONS}", parse_mode=config.PARSE_MODE)


    except Exception as e:
        content_logger.error(f"Error handling content_select_quality callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        # State is SELECTING_METADATA_QUALITY. Could stay there.
        # await clear_user_state(user_id) # Clear state if unsure


# This callback handler builds the Audio selection keyboard (multi-select)
async def prompt_for_metadata_audio(client: Client, chat_id: int, current_selection: List[str]):
    """Sends the prompt and buttons for admin to select audio languages."""
    prompt_text = PROMPT_AUDIO_LANGUAGES_BUTTONS
    languages = config.AUDIO_LANGUAGES_PRESETS # Use presets

    buttons = []
    for lang in languages:
        # Indicate selection state: content_toggle_audio|<language_value>
        is_selected = lang in current_selection
        button_text = f"🎧 {lang}" if is_selected else lang
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_audio|{lang}"))

    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    # Add Done and Cancel buttons
    keyboard_rows.append([
        InlineKeyboardButton(BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Audio Languages"), callback_data="content_audio_done"),
        InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        # Edit the previous message to display the new set of buttons
        await client.send_message( # Usually triggered after QUALITY selection, send NEW message for clarity?
             chat_id=chat_id, # Or edit message with quality? Editing is cleaner.
             text=prompt_text, # Message text already set in SELECT_QUALITY callback's edit
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send audio languages prompt to chat {chat_id}: {e}")

# Handler for Audio Language toggling (multi-select)
@Client.on_callback_query(filters.regex("^content_toggle_audio\|.*") & filters.private)
async def content_toggle_audio_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin toggling audio language selection via buttons."""
    user_id = callback_query.from_user.id
    # chat_id = callback_query.message.chat.id # Needed for retry editing?

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer() # Acknowledge immediately

    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_AUDIO
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_AUDIO):
        content_logger.warning(f"Admin {user_id} clicked audio toggle callback but state is {user_state}.")
        await callback_query.message.reply_text("🔄 Invalid state for selecting audio.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for toggling audio language.")
        language_to_toggle = parts[1]

        # Get currently selected audio languages from state data, initialize if not present
        temp_metadata = user_state.data.get("temp_metadata", {})
        selected_audio_languages = temp_metadata.get("audio_languages", [])

        # Toggle the language
        if language_to_toggle in selected_audio_languages:
            selected_audio_languages.remove(language_to_toggle)
        else:
             selected_audio_languages.append(language_to_toggle)
             # Add validation if max selected needed?

        # Update the selected languages in state data
        temp_metadata["audio_languages"] = selected_audio_languages
        user_state.data["temp_metadata"] = temp_metadata # Update the whole nested dict

        # We need to save the state update back to DB before editing the message/keyboard
        # Or ensure set_user_state does a merge update?
        # set_user_state({"temp_metadata": temp_metadata})
        # Our set_user_state(..., data=...) *replaces* data. Need to pass updated *full* data dict.
        await set_user_state(user_id, ContentState.SELECTING_METADATA_AUDIO.split(':')[0], ContentState.SELECTING_METADATA_AUDIO.split(':')[1], data=user_state.data) # Pass updated state.data


        # Recreate the audio selection keyboard with updated states
        prompt_text = PROMPT_AUDIO_LANGUAGES_BUTTONS # Use the base prompt again
        languages = config.AUDIO_LANGUAGES_PRESETS
        buttons = []
        for lang in languages:
            is_selected = lang in selected_audio_languages
            button_text = f"🎧 {lang}" if is_selected else lang # Use '🎧' as selected indicator
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_audio|{lang}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
        keyboard_rows.append([
             InlineKeyboardButton(BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Audio Languages"), callback_data="content_audio_done"),
             InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        # Edit the message to reflect the new selection using edit_reply_markup
        try:
             # Just edit the reply markup to avoid MessageNotModified issues if text hasn't changed
             await callback_query.message.edit_reply_markup(reply_markup)
        except MessageNotModified:
            pass
        except FloodWait as e:
            content_logger.warning(f"FloodWait while editing audio buttons for admin {user_id}: {e.value}")
            await asyncio.sleep(e.value)
            try: await callback_query.message.edit_reply_markup(reply_markup)
            except Exception: pass # Ignore retry failure

    except Exception as e:
        content_logger.error(f"Error handling content_toggle_audio callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        # Stay in state


# Handler for the "Done Selecting Audio" button
@Client.on_callback_query(filters.regex("^content_audio_done$") & filters.private)
async def content_audio_done_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Done after selecting audio languages."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Audio languages selected.")

    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_AUDIO
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_AUDIO):
        content_logger.warning(f"Admin {user_id} clicked Done Audio but state is {user_state}.")
        await callback_query.message.reply_text("🔄 Invalid state. Please restart the process.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return

    temp_metadata = user_state.data.get("temp_metadata", {})
    selected_audio_languages = temp_metadata.get("audio_languages", [])
    content_logger.info(f"Admin {user_id} finished selecting audio languages: {selected_audio_languages}")

    # Move to the next step: SELECTING_METADATA_SUBTITLES
    await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_SUBTITLES, data=user_state.data) # Keep state data with audio selection

    # Prompt for Subtitle Languages selection (Callback-based, multi-select)
    await prompt_for_metadata_subtitles(client, chat_id, []) # Start with empty selection

    # Edit the message to confirm audio selection and prompt for subtitles
    try:
        await callback_query.message.edit_text(
            f"🎧 Audio Languages saved: {', '.join(selected_audio_languages) if selected_audio_languages else 'None'}.\n\n{PROMPT_SUBTITLE_LANGUAGES_BUTTONS}",
            parse_mode=config.PARSE_MODE,
            disable_web_page_preview=True
        )
    except Exception as e:
        content_logger.warning(f"Failed to edit message after audio done for admin {user_id}: {e}")
        await client.send_message(chat_id, f"✅ Audio Languages saved. Please select **__Subtitle Languages__**.", parse_mode=config.PARSE_MODE)


# This callback handler builds the Subtitle selection keyboard (multi-select)
async def prompt_for_metadata_subtitles(client: Client, chat_id: int, current_selection: List[str]):
    """Sends the prompt and buttons for admin to select subtitle languages."""
    prompt_text = PROMPT_SUBTITLE_LANGUAGES_BUTTONS
    languages = config.SUBTITLE_LANGUAGES_PRESETS # Use presets

    buttons = []
    for lang in languages:
        # Indicate selection state: content_toggle_subtitle|<language_value>
        is_selected = lang in current_selection
        button_text = f"📝 {lang}" if is_selected else lang
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_subtitle|{lang}"))

    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    # Add Done and Cancel buttons
    keyboard_rows.append([
        InlineKeyboardButton(BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Subtitle Languages"), callback_data="content_subtitles_done"),
        InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        await client.send_message( # Send NEW message for clarity? Or edit the audio done message? Edit is cleaner.
             chat_id=chat_id, # This assumes the text message sent from content_audio_done exists.
             text=prompt_text, # Message text is already set in audio_done callback
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send subtitle languages prompt to chat {chat_id}: {e}")

# Handler for Subtitle Language toggling (multi-select)
@Client.on_callback_query(filters.regex("^content_toggle_subtitle\|.*") & filters.private)
async def content_toggle_subtitle_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin toggling subtitle language selection via buttons."""
    user_id = callback_query.from_user.id

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer()

    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_SUBTITLES
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_SUBTITLES):
        content_logger.warning(f"Admin {user_id} clicked subtitle toggle callback but state is {user_state}.")
        await callback_query.message.reply_text("🔄 Invalid state for selecting subtitles.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for toggling subtitle language.")
        language_to_toggle = parts[1]

        # Get currently selected subtitle languages from state data
        temp_metadata = user_state.data.get("temp_metadata", {})
        selected_subtitle_languages = temp_metadata.get("subtitle_languages", [])


        if language_to_toggle in selected_subtitle_languages:
            selected_subtitle_languages.remove(language_to_toggle)
        else:
             selected_subtitle_languages.append(language_to_toggle)

        # Update the selected languages in state data
        temp_metadata["subtitle_languages"] = selected_subtitle_languages
        user_state.data["temp_metadata"] = temp_metadata # Update nested dict

        await set_user_state(user_id, ContentState.SELECTING_METADATA_SUBTITLES.split(':')[0], ContentState.SELECTING_METADATA_SUBTITLES.split(':')[1], data=user_state.data) # Save state


        # Recreate the subtitle selection keyboard with updated states
        prompt_text = PROMPT_SUBTITLE_LANGUAGES_BUTTONS
        languages = config.SUBTITLE_LANGUAGES_PRESETS
        buttons = []
        for lang in languages:
            is_selected = lang in selected_subtitle_languages
            button_text = f"📝 {lang}" if is_selected else lang # Use '📝' as selected indicator
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_subtitle|{lang}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
        keyboard_rows.append([
             InlineKeyboardButton(BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Subtitle Languages"), callback_data="content_subtitles_done"),
             InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        # Edit the message to reflect the new selection
        try:
             await callback_query.message.edit_reply_markup(reply_markup)
        except MessageNotModified:
            pass
        except FloodWait as e:
            content_logger.warning(f"FloodWait while editing subtitle buttons for admin {user_id}: {e.value}")
            await asyncio.sleep(e.value)
            try: await callback_query.message.edit_reply_markup(reply_markup)
            except Exception: pass # Ignore retry failure

    except Exception as e:
        content_logger.error(f"Error handling content_toggle_subtitle callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        # Stay in state


# Handler for the "Done Selecting Subtitles" button
@Client.on_callback_query(filters.regex("^content_subtitles_done$") & filters.private)
async def content_subtitles_done_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Done after selecting subtitle languages."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 You are not authorized.", show_alert=True); return
    await callback_query.answer("Subtitle languages selected. Finalizing...")

    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_SUBTITLES
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_SUBTITLES):
        content_logger.warning(f"Admin {user_id} clicked Done Subtitles but state is {user_state}.")
        await callback_query.message.reply_text("🔄 Invalid state. Please restart the process.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return

    temp_metadata = user_state.data.get("temp_metadata", {})
    selected_subtitle_languages = temp_metadata.get("subtitle_languages", [])

    # --- All Metadata Collected! Now Save the FileVersion to the Episode! ---
    # Retrieve temp file and episode context from state data
    temp_upload_data = user_state.data.get("temp_upload")
    anime_id_str = user_state.data.get("anime_id")
    season_number = user_state.data.get("season_number")
    episode_number = user_state.data.get("episode_number")

    if not all([temp_upload_data, anime_id_str, season_number is not None, episode_number is not None]):
        content_logger.error(f"Admin {user_id} finished metadata selection but missing temp_upload or episode context from state.")
        await callback_query.message.reply_text("💔 Error: Required data missing from state. File not saved. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return

    # Ensure quality and audio languages are also present in temp_metadata (should be from previous steps)
    selected_quality = temp_metadata.get("quality_resolution")
    selected_audio_languages = temp_metadata.get("audio_languages", []) # Default to empty list if somehow missing


    if not selected_quality:
        content_logger.error(f"Admin {user_id} finished metadata but quality is missing from temp_metadata state.")
        await callback_query.message.reply_text("💔 Error: Quality missing from state data. File not saved. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return

    # Create the FileVersion Pydantic model instance from collected data
    try:
         file_version_data = {
              "file_id": temp_upload_data.get("file_id"),
              "file_unique_id": temp_upload_data.get("file_unique_id"),
              "file_name": temp_upload_data.get("file_name"),
              "file_size_bytes": temp_upload_data.get("file_size_bytes"),
              "quality_resolution": selected_quality,
              "audio_languages": selected_audio_languages,
              "subtitle_languages": selected_subtitle_languages,
              "added_at": datetime.now(timezone.utc) # Set addition time
         }
         new_file_version = FileVersion(**file_version_data)

    except Exception as e:
        content_logger.error(f"Error creating FileVersion model for admin {user_id}: {e}. Data: {file_version_data}")
        await callback_query.message.reply_text("💔 Error creating file data. File not saved. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return


    # Add the new FileVersion subdocument to the specific Episode in the Season in the Anime
    # Use $push with positional operator
    try:
        update_result = await MongoDB.anime_collection().update_one(
             {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number},
             {
                  "$push": {"seasons.$.episodes.$.files": model_to_mongo_dict(new_file_version)}, # Push the new file version dict
                  "$set": {"last_updated_at": datetime.now(timezone.utc)} # Update top-level timestamp
             }
        )

        if update_result.modified_count > 0:
            content_logger.info(f"Admin {user_id} added file version ({new_file_version.quality_resolution}) to {anime_id_str}/S{season_number}E{episode_number}.")
            await callback_query.message.edit_text(FILE_ADDED_SUCCESS.format(
                episode_number=episode_number,
                quality=new_file_version.quality_resolution,
                audio='/'.join(new_file_version.audio_languages),
                subs='/'.join(new_file_version.subtitle_languages)
            ), parse_mode=config.PARSE_MODE)

            # After saving the file, transition back to the episode management menu
            # We need to fetch the episode data again to display the updated menu
            anime_doc = await MongoDB.anime_collection().find_one(
                 {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number},
                 {"name": 1, "seasons.episode_number": 1, "seasons.$": 1}
            )
            if anime_doc and anime_doc.get("seasons"):
                 anime_name = anime_doc.get("name", "Anime Name Unknown")
                 season_data = anime_doc["seasons"][0]
                 episodes_list = season_data.get("episodes", []) # Get episodes of this season
                 updated_episode = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None) # Find this specific episode

                 if updated_episode:
                     # Clear file upload/metadata selection states and temp data, set state back to managing episode
                     # Remove temp_upload and temp_metadata, selected_audio/subtitle keys from state data
                     updated_state_data = {k: v for k, v in user_state.data.items() if k not in ["temp_upload", "temp_metadata", "selected_audio_languages", "selected_subtitle_languages"]}
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODE_MENU, data=updated_state_data)

                     await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, updated_episode)
                 else: raise Exception("Updated episode not found in refetch after saving file.")


            else:
                 content_logger.error(f"Failed to fetch anime/season/episode after saving file version for admin {user_id}.")
                 await callback_query.message.reply_text("💔 Saved file, but failed to reload episode menu.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id) # Clear state if cannot display menu

        else:
             content_logger.warning(f"Admin {user_id} finished metadata for {anime_id_str}/S{season_number}E{episode_number} but modified_count was 0.")
             await callback_query.message.edit_text("⚠️ File version update modified 0 documents. Episode not found or something else prevented save?", parse_mode=config.PARSE_MODE)
             # State is SELECTING_METADATA_SUBTITLES. Clear it as something went wrong.
             await clear_user_state(user_id)

    except Exception as e:
         content_logger.error(f"Error saving FileVersion for admin {user_id}: {e}")
         await callback_query.message.reply_text("💔 Error saving file version to database. Process cancelled.", parse_mode=config.PARSE_MODE)
         # Critical error saving, clear state
         await clear_user_state(user_id)


    except Exception as e:
        content_logger.error(f"Error handling content_subtitles_done callback for admin {user_id}: {e}")
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        # State is SELECTING_METADATA_SUBTITLES, keep it? Or clear on complex errors?
        await clear_user_state(user_id) # Clear on complex error


#----------------------------------------------------------------------------------------------------


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
