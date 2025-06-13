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
    AWAITING_ANIME_NAME = "awaiting_anime_name" # Waiting for admin to send anime name for add/edit
    # --- Other steps will be added later ---
    # SELECTING_SEARCH_RESULT = "selecting_search_result" # Admin needs to pick from search results
    # AWAITING_POSTER = "awaiting_poster" # Waiting for admin to send poster image
    # AWAITING_SYNOPSIS = "awaiting_synopsis"
    # AWAITING_SEASONS_COUNT = "awaiting_seasons_count"
    # SELECTING_GENRES = "selecting_genres" # Multi-step via callbacks
    # AWAITING_RELEASE_YEAR = "awaiting_release_year"
    # SELECTING_STATUS = "selecting_status"
    # MANAGING_SEASONS_MENU = "managing_seasons_menu" # Displaying season options for an anime
    # MANAGING_EPISODES_MENU = "managing_episodes_menu" # Displaying episode options for a season
    # SELECTING_METADATA_QUALITY = "selecting_metadata_quality" # Adding file metadata
    # SELECTING_METADATA_AUDIO = "selecting_metadata_audio"
    # SELECTING_METADATA_SUBTITLES = "selecting_metadata_subtitles"
    # UPLOADING_FILE = "uploading_file" # Waiting for file upload
    # AWAITING_RELEASE_DATE = "awaiting_release_date"

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

    # Ensure input isn't too long or weird?

    current_step = user_state.step

    content_logger.debug(f"Handling content input for user {user_id} at step: {current_step} with text: '{input_text[:50]}...'")

    if current_step == ContentState.AWAITING_ANIME_NAME:
        anime_name_input = input_text

        # --- Fuzzy Search for Existing Anime ---
        anime_docs = list(await MongoDB.anime_collection().find().to_list(1000)) # Fetch some anime for search
        anime_names = {doc['name']: str(doc['_id']) for doc in anime_docs} # Map name to ID

        # Perform fuzzy matching
        # process.extract(query, choices, limit) returns list of (match, score)
        # limit should probably be higher than 1 if multiple close matches are possible
        search_results = process.extract(anime_name_input, anime_names.keys(), limit=5) # Get top 5 matches

        content_logger.info(f"Fuzzy search results for '{anime_name_input}': {search_results} for admin {user_id}")

        matching_anime = []
        # Filter results by confidence score threshold and gather details
        for name, score in search_results:
            if score >= config.FUZZYWUZZY_THRESHOLD:
                 original_doc = next((doc for doc in anime_docs if doc['name'] == name), None) # Find original doc
                 if original_doc:
                      matching_anime.append({"_id": original_doc['_id'], "name": name, "score": score})

        # --- Determine Next Step Based on Search Results and Purpose (Add/Edit) ---

        purpose = user_state.data.get("purpose", "add") # Default to "add" purpose

        if purpose == "add":
             # Admin chose "Add New Anime", now sent a name.
             # Even if matches found, default path is to ADD NEW, BUT offer option to select a match
             if matching_anime:
                 # Show found matches and offer to select one or add new
                 response_text = ADD_ANIME_NAME_SEARCH_RESULTS.format(name=anime_name_input)
                 buttons = []
                 # Add buttons for existing matches
                 for match in matching_anime:
                     # Callback data needs to include anime_id and possibly action
                     # Example: content_edit_existing|<anime_id>
                     buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing|{match['_id']}")])

                 # Add option to proceed with adding NEW anime with the given name
                 buttons.append([InlineKeyboardButton(BUTTON_ADD_AS_NEW_ANIME.format(name=anime_name_input), callback_data=f"content_proceed_add_new|{anime_name_input}")]) # Pass name

                 buttons.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]) # Add cancel button
                 reply_markup = InlineKeyboardMarkup(buttons)

                 # Keep the state as AWAITING_ANIME_NAME, but now expecting callback selection
                 # Could create a new state 'SELECTING_SEARCH_RESULT' if the logic gets complicated
                 # For now, AWAITING_ANIME_NAME covers "initial name input" & "selection after search"

                 try:
                     await message.reply_text(
                         response_text,
                         reply_markup=reply_markup,
                         parse_mode=config.PARSE_MODE
                     )
                 except Exception as e:
                     content_logger.error(f"Failed to send anime search results (add flow) for admin {user_id}: {e}")
                     await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)

                 # No state change needed, waiting for callback


             else:
                  # No significant matches found OR admin wants to add fresh.
                  # Proceed with adding new anime. Next step is awaiting poster.
                  # Call a helper function for the rest of the ADD NEW ANIME flow.
                  await set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={"new_anime_name": anime_name_input})
                  await prompt_for_poster(client, chat_id, anime_name_input)


        elif purpose == "edit":
            # Admin chose "Edit Existing Anime", now sent a name.
            # Must select an EXISTING anime. If no strong match, inform admin.
            if matching_anime:
                # Show found matches to select for editing
                response_text = f"🔍 Found these anime matching '{anime_name_input}'. Select one to **__edit__**: 👇"
                buttons = []
                for match in matching_anime:
                    # Callback data for editing needs the anime_id
                    buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing|{match['_id']}")])

                buttons.append([InlineKeyboardButton(BUTTON_BACK, callback_data="content_edit_anime")]) # Go back to prompting name for edit
                buttons.append([InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")])
                reply_markup = InlineKeyboardMarkup(buttons)

                # Keep state as AWAITING_ANIME_NAME with purpose: edit, waiting for selection callback
                try:
                    await message.reply_text(
                         response_text,
                         reply_markup=reply_markup,
                         parse_mode=config.PARSE_MODE
                    )
                except Exception as e:
                     content_logger.error(f"Failed to send anime search results (edit flow) for admin {user_id}: {e}")
                     await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)

            else:
                 # No strong matches found for editing
                 await message.reply_text(f"😔 Couldn't find any anime matching '{anime_name_input}' with confidence above {config.FUZZYWUZZY_THRESHOLD} for editing.", parse_mode=config.PARSE_MODE)
                 # Maybe reset state or prompt again? Let's prompt again with cancel option.
                 prompt_text = ADD_ANIME_NAME_PROMPT.format() # Use the same prompt again
                 reply_markup = InlineKeyboardMarkup([
                     [InlineKeyboardButton(BUTTON_CANCEL, callback_data="content_cancel")]
                 ])
                 try:
                    await message.reply_text(
                        "🤔 Please try a different name to search for an anime to edit, or cancel.",
                        reply_markup=reply_markup,
                        parse_mode=config.PARSE_MODE
                    )
                    # State remains content_management:AWAITING_ANIME_NAME with purpose: edit
                 except Exception as e:
                     content_logger.error(f"Failed to resend prompt after no edit match for admin {user_id}: {e}")
                     await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


    else:
        # Input received in AWAITING_ANIME_NAME state but purpose is somehow invalid/missing
        content_logger.warning(f"Admin {user_id} sent anime name input in AWAITING_ANIME_NAME state but purpose is {purpose}.")
        await message.reply_text("🤷 Unexpected input or state purpose. Please use the menu buttons to start an action.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id) # Clear state to prevent getting stuck


    # --- Add placeholder routing for other steps here later ---
    # elif current_step == ContentState.AWAITING_POSTER:
    #     # Handle received photo (if message.photo exists)
    #     # Save photo file_id in state.data
    #     # await set_user_state(user_id, "content_management", ContentState.AWAITING_SYNOPSIS, data={...})
    #     # await prompt_for_synopsis(client, chat_id)
    #     pass # Placeholder


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
