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
from database.models import User, Anime


# Import helper from search_handler to display anime details menu
from handlers.search_handler import display_user_anime_details_menu # This helper is defined in search_handler


browse_logger = logging.getLogger(__name__)

# --- Browse States and Data ---
# handler: "browse"
class BrowseState:
    MAIN_MENU = "browse_main_menu"
    FILTER_SELECTION = "browse_filter_selection"
    BROWSING_LIST = "browsing_list"
    # 'viewing_anime_details' state is shared with search handler and managed implicitly


# --- Entry Point for Browse ---

@Client.on_callback_query(filters.regex("^menu_browse$") & filters.private)
async def browse_main_menu_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id

    try: await client.answer_callback_query(message_id)
    except Exception: browse_logger.warning(f"Failed to answer callback menu_browse from user {user_id}")


    user_state = await MongoDB.get_user_state(user_id)
    # Clear any previous state if not already in a browse state, and not just selecting a filter
    if user_state and user_state.handler != "browse":
        browse_logger.warning(f"User {user_id} in state {user_state.handler}:{user_state.step} clicking browse. Clearing old state.")
        await MongoDB.clear_user_state(user_id)

    # Set or ensure the user is in the browse main menu state
    await MongoDB.set_user_state(user_id, "browse", BrowseState.MAIN_MENU, data={"filter_data": {}}) # Initialize filter_data


    menu_text = strings.BROWSE_MAIN_MENU
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(strings.BROWSE_OPTION_ALL, callback_data="browse_view_all"),
             InlineKeyboardButton(strings.BROWSE_OPTION_GENRE, callback_data="browse_filter_genre_prompt"),
        ],
        [
             InlineKeyboardButton(strings.BROWSE_OPTION_YEAR, callback_data="browse_filter_year_prompt"),
             InlineKeyboardButton(strings.BROWSE_OPTION_STATUS, callback_data="browse_filter_status_prompt"),
        ],
        [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")] # Back to main bot menu
    ])


    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)


# --- Handle Filtering Options Prompts ---

