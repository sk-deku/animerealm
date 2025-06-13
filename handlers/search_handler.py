# handlers/search_handler.py
import logging
import asyncio
from typing import Union, List, Dict, Any, Tuple
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

from database.models import User, Anime
from database.mongo_db import get_user_state, set_user_state, clear_user_state


# Import helper for getting user status/premium check from common_handlers
from handlers.common_handlers import get_user # Use this helper


# Import fuzzy search library
from fuzzywuzzy import process


search_logger = logging.getLogger(__name__)

# --- Search States ---
# handler: "search"
class SearchState:
    AWAITING_QUERY = "search_awaiting_query"
    RESULTS_LIST = "search_results_list"
    # 'viewing_anime_details' state is shared with browse handler implicitly

# Helper to display anime details menu to the user (shared with browse)
# Redefined here for clarity as used within this file.
async def display_user_anime_details_menu(client: Client, message: Message, anime: Anime):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;

     details_text = strings.ANIME_DETAILS_TITLE + "\n\n" + strings.ANIME_DETAILS_FORMAT.format(
          title=anime.name,
          synopsis=anime.synopsis if anime.synopsis else '<i>Not available.</i>',
          genres=', '.join(anime.genres) if anime.genres else '<i>Not specified.</i>',
          release_year=anime.release_year if anime.release_year else '<i>Unknown Year.</i>',
          status=anime.status if anime.status else '<i>Unknown Status.</i>',
          total_seasons_declared=anime.total_seasons_declared,
          # Use placeholder link logic consistent with browse
          poster_link=f"https://tme.ly/{str(anime.poster_file_id)}" # Example IV link simplified
      ).replace(f'<a href="https://tme.ly/None">🖼️ Poster</a>', '<i>No poster set.</i>') # Remove tag if poster ID is None


     user = await MongoDB.users_collection().find_one({"user_id": user_id}, {"watchlist": 1}); # Get only watchlist for user
     watchlist_button = None;
     if user is None: search_logger.error(f"Failed to get user {user_id} while displaying anime details menu for watchlist check.");
     else:
          watchlist_anime_ids = user.get("watchlist", []);
          anime_id_obj = ObjectId(anime.id);
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
     if source_handler == "browse": back_callback = "browse_main_menu";
     elif source_handler == "search": back_callback = "search_awaiting_query"; # Back to search prompt

     nav_buttons_row.append(InlineKeyboardButton(strings.BUTTON_BACK, callback_data=back_callback));

     if watchlist_button: nav_buttons_row.append(watchlist_button);
     nav_buttons_row.append(InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home"));

     if nav_buttons_row: buttons.append(nav_buttons_row);

     await edit_or_send_message(client, chat_id, message_id, details_text, InlineKeyboardMarkup(buttons), disable_web_page_preview=True);


# --- Entry Point for Search ---

@Client.on_message(filters.command("search") & filters.private)
@Client.on_callback_query(filters.regex("^menu_search$") & filters.private)
async def search_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    user_id = update.from_user.id;
    is_callback = isinstance(update, CallbackQuery);
    message = update if isinstance(update, Message) else update.message;
    chat_id = message.chat.id;
    message_id = message.id;


    try:
        if is_callback: await update.answer()
        else: pass
    except Exception: search_logger.warning(f"Failed to answer callback menu_search from user {user_id}");


    user_state = await MongoDB.get_user_state(user_id);

    if user_state and user_state.handler != "search":
        search_logger.warning(f"User {user_id} in state {user_state.handler}:{user_state.step} clicking search. Clearing old state.");
        await MongoDB.clear_user_state(user_id);

    await MongoDB.set_user_state(user_id, "search", SearchState.AWAITING_QUERY, data={});

    prompt_text = strings.SEARCH_PROMPT.format();

    target_message_id = message_id if is_callback else None;

    await edit_or_send_message(client, chat_id, target_message_id, prompt_text, disable_web_page_preview=True);

async def handle_search_query_text(client: Client, message: Message, query_text: str, user: User):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
    search_logger.info(f"User {user_id} searching for: '{query_text}'.");
    user_state = await MongoDB.get_user_state(user_id);

    if user_state and user_state.handler == "search" and user_state.step == SearchState.AWAITING_QUERY: await MongoDB.clear_user_state(user_id);


    await MongoDB.set_user_state(user_id, "search", SearchState.RESULTS_LIST, data={"query": query_text, "page": 1});
    try: await message.reply_text("🔍 Searching database...", parse_mode=config.PARSE_MODE);
    except Exception as e: search_logger.warning(f"Failed to reply search loading message to user {user_id}: {e}");

    try:
        db_query_filter: Dict[str, Any] = {};
        if len(query_text) > 3: db_query_filter = {"$text": {"$search": query_text}};

        projection = {"name": 1, "_id": 1, "status": 1, "release_year": 1, "overall_download_count": 1};
        sort_criteria: List[Tuple[str, Union[int, Dict[str, Any]]]] = [("name", 1)];
        if db_query_filter: projection["score"] = {"$meta": "textScore"}; sort_criteria.insert(0, ("score", {"$meta": "textScore"}));
        anime_docs_subset = await MongoDB.anime_collection().find(db_query_filter, projection).sort(sort_criteria).limit(200).to_list(200);


        if anime_docs_subset:
            anime_name_to_doc_dict = {doc['name']: doc for doc in anime_docs_subset}; anime_names_list = list(anime_name_to_doc_dict.keys());
            fuzzy_results_raw = process.extract(query_text, anime_names_list, limit=config.PAGE_SIZE * 3); # Get more candidates before threshold

            matching_anime_filtered = [];
            for name_match, score in fuzzy_results_raw:
                 if score >= config.FUZZYWUZZY_THRESHOLD:
                      original_doc = anime_name_to_doc_dict.get(name_match); # Use get with fallback
                      if original_doc: matching_anime_filtered.append(original_doc);


            matching_anime_filtered.sort(key=lambda doc: doc.get("name", ""));

            result_anime_ids_str = [str(doc['_id']) for doc in matching_anime_filtered];

            await MongoDB.set_user_state(user_id, "search", SearchState.RESULTS_LIST, data={"query": query_text, "result_ids": result_anime_ids_str, "page": 1});

            page_size = config.PAGE_SIZE; page_number = 1; start_index = (page_number - 1) * page_size; end_index = start_index + page_size;
            anime_docs_for_display_page = matching_anime_filtered[start_index:end_index];


            await display_search_results_list(client, message, query_text, anime_docs_for_display_page, user);


        else:
             db_query_filter_all = {} # Query all to check total count
             if await MongoDB.anime_collection().count_documents(db_query_filter_all) < 500: # Check threshold against total count (more relevant than subset size)
                 all_anime_names_docs = await MongoDB.anime_collection().find(db_query_filter_all, {"name": 1, "_id": 1}).to_list(None);
                 all_anime_names_dict = {doc['name']: str(doc['_id']) for doc in all_anime_names_docs};
                 fuzzy_results_raw = process.extract(query_text, all_anime_names_dict.keys(), limit=config.PAGE_SIZE * 3); # Try global fuzzy

                 matching_anime_filtered = [];
                 for name_match, score in fuzzy_results_raw:
                      if score >= config.FUZZYWUZZY_THRESHOLD:
                          anime_id_str = all_anime_names_dict.get(name_match) # Use get
                          if anime_id_str:
                             full_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, projection); # Fetch relevant fields
                             if full_anime_doc: matching_anime_filtered.append(full_anime_doc);


                 if matching_anime_filtered: # Found results after global fuzzy
                     search_logger.debug(f"User {user_id} fuzzy matched {len(matching_anime_filtered)} docs (score>={config.FUZZYWUZZY_THRESHOLD}) for '{query_text}' after text search failed (global).");
                     result_anime_ids_str = [str(doc['_id']) for doc in matching_anime_filtered];
                     await MongoDB.set_user_state(user_id, "search", SearchState.RESULTS_LIST, data={"query": query_text, "result_ids": result_anime_ids_str, "page": 1});
                     page_size = config.PAGE_SIZE; page_number = 1; start_index = (page_number - 1) * page_size; end_index = start_index + page_size;
                     anime_docs_for_display_page = matching_anime_filtered[start_index:end_index];
                     await display_search_results_list(client, message, query_text, anime_docs_for_display_page, user);

                 else: # Still no results after global fuzzy
                    search_logger.debug(f"User {user_id} search found 0 results for '{query_text}' after text search and global fuzzy.");
                    await MongoDB.set_user_state(user_id, "search", SearchState.RESULTS_LIST, data={"query": query_text, "result_ids": [], "page": 1});
                    await display_search_no_results(client, message, query_text, user);


             else:
                  search_logger.debug(f"User {user_id} search found 0 results after text search and total count too large for global fuzzy.");
                  await MongoDB.set_user_state(user_id, "search", SearchState.RESULTS_LIST, data={"query": query_text, "result_ids": [], "page": 1});
                  await display_search_no_results(client, message, query_text, user);

    except Exception as e:
        search_logger.error(f"FATAL error during search query processing for user {user_id} query '{query_text}': {e}", exc_info=True);
        user_state = await MongoDB.get_user_state(user_id); if user_state and user_state.handler == "search": await MongoDB.clear_user_state(user_id);
        await message.reply_text(strings.ERROR_OCCURRED, parse_mode=config.PARSE_MODE);

