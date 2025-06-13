# handlers/browse_handler.py
import logging
import asyncio
from typing import Union, List, Dict, Any, Tuple
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified
)


import config
import strings

from database.mongo_db import MongoDB
from database.mongo_db import get_user_state, set_user_state, clear_user_state
from database.models import User, Anime # Import models for browsing


async def get_user(client: Client, user_id: int) -> Optional[User]: pass
async def edit_or_send_message(client: Client, chat_id: int, message_id: Optional[int], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = True): pass


browse_logger = logging.getLogger(__name__)

# --- Browse States and Data ---
# Using a simple state to manage browse filtering criteria
# handler: "browse"
# step: "browsing" (or more specific like "filtering_genre")
# data: stores current filter selections (genres, year, status) and pagination page

class BrowseState:
    MAIN_MENU = "browse_main_menu"           # Displaying the main browse options
    FILTER_SELECTION = "browse_filter_selection" # Selecting criteria for filtering (e.g., genres)
    BROWSING_LIST = "browsing_list"            # Displaying a paginated list of anime


# --- Entry Point for Browse ---

@Client.on_callback_query(filters.regex("^menu_browse$") & filters.private)
async def browse_main_menu_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id

    try: await client.answer_callback_query(message.id)
    except Exception: browse_logger.warning(f"Failed to answer callback menu_browse from user {user_id}")


    user_state = await get_user_state(user_id)
    if user_state and user_state.handler != "browse":
        browse_logger.warning(f"User {user_id} in state {user_state.handler}:{user_state.step} clicking browse. Clearing old state.")
        await clear_user_state(user_id) # Clear previous state when entering browse


    # Set or ensure the user is in the browse main menu state
    await set_user_state(user_id, "browse", BrowseState.MAIN_MENU, data={}) # Clear old browse filter data


    menu_text = strings.BROWSE_MAIN_MENU
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(strings.BROWSE_OPTION_ALL, callback_data="browse_view_all"),
            # Option to filter (leads to selection menus)
             InlineKeyboardButton(strings.BROWSE_OPTION_GENRE, callback_data="browse_filter_genre_prompt"),
        ],
        [
             InlineKeyboardButton(strings.BROWSE_OPTION_YEAR, callback_data="browse_filter_year_prompt"),
             InlineKeyboardButton(strings.BROWSE_OPTION_STATUS, callback_data="browse_filter_status_prompt"),
        ],
         # Optional: Buttons for Latest/Popular/Leaderboard? Could be in main menu. Let's add to main menu per strings.
         # But if user clicks them from browse menu, they might expect to filter... No, those are discovery, not filtering.
        [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")] # Back to main bot menu
    ])


    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)


# --- Handle Filtering Options Prompts ---
# Callbacks: browse_filter_genre_prompt, browse_filter_year_prompt, browse_filter_status_prompt