@Client.on_callback_query(filters.regex("^browse_filter_(genre|year|status)_prompt$") & filters.private)
async def browse_filter_prompt_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # browse_filter_genre_prompt etc.

    try: await client.answer_callback_query(message_id)
    except Exception: browse_logger.warning(f"Failed to answer callback {data} from user {user_id}")

    user_state = await MongoDB.get_user_state(user_id)
    # Must be in browse state to select filter
    if not (user_state and user_state.handler == "browse" and user_state.step == BrowseState.MAIN_MENU):
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking browse filter prompt. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Browse Menu.", disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query) # Re-display browse main menu
         return

    filter_type = data.split('_')[2] # Extract 'genre', 'year', or 'status'

    user_state.data["filter_data"] = user_state.data.get("filter_data", {})

    await MongoDB.set_user_state(user_id, "browse", BrowseState.FILTER_SELECTION, data={**user_state.data, "filter_type": filter_type})


    if filter_type == 'genre':
        prompt_text = strings.GENRE_SELECTION_TITLE
        options = config.INITIAL_GENRES

        current_selection = user_state.data.get("filter_data", {}).get("genres", [])
        buttons = []
        for option in options:
             is_selected = option in current_selection
             button_text = f"✅ {option}" if is_selected else f"⬜ {option}"
             buttons.append(InlineKeyboardButton(button_text, callback_data=f"browse_toggle_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}{config.CALLBACK_DATA_SEPARATOR}{option}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
        keyboard_rows.append([
             InlineKeyboardButton(strings.BUTTON_APPLY_FILTER, callback_data=f"browse_apply_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}"),
             InlineKeyboardButton(strings.BUTTON_CLEAR_FILTERS, callback_data=f"browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}")
        ])
        keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)


    elif filter_type == 'year':
        prompt_text = strings.YEAR_SELECTION_TITLE
        try:
             # Assuming MongoDB distinct returns list for Motor or using executor
             distinct_years_cursor = await MongoDB.anime_collection().distinct("release_year", {"release_year": {"$ne": None}})
             options = sorted([year for year in distinct_years_cursor if isinstance(year, int)], reverse=True)

             if not options: prompt_text = "😔 No anime with specified release years found."; buttons = []
             else:
                 current_selection = user_state.data.get("filter_data", {}).get("year")
                 buttons = []
                 for option in options:
                      button_text = str(option)
                      if current_selection is not None and option == current_selection:
                          button_text = f"✅ {button_text}"
                      buttons.append(InlineKeyboardButton(button_text, callback_data=f"browse_select_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}{config.CALLBACK_DATA_SEPARATOR}{option}"))

                 keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
                 keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_CLEAR_FILTERS, callback_data=f"browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}")])
                 keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")])
                 reply_markup = InlineKeyboardMarkup(keyboard_rows)

        except Exception as e:
             browse_logger.error(f"Failed to get distinct years for browse filter for user {user_id}: {e}", exc_info=True)
             prompt_text = "💔 Error loading years for filtering."; buttons = []; keyboard_rows = [[InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")]]; reply_markup = InlineKeyboardMarkup(keyboard_rows)


    elif filter_type == 'status':
        prompt_text = strings.STATUS_SELECTION_TITLE
        options = config.ANIME_STATUSES

        current_selection = user_state.data.get("filter_data", {}).get("status")

        buttons = []
        for option in options:
             button_text = option
             if current_selection and option == current_selection: button_text = f"✅ {button_text}"
             buttons.append(InlineKeyboardButton(button_text, callback_data=f"browse_select_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}{config.CALLBACK_DATA_SEPARATOR}{option}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]
        keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_CLEAR_FILTERS, callback_data=f"browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}")])
        keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

    else: browse_logger.error(f"User {user_id} clicked invalid browse filter prompt callback data: {data}"); await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid filter option.", disable_web_page_preview=True); return


    await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(f"^browse_(toggle|select)_filter{config.CALLBACK_DATA_SEPARATOR}(genre|year|status){config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def browse_select_or_toggle_filter_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    try: await client.answer_callback_query(message_id)
    except Exception: browse_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")

    user_state = await MongoDB.get_user_state(user_id)
    if not (user_state and user_state.handler == "browse" and user_state.step == BrowseState.FILTER_SELECTION):
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking filter select {data}. Data: {user_state.data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for filter selection. Please return to the Browse Menu.", disable_web_page_preview=True)
         await browse_main_menu_callback(client, callback_query)
         return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 3: raise ValueError("Invalid callback data format."); filter_action = parts[0].split('_')[1]; filter_type = parts[1]; filter_value_raw = parts[2]

        filter_value: Union[str, int];
        if filter_type == 'year': try: filter_value = int(filter_value_raw); except ValueError: raise ValueError("Invalid integer value in year filter callback");
        else: filter_value = filter_value_raw;

        user_state.data["filter_data"] = user_state.data.get("filter_data", {});


        if filter_type == 'genre':
            current_genre_selection = user_state.data["filter_data"].get("genres", []);
            if filter_value not in config.INITIAL_GENRES: browse_logger.warning(f"User {user_id} selected non-preset genre: {filter_value}."); await client.answer_callback_query(message_id, "🚫 Invalid genre option.", show_alert=False); return;
            if filter_action != 'toggle': raise ValueError("Invalid action for genre filter");

            if filter_value in current_genre_selection: selected_genre_index = current_genre_selection.index(filter_value); del current_genre_selection[selected_genre_index];
            else: current_genre_selection.append(filter_value);
            current_genre_selection.sort();
            user_state.data["filter_data"]["genres"] = current_genre_selection;

            await handle_toggle_filter_display(client, chat_id, message_id, filter_type, current_genre_selection);


        elif filter_type == 'year' or filter_type == 'status':
            if filter_action != 'select': raise ValueError("Invalid action for year/status filter");
            user_state.data["filter_data"][filter_type] = filter_value;
            await handle_apply_filter_callback(client, callback_query);
            return;


        else: raise ValueError(f"Unknown filter type: {filter_type}");

        await MongoDB.set_user_state(user_id, "browse", BrowseState.FILTER_SELECTION, data=user_state.data);

    except ValueError as e: browse_logger.warning(f"User {user_id} invalid filter selection data for {data}: {e}"); await client.answer_callback_query(message_id, f"🚫 Invalid selection data: {e}.", show_alert=False);
    except Exception as e:
         browse_logger.error(f"FATAL error handling browse select/toggle filter callback {data} for user {user_id}: {e}", exc_info=True);
         await MongoDB.clear_user_state(user_id);
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
         await browse_main_menu_callback(client, callback_query);


async def handle_toggle_filter_display(client: Client, chat_id: int, message_id: int, filter_type: str, current_selection: List[str]):
     if filter_type == 'genre':
          options = config.INITIAL_GENRES
          prompt_text = strings.GENRE_SELECTION_TITLE;

          buttons = [];
          for option in options: is_selected = option in current_selection; button_text = f"✅ {option}" if is_selected else f"⬜ {option}"; buttons.append(InlineKeyboardButton(button_text, callback_data=f"browse_toggle_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}{config.CALLBACK_DATA_SEPARATOR}{option}"));

          keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)];
          keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_APPLY_FILTER, callback_data=f"browse_apply_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type}"), InlineKeyboardButton(strings.BUTTON_CLEAR_FILTERS, callback_data=f"browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}{filter_type})"]]);
          keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")]);
          reply_markup = InlineKeyboardMarkup(keyboard_rows);


     else: browse_logger.error(f"handle_toggle_filter_display called with non-toggle filter type: {filter_type}."); return;

     try:
          await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup);
     except MessageNotModified: pass;
     except FloodWait as e:
          browse_logger.warning(f"FloodWait editing toggle filter buttons for chat {chat_id} (retry in {e.value}s): {e}"); await asyncio.sleep(e.value);
          try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup);
          except Exception as retry_e: browse_logger.error(f"Retry failed editing toggle filter buttons for chat {chat_id} (msg {message_id}): {retry_e}", exc_info=True);
     except Exception as e:
          browse_logger.error(f"Failed to edit reply markup for toggle filter display for chat {chat_id}: {e}", exc_info=True);


