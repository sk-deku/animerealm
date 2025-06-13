# handlers/content_handler.py
import logging
from typing import Union
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import config
from strings import (
    MANAGE_CONTENT_TITLE, MANAGE_CONTENT_OPTIONS,
    BUTTON_ADD_NEW_ANIME, BUTTON_EDIT_ANIME, BUTTON_VIEW_ALL_ANIME, BUTTON_HOME,
    ADD_ANIME_NAME_PROMPT, ADD_ANIME_NAME_SEARCH_RESULTS, BUTTON_ADD_AS_NEW_ANIME,
    BUTTON_CANCEL, ACTION_CANCELLED, ERROR_OCCURRED
)

from database.mongo_db import MongoDB, get_user_state, set_user_state, clear_user_state
from database.models import UserState, Anime # Import necessary models
from handlers.common_handlers import get_user, create_main_menu_keyboard # Import user helpers

# Fuzzy search library
from fuzzywuzzy import process

# Configure logger for content handlers
content_logger = logging.getLogger(__name__)

# --- States for Content Management Process ---
# These will be stored in the user_states collection
# Handler Name: "content_management"
class ContentState:
    AWAITING_ANIME_NAME = "awaiting_anime_name"
    # SELECTING_SEARCH_RESULT = "selecting_search_result" # This is handled within AWAITING_ANIME_NAME processing now
    AWAITING_POSTER = "awaiting_poster"
    AWAITING_SYNOPSIS = "awaiting_synopsis"
    AWAITING_SEASONS_COUNT = "awaiting_seasons_count"
    SELECTING_GENRES = "selecting_genres"
    AWAITING_RELEASE_YEAR = "awaiting_release_year"
    SELECTING_STATUS = "selecting_status"
    MANAGING_SEASONS_MENU = "managing_seasons_menu"
    MANAGING_EPISODES_MENU = "managing_episodes_menu"
    SELECTING_METADATA_QUALITY = "selecting_metadata_quality"
    SELECTING_METADATA_AUDIO = "selecting_metadata_audio"
    SELECTING_METADATA_SUBTITLES = "selecting_metadata_subtitles"
    UPLOADING_FILE = "uploading_file"
    AWAITING_RELEASE_DATE = "awaiting_release_date"
    # EDITING_SYNOPSIS = "editing_synopsis" # Can reuse AWAITING_SYNOPSIS with state data context
    # EDITING_POSTER = "editing_poster" # Can reuse AWAITING_POSTER with state data context


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