@Client.on_callback_query(filters.regex("^browse_filter_(genre|year|status)_prompt$") & filters.private)
async def browse_filter_prompt_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # browse_filter_genre_prompt etc.

    try: await client.answer_callback_query(message.id)
    except Exception: browse_logger.warning(f"Failed to answer callback {data} from user {user_id}")

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "browse" and user_state.step == BrowseState.MAIN_MENU):
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking browse filter prompt. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Browse Menu.", disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query) # Re-display browse main menu
         return

    filter_type = data.split('_')[2] # Extract 'genre', 'year', or 'status'

    # Ensure initial filter data exists in state if coming from main menu.
    if "filter_data" not in user_state.data:
        user_state.data["filter_data"] = {} # Initialize if missing


    # Transition to state for filter selection for this type
    # Step format: browse_filter_selection
    await set_user_state(user_id, "browse", BrowseState.FILTER_SELECTION, data={**user_state.data, "filter_type": filter_type})


    # Send the specific prompt and buttons based on filter type
    if filter_type == 'genre':
        prompt_text = strings.GENRE_SELECTION_TITLE
        options = config.INITIAL_GENRES # Use configured presets

        # Multi-select setup for Genres
        current_selection = user_state.data.get("filter_data", {}).get("genres", [])
        buttons = []
        for option in options:
             is_selected = option in current_selection
             # Button text shows selection status (✅/⬜) and option value
             button_text = f"✅ {option}" if is_selected else f"⬜ {option}"
             # Callback data to toggle selection: browse_toggle_filter|<filter_type>|<value>
             buttons.append(InlineKeyboardButton(button_text, callback_data=f"browse_toggle_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}{config.CALLBACK_DATA_SEPARATOR}{option}"))

        # Arrange buttons, add Apply and Cancel
        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
        keyboard_rows.append([
             # Apply filter button: browse_apply_filter|<filter_type> (pass type to handler)
             InlineKeyboardButton(strings.BUTTON_APPLY_FILTER, callback_data=f"browse_apply_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}"),
             InlineKeyboardButton(strings.BUTTON_CLEAR_FILTERS, callback_data=f"browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}") # Clear selection for this filter type
        ])
        keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")]) # Back to browse main menu
        reply_markup = InlineKeyboardMarkup(keyboard_rows)


    elif filter_type == 'year':
        prompt_text = strings.YEAR_SELECTION_TITLE
        # Get unique release years from database dynamically or use a range
        # Let's get distinct years from existing anime
        try:
             distinct_years_cursor = MongoDB.anime_collection().distinct("release_year", {"release_year": {"$ne": None}}) # Exclude null years
             # Motor distinct is synchronous in current pymongo versions
             # Use asyncio executor if it takes time, or run in background task
             options = sorted([year for year in distinct_years_cursor if isinstance(year, int)], reverse=True) # Get years, filter non-ints, sort descending


             if not options:
                  prompt_text = "😔 No anime with specified release years found."
                  buttons = [] # No year buttons to show
             else:
                 # Single-select for Year - Highlight selected? Or just select and apply? Let's select and go back/apply.
                 current_selection = user_state.data.get("filter_data", {}).get("year") # Get current year selection

                 buttons = []
                 for option in options:
                      # Callback to select a year: browse_select_filter|<filter_type>|<value>
                      button_text = str(option)
                      if current_selection and option == current_selection:
                          button_text = f"✅ {button_text}" # Highlight if currently selected

                      buttons.append(InlineKeyboardButton(button_text, callback_data=f"browse_select_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}{config.CALLBACK_DATA_SEPARATOR}{option}")) # Single select button

                 # Arrange buttons into rows
                 keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
                 keyboard_rows.append([
                     InlineKeyboardButton(strings.BUTTON_CLEAR_FILTERS, callback_data=f"browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}") # Clear selection
                 ])
                 keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")]) # Back to browse main menu
                 reply_markup = InlineKeyboardMarkup(keyboard_rows)


        except Exception as e:
             browse_logger.error(f"Failed to get distinct years for browse filter for user {user_id}: {e}", exc_info=True)
             prompt_text = "💔 Error loading years for filtering."
             buttons = [] # No buttons on error
             keyboard_rows = [[InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")]]
             reply_markup = InlineKeyboardMarkup(keyboard_rows)


    elif filter_type == 'status':
        prompt_text = strings.STATUS_SELECTION_TITLE
        options = config.ANIME_STATUSES # Use configured presets

        # Single-select for Status - Similar to Year
        current_selection = user_state.data.get("filter_data", {}).get("status") # Get current status selection

        buttons = []
        for option in options:
             # Callback to select a status: browse_select_filter|<filter_type>|<value>
             button_text = option
             if current_selection and option == current_selection:
                 button_text = f"✅ {button_text}" # Highlight if currently selected

             buttons.append(InlineKeyboardButton(button_text, callback_data=f"browse_select_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}{config.CALLBACK_DATA_SEPARATOR}{option}")) # Single select button


        # Arrange buttons
        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
        keyboard_rows.append([
            InlineKeyboardButton(strings.BUTTON_CLEAR_FILTERS, callback_data=f"browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}") # Clear selection
         ])
        keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")]) # Back to browse main menu
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

    else: # Invalid filter type received in callback
         browse_logger.error(f"User {user_id} clicked invalid browse filter prompt callback data: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid filter option.", disable_web_page_preview=True)
         # State remains the same, user can retry
         return # Stop execution


    # Send the prompt and the filter selection keyboard
    await edit_or_send_message(
         client, chat_id, message_id,
         prompt_text,
         reply_markup,
         disable_web_page_preview=True # Ensure no weird link previews
     )


# --- Handle Filter Selection Callbacks ---
# Catches callbacks for selecting filters (toggling multi-select or selecting single)
# browse_toggle_filter|<filter_type>|<value> (for genre multi-select)
# browse_select_filter|<filter_type>|<value> (for year/status single select)

@Client.on_callback_query(filters.regex(f"^browse_(toggle|select)_filter{config.CALLBACK_DATA_SEPARATOR}(genre|year|status){config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def browse_select_or_toggle_filter_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message with filter buttons
    data = callback_query.data # browse_toggle_filter|genre|value OR browse_select_filter|year|value

    try: await client.answer_callback_query(message.id) # Answer immediately
    except Exception: browse_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")


    user_state = await get_user_state(user_id)
    # State should be FILTER_SELECTION for this filter type
    if not (user_state and user_state.handler == "browse" and user_state.step == BrowseState.FILTER_SELECTION):
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking filter select {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for filter selection. Please return to the Browse Menu.", disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query) # Re-display browse main menu
         return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3: raise ValueError("Invalid callback data format for filter selection.")
        filter_action = parts[0].split('_')[1] # 'toggle' or 'select'
        filter_type = parts[1]                # 'genre', 'year', or 'status'
        filter_value_raw = parts[2] # The raw string value from the button


        # Determine the actual filter value type (e.g., int for year)
        filter_value: Union[str, int]
        if filter_type == 'year':
            try: filter_value = int(filter_value_raw)
            except ValueError: raise ValueError("Invalid integer value in year filter callback") # Handle invalid year data
        # Add casting for other types if needed
        else: filter_value = filter_value_raw # Default to string


        # Get the current filter selections from state data, initialize if missing
        user_state.data["filter_data"] = user_state.data.get("filter_data", {})

        if filter_type == 'genre':
            # Multi-select logic for genres
            current_genre_selection = user_state.data["filter_data"].get("genres", []) # Get list

            # Ensure value is a valid preset? Optional sanity check.
            if filter_value not in config.INITIAL_GENRES:
                 browse_logger.warning(f"User {user_id} selected non-preset genre: {filter_value} in filter selection.")
                 await callback_query.answer("🚫 Invalid genre option.", show_alert=False)
                 # Don't update state, just re-render the current keyboard
                 await handle_toggle_filter_display(client, chat_id, message_id, filter_type, current_genre_selection)
                 return

            if filter_action != 'toggle': raise ValueError("Invalid action for genre filter") # Should be toggle


            if filter_value in current_genre_selection:
                current_genre_selection.remove(filter_value)
                browse_logger.debug(f"User {user_id} unselected genre filter: {filter_value}")
            else:
                current_genre_selection.append(filter_value)
                browse_logger.debug(f"User {user_id} selected genre filter: {filter_value}")

            # Sort for consistency (optional)
            current_genre_selection.sort()

            # Update genre selection in state data
            user_state.data["filter_data"]["genres"] = current_genre_selection

            # Re-display the filter selection keyboard with updated button states
            await handle_toggle_filter_display(client, chat_id, message_id, filter_type, current_genre_selection) # Helper


        elif filter_type == 'year' or filter_type == 'status':
            # Single-select logic for Year and Status
            # If selected, this becomes the ONLY selection for this filter type
            if filter_action != 'select': raise ValueError("Invalid action for year/status filter") # Should be select


            # Update selection in state data
            user_state.data["filter_data"][filter_type] = filter_value # Store the single value


            # No need to re-display the filter selection keyboard. Automatically go back to browse list.
            # Automatically apply filter and display the browse list starting from page 1
            await handle_apply_filter_callback(client, callback_query, f"browse_apply_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}", user_state.data["filter_data"]) # Call apply filter logic

            # Note: handle_apply_filter_callback will answer the callback, transition state, and display the list.
            return # Stop processing here, apply handler takes over.


        else: # Invalid filter type in regex catch, should not happen
            raise ValueError(f"Unknown filter type: {filter_type}")


        # After handling toggle (for genres), save the updated state
        await set_user_state(user_id, "browse", BrowseState.FILTER_SELECTION, data=user_state.data)

    except ValueError as e:
        browse_logger.warning(f"User {user_id} invalid filter selection data format/value for {data}: {e}")
        await client.answer_callback_query(message.id, f"🚫 Invalid selection data: {e}.", show_alert=False) # Toast with specific error
        # State remains the same, user can retry valid buttons.
    except Exception as e:
         browse_logger.error(f"FATAL error handling browse select/toggle filter callback {data} for user {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query) # Offer to restart browse


# Helper to re-display toggle-filter keyboard (e.g., Genres) with updated states
async def handle_toggle_filter_display(client: Client, chat_id: int, message_id: int, filter_type: str, current_selection: List[str]):
     """Re-edits the message with the filter selection keyboard, updating button states."""
     if filter_type == 'genre':
          options = config.INITIAL_GENRES
          prompt_text = strings.GENRE_SELECTION_TITLE # Original prompt text

          buttons = []
          for option in options:
               is_selected = option in current_selection
               button_text = f"✅ {option}" if is_selected else f"⬜ {option}"
               buttons.append(InlineKeyboardButton(button_text, callback_data=f"browse_toggle_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}{config.CALLBACK_DATA_SEPARATOR}{option}"))

          keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
          keyboard_rows.append([
               InlineKeyboardButton(strings.BUTTON_APPLY_FILTER, callback_data=f"browse_apply_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}"), # Still apply only genre filter with this type
               InlineKeyboardButton(strings.BUTTON_CLEAR_FILTERS, callback_data=f"browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}")
          ])
          keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")])
          reply_markup = InlineKeyboardMarkup(keyboard_rows)

     # Add elifs for other multi-select filter types if implemented


     else: # Should not happen if called correctly - Filter type isn't a toggle type
          browse_logger.error(f"handle_toggle_filter_display called with non-toggle filter type: {filter_type}. User likely in wrong state.")
          return # Stop

     # Edit only the reply markup to update button states, leave text as is.
     try:
          await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
     except MessageNotModified: pass
     except FloodWait as e:
          browse_logger.warning(f"FloodWait editing toggle filter buttons for chat {chat_id} (retry in {e.value}s): {e}")
          await asyncio.sleep(e.value)
          try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
          except Exception as retry_e: browse_logger.error(f"Retry failed editing toggle filter buttons for chat {chat_id} (msg {message_id}): {retry_e}", exc_info=True)
     except Exception as e:
          browse_logger.error(f"Failed to edit reply markup for toggle filter display for chat {chat_id}: {e}", exc_info=True)


# --- Handle Applying Filters ---
# Catches callbacks browse_apply_filter|<filter_type> (from multi-select, e.g., Genres)
# Also implicitly called by handle_select_or_toggle_filter_callback for single select types (Year, Status)

@Client.on_callback_query(filters.regex(f"^browse_apply_filter{config.CALLBACK_DATA_SEPARATOR}(genre|year|status)$") & filters.private)
@Client.on_callback_query(filters.regex("^browse_view_all$") & filters.private) # Also handles view all which means apply filters (including cleared/none)
async def handle_apply_filter_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message with apply/view all button
    data = callback_query.data

    # Check if it's "view_all" specifically
    is_view_all = data == "browse_view_all"

    # Check if it's an apply filter from a specific filter selection menu
    is_apply_filter = data.startswith("browse_apply_filter|")
    if is_apply_filter:
         filter_type = data.split(config.CALLBACK_DATA_SEPARATOR)[1] # e.g., 'genre'
         # Filter value(s) for genre should already be in state data
         apply_msg = f"Applying {filter_type} filter..." # Answer message
    elif is_view_all:
         apply_msg = "Viewing all anime..." # Answer message
         filter_type = "all" # For logging


    # Answer immediately with action message
    try: await client.answer_callback_query(message.id, apply_msg)
    except Exception: browse_logger.warning(f"Failed to answer callback query {data} from user {user_id}")


    user_state = await get_user_state(user_id)

    # Ensure user is in a browse state (either FILTER_SELECTION or MAIN_MENU for view_all)
    if not (user_state and user_state.handler == "browse" and (user_state.step == BrowseState.FILTER_SELECTION or (is_view_all and user_state.step == BrowseState.MAIN_MENU))):
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking apply filter/view all. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Browse Menu.", disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query) # Re-display browse main menu
         return

    # Get filter data from state (if any), reset page to 1 for new filter
    filter_data = user_state.data.get("filter_data", {}) if not is_view_all else {} # Use filter_data from state unless viewing all (clears filters conceptually)
    page_number = 1 # Always start from page 1 when applying filters

    # Clear the filter selection state or maintain browse state based on action
    if is_apply_filter:
         # Coming from FILTER_SELECTION. Transition to BROWSING_LIST state.
         # Keep filter_data, set page to 1
         await set_user_state(user_id, "browse", BrowseState.BROWSING_LIST, data={**user_state.data, "filter_data": filter_data, "page": page_number})

    elif is_view_all:
         # Coming from MAIN_MENU. Transition to BROWSING_LIST state.
         # Clear filters conceptually, set page to 1
         await set_user_state(user_id, "browse", BrowseState.BROWSING_LIST, data={"filter_data": {}, "page": page_number})
         filter_data = {} # Ensure filter_data is empty for view_all display/query


    # --- Build the MongoDB Query Filter based on selected filter_data ---
    # Example: {"genres": {"$all": ["Action", "Comedy"]}, "release_year": 2023, "status": "Completed"}
    db_query_filter = {}

    selected_genres = filter_data.get("genres", [])
    selected_year = filter_data.get("year")
    selected_status = filter_data.get("status")

    if selected_genres:
         # Query documents where the 'genres' array contains ALL selected genres. Use $all operator.
         db_query_filter["genres"] = {"$all": selected_genres}

    if selected_year is not None: # Only add if a year was selected (0 is a valid year)
         db_query_filter["release_year"] = selected_year

    if selected_status:
         db_query_filter["status"] = selected_status

    # Exclude documents where 'name' or 'status' is null/empty for browsing? No, assume data is clean from admin side.
    # Ensure anime with at least one season/episode are shown? Not required by design currently, show all base anime docs.


    browse_logger.info(f"User {user_id} applying filter: {db_query_filter}. Starting browse list page {page_number}.")

    # --- Fetch Paginated Anime List from Database ---
    await display_browsed_anime_list(client, callback_query.message, db_query_filter, page_number, filter_data)

    # The display function handles retrieving data, building menu, and sending/editing message.
    # It also creates pagination buttons that link back to itself (or a pagination handler)
    # but carry the filter data and new page number.

# --- Helper to display paginated browsed anime list ---
# Called by handle_apply_filter_callback and the pagination callback (browse_list_page)
async def display_browsed_anime_list(client: Client, message: Message, query_filter: Dict, page: int, active_filter_data: Dict):
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id


     browse_logger.debug(f"Displaying browse list page {page} for user {user_id} with filter: {query_filter}")

     try:
        # Count total matching documents first for pagination info
        total_anime_count = await MongoDB.anime_collection().count_documents(query_filter)
        total_pages = (total_anime_count + config.PAGE_SIZE - 1) // config.PAGE_SIZE
        if page < 1: page = 1
        if page > total_pages and total_pages > 0: page = total_pages

        # Fetch anime documents for the current page, projecting needed fields for display
        skip_count = (page - 1) * config.PAGE_SIZE
        # Project relevant fields for the user list view (name, synopsis snippet, maybe poster?)
        # Displaying posters in a text/button list is complex. Let's stick to text list.
        # Name, maybe year, status, snippet of synopsis for info?
        projection = {"name": 1, "synopsis": 1, "status": 1, "release_year": 1, "overall_download_count": 1} # Add other needed fields
        # Sort by name for consistency
        anime_docs_on_page = await MongoDB.anime_collection().find(query_filter, projection).sort("name", 1).skip(skip_count).limit(config.PAGE_SIZE).to_list(config.PAGE_SIZE)


        # Build the message text with the list of anime
        filter_info_text = ""
        if active_filter_data: # Show applied filters if any
             filter_info_parts = []
             if active_filter_data.get("genres"): filter_info_parts.append(f"Genres: {', '.join(active_filter_data['genres'])}")
             if active_filter_data.get("year") is not None: filter_info_parts.append(f"Year: {active_filter_data['year']}")
             if active_filter_data.get("status"): filter_info_parts.append(f"Status: {active_filter_data['status']}")
             if filter_info_parts: filter_info_text = "Active Filters: " + "; ".join(filter_info_parts) + "\n\n"


        menu_text = strings.BROWSE_LIST_TITLE + filter_info_text

        buttons = []
        if not anime_docs_on_page:
            menu_text += "😔 No anime found matching these criteria."
        else:
             menu_text += f"Page <b>{page}</b> / <b>{total_pages}</b>\n\n"
             # Create buttons for each anime on the page to select for details/download
             for anime_doc in anime_docs_on_page:
                 # Display name and maybe a little extra info in button or just above it.
                 anime_name = anime_doc.get("name", "Unnamed Anime")
                 anime_id_str = str(anime_doc["_id"]) # Get the ID for the callback data

                 # Format button label: "Anime Name" - clicking goes to details/download menu
                 # Callback: browse_select_anime|<anime_id>
                 buttons.append([InlineKeyboardButton(anime_name, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")])

        # Add pagination buttons
        pagination_buttons = []
        if page > 1:
            pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_PREVIOUS_PAGE, callback_data=f"browse_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}{page - 1}"))
        if page < total_pages:
             pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_NEXT_PAGE, callback_data=f"browse_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}{page + 1}"))
        if pagination_buttons: # Only add if there are pagination buttons
             buttons.append(pagination_buttons)


        # Add navigation buttons: Back to Browse main menu, Back to main bot menu
        # Back button should go back to the filter selection if filters were applied, or main browse menu if just view_all.
        # Simplify: Back always goes to Browse main menu
        buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")]) # Back to browse options
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Back to main bot menu


        reply_markup = InlineKeyboardMarkup(buttons)

        # Edit the message (apply filter message or previous list page) to display this page.
        await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)


     except Exception as e:
         browse_logger.error(f"FATAL error displaying browsed anime list page {page} for user {user_id}: {e}", exc_info=True)
         # Decide whether to clear state or try returning to browse main menu
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await clear_user_state(user_id); # Clear state on fatal error
         await browse_main_menu_callback(client, callback_query) # Re-display browse main menu (uses original callback)

# --- Handle Pagination Clicks ---
# Catches callbacks browse_admin_anime_list_page|<page_number>
@Client.on_callback_query(filters.regex(f"^browse_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def browse_list_page_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    # Chat/Message ID from callback_query.message
    message = callback_query.message
    data = callback_query.data

    try:
         # Parse target page number
         parts = data.split(config.CALLBACK_DATA_SEPARATOR)
         if len(parts) != 2: raise ValueError("Invalid pagination callback data format.")
         target_page = int(parts[1])

    except ValueError:
         browse_logger.warning(f"User {user_id} invalid page number in browse list pagination callback: {data}")
         await client.answer_callback_query(message.id, "🚫 Invalid page number.", show_alert=False) # Toast error
         return # Stop processing invalid callback


    try: await client.answer_callback_query(message.id, f"Loading page {target_page}...")
    except Exception: browse_logger.warning(f"Failed to answer callback {data} from user {user_id}")

    user_state = await get_user_state(user_id)

    # State should be BROWSING_LIST
    if not (user_state and user_state.handler == "browse" and user_state.step == BrowseState.BROWSING_LIST):
        browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking browse pagination. Data: {data}. Clearing state.")
        await edit_or_send_message(client, message.chat.id, message.id, "🔄 Invalid state for pagination. Please return to the Browse Menu.", disable_web_page_preview=True)
        await browse_main_menu_callback(client, callback_query) # Re-display browse main menu (uses original callback)
        return


    # Get the currently active filters from state data
    active_filter_data = user_state.data.get("filter_data", {})
    # Build the DB query filter using this data
    db_query_filter = {}
    selected_genres = active_filter_data.get("genres", [])
    selected_year = active_filter_data.get("year")
    selected_status = active_filter_data.get("status")

    if selected_genres: db_query_filter["genres"] = {"$all": selected_genres}
    if selected_year is not None: db_query_filter["release_year"] = selected_year
    if selected_status: db_query_filter["status"] = selected_status


    browse_logger.info(f"User {user_id} browsing list page {target_page} with filters: {db_query_filter}.")

    # Store the new page number in the state data
    user_state.data["page"] = target_page
    # Save the updated state with the new page number
    await set_user_state(user_id, "browse", BrowseState.BROWSING_LIST, data=user_state.data)


    # Display the browsed anime list for the target page with the current filters
    await display_browsed_anime_list(client, message, db_query_filter, target_page, active_filter_data) # Pass original message to edit


    # Note: The display_browsed_anime_list function handles checking page bounds.


    except Exception as e:
         browse_logger.error(f"FATAL error handling browse pagination callback {data} for user {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id) # Clear state on fatal error
         await edit_or_send_message(client, message.chat.id, message.id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query) # Offer to restart browse


# --- Handle Clear Filters ---
# Catches callbacks browse_clear_filter|<filter_type>
@Client.on_callback_query(filters.regex(f"^browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}(genre|year|status)$") & filters.private)
async def browse_clear_filter_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message with filter buttons
    data = callback_query.data

    try: await client.answer_callback_query(message.id, "Clearing filter...")
    except Exception: browse_logger.warning(f"Failed to answer callback {data} from user {user_id}")


    user_state = await get_user_state(user_id)
    # State should be FILTER_SELECTION for the specific type or maybe BROWSING_LIST
    # Clear filter logic makes sense in FILTER_SELECTION state
    if not (user_state and user_state.handler == "browse"): # Allow clear from any browse state? Let's simplify state check
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking clear filter. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Browse Menu.", disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query) # Re-display browse main menu (uses original callback)
         return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for clear filter.")
        filter_type_to_clear = parts[1] # 'genre', 'year', or 'status'

        # Ensure filter_data exists in state
        user_state.data["filter_data"] = user_state.data.get("filter_data", {})


        # Remove the specific filter type's data from the state dictionary
        if filter_type_to_clear in user_state.data["filter_data"]:
             del user_state.data["filter_data"][filter_type_to_clear]
             browse_logger.info(f"User {user_id} cleared {filter_type_to_clear} filter. New filter data: {user_state.data['filter_data']}")
        else:
             browse_logger.debug(f"User {user_id} clicked clear filter for {filter_type_to_clear} but it wasn't set in state data.")
             # Already cleared, no action needed, but can inform user
             # await client.answer_callback_query(message.id, "Filter already cleared.", show_alert=False)


        # Save the updated state with cleared filter data
        # Stay in the current state, unless it was FILTER_SELECTION -> return to BROWSE_MAIN_MENU after clear
        # Let's define clear filter always returns to the BROWSE_MAIN_MENU after clear
        await set_user_state(user_id, "browse", BrowseState.MAIN_MENU, data={**user_state.data}) # Keep other potential data


        # Re-display the browse main menu (which implies no filter applied visually)
        await browse_main_menu_callback(client, callback_query) # Re-display using the callback query to edit message


    except ValueError as e:
        browse_logger.warning(f"User {user_id} invalid filter type in clear filter callback: {data}: {e}")
        await client.answer_callback_query(message.id, "🚫 Invalid filter type to clear.", show_alert=False)

    except Exception as e:
         browse_logger.error(f"FATAL error handling browse clear filter callback {data} for user {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query)


# --- Handle Selecting an Anime from Browse List ---
# Catches callbacks browse_select_anime|<anime_id> (from display_browsed_anime_list)
@Client.on_callback_query(filters.regex(f"^browse_select_anime{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def browse_select_anime_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    try: await client.answer_callback_query(message.id, "Loading anime details...")
    except Exception: browse_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")

    user_state = await get_user_state(user_id)
    # State should be BROWSING_LIST or perhaps SEARCH_RESULTS_LIST (search also uses this select logic)
    # Allow selection from any browse or search list state
    if not (user_state and user_state.handler in ["browse", "search"]): # Check handler, allow from either browsing or search list
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking select anime. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting anime.", disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query) # Re-display browse main menu (simpler fallback)
         return


    try:
        # Parse anime_id
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for selecting anime.")
        anime_id_str = parts[1]

        browse_logger.info(f"User {user_id} selected anime {anime_id_str} from {user_state.handler} list.")

        # Retrieve the full anime document from the database
        anime = await MongoDB.get_anime_by_id(anime_id_str) # Use the database helper

        if not anime:
            browse_logger.error(f"Selected anime {anime_id_str} not found in DB for user {user_id} browsing/searching.")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found in database.", disable_web_page_preview=True)
            # Keep the current list display or return to main menu? Let's try to return to the list they were on.
            # If coming from browse, state is BROWSING_LIST, contains filter_data and page
            if user_state.handler == "browse" and user_state.step == BrowseState.BROWSING_LIST:
                query_filter = {} # Reconstruct filter for display
                active_filter_data = user_state.data.get("filter_data", {})
                selected_genres = active_filter_data.get("genres", [])
                selected_year = active_filter_data.get("year")
                selected_status = active_filter_data.get("status")

                if selected_genres: db_query_filter["genres"] = {"$all": selected_genres}
                if selected_year is not None: db_query_filter["release_year"] = selected_year
                if selected_status: db_query_filter["status"] = selected_status
                page = user_state.data.get("page", 1)

                await display_browsed_anime_list(client, callback_query.message, db_query_filter, page, active_filter_data)

            # If coming from search list? Need similar logic for search list.
            # Simplest fallback: go back to browse main menu.
            else:
                await clear_user_state(user_id)
                await browse_main_menu_callback(client, callback_query)


            return # Stop

        # --- Transition to displaying anime details / season selection (implicitly part of download workflow) ---
        # We are transitioning from a list state (BROWZING_LIST or SEARCH_RESULTS_LIST)
        # Set state to indicate we are now viewing this specific anime's details.
        # Step can be 'viewing_anime_details'
        # Or maybe just use a broader state like "browsing" but data contains "viewing_anime_id"
        # Simpler state: Remain in "browse" or "search" handler context, but state.data now indicates selected anime ID.
        # No, let's use a dedicated state like BROWSING_ANIME_DETAILS or VIEWING_ANIME
        # Step: 'viewing_anime_details' in the browse handler context.

        await set_user_state(user_id, user_state.handler, 'viewing_anime_details', data={**user_state.data, "viewing_anime_id": str(anime.id)}) # Preserve list state if possible for BACK button


        # Display anime details and options (Watchlist, Season selection)
        await display_user_anime_details_menu(client, callback_query.message, anime)


    except ValueError:
        browse_logger.warning(f"User {user_id} invalid anime ID data in callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid anime data in callback.", disable_web_page_preview=True)
        # Stay in current state/list


    except Exception as e:
        browse_logger.error(f"FATAL error handling browse_select_anime callback {data} for user {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await browse_main_menu_callback(client, callback_query)


# Helper to display anime details menu to the user
# This is also used by the search handler after a direct search result selection.
async def display_user_anime_details_menu(client: Client, message: Message, anime: Anime):
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id


    # Build anime details text
    details_text = strings.ANIME_DETAILS_TITLE + "\n\n"
    details_text += strings.ANIME_DETAILS_FORMAT.format(
         title=anime.name,
         synopsis=anime.synopsis if anime.synopsis else 'Not available.', # Provide default
         genres=', '.join(anime.genres) if anime.genres else 'Not specified',
         release_year=anime.release_year if anime.release_year else 'Unknown Year',
         status=anime.status if anime.status else 'Unknown Status',
         total_seasons_declared=anime.total_seasons_declared,
         poster_link="https://placeholder.com" # Placeholder for poster link if needed, or omit tag
     )

    # Determine Watchlist button state (Add or Remove)
    user = await get_user(client, user_id) # Get user to check watchlist
    if user is None:
         browse_logger.error(f"Failed to get user {user_id} while displaying anime details menu for watchlist check.")
         watchlist_button = None # Don't show watchlist button on error
    else:
         # Check if this anime's ID is in the user's watchlist list
         anime_id_obj = ObjectId(anime.id) # Ensure ObjectId for comparison
         is_on_watchlist = anime_id_obj in user.watchlist
         if is_on_watchlist:
             # Callback to remove: watchlist_remove|<anime_id>
             watchlist_button = InlineKeyboardButton(strings.BUTTON_REMOVE_FROM_WATCHLIST, callback_data=f"watchlist_remove{config.CALLBACK_DATA_SEPARATOR}{anime.id}")
         else:
             # Callback to add: watchlist_add|<anime_id>
             watchlist_button = InlineKeyboardButton(strings.BUTTON_ADD_TO_WATCHLIST, callback_data=f"watchlist_add{config.CALLBACK_DATA_SEPARATOR}{anime.id}")


    # Build season selection buttons. Only show if anime has seasons.
    buttons = []
    if anime.seasons:
        # Display header
        details_text += f"\n{strings.SEASON_LIST_TITLE_USER.format(anime_title=anime.name)}\n"

        # Sort seasons numerically before creating buttons
        seasons = sorted(anime.seasons, key=lambda s: s.season_number)

        # Add buttons for each season
        for season in seasons:
             season_number = season.season_number
             episodes_list = season.episodes # Access list of episodes for this season
             # Show count of episodes with files if any? Or just season number.
             ep_count = len(episodes_list)

             button_label = f"📺 Season {season_number}"
             if ep_count > 0: button_label += f" ({ep_count} Episodes)" # Indicate episode count

             # Callback to select a season: download_select_season|<anime_id>|<season_number>
             # Route to the download handler as this is the start of the download path.
             buttons.append([InlineKeyboardButton(button_label, callback_data=f"download_select_season{config.CALLBACK_DATA_SEPARATOR}{anime.id}{config.CALLBACK_DATA_SEPARATOR}{season_number}")])

    # Add navigation buttons: Back to list (browse/search), Watchlist (if available), Home.
    nav_buttons_row = []
    # Determine the BACK button callback based on previous state (search or browse)
    user_state = await get_user_state(user_id)
    if user_state and user_state.handler == "browse" and user_state.step == "viewing_anime_details" and "page" in user_state.data:
         # Came from browse list, filter data and page number should be in state.data
         # Back button should go back to that specific page/filter of the browse list
         # The display_browsed_anime_list needs the query filter and page to redisplay.
         # This requires saving filter data/page consistently through selection.
         # Simplified approach: Back from details always goes back to Browse main menu or Search result menu (if search was the source)

         # Need a robust way to get the BACK callback based on *which* list (browse/search) the user came from
         # Store source in state.data when transitioning to 'viewing_anime_details': {"source": "browse", ...} or {"source": "search", ...}
         # Let's add "source_handler" to state data when setting "viewing_anime_details".
         source_handler = user_state.data.get("source_handler") # Added when transitioning to viewing_anime_details

         back_callback = "browse_main_menu" # Default back destination

         if source_handler == "browse":
              # Back to Browse List needs filter data and page. Pass just 'browse_view_all' for simplicity first.
              # A better way: pass callback data like "browse_go_back_list" which reads state data filters/page.
              # Let's use a simplified BACK that goes to the entry point of the source handler for now.
              back_callback = "browse_main_menu" # Go back to browse options


         elif source_handler == "search":
              # Back to Search Results needs search query text.
              # Store search query in state data when routing from search handler.
              # State: search_handler -> state 'viewing_anime_details', data includes {"search_query": "...", "source_handler": "search"}
              # Callback to trigger search result list display: search_display_results|<query>
              search_query_from_state = user_state.data.get("search_query")
              if search_query_from_state:
                  back_callback = f"search_display_results{config.CALLBACK_DATA_SEPARATOR}{search_query_from_state}" # Needs this callback handler

         nav_buttons_row.append(InlineKeyboardButton(strings.BUTTON_BACK, callback_data=back_callback))


    if watchlist_button: nav_buttons_row.append(watchlist_button)
    nav_buttons_row.append(InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")) # Home is universal


    if nav_buttons_row: buttons.append(nav_buttons_row) # Add the row of nav/action buttons if not empty


    # Send or edit the message to display anime details and season buttons
    await edit_or_send_message(client, chat_id, message_id, details_text, InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

# Watchlist Callbacks (Implemented in watchlist_handler.py but needed here for button calls)
# watchlist_add|<anime_id>
# watchlist_remove|<anime_id>

# Download Select Season Callback (Implemented in download_handler.py but needed here for button calls)
# download_select_season|<anime_id>|<season_number>


# Note: User clicks on season button -> handled by download_handler.py