@Client.on_callback_query(filters.regex(f"^browse_apply_filter{config.CALLBACK_DATA_SEPARATOR}(genre|year|status)$") & filters.private)
@Client.on_callback_query(filters.regex("^browse_view_all$") & filters.private)
async def handle_apply_filter_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id; data = callback_query.data;

    is_view_all = data == "browse_view_all"; is_apply_filter = data.startswith("browse_apply_filter|");
    if is_apply_filter: filter_type = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; apply_msg = f"Applying {filter_type} filter...";
    elif is_view_all: apply_msg = "Viewing all anime..."; filter_type = "all";

    try: await client.answer_callback_query(message_id, apply_msg);
    except Exception: browse_logger.warning(f"Failed to answer callback query {data} from user {user_id}");


    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "browse" and (user_state.step == BrowseState.FILTER_SELECTION or (is_view_all and user_state.step == BrowseState.MAIN_MENU))):
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking apply filter/view all. Data: {data}. Clearing state.");
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Browse Menu.", disable_web_page_preview=True);
         await browse_main_menu_callback(client, callback_query); return;


    filter_data = user_state.data.get("filter_data", {}) if not is_view_all else {}; page_number = 1;

    if is_apply_filter: await MongoDB.set_user_state(user_id, "browse", BrowseState.BROWSING_LIST, data={**user_state.data, "filter_data": filter_data, "page": page_number});
    elif is_view_all: await MongoDB.set_user_state(user_id, "browse", BrowseState.BROWSING_LIST, data={"filter_data": {}, "page": page_number}); filter_data = {};


    db_query_filter = {}; selected_genres = filter_data.get("genres", []); selected_year = filter_data.get("year"); selected_status = filter_data.get("status");
    if selected_genres: db_query_filter["genres"] = {"$all": selected_genres};
    if selected_year is not None: db_query_filter["release_year"] = selected_year;
    if selected_status: db_query_filter["status"] = selected_status;


    browse_logger.info(f"User {user_id} applying filter: {db_query_filter}. Starting browse list page {page_number}. Source callback: {data}");

    await display_browsed_anime_list(client, callback_query.message, db_query_filter, page_number, filter_data);