# This function is NOT a Pyrogram handler decorated with @Client.on_message.
# It is called *from* the generic handle_plain_text_input function in common_handlers.py
# when it detects that an admin user is in a "content_management" state and sent text.
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

    if current_step == ContentState.AWAITING_ANIME_NAME:
         await handle_awaiting_anime_name_input(client, message, user_state)
    elif current_step == ContentState.AWAITING_SYNOPSIS:
         await handle_awaiting_synopsis_input(client, message, user_state, input_text) # Pass input_text
    elif current_step == ContentState.AWAITING_SEASONS_COUNT:
         await handle_awaiting_seasons_count_input(client, message, user_state, input_text) # Pass input_text
    elif current_step == ContentState.AWAITING_RELEASE_YEAR:
         await handle_awaiting_release_year_input(client, message, user_state, input_text) # Pass input_text
    # Add routing for other text input states if needed (like search within lists)
    # State SELECTING_GENRES/STATUS use callbacks primarily, but might need text fallback
    
    else:
        # Received unexpected text input for the current state
        common_logger.warning(f"Admin {user_id} sent unexpected text input while in content management state {user_state.step}: {input_text[:50]}")
        await message.reply_text("🤔 That wasn't the input I was expecting for this step. Please send the requested information, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        # Stay in the current state, just re-prompt or ask for valid input    

# --- Helper Functions for Specific Steps in Add New Anime Flow ---

async def handle_awaiting_anime_name_input(client: Client, message: Message, user_state: UserState):
    """Handles admin text input when in the AWAITING_ANIME_NAME state."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    input_text = message.text.strip() # The anime name provided by the admin

    anime_name_input = input_text


    # --- Fuzzy Search for Existing Anime (Existing Logic - Extracted) ---
    anime_docs = list(await MongoDB.anime_collection().find().to_list(1000)) # Fetch some anime for search
    anime_names = {doc['name']: str(doc['_id']) for doc in anime_docs} # Map name to ID
    search_results = process.extract(anime_name_input, anime_names.keys(), limit=config.LEADERBOARD_COUNT) # Use config for limit? or separate limit? Use 5 for search
    # Use config.FUZZYWUZZY_THRESHOLD

    matching_anime = []
    for name, score in search_results:
        if score >= config.FUZZYWUZZY_THRESHOLD:
             original_doc = next((doc for doc in anime_docs if doc['name'] == name), None)
             if original_doc:
                  matching_anime.append({"_id": original_doc['_id'], "name": name, "score": score})
                 
    # --- Determine Next Step Based on Search Results and Purpose (Add/Edit) ---
    purpose = user_state.data.get("purpose", "add")

    if purpose == "add":
         if matching_anime:
             response_text = ADD_ANIME_NAME_SEARCH_RESULTS.format(name=anime_name_input)
             buttons = []
             for match in matching_anime:
                 buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing|{match['_id']}")])

             buttons.append([InlineKeyboardButton(BUTTON_ADD_AS_NEW_ANIME.format(name=anime_name_input), callback_data=f"content_proceed_add_new|{anime_name_input}")])

             buttons.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")])
             reply_markup = InlineKeyboardMarkup(buttons)
             try:
                 await message.reply_text(response_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
             except Exception as e:
                 content_logger.error(f"Failed to send anime search results (add flow) for admin {user_id}: {e}")
                 await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
             # Stay in state, waiting for callback
         else:
              # No matches, proceed to add new flow. Set state to awaiting poster.
              await set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={"new_anime_name": anime_name_input})
              await prompt_for_poster(client, chat_id, anime_name_input)

    elif purpose == "edit":
        if matching_anime:
            response_text = f"🔍 Found these anime matching '{anime_name_input}'. Select one to **__edit__**: 👇"
            buttons = []
            for match in matching_anime:
                buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing|{match['_id']}")])

            buttons.append([InlineKeyboardButton(BUTTON_BACK, callback_data="content_edit_anime")]) # Go back to prompting name for edit
            buttons.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")])
            reply_markup = InlineKeyboardMarkup(buttons)
            try:
                 await message.reply_text(response_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
            except Exception as e:
                 content_logger.error(f"Failed to send anime search results (edit flow) for admin {user_id}: {e}")
                 await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
            # Stay in state, waiting for callback
        else:
             await message.reply_text(f"😔 Couldn't find any anime matching '{anime_name_input}' with confidence above {config.FUZZYWUZZY_THRESHOLD} for editing.\nPlease try a different name to search, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
             # State remains AWAITING_ANIME_NAME with purpose: edit


    else: # Should not happen if state data is handled correctly
         content_logger.warning(f"Admin {user_id} in AWAITING_ANIME_NAME state with invalid purpose: {purpose}")
         await message.reply_text("🤷 Invalid state data. Please try again.", parse_mode=config.PARSE_MODE)
         await manage_content_command(client, message) # Send main menu

# Helper function to display the management menu for a specific anime (Expanded Placeholder)
async def display_anime_management_menu(client: Client, message: Message, anime: Anime):
     """Displays the management menu for a specific anime."""
     user_id = message.from_user.id
     # We are in state content_management:MANAGING_SEASONS_MENU with anime_id in data
     # Ensure state is set before calling this or called *from* where state is set
     # current_state = await get_user_state(user_id) # Optional check if this helper could be called from different states


     menu_text = f"🛠️ __**Managing**__ **__{anime.name}__** ({anime.release_year}, {anime.status}) 🛠️\n"
     if anime.synopsis:
         menu_text += f"📚 __**Synopsis**__: <blockquote>{anime.synopsis[:200]}...</blockquote>\n" # Show snippet
     if anime.poster_file_id:
         menu_text += "🖼️ Poster set.\n"
     menu_text += f"🌟 Seasons Declared: {anime.total_seasons_declared}\n" # Show current declared seasons
     menu_text += f"\n👇 Select an option to edit or manage seasons:"


     buttons = [
         # Manage Seasons button will show list of seasons/option to add
         [InlineKeyboardButton("📺 Manage Seasons/Episodes", callback_data=f"content_manage_seasons|{anime.id}")],
         # Individual edit options for anime metadata
         [
            InlineKeyboardButton("✏️ Edit Name", callback_data=f"content_edit_name|{anime.id}"),
            InlineKeyboardButton("📝 Edit Synopsis", callback_data=f"content_edit_synopsis|{anime.id}")
         ],
         [
            InlineKeyboardButton("🖼️ Edit Poster", callback_data=f"content_edit_poster|{anime.id}"),
            InlineKeyboardButton("🏷️ Edit Genres", callback_data=f"content_edit_genres|{anime.id}")
         ],
         [
            InlineKeyboardButton("🗓️ Edit Release Year", callback_data=f"content_edit_year|{anime.id}"),
            InlineKeyboardButton("🚦 Edit Status", callback_data=f"content_edit_status|{anime.id}")
         ],
         [InlineKeyboardButton("🔄 Re-prompt Season Count", callback_data=f"content_edit_seasons_count|{anime.id}")], # Option to change declared seasons
         [InlineKeyboardButton(BUTTON_BACK, callback_data="content_view_all")], # Go back to full admin list of anime
         [InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home")], # Go back to main bot menu
     ]
     reply_markup = InlineKeyboardMarkup(buttons)

     try:
         # Always edit the current message when navigating sub-menus for cleaner UI
         await message.edit_text(
              menu_text,
              reply_markup=reply_markup,
              parse_mode=config.PARSE_MODE,
              disable_web_page_preview=True
         )
     except Exception as e:
         content_logger.error(f"Failed to display anime management menu for anime {anime.id}: {e}")
         # If edit fails, send as new message with error
         await client.send_message(
             chat_id=message.chat.id,
             text="💔 Error displaying management menu. Sending it as a new message.",
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True
         )
         await client.send_message(message.chat.id, ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


# --- Handling Input for Adding New Anime Steps (after Name) ---
# Helper to prompt admin for poster
async def prompt_for_poster(client: Client, chat_id: int, anime_name: str):
    """Sends the prompt to the admin to upload a poster image."""
    prompt_text = ADD_ANIME_POSTER_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([
         [InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]
    ])
    try:
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send poster prompt to chat {chat_id}: {e}")

async def handle_awaiting_poster(client: Client, message: Message, user_state: UserState):
    """Handles admin input when in the AWAITING_POSTER state (expects photo)."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.photo:
         file_id = message.photo[-1].file_id # Get the highest quality version file_id
         anime_name = user_state.data.get("new_anime_name")
         content_logger.info(f"Admin {user_id} provided poster photo for '{anime_name}'")

         # Update state data with the poster_file_id
         user_state.data["poster_file_id"] = file_id

         # Move to the next step: AWAITING_SYNOPSIS
         await set_user_state(user_id, "content_management", ContentState.AWAITING_SYNOPSIS, data=user_state.data)

         # Prompt for synopsis
         await prompt_for_synopsis(client, chat_id, anime_name)

         # Optional: Reply to the photo message to confirm receipt and state change
         try:
             await message.reply_text(
                  "🖼️ Poster received! Now send the **__Synopsis__** for this anime.",
                  parse_mode=config.PARSE_MODE
              )
         except Exception as e:
              content_logger.warning(f"Failed to reply after poster input for admin {user_id}: {e}")


    else:
        # Received non-photo input when expecting a poster
        await message.reply_text("👆 Please send a **photo** to use as the anime poster, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        # State remains AWAITING_POSTER, user needs to try again


async def prompt_for_synopsis(client: Client, chat_id: int, anime_name: str):
    """Sends the prompt to the admin to provide the synopsis."""
    prompt_text = ADD_ANIME_SYNOPSIS_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([
         [InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]
    ])
    try:
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send synopsis prompt to chat {chat_id}: {e}")

async def handle_awaiting_synopsis_input(client: Client, message: Message, user_state: UserState, synopsis_text: str):
    """Handles admin text input when in the AWAITING_SYNOPSIS state."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_name = user_state.data.get("new_anime_name")
    content_logger.info(f"Admin {user_id} provided synopsis for '{anime_name}': {synopsis_text[:50]}...")

    # Validate synopsis length?

    # Update state data with the synopsis
    user_state.data["synopsis"] = synopsis_text

    # Move to the next step: AWAITING_SEASONS_COUNT
    await set_user_state(user_id, "content_management", ContentState.AWAITING_SEASONS_COUNT, data=user_state.data)

    # Prompt for seasons count
    await prompt_for_seasons_count(client, chat_id, anime_name)

    # Optional confirmation reply
    try:
        await message.reply_text("📝 Synopsis received. Now send the **__Total Number of Seasons__**.", parse_mode=config.PARSE_MODE)
    except Exception as e:
        content_logger.warning(f"Failed to reply after synopsis input for admin {user_id}: {e}")

async def prompt_for_seasons_count(client: Client, chat_id: int, anime_name: str):
    """Sends the prompt to the admin to provide the total seasons count."""
    prompt_text = ADD_ANIME_SEASONS_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([
         [InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]
    ])
    try:
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send seasons count prompt to chat {chat_id}: {e}")


async def handle_awaiting_seasons_count_input(client: Client, message: Message, user_state: UserState, count_text: str):
    """Handles admin text input when in the AWAITING_SEASONS_COUNT state (expects a number)."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_name = user_state.data.get("new_anime_name")
    content_logger.info(f"Admin {user_id} provided seasons count for '{anime_name}': {count_text}")

    # Validate if the input is a number and non-negative
    try:
        seasons_count = int(count_text)
        if seasons_count < 0:
            raise ValueError("Negative count not allowed")

        # Store seasons count in state data
        user_state.data["total_seasons_declared"] = seasons_count

        # Move to the next step: SELECTING_GENRES
        await set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data=user_state.data)

        # Prompt for genres selection (Callback-based step)
        await prompt_for_genres(client, chat_id, anime_name, user_state.data.get("selected_genres", [])) # Pass potentially existing selection

        # Optional confirmation reply
        try:
             await message.reply_text(f"📺 Total seasons ({seasons_count}) received. Now select the **__Genres__**.", parse_mode=config.PARSE_MODE)
        except Exception as e:
             content_logger.warning(f"Failed to reply after seasons count input for admin {user_id}: {e}")

    except ValueError:
        # Input was not a valid non-negative integer
        await message.reply_text("🚫 Please send a valid **__number__** for the total seasons count, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        # State remains AWAITING_SEASONS_COUNT, user needs to try again

async def prompt_for_genres(client: Client, chat_id: int, anime_name: str, selected_genres: List[str]):
    """Sends the prompt and buttons for admin to select genres."""
    prompt_text = ADD_ANIME_GENRES_PROMPT.format(anime_name=anime_name)
    genres = config.INITIAL_GENRES # Use the preset genres from config
    # Could also fetch genres from DB if you want to allow adding new ones over time?

    # Create genre buttons with multi-select state indicated
    buttons = []
    for genre in genres:
        # Use ✅ or ❌ to indicate if the genre is selected in the current state data
        is_selected = genre in selected_genres
        button_text = f"✅ {genre}" if is_selected else genre
        # Callback data format: content_toggle_genre|<genre_name>
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_genre|{genre}"))

    # Arrange buttons into rows
    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    # Add Done and Cancel buttons
    keyboard_rows.append([
        InlineKeyboardButton(BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Genres"), callback_data="content_genres_done"),
        InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        # Since this is triggered after AWAITING_SEASONS_COUNT input, it should be a new message
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True
         )
    except Exception as e:
        content_logger.error(f"Failed to send genres prompt to chat {chat_id}: {e}")

# Handler for genre selection callback buttons
@Client.on_callback_query(filters.regex("^content_toggle_genre\|.*") & filters.private)
async def content_toggle_genre_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin toggling genre selection via buttons."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # Format: content_toggle_genre|<genre_name>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    await callback_query.answer() # Acknowledge immediately

    user_state = await get_user_state(user_id)

    # Check if user is in the correct state and has required data
    if user_state is None or user_state.handler != "content_management" or user_state.step != ContentState.SELECTING_GENRES:
        content_logger.warning(f"Admin {user_id} clicked genre toggle callback but state is {user_state}.")
        await callback_query.message.reply_text("🔄 Invalid state or action. Please restart the process.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id) # Clear incorrect state
        return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2:
             raise ValueError("Invalid callback data format for toggling genre.")
        genre_to_toggle = parts[1]

        # Get currently selected genres from state data, initialize if not present
        selected_genres = user_state.data.get("selected_genres", [])

        # Toggle the genre
        if genre_to_toggle in selected_genres:
            selected_genres.remove(genre_to_toggle)
        else:
             selected_genres.append(genre_to_toggle)

        # Update the selected genres in state data
        user_state.data["selected_genres"] = selected_genres
        # We need to save the state update back to DB *before* editing the message/keyboard
        # Or set the state *with* the updated data including selected genres.
        await set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data=user_state.data)

        # Re-send/Edit the genre selection message with updated button states
        # We need to recreate the keyboard with the new selection status
        genres = config.INITIAL_GENRES # Get presets again
        buttons = []
        for genre in genres:
            is_selected = genre in selected_genres
            button_text = f"✅ {genre}" if is_selected else genre
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_genre|{genre}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
        keyboard_rows.append([
             InlineKeyboardButton(BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Genres"), callback_data="content_genres_done"),
             InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        # Edit the message to reflect the new selection
        # This needs to be done carefully as multiple clicks might cause flooding errors
        # Simple try/except FloodWait can help.
        try:
             await callback_query.message.edit_reply_markup(reply_markup) # Edit *only* the keyboard
        except MessageNotModified:
            pass # Ignore if the user clicked the exact same button again
        except FloodWait as e:
            content_logger.warning(f"FloodWait while editing genre buttons for admin {user_id}: {e.value}")
            await asyncio.sleep(e.value)
            try: await callback_query.message.edit_reply_markup(reply_markup) # Retry
            except Exception: pass # Ignore if retry fails


    except Exception as e:
         content_logger.error(f"Error handling content_toggle_genre callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)

# Handler for the "Done Selecting Genres" button
@Client.on_callback_query(filters.regex("^content_genres_done$") & filters.private)
async def content_genres_done_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Done after selecting genres."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    await callback_query.answer("Genres selected.") # Acknowledge

    user_state = await get_user_state(user_id)

    # Check state
    if user_state is None or user_state.handler != "content_management" or user_state.step != ContentState.SELECTING_GENRES:
        content_logger.warning(f"Admin {user_id} clicked Done Genres but state is {user_state}.")
        await callback_query.message.reply_text("🔄 Invalid state or action. Please restart the process.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id) # Clear incorrect state
        return

    selected_genres = user_state.data.get("selected_genres", [])
    anime_name = user_state.data.get("new_anime_name", "Anime Name Unknown") # Fallback

    content_logger.info(f"Admin {user_id} finished selecting genres for '{anime_name}': {selected_genres}")

    # Move to the next step: AWAITING_RELEASE_YEAR
    await set_user_state(user_id, "content_management", ContentState.AWAITING_RELEASE_YEAR, data=user_state.data)

    # Prompt for release year
    await prompt_for_release_year(client, chat_id, anime_name)

    # Edit the message to confirm completion of genres and prompt next step
    try:
        await callback_query.message.edit_text(
            f"🏷️ Genres saved: {', '.join(selected_genres) if selected_genres else 'None'}.\n\n🗓️ Now send the **__Release Year__**.",
            parse_mode=config.PARSE_MODE
        )
    except Exception as e:
         content_logger.warning(f"Failed to edit message after genres done for admin {user_id}: {e}")
         await client.send_message(chat_id, "✅ Genres saved. Please send the **__Release Year__**.", parse_mode=config.PARSE_MODE) # Send new message


async def prompt_for_release_year(client: Client, chat_id: int, anime_name: str):
    """Sends the prompt to the admin to provide the release year."""
    prompt_text = ADD_ANIME_YEAR_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([
         [InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]
    ])
    try:
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send release year prompt to chat {chat_id}: {e}")

async def handle_awaiting_release_year_input(client: Client, message: Message, user_state: UserState, year_text: str):
    """Handles admin text input when in the AWAITING_RELEASE_YEAR state (expects a number)."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_name = user_state.data.get("new_anime_name")
    content_logger.info(f"Admin {user_id} provided release year for '{anime_name}': {year_text}")

    # Validate if the input is a valid year (e.g., a 4-digit number, maybe within a reasonable range)
    try:
        release_year = int(year_text)
        if not (1900 <= release_year <= datetime.now().year + 5): # Simple range check
            raise ValueError("Invalid year range")

        # Store release year in state data
        user_state.data["release_year"] = release_year

        # Move to the next step: SELECTING_STATUS
        await set_user_state(user_id, "content_management", ContentState.SELECTING_STATUS, data=user_state.data)

        # Prompt for status selection (Callback-based step)
        await prompt_for_status(client, chat_id, anime_name)

        # Optional confirmation reply
        try:
             await message.reply_text(f"🗓️ Release year ({release_year}) saved. Now select the **__Status__**.", parse_mode=config.PARSE_MODE)
        except Exception as e:
             content_logger.warning(f"Failed to reply after release year input for admin {user_id}: {e}")


    except ValueError:
        # Input was not a valid year
        await message.reply_text("🚫 Please send a valid **__year__** (e.g., 2024), or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        # State remains AWAITING_RELEASE_YEAR


async def prompt_for_status(client: Client, chat_id: int, anime_name: str):
    """Sends the prompt and buttons for admin to select status."""
    prompt_text = ADD_ANIME_STATUS_PROMPT.format(anime_name=anime_name)
    statuses = config.ANIME_STATUSES # Use presets

    buttons = []
    # Status is typically single-select, but button style can show selected one
    # Or simply rely on callback to update message showing selected status
    for status in statuses:
         # Callback data: content_select_status|<status_name>
         buttons.append(InlineKeyboardButton(status, callback_data=f"content_select_status|{status}"))

    # Arrange buttons (potentially just one row if few statuses)
    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
    keyboard_rows.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        # Send as a new message
        await client.send_message(
             chat_id=chat_id,
             text=prompt_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True
         )
    except Exception as e:
        content_logger.error(f"Failed to send status prompt to chat {chat_id}: {e}")


# Handler for status selection callback buttons
@Client.on_callback_query(filters.regex("^content_select_status\|.*") & filters.private)
async def content_select_status_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting anime status via buttons."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # Format: content_select_status|<status_name>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    await callback_query.answer() # Acknowledge

    user_state = await get_user_state(user_id)

    # Check state
    if user_state is None or user_state.handler != "content_management" or user_state.step != ContentState.SELECTING_STATUS:
        content_logger.warning(f"Admin {user_id} clicked status select callback but state is {user_state}.")
        await callback_query.message.reply_text("🔄 Invalid state or action. Please restart the process.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)
        return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2:
             raise ValueError("Invalid callback data format for selecting status.")
        selected_status = parts[1]

        # Validate if the selected status is one of the valid presets (safety)
        if selected_status not in config.ANIME_STATUSES:
             content_logger.warning(f"Admin {user_id} selected invalid status: {selected_status}")
             await callback_query.message.reply_text("🚫 Invalid status selected. Please choose from the buttons.", parse_mode=config.PARSE_MODE)
             # State remains the same, keep the menu
             return # Stop processing this invalid selection


        # Store the selected status in state data
        user_state.data["status"] = selected_status

        anime_name = user_state.data.get("new_anime_name", "Anime Name Unknown") # Fallback

        content_logger.info(f"Admin {user_id} selected status '{selected_status}' for '{anime_name}'.")

        # --- All New Anime Data Collected! Now Create the Anime Document! ---
        # This is the end of the "Add New Anime" initial data collection flow.
        # Collect all the data from user_state.data:
        # - new_anime_name (key: "new_anime_name")
        # - poster_file_id (key: "poster_file_id", Optional)
        # - synopsis (key: "synopsis")
        # - total_seasons_declared (key: "total_seasons_declared")
        # - selected_genres (key: "selected_genres", defaults to [])
        # - release_year (key: "release_year")
        # - status (key: "status")

        # Create the Anime Pydantic model instance
        # Pydantic will handle defaults for lists and ints where not provided (though we collected essentials)
        try:
            # Construct dictionary from state data
            new_anime_data = {
                 "name": user_state.data.get("new_anime_name"),
                 "poster_file_id": user_state.data.get("poster_file_id"), # Optional
                 "synopsis": user_state.data.get("synopsis"),
                 "total_seasons_declared": user_state.data.get("total_seasons_declared"),
                 "genres": user_state.data.get("selected_genres", []), # Use default []
                 "release_year": user_state.data.get("release_year"),
                 "status": user_state.data.get("status"),
                 "seasons": [], # Start with empty seasons array - manage later
                 "overall_download_count": 0, # Default to 0
                 "last_updated_at": datetime.now(timezone.utc) # Set initial update time
            }

            # Create the Pydantic model
            new_anime = Anime(**new_anime_data)

            # Insert into database
            insert_result = await MongoDB.anime_collection().insert_one(new_anime.dict(by_alias=True, exclude_none=True))
            new_anime_id = insert_result.inserted_id # Get the generated _id

            # Update the created_at time in the model if needed (MongoDb sets it on _id usually)
            # We'll rely on DB default for _id, Pydantic model's id maps to it.

            content_logger.info(f"Successfully added new anime '{new_anime.name}' ({new_anime_id}) by admin {user_id}.")

            # --- Transition to Managing the Newly Created Anime ---
            # Clear the multi-step ADD state and set state to managing THIS anime
            await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_MENU, data={"anime_id": str(new_anime_id), "anime_name": new_anime.name})

            # Edit the message to confirm addition and show the anime management menu
            await callback_query.message.edit_text(
                 f"🎉 Anime **__{new_anime.name}__** added successfully! 🎉\n\nYou can now add seasons and episodes.\n\n👇 Select an option:",
                 parse_mode=config.PARSE_MODE
             )
            # Now display the menu for this specific anime (will call display_anime_management_menu)
            # Fetch the anime again or reuse the model instance
            created_anime = await MongoDB.anime_collection().find_one({"_id": new_anime_id})
            if created_anime:
                 await display_anime_management_menu(client, callback_query.message, Anime(**created_anime))
            else:
                 content_logger.error(f"Failed to retrieve newly created anime {new_anime_id} after insertion for admin {user_id}.")
                 # Fallback: Tell admin it was added, but menu couldn't load. Send main CM menu.
                 await callback_query.message.reply_text("💔 Added anime successfully, but failed to load management menu. Returning to main content menu.", parse_mode=config.PARSE_MODE)
                 await manage_content_command(client, callback_query.message)


        except Exception as e:
            content_logger.error(f"FATAL: Error creating or inserting new anime document after status selection for admin {user_id}: {e}")
            # This is a critical error, all collected data is lost. Inform admin and clear state.
            await callback_query.message.reply_text("💔 A critical error occurred while saving the new anime data. All collected details were lost. Please try again.", parse_mode=config.PARSE_MODE)
            await clear_user_state(user_id)


    except Exception as e:
         content_logger.error(f"Error handling content_select_status callback for admin {user_id}: {e}")
         await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         # State is likely fine, let admin retry selecting


# --- Callbacks After Initial Search ---
# These handle the selection after an admin enters an anime name and sees matches.
# This uses callbacks with specific data formats (e.g., content_edit_existing|<anime_id>, content_proceed_add_new|<anime_name>)

@Client.on_callback_query(filters.regex("^content_edit_existing\|.*") & filters.private)
async def content_edit_existing_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin selecting an existing anime from search results to edit."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # Format: content_edit_existing|<anime_id>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    content_logger.info(f"Admin user {user_id} selected existing anime to edit: {data}")
    await callback_query.answer("Loading anime for editing...")

    try:
        parts = data.split(CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2:
            raise ValueError("Invalid callback data format for editing existing anime.")

        anime_id_str = parts[1]

        # Retrieve the anime document from the database using the ObjectId
        anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)})

        if not anime_doc:
            content_logger.error(f"Admin {user_id} tried to edit non-existent anime ID: {anime_id_str}")
            await callback_query.message.edit_text("💔 Error: Selected anime not found in database. Please try again.", parse_mode=config.PARSE_MODE)
            await manage_content_command(client, callback_query.message) # Send main menu again
            return

        # Convert to Pydantic model (optional but good practice)
        try:
             anime = Anime(**anime_doc)
        except Exception as e:
             content_logger.error(f"Error validating anime data from DB for editing {anime_id_str}: {e}")
             await callback_query.message.edit_text(f"💔 Error loading anime details for editing: {e}", parse_mode=config.PARSE_MODE)
             await manage_content_command(client, callback_query.message)
             return


        content_logger.info(f"Admin {user_id} is now managing anime '{anime.name}' ({anime.id})")

        # --- Proceed to Anime Management Menu (Next State) ---
        # Clear the AWAITING_ANIME_NAME state and set the state to managing this specific anime
        await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_MENU, data={"anime_id": str(anime.id), "anime_name": anime.name})

        # Display the anime details and options to manage seasons, synopsis, etc.
        await display_anime_management_menu(client, callback_query.message, anime)


    except Exception as e:
        content_logger.error(f"Error handling content_edit_existing callback for admin {user_id}: {e}")
        await callback_query.message.edit_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id) # Clear state on unexpected error

# Helper function to display the management menu for a specific anime
async def display_anime_management_menu(client: Client, message: Message, anime: Anime):
     """Displays the management menu for a specific anime."""
     # This is the starting point after adding or selecting an anime for editing.
     # Will include options to edit synopsis, poster, genres, status, year, and manage seasons.

     # --- Placeholder for now ---
     menu_text = f"🛠️ __**Managing**__ **__{anime.name}__** 🛠️\n\nSelect an option:"
     # Build buttons to manage Seasons, edit Synopsis, Poster, etc.
     buttons = [
         [InlineKeyboardButton("📺 Manage Seasons", callback_data=f"content_manage_seasons|{anime.id}")],
         [InlineKeyboardButton("✏️ Edit Synopsis", callback_data=f"content_edit_synopsis|{anime.id}")],
         # ... add other edit options ...
         [InlineKeyboardButton(BUTTON_BACK_TO_ANIME_LIST, callback_data="content_view_all")], # Go back to full admin list
         [InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home")], # Go back to main bot menu
     ]
     reply_markup = InlineKeyboardMarkup(buttons)

     try:
         await message.edit_text(
              menu_text,
              reply_markup=reply_markup,
              parse_mode=config.PARSE_MODE,
              disable_web_page_preview=True
         )
     except Exception as e:
         content_logger.error(f"Failed to display anime management menu for anime {anime.id}: {e}")
         # Handle failure (e.g., send as new message)
         pass # Placeholder error handling


@Client.on_callback_query(filters.regex("^content_proceed_add_new\|.*") & filters.private)
async def content_proceed_add_new_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin confirming adding a NEW anime after search."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    data = callback_query.data # Format: content_proceed_add_new|<anime_name>

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    content_logger.info(f"Admin user {user_id} confirmed adding new anime: {data}")
    await callback_query.answer("Proceeding to add new anime...")

    try:
        parts = data.split(CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2:
            raise ValueError("Invalid callback data format for proceeding to add new anime.")

        new_anime_name = parts[1]

        # Clear the AWAITING_ANIME_NAME state and set the state to awaiting poster
        # The anime name is now stored in the state's data
        await set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={"new_anime_name": new_anime_name})

        # Prompt the admin for the poster image
        await prompt_for_poster(client, callback_query.message.chat.id, new_anime_name)

        # Edit the message to confirm progression
        await callback_query.message.edit_text(
             f"✅ Okay, adding new anime: **{new_anime_name}**",
             parse_mode=config.PARSE_MODE
         )

    except Exception as e:
        content_logger.error(f"Error handling content_proceed_add_new callback for admin {user_id}: {e}")
        await callback_query.message.edit_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id) # Clear state on unexpected error


# --- Placeholders for subsequent steps in Add New Anime flow ---

# Example of a handler function that would be called by handle_content_input
# when current_step is AWAITING_POSTER and a photo message is received.
# async def handle_awaiting_poster(client: Client, message: Message, user_state: UserState):
#     user_id = message.from_user.id
#     chat_id = message.chat.id
#     if message.photo:
#          # Process the photo - get the file_id
#          file_id = message.photo[-1].file_id # Get the highest quality version
#          anime_name = user_state.data.get("new_anime_name")
#
#          # Update state data with the poster_file_id
#          user_state.data["poster_file_id"] = file_id
#
#          # Move to the next step: AWAITING_SYNOPSIS
#          await set_user_state(user_id, "content_management", ContentState.AWAITING_SYNOPSIS, data=user_state.data)
#
#          # Prompt for synopsis
#          await prompt_for_synopsis(client, chat_id, anime_name)
#          # Optionally edit the user's input message confirmation?
#
#     else:
#          # Received text or non-photo media when expecting a poster
#          await message.reply_text("👆 Please send a **photo** to use as the anime poster, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
#          # State remains the same, expecting the photo


# Similar functions needed for AWAITING_SYNOPSIS, AWAITING_SEASONS_COUNT, SELECTING_GENRES, etc.
# These functions would take client, message, user_state as arguments
# And be called by handle_content_input based on the current_step.
# They would validate the input (text for synopsis/year, number for seasons count, callback for genres/status),
# update the user state with the captured data, set the state to the next step,
# and send the next prompt message to the admin.