async def display_search_results_list(client: Client, message: Message, query: str, results_on_page: List[Dict], user: User):
    user_id = user.user_id; chat_id = message.chat.id; message_id = message.id;
    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "search" and user_state.step == SearchState.RESULTS_LIST):
         search_logger.error(f"display_search_results_list called in invalid state {user_state.handler}:{user_state.step if user_state else 'None'} for user {user_id}. State data: {user_state.data}. Query: {query}.");
         await edit_or_send_message(client, chat_id, message_id, "💔 Error loading search results state.", disable_web_page_preview=True);
         await MongoDB.clear_user_state(user_id); return;

    total_results = len(user_state.data.get("result_ids", [])); page = user_state.data.get("page", 1); page_size = config.PAGE_SIZE;
    total_pages = (total_results + page_size - 1) // page_size; if total_pages == 0: total_pages = 1; if page < 1: page = 1; if page > total_pages: page = total_pages;

    menu_text = strings.SEARCH_RESULTS_TITLE.format(query=query) + "\n\n"; buttons = [];
    if total_results == 0: menu_text += "😔 No anime found matching this query.";
    else:
         menu_text += f"Page <b>{page}</b> / <b>{total_pages}</b>\n\n";
         for result_doc in results_on_page:
              anime_name = result_doc.get("name", "Unnamed Anime"); anime_id_str = str(result_doc["_id"]);
              status = result_doc.get("status", "Unknown"); year = result_doc.get("release_year", "Unknown Year"); downloads = result_doc.get("overall_download_count", 0);
              button_label = f"🔍 {anime_name} ({status}, {year}) [{downloads} ↓]";
              buttons.append([InlineKeyboardButton(button_label, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")]));

    pagination_buttons = [];
    if total_results > page_size:
        if page > 1: pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_PREVIOUS_PAGE, callback_data=f"search_results_page{config.CALLBACK_DATA_SEPARATOR}{page - 1}"));
        if page < total_pages: pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_NEXT_PAGE, callback_data=f"search_results_page{config.CALLBACK_DATA_SEPARATOR}{page + 1}"));

    if pagination_buttons: buttons.append(pagination_buttons);

    buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="search_awaiting_query")]);
    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]);
    reply_markup = InlineKeyboardMarkup(buttons);

    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True);

