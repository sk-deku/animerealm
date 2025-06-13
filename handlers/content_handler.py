# handlers/content_handler.py
import logging
import asyncio # Needed for FloodWait, sleeps, etc.
from typing import Union, List, Dict, Any # Import type hints
from datetime import datetime, timedelta, timezone # For handling date and time inputs and expiries
from pyrogram import Client, filters # Import Pyrogram core and filters
# Import Pyrogram types needed for message/callback handling and file processing
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    Document, Video, Photo # Specific media types for file handling
)
# Import specific Pyrogram errors for graceful handling
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant,
    AsyncioErrorMessage, BotInlineMessageNotFoundError # More specific error types
)


# Import configuration constants
import config

# Import string constants for messages and button labels
import strings

# Import database models and utilities
from database.mongo_db import MongoDB # Access the MongoDB class instance methods
# Import specific DB state management helper functions
from database.mongo_db import get_user_state, set_user_state, clear_user_state
# Import models for type hinting, validation, and dictionary conversion
from database.models import (
    UserState, Anime, Season, Episode, FileVersion, PyObjectId, model_to_mongo_dict # Model and helper
)

# Import fuzzy matching for searching existing anime during admin add/edit
from fuzzywuzzy import process

# Import necessary helpers from common_handlers if used there (e.g., get_user, edit_or_send_message)
# Although many common helpers are replicated or integrated here for context
# It's generally better to import them from common_handlers if they are truly common and not content-specific.
# For this example, assume some basic helpers are used directly for self-containment or common imports at the top.
# Let's rely on config, strings, and DB modules being imported and common imports like asyncio, logging, typing etc.
# Need get_user and edit_or_send_message - they were defined in common_handlers. Let's re-import those patterns here if not globally accessible.
# Re-import necessary helpers (or ensure they are globally available from common) - assuming they are defined here now for completeness
async def get_user(client: Client, user_id: int) -> Optional[User]: pass # Assume this is accessible
async def edit_or_send_message(client: Client, chat_id: int, message_id: Optional[int], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = True): pass # Assume accessible


# Configure logger specifically for content handlers
content_logger = logging.getLogger(__name__)


# --- States for Content Management Process ---
# Defines all possible steps within the "content_management" state handler
class ContentState:
    # Initial Steps (Add New Anime Flow)
    AWAITING_ANIME_NAME = "awaiting_anime_name"          # Expecting text (anime name)
    AWAITING_POSTER = "awaiting_poster"                  # Expecting photo
    AWAITING_SYNOPSIS = "awaiting_synopsis"              # Expecting text
    AWAITING_TOTAL_SEASONS_COUNT = "awaiting_total_seasons_count" # Expecting number (total seasons for series)
    SELECTING_GENRES = "selecting_genres"                # Expecting callback (genre buttons) or text (manual entry fallback)
    AWAITING_RELEASE_YEAR = "awaiting_release_year"      # Expecting number (year)
    SELECTING_STATUS = "selecting_status"                # Expecting callback (status buttons)

    # Managing Existing Anime (Main Menu for a Specific Anime)
    MANAGING_ANIME_MENU = "managing_anime_menu"          # Expecting callback (menu buttons)

    # Managing Seasons (List of Seasons for an Anime)
    MANAGING_SEASONS_LIST = "managing_seasons_list"      # Expecting callback (season buttons) or text (search? Not implemented)
    # States for editing top-level anime fields via callbacks
    EDITING_NAME_PROMPT = "editing_name_prompt"           # Waiting for text input for new name
    EDITING_SYNOPSIS_PROMPT = "editing_synopsis_prompt"   # Waiting for text input for new synopsis
    EDITING_POSTER_PROMPT = "editing_poster_prompt"       # Waiting for photo input for new poster
    EDITING_TOTAL_SEASONS_COUNT_PROMPT = "editing_total_seasons_count_prompt" # Waiting for number input for total seasons

    # Managing Episodes (List of Episodes for a Season)
    MANAGING_EPISODES_LIST = "managing_episodes_list"    # Expecting callback (episode buttons)

    # Managing a Specific Episode (Options Menu for a Single Episode)
    MANAGING_EPISODE_MENU = "managing_episode_menu"      # Expecting callback (file/date/delete buttons)

    # Episode Content Steps (Adding File Version or Release Date)
    AWAITING_RELEASE_DATE_INPUT = "awaiting_release_date_input"# Expecting text (DD/MM/YYYY date string)
    UPLOADING_FILE = "uploading_file"                    # Expecting document/video (actual file)

    # Episode File Metadata Collection (Multi-step, Callback/Text)
    SELECTING_METADATA_QUALITY = "selecting_metadata_quality" # Expecting callback (quality buttons) or text
    SELECTING_METADATA_AUDIO = "selecting_metadata_audio"     # Expecting callback (audio buttons, multi-select) or text
    SELECTING_METADATA_SUBTITLES = "selecting_metadata_subtitles"# Expecting callback (subtitle buttons, multi-select) or text

    # Removing Resources (Confirmation Step)
    CONFIRM_REMOVE_SEASON = "confirm_remove_season"       # Expecting callback (confirm/cancel buttons)
    CONFIRM_REMOVE_EPISODE = "confirm_remove_episode"     # Expecting callback (confirm/cancel buttons)
    SELECT_FILE_VERSION_TO_DELETE = "select_file_version_to_delete" # Expecting callback (version buttons)
    CONFIRM_REMOVE_FILE_VERSION = "confirm_remove_file_version" # Expecting callback (confirm/cancel buttons)


# --- Core Routing Functions (Called from common_handlers) ---
# These functions handle the logic when common_handlers determines the user
# is in the "content_management" state and has sent text or media.

async def handle_content_input(client: Client, message: Message, user_state: UserState):
    """
    Routes text input from an admin user currently in the content_management state
    to the specific helper function for that step.
    Called by common_handlers.handle_plain_text_input.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    input_text = message.text.strip()
    current_step = user_state.step

    content_logger.debug(f"Handling text input for admin {user_id} at step: {current_step} with text: '{input_text[:100]}...'")

    try:
        # Route based on the current step (dispatch to helper functions)
        if current_step == ContentState.AWAITING_ANIME_NAME:
             await handle_awaiting_anime_name_input(client, message, user_state, input_text) # Pass input_text here

        # Add New Anime Flow - Steps expecting Text Input
        elif current_step == ContentState.AWAITING_SYNOPSIS:
             await handle_awaiting_synopsis_input(client, message, user_state, input_text)
        elif current_step == ContentState.AWAITING_TOTAL_SEASONS_COUNT:
             await handle_awaiting_total_seasons_count_input(client, message, user_state, input_text)
        elif current_step == ContentState.AWAITING_RELEASE_YEAR:
             await handle_awaiting_release_year_input(client, message, user_state, input_text)
        # SELECTING_GENRES/STATUS primarily use callbacks, but *could* have text input fallback (e.g., typing genre name if not in presets).
        # We will not implement text input fallback for selections initially for simplicity.

        # Editing Anime Fields - Steps expecting Text Input
        elif current_step == ContentState.EDITING_NAME_PROMPT:
             await handle_editing_name_input(client, message, user_state, input_text)
        elif current_step == ContentState.EDITING_SYNOPSIS_PROMPT:
             await handle_editing_synopsis_input(client, message, user_state, input_text)
        elif current_step == ContentState.EDITING_TOTAL_SEASONS_COUNT_PROMPT:
             await handle_editing_total_seasons_count_input(client, message, user_state, input_text) # Edit total seasons count
        elif current_step == ContentState.EDITING_RELEASE_YEAR_PROMPT:
             await handle_editing_release_year_input(client, message, user_state, input_text)

        # Episode Management - Step expecting Text Input
        elif current_step == ContentState.AWAITING_RELEASE_DATE_INPUT:
             await handle_awaiting_release_date_input(client, message, user_state, input_text)


        # File Metadata - Text input fallback (Not implemented in first pass, rely on buttons)
        # elif current_step == ContentState.SELECTING_METADATA_QUALITY:
        #      # Admin might type quality manually if not in buttons
        #      await handle_selecting_metadata_quality_input(client, message, user_state, input_text)
        # elif current_step == ContentState.SELECTING_METADATA_AUDIO:
        #      # Admin might type languages manually if not in buttons
        #      await handle_selecting_metadata_audio_input(client, message, user_state, input_text)
        # elif current_step == ContentState.SELECTING_METADATA_SUBTITLES:
        #      # Admin might type languages manually
        #      await handle_selecting_metadata_subtitles_input(client, message, user_state, input_text)


        else:
            # Received unexpected text input for a known content_management state.
            content_logger.warning(f"Admin {user_id} sent unexpected text input while in content_management state {current_step}: '{input_text[:100]}...'")
            await message.reply_text("🤔 That wasn't the input I was expecting for this step. Please provide the requested information, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
            # Stay in the current state, user can try again or cancel.


    except Exception as e:
         content_logger.error(f"FATAL error in handle_content_input for user {user_id} at step {current_step}: {e}", exc_info=True)
         # Clear the state on critical error to prevent getting stuck
         await clear_user_state(user_id)
         await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await manage_content_command(client, message) # Offer to restart CM flow

async def handle_media_input(client: Client, message: Message, user_state: UserState):
    """
    Handles media input from an admin user currently in the content_management state.
    Called by common_handlers.handle_media_input.
    Routes file input based on the current state.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_step = user_state.step

    content_logger.debug(f"Handling media input for admin {user_id} at step: {current_step} (Photo: {bool(message.photo)}, Doc: {bool(message.document)}, Video: {bool(message.video)})")

    try:
        if current_step == ContentState.AWAITING_POSTER or current_step == ContentState.EDITING_POSTER_PROMPT:
             # Expecting a PHOTO for a poster image
             if message.photo:
                  await handle_awaiting_poster(client, message, user_state) # This helper now handles both ADD and EDIT poster based on state data purpose
             else:
                  # Received non-photo media when expecting a poster
                  await message.reply_text("👆 Please send a **photo** to use as the anime poster, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
                  # State remains the same (AWAITING_POSTER or EDITING_POSTER_PROMPT), user needs to send a photo

        elif current_step == ContentState.UPLOADING_FILE:
             # Expecting a DOCUMENT or VIDEO for an episode file
             if message.document or message.video:
                  await handle_episode_file_upload(client, message, user_state, message.document or message.video) # Pass the file object itself
             else:
                  # Received non-file media when expecting episode file
                  await message.reply_text("⬆️ Please upload the episode file (video or document), or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
                  # State remains UPLOADING_FILE, user needs to send doc/video


        else:
            # Admin is in content management state, but this step does not expect media input.
            content_logger.warning(f"Admin {user_id} sent media input ({message.media}) while in content_management state {current_step}, which does not expect media input.")
            await message.reply_text("🤷 I'm not expecting a file or photo right now based on your current action. Please continue with the current step or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
            # State remains the same.

    except Exception as e:
         content_logger.error(f"FATAL error handling media input for user {user_id} at step {current_step}: {e}", exc_info=True)
         await clear_user_state(user_id) # Clear state on critical error
         await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await manage_content_command(client, message) # Offer to restart CM flow


# --- Entry Point Handler ---

# Handles the initial command to enter Content Management.
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

    # Clear any previous lingering state, and set the state for the main CM menu
    # This assumes that entering /manage_content *always* starts them at the top menu.
    # If you wanted to resume progress, you'd check state here and route accordingly.
    try:
        await clear_user_state(user_id)
        await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU) # Main CM menu state

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(strings.BUTTON_ADD_NEW_ANIME, callback_data="content_add_new_anime")],
            [InlineKeyboardButton(strings.BUTTON_EDIT_ANIME, callback_data="content_edit_anime_prompt")], # Edit starts by prompting name search
            # Implement content_view_all handler which shows a paginated list of anime to manage
            [InlineKeyboardButton(strings.BUTTON_VIEW_ALL_ANIME, callback_data="content_view_all_anime_list")], # List all for selecting one to edit/delete

            [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")], # Back to main bot user menu
        ])

        await message.reply_text(
            f"**{strings.MANAGE_CONTENT_TITLE}**\n\n{strings.MANAGE_CONTENT_OPTIONS}",
            reply_markup=reply_markup,
            parse_mode=config.PARSE_MODE,
            disable_web_page_preview=True
        )
    except Exception as e:
        content_logger.error(f"Failed to send manage content menu to admin {user_id}: {e}", exc_info=True)
        await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


# --- Callbacks from the Main Content Management Menu ---