async def display_browsed_anime_list(client: Client, message: Message, query_filter: Dict, page: int, active_filter_data: Dict):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;

     browse_logger.debug(f"Displaying browse list page {page} for user {user_id} with filter: {query_filter}");

     try:
        total_anime_count = await MongoDB.anime_collection().count_documents(query_filter);
        total_pages = (total_anime_count + config.PAGE_SIZE - 1) // config.PAGE_SIZE; if total_pages == 0: total_pages = 1;
        if page < 1: page = 1; if page > total_pages and total_pages > 0: page = total_pages;

        skip_count = (page - 1) * config.PAGE_SIZE;
        projection = {"name": 1, "status": 1, "release_year": 1, "overall_download_count": 1};
        anime_docs_on_page = await MongoDB.anime_collection().find(query_filter, projection).sort("name", 1).skip(skip_count).limit(config.PAGE_SIZE).to_list(config.PAGE_SIZE);


        filter_info_text = "";
        if active_filter_data:
             filter_info_parts = [];
             if active_filter_data.get("genres"): filter_info_parts.append(f"Genres: {', '.join(active_filter_data['genres'])}");
             if active_filter_data.get("year") is not None: filter_info_parts.append(f"Year: {active_filter_data['year']}");
             if active_filter_data.get("status"): filter_info_parts.append(f"Status: {active_filter_data['status']}");
             if filter_info_parts: filter_info_text = "Active Filters: " + "; ".join(filter_info_parts) + "\n\n";


        menu_text = strings.BROWSE_LIST_TITLE + filter_info_text; buttons = [];
        if not anime_docs_on_page: menu_text += "😔 No anime found matching these criteria.";
        else:
             menu_text += f"Page <b>{page}</b> / <b>{total_pages}</b>\n\n";
             for anime_doc in anime_docs_on_page:
                 anime_name = anime_doc.get("name", "Unnamed Anime"); anime_id_str = str(anime_doc["_id"]);
                 status = anime_doc.get("status", "Unknown"); year = anime_doc.get("release_year", "Unknown Year"); downloads = anime_doc.get("overall_download_count", 0);
                 button_label = f"🔍 {anime_name} ({status}, {year}) [{downloads} ↓]";

                 buttons.append([InlineKeyboardButton(button_label, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")]));


        pagination_buttons = [];
        if total_anime_count > config.PAGE_SIZE: # Only show pagination if total results is more than one page size (different check logic)
             if page > 1: pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_PREVIOUS_PAGE, callback_data=f"browse_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}{page - 1}"));
             if page < total_pages: pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_NEXT_PAGE, callback_data=f"browse_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}{page + 1}"));

        if pagination_buttons: buttons.append(pagination_buttons);


        buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")]);
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]);

        reply_markup = InlineKeyboardMarkup(buttons);

        await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True);

     except Exception as e:
         browse_logger.error(f"FATAL error displaying browsed anime list page {page} for user {user_id}: {e}", exc_info=True);
         await MongoDB.clear_user_state(user_id);
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
         await browse_main_menu_callback(client, callback_query);