@Client.on_callback_query(filters.regex(f"^search_results_page{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def search_results_page_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; message = callback_query.message; data = callback_query.data;
    try: parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 2: raise ValueError("Invalid pagination callback data format."); target_page = int(parts[1]);
    except ValueError: search_logger.warning(f"User {user_id} invalid page number in search list pagination callback: {data}"); await client.answer_callback_query(message.id, "🚫 Invalid page number.", show_alert=False); return;

    try: await client.answer_callback_query(message.id, f"Loading page {target_page}...");
    except Exception: search_logger.warning(f"Failed to answer callback {data} from user {user_id}");

    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "search" and user_state.step == SearchState.RESULTS_LIST):
        search_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking search pagination. Data: {data}. Clearing state.");
        await edit_or_send_message(client, message.chat.id, message.id, "🔄 Invalid state for pagination. Please return to the Search Menu.", disable_web_page_preview=True);
        await search_command_or_callback(client, callback_query); return;

    original_query = user_state.data.get("query", ""); result_ids_str = user_state.data.get("result_ids", []);
    if not original_query or not result_ids_str:
        search_logger.error(f"User {user_id} in RESULTS_LIST state, but missing original query or result IDs in state data: {user_state.data}");
        await edit_or_send_message(client, message.chat.id, message.id, "💔 Error: Search results state data missing. Please try a new search.", disable_web_page_preview=True);
        await MongoDB.clear_user_state(user_id); return;

    total_results = len(result_ids_str); page_size = config.PAGE_SIZE; total_pages = (total_results + page_size - 1) // page_size; if total_pages == 0: total_pages = 1;
    if target_page < 1: target_page = 1; if target_page > total_pages: target_page = total_pages;

    start_index = (target_page - 1) * page_size; end_index = start_index + page_size;
    ids_for_page = result_ids_str[start_index:end_index];

    if not ids_for_page: anime_docs_on_page: List[Dict] = [];
    else:
        fetch_filter = {"_id": {"$in": [ObjectId(anime_id) for anime_id in ids_for_page]}};
        projection = {"name": 1, "_id": 1, "status": 1, "release_year": 1, "overall_download_count": 1};
        anime_docs_on_page = await MongoDB.anime_collection().find(fetch_filter, projection).sort("name", 1).to_list(page_size);


    search_logger.debug(f"User {user_id} browsing search results page {target_page}. Fetched {len(anime_docs_on_page)} docs.");
    user_state.data["page"] = target_page; await MongoDB.set_user_state(user_id, "search", SearchState.RESULTS_LIST, data=user_state.data);

    user = await get_user(client, user_id); if user is None: search_logger.error(f"User {user_id} not found for search pagination display."); # Continue with error
    await display_search_results_list(client, message, original_query, anime_docs_on_page, user if user else {} as user ); # Pass user


    except Exception as e:
         search_logger.error(f"FATAL error handling search pagination callback {data} for user {user_id}: {e}", exc_info=True);
         await MongoDB.clear_user_state(user_id);
         await edit_or_send_message(client, message.chat.id, message.id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
         await search_command_or_callback(client, callback_query);

async def display_search_no_results(client: Client, message: Message, query: str, user: User):
    user_id = user.user_id; chat_id = message.chat.id; message_id = message.id;

    menu_text = strings.NO_ANIME_FOUND_SEARCH.format(query=query) + "\n\n"; buttons = [];
    request_button_text = None; request_callback_data = None;

    if user.premium_status != "free":
        request_button_text = strings.SEARCH_NO_MATCHES_REQUEST_BUTTON_PREMIUM.format(query=query);
        request_callback_data = f"request_anime{config.CALLBACK_DATA_SEPARATOR}{query}";
    elif config.REQUEST_TOKEN_COST > 0:
         if user.tokens >= config.REQUEST_TOKEN_COST:
              request_button_text = strings.SEARCH_NO_MATCHES_REQUEST_BUTTON_FREE.format(query=query, cost=config.REQUEST_TOKEN_COST);
              request_callback_data = f"request_anime{config.CALLBACK_DATA_SEPARATOR}{query}";
         else: menu_text += strings.NOT_ENOUGH_TOKENS.format(required_tokens=config.REQUEST_TOKEN_COST, user_tokens=user.tokens) + "\n\n";
    elif config.REQUEST_TOKEN_COST == 0: request_button_text = strings.SEARCH_NO_MATCHES_REQUEST_BUTTON_FREE.format(query=query, cost=config.REQUEST_TOKEN_COST); request_callback_data = f"request_anime{config.CALLBACK_DATA_SEPARATOR}{query}";


    if request_button_text and request_callback_data: buttons.append([InlineKeyboardButton(request_button_text, callback_data=request_callback_data)]);
    else:
         if user.premium_status == "free" and config.REQUEST_TOKEN_COST > 0: menu_text += strings.REQUEST_FROM_SEARCH_ONLY_PREMIUM.format() + "\n\n";

    buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="search_awaiting_query")]);
    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]);
    reply_markup = InlineKeyboardMarkup(buttons);

    await message.reply_text(menu_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True);