@Client.on_callback_query(filters.regex("^content_(?!toggle|select|done).*") & filters.private) # Catch content_ callbacks EXCEPT those for genre/metadata multi-select
async def content_main_menu_callbacks(client: Client, callback_query: CallbackQuery):
    """Handles non-selection callbacks from the main content management menu and sub-menus."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # ID of the message to edit
    data = callback_query.data

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    content_logger.info(f"Admin {user_id} clicked CM callback: {data}")

    # Acknowledge the callback query immediately
    try:
        # Some actions might take time, indicate progress. Or answer silently depending on the action.
        # Default to silent answer for general navigation/prompts
        await callback_query.answer()
    except Exception:
        content_logger.warning(f"Failed to answer callback query: {data} from admin {user_id}")


    # Check user state to ensure they are in the content management flow or starting one
    # We don't necessarily need to check for a *specific* step here, but being within handler="content_management" is a good sign.
    user_state = await get_user_state(user_id)
    # If state is missing or handler is wrong, reset to main CM menu
    if user_state is None or user_state.handler != "content_management":
         content_logger.warning(f"Admin {user_id} clicked {data} but state is {user_state}. Resetting to main CM menu.")
         # Don't clear state here, let manage_content_command handle it for the start state
         await manage_content_command(client, callback_query.message) # Resend the main menu
         return # Stop here


    # --- Process Callback Data (Routing for non-selection CM callbacks) ---
    try:
        if data == "content_add_new_anime":
            # Start the "Add New Anime" sequence - requires anime name input first
            await set_user_state(user_id, "content_management", ContentState.AWAITING_ANIME_NAME, data={"purpose": "add"})

            # Prompt for the anime name
            await edit_or_send_message(
                 client,
                 chat_id,
                 message_id, # Edit the message the button was on
                 strings.ADD_ANIME_NAME_PROMPT.format(),
                 InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]) # Cancel button
             )


        elif data == "content_edit_anime_prompt":
             # Start the "Edit Existing Anime" sequence - requires anime name search first
             # Reuse AWAITING_ANIME_NAME state, but signify purpose is 'edit' in state data
            await set_user_state(user_id, "content_management", ContentState.AWAITING_ANIME_NAME, data={"purpose": "edit"})

            # Prompt for the anime name to search for editing
            await edit_or_send_message(
                 client,
                 chat_id,
                 message_id, # Edit message
                 strings.ADD_ANIME_NAME_PROMPT.format(), # Reuse prompt text
                 InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
             )


        elif data == "content_view_all_anime_list":
             # Handle displaying a paginated list of all anime for admins to browse and select for editing
             # This will involve fetching data and building the list/pagination UI.
             # Implement browse_handler-like logic adapted for admin view.
             await edit_or_send_message(
                  client,
                  chat_id,
                  message_id,
                  "📚 <b><u>Admin View All Anime</u></b> 📚\n\n<i>(Under Construction - Will show list of anime for editing)</i>",
                   InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")]]) # Back to CM main
              )
             # No state change yet, admin is just viewing a list. Selecting an anime from the list would set state for managing THAT anime.
             # await display_admin_anime_list(client, callback_query.message) # Needs implementation


        elif data == "content_management_main_menu":
            # Handle explicit return to the main content management menu
            # Ensures state is set correctly and displays the menu.
            await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU) # Ensure state is the main CM menu

            reply_markup = InlineKeyboardMarkup([
                 [InlineKeyboardButton(strings.BUTTON_ADD_NEW_ANIME, callback_data="content_add_new_anime")],
                 [InlineKeyboardButton(strings.BUTTON_EDIT_ANIME, callback_data="content_edit_anime_prompt")],
                 [InlineKeyboardButton(strings.BUTTON_VIEW_ALL_ANIME, callback_data="content_view_all_anime_list")],
                 [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")],
            ])
            await edit_or_send_message(
                 client,
                 chat_id,
                 message_id,
                 f"**{strings.MANAGE_CONTENT_TITLE}**\n\n{strings.MANAGE_CONTENT_OPTIONS}",
                 reply_markup,
                 disable_web_page_preview=True
             )

        elif data == "content_cancel":
            # Universal cancel button within the content management flow
            await clear_user_state(user_id)
            await edit_or_send_message(
                 client,
                 chat_id,
                 message_id,
                 strings.ACTION_CANCELLED,
                 # Remove reply markup after cancelling
             )
            content_logger.info(f"Admin {user_id} explicitly cancelled content management process.")


        # --- Handlers triggered AFTER initial name search ---
        # content_edit_existing|<anime_id> is handled here as it initiates management of an existing anime
        elif data.startswith("content_edit_existing|"):
             anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
             await handle_edit_existing_anime_selection(client, callback_query.message, user_state, anime_id_str) # Pass message for editing

        # content_proceed_add_new|<anime_name> is handled here as it proceeds to adding a new anime after name check
        elif data.startswith("content_proceed_add_new|"):
            new_anime_name = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
            await handle_proceed_add_new_anime(client, callback_query.message, user_state, new_anime_name) # Pass message for editing

        # --- Anime Management Menu Callbacks (within MANAGING_ANIME_MENU state) ---
        # content_manage_seasons|<anime_id> is handled here
        elif data.startswith("content_manage_seasons|"):
            anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
             # Ensure current state matches or transition is allowed from a previous CM state
             # We are coming from MANAGEMENT_ANIME_MENU
            if not (user_state.step == ContentState.MANAGING_ANIME_MENU):
                content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking manage seasons. State data: {user_state.data}")
                await callback_query.message.reply_text("🔄 Invalid state to manage seasons. Please return to the Anime Management Menu.", parse_mode=config.PARSE_MODE)
                # Do NOT clear state, just prompt them to go back


            # Transition to MANAGING_SEASONS_LIST state for this anime
            await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data={**user_state.data, "anime_id": anime_id_str}) # Ensure anime_id in state data

            # Display the seasons list menu
            # Need to fetch anime seasons
            anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})
            if not anime_doc:
                content_logger.error(f"Anime {anime_id_str} not found for managing seasons (callback) for admin {user_id}.")
                await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found.", disable_web_page_preview=True)
                await clear_user_state(user_id) # Clear state as anime is missing
                return

            await display_seasons_management_menu(client, callback_query.message, Anime(**anime_doc)) # Pass message to edit

        # Handlers for editing specific fields like name, synopsis, etc. (trigger text/file input states)
        elif data.startswith("content_edit_name|"): await handle_edit_name_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_synopsis|"): await handle_edit_synopsis_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_poster|"): await handle_edit_poster_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_genres|"): await handle_edit_genres_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_year|"): await handle_edit_year_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_status|"): await handle_edit_status_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_total_seasons_count|"): await handle_edit_total_seasons_count_callback(client, callback_query.message, user_state, data)


        # --- Season Management Menu Callbacks (within MANAGING_SEASONS_LIST state) ---
        # content_add_new_season|<anime_id>|<next_season_number>
        elif data.startswith("content_add_new_season|"): await handle_add_new_season_callback(client, callback_query.message, user_state, data)

        # content_remove_season_select|<anime_id>
        elif data.startswith("content_remove_season_select|"): await handle_remove_season_select_callback(client, callback_query.message, user_state, data)
        # content_confirm_remove_season|<anime_id>|<season_number> (Confirmation step)
        elif data.startswith("content_confirm_remove_season|"): await handle_confirm_remove_season_callback(client, callback_query.message, user_state, data)


        # content_select_season|<anime_id>|<season_number> - Handles selection from seasons list
        elif data.startswith("content_select_season|"): await handle_select_season_callback(client, callback_query.message, user_state, data)


        # --- Episode Management List Callbacks (within MANAGING_EPISODES_LIST state) ---
        # content_manage_episode|<anime_id>|<season_number>|<episode_number> - Handles selection from episodes list
        elif data.startswith("content_manage_episode|"): await handle_select_episode_callback(client, callback_query.message, user_state, data)


        # --- Episode Management Menu Callbacks (within MANAGING_EPISODE_MENU state) ---
        # content_add_file_version|<anime_id>|<season>|<ep> - Trigger file upload state
        elif data.startswith("content_add_file_version|"): await handle_add_file_version_callback(client, callback_query.message, user_state, data)

        # content_add_release_date|<anime_id>|<season>|<ep> - Trigger release date input state
        elif data.startswith("content_add_release_date|"): await handle_add_release_date_callback(client, callback_query.message, user_state, data)

        # content_go_next_episode|<anime_id>|<season>|<ep> - Navigate to next episode menu
        elif data.startswith("content_go_next_episode|"): await handle_go_next_episode_callback(client, callback_query.message, user_state, data)

        # content_remove_episode|<anime_id>|<season>|<ep> - Remove a single episode (Needs confirmation!)
        # Adding confirmation step here like remove season
        elif data.startswith("content_remove_episode|"): await handle_remove_episode_callback(client, callback_query.message, user_state, data) # This handler will initiate confirmation


        # content_delete_file_version_menu|<anime_id>|<season>|<ep> - Trigger select version to delete menu
        elif data.startswith("content_delete_file_version_menu|"): await handle_delete_file_version_select_callback(client, callback_query.message, user_state, data)
        # content_confirm_remove_file_version|<anime_id>|<season>|<ep>|<file_unique_id> - Confirm deletion
        elif data.startswith("content_confirm_remove_file_version|"): await handle_confirm_remove_file_version_callback(client, callback_query.message, user_state, data)


        else:
            # A content_ callback was received that doesn't match any implemented handlers.
            content_logger.warning(f"Admin {user_id} clicked unhandled content_ callback: {data} in state {user_state.step}")
            await callback_query.answer("⚠️ This action is not implemented yet or invalid.", show_alert=False) # Acknowledge silently

    except ValueError as e:
        content_logger.error(f"Invalid callback data format for admin {user_id} clicking {data}: {e}", exc_info=True)
        await callback_query.message.reply_text("🚫 Invalid data received from button. Please try again.", parse_mode=config.PARSE_MODE)
        # State remains the same. User can retry clicking valid buttons.

    except Exception as e:
         content_logger.error(f"FATAL error processing content callback {data} for user {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id) # Clear state on complex error
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await manage_content_command(client, callback_query.message) # Offer to restart CM flow

# --- Helper Functions for Specific Steps in Add New Anime Flow ---

# This helper is called by handle_content_input when state is AWAITING_ANIME_NAME
async def handle_awaiting_anime_name_input(client: Client, message: Message, user_state: UserState, anime_name_input: str):
    """Handles admin text input when in the AWAITING_ANIME_NAME state."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    # --- Fuzzy Search for Existing Anime ---
    try:
        # Fetch all anime names and their IDs for fuzzy matching. Cache this list if it gets very large.
        # Projecting only 'name' and '_id' for efficiency.
        anime_name_docs = await MongoDB.anime_collection().find({}, {"name": 1}).to_list(None) # to_list(None) gets all results
        anime_names_dict = {doc['name']: str(doc['_id']) for doc in anime_name_docs} # Map name string to DB ObjectId string

        # Perform fuzzy matching. Use the list of names as choices.
        # process.extract(query, choices, limit) returns list of (match_string, score)
        # Set limit to config value, e.g., top 5.
        search_results = process.extract(anime_name_input, anime_names_dict.keys(), limit=config.POPULAR_COUNT) # Reuse popular count config limit, maybe add specific config for this? Let's use a sensible small number like 5 or 10 directly

        content_logger.info(f"Fuzzy search for '{anime_name_input}' by admin {user_id} in AWAITING_ANIME_NAME returned {len(search_results)} matches.")

        # Filter results by confidence score threshold
        # Store filtered matches as a list of dicts with _id and name
        matching_anime = []
        for name_match, score in search_results:
             if score >= config.FUZZYWUZZY_THRESHOLD:
                 anime_id_str = anime_names_dict[name_match] # Get the original DB _id string for this name match
                 matching_anime.append({"_id": anime_id_str, "name": name_match, "score": score})

        content_logger.debug(f"Filtered fuzzy search results ({len(matching_anime)}) for admin {user_id}: {matching_anime}")


    except Exception as e:
        content_logger.error(f"Error during fuzzy search for anime name input '{anime_name_input}' by admin {user_id}: {e}", exc_info=True)
        await message.reply_text("💔 Error performing search for existing anime.", parse_mode=config.PARSE_MODE)
        # Stay in state, admin can retry typing name or cancel.
        return


    # --- Determine Next Step Based on Search Results and Purpose (Add/Edit) ---
    purpose = user_state.data.get("purpose", "add") # Get purpose from state data, default to 'add'

    # Logic branches significantly based on the purpose ('add' vs 'edit')
    if purpose == "add":
        # Admin clicked "Add New Anime" -> sent a name.
        # We now check if the name is similar to existing ones to prevent duplicates, but the primary path is ADD NEW.
        if matching_anime:
             # Found matches - show them and offer to select one for editing OR proceed with adding NEW.
             response_text = strings.ADD_ANIME_NAME_SEARCH_RESULTS.format(name=anime_name_input)
             buttons = []
             # Add buttons for each existing match, enabling admin to jump to EDITING if it's what they wanted
             for match in matching_anime:
                 # Callback data to edit an existing anime: content_edit_existing|<anime_id>
                 buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing|{match['_id']}")])

             # Add the crucial option to IGNORE matches and proceed with adding a NEW anime with the provided name
             # Callback data: content_proceed_add_new|<anime_name> (Pass the input name)
             # Ensure name is URL-encoded if it can contain special characters not safe for callback_data? Or limit allowed chars?
             # Base64 encoding is an option if names can be arbitrary, but increases callback size. Let's hope typical names are fine or encode simple.
             encoded_anime_name = anime_name_input # Simple approach for now, review callback data size limits!
             buttons.append([InlineKeyboardButton(strings.BUTTON_ADD_AS_NEW_ANIME.format(name=anime_name_input), callback_data=f"content_proceed_add_new|{encoded_anime_name}")])

             # Add a Cancel button
             buttons.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")])

             reply_markup = InlineKeyboardMarkup(buttons)

             # Stay in AWAITING_ANIME_NAME state, but now waiting for callback selection from these options
             try:
                 await message.reply_text(response_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
             except Exception as e:
                 content_logger.error(f"Failed to send anime search results (add flow) for admin {user_id}: {e}", exc_info=True)
                 await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)

             # No state change needed, user remains in AWAITING_ANIME_NAME waiting for selection.


        else:
             # No significant matches found using fuzzy search (score below threshold).
             # Proceed directly with the "Add New Anime" flow using the name provided by the admin.
             # Call the helper function that handles this progression.
             await handle_proceed_add_new_anime(client, message, user_state, anime_name_input) # Reuse the helper for "Add New" sequence start


    elif purpose == "edit":
        # Admin clicked "Edit Existing Anime" -> sent a name to search for editing.
        # We must find a specific anime for editing.
        if matching_anime:
            # Found matches - show them and require the admin to select one to edit.
            response_text = f"🔍 Found these anime matching '<code>{anime_name_input}</code>'. Select one to <b><u>edit</u></b>: 👇"
            buttons = []
            # Add buttons for each matching anime
            for match in matching_anime:
                 # Callback data for editing needs the anime_id: content_edit_existing|<anime_id>
                buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing|{match['_id']}")])

            # Add a Back button to re-prompt name input for editing, and a Cancel button.
            buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="content_edit_anime_prompt")]) # Go back to the initial prompt for editing name search
            buttons.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")])

            reply_markup = InlineKeyboardMarkup(buttons)

            # State remains AWAITING_ANIME_NAME with purpose: 'edit', waiting for callback selection.
            try:
                 await message.reply_text(response_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
            except Exception as e:
                 content_logger.error(f"Failed to send anime search results (edit flow) for admin {user_id}: {e}", exc_info=True)
                 await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


        else:
             # No strong matches found for editing with the given name. Inform admin and prompt again.
             await message.reply_text(
                  f"😔 Couldn't find any anime matching '<code>{anime_name_input}</code>' with confidence above {config.FUZZYWUZZY_THRESHOLD} for editing."
                   "\nPlease try a different name to search for an anime to edit, or type '❌ Cancel'.",
                  parse_mode=config.PARSE_MODE
              )
             # State remains AWAITING_ANIME_NAME with purpose: 'edit', waiting for text input. Admin needs to send another name or cancel.


    else:
        # Should not happen if initial state data setting is correct.
        # Input received in AWAITING_ANIME_NAME state but 'purpose' is invalid or missing from state data.
        content_logger.error(f"Admin {user_id} sent input in AWAITING_ANIME_NAME state but purpose is {purpose}.", exc_info=True)
        await message.reply_text("🤷 Invalid state data for this step. Please try again.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id) # Clear potentially broken state


# --- Helpers for transitioning out of AWAITING_ANIME_NAME state ---

# Helper called by handle_awaiting_anime_name_input or content_main_menu_callbacks (proceed_add_new)
async def handle_proceed_add_new_anime(client: Client, message: Message, user_state: UserState, anime_name: str):
    """Starts the multi-step process of adding a NEW anime after the name has been determined."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id # ID of the message to edit if applicable (coming from callback)

    content_logger.info(f"Admin {user_id} proceeding to add new anime with name: '{anime_name}'.")

    # Check for and clear any previous related state just to be safe
    if user_state.handler == "content_management" and user_state.step == ContentState.AWAITING_ANIME_NAME:
        await clear_user_state(user_id) # Clear the name input state

    # Set the state for the next step: AWAITING_POSTER. Store initial data.
    # Use the received anime_name as the primary key piece of info in state data for this flow
    await set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={"new_anime_name": anime_name})

    # Send the prompt for the poster image
    await prompt_for_poster(client, chat_id, anime_name)

    # Optionally edit the previous message or send a confirmation reply
    try:
         if message_id is not None and isinstance(message, CallbackQuery): # If triggered from a callback
             await message.edit_text(
                  f"✅ Okay, adding new anime: <b>{anime_name}</b>\n\nSent prompt for poster.", # Edit callback message
                  parse_mode=config.PARSE_MODE
             )
         else: # Triggered from initial text input after no fuzzy match
             await message.reply_text(
                  f"✅ Okay, adding new anime: <b>{anime_name}</b>", # Reply to input message
                   parse_mode=config.PARSE_MODE
             )
    except Exception as e:
        content_logger.warning(f"Failed to confirm proceeding add new anime message for admin {user_id}: {e}")


# Helper called by handle_awaiting_anime_name_input or content_main_menu_callbacks (edit_existing)
async def handle_edit_existing_anime_selection(client: Client, message: Message, user_state: UserState, anime_id_str: str):
     """Starts the management flow for an existing anime after its ID is selected."""
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id # ID of the message to edit


     content_logger.info(f"Admin {user_id} selected existing anime ID {anime_id_str} for editing.")

     # Check for and clear any previous related state (e.g., AWAITING_ANIME_NAME)
     if user_state.handler == "content_management" and user_state.step == ContentState.AWAITING_ANIME_NAME:
         await clear_user_state(user_id)

     # Retrieve the anime document from the database using the ObjectId
     try:
         anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)})
         if not anime_doc:
             content_logger.error(f"Admin {user_id} tried to edit non-existent anime ID: {anime_id_str} after selection.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Selected anime not found in database.", disable_web_page_preview=True)
             # Offer to return to CM main menu?
             await manage_content_command(client, message) # Re-send main CM menu
             return

         # Convert to Pydantic model for safer handling
         anime = Anime(**anime_doc)
         content_logger.info(f"Admin {user_id} is now managing anime '{anime.name}' ({anime.id})")

         # --- Transition to Managing the Specific Anime ---
         # Set the state to managing this specific anime, storing its ID and Name for context in subsequent steps/callbacks
         # State: "content_management":"managing_anime_menu"
         await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(anime.id), "anime_name": anime.name}) # Store ID as string in state data


         # Display the anime details and options to manage seasons, synopsis, etc.
         await display_anime_management_menu(client, message, anime) # Pass the fetched anime model

     except Exception as e:
          content_logger.error(f"Error loading anime ID {anime_id_str} after selection for admin {user_id}: {e}", exc_info=True)
          await edit_or_send_message(client, chat_id, message_id, "💔 Error loading anime details for editing.", disable_web_page_preview=True)
          await clear_user_state(user_id) # Clear state on error

# --- Helper to display the main management menu for a specific Anime ---
# This function is called after adding a new anime or selecting an existing one to edit.
async def display_anime_management_menu(client: Client, message: Message, anime: Anime):
     """Displays the management menu for a specific anime."""
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id # ID of the message to edit

     # We are displaying the menu for state MANAGING_ANIME_MENU.
     # Ensure the user's state reflects this when this function is called *initially*

     menu_text = f"🛠️ <b><u>Managing</u></b> <b>{anime.name}</b> 🛠️\n" # Use title case?
     # Add key details about the anime
     if anime.synopsis:
         menu_text += f"📚 <b><u>Synopsis</u></b>:<blockquote>{anime.synopsis[:300] + '...' if len(anime.synopsis) > 300 else anime.synopsis}</blockquote>\n" # Show snippet with blockquote
     if anime.poster_file_id:
         menu_text += "🖼️ Poster is set.\n"
     menu_text += f"🏷️ <b><u>Genres</u></b>: {', '.join(anime.genres) if anime.genres else 'Not set'}\n"
     menu_text += f"🗓️ <b><u>Release Year</u></b>: {anime.release_year if anime.release_year else 'Not set'}\n"
     menu_text += f"🚦 <b><u>Status</u></b>: {anime.status if anime.status else 'Not set'}\n"
     menu_text += f"🌟 <b><u>Total Seasons Declared</u></b>: {anime.total_seasons_declared}\n"
     # Optional: Show number of seasons actually in the 'seasons' array? len(anime.seasons)
     menu_text += f"📁 Files Uploaded: {sum(len(s.episodes[e_idx].files) for s in anime.seasons for e_idx in range(len(s.episodes)) if s.episodes) if anime.seasons else 0} Versions Total\n" # Count all files across all episodes/seasons

     menu_text += f"\n👇 Select an option to edit details or manage content structure:"

     # Build buttons for managing content for this anime
     buttons = [
         # Button to go to Seasons/Episodes management list (callback: content_manage_seasons|<anime_id>)
         [InlineKeyboardButton(strings.BUTTON_MANAGE_SEASONS_EPISODES, callback_data=f"content_manage_seasons|{anime.id}")],

         # Buttons for editing individual top-level anime fields
         [
            InlineKeyboardButton(strings.BUTTON_EDIT_NAME, callback_data=f"content_edit_name|{anime.id}"),
            InlineKeyboardButton(strings.BUTTON_EDIT_SYNOPSIS, callback_data=f"content_edit_synopsis|{anime.id}")
         ],
         [
            InlineKeyboardButton(strings.BUTTON_EDIT_POSTER, callback_data=f"content_edit_poster|{anime.id}"),
            InlineKeyboardButton(strings.BUTTON_EDIT_GENRES, callback_data=f"content_edit_genres|{anime.id}") # Needs separate genre selection flow
         ],
         [
            InlineKeyboardButton(strings.BUTTON_EDIT_YEAR, callback_data=f"content_edit_year|{anime.id}"),
            InlineKeyboardButton(strings.BUTTON_EDIT_STATUS, callback_data=f"content_edit_status|{anime.id}") # Needs status selection flow
         ],
         # Button to re-prompt total seasons declared - handy if initial count was wrong
         [InlineKeyboardButton(strings.BUTTON_EDIT_TOTAL_SEASONS, callback_data=f"content_edit_total_seasons_count|{anime.id}")],


         # --- Admin Utilities for THIS Anime ---
         # Button to Delete THIS anime (Needs confirmation state!)
         [InlineKeyboardButton("💀 Delete This Anime", callback_data=f"content_delete_anime_prompt|{anime.id}")],


         # --- Navigation Buttons ---
         [InlineKeyboardButton(strings.BUTTON_BACK, callback_data="content_view_all_anime_list")], # Go back to full admin list (Needs implementation)
         [InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")], # Back to main CM menu
         [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")], # Back to main user menu
     ]
     reply_markup = InlineKeyboardMarkup(buttons)

     # Edit the current message to display the anime management menu
     await edit_or_send_message(
          client,
          chat_id,
          message_id, # Edit the message that triggered this (callback message)
          menu_text,
          reply_markup,
          disable_web_page_preview=True # Ensure links in synopsis or poster link (if added) are not auto-previewed big.
      )


# --- Implementations for specific ADD NEW ANIME steps (Text Input) ---

# Called by handle_content_input when state is AWAITING_POSTER
async def handle_awaiting_poster(client: Client, message: Message, user_state: UserState):
    """Handles admin media input when in AWAITING_POSTER state (expects photo). Called by common_handlers.handle_media_input."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    # This function is called BY handle_media_input *after* checking if message contains a photo
    # So, message.photo should be True here.

    # Get the highest quality version's file_id
    file_id = message.photo[-1].file_id
    # Also capture file_unique_id and size, potentially name? Telegram photo doesn't have name directly.
    # file_unique_id = message.photo[-1].file_unique_id
    # file_size = message.photo[-1].file_size

    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")) # Get name from state (new add or edit purpose)
    purpose = user_state.data.get("purpose", "add") # Get the purpose (add or edit) from state data

    content_logger.info(f"Admin {user_id} provided poster photo ({file_id}) for '{anime_name}' in AWAITING_POSTER state (Purpose: {purpose}).")


    if purpose == "add":
        # We are in the Add New Anime flow, coming from AWAITING_ANIME_NAME or proceed_add_new callback.
        # Store the poster_file_id in state data for later document creation.
        user_state.data["poster_file_id"] = file_id

        # Move to the next step: AWAITING_SYNOPSIS
        await set_user_state(user_id, "content_management", ContentState.AWAITING_SYNOPSIS, data=user_state.data)

        # Prompt for synopsis.
        # Reply to the photo message received.
        await message.reply_text(
             f"🖼️ Poster received! Now send the **<u>Synopsis</u>** for this anime ({anime_name}).",
             parse_mode=config.PARSE_MODE,
             reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
         )
        # No need to edit the previous prompt message explicitly, sending a new message is confirmation + prompt


    elif purpose == "edit":
         # We are in the Edit Existing Anime flow, coming from clicking "Edit Poster" callback in anime management menu.
         anime_id_str = user_state.data.get("anime_id")

         if not anime_id_str:
             content_logger.error(f"Admin {user_id} in EDIT purpose AWAITING_POSTER state but missing anime_id in state data.")
             await message.reply_text("💔 Error: Anime ID missing from state data for poster edit. Process cancelled.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); # Clear state
             # Offer to restart CM flow? Or just clear? Clear and rely on user returning is simple.
             return

         # Update the EXISTING anime document's poster_file_id in the database.
         try:
             update_result = await MongoDB.anime_collection().update_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"$set": {"poster_file_id": file_id, "last_updated_at": datetime.now(timezone.utc)}}
             )

             if update_result.matched_count > 0 and update_result.modified_count > 0:
                  content_logger.info(f"Admin {user_id} successfully updated poster for anime {anime_id_str}.")
                  await message.reply_text("✅ Poster updated!", parse_mode=config.PARSE_MODE)

                  # Fetch the updated anime document to display the management menu.
                  updated_anime = await MongoDB.get_anime_by_id(anime_id_str) # Use helper
                  if updated_anime:
                       # Transition state back to managing this specific anime
                       await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                       # Display the anime management menu
                       await display_anime_management_menu(client, message, updated_anime)
                  else:
                       content_logger.error(f"Failed to fetch updated anime {anime_id_str} after poster update for admin {user_id}. Cannot display menu.")
                       await message.reply_text("💔 Updated poster, but failed to load the management menu. Please navigate back to the Anime Menu.", parse_mode=config.PARSE_MODE)
                       # State is still AWAITING_POSTER edit. Need to route admin back.
                       # Re-displaying main CM menu is safest if we cannot guarantee return to specific anime menu.
                       await manage_content_command(client, message) # Re-send CM main menu

             else:
                 # Matched count > 0 but modified_count == 0 - likely same file was sent again
                 content_logger.info(f"Admin {user_id} sent poster for {anime_id_str} but it was unchanged (modified_count=0).")
                 await message.reply_text("✅ Poster appears unchanged. No update needed.", parse_mode=config.PARSE_MODE)
                 # Re-fetch and re-display the anime management menu as if update happened to show current state.
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     # Clear AWAITING_POSTER edit state, return to managing menu state
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                     content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change poster edit for admin {user_id}.")
                     await message.reply_text("🔄 No change made. Failed to load the management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                     await manage_content_command(client, message)


         except Exception as e:
              content_logger.error(f"Error updating poster for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
              await message.reply_text("💔 Error updating poster.", parse_mode=config.PARSE_MODE)
              # State is EDITING_POSTER_PROMPT. User can retry sending photo or type cancel.


    else:
         # Should not happen - AWAITING_POSTER state with unexpected purpose.
         content_logger.error(f"Admin {user_id} in AWAITING_POSTER state with invalid purpose in state data: {purpose}. State data: {user_state.data}")
         await message.reply_text("🤷 Unexpected data in state. Your process was cancelled.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id) # Clear broken state


# Called by handle_content_input when state is AWAITING_SYNOPSIS or EDITING_SYNOPSIS_PROMPT
async def handle_awaiting_synopsis_input(client: Client, message: Message, user_state: UserState, synopsis_text: str):
    """Handles admin text input when in AWAITING_SYNOPSIS state."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_step = user_state.step # Should be AWAITING_SYNOPSIS or EDITING_SYNOPSIS_PROMPT

    # Get context (anime name, ID) from state data
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")) # Name can come from add or edit flow
    anime_id_str = user_state.data.get("anime_id") # Only available in edit flow

    content_logger.info(f"Admin {user_id} provided synopsis text (step {current_step}) for '{anime_name}': '{synopsis_text[:100]}...'")

    # You might want to validate synopsis length, content etc.

    if current_step == ContentState.AWAITING_SYNOPSIS:
        # Add New Anime flow
        # Store synopsis in state data
        user_state.data["synopsis"] = synopsis_text

        # Move to the next step: AWAITING_TOTAL_SEASONS_COUNT
        await set_user_state(user_id, "content_management", ContentState.AWAITING_TOTAL_SEASONS_COUNT, data=user_state.data)

        # Prompt for total seasons count
        await prompt_for_total_seasons_count(client, chat_id, anime_name)

        # Confirm reception of synopsis
        await message.reply_text(f"📝 Synopsis received. Now send the **<u>Total Number of Seasons</u>** for {anime_name}.", parse_mode=config.PARSE_MODE)


    elif current_step == ContentState.EDITING_SYNOPSIS_PROMPT:
        # Edit Existing Anime flow
        if not anime_id_str:
            content_logger.error(f"Admin {user_id} in EDITING_SYNOPSIS_PROMPT state but missing anime_id in state data.")
            await message.reply_text("💔 Error: Anime ID missing from state data for synopsis edit. Process cancelled.", parse_mode=config.PARSE_MODE)
            await clear_user_state(user_id); return

        # Update the EXISTING anime document's synopsis in the database
        try:
            update_result = await MongoDB.anime_collection().update_one(
                {"_id": ObjectId(anime_id_str)},
                {"$set": {"synopsis": synopsis_text, "last_updated_at": datetime.now(timezone.utc)}}
            )

            if update_result.matched_count > 0 and update_result.modified_count > 0:
                content_logger.info(f"Admin {user_id} successfully updated synopsis for anime {anime_id_str}.")
                await message.reply_text("✅ Synopsis updated!", parse_mode=config.PARSE_MODE)

                # Fetch updated anime and return to management menu
                updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                if updated_anime:
                    # Clear EDITING_SYNOPSIS_PROMPT state, set state back to managing
                    await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                    await display_anime_management_menu(client, message, updated_anime) # Use updated anime

                else:
                    content_logger.error(f"Failed to fetch updated anime {anime_id_str} after synopsis update for admin {user_id}.")
                    await message.reply_text("💔 Updated synopsis, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                    await manage_content_command(client, message) # Go to CM main menu

            elif update_result.matched_count > 0: # Modified count is 0 - same synopsis sent
                 content_logger.info(f"Admin {user_id} sent synopsis for {anime_id_str} but it was unchanged (modified_count=0).")
                 await message.reply_text("✅ Synopsis appears unchanged. No update needed.", parse_mode=config.PARSE_MODE)
                 # Fetch current anime and re-display management menu
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change synopsis edit for admin {user_id}.")
                      await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)


        except Exception as e:
             content_logger.error(f"Error updating synopsis for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
             await message.reply_text("💔 Error updating synopsis.", parse_mode=config.PARSE_MODE)
             # State remains EDITING_SYNOPSIS_PROMPT, admin can retry text or cancel.


    else:
        # Should not happen - unexpected step reaching this handler function
        content_logger.error(f"Admin {user_id} sent synopsis input in unexpected state {current_step}.")
        await message.reply_text("🤷 Unexpected state data for this step. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)


# Called by handle_awaiting_synopsis_input
async def prompt_for_total_seasons_count(client: Client, chat_id: int, anime_name: str):
    """Sends the prompt to the admin to provide the total seasons count (Add New flow)."""
    prompt_text = strings.ADD_ANIME_SEASONS_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([
         [InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]
    ])
    try:
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send total seasons count prompt to chat {chat_id}: {e}", exc_info=True)


# Called by handle_content_input when state is AWAITING_TOTAL_SEASONS_COUNT or EDITING_TOTAL_SEASONS_COUNT_PROMPT
async def handle_awaiting_total_seasons_count_input(client: Client, message: Message, user_state: UserState, count_text: str):
    """Handles admin text input when in AWAITING_TOTAL_SEASONS_COUNT or EDITING_TOTAL_SEASONS_COUNT_PROMPT state (expects a number)."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_step = user_state.step # Should be AWAITING_TOTAL_SEASONS_COUNT or EDITING_TOTAL_SEASONS_COUNT_PROMPT

    # Get context (anime name, ID) from state data
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")) # Name from add or edit flow
    anime_id_str = user_state.data.get("anime_id") # Only available in edit flow

    content_logger.info(f"Admin {user_id} provided seasons count input ({count_text}) for '{anime_name}' at step {current_step}.")


    # Validate if the input is a non-negative integer
    try:
        seasons_count = int(count_text)
        if seasons_count < 0:
             raise ValueError("Negative count not allowed") # Handled in except block

    except ValueError:
        # Input was not a valid non-negative integer
        await message.reply_text("🚫 Please send a valid **<u>non-negative number</u>** for the total seasons count, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        # State remains the same, user needs to try again or cancel.
        return # Stop processing input if invalid format

    # Input is valid integer, proceed based on current step (Add New vs Edit)
    if current_step == ContentState.AWAITING_TOTAL_SEASONS_COUNT:
        # Add New Anime flow (coming from AWAITING_SYNOPSIS)
        # Store the count in state data for later document creation
        user_state.data["total_seasons_declared"] = seasons_count

        # Move to the next step: SELECTING_GENRES
        await set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data=user_state.data)

        # Prompt for genre selection (Callback-based multi-select)
        await prompt_for_genres(client, chat_id, anime_name, user_state.data.get("selected_genres", [])) # Pass potentially existing selection from state (though unlikely in this add flow step)

        # Confirm reception and prompt for next step
        await message.reply_text(f"📺 Total seasons (<b>{seasons_count}</b>) received. Now select the **<u>Genres</u>** for {anime_name}.", parse_mode=config.PARSE_MODE)


    elif current_step == ContentState.EDITING_TOTAL_SEASONS_COUNT_PROMPT:
        # Edit Existing Anime flow (coming from content_edit_total_seasons_count callback)
        if not anime_id_str:
             content_logger.error(f"Admin {user_id} in EDITING_TOTAL_SEASONS_COUNT_PROMPT state but missing anime_id.")
             await message.reply_text("💔 Error: Anime ID missing from state data for seasons count edit. Process cancelled.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return


        # Update the EXISTING anime document's total_seasons_declared count in the database.
        try:
            update_result = await MongoDB.anime_collection().update_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"$set": {"total_seasons_declared": seasons_count, "last_updated_at": datetime.now(timezone.utc)}}
             )

            if update_result.matched_count > 0 and update_result.modified_count > 0:
                 content_logger.info(f"Admin {user_id} successfully updated total_seasons_declared for anime {anime_id_str} to {seasons_count}.")
                 await message.reply_text(f"✅ Total seasons updated to **__{seasons_count}__**!", parse_mode=config.PARSE_MODE)

                 # Fetch updated anime and return to management menu
                 updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if updated_anime:
                     # Clear EDITING_TOTAL_SEASONS_COUNT_PROMPT state, set state back to managing
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                     await display_anime_management_menu(client, message, updated_anime) # Use updated anime
                 else:
                      content_logger.error(f"Failed to fetch updated anime {anime_id_str} after seasons count update for admin {user_id}.")
                      await message.reply_text("💔 Updated total seasons, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message) # Go to CM main menu


            elif update_result.matched_count > 0: # Modified count is 0 - same count sent
                 content_logger.info(f"Admin {user_id} sent total seasons count for {anime_id_str} but it was unchanged (modified_count=0).")
                 await message.reply_text(f"✅ Total seasons count is already <b>{seasons_count}</b>. No update needed.", parse_mode=config.PARSE_MODE)
                 # Fetch current anime and re-display management menu
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change seasons count edit for admin {user_id}.")
                      await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)


        except Exception as e:
            content_logger.error(f"Error updating total seasons count for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
            await message.reply_text("💔 Error updating total seasons count.", parse_mode=config.PARSE_MODE)
            # State is EDITING_TOTAL_SEASONS_COUNT_PROMPT. Admin can retry text or cancel.


    else:
        # Should not happen - unexpected step reaching this handler function
        content_logger.error(f"Admin {user_id} sent seasons count input in unexpected state {current_step}.")
        await message.reply_text("🤷 Unexpected state data for this step. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)


# Called by handle_awaiting_total_seasons_count_input
async def prompt_for_genres(client: Client, chat_id: int, anime_name: str, current_selection: List[str]):
    """Sends the prompt and buttons for admin to select genres."""
    # Ensure current_selection is passed from state data for multi-select update
    prompt_text = strings.ADD_ANIME_GENRES_PROMPT.format(anime_name=anime_name)
    genres_presets = config.INITIAL_GENRES # Use the preset genres from config

    buttons = []
    # Create genre buttons with multi-select state indicated
    for genre in genres_presets:
        # Use ✅ or ❌ style to indicate if the genre is selected in the current state data (passed in current_selection)
        is_selected = genre in current_selection
        # Use different emojis or styles for clarity. 🟩 (green square) or ✅ (check) for selected, ⬜ (white square) for unselected
        button_text = f"✅ {genre}" if is_selected else f"⬜ {genre}" # Use emoji to clearly show state
        # Callback data format: content_toggle_genre|<genre_name> (standardized callback type)
        # Callback should include anime_id? No, anime_id should be in state data.
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}{genre}")) # Use separator


    # Arrange buttons into rows based on configured MAX_BUTTONS_PER_ROW
    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    # Add Done and Cancel buttons in the last row
    # Done button callback: content_genres_done
    # Cancel button callback: content_cancel (universal)
    keyboard_rows.append([
        InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Genres"), callback_data="content_genres_done"),
        InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        # Send as a new message. The previous prompt message stays.
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True # Good practice for messages with buttons
         )
    except Exception as e:
        content_logger.error(f"Failed to send genres selection prompt to chat {chat_id}: {e}", exc_info=True)

# --- Callback Handlers for Selection (e.g., Genres, Status, Metadata) ---
# These handle button clicks that change state data but might keep the user in the same state type (e.g., toggling genre selections)

# Handler for genre selection callback buttons
# Catches callbacks starting with 'content_toggle_genre|'
@Client.on_callback_query(filters.regex(f"^content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def content_toggle_genre_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin toggling genre selection via buttons."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # ID of the message containing the buttons
    data = callback_query.data # Format: content_toggle_genre|genre_name

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    # Acknowledge the callback query immediately
    try: await callback_query.answer() # Silent acknowledgement (toast notification on some clients)
    except Exception: content_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")


    user_state = await get_user_state(user_id)

    # Check if user is in the correct state expecting genre selection
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_GENRES):
        content_logger.warning(f"Admin {user_id} clicked genre toggle callback {data} but state is {user_state.handler}:{user_state.step if user_state else 'None'}.")
        # Re-prompt with the genre selection menu based on their actual state if it was just wrong step but correct handler?
        # For now, simple approach: inform invalid state and clear.
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting genres. Please restart the process.", disable_web_page_preview=True)
        await clear_user_state(user_id)
        # Offer to restart CM flow or just return to main menu? Returning to main CM menu is user-friendly.
        await manage_content_command(client, callback_query.message) # Pass message to re-send menu command logic
        return


    try:
        # Parse the genre name from the callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2:
             raise ValueError("Invalid callback data format for toggling genre.")
        genre_to_toggle = parts[1]

        # Get currently selected genres from state data, initialize if 'selected_genres' key is missing
        # The data dictionary in UserState holds temporary info for this flow.
        # Access the nested dict holding selection states or temporary metadata
        temp_metadata = user_state.data.get("temp_metadata", {}) # Use 'temp_metadata' to group file/selection details? Or just use 'selected_genres' directly at top level of data. Let's use 'selected_genres' for simplicity here.
        # No, selected_genres should be directly in state.data for Genres/Status selection,
        # temp_metadata for File Metadata flow.
        selected_genres = user_state.data.get("selected_genres", [])


        # Ensure the genre to toggle is one of the allowed presets as a basic sanity check
        # Or allow adding new genres via admin UI? Assuming only preset selection for now.
        if genre_to_toggle not in config.INITIAL_GENRES:
             content_logger.warning(f"Admin {user_id} attempted to toggle non-preset genre: {genre_to_toggle}.")
             # Inform admin it's an invalid option
             await callback_query.answer("🚫 Invalid genre option.", show_alert=False) # Use toast
             # Don't modify state, just ignore the invalid click
             return


        # Toggle the genre in the list
        if genre_to_toggle in selected_genres:
            selected_genres.remove(genre_to_toggle)
            content_logger.debug(f"Admin {user_id} unselected genre: {genre_to_toggle}")
        else:
             selected_genres.append(genre_to_toggle)
             content_logger.debug(f"Admin {user_id} selected genre: {genre_to_toggle}")

        # Sort selected genres for consistency in storage and display (optional)
        selected_genres.sort()

        # Update the selected genres in the user's state data.
        # This saves the state back to the database after each toggle.
        user_state.data["selected_genres"] = selected_genres
        # Re-set the entire state object with the updated data dictionary.
        # The user is staying in the same SELECTING_GENRES step.
        await set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data=user_state.data)


        # Re-create the genre selection keyboard to reflect the updated selection states (emojis on buttons)
        # Re-fetch the original genre presets from config
        genres_presets = config.INITIAL_GENRES
        buttons = []
        for genre in genres_presets:
            is_selected = genre in selected_genres # Check against the *updated* selected_genres list
            # Use different emojis to clearly show selection status
            button_text = f"✅ {genre}" if is_selected else f"⬜ {genre}"
            # The callback data remains the same
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}{genre}"))

        # Arrange buttons into rows
        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

        # Add Done and Cancel buttons
        keyboard_rows.append([
             InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Genres"), callback_data="content_genres_done"),
             InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        # Edit *only* the reply markup of the message to update button states.
        # This avoids sending edit messages if the text hasn't changed.
        try:
             await callback_query.message.edit_reply_markup(reply_markup=reply_markup)
        except MessageNotModified:
            # Ignore if the user clicked a button multiple times without the selection state changing (e.g., clicking already selected button before update)
            common_logger.debug(f"Admin {user_id} clicked genre toggle, but message reply_markup was unchanged.")
            pass
        except FloodWait as e:
            # Telegram API limits - wait and try to edit again.
            content_logger.warning(f"FloodWait while editing genre buttons for admin {user_id} (retry in {e.value}s): {e}")
            await asyncio.sleep(e.value)
            try:
                # Retry editing the reply markup after the flood wait
                await callback_query.message.edit_reply_markup(reply_markup=reply_markup)
            except Exception as retry_e:
                 # Log failure even after retry
                 content_logger.error(f"Retry after FloodWait failed editing genre buttons for admin {user_id}: {retry_e}", exc_info=True)

    except Exception as e:
         # Catch any errors during callback processing (parsing, state access, DB save, etc.)
         content_logger.error(f"Error handling content_toggle_genre callback {data} for admin {user_id}: {e}", exc_info=True)
         # Don't necessarily clear state, the user might retry clicking valid buttons.
         # But if it's a persistent DB error or state data issue, clearing state might be necessary.
         # For now, just log and maybe answer with generic error alert if answer wasn't sent yet.
         try:
              await callback_query.answer(strings.ERROR_OCCURRED, show_alert=True)
         except Exception: common_logger.warning(f"Failed to answer callback error alert for admin {user_id}, data {data}.")

# Handler for the "Done Selecting Genres" button
@Client.on_callback_query(filters.regex("^content_genres_done$") & filters.private)
async def content_genres_done_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Done after selecting genres."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    # Acknowledge immediately
    try: await callback_query.answer("Genres selected. Proceeding...") # Toast indicating done
    except Exception: common_logger.warning(f"Failed to answer callback query content_genres_done from admin {user_id}.")


    user_state = await get_user_state(user_id)

    # Check if user is in the correct state
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_GENRES):
        content_logger.warning(f"Admin {user_id} clicked Done Genres but state is {user_state.handler}:{user_state.step if user_state else 'None'}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Your previous process was cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id)
        await manage_content_command(client, callback_query.message) # Offer to restart CM flow
        return

    # Retrieve selected genres from state data
    selected_genres = user_state.data.get("selected_genres", [])
    # Get context (anime name, ID) from state data
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")) # Name from add or edit flow
    anime_id_str = user_state.data.get("anime_id") # Only available in edit flow
    purpose = user_state.data.get("purpose", "add") # Purpose from add/edit flow

    content_logger.info(f"Admin {user_id} finished selecting genres ({purpose} purpose) for '{anime_name}': {selected_genres}")

    # --- Proceed based on purpose (Add New vs Edit Existing) ---
    if purpose == "add":
        # Add New Anime flow - Store genres in state data and proceed to the next step.
        user_state.data["genres"] = selected_genres # Store under 'genres' key for Anime model

        # Move to the next step: AWAITING_RELEASE_YEAR
        await set_user_state(user_id, "content_management", ContentState.AWAITING_RELEASE_YEAR, data=user_state.data)

        # Prompt for release year (Text input step)
        await prompt_for_release_year(client, chat_id, anime_name)

        # Edit the message to confirm genre selection completion and prompt for next step
        try:
            await callback_query.message.edit_text(
                 f"🏷️ Genres saved: {', '.join(selected_genres) if selected_genres else 'None'}.\n\n🗓️ Now send the **<u>Release Year</u>** for {anime_name}.",
                 parse_mode=config.PARSE_MODE
             )
        except Exception as e:
             # If edit fails, send as a new message
             content_logger.warning(f"Failed to edit message after genres done (add flow) for admin {user_id}: {e}")
             await client.send_message(chat_id, f"✅ Genres saved. Please send the **<u>Release Year</u>** for {anime_name}.", parse_mode=config.PARSE_MODE)


    elif purpose == "edit":
        # Edit Existing Anime flow - Update the EXISTING anime document in the database
        if not anime_id_str:
             content_logger.error(f"Admin {user_id} in SELECTING_GENRES (edit) state but missing anime_id in state data.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime ID missing from state data for genre edit. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return

        try:
            update_result = await MongoDB.anime_collection().update_one(
                {"_id": ObjectId(anime_id_str)},
                {"$set": {"genres": selected_genres, "last_updated_at": datetime.now(timezone.utc)}}
            )

            if update_result.matched_count > 0 and update_result.modified_count > 0:
                 content_logger.info(f"Admin {user_id} successfully updated genres for anime {anime_id_str}.")
                 await callback_query.message.edit_text(f"✅ Genres updated to: {', '.join(selected_genres) if selected_genres else 'None'}!", parse_mode=config.PARSE_MODE)

                 # Fetch updated anime and return to management menu
                 updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if updated_anime:
                     # Clear SELECTING_GENRES edit state, set state back to managing
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                     # Delay slightly before displaying the next menu to give user time to see the confirmation message
                     await asyncio.sleep(1) # Short delay
                     await display_anime_management_menu(client, callback_query.message, updated_anime) # Use the message from the callback

                 else:
                     content_logger.error(f"Failed to fetch updated anime {anime_id_str} after genre update for admin {user_id}.")
                     await client.send_message(chat_id, "💔 Updated genres, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                     await manage_content_command(client, callback_query.message) # Go to CM main menu

            elif update_result.matched_count > 0: # Modified count is 0 - same genres selected
                 content_logger.info(f"Admin {user_id} sent genres for {anime_id_str} but it was unchanged (modified_count=0).")
                 await callback_query.message.edit_text("✅ Genres appear unchanged. No update needed.", parse_mode=config.PARSE_MODE)
                 # Fetch current anime and re-display management menu
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                      # Clear SELECTING_GENRES edit state, set state back to managing
                      await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                      await asyncio.sleep(1) # Short delay
                      await display_anime_management_menu(client, callback_query.message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change genre edit for admin {user_id}.")
                      await client.send_message(chat_id, "🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, callback_query.message)


        except Exception as e:
             content_logger.error(f"Error updating genres for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
             await client.send_message(chat_id, "💔 Error updating genres.", parse_mode=config.PARSE_MODE)
             # State is SELECTING_GENRES. Clear it as it implies a complex update failed.
             await clear_user_state(user_id)


    else:
        # Should not happen - unexpected purpose in state data
        content_logger.error(f"Admin {user_id} finished genre selection with invalid purpose in state data: {purpose}. State data: {user_state.data}")
        await edit_or_send_message(client, chat_id, message_id, "🤷 Unexpected data in state. Your process was cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id)


# Called by handle_awaiting_total_seasons_count_input
async def prompt_for_release_year(client: Client, chat_id: int, anime_name: str):
    """Sends the prompt to the admin to provide the release year."""
    prompt_text = strings.ADD_ANIME_YEAR_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([
         [InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]
    ])
    try:
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send release year prompt to chat {chat_id}: {e}", exc_info=True)


# Called by handle_content_input when state is AWAITING_RELEASE_YEAR or EDITING_RELEASE_YEAR_PROMPT
async def handle_awaiting_release_year_input(client: Client, message: Message, user_state: UserState, year_text: str):
    """Handles admin text input when in AWAITING_RELEASE_YEAR or EDITING_RELEASE_YEAR_PROMPT state (expects a number)."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_step = user_state.step # AWAITING_RELEASE_YEAR or EDITING_RELEASE_YEAR_PROMPT

    # Get context (anime name, ID)
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime"))
    anime_id_str = user_state.data.get("anime_id")

    content_logger.info(f"Admin {user_id} provided release year input ({year_text}) for '{anime_name}' at step {current_step}.")


    # Validate and parse the year input (expects a number, maybe within range)
    try:
        release_year = int(year_text)
        # Optional range check
        # if not (1850 <= release_year <= datetime.now().year + 5): # Simple reasonable range
        #     raise ValueError("Year out of typical anime range")

    except ValueError:
        # Input was not a valid integer or within range (if range check added)
        await message.reply_text("🚫 Please send a valid **<u>year</u>** (e.g., 2024), or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        # State remains the same, user needs to try again or cancel.
        return # Stop processing if invalid format

    # Input is valid integer year, proceed based on current step (Add New vs Edit)
    if current_step == ContentState.AWAITING_RELEASE_YEAR:
        # Add New Anime flow (coming from SELECTING_GENRES)
        # Store the year in state data
        user_state.data["release_year"] = release_year

        # Move to the next step: SELECTING_STATUS
        await set_user_state(user_id, "content_management", ContentState.SELECTING_STATUS, data=user_state.data)

        # Prompt for status selection (Callback-based single-select)
        await prompt_for_status(client, chat_id, anime_name)

        # Confirm reception and prompt for next step
        await message.reply_text(f"🗓️ Release year (<b>{release_year}</b>) saved. Now select the **<u>Status</u>** for {anime_name}.", parse_mode=config.PARSE_MODE)


    elif current_step == ContentState.EDITING_RELEASE_YEAR_PROMPT:
         # Edit Existing Anime flow (coming from content_edit_year callback)
        if not anime_id_str:
             content_logger.error(f"Admin {user_id} in EDITING_RELEASE_YEAR_PROMPT state but missing anime_id.")
             await message.reply_text("💔 Error: Anime ID missing from state data for year edit. Process cancelled.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return

        # Update the EXISTING anime document's release_year in the database.
        try:
            update_result = await MongoDB.anime_collection().update_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"$set": {"release_year": release_year, "last_updated_at": datetime.now(timezone.utc)}}
             )

            if update_result.matched_count > 0 and update_result.modified_count > 0:
                 content_logger.info(f"Admin {user_id} successfully updated release year for anime {anime_id_str} to {release_year}.")
                 await message.reply_text(f"✅ Release year updated to **__{release_year}__**!", parse_mode=config.PARSE_MODE)

                 # Fetch updated anime and return to management menu
                 updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if updated_anime:
                      # Clear EDITING_RELEASE_YEAR_PROMPT state, set state back to managing
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                     await asyncio.sleep(1) # Short delay
                     await display_anime_management_menu(client, message, updated_anime) # Use updated anime
                 else:
                      content_logger.error(f"Failed to fetch updated anime {anime_id_str} after year update for admin {user_id}.")
                      await message.reply_text("💔 Updated release year, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message) # Go to CM main menu

            elif update_result.matched_count > 0: # Modified count is 0 - same year sent
                 content_logger.info(f"Admin {user_id} sent release year for {anime_id_str} but it was unchanged (modified_count=0).")
                 await message.reply_text(f"✅ Release year is already <b>{release_year}</b>. No update needed.", parse_mode=config.PARSE_MODE)
                 # Fetch current anime and re-display management menu
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await asyncio.sleep(1) # Short delay
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                     content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change year edit for admin {user_id}.")
                     await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                     await manage_content_command(client, message)


        except Exception as e:
            content_logger.error(f"Error updating release year for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
            await message.reply_text("💔 Error updating release year.", parse_mode=config.PARSE_MODE)
            # State is EDITING_RELEASE_YEAR_PROMPT. Admin can retry text or cancel.


    else:
        # Should not happen - unexpected step reaching this handler function
        content_logger.error(f"Admin {user_id} sent year input in unexpected state {current_step}.")
        await message.reply_text("🤷 Unexpected state data for this step. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)


# Called by handle_awaiting_release_year_input or handle_editing_status_callback
async def prompt_for_status(client: Client, chat_id: int, anime_name: str, current_selection: Optional[str] = None):
    """Sends the prompt and buttons for admin to select status."""
    prompt_text = strings.ADD_ANIME_STATUS_PROMPT.format(anime_name=anime_name)
    status_presets = config.ANIME_STATUSES # Use presets

    buttons = []
    # Status is single-select. Maybe highlight the currently selected one if editing.
    # Or simply present the options, the selection handler updates DB/state and moves on.
    for status in status_presets:
         # Callback data format: content_select_status|<status_name> (standardized callback type)
         # Could indicate current selection if editing?
         button_text = f"✅ {status}" if current_selection and status == current_selection else status
         buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_select_status{config.CALLBACK_DATA_SEPARATOR}{status}"))

    # Arrange buttons (potentially just one row if few statuses)
    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    # Add Cancel button
    keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        # Send as a new message in add flow. Edit in edit flow.
        # Check if state purpose is 'edit'. If so, message_id should be available.
        user_state = await get_user_state(client.me.id, user_id) # Need user_id context from state to check purpose/msg_id? No, state not updated yet when calling prompt.
        # Simpler: have separate prompt functions or pass message_id if editing?
        # Let's always send as a new message from here, unless it's editing from an inline menu action.
        # Callback content_edit_status needs to call a specific prompt function or handle editing the prompt itself.

        await client.send_message( # Send NEW message
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True
         )
    except Exception as e:
        content_logger.error(f"Failed to send status selection prompt to chat {chat_id}: {e}", exc_info=True)


# Handler for status selection callback buttons
# Catches callbacks starting with 'content_select_status|'
@Client.on_callback_query(filters.regex(f"^content_select_status{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def content_select_status_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting anime status via buttons."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # Format: content_select_status|status_name

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    # Acknowledge immediately
    try: await callback_query.answer()
    except Exception: content_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")


    user_state = await get_user_state(user_id)

    # Check if user is in the correct state
    # This callback can be used for *adding* anime (from AWAITING_RELEASE_YEAR state)
    # OR for *editing* anime status (from EDITING_STATUS_SELECTING or similar state, where anime_id is in state data)
    # Let's assume state should be SELECTING_STATUS for Add flow OR a specific state for Edit flow.
    # Let's simplify: State is SELECTING_STATUS for both, but check purpose/context in state data.
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_STATUS):
        content_logger.warning(f"Admin {user_id} clicked status select callback {data} but state is {user_state.handler}:{user_state.step if user_state else 'None'}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting status. Please restart the process.", disable_web_page_preview=True)
        await clear_user_state(user_id); return # Offer to restart CM flow
        await manage_content_command(client, callback_query.message) # Use message from callback to re-send CM menu


    try:
        # Parse the selected status
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2:
             raise ValueError("Invalid callback data format for selecting status.")
        selected_status = parts[1]

        # Validate if the selected status is one of the allowed presets (sanity check)
        if selected_status not in config.ANIME_STATUSES:
             content_logger.warning(f"Admin {user_id} attempted to select non-preset status: {selected_status}.")
             await callback_query.answer("🚫 Invalid status option.", show_alert=False) # Toast
             # Don't modify state, just ignore invalid click. Re-edit menu below might fail.
             # Re-display status selection menu
             await prompt_for_status(client, chat_id, user_state.data.get("anime_name", "Anime"), user_state.data.get("status")) # Pass current name and selection (if edit)
             # This could cause a FloodWait if done too fast after answer() or initial edit.

             # Better: just rely on re-editing reply_markup with highlighting. No, that's multi-select logic.
             # For single select: accept, save, move on. If invalid value, inform user.
             await edit_or_send_message(
                 client,
                 chat_id,
                 message_id,
                 f"🚫 Invalid status option selected: {selected_status}.",
                 disable_web_page_preview=True
             )
             return # Stop processing


        # Store the selected status in user's state data.
        user_state.data["status"] = selected_status

        # Get context (anime name, ID, purpose)
        anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime"))
        anime_id_str = user_state.data.get("anime_id") # Only for edit purpose
        purpose = user_state.data.get("purpose", "add")


        content_logger.info(f"Admin {user_id} selected status '{selected_status}' ({purpose} purpose) for '{anime_name}'.")

        # --- Proceed based on purpose (Add New vs Edit Existing) ---
        if purpose == "add":
            # Add New Anime flow (coming from AWAITING_RELEASE_YEAR). All required data should be in state.data.
            # --- Create and Insert the New Anime Document into Database ---
            # Collect all the data stored in state.data:
            # - name (from new_anime_name)
            # - poster_file_id (optional, from poster_file_id)
            # - synopsis (from synopsis)
            # - total_seasons_declared (from total_seasons_declared)
            # - genres (from genres)
            # - release_year (from release_year)
            # - status (from status - just selected)

            # Build the dictionary for the new anime document
            new_anime_data_dict = {
                 "name": user_state.data.get("new_anime_name"),
                 "poster_file_id": user_state.data.get("poster_file_id"), # Optional, can be None
                 "synopsis": user_state.data.get("synopsis"),
                 "total_seasons_declared": user_state.data.get("total_seasons_declared", 0), # Default to 0 if somehow missing
                 "genres": user_state.data.get("genres", []), # Default to empty list
                 "release_year": user_state.data.get("release_year"), # Optional
                 "status": user_state.data.get("status"), # Should be set by now
                 "seasons": [], # Start with empty seasons array, managed later
                 "overall_download_count": 0, # Initial count is 0
                 "last_updated_at": datetime.now(timezone.utc) # Set initial update timestamp
            }
            # Ensure name and status are actually present as minimum required fields
            if not new_anime_data_dict.get("name") or not new_anime_data_dict.get("status"):
                content_logger.error(f"Admin {user_id} finished add flow, but missing name or status in state data! Data: {user_state.data}")
                await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing critical data to create anime. Process cancelled.", disable_web_page_preview=True)
                await clear_user_state(user_id); return


            # Use Pydantic model to validate data structure before inserting (good practice)
            try:
                new_anime = Anime(**new_anime_data_dict)
            except Exception as e:
                content_logger.error(f"Error validating Anime model from state data for admin {user_id}: {e}. Data: {new_anime_data_dict}", exc_info=True)
                await edit_or_send_message(client, chat_id, message_id, "💔 Error validating anime data structure. Process cancelled.", disable_web_page_preview=True)
                await clear_user_state(user_id); return

            # Insert the new anime document into the database
            try:
                insert_result = await MongoDB.anime_collection().insert_one(new_anime.dict(by_alias=True, exclude_none=True))
                new_anime_id = insert_result.inserted_id # Get the generated _id
                content_logger.info(f"Successfully added new anime '{new_anime.name}' (ID: {new_anime_id}) by admin {user_id}.")

                # --- Transition to Managing the Newly Created Anime ---
                # Clear the multi-step ADD NEW state and set state to managing THIS anime.
                # Store the new anime's ID and Name in the state data for the management menu context.
                await set_user_state(
                     user_id,
                     "content_management",
                     ContentState.MANAGING_ANIME_MENU, # State is now managing a specific anime
                     data={"anime_id": str(new_anime_id), "anime_name": new_anime.name} # Store ID as string in state data
                 )

                # Confirm addition and display the anime management menu for the new anime.
                await edit_or_send_message(
                     client,
                     chat_id,
                     message_id,
                     f"🎉 Anime <b><u>{new_anime.name}</u></b> added successfully! 🎉\nYou can now add seasons and episodes. 👇",
                     disable_web_page_preview=True # Edit the message
                 )
                # Delay slightly before displaying the menu message to allow the confirmation to be seen.
                await asyncio.sleep(1) # Short delay


                # Fetch the newly created anime again (safer than relying on in-memory model potentially missing fields set by DB)
                created_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(new_anime_id)})
                if created_anime_doc:
                    created_anime = Anime(**created_anime_doc)
                    # Now display the main management menu for this specific anime
                    await display_anime_management_menu(client, callback_query.message, created_anime) # Pass message from callback for editing

                else:
                     # Failed to re-fetch the newly created anime. This is a logic error or immediate DB issue after insert.
                     content_logger.error(f"Failed to retrieve newly created anime {new_anime_id} after insertion for admin {user_id}. Cannot display management menu.", exc_info=True)
                     await client.send_message(chat_id, "💔 Added anime successfully, but failed to load its management menu. Please navigate manually from the Content Management main menu.", parse_mode=config.PARSE_MODE)
                     # User's state IS set correctly to MANAGING_ANIME_MENU, so they should be able to go back to main CM menu and then edit the anime from the list (if implemented).
                     # No need to clear state here. Just inform them menu failed.
                     await manage_content_command(client, callback_query.message) # Re-send CM main menu as fallback

            except Exception as e:
                 # Database error during insert operation
                 content_logger.critical(f"CRITICAL: Error inserting new anime document after status selection for admin {user_id}: {e}. State data: {user_state.data}", exc_info=True)
                 # This is a critical error - all collected data is lost. Inform admin and clear state.
                 await edit_or_send_message(client, chat_id, message_id, "💔 A critical database error occurred while saving the new anime data. All collected details were lost. Please try again.", disable_web_page_preview=True)
                 await clear_user_state(user_id); # Clear broken state
                 await manage_content_command(client, callback_query.message) # Offer to restart CM flow


        elif purpose == "edit":
            # Edit Existing Anime flow - Update the EXISTING anime document's status in the database.
            if not anime_id_str:
                content_logger.error(f"Admin {user_id} in SELECTING_STATUS (edit) state but missing anime_id in state data.")
                await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime ID missing from state data for status edit. Process cancelled.", disable_web_page_preview=True)
                await clear_user_state(user_id); return


            try:
                # Update the 'status' field for the anime document by its ID
                update_result = await MongoDB.anime_collection().update_one(
                    {"_id": ObjectId(anime_id_str)},
                    {"$set": {"status": selected_status, "last_updated_at": datetime.now(timezone.utc)}}
                )

                if update_result.matched_count > 0 and update_result.modified_count > 0:
                     content_logger.info(f"Admin {user_id} successfully updated status for anime {anime_id_str} to '{selected_status}'.")
                     await callback_query.message.edit_text(f"✅ Status updated to: **__{selected_status}__**!", parse_mode=config.PARSE_MODE)

                     # Fetch updated anime document to display management menu
                     updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                     if updated_anime:
                         # Clear SELECTING_STATUS edit state, set state back to managing this anime
                         await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                         await asyncio.sleep(1) # Short delay
                         await display_anime_management_menu(client, callback_query.message, updated_anime)

                     else:
                         content_logger.error(f"Failed to fetch updated anime {anime_id_str} after status update for admin {user_id}. Cannot display menu.")
                         await client.send_message(chat_id, "💔 Updated status, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                         await manage_content_command(client, callback_query.message) # Go to CM main menu


                elif update_result.matched_count > 0: # Modified count is 0 - same status selected
                     content_logger.info(f"Admin {user_id} selected status for {anime_id_str} but it was unchanged (modified_count=0).")
                     await callback_query.message.edit_text(f"✅ Status is already <b>{selected_status}</b>. No update needed.", parse_mode=config.PARSE_MODE)
                     # Fetch current anime and re-display management menu
                     current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                     if current_anime:
                          # Clear SELECTING_STATUS edit state, set state back to managing
                         await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                         await asyncio.sleep(1) # Short delay
                         await display_anime_management_menu(client, callback_query.message, current_anime)

                     else:
                          content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change status edit for admin {user_id}.")
                          await client.send_message(chat_id, "🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                          await manage_content_command(client, callback_query.message)


            except Exception as e:
                content_logger.error(f"Error updating status for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
                await client.send_message(chat_id, "💔 Error updating status.", parse_mode=config.PARSE_MODE)
                # State is SELECTING_STATUS edit. Clear state as a safety.
                await clear_user_state(user_id)

        else:
            # Should not happen - unexpected purpose in state data for SELECTING_STATUS
             content_logger.error(f"Admin {user_id} finished status selection with invalid purpose in state data: {purpose}. State data: {user_state.data}")
             await edit_or_send_message(client, chat_id, message_id, "🤷 Unexpected data in state. Your process was cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id)


    except Exception as e:
        # Generic error during callback processing
        content_logger.error(f"FATAL error handling content_select_status callback {data} for admin {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await clear_user_state(user_id); # Clear state
        await manage_content_command(client, callback_query.message) # Offer to restart CM flow

# --- Helper for editing top-level anime fields (Callbacks from display_anime_management_menu) ---
# These functions transition to text input states, similar to add flow prompts

@Client.on_callback_query(filters.regex("^content_edit_name\|.*") & filters.private)
async def handle_edit_name_callback(client: Client, message: Message, user_state: UserState, data: str):
    """Handles admin clicking Edit Name button, prompts for new name."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await client.answer_callback_query(message.id, "🚫 You are not authorized.") # Answer here if no explicit answer needed elsewhere
        return

    # Ensure state is managing a specific anime
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking edit name. Data: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing name.", disable_web_page_preview=True)
        await clear_user_state(user_id)
        await manage_content_command(client, message) # Offer to restart
        return

    try:
        # Parse anime_id from callback data
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        # Ensure anime_id from callback matches ID in state data as a safety (or trust callback)
        if user_state.data.get("anime_id") != anime_id_str:
            content_logger.warning(f"Admin {user_id} state anime_id {user_state.data.get('anime_id')} doesn't match callback anime_id {anime_id_str} for editing name.")
            # Decide robust handling: Trust callback data but log mismatch, or abort. Let's update state data and trust callback for the action.
            user_state.data["anime_id"] = anime_id_str

        # Store that we are editing name in state data purpose (not needed if step is EDITING_NAME_PROMPT)
        # user_state.data["purpose"] = "edit_name"

        # Transition state to waiting for the new name input
        await set_user_state(user_id, "content_management", ContentState.EDITING_NAME_PROMPT, data=user_state.data) # Keep existing state data including anime_id/name


        # Prompt admin for new name (text input)
        prompt_text = "✏️ Send the **<u>New Name</u>** for this anime:" # Specific prompt for clarity
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])

        # Edit the message that triggered the callback (the management menu)
        await edit_or_send_message(
            client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True
        )
         # Acknowledge the callback *after* successful message edit
        try: await client.answer_callback_query(message.id)
        except Exception: common_logger.warning(f"Failed to answer callback {data} after message edit for {user_id}")

    except Exception as e:
         content_logger.error(f"Error handling content_edit_name callback for admin {user_id}: {e}", exc_info=True)
         # Answer with alert and try to inform the user
         try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True)
         except Exception: common_logger.warning(f"Failed to answer callback {data} error alert for {user_id}")
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)


# Called by handle_content_input when state is EDITING_NAME_PROMPT
async def handle_editing_name_input(client: Client, message: Message, user_state: UserState, new_name: str):
    """Handles admin text input when in the EDITING_NAME_PROMPT state (expects new name)."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_id_str = user_state.data.get("anime_id")

    # We are editing a specific anime, anime_id must be in state data.
    if not anime_id_str:
        content_logger.error(f"Admin {user_id} sent new anime name but missing anime_id in state data (step: {user_state.step}). State data: {user_state.data}")
        await message.reply_text("💔 Error: Anime ID missing from state. Cannot update name. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return # Clear broken state

    content_logger.info(f"Admin {user_id} provided new name '{new_name}' for anime ID {anime_id_str} in EDITING_NAME_PROMPT.")

    # Find the anime by ID and update its 'name' field
    try:
         update_result = await MongoDB.anime_collection().update_one(
             {"_id": ObjectId(anime_id_str)}, # Filter by the anime ID
             {"$set": {"name": new_name, "last_updated_at": datetime.now(timezone.utc)}} # Update name and timestamp
         )

         if update_result.matched_count > 0:
             # Document was found, check if it was modified
             if update_result.modified_count > 0:
                  content_logger.info(f"Admin {user_id} successfully updated name of anime {anime_id_str} to '{new_name}'.")
                  await message.reply_text(f"✅ Name updated to **<u>{new_name}</u>**!", parse_mode=config.PARSE_MODE)

                  # Fetch the updated anime document and return to the anime management menu.
                  updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                  if updated_anime:
                       # Clear editing state and set state back to managing this specific anime
                       await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name}) # Update name in state data
                       await asyncio.sleep(1) # Short delay before displaying menu
                       await display_anime_management_menu(client, message, updated_anime) # Pass message from input

                  else:
                      content_logger.error(f"Failed to fetch updated anime {anime_id_str} after name update for admin {user_id}.")
                      # State is set correctly, but failed to display menu. Inform and fallback.
                      await message.reply_text("💔 Updated name, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message) # Go back to main CM menu as fallback


             else: # Matched but not modified (same name sent)
                 content_logger.info(f"Admin {user_id} tried to update name of anime {anime_id_str} but name was unchanged ('{new_name}').")
                 await message.reply_text(f"✅ Name is already **<u>{new_name}</u>**. No update needed.", parse_mode=config.PARSE_MODE)
                 # Re-display the management menu for the current anime.
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     # Clear editing state, set state back to managing
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await asyncio.sleep(1) # Short delay
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change name edit for admin {user_id}.")
                      await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message) # Go to CM main menu


         else: # Matched count is 0 - Anime not found during update query
             content_logger.error(f"Anime ID {anime_id_str} not found during update operation by admin {user_id} in EDITING_NAME_PROMPT.")
             await message.reply_text("💔 Error: Anime not found during update. Please try editing again from the management menu.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return # Clear state

    except Exception as e:
         # Error during the database update operation
         content_logger.error(f"Error updating anime name {anime_id_str} to '{new_name}' for admin {user_id}: {e}", exc_info=True)
         await message.reply_text("💔 Error updating anime name.", parse_mode=config.PARSE_MODE)
         # State is EDITING_NAME_PROMPT. User can send text again or cancel.

# Implement handlers for other edit field callbacks similar to handle_edit_name_callback
# content_edit_synopsis|<anime_id> -> state EDITING_SYNOPSIS_PROMPT -> expects text
@Client.on_callback_query(filters.regex("^content_edit_synopsis\|.*") & filters.private)
async def handle_edit_synopsis_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing synopsis."); await clear_user_state(user_id); await manage_content_command(client, message); return
     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
         if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str # Update state ID
         await set_user_state(user_id, "content_management", ContentState.EDITING_SYNOPSIS_PROMPT, data=user_state.data)
         prompt_text = "📝 Send the **<u>New Synopsis</u>** for this anime:"
         reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
         await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
         try: await client.answer_callback_query(message.id)
         except Exception: pass # Ignore answer failure
     except Exception as e: content_logger.error(f"Error handling edit synopsis callback {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);


# handle_editing_synopsis_input already implemented to handle both add (AWAITING_SYNOPSIS) and edit (EDITING_SYNOPSIS_PROMPT) purposes.

# content_edit_poster|<anime_id> -> state EDITING_POSTER_PROMPT -> expects photo (handled by handle_media_input routing to handle_awaiting_poster which checks purpose)
@Client.on_callback_query(filters.regex("^content_edit_poster\|.*") & filters.private)
async def handle_edit_poster_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing poster."); await clear_user_state(user_id); await manage_content_command(client, message); return
     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
         if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str
         # Set state to AWAITING_POSTER, but specify the purpose is 'edit'
         await set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={**user_state.data, "purpose": "edit"}) # Add purpose to state data
         prompt_text = "🖼️ Send the **<u>New Poster Image</u>** for this anime:" # Specific prompt
         reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
         await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
         try: await client.answer_callback_query(message.id)
         except Exception: pass
     except Exception as e: content_logger.error(f"Error handling edit poster callback {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

# handle_awaiting_poster now handles both 'add' and 'edit' purpose based on state data.

# content_edit_genres|<anime_id> -> state SELECTING_GENRES -> expects callbacks (and uses purpose in done callback)
@Client.on_callback_query(filters.regex("^content_edit_genres\|.*") & filters.private)
async def handle_edit_genres_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing genres."); await clear_user_state(user_id); await manage_content_command(client, message); return
     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
         if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str
         # Fetch the anime to get its current genres for initial selection state display
         anime = await MongoDB.get_anime_by_id(anime_id_str)
         if not anime: raise Exception("Anime not found for genre edit after state check.")
         # Store current genres and purpose in state data, transition state
         await set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data={**user_state.data, "purpose": "edit", "selected_genres": anime.genres})
         # Prompt for genre selection - Pass current genres for highlighting buttons
         prompt_text = strings.ADD_ANIME_GENRES_PROMPT.format(anime_name=anime.name) # Use original string, pass anime name
         await client.send_message(chat_id, prompt_text, parse_mode=config.PARSE_MODE) # Send as new message
         await prompt_for_genres(client, chat_id, anime.name, anime.genres) # Helper handles keyboard
         try: await client.answer_callback_query(message.id, "Select genres to toggle."); # Answer and message appear together
         except Exception: pass # Ignore answer failure

     except Exception as e: content_logger.error(f"Error handling edit genres callback {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

# content_toggle_genre_callback and content_genres_done_callback now handle both 'add' and 'edit' based on purpose in state data.

# content_edit_year|<anime_id> -> state EDITING_RELEASE_YEAR_PROMPT -> expects text
@Client.on_callback_query(filters.regex("^content_edit_year\|.*") & filters.private)
async def handle_edit_year_callback(client: Client, message: Message, user_state: UserState, data: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing year."); await clear_user_state(user_id); await manage_content_command(client, message); return
    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str
        await set_user_state(user_id, "content_management", ContentState.EDITING_RELEASE_YEAR_PROMPT, data=user_state.data)
        prompt_text = "🗓️ Send the **<u>New Release Year</u>** for this anime:"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
        await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
        try: await client.answer_callback_query(message.id)
        except Exception: pass
    except Exception as e: content_logger.error(f"Error handling edit year callback {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

# handle_awaiting_release_year_input already handles both 'add' and 'edit' based on purpose/state.

# content_edit_status|<anime_id> -> state SELECTING_STATUS -> expects callbacks (and uses purpose in selection callback)
@Client.on_callback_query(filters.regex("^content_edit_status\|.*") & filters.private)
async def handle_edit_status_callback(client: Client, message: Message, user_state: UserState, data: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing status."); await clear_user_state(user_id); await manage_content_command(client, message); return
    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str
        # Fetch the anime to get its current status (optional, but could highlight on buttons if implementing)
        anime = await MongoDB.get_anime_by_id(anime_id_str)
        if not anime: raise Exception("Anime not found for status edit after state check.")

        # Store purpose in state data, transition state
        await set_user_state(user_id, "content_management", ContentState.SELECTING_STATUS, data={**user_state.data, "purpose": "edit", "status": anime.status})
        # Prompt for status selection - Pass current status
        prompt_text = strings.ADD_ANIME_STATUS_PROMPT.format(anime_name=anime.name) # Use original string
        # Use the prompt_for_status helper which will send a NEW message with buttons
        await prompt_for_status(client, chat_id, anime.name, anime.status) # Pass message, name, and current status for potential highlighting

        # Edit the triggering message (management menu) to indicate where the status prompt was sent
        await edit_or_send_message(
            client, chat_id, message_id, f"🚦 Sent status selection menu for {anime.name}...",
             disable_web_page_preview=True # Keep original message edited with simple confirmation
         )
        try: await client.answer_callback_query(message.id, "Select status."); # Answer and confirmation message appear together
        except Exception: pass


    except Exception as e: content_logger.error(f"Error handling edit status callback {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

# content_select_status_callback now handles both 'add' and 'edit' based on purpose in state data.
# The logic within content_select_status_callback needs to get the anime_id and update the EXISTING anime doc if purpose is 'edit', then return to MANAGING_ANIME_MENU.


# content_edit_total_seasons_count|<anime_id> -> state EDITING_TOTAL_SEASONS_COUNT_PROMPT -> expects text
@Client.on_callback_query(filters.regex("^content_edit_total_seasons_count\|.*") & filters.private)
async def handle_edit_total_seasons_count_callback(client: Client, message: Message, user_state: UserState, data: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing total seasons."); await clear_user_state(user_id); await manage_content_command(client, message); return
    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str

        await set_user_state(user_id, "content_management", ContentState.EDITING_TOTAL_SEASONS_COUNT_PROMPT, data=user_state.data)
        prompt_text = "🔢 Send the **<u>New Total Number of Seasons</u>** for this anime:"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
        await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
        try: await client.answer_callback_query(message.id)
        except Exception: pass

    except Exception as e: content_logger.error(f"Error handling edit total seasons count callback {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

# handle_awaiting_total_seasons_count_input now handles both add (AWAITING_TOTAL_SEASONS_COUNT) and edit (EDITING_TOTAL_SEASONS_COUNT_PROMPT).

# --- Implementations for SEASONS management ---

# This helper displays the list of seasons with options to manage them.
# Called from content_manage_seasons callback (to initially view seasons) and handle_awaiting_seasons_count_input (after setting episode count for a season)
async def display_seasons_management_menu(client: Client, message: Message, anime: Anime):
     """Displays the list of seasons for an anime to the admin with management options."""
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id

     # State should be MANAGING_SEASONS_LIST when displaying this menu
     # If it's not, set it, or maybe verify it was set correctly by the caller

     anime_id_str = str(anime.id)
     anime_name = anime.name

     # Sort seasons numerically
     seasons = sorted(anime.seasons, key=lambda s: s.season_number) # Sort using Pydantic model field


     menu_text = strings.MANAGE_SEASONS_TITLE.format(anime_name=anime_name) + "\n\n"

     buttons = []
     if not seasons:
          menu_text += "No seasons added yet.\n\n"

     # Add buttons for each existing season to select for managing episodes
     for season in seasons:
          # Use a robust getter with default for nested structures
          season_number = season.season_number
          episodes_list = season.episodes
          ep_count = len(episodes_list) # Actual count of episode documents in array
          declared_count = season.episode_count_declared # Admin-declared count

          button_label = f"📺 Season {season_number}"
          if declared_count is not None and declared_count > 0:
               button_label += f" ({declared_count} Episodes Declared)" # Show declared count if set
               # Optionally, show actual count vs declared if they mismatch
               if ep_count > 0 and ep_count != declared_count:
                    button_label += f" [{ep_count} Existing]" # Show actual count if different from declared

          elif ep_count > 0: # Declared count not set, but episodes exist
               button_label += f" ({ep_count} Episodes)"

          # Callback to select this season for episode management: content_select_season|<anime_id>|<season_number>
          buttons.append([InlineKeyboardButton(button_label, callback_data=f"content_select_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}")])


     # Add options: Add New Season, Remove Season
     # Determine the next sequential season number based on existing seasons
     next_season_number = (seasons[-1].season_number if seasons else 0) + 1
     buttons.append([InlineKeyboardButton(strings.BUTTON_ADD_NEW_SEASON, callback_data=f"content_add_new_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{next_season_number}")])

     # Add Remove Season button (requires admin to select which season to remove - leads to a selection submenu/view)
     if seasons: # Only show remove option if there are seasons
          # Callback: content_remove_season_select|<anime_id> (Leads to list of seasons with remove buttons)
          buttons.append([InlineKeyboardButton("🗑️ Remove a Season", callback_data=f"content_remove_season_select{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")])


     # Navigation buttons: Back to Anime Menu, Home CM Menu, Home Bot Menu
     buttons.append([InlineKeyboardButton(strings.BUTTON_BACK_TO_ANIME_LIST_ADMIN, callback_data=f"content_edit_existing|{anime_id_str}")]) # Back to management menu for this anime
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")]) # Back to CM main menu
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Back to main user menu


     reply_markup = InlineKeyboardMarkup(buttons)

     # Edit the current message (where the button was clicked) to display this season list
     await edit_or_send_message(
          client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True
      )

# Callback to display seasons management menu - Route from anime management menu
# Catches callbacks content_manage_seasons|<anime_id>
@Client.on_callback_query(filters.regex(f"^content_manage_seasons{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_manage_seasons_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Manage Seasons/Episodes button for an anime."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_manage_seasons|<anime_id>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Loading seasons...") # Answer immediately
    except Exception: pass # Ignore answer failure

    user_state = await get_user_state(user_id)
    # We expect admin to be in a CM state when clicking this. Ensure state is managing an anime?
    # If state is missing or handler is wrong, reset.
    if not (user_state and user_state.handler == "content_management"):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking manage seasons. Data: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please navigate from the Content Management main menu.", disable_web_page_preview=True)
        await clear_user_state(user_id) # Clear incorrect state
        await manage_content_command(client, callback_query.message) # Offer to start fresh CM
        return

    try:
        # Parse anime_id from callback data
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        # Ensure state data also holds the correct anime_id if transitioning within flow
        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id {user_state.data.get('anime_id')} doesn't match callback anime_id {anime_id_str} for manage seasons. Updating state.")
             user_state.data["anime_id"] = anime_id_str

        # Set the state to indicate the admin is now managing seasons for this specific anime.
        await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data=user_state.data)


        # Fetch the anime document, projecting only the 'seasons' and 'name' for efficiency.
        anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})

        if not anime_doc:
            content_logger.error(f"Anime {anime_id_str} not found for managing seasons for admin {user_id}. State data: {user_state.data}")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found for season management.", disable_web_page_preview=True)
            await clear_user_state(user_id); # Clear state as anime is missing
            await manage_content_command(client, callback_query.message) # Offer to restart CM


        # Convert to Anime model (even if only seasons/name are present) to use model properties and sorting logic in helper.
        # Need to handle potential missing fields if not projected - Pydantic defaults help here.
        anime = Anime(**anime_doc)

        # Display the seasons management menu using the helper function
        await display_seasons_management_menu(client, callback_query.message, anime)


    except Exception as e:
         content_logger.error(f"FATAL error handling content_manage_seasons callback {data} for admin {user_id}: {e}", exc_info=True)
         await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
         await clear_user_state(user_id) # Clear state
         await manage_content_command(client, callback_query.message) # Offer to restart CM

# handle_add_new_season_callback updated previously to handle add season and route to AWAITING_TOTAL_SEASONS_COUNT


# --- Implement Remove Season Workflow (Selection and Confirmation) ---

# Callback to trigger the season removal selection menu
# Catches callbacks content_remove_season_select|<anime_id>
@Client.on_callback_query(filters.regex(f"^content_remove_season_select{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_remove_season_select_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking 'Remove a Season', displays seasons to select for removal."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_remove_season_select|<anime_id>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Select season to remove...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be MANAGING_SEASONS_LIST
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_SEASONS_LIST):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking remove season select. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting season to remove.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse anime_id
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        # Ensure anime_id from callback matches state for robustness
        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id mismatch for remove season select: {user_state.data.get('anime_id')} vs callback {anime_id_str}")
             user_state.data["anime_id"] = anime_id_str


        # Fetch the anime seasons to display list of seasons to remove
        anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})
        if not anime_doc:
            content_logger.error(f"Anime {anime_id_str} not found for removing season for admin {user_id}.")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found.", disable_web_page_preview=True)
            await clear_user_state(user_id); return # Clear state

        anime = Anime(**anime_doc) # Convert to model to use seasons property
        seasons = sorted(anime.seasons, key=lambda s: s.season_number) # Sort seasons

        if not seasons:
            # Should ideally not reach here if the option to remove isn't shown when no seasons exist, but as a safeguard
            await edit_or_send_message(client, chat_id, message_id, "🤔 No seasons available to remove for this anime.", disable_web_page_preview=True)
             # State is still MANAGING_SEASONS_LIST. Can let them stay here.
            return

        # Set the state to indicate we are now in the process of confirming season removal
        # State: "content_management":"confirm_remove_season"
        await set_user_state(user_id, "content_management", ContentState.CONFIRM_REMOVE_SEASON, data=user_state.data) # Keep existing state data (incl. anime_id)


        menu_text = f"🗑️ <b><u>Remove Season from</u></b> <b>{anime.name}</b> 🗑️\n\n👇 Select the season you want to **<u>permanently remove</u>**: (This will delete all episodes and files in that season!)"

        buttons = []
        # Create buttons for each season allowing confirmation of removal
        for season in seasons:
             season_number = season.season_number
             # Callback: content_confirm_remove_season|<anime_id>|<season_number>
             buttons.append([InlineKeyboardButton(f"❌ Remove Season {season_number}", callback_data=f"content_confirm_remove_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}")])


        # Add Back button to seasons list and Home buttons
        # Back button callback needs to return to the MANAGING_SEASONS_LIST state display
        buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"content_manage_seasons|{anime_id_str}")]) # Pass anime_id back to manage_seasons handler
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")])
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])

        reply_markup = InlineKeyboardMarkup(buttons)

        # Edit the message (the seasons list menu) to display the selection for removal.
        await edit_or_send_message(
             client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True
         )


    except Exception as e:
        content_logger.error(f"FATAL error handling content_remove_season_select callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id) # Clear state
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message); # Offer to restart CM

# Callback to confirm season removal
# Catches callbacks content_confirm_remove_season|<anime_id>|<season_number>
@Client.on_callback_query(filters.regex(f"^content_confirm_remove_season{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_confirm_remove_season_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking a specific season to remove after clicking 'Remove a Season'."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_confirm_remove_season|<anime_id>|<season_number>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Removing season permanently...") # Indicate ongoing process
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be CONFIRM_REMOVE_SEASON
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.CONFIRM_REMOVE_SEASON):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking confirm remove season. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for confirming season removal.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse anime_id and season_number from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3:
             raise ValueError("Invalid callback data format for removing season.")
        anime_id_str = parts[1]
        season_number_to_remove = int(parts[2])

        # Ensure anime_id from callback matches state
        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id mismatch for confirm remove season: {user_state.data.get('anime_id')} vs callback {anime_id_str}")
             user_state.data["anime_id"] = anime_id_str # Update state data

        content_logger.info(f"Admin {user_id} confirming remove Season {season_number_to_remove} from anime {anime_id_str}.")


        # --- Perform the database update: remove the season ---
        # Use $pull operator to remove the season subdocument from the 'seasons' array by matching its season_number
        update_result = await MongoDB.anime_collection().update_one(
            {"_id": ObjectId(anime_id_str)}, # Filter by the anime ID
            {"$pull": {"seasons": {"season_number": season_number_to_remove}}}, # Pull elements from 'seasons' array matching the season_number
            # Update last_updated_at on parent document? Add separate $set operation if needed or relies on DB's upserted/modified time?
            # Using $pull doesn't automatically update last_updated_at on parent in some MongoDB versions? Safe to add explicitly:
             # {"$set": {"last_updated_at": datetime.now(timezone.utc)}} # Requires combining with $pull or a separate update call if both needed
        )

        if update_result.matched_count > 0: # Anime was found
             if update_result.modified_count > 0:
                  # Season was successfully removed
                  content_logger.info(f"Admin {user_id} successfully removed Season {season_number_to_remove} from anime {anime_id_str}.")
                  await edit_or_send_message(client, chat_id, message_id, f"✅ Permanently removed Season **<u>{season_number_to_remove}</u>** from this anime.", disable_web_page_preview=True)

                  # Update top-level timestamp if $pull didn't
                  await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"last_updated_at": datetime.now(timezone.utc)}})
                  db_logger.debug(f"Updated last_updated_at for anime {anime_id_str} after season removal.")


                  # --- Transition back to the updated seasons list menu ---
                  # Clear the CONFIRM_REMOVE_SEASON state
                  # Set state back to MANAGING_SEASONS_LIST for this anime
                  await set_user_state(
                       user_id,
                       "content_management",
                       ContentState.MANAGING_SEASONS_LIST,
                       data={"anime_id": anime_id_str, "anime_name": user_state.data.get("anime_name", "Anime")} # Keep relevant context
                  )

                  # Fetch the updated anime seasons to display the list again
                  updated_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})
                  if updated_anime_doc:
                      # Display the seasons menu helper will re-sort and build buttons based on new data
                      await display_seasons_management_menu(client, callback_query.message, Anime(**updated_anime_doc)) # Pass message from callback

                  else:
                      # Failed to re-fetch the anime seasons after removal - should not happen if update was successful.
                       content_logger.error(f"Failed to re-fetch anime {anime_id_str} seasons after removal for admin {user_id}.", exc_info=True)
                       await client.send_message(chat_id, "💔 Removed season, but failed to reload the seasons menu.", parse_mode=config.PARSE_MODE)
                       # State is set correctly. User can navigate back to main CM menu.
                       await manage_content_command(client, callback_query.message) # Offer to restart CM

             else: # Matched count > 0, Modified count == 0 - Season not found or already removed between clicks
                 content_logger.warning(f"Admin {user_id} confirmed remove season {season_number_to_remove} for {anime_id_str} but modified_count was 0. Season not found or already removed.")
                 await edit_or_send_message(client, chat_id, message_id, f"⚠️ Season **<u>{season_number_to_remove}</u>** was not found or already removed.", disable_web_page_preview=True)
                 # Remain in CONFIRM_REMOVE_SEASON state? Or go back to selection list?
                 # Re-displaying the remove selection menu based on current DB state is better.
                 # The content_remove_season_select callback handles fetching and displaying the list.
                 await handle_remove_season_select_callback(client, callback_query.message, user_state, f"content_remove_season_select|{anime_id_str}")


        else: # Matched count is 0 - Anime not found during update operation
            content_logger.error(f"Anime ID {anime_id_str} not found during remove season update operation by admin {user_id} (Season {season_number_to_remove}).")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found. Cannot remove season.", disable_web_page_preview=True)
            await clear_user_state(user_id); # Clear state
            await manage_content_command(client, callback_query.message); # Offer to restart CM

    except Exception as e:
         # Error during database removal or callback parsing
         content_logger.error(f"FATAL error handling content_confirm_remove_season callback {data} for admin {user_id}: {e}", exc_info=True)
         await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
         await clear_user_state(user_id) # Clear state
         await manage_content_command(client, callback_query.message) # Offer to restart CM


# --- Implementations for EPISODE management ---
# display_episodes_management_list helper defined previously

# Callback to display episodes management list for a season - Route from seasons list
# Catches callbacks content_select_season|<anime_id>|<season_number>
@Client.on_callback_query(filters.regex(f"^content_select_season{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_select_season_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting a season from the seasons list to manage episodes."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_select_season|<anime_id>|<season_number>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Loading episodes...") # Answer immediately
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be MANAGING_SEASONS_LIST when clicking this button
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_SEASONS_LIST):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking select season. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting season.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse anime_id and season_number
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3:
             raise ValueError("Invalid callback data format for selecting season.")
        anime_id_str = parts[1]
        season_number = int(parts[2])

        # Ensure anime_id from callback matches state for robustness
        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id mismatch for select season: {user_state.data.get('anime_id')} vs callback {anime_id_str}. Updating state data.")
             user_state.data["anime_id"] = anime_id_str # Update state data

        content_logger.info(f"Admin {user_id} selected Season {season_number} from anime {anime_id_str} to manage episodes.")

        # Find the specific anime and the specific season to get its episodes list.
        # Project name and the matched season (with its episodes array).
        filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
        projection = {"name": 1, "seasons.$": 1} # Project only the matched season

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

        # $elemMatch projection returns 'seasons' as an array containing only the matched element
        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0]:
             content_logger.error(f"Anime/Season {anime_id_str}/S{season_number} not found for episode management (select season callback) for admin {user_id}.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime or season not found for episode management.", disable_web_page_preview=True)
             await clear_user_state(user_id); return


        anime_name = anime_doc.get("name", "Anime Name Unknown")
        season_data = anime_doc["seasons"][0] # Access the single matched season document
        episodes = season_data.get("episodes", []) # Get the episodes list from the season data

        # Sort episodes numerically
        episodes.sort(key=lambda e: e.get("episode_number", 0))

        # --- Transition to Managing Episodes List State ---
        # Set state to MANAGING_EPISODES_LIST, preserving anime/season context.
        # Also store anime_name in state data for display/logging in subsequent steps.
        await set_user_state(
             user_id,
             "content_management",
             ContentState.MANAGING_EPISODES_LIST,
             data={**user_state.data, "anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_name} # Update state data with context
         )

        # Display the list of episodes for the selected season.
        await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_name, season_number, episodes) # Pass the message to edit

    except ValueError:
        content_logger.warning(f"Admin {user_id} invalid season number data in callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid season number data in callback.", disable_web_page_preview=True)
        # Stay in the seasons list state implicitly.

    except Exception as e:
         content_logger.error(f"FATAL error handling content_select_season callback {data} for admin {user_id}: {e}", exc_info=True)
         await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
         await clear_user_state(user_id); # Clear state
         await manage_content_command(client, callback_query.message) # Offer to restart CM


# Helper to display list of episodes for a season with management buttons
# Called from handle_select_season_callback and after actions in episode menu that return here (e.g., deleting episode)
async def display_episodes_management_list(client: Client, message: Message, anime_id_str: str, anime_name: str, season_number: int, episodes: List[Dict]):
    """Displays the list of episodes for a season to the admin with management options."""
    user_id = message.from_user.id # Needed for logging context
    chat_id = message.chat.id
    message_id = message.id


    menu_text = strings.MANAGE_EPISODES_TITLE.format(anime_name=anime_name, season_number=season_number) + "\n\n"

    buttons = []
    if not episodes:
        menu_text += "No episodes added for this season. Add episodes by setting the Total Episodes count for the season in the Seasons Menu.\n\n"
         # Note: Adding episodes is currently done by setting the episode_count_declared for the season.

    # Add buttons for each existing episode placeholder/entry
    for episode in episodes:
         ep_number = episode.get("episode_number")
         # Skip if episode number is None (bad data)
         if ep_number is None:
             content_logger.warning(f"Admin {user_id} found episode document with no episode_number for {anime_id_str}/S{season_number}. Skipping display.")
             continue # Skip this invalid entry

         # Determine episode status for button label
         files = episode.get("files", []) # Ensure default list if missing
         release_date = episode.get("release_date") # Datetime object

         ep_label = f"🎬 EP{ep_number:02d}" # Format episode number (e.g., EP01)

         # Indicate status in button label
         if files: # Check if the files array is non-empty
             ep_label += f" [{strings.EPISODE_STATUS_HAS_FILES}]"
         elif isinstance(release_date, datetime): # Check if release_date is a datetime object
              # Format date nicely, ensure it's UTC if possible
              formatted_date = release_date.astimezone(timezone.utc).strftime('%Y-%m-%d') # e.g., 2024-12-25
              ep_label += f" [{strings.EPISODE_STATUS_HAS_DATE.format(date=formatted_date)}]" # Use placeholder
         else: # Neither files nor release date are set
              ep_label += f" [{strings.EPISODE_STATUS_NO_CONTENT}]"


         # Callback data to manage this specific episode: content_manage_episode|<anime_id>|<season_number>|<episode_number>
         buttons.append([InlineKeyboardButton(ep_label, callback_data=f"content_manage_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{ep_number}")])


    # Navigation buttons: Back to seasons list, Back to main CM menu, Back to main bot menu
    # Back button to seasons list menu
    buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"content_manage_seasons|{anime_id_str}")]) # Pass anime_id back to manage_seasons handler (reloads seasons menu)

    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")]) # Back to main CM menu
    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Back to main user menu


    reply_markup = InlineKeyboardMarkup(buttons)

    # Edit the message (the season list menu) to display this episode list
    await edit_or_send_message(
         client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True
     )


# Callback to display management options for a specific episode
# Catches callbacks content_manage_episode|<anime_id>|<season_number>|<episode_number>
@Client.on_callback_query(filters.regex(f"^content_manage_episode{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_select_episode_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting a specific episode from the episodes list to manage files/release date/delete."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # ID of the message to edit
    data = callback_query.data # content_manage_episode|<anime_id>|<season_number>|<episode_number>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Loading episode management menu...") # Answer immediately
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be MANAGING_EPISODES_LIST
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODES_LIST):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking manage episode. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting episode.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse anime_id, season_number, episode_number
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4:
             raise ValueError("Invalid callback data format for managing episode.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        # Ensure context data matches state for robustness
        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number:
            content_logger.warning(f"Admin {user_id} state anime/season mismatch for manage episode: {user_state.data.get('anime_id')}/S{user_state.data.get('season_number')} vs callback {anime_id_str}/S{season_number}. Updating state data.")
            # Update state data to match callback context
            user_state.data.update({"anime_id": anime_id_str, "season_number": season_number})
            await set_user_state(user_id, user_state.handler, user_state.step, data=user_state.data) # Save updated state data

        content_logger.info(f"Admin {user_id} selected Episode {episode_number} from {anime_id_str}/S{season_number} for management.")

        # Find the specific episode document to get its current details (files, release_date)
        # Efficiently fetch the episode details by projecting and using $elemMatch
        filter_query = {"_id": ObjectId(anime_id_str)} # Filter anime by ID
        projection = {"name": 1, # Project anime name
                      "seasons": {"$elemMatch": {"season_number": season_number}}, # Project the matched season
                      # Could add more projections for nested episodes? Or filter episodes in app logic?
                      # Projecting the specific episode might be complex with MongoDB projections ($) if its index is unknown.
                      # It might be easier to project the matched season, then find the episode in its array in app logic.
                      }

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)


        # Validate results - anime must exist, season must exist and be in the seasons array (due to $elemMatch)
        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0]:
            content_logger.error(f"Anime/Season {anime_id_str}/S{season_number} not found for episode management (manage episode callback) for admin {user_id}.")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime or season not found.", disable_web_page_preview=True)
            await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


        anime_name = anime_doc.get("name", "Anime Name Unknown")
        season_data = anime_doc["seasons"][0] # The matched season data as a single-element list


        # Find the specific episode within the season's episodes list
        episodes_list_of_season = season_data.get("episodes", [])
        current_episode_doc = next((ep for ep in episodes_list_of_season if ep.get("episode_number") == episode_number), None)

        if not current_episode_doc:
            content_logger.error(f"Episode {episode_number} not found in season {season_number} for anime {anime_id_str} for admin {user_id}.")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Episode not found in season.", disable_web_page_preview=True)
            # No need to clear state, just prompt them that the episode wasn't found. They can go back to the list.
            # But display the episodes list again as the original button/context might be stale.
            # Fetch full episode list for this season to re-display episodes management list
            # Re-fetch the whole season document with episodes to be safe
            full_season_doc = await MongoDB.anime_collection().find_one(filter_query, {"name":1, "seasons.$": 1})
            if full_season_doc and full_season_doc.get("seasons"):
                updated_episodes_list = full_season_doc["seasons"][0].get("episodes", [])
                updated_episodes_list.sort(key=lambda e: e.get("episode_number", 0)) # Sort
                # Remain in MANAGING_EPISODES_LIST state
                # await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODES_LIST, data=user_state.data) # State is already this if correct
                await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_name, season_number, updated_episodes_list)

            else:
                 content_logger.error(f"Failed to fetch full season document to re-display list after episode not found for admin {user_id}.")
                 await edit_or_send_message(client, chat_id, message_id, "💔 Episode not found and failed to reload episodes list.", disable_web_page_preview=True)
                 # Fallback: Return to season list? Return to main CM menu? Clear state.
                 await clear_user_state(user_id); await manage_content_command(client, callback_query.message);


            return # Stop execution after error handling


        # Convert the specific episode dictionary to Episode model (if schema allows partial load?)
        # Easier: Work with the dictionary directly as display_episode_management_menu expects Dict
        # Pass the specific episode document dictionary
        # Use Pydantic Episode model validation just for safety if desired:
        # try:
        #      current_episode = Episode(**current_episode_doc)
        # except Exception as e:
        #      content_logger.error(f"Error validating Episode model for {anime_id_str}/S{season_number}E{episode_number} for admin {user_id}: {e}", exc_info=True)
        #      # Decide handling: use dict data anyway? Fail? Use the doc dict for display.
        #      pass


        # --- Transition to Managing Episode Menu State ---
        # Set state to MANAGING_EPISODE_MENU, storing specific episode context
        # This state holds context for actions within this episode's options (add file, add date, delete file, delete episode)
        await set_user_state(
             user_id,
             "content_management",
             ContentState.MANAGING_EPISODE_MENU, # Set to managing this specific episode
             data={
                 "anime_id": anime_id_str,
                 "season_number": season_number,
                 "episode_number": episode_number, # Store current episode number
                 "anime_name": anime_name,
                 # Preserve other relevant state data if any? (Less likely in episode management)
                 # Add back navigation context implicitly via callbacks and state transitions back.
             }
         )

        # Display the episode management options menu using the helper
        await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, current_episode_doc)


    except ValueError:
        content_logger.warning(f"Admin {user_id} invalid episode number data in callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid episode number data in callback.", disable_web_page_preview=True)
        # Stay in episodes list state.

    except Exception as e:
         content_logger.error(f"FATAL error handling content_manage_episode callback {data} for admin {user_id}: {e}", exc_info=True)
         await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
         await clear_user_state(user_id); # Clear state
         await manage_content_command(client, callback_query.message); # Offer to restart CM

# Helper to display the options menu for a single episode
# Called from handle_select_episode_callback and after actions within the episode menu (add file version, set date, delete)
async def display_episode_management_menu(client: Client, message: Message, anime_name: str, season_number: int, episode_number: int, episode_data: Dict):
     """Displays options for managing a specific episode (files, release date, delete). Expects episode data as Dict."""
     user_id = message.from_user.id # Needed for logging context
     chat_id = message.chat.id
     message_id = message.id # ID of the message to edit


     menu_text = f"🛠️ <b><u>Manage Episode</u></b> <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> 🛠️\n\n"

     buttons = []
     files = episode_data.get("files", []) # Ensure default list if missing
     release_date = episode_data.get("release_date") # Could be datetime or None/missing


     if files:
         menu_text += f"📥 <b><u>Available Versions</u></b>:\n"
         # List existing file versions (dicts in the list)
         for i, file_ver_dict in enumerate(files):
              # Safely access dictionary keys
              quality = file_ver_dict.get('quality_resolution', 'Unknown Quality')
              size_bytes = file_ver_dict.get('file_size_bytes', 0)
              audio_langs = file_ver_dict.get('audio_languages', [])
              subtitle_langs = file_ver_dict.get('subtitle_languages', [])

              # Format file size
              formatted_size = f"{size_bytes / (1024 * 1024):.2f} MB" if size_bytes > 0 else "0 MB"
              if size_bytes >= 1024 * 1024 * 1024: # If size is 1GB or more
                  formatted_size = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

              # Format languages
              audio_str = ', '.join(audio_langs) if audio_langs else 'N/A'
              subs_str = ', '.join(subtitle_langs) if subtitle_langs else 'None'


              menu_text += f"  <b>{i+1}.</b> <b>{quality}</b> ({formatted_size}) 🎧 {audio_str} 📝 {subs_str}\n"


         # Add button to add another version, go to next episode, delete versions
         # These buttons need current episode context in their callback data.
         # Get anime_id from state data as it's needed for callbacks.
         user_state = asyncio.run(get_user_state(user_id)) # Synchronously get state (bad practice? State should be current. Use a param or get in caller.)
         # Prefer to get state inside handlers if possible. Assuming state is already set by caller:
         # UserState model ensures needed data if set correctly.
         # Let's assume anime_id is in state.data when this is called.
         anime_id_str = user_state.data.get('anime_id')

         if not anime_id_str:
             content_logger.error(f"Missing anime_id in state data while displaying episode menu for admin {user_id}. State: {user_state.data}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing anime ID in state. Cannot display menu.", disable_web_page_preview=True)
             await clear_user_state(user_id)
             await manage_content_command(client, message); return

         # Need to determine the highest episode number in this season for the "Next Episode" button.
         # Fetch episodes list again just for determining max episode number for NEXT button text
         try:
              season_doc_episodes = await MongoDB.anime_collection().find_one(
                   {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number},
                   {"seasons.$.episodes.episode_number": 1} # Project only episode numbers
               )
              max_episode_number_in_season = max([ep.get("episode_number", 0) for ep in season_doc_episodes["seasons"][0]["episodes"]]) if (season_doc_episodes and season_doc_episodes.get("seasons") and season_doc_episodes["seasons"][0].get("episodes")) else episode_number # Fallback

         except Exception as e:
              content_logger.warning(f"Failed to determine max episode number for 'Next Episode' button for admin {user_id}: {e}")
              max_episode_number_in_season = episode_number # Use current if failed


         buttons = [
             # content_add_file_version|<anime_id>|<season>|<ep> - Initiates file upload flow
             [InlineKeyboardButton(strings.BUTTON_ADD_OTHER_VERSION.format(episode_number=episode_number), callback_data=f"content_add_file_version{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
             # content_go_next_episode|<anime_id>|<season>|<target_ep_number> - Navigates to target ep menu (next sequential)
             [InlineKeyboardButton(strings.BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number + 1}")], # Assuming next sequential is next ep number
             # content_delete_file_version_select|<anime_id>|<season>|<ep> - Initiates file deletion flow (needs selecting version)
             [InlineKeyboardButton(strings.BUTTON_DELETE_FILE_VERSION_SELECT, callback_data=f"content_delete_file_version_select{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
         ]

     elif isinstance(release_date, datetime): # Has a release date but no files
          formatted_date = release_date.astimezone(timezone.utc).strftime('%Y-%m-%d')
          menu_text = f"🛠️ <b><u>Manage Episode</u></b> <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> 🛠️\n\n"
          menu_text += strings.EPISODE_OPTIONS_WITH_RELEASE_DATE_ADMIN.format(release_date=formatted_date) + "\n\n"

          user_state = asyncio.run(get_user_state(user_id))
          anime_id_str = user_state.data.get('anime_id')
          if not anime_id_str:
              content_logger.error(f"Missing anime_id in state data while displaying episode menu (date) for admin {user_id}.")
              await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing anime ID in state.", disable_web_page_preview=True)
              await clear_user_state(user_id)
              await manage_content_command(client, message); return

          # Need highest episode number for NEXT button... similar fetch as above
          try:
              season_doc_episodes = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}, {"seasons.$.episodes.episode_number": 1})
              max_episode_number_in_season = max([ep.get("episode_number", 0) for ep in season_doc_episodes["seasons"][0]["episodes"]]) if (season_doc_episodes and season_doc_episodes.get("seasons") and season_doc_episodes["seasons"][0].get("episodes")) else episode_number
          except Exception as e:
               content_logger.warning(f"Failed to determine max episode number for 'Next Episode' button (date view) for admin {user_id}: {e}")
               max_episode_number_in_season = episode_number # Use current if failed


          # Options: Add file (removes release date), go to next episode, remove episode
          buttons = [
             [InlineKeyboardButton(strings.BUTTON_ADD_EPISODE_FILE, callback_data=f"content_add_file_version{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
             [InlineKeyboardButton(strings.BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number + 1}")],
              # Remove Episode button needs a confirmation step? Or remove directly? Direct removal for simplicity.
              # content_remove_episode|<anime_id>|<season>|<ep>
             [InlineKeyboardButton(strings.BUTTON_REMOVE_EPISODE.format(episode_number=episode_number), callback_data=f"content_remove_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
          ]
     else: # No files and no release date set
         menu_text = f"🛠️ <b><u>Manage Episode</u></b> <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> 🛠️\n\n"
         menu_text += f"❓ No files or release date set yet for this episode.\n\n"

         user_state = asyncio.run(get_user_state(user_id)) # Get state data for anime_id
         anime_id_str = user_state.data.get('anime_id')
         if not anime_id_str:
             content_logger.error(f"Missing anime_id in state data while displaying episode menu (no content) for admin {user_id}.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing anime ID in state.", disable_web_page_preview=True)
             await clear_user_state(user_id)
             await manage_content_command(client, message); return


          # Need highest episode number for NEXT button...
         try:
              season_doc_episodes = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}, {"seasons.$.episodes.episode_number": 1})
              max_episode_number_in_season = max([ep.get("episode_number", 0) for ep in season_doc_episodes["seasons"][0]["episodes"]]) if (season_doc_episodes and season_doc_episodes.get("seasons") and season_doc_episodes["seasons"][0].get("episodes")) else episode_number
         except Exception as e:
               content_logger.warning(f"Failed to determine max episode number for 'Next Episode' button (no content) for admin {user_id}: {e}")
               max_episode_number_in_season = episode_number


         # Options: Add file, Add release date, go to next episode, remove episode
         buttons = [
             [InlineKeyboardButton(strings.BUTTON_ADD_EPISODE_FILE, callback_data=f"content_add_file_version{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
             [InlineKeyboardButton(strings.BUTTON_ADD_RELEASE_DATE, callback_data=f"content_add_release_date{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
             [InlineKeyboardButton(strings.BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number + 1}")],
             # Remove Episode button
             [InlineKeyboardButton(strings.BUTTON_REMOVE_EPISODE.format(episode_number=episode_number), callback_data=f"content_remove_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
         ]


     # Add navigation buttons: Back to episode list, Home CM Menu, Home Bot Menu
     buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"content_select_season{config.CALLBACK_DATA_SEPARATOR}{user_state.data.get('anime_id')}{config.CALLBACK_DATA_SEPARATOR}{season_number}")]) # Back to episodes list for this season
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")]) # Back to main CM menu
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Back to main user menu


     reply_markup = InlineKeyboardMarkup(buttons)

     # Edit the message (the episode list menu) to display this episode management menu
     await edit_or_send_message(
          client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True
     )

# handle_add_release_date_callback and handle_awaiting_release_date_input implemented previously

# handle_remove_episode_callback needs implementation
@Client.on_callback_query(filters.regex(f"^content_remove_episode{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_remove_episode_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Remove Episode button. Initiates confirmation."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_remove_episode|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be MANAGING_EPISODE_MENU
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODE_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking remove episode. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for removing episode.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse episode context from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for removing episode.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        # Ensure callback data matches state context as safety
        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for remove episode: {user_state.data} vs callback {data}. Updating state data.")
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number})
             await set_user_state(user_id, user_state.handler, user_state.step, data=user_state.data)


        # --- Initiate Confirmation State/Menu ---
        # Set state to CONFIRM_REMOVE_EPISODE, preserving episode context
        await set_user_state(user_id, "content_management", ContentState.CONFIRM_REMOVE_EPISODE, data=user_state.data)

        # Display confirmation message and buttons
        confirm_text = f"💀 **<u>Confirm Episode Removal</u>** 💀\n\nAre you absolutely sure you want to permanently remove Episode <b>__{episode_number:02d}__</b> from Season <b>__{season_number}__</b> of <b>{user_state.data.get('anime_name', 'Anime')}</b>?\n\n<b>THIS WILL PERMANENTLY DELETE ALL FILE VERSIONS AND DATA FOR THIS EPISODE. THIS CANNOT BE UNDONE.</b>"

        buttons = [
            [InlineKeyboardButton("✅ Yes, Remove PERMANENTLY", callback_data=f"content_confirm_remove_episode_final{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")], # New callback for final confirmation
            [InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data=f"content_cancel_remove_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")], # Specific cancel for this process, routes back
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        # Edit the episode management menu message to show confirmation
        await edit_or_send_message(client, chat_id, message_id, confirm_text, reply_markup, disable_web_page_preview=True)


    except Exception as e:
        content_logger.error(f"FATAL error handling content_remove_episode (init confirmation) callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message);

# Callback for final confirmation of episode removal
# Catches callbacks content_confirm_remove_episode_final|<anime_id>|<season>|<ep>
@Client.on_callback_query(filters.regex(f"^content_confirm_remove_episode_final{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_confirm_remove_episode_final_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin finally confirming episode removal after confirmation prompt."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_confirm_remove_episode_final|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Removing episode permanently...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be CONFIRM_REMOVE_EPISODE
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.CONFIRM_REMOVE_EPISODE):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking confirm episode final. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for finalizing episode removal.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse context from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for confirming episode removal.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        # Ensure callback data matches state context
        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for final remove episode: {user_state.data} vs callback {data}. Data mismatch!")
             # Treat mismatch as error, clear state
             await edit_or_send_message(client, chat_id, message_id, "💔 Data mismatch. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return # Clear broken state


        # --- Perform the database update: remove the episode ---
        # Use $pull operator within $set to remove the specific episode subdocument from the episodes array
        update_result = await MongoDB.anime_collection().update_one(
             {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}, # Filter by anime and season
             {"$pull": {"seasons.$.episodes": {"episode_number": episode_number}}}, # Pull element from episodes array by number
             # Need to also update last_updated_at on the anime document
             # Using two update operations is safer/simpler than a single complex one
             # await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"last_updated_at": datetime.now(timezone.utc)}})
             # Let's add the timestamp update to the same operation as $pull on MongoDB 4.2+ or separate.
             # $pull does cause modifiedCount to increment on parent. Add timestamp in separate.
             # result = await MongoDB.anime_collection().update_one(... $pull ...)

        )
        # Add separate update for last_updated_at
        await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"last_updated_at": datetime.now(timezone.utc)}})


        if update_result.matched_count > 0: # Anime/Season found
             if update_result.modified_count > 0:
                  # Episode successfully removed
                  content_logger.info(f"Admin {user_id} successfully removed Episode {episode_number} from anime {anime_id_str} S{season_number}.")
                  await edit_or_send_message(client, chat_id, message_id, f"✅ Permanently removed Episode **<u>{episode_number:02d}</u>**.", disable_web_page_preview=True)

                  # --- Transition back to the episodes list menu ---
                  # Clear the CONFIRM_REMOVE_EPISODE state
                  # Set state back to MANAGING_EPISODES_LIST for this season
                  await set_user_state(
                       user_id,
                       "content_management",
                       ContentState.MANAGING_EPISODES_LIST,
                       data={k: v for k,v in user_state.data.items() if k not in ["episode_number", "temp_upload", "temp_metadata", "selected_audio_languages", "selected_subtitle_languages"]} # Clean state data, preserve episode context only needed for display
                  )


                  # Fetch the updated episode list for the season and re-display the episodes list menu
                  # Fetch only the season document containing the episodes list
                  filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
                  projection_season_episodes = {"name": 1, "seasons.$": 1} # Project matched season

                  anime_doc = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes)

                  if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
                       anime_name = anime_doc.get("name", "Anime Name Unknown")
                       season_data = anime_doc["seasons"][0]
                       episodes_list = season_data.get("episodes", [])
                       episodes_list.sort(key=lambda e: e.get("episode_number", 0)) # Sort

                       await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_name, season_number, episodes_list)

                  else:
                       # Failed to re-fetch the episode list for the season after removal
                       content_logger.error(f"Failed to re-fetch anime/season after episode removal {anime_id_str}/S{season_number} for admin {user_id}.", exc_info=True)
                       await client.send_message(chat_id, "💔 Removed episode, but failed to reload episodes list.", parse_mode=config.PARSE_MODE)
                       # State is set correctly. User can navigate back.
                       await manage_content_command(client, callback_query.message); # Offer to restart CM

             else: # Matched count > 0, Modified count == 0 - Episode not found in array
                 content_logger.warning(f"Admin {user_id} clicked confirm remove episode {episode_number} for {anime_id_str} S{season_number} but modified_count was 0. Episode not found in array?")
                 await edit_or_send_message(client, chat_id, message_id, f"⚠️ Episode **<u>{episode_number:02d}</u>** was not found or already removed.", disable_web_page_preview=True)
                 # Go back to the episodes list view which will show the current state
                 filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
                 projection_season_episodes = {"name": 1, "seasons.$": 1}
                 anime_doc = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes)
                 if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
                      anime_name = anime_doc.get("name", "Anime Name Unknown")
                      season_data = anime_doc["seasons"][0]
                      episodes_list = season_data.get("episodes", [])
                      episodes_list.sort(key=lambda e: e.get("episode_number", 0))
                       # State is set correctly by content_remove_episode...
                       # await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODES_LIST, data=...) # Already set
                      await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_name, season_number, episodes_list)

                 else:
                       content_logger.error(f"Failed to fetch anime/season to reload episode list after failed episode remove {anime_id_str}/S{season_number} for admin {user_id}.", exc_info=True)
                       await client.send_message(chat_id, "💔 Episode not found and failed to reload episodes list.", parse_mode=config.PARSE_MODE)
                       # Fallback to main CM menu
                       await manage_content_command(client, callback_query.message);


        else: # Matched count is 0 - Anime/Season not found
            content_logger.error(f"Anime/Season {anime_id_str}/S{season_number} not found during episode remove operation by admin {user_id} (Episode {episode_number}).")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime or season not found. Cannot remove episode.", disable_web_page_preview=True)
            await clear_user_state(user_id); # Clear state
            await manage_content_command(client, callback_query.message); # Offer to restart CM


    except ValueError:
        content_logger.warning(f"Admin {user_id} invalid callback data format for final remove episode: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid data in callback.", disable_web_page_preview=True)
        # State is CONFIRM_REMOVE_EPISODE, should stay.


    except Exception as e:
        content_logger.error(f"FATAL error handling content_confirm_remove_episode_final callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message)

# Callback to cancel episode removal confirmation, routes back to episode menu
@Client.on_callback_query(filters.regex(f"^content_cancel_remove_episode{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_cancel_remove_episode_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Cancel during episode removal confirmation."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_cancel_remove_episode|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, strings.ACTION_CANCELLED) # Toast confirming cancellation
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be CONFIRM_REMOVE_EPISODE
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.CONFIRM_REMOVE_EPISODE):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking cancel remove episode. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for cancelling episode removal.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Clear the CONFIRM_REMOVE_EPISODE state
        # Set state back to MANAGING_EPISODE_MENU, preserving episode context from the state data
        # Get episode context from the state data *before* clearing
        anime_id_str = user_state.data.get("anime_id")
        season_number = user_state.data.get("season_number")
        episode_number = user_state.data.get("episode_number")
        anime_name = user_state.data.get("anime_name") # Anime name for display

        if not all([anime_id_str, season_number is not None, episode_number is not None, anime_name]):
             content_logger.error(f"Admin {user_id} cancelling episode remove, but missing episode context from state: {user_state.data}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing episode context in state data to return to menu. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return


        # Reset state to MANAGING_EPISODE_MENU
        await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODE_MENU, data={"anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number, "anime_name": anime_name})

        # Fetch the current episode data to redisplay the menu
        # Use MongoDB class method if implemented: await MongoDB.get_episode_details(...)
        # Or fetch anime/season/episode manually
        filter_query = {"_id": ObjectId(anime_id_str)}
        projection = {"name": 1, "seasons": {"$elemMatch": {"season_number": season_number}}}

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

        if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
             season_data = anime_doc["seasons"][0]
             episodes_list = season_data.get("episodes", [])
             current_episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None)

             if current_episode_doc:
                  await edit_or_send_message(client, chat_id, message_id, strings.ACTION_CANCELLED, parse_mode=config.PARSE_MODE) # Edit previous message to confirm cancel
                  await asyncio.sleep(1) # Short delay
                  # Display the episode management menu using the helper
                  await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, current_episode_doc)
             else: raise Exception("Episode not found after cancelling remove confirmation.") # Should re-fetch error block


        else: raise Exception("Anime/Season not found after cancelling remove confirmation.")


    except Exception as e:
        content_logger.error(f"FATAL error handling content_cancel_remove_episode callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message)

# handle_go_next_episode_callback implemented previously

# handle_add_file_version_callback implemented previously, transitions to UPLOADING_FILE state

# handle_episode_file_upload is implemented in common_handlers but calls functions HERE
# handle_episode_file_upload(client, message, user_state, file_obj) needs to route based on received file type
# The one in common_handlers.py already does that:
# - If message.photo: routes to content_handler.handle_awaiting_poster (handles EDITING_POSTER_PROMPT & AWAITING_POSTER)
# - If message.document or message.video: routes to content_handler.handle_episode_file_upload
# This helper handles file AFTER it's determined it's for an episode
async def handle_episode_file_upload(client: Client, message: Message, user_state: UserState, file_obj: Union[Document, Video, Photo]):
    """Handles actual file upload when in UPLOADING_FILE state. Extracts data and prompts for metadata."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id # The ID of the message containing the file

    # Get context (anime_id, season_number, episode_number, anime_name) from state data
    # Ensure these are present! UPLOADING_FILE state should contain this.
    anime_id_str = user_state.data.get("anime_id")
    season_number = user_state.data.get("season_number")
    episode_number = user_state.data.get("episode_number")
    anime_name = user_state.data.get("anime_name", "Anime Name Unknown")

    if not all([anime_id_str, season_number is not None, episode_number is not None]):
         content_logger.error(f"Admin {user_id} uploaded episode file but missing critical episode context from state {user_state.step}: {user_state.data}")
         await message.reply_text("💔 Error: Missing episode context from state data for file upload. Process cancelled.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id); # Clear broken state
         await manage_content_command(client, message); return

    content_logger.info(f"Admin {user_id} uploaded episode file ({file_obj.file_id}) for {anime_name} S{season_number}E{episode_number}.")

    # Extract relevant file details
    temp_upload_data = {
        "file_id": file_obj.file_id,
        "file_unique_id": file_obj.file_unique_id, # Crucial for deleting later!
        "file_name": file_obj.file_name or f"EP{episode_number:02d}_File_{datetime.now().strftime('%Y%m%d%H%M%S')}", # Use Telegram name or generate generic
        "file_size_bytes": file_obj.file_size,
        "mime_type": file_obj.mime_type,
        "duration": getattr(file_obj, 'duration', None), # Optional: Get video/audio duration
        "width": getattr(file_obj, 'width', None), # Optional: Get video width (resolution clue)
        "height": getattr(file_obj, 'height', None), # Optional: Get video height
        "added_at": datetime.now(timezone.utc), # Timestamp of the upload to Telegram
    }

    # Store temporary file details in user's state data. This is important for metadata collection.
    user_state.data["temp_upload"] = temp_upload_data
    # Initialize a dictionary for temporary metadata being collected via buttons
    user_state.data["temp_metadata"] = {
         "quality_resolution": None,
         "audio_languages": [],
         "subtitle_languages": []
     }
    # Add placeholder for selected languages in metadata collection states
    # No, temp_metadata dictionary structure holds selected_languages.

    # Save updated state data including temp_upload and temp_metadata
    await set_user_state(user_id, "content_management", ContentState.UPLOADING_FILE, data=user_state.data) # Still in UPLOADING_FILE state briefly


    # Transition to the next logical state: Starting Metadata Selection (Quality)
    # Note: Even though file is received, the step is logically now metadata collection.
    await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_QUALITY, data=user_state.data)


    # Send a confirmation message AND the prompt for quality selection
    await message.reply_text(f"✅ File received for Episode {episode_number:02d}!\n\nLoading metadata selection...", parse_mode=config.PARSE_MODE)

    # Send the prompt and buttons for Quality selection
    # Use a helper function to send the quality selection menu
    await prompt_for_metadata_quality(client, chat_id)

# --- File Metadata Selection Implementation (Callbacks and Helpers) ---

# prompt_for_metadata_quality implemented previously, transitions to SELECTING_METADATA_QUALITY
# Called by handle_episode_file_upload
# prompt_for_metadata_quality needs a button_cancel in its markup

# Callback handler for Quality selection buttons (e.g., content_select_quality|1080p)
# Catches callbacks starting with content_select_quality|
@Client.on_callback_query(filters.regex(f"^content_select_quality{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_select_quality_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting file quality via buttons."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message with quality buttons
    data = callback_query.data # content_select_quality|quality_value

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id) # Answer immediately
    except Exception: common_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")

    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_QUALITY
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_QUALITY):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking quality select. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting quality.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse the selected quality value
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for selecting quality.")
        selected_quality = parts[1]

        # No need to validate against presets strictly, as we'll save whatever value is provided.
        # However, a warning could be logged if it's not in presets.
        if selected_quality not in config.QUALITY_PRESETS:
             content_logger.warning(f"Admin {user_id} selected non-preset quality: {selected_quality}. Saving anyway.")
             await callback_query.answer("⚠️ Non-preset quality selected. Saving anyway.", show_alert=False) # Toast


        # Store selected quality in the 'temp_metadata' dictionary in state data.
        # Ensure temp_metadata dictionary exists.
        user_state.data["temp_metadata"] = user_state.data.get("temp_metadata", {}) # Initialize if missing
        user_state.data["temp_metadata"]["quality_resolution"] = selected_quality


        # Move to the next state: SELECTING_METADATA_AUDIO
        await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_AUDIO, data=user_state.data) # Pass the updated state data


        # Prompt for Audio Languages selection (Callback-based, multi-select)
        # Send a new message with the next prompt and keyboard.
        # The text of the message can indicate the previously selected quality.
        # Pass an empty list as current_selection for audio, as it's a new selection.
        audio_prompt_text = f"🎧 Quality selected: <b><u>{selected_quality}</u></b>.\n\n" + strings.PROMPT_AUDIO_LANGUAGES_BUTTONS # Combine confirmation and next prompt
        await client.send_message(chat_id, audio_prompt_text, parse_mode=config.PARSE_MODE) # Send new message
        await prompt_for_metadata_audio(client, chat_id, []) # Helper sends the audio selection buttons


    except Exception as e:
        content_logger.error(f"FATAL error handling content_select_quality callback {data} for admin {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await clear_user_state(user_id); # Clear state
        await manage_content_command(client, callback_query.message); # Offer to restart CM

# prompt_for_metadata_audio implemented previously, sends buttons for SELECTING_METADATA_AUDIO
# Called by handle_select_quality_callback

# Handler for Audio Language toggling (multi-select) - e.g., content_toggle_audio|Japanese
# Catches callbacks starting with content_toggle_audio|
@Client.on_callback_query(filters.regex(f"^content_toggle_audio{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_toggle_audio_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin toggling audio language selection via buttons."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message with audio buttons
    data = callback_query.data # content_toggle_audio|language_value

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    # Acknowledge immediately (silent toast)
    try: await client.answer_callback_query(message.id)
    except Exception: common_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")


    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_AUDIO
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_AUDIO):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking audio toggle {data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting audio.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse the language name from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for toggling audio language.")
        language_to_toggle = parts[1]

        # Get currently selected audio languages from the 'temp_metadata' dictionary in state data.
        # Initialize temp_metadata and its audio_languages key if they don't exist.
        user_state.data["temp_metadata"] = user_state.data.get("temp_metadata", {})
        selected_audio_languages = user_state.data["temp_metadata"].get("audio_languages", [])

        # Toggle the language in the selected list
        if language_to_toggle in selected_audio_languages:
            selected_audio_languages.remove(language_to_toggle)
            content_logger.debug(f"Admin {user_id} unselected audio language: {language_to_toggle}")
        else:
             selected_audio_languages.append(language_to_toggle)
             content_logger.debug(f"Admin {user_id} selected audio language: {language_to_toggle}")

        # Sort selected languages for consistency (optional)
        selected_audio_languages.sort()

        # Update the selected audio languages list in state data
        user_state.data["temp_metadata"]["audio_languages"] = selected_audio_languages
        # Save the entire updated state data (including temp_upload, quality, and now audio selection) back to DB.
        # User remains in the same SELECTING_METADATA_AUDIO step.
        await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_AUDIO, data=user_state.data)


        # Re-create the audio language selection keyboard to reflect updated selection states
        # Use prompt_for_metadata_audio helper, passing the *updated* selected_audio_languages
        # This helper will send a NEW message? No, the logic needs to EDIT the existing message's reply_markup.
        # We need to replicate keyboard creation logic here and use edit_reply_markup.
        audio_languages_presets = config.AUDIO_LANGUAGES_PRESETS # Get presets
        buttons = []
        for lang in audio_languages_presets:
            is_selected = lang in selected_audio_languages # Check against the *updated* list
            button_text = f"🎧 {lang}" if is_selected else f"⬜ {lang}" # Use emoji for state
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_audio{config.CALLBACK_DATA_SEPARATOR}{lang}")) # Keep the same callback data


        # Arrange buttons into rows
        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

        # Add Done and Cancel buttons
        keyboard_rows.append([
             InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Audio Languages"), callback_data="content_audio_done"),
             InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        # Edit ONLY the reply markup of the message containing the audio buttons
        try:
             await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        except MessageNotModified:
            # Ignore if reply markup is unchanged
            common_logger.debug(f"Admin {user_id} clicked audio toggle, but reply_markup was unchanged for msg {message_id}.")
            pass
        except FloodWait as e:
            content_logger.warning(f"FloodWait while editing audio buttons for admin {user_id} (retry in {e.value}s) for msg {message_id}: {e}")
            await asyncio.sleep(e.value)
            try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup) # Retry
            except Exception as retry_e: content_logger.error(f"Retry failed editing audio buttons for admin {user_id} (msg {message_id}): {retry_e}", exc_info=True)

    except Exception as e:
        content_logger.error(f"FATAL error handling content_toggle_audio callback {data} for admin {user_id}: {e}", exc_info=True)
        # Clear state on complex error
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message); # Offer to restart CM


# Handler for the "Done Selecting Audio" button - Catches content_audio_done
@Client.on_callback_query(filters.regex("^content_audio_done$") & filters.private)
async def handle_audio_done_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Done after selecting audio languages."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message with audio buttons

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    # Acknowledge
    try: await client.answer_callback_query(message.id, "Audio languages selected. Proceeding to subtitles...")
    except Exception: common_logger.warning(f"Failed to answer callback query content_audio_done from admin {user_id}.")


    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_AUDIO
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_AUDIO):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking Done Audio. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Your previous process was cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    # Retrieve selected audio languages from state data
    temp_metadata = user_state.data.get("temp_metadata", {})
    selected_audio_languages = temp_metadata.get("audio_languages", [])
    content_logger.info(f"Admin {user_id} finished selecting audio languages: {selected_audio_languages}")

    # Store audio selection (already in state data from toggle callback), no need to re-add.

    # Move to the next state: SELECTING_METADATA_SUBTITLES
    # State data already contains temp_upload and temp_metadata (with quality and audio)
    await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_SUBTITLES, data=user_state.data)


    # Prompt for Subtitle Languages selection (Callback-based multi-select)
    # Send a new message with the prompt and buttons. The text can confirm audio.
    subtitle_prompt_text = f"🎧 Audio Languages saved: <b>{', '.join(selected_audio_languages) if selected_audio_languages else 'None'}</b>.\n\n" + strings.PROMPT_SUBTITLE_LANGUAGES_BUTTONS # Combine confirmation and prompt

    await client.send_message(chat_id, subtitle_prompt_text, parse_mode=config.PARSE_MODE) # Send NEW message for subtitles selection
    await prompt_for_metadata_subtitles(client, chat_id, []) # Helper sends subtitle selection buttons (starts with empty list)

    # Optionally, edit the previous audio selection message to indicate done/proceeding
    try:
         # Edit the message that contained the audio buttons (to remove those buttons)
         await callback_query.message.edit_text(
              f"🎧 Audio Languages saved: <b>{', '.join(selected_audio_languages) if selected_audio_languages else 'None'}</b>.",
               parse_mode=config.PARSE_MODE,
               reply_markup=None # Remove buttons after clicking 'Done'
          )
    except MessageNotModified: pass # Ignore if already edited or no buttons


    except Exception as e:
        content_logger.error(f"FATAL error handling content_audio_done callback for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message)


# prompt_for_metadata_subtitles implemented previously, sends buttons for SELECTING_METADATA_SUBTITLES
# Called by handle_audio_done_callback

# Handler for Subtitle Language toggling (multi-select) - e.g., content_toggle_subtitle|English
# Catches callbacks starting with content_toggle_subtitle|
@Client.on_callback_query(filters.regex(f"^content_toggle_subtitle{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_toggle_subtitle_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin toggling subtitle language selection via buttons."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message with subtitle buttons
    data = callback_query.data # content_toggle_subtitle|language_value

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id) # Acknowledge immediately
    except Exception: common_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")

    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_SUBTITLES
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_SUBTITLES):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking subtitle toggle {data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting subtitles.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse the language name from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for toggling subtitle language.")
        language_to_toggle = parts[1]

        # Get currently selected subtitle languages from 'temp_metadata' in state data
        user_state.data["temp_metadata"] = user_state.data.get("temp_metadata", {})
        selected_subtitle_languages = user_state.data["temp_metadata"].get("subtitle_languages", [])

         # Ensure the language is a valid preset (sanity check, like with genres)
        if language_to_toggle not in config.SUBTITLE_LANGUAGES_PRESETS:
             content_logger.warning(f"Admin {user_id} attempted to toggle non-preset subtitle: {language_to_toggle}.")
             await callback_query.answer("🚫 Invalid subtitle option.", show_alert=False)
             return


        # Toggle the language in the selected list
        if language_to_toggle in selected_subtitle_languages:
            selected_subtitle_languages.remove(language_to_toggle)
            content_logger.debug(f"Admin {user_id} unselected subtitle language: {language_to_toggle}")
        else:
             selected_subtitle_languages.append(language_to_toggle)
             content_logger.debug(f"Admin {user_id} selected subtitle language: {language_to_toggle}")

        # Sort selected languages for consistency
        selected_subtitle_languages.sort()

        # Update the selected subtitle languages list in state data
        user_state.data["temp_metadata"]["subtitle_languages"] = selected_subtitle_languages
        # Save the updated state data back to DB. User remains in the same state.
        await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_SUBTITLES, data=user_state.data)


        # Re-create the subtitle selection keyboard to reflect updated states
        subtitle_languages_presets = config.SUBTITLE_LANGUAGES_PRESETS
        buttons = []
        for lang in subtitle_languages_presets:
            is_selected = lang in selected_subtitle_languages # Check against *updated* list
            button_text = f"📝 {lang}" if is_selected else f"⬜ {lang}" # Use emoji
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_subtitle{config.CALLBACK_DATA_SEPARATOR}{lang}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

        buttons_done_cancel = [
             InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Subtitle Languages"), callback_data="content_subtitles_done"),
             InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
        ]
        keyboard_rows.append(buttons_done_cancel) # Add Done and Cancel buttons

        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        # Edit ONLY the reply markup of the message containing the subtitle buttons
        try:
             await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        except MessageNotModified:
            common_logger.debug(f"Admin {user_id} clicked subtitle toggle, but reply_markup was unchanged for msg {message_id}.")
            pass
        except FloodWait as e:
            content_logger.warning(f"FloodWait while editing subtitle buttons for admin {user_id} (retry in {e.value}s) for msg {message_id}: {e}")
            await asyncio.sleep(e.value)
            try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup) # Retry
            except Exception as retry_e: content_logger.error(f"Retry failed editing subtitle buttons for admin {user_id} (msg {message_id}): {retry_e}", exc_info=True)


    except Exception as e:
        content_logger.error(f"FATAL error handling content_toggle_subtitle callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id) # Clear state
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message); # Offer to restart CM

# Handler for the "Done Selecting Subtitles" button - Catches content_subtitles_done
@Client.on_callback_query(filters.regex("^content_subtitles_done$") & filters.private)
async def handle_subtitles_done_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Done after selecting subtitle languages. FINALIZES FILE VERSION ADDITION."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message with subtitle buttons

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    # Acknowledge
    try: await client.answer_callback_query(message.id, "Subtitle languages selected. Saving file version...")
    except Exception: common_logger.warning(f"Failed to answer callback query content_subtitles_done from admin {user_id}.")


    user_state = await get_user_state(user_id)
    # State should be SELECTING_METADATA_SUBTITLES
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_SUBTITLES):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking Done Subtitles. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Your previous process was cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    # --- Collect ALL Data and Save the FileVersion to the Database ---
    # Retrieve temp file details AND collected metadata from user_state.data
    temp_upload_data = user_state.data.get("temp_upload") # File ID, size, unique_id etc.
    temp_metadata = user_state.data.get("temp_metadata") # Quality, audio, subtitle selections

    # Retrieve episode context (anime_id, season_number, episode_number) from state data
    anime_id_str = user_state.data.get("anime_id")
    season_number = user_state.data.get("season_number")
    episode_number = user_state.data.get("episode_number")

    # Validate that all necessary data is present
    if not all([temp_upload_data, temp_metadata, anime_id_str, season_number is not None, episode_number is not None]):
        content_logger.error(f"Admin {user_id} finished metadata selection but missing required data from state for saving file version: temp_upload={bool(temp_upload_data)}, temp_metadata={bool(temp_metadata)}, context_ids={all([anime_id_str, season_number is not None, episode_number is not None])}. State data: {user_state.data}")
        await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing required data from state to save file version. Process cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); return # Clear broken state


    # Ensure essential metadata keys exist and are in expected format (dict, lists)
    # Get selected metadata, providing defaults if keys are missing
    selected_quality = temp_metadata.get("quality_resolution")
    selected_audio_languages = temp_metadata.get("audio_languages", []) # Default to empty list if missing
    selected_subtitle_languages = temp_metadata.get("subtitle_languages", []) # Default to empty list if missing

    if not selected_quality or not isinstance(selected_audio_languages, list) or not isinstance(selected_subtitle_languages, list):
        content_logger.error(f"Admin {user_id} finished metadata, but collected metadata structure is invalid. Temp metadata: {temp_metadata}")
        await edit_or_send_message(client, chat_id, message_id, "💔 Error: Invalid metadata collected. File version not saved. Process cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); return


    # Build the data for the FileVersion Pydantic model instance
    # Combine temporary file details with collected metadata
    file_version_data_dict = {
         "file_id": temp_upload_data.get("file_id"),
         "file_unique_id": temp_upload_data.get("file_unique_id"), # Crucial!
         "file_name": temp_upload_data.get("file_name", "Unnamed File"),
         "file_size_bytes": temp_upload_data.get("file_size_bytes", 0),
         "quality_resolution": selected_quality,
         "audio_languages": selected_audio_languages,
         "subtitle_languages": selected_subtitle_languages,
         "added_at": datetime.now(timezone.utc), # Set addition time in DB using server time via Pydantic default_factory
         # Can add other metadata extracted from message if needed (mime_type, duration, dimensions)
     }

    # Use Pydantic model to validate data before inserting as subdocument
    try:
         new_file_version = FileVersion(**file_version_data_dict)
         content_logger.debug(f"Admin {user_id} built FileVersion model: {new_file_version.dict()}")
    except Exception as e:
        content_logger.error(f"Error creating FileVersion model for admin {user_id} before save: {e}. Data: {file_version_data_dict}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, "💔 Error validating file data before saving. File version not saved. Process cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); return


    # --- Add the new FileVersion subdocument to the specific Episode in the Database ---
    # Use the database helper method for this complex update
    try:
        success = await MongoDB.add_file_version_to_episode(
            anime_id=anime_id_str,
            season_number=season_number,
            episode_number=episode_number,
            file_version=new_file_version # Pass the Pydantic model instance
        )

        if success:
            content_logger.info(f"Admin {user_id} successfully added file version ({new_file_version.quality_resolution}, {new_file_version.file_unique_id}) to {anime_id_str}/S{season_number}E{episode_number}.")
            await edit_or_send_message(
                 client,
                 chat_id,
                 message_id,
                 strings.FILE_ADDED_SUCCESS.format(
                     episode_number=episode_number,
                     quality=new_file_version.quality_resolution,
                     audio=', '.join(new_file_version.audio_languages), # Use formatted language strings
                     subs=', '.join(new_file_version.subtitle_languages)
                 ),
                 disable_web_page_preview=True
            )

            # --- Transition back to the episode management menu ---
            # Need to fetch the *updated* episode data from the database to display the correct menu (with the new file version listed)
            # Fetch just the specific episode's context and content
            filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}
            projection = {"name": 1, "seasons.$": 1} # Project anime name and the matched season


            anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

            if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
                 anime_name_for_menu = anime_doc.get("name", "Anime Name Unknown")
                 season_data = anime_doc["seasons"][0]
                 episodes_list = season_data.get("episodes", []) # Episodes list within the season
                 # Find the *updated* episode doc within this list
                 updated_episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None)

                 if updated_episode_doc:
                     # Clear all temporary file upload and metadata collection states/data
                     updated_state_data = {k: v for k, v in user_state.data.items() if k not in ["temp_upload", "temp_metadata"]}
                     # Set state back to managing this specific episode
                     await set_user_state(
                          user_id,
                          "content_management",
                          ContentState.MANAGING_EPISODE_MENU, # Back to episode options state
                          data={**updated_state_data} # Preserve original episode context data
                     )
                     await asyncio.sleep(1) # Short delay before next menu
                     # Display the episode management menu using the helper (needs episode doc)
                     await display_episode_management_menu(client, callback_query.message, anime_name_for_menu, season_number, episode_number, updated_episode_doc)

                 else: # Failed to find the updated episode document in the fetched season data. Error!
                      content_logger.error(f"Failed to find updated episode document after saving file version for admin {user_id}. Anime ID: {anime_id_str}, S:{season_number}, E:{episode_number}.", exc_info=True)
                      # Clear state and inform admin that menu couldn't load
                      await client.send_message(chat_id, "💔 Saved file, but failed to load episode management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                      await clear_user_state(user_id); # Clear broken state
                      await manage_content_command(client, callback_query.message) # Offer to restart CM

            else:
                 # Failed to re-fetch the anime/season document after saving the file. Critical error.
                 content_logger.critical(f"FATAL: Failed to fetch anime/season document after saving file version for admin {user_id}: {anime_id_str}/S{season_number}.", exc_info=True)
                 await client.send_message(chat_id, "💔 Saved file version, but a critical error occurred reloading data. Please navigate manually from Content Management menu.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id); # Clear broken state
                 await manage_content_command(client, callback_query.message) # Offer to restart CM

        else: # update_result.matched_count is 0 (Anime/Season/Episode not found during update) OR modified_count is 0 (unlikely after $push if matched)
             # Modified count being 0 with $push is usually unexpected if matched. Asssume matched_count is 0 = episode path not found.
             content_logger.error(f"Failed to find episode {anime_id_str}/S{season_number}E{episode_number} to push file version. Modified 0 docs. Admin {user_id}.", exc_info=True)
             await edit_or_send_message(client, chat_id, message_id, "⚠️ Failed to add file version to episode. Episode path not found in database.", disable_web_page_preview=True)
             await clear_user_state(user_id); # Clear state as the path in DB is likely broken
             await manage_content_command(client, callback_query.message); # Offer to restart CM

    except Exception as e:
        # Error during database update or data processing
        content_logger.critical(f"FATAL error handling content_subtitles_done callback for admin {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await clear_user_state(user_id) # Clear state
        await manage_content_command(client, callback_query.message)

# --- Implement File Version Deletion Workflow (Selection and Confirmation) ---

# handlers/content_handler.py (File Version Deletion Finalization)
# ... (previous imports and code in content_handler.py) ...


# Callback to trigger the file version selection menu for deletion (Continued)
# Catches callbacks content_delete_file_version_select|<anime_id>|<season>|<ep>
@Client.on_callback_query(filters.regex(f"^content_delete_file_version_select{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_delete_file_version_select_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking 'Delete File Version(s)', displays versions to select for removal."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_delete_file_version_select|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Select file version to remove...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be MANAGING_EPISODE_MENU
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODE_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking delete file select. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting file version to remove.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse context from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for deleting file version selection.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

         # Ensure callback data matches state context
        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for delete file select: {user_state.data} vs callback {data}. Updating state data.")
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number})
             await set_user_state(user_id, user_state.handler, user_state.step, data=user_state.data) # Save updated state data


        # Fetch the specific episode document to get its file versions
        # Need to filter anime by ID, then season by number, then episode by number
        # Projection to get only the file versions array from that specific episode
        filter_query = {"_id": ObjectId(anime_id_str)}
        # Using $elemMatch and dot notation to target the specific episode within its season within the anime
        # Projecting specifically the files array and maybe anime name for context
        projection = {
            "name": 1,
             "seasons": {
                  "$elemMatch": { # Find the season
                       "season_number": season_number,
                       "episodes": { # Find the episode within the season
                            "$elemMatch": {
                                "episode_number": episode_number,
                                "files": 1 # Project the files array for this specific episode
                                # If episode_count_declared or release_date is also needed here, add them: "episode_count_declared":1, "release_date":1
                           }
                      }
                 }
            }
         }

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)


        # Validate if anime/season/episode found and files list exists
        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0] or not anime_doc["seasons"][0].get("episodes") or not anime_doc["seasons"][0]["episodes"][0]:
             content_logger.error(f"Anime/Season/Episode not found for deleting file version {anime_id_str}/S{season_number}E{episode_number} for admin {user_id}. Or no episodes array/data.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Episode not found or no files available for deletion.", disable_web_page_preview=True)
             # Go back to episodes list for safety
             filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection_season_episodes = {"name": 1, "seasons.$": 1}
             anime_doc_season = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes)
             if anime_doc_season and anime_doc_season.get("seasons") and anime_doc_season["seasons"][0]:
                  episodes_list = anime_doc_season["seasons"][0].get("episodes", [])
                  episodes_list.sort(key=lambda e: e.get("episode_number", 0)) # Sort
                  # Set state back to episodes list
                  await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODES_LIST, data={"anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_doc_season.get("name", "Anime")})

                  await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_doc_season.get("name", "Anime Name"), season_number, episodes_list)
             else:
                 content_logger.error(f"Failed to fetch anime/season after episode not found for file delete for admin {user_id}. Cannot re-display list.")
                 await edit_or_send_message(client, chat_id, message_id, "💔 Error loading episode list.", disable_web_page_preview=True)
                 await clear_user_state(user_id); await manage_content_command(client, callback_query.message); # Fallback

             return # Stop

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        # Access the specific episode document from the nested projection results
        # The result of $elemMatch on two levels creates a complex nested structure
        # The structure will be like: {"_id":..., "name":..., "seasons": [{"season_number": ..., "episodes": [{"episode_number":..., "files":[...]}]}]}
        # Need to navigate this to get the files list.
        # Safety: Ensure 'seasons' and 'episodes' exist at the projected paths.
        try:
             episode_data_proj = anime_doc["seasons"][0]["episodes"][0] # The deeply nested episode doc with files projected
             files = episode_data_proj.get("files", []) # Get the list of file version dicts from *that* episode
        except (KeyError, IndexError) as e:
            content_logger.error(f"Error accessing deeply nested files list in projected document for {anime_id_str}/S{season_number}E{episode_number} for admin {user_id}: {e}. Doc: {anime_doc}", exc_info=True)
            await edit_or_send_message(client, chat_id, message_id, "💔 Error accessing file data. Cannot display versions for deletion.", disable_web_page_preview=True)
            # Go back to episode menu, state should be ManagingEpisodeMenu
            # Need to refetch episode data for display_episode_management_menu
            # content_manage_episode|<anime_id>|<season>|<ep> callback has logic to fetch and display episode menu.
            await handle_select_episode_callback(client, callback_query.message, user_state, f"content_manage_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")

            return # Stop


        if not files:
            content_logger.warning(f"Admin {user_id} attempted to delete file version but no files found for {anime_id_str}/S{season_number}E{episode_number}. Displayed selection anyway.")
            await edit_or_send_message(client, chat_id, message_id, "🤔 No file versions found for this episode to remove.", disable_web_page_preview=True)
            # State is MANAGING_EPISODE_MENU. Can leave them here.
            # Re-display the episode menu might be better to show current state accurately.
            # Need to refetch episode data again
            # handle_select_episode_callback(client, callback_query.message, user_state, f"content_manage_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")

            return # Stop


        # --- Transition to Selecting File Version to Delete State ---
        # Set state to SELECT_FILE_VERSION_TO_DELETE, storing episode context and the files list for display
        await set_user_state(
             user_id,
             "content_management",
             ContentState.SELECT_FILE_VERSION_TO_DELETE,
             data={
                 **user_state.data, # Preserve existing context (anime_id, season, episode, name)
                 "file_versions": files # Store the list of file version dictionaries
             }
        )

        menu_text = f"🗑️ <b><u>Delete File Version</u></b> 🗑️\n\nSelect the version you want to **<u>permanently remove</u>** for <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b>:"
        buttons = []

        # Create buttons for each file version using details from the 'files' list stored in state data
        # These buttons will trigger the confirmation handler directly
        for i, file_ver_dict in enumerate(files):
            # Access dictionary keys safely
            quality = file_ver_dict.get('quality_resolution', 'Unknown Quality')
            size_bytes = file_ver_dict.get('file_size_bytes', 0)
            audio_langs = file_ver_dict.get('audio_languages', [])
            subs_langs = file_ver_dict.get('subtitle_languages', [])
            file_unique_id = file_ver_dict.get('file_unique_id', None)

            # Cannot create a delete button if file_unique_id is missing - data inconsistency!
            if file_unique_id is None:
                content_logger.error(f"File version dictionary in DB/state missing file_unique_id for {anime_id_str}/S{season_number}E{episode_number} index {i}. Skipping button.")
                continue # Skip this entry


            # Format button label: "❌ Quality (Size) Audio / Subs"
            formatted_size = f"{size_bytes / (1024 * 1024):.2f} MB" if size_bytes > 0 else "0 MB"
            if size_bytes >= 1024 * 1024 * 1024: formatted_size = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
            audio_str = ', '.join(audio_langs) if audio_langs else 'N/A'
            subs_str = ', '.join(subs_langs) if subs_langs else 'None'

            button_label = f"❌ {quality} ({formatted_size}) 🎧 {audio_str} 📝 {subs_str}"

            # Callback data for final confirmation: content_confirm_remove_file_version|<anime_id>|<season>|<ep>|<file_unique_id>
            buttons.append([InlineKeyboardButton(button_label, callback_data=f"content_confirm_remove_file_version{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}{config.CALLBACK_DATA_SEPARATOR}{file_unique_id}")])


        # Add Back button to episode management menu (Returns to the specific episode's options menu)
        buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"content_manage_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")])
        # Add other navigation buttons if needed (CM main, Home)

        reply_markup = InlineKeyboardMarkup(buttons)


        # Edit the episode management menu message to display file version selection for deletion.
        await edit_or_send_message(
             client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True
         )


    except ValueError:
         content_logger.warning(f"Admin {user_id} invalid callback data format for delete file version select: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid data in callback.", disable_web_page_preview=True)
         # State is MANAGING_EPISODE_MENU. Let admin retry clicking.

    except Exception as e:
        content_logger.error(f"FATAL error handling content_delete_file_version_select callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message); # Offer to restart CM

# Callback for final confirmation of file version removal
# Catches callbacks content_confirm_remove_file_version|<anime_id>|<season>|<ep>|<file_unique_id>
@Client.on_callback_query(filters.regex(f"^content_confirm_remove_file_version{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_confirm_remove_file_version_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin confirming a specific file version removal."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_confirm_remove_file_version|<anime_id>|<season>|<ep>|<file_unique_id>

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Removing file version permanently...") # Indicate ongoing process
    except Exception: pass


    user_state = await get_user_state(user_id)
    # State should be SELECT_FILE_VERSION_TO_DELETE
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECT_FILE_VERSION_TO_DELETE):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking confirm remove file version. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for confirming file version removal.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse context from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 5: raise ValueError("Invalid callback data format for confirming file version removal.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])
        file_unique_id_to_remove = parts[4] # The unique identifier for the file version

         # Ensure callback data matches state context as safety
        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for final remove file version: {user_state.data} vs callback {data}. Data mismatch!")
             # Treat mismatch as error, clear state
             await edit_or_send_message(client, chat_id, message_id, "💔 Data mismatch. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return # Clear broken state

        content_logger.info(f"Admin {user_id} confirming remove file version {file_unique_id_to_remove} from {anime_id_str}/S{season_number}E{episode_number}.")

        # --- Perform the database update: remove the file version ---
        # Use $pull operator on the nested files array, targeting the element by its unique_id
        success = await MongoDB.delete_file_version_from_episode(
            anime_id=anime_id_str,
            season_number=season_number,
            episode_number=episode_number,
            file_unique_id=file_unique_id_to_remove
        )


        if success:
             content_logger.info(f"Admin {user_id} successfully removed file version {file_unique_id_to_remove} from {anime_id_str}/S{season_number}E{episode_number}.")
             await edit_or_send_message(client, chat_id, message_id, strings.FILE_DELETED_SUCCESS, disable_web_page_preview=True)

             # --- Transition back to the episode management menu ---
             # Need to fetch the updated episode data (files list should be smaller now)
             # Clear the SELECT_FILE_VERSION_TO_DELETE state and any specific file data in state
             # Preserve original episode context in state
             updated_state_data = {k: v for k,v in user_state.data.items() if k not in ["file_versions"]} # Remove the list of file versions

             await set_user_state(
                  user_id,
                  "content_management",
                  ContentState.MANAGING_EPISODE_MENU, # Back to episode options state
                  data={**updated_state_data}
              )


             # Fetch the specific episode's current data from DB to re-display the menu.
             filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection = {"name": 1, "seasons.$": 1} # Project name and the matched season

             anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

             if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
                  anime_name = anime_doc.get("name", "Anime Name Unknown")
                  season_data = anime_doc["seasons"][0]
                  episodes_list = season_data.get("episodes", []) # Episodes of this season
                  # Find the correct episode doc (will have updated files array)
                  updated_episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None)

                  if updated_episode_doc:
                       await asyncio.sleep(1) # Short delay before menu
                       await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, updated_episode_doc)
                  else:
                       content_logger.error(f"Failed to find updated episode document after removing file version for admin {user_id}. Anime ID: {anime_id_str}, S:{season_number}, E:{episode_number}.", exc_info=True)
                       # Clear state and prompt for navigation
                       await client.send_message(chat_id, "💔 Removed file version, but failed to load episode management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                       await clear_user_state(user_id); await manage_content_command(client, callback_query.message) # Offer to restart CM


             else:
                  # Failed to re-fetch anime/season after removing file version.
                 content_logger.critical(f"FATAL: Failed to fetch anime/season document after removing file version for admin {user_id}: {anime_id_str}/S{season_number}.", exc_info=True)
                 await client.send_message(chat_id, "💔 Removed file version, but a critical error occurred reloading data. Please navigate manually from Content Management menu.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id); # Clear state
                 await manage_content_command(client, callback_query.message); # Offer to restart CM


        else: # Success = False (Database method returned False - likely match/modified count was 0)
            content_logger.warning(f"Admin {user_id} confirmed remove file version {file_unique_id_to_remove} but DB modified 0 docs. Version not found?")
            await edit_or_send_message(client, chat_id, message_id, "⚠️ File version was not found or already removed.", disable_web_page_preview=True)
            # Go back to the file version deletion selection menu, which will show current state
            # The callback to initiate selection also handles fetching and displaying.
            # Need episode context to rebuild the callback data.
            episode_context_callback_data = f"content_delete_file_version_select{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}"
            await handle_delete_file_version_select_callback(client, callback_query.message, user_state, episode_context_callback_data) # Re-display selection menu


    except ValueError:
         content_logger.warning(f"Admin {user_id} invalid callback data format for confirm remove file version: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid data in callback.", disable_web_page_preview=True)
         # State is SELECT_FILE_VERSION_TO_DELETE, stay there.

    except Exception as e:
         content_logger.critical(f"FATAL error handling content_confirm_remove_file_version callback {data} for admin {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
         await manage_content_command(client, callback_query.message)


# --- Implement Callback to Cancel File Version Deletion Selection ---
# Catches callbacks content_cancel_delete_file_version_select|<anime_id>|<season>|<ep>
@Client.on_callback_query(filters.regex(f"^content_cancel_delete_file_version_select{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_cancel_delete_file_version_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Cancel during file version deletion selection."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_cancel_delete_file_version_select|<anime_id>|<season>|<ep>

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, strings.ACTION_CANCELLED) # Toast
    except Exception: pass


    user_state = await get_user_state(user_id)
    # State should be SELECT_FILE_VERSION_TO_DELETE
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECT_FILE_VERSION_TO_DELETE):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking cancel delete file version. Data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for cancelling file version deletion.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return

    try:
        # Clear the SELECT_FILE_VERSION_TO_DELETE state and temporary data
        # Return to the MANAGING_EPISODE_MENU state
        # Get episode context from state data (needed for returning to episode menu)
        anime_id_str = user_state.data.get("anime_id")
        season_number = user_state.data.get("season_number")
        episode_number = user_state.data.get("episode_number")
        anime_name = user_state.data.get("anime_name") # Anime name for display

        if not all([anime_id_str, season_number is not None, episode_number is not None, anime_name]):
             content_logger.error(f"Admin {user_id} cancelling file version delete, but missing episode context from state: {user_state.data}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing episode context in state data to return to menu. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return

        # Reset state to MANAGING_EPISODE_MENU
        updated_state_data = {k: v for k, v in user_state.data.items() if k not in ["file_versions"]} # Remove file list from state
        await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODE_MENU, data=updated_state_data)


        # Fetch the current episode data to redisplay the menu
        # Need to refetch to ensure file list displayed reflects actual data if changes occurred between clicks
        filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
        projection = {"name": 1, "seasons.$": 1} # Project name and the matched season

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

        if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
             season_data = anime_doc["seasons"][0]
             episodes_list = season_data.get("episodes", []) # Episodes of this season
             current_episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None)

             if current_episode_doc:
                  await edit_or_send_message(client, chat_id, message_id, strings.ACTION_CANCELLED, parse_mode=config.PARSE_MODE) # Edit previous message to confirm cancel
                  await asyncio.sleep(1) # Short delay
                  # Display the episode management menu using the helper
                  await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, current_episode_doc)
             else: raise Exception("Episode not found after cancelling file version delete.")

        else: raise Exception("Anime/Season not found after cancelling file version delete.")


    except Exception as e:
        content_logger.error(f"FATAL error handling content_cancel_delete_file_version callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message)

# --- Implement Admin View All Anime List (Initial) ---

# Callback: content_view_all_anime_list (from CM main menu)
# Needs to fetch and display a paginated list of anime for admin selection.
# Needs buttons for each anime, pagination, and back/home buttons.
# Selecting an anime should call handle_edit_existing_anime_selection to jump into its management menu.