@Client.on_callback_query(filters.regex(f"^browse_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def browse_list_page_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; message = callback_query.message; data = callback_query.data;
    try: parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 2: raise ValueError("Invalid pagination callback data format."); target_page = int(parts[1]);
    except ValueError: browse_logger.warning(f"User {user_id} invalid page number in browse list pagination callback: {data}"); await client.answer_callback_query(message.id, "🚫 Invalid page number.", show_alert=False); return;

    try: await client.answer_callback_query(message.id, f"Loading page {target_page}...");
    except Exception: browse_logger.warning(f"Failed to answer callback {data} from user {user_id}");

    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "browse" and user_state.step == BrowseState.BROWSING_LIST):
        browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking browse pagination. Data: {data}. Clearing state.");
        await edit_or_send_message(client, message.chat.id, message.id, "🔄 Invalid state for pagination. Please return to the Browse Menu.", disable_web_page_preview=True);
        await browse_main_menu_callback(client, callback_query); return;


    active_filter_data = user_state.data.get("filter_data", {});
    db_query_filter = {}; selected_genres = active_filter_data.get("genres", []); selected_year = active_filter_data.get("year"); selected_status = active_filter_data.get("status");
    if selected_genres: db_query_filter["genres"] = {"$all": selected_genres};
    if selected_year is not None: db_query_filter["release_year"] = selected_year;
    if selected_status: db_query_filter["status"] = selected_status;


    browse_logger.info(f"User {user_id} browsing list page {target_page} with filters: {db_query_filter}. Source callback: {data}");

    user_state.data["page"] = target_page;
    await MongoDB.set_user_state(user_id, "browse", BrowseState.BROWSING_LIST, data=user_state.data);


    await display_browsed_anime_list(client, message, db_query_filter, target_page, active_filter_data);


    except Exception as e:
         browse_logger.error(f"FATAL error handling browse pagination callback {data} for user {user_id}: {e}", exc_info=True);
         await MongoDB.clear_user_state(user_id);
         await edit_or_send_message(client, message.chat.id, message.id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
         await browse_main_menu_callback(client, callback_query);


@Client.on_callback_query(filters.regex(f"^browse_clear_filter{config.CALLBACK_DATA_SEPARATOR}(genre|year|status)$") & filters.private)
async def browse_clear_filter_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id; data = callback_query.data;
    try: await client.answer_callback_query(message_id, "Clearing filter...");
    except Exception: browse_logger.warning(f"Failed to answer callback {data} from user {user_id}");

    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "browse"):
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking clear filter. Data: {data}. Clearing state.");
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Browse Menu.", disable_web_page_preview=True);
         await browse_main_menu_callback(client, callback_query); return;


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 2: raise ValueError("Invalid callback data format for clear filter."); filter_type_to_clear = parts[1];

        user_state.data["filter_data"] = user_state.data.get("filter_data", {});

        if filter_type_to_clear in user_state.data["filter_data"]:
             del user_state.data["filter_data"][filter_type_to_clear];
             browse_logger.info(f"User {user_id} cleared {filter_type_to_clear} filter. New filter data: {user_state.data['filter_data']}");
        else:
             browse_logger.debug(f"User {user_id} clicked clear filter for {filter_type_to_clear} but it wasn't set in state data.");

        await MongoDB.set_user_state(user_id, "browse", BrowseState.MAIN_MENU, data={**user_state.data});

        await browse_main_menu_callback(client, callback_query);

    except ValueError as e:
        browse_logger.warning(f"User {user_id} invalid filter type in clear filter callback: {data}: {e}"); await client.answer_callback_query(message_id, "🚫 Invalid filter type to clear.", show_alert=False);
    except Exception as e:
         browse_logger.error(f"FATAL error handling browse clear filter callback {data} for user {user_id}: {e}", exc_info=True);
         await MongoDB.clear_user_state(user_id);
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
         await browse_main_menu_callback(client, callback_query);


@Client.on_callback_query(filters.regex(f"^browse_select_anime{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def browse_select_anime_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id; data = callback_query.data;

    try: await client.answer_callback_query(message_id, "Loading anime details...");
    except Exception: browse_logger.warning(f"Failed to answer callback query {data} from user {user_id}.");

    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler in ["browse", "search"] and user_state.step in [BrowseState.BROWSING_LIST, search_handler.SearchState.RESULTS_LIST]):
         browse_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking select anime. Data: {data}. Clearing state.");
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting anime.", disable_web_page_preview=True);
         await browse_main_menu_callback(client, callback_query); return;


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 2: raise ValueError("Invalid callback data format."); anime_id_str = parts[1];

        browse_logger.info(f"User {user_id} selected anime {anime_id_str} from {user_state.handler} list.");

        anime = await MongoDB.get_anime_by_id(anime_id_str);

        if not anime:
            browse_logger.error(f"Selected anime {anime_id_str} not found in DB for user {user_id} browsing/searching.");
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found in database.", disable_web_page_preview=True);

            if user_state.handler == "browse" and user_state.step == BrowseState.BROWSING_LIST:
                query_filter = {};
                active_filter_data = user_state.data.get("filter_data", {}); selected_genres = active_filter_data.get("genres", []); selected_year = active_filter_data.get("year"); selected_status = active_filter_data.get("status");

                if selected_genres: query_filter["genres"] = {"$all": selected_genres};
                if selected_year is not None: query_filter["release_year"] = selected_year;
                if selected_status: query_filter["status"] = selected_status;
                page = user_state.data.get("page", 1);

                await display_browsed_anime_list(client, callback_query.message, query_filter, page, active_filter_data);

            else:
                await MongoDB.clear_user_state(user_id);
                await browse_main_menu_callback(client, callback_query);


            return;

        # Capture source handler before changing state
        source_handler_name = user_state.handler # "browse" or "search"

        await MongoDB.set_user_state(user_id, user_state.handler, 'viewing_anime_details', data={**user_state.data, "viewing_anime_id": str(anime.id), "source_handler": source_handler_name}); # Add source_handler context


        await display_user_anime_details_menu(client, callback_query.message, anime);

    except ValueError:
        browse_logger.warning(f"User {user_id} invalid anime ID data in callback: {data}");
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid anime data in callback.", disable_web_page_preview=True);

    except Exception as e:
        browse_logger.error(f"FATAL error handling browse_select_anime callback {data} for user {user_id}: {e}", exc_info=True);
        await MongoDB.clear_user_state(user_id);
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
        await browse_main_menu_callback(client, callback_query);


# --- Helper to display anime details menu to the user (Shared) ---
# This function is used by browse_handler (browse_select_anime_callback)
# AND by search_handler (after successful search result selection)
# It initiates the user's "download workflow" conceptually (selecting seasons/episodes/files)
async def display_user_anime_details_menu(client: Client, message: Message, anime: Anime):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;

    details_text = strings.ANIME_DETAILS_TITLE + "\n\n" + strings.ANIME_DETAILS_FORMAT.format(
         title=anime.name,
         synopsis=anime.synopsis if anime.synopsis else '<i>Not available.</i>',
         genres=', '.join(anime.genres) if anime.genres else '<i>Not specified.</i>',
         release_year=anime.release_year if anime.release_year else '<i>Unknown Year.</i>',
         status=anime.status if anime.status else '<i>Unknown Status.</i>',
         total_seasons_declared=anime.total_seasons_declared,
         poster_link=f"https://t.me/iv?url=https://example.com/posterview?id={anime.poster_file_id}&rhash=xyz" # Example IV link
     ).replace('<a href="https://t.me/iv?url=https://example.com/posterview?id=None&rhash=xyz">🖼️ Poster</a>', '<i>No poster set.</i>')


    user = await MongoDB.users_collection().find_one({"user_id": user_id}, {"watchlist": 1}); # Get only watchlist for user
    watchlist_button = None;
    if user is None: browse_logger.error(f"Failed to get user {user_id} while displaying anime details menu for watchlist check.");
    else:
         watchlist_anime_ids = user.get("watchlist", []); # list of ObjectIds
         anime_id_obj = ObjectId(anime.id); # Convert anime ID string to ObjectId for comparison
         is_on_watchlist = anime_id_obj in watchlist_anime_ids;
         if is_on_watchlist: watchlist_button = InlineKeyboardButton(strings.BUTTON_REMOVE_FROM_WATCHLIST, callback_data=f"watchlist_remove{config.CALLBACK_DATA_SEPARATOR}{anime.id}");
         else: watchlist_button = InlineKeyboardButton(strings.BUTTON_ADD_TO_WATCHLIST, callback_data=f"watchlist_add{config.CALLBACK_DATA_SEPARATOR}{anime.id}");


    buttons = [];
    if anime.seasons:
        details_text += f"\n{strings.SEASON_LIST_TITLE_USER.format(anime_title=anime.name)}\n";
        seasons = sorted(anime.seasons, key=lambda s: s.season_number);
        for season in seasons:
             season_number = season.season_number; episodes_list = season.episodes; ep_count = len(episodes_list);
             button_label = f"📺 Season {season_number}"; if ep_count > 0: button_label += f" ({ep_count} Episodes)";
             buttons.append([InlineKeyboardButton(button_label, callback_data=f"download_select_season{config.CALLBACK_DATA_SEPARATOR}{anime.id}{config.CALLBACK_DATA_SEPARATOR}{season_number}")]));

    nav_buttons_row = [];
    user_state = await MongoDB.get_user_state(user_id);
    source_handler = user_state.data.get("source_handler") if user_state else None;

    back_callback = "browse_main_menu";
    if source_handler == "browse": back_callback = "browse_main_menu"; # Simple back
    elif source_handler == "search": back_callback = "search_awaiting_query"; # Simple back to search prompt

    nav_buttons_row.append(InlineKeyboardButton(strings.BUTTON_BACK, callback_data=back_callback));

    if watchlist_button: nav_buttons_row.append(watchlist_button);
    nav_buttons_row.append(InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home"));

    if nav_buttons_row: buttons.append(nav_buttons_row);

    await edit_or_send_message(client, chat_id, message_id, details_text, InlineKeyboardMarkup(buttons), disable_web_page_preview=True);
