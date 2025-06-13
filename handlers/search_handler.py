# handlers/search_handler.py
import logging
import asyncio
from typing import Union, List, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified
)

# Import config
import config
# Import strings
import strings

# Import database methods
from database.mongo_db import MongoDB

# Import models for type hinting/validation
from database.models import User, Anime

# Import user-getting helper
from handlers.common_handlers import get_user
# Import helper to display anime details menu (shared with browse)
from handlers.browse_handler import display_user_anime_details_menu


# Fuzzy search library
from fuzzywuzzy import process

search_logger = logging.getLogger(__name__)


# --- Search States ---
# handler: "search"
class SearchState:
    AWAITING_QUERY = "search_awaiting_query" # Waiting for the user to send text for the search query
    RESULTS_LIST = "search_results_list" # Displaying search results list
    # 'viewing_anime_details' state is shared with browse handler, set in browse_select_anime_callback


# --- Entry Point for Search ---

@Client.on_message(filters.command("search") & filters.private)
@Client.on_callback_query(filters.regex("^menu_search$") & filters.private)
async def search_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    user_id = update.from_user.id
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    message_id = update.id if isinstance(update, Message) else update.message.id
    is_callback = isinstance(update, CallbackQuery)

    # Answer callback immediately
    try:
         # If from command, answer None (implicit). If callback, answer it.
         if is_callback: await client.answer_callback_query(message.id)
     # Or answer always just message_id? No, if update is Message, update.id is message_id.
     # Try answer using update.id regardless of type, Pyrogram should handle it? No, needs callback id.
     # Better: if isinstance(update, CallbackQuery): await update.answer()
         if is_callback: await update.answer()
         else: pass # No answer needed for messages
     except Exception: search_logger.warning(f"Failed to answer callback menu_search from user {user_id}")


    user_state = await MongoDB.get_user_state(user_id) # Use DB helper

    # Clear any previous state if they explicitly enter search via command/button
    if user_state and user_state.handler != "search":
        search_logger.warning(f"User {user_id} in state {user_state.handler}:{user_state.step} explicitly starting new search. Clearing old state.")
        await MongoDB.clear_user_state(user_id)

    # Set state to awaiting query for text input
    await MongoDB.set_user_state(user_id, "search", SearchState.AWAITING_QUERY, data={}) # No specific data needed yet


    prompt_text = strings.SEARCH_PROMPT.format()

    # If coming from command, reply to the command. If from callback, edit the message the button was on.
    target_message_id = message_id if is_callback else None

    await edit_or_send_message(client, chat_id, target_message_id, prompt_text, disable_web_page_preview=True)

    # Note: Actual text input handling is in common_handlers, which routes to handle_search_query_text


# --- Handle Search Query Input (Text Input when in AWAITING_QUERY state OR Default Input) ---
# This function is called by common_handlers.handle_plain_text_input

async def handle_search_query_text(client: Client, message: Message, query_text: str, user: User):
    """
    Performs fuzzy search on anime names based on user text input.
    Displays search results as a paginated list or a 'no results' message with request option.
    Called by common_handlers.handle_plain_text_input.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id

    search_logger.info(f"User {user_id} searching for: '{query_text}'.")

    # Get current state - will be AWAITING_QUERY if initiated by command/callback prompt,
    # or might be None if text input was treated as default action.
    # In either case, after processing this query, state should be RESULTS_LIST.
    user_state = await MongoDB.get_user_state(user_id)

    # If user was in AWAITING_QUERY, clear that state now that query is received.
    # If user was in RESULTS_LIST and sent new text, treat as NEW search, state will be updated below.
    if user_state and user_state.handler == "search" and user_state.step == SearchState.AWAITING_QUERY:
        await MongoDB.clear_user_state(user_id) # Clear input prompt state


    # --- Perform Fuzzy Search ---
    # Query documents for name matching the query text.
    # Use text index first if query is long enough for basic tokenization
    # Limit the results from the DB query to a reasonable number before doing fuzzy match on them.
    # Then use fuzzywuzzy to find closest matches in this smaller set.

    try:
        # Basic Text Search (if query > min length) as initial filter
        db_query_filter: Dict[str, Any] = {}
        if len(query_text) > 3: # Arbitrary length threshold for text index efficiency
             db_query_filter = {"$text": {"$search": query_text}}

        # Project relevant fields for search results list display (name, status, year, download count, _id)
        projection = {"name": 1, "_id": 1, "status": 1, "release_year": 1, "overall_download_count": 1}

        # Fetch a reasonable subset of anime docs, sorting by text score (if using text search) or alphabetically otherwise
        sort_criteria: List[Tuple[str, Union[int, Dict[str, Any]]]] = [("name", 1)] # Default sort
        if db_query_filter: # If text search filter is used, add text score sort priority
            projection["score"] = {"$meta": "textScore"} # Project score to sort by it
            sort_criteria.insert(0, ("score", {"$meta": "textScore"})) # Sort by score first

        # Limit the initial database fetch for fuzzy matching candidates
        anime_docs_subset = await MongoDB.anime_collection().find(db_query_filter, projection).sort(sort_criteria).limit(200).to_list(200) # Limit candidates

        # Build a dictionary of name (string) -> full document dictionary from the subset for fuzzy matching
        # This allows retrieving full projected data after fuzzy match.
        anime_name_to_doc_dict = {doc['name']: doc for doc in anime_docs_subset}
        anime_names_list = list(anime_name_to_doc_dict.keys())


        # Perform fuzzy matching using fuzzywuzzy's process.extract on the subset of names
        # Extract the top N matches based on score.
        # Use a slightly higher limit than display PAGE_SIZE initially if needing robust result ordering later.
        fuzzy_results_raw = process.extract(query_text, anime_names_list, limit=config.PAGE_SIZE * 2)

        # Filter fuzzy results by the confidence score threshold
        matching_anime_filtered = []
        for name_match, score in fuzzy_results_raw:
             if score >= config.FUZZYWUZZY_THRESHOLD:
                 # Retrieve the original projected document from the dictionary
                 original_doc = anime_name_to_doc_dict[name_match]
                 matching_anime_filtered.append(original_doc) # Store the projected doc for display


        # Sort final list of matching anime (e.g., by name for consistency)
        # This sorting happens *after* fuzzy filtering, applies to the display list.
        # Re-sorting by relevance based on fuzzy score isn't standard in display list buttons usually.
        # Let's sort by name.
        matching_anime_filtered.sort(key=lambda doc: doc.get("name", ""))


        search_logger.info(f"User {user_id} search for '{query_text}': {len(matching_anime_filtered)} results found after fuzzy score filter (threshold {config.FUZZYWUZZY_THRESHOLD}).")

        # --- Display Search Results List or No Results Message ---
        if matching_anime_filtered:
             # Found results, display as a paginated list similar to browse.
             # State needs to store the QUERY STRING itself to re-perform search for pagination!
             # Or, store the LIST of result _ids + query string? List of IDs is smaller.
             # Let's store list of result _id strings and the query string in state data.
             # Query string for 'No Results, Request' back link or displaying in header.
             # List of _ids for retrieving documents on later pages if implemented.

             result_anime_ids_str = [str(doc['_id']) for doc in matching_anime_filtered] # Get just the list of IDs


             # Set state to RESULTS_LIST. Store original query and result IDs list, and page 1.
             # No need to store full docs, can fetch from DB by ID when displaying specific page.
             await MongoDB.set_user_state(
                  user_id,
                  "search",
                  SearchState.RESULTS_LIST,
                  data={"query": query_text, "result_ids": result_anime_ids_str, "page": 1}
              )

             # Display the search results list using a helper function.
             # Pass the original query and the list of matching documents for *this* page.
             # Needs to simulate pagination logic for the display. Let's display first page directly.
             page_size = config.PAGE_SIZE
             page_number = 1
             start_index = (page_number - 1) * page_size
             end_index = start_index + page_size
             anime_docs_for_display_page = matching_anime_filtered[start_index:end_index] # Slice the full list for the first page

             await display_search_results_list(client, message, query_text, anime_docs_for_display_page, user)


        else:
             # No results found after filtering, display message and offer request option.
             # State is still RESULTS_LIST? Or a separate NO_RESULTS state?
             # Let state remain RESULTS_LIST with an empty result_ids list. Simplifies state handling.
             await MongoDB.set_user_state(user_id, "search", SearchState.RESULTS_LIST, data={"query": query_text, "result_ids": [], "page": 1}) # Store empty list and query


             await display_search_no_results(client, message, query_text, user)


    except Exception as e:
        # Error during search execution (DB query, fuzzy matching, data processing)
        search_logger.error(f"FATAL error during search query processing for user {user_id} query '{query_text}': {e}", exc_info=True)
        # Clear the results state on error
        # Get current state, should be RESULTS_LIST by now.
        user_state = await MongoDB.get_user_state(user_id)
        if user_state and user_state.handler == "search": await MongoDB.clear_user_state(user_id)

        await message.reply_text(strings.ERROR_OCCURRED, parse_mode=config.PARSE_MODE) # Reply error message
        # User needs to restart search


# --- Helper to display search results list ---
# Called by handle_search_query_text (for first page) and browse_list_page_callback (for other pages - needs adaptation)
# Note: Re-using browsing list display structure.
async def display_search_results_list(client: Client, message: Message, query: str, results_on_page: List[Dict], user: User):
    user_id = user.user_id
    chat_id = message.chat.id
    message_id = message.id

    user_state = await MongoDB.get_user_state(user_id) # Need state for pagination context (total results, current page, all result IDs)
    if not (user_state and user_state.handler == "search" and user_state.step == SearchState.RESULTS_LIST):
         # This display function called in wrong state.
         search_logger.error(f"display_search_results_list called in invalid state {user_state.handler}:{user_state.step} for user {user_id}. State data: {user_state.data}. Query: {query}.")
         # Try to reset and inform.
         await edit_or_send_message(client, chat_id, message_id, "💔 Error loading search results state.", disable_web_page_preview=True)
         await MongoDB.clear_user_state(user_id); return # Critical state error


    total_results = len(user_state.data.get("result_ids", [])) # Get total count from the list of IDs in state data
    page = user_state.data.get("page", 1)
    page_size = config.PAGE_SIZE
    total_pages = (total_results + page_size - 1) // page_size
    if total_pages == 0: total_pages = 1 # At least one page even if 0 results


    menu_text = strings.SEARCH_RESULTS_TITLE.format(query=query) + "\n\n"

    buttons = []
    if total_results == 0:
         menu_text += "😔 No anime found matching this query." # Displayed if result_ids list in state is empty

    else:
         menu_text += f"Page <b>{page}</b> / <b>{total_pages}</b>\n\n"
         # Create buttons for each result document provided in the `results_on_page` list
         for result_doc in results_on_page:
              anime_name = result_doc.get("name", "Unnamed Anime")
              anime_id_str = str(result_doc["_id"])

              # Format button label for clarity (Name (Status, Year) [Downloads])
              status = result_doc.get("status", "Unknown")
              year = result_doc.get("release_year", "Unknown Year")
              downloads = result_doc.get("overall_download_count", 0)

              button_label = f"🔍 {anime_name} ({status}, {year}) [{downloads} ↓]"

              # Callback to select anime details/download flow: browse_select_anime|<anime_id> (Reuses browse handler's logic)
              # State transition: search_handler:RESULTS_LIST -> browse_handler:viewing_anime_details (with source_handler='search' in data)
              buttons.append([InlineKeyboardButton(button_label, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")])


    # --- Pagination Buttons (Re-uses logic structure from browse_handler but links back to search paging) ---
    pagination_buttons = []
    if total_results > page_size: # Only show pagination if there's more than one page of results
        if page > 1:
            # Callback: search_results_page|<target_page>
             pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_PREVIOUS_PAGE, callback_data=f"search_results_page{config.CALLBACK_DATA_SEPARATOR}{page - 1}"))
        if page < total_pages:
             pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_NEXT_PAGE, callback_data=f"search_results_page{config.CALLBACK_DATA_SEPARATOR}{page + 1}"))

    if pagination_buttons: # Only add if there are pagination buttons
         buttons.append(pagination_buttons)

    # Add Navigation buttons: Back to Search Prompt, Back to Main Menu
    buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="search_awaiting_query")]) # Goes back to prompting a new query
    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Main menu


    reply_markup = InlineKeyboardMarkup(buttons)

    # Edit or send the message to display the search results list
    # This could be replying to the loading message or the user's query message
    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)

    # State is SearchState.RESULTS_LIST, stays until user selects anime, cancels, or navigates back/home.


# --- Handle Search Results Pagination ---
# Catches callbacks search_results_page|<page_number>
@Client.on_callback_query(filters.regex(f"^search_results_page{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def search_results_page_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    message = callback_query.message
    data = callback_query.data

    try:
         # Parse target page number
         parts = data.split(config.CALLBACK_DATA_SEPARATOR)
         if len(parts) != 2: raise ValueError("Invalid pagination callback data format.")
         target_page = int(parts[1])

    except ValueError:
         search_logger.warning(f"User {user_id} invalid page number in search list pagination callback: {data}")
         await client.answer_callback_query(message.id, "🚫 Invalid page number.", show_alert=False) # Toast error
         return # Stop processing invalid callback


    try: await client.answer_callback_query(message.id, f"Loading page {target_page}...")
    except Exception: search_logger.warning(f"Failed to answer callback {data} from user {user_id}")

    user_state = await MongoDB.get_user_state(user_id)

    # State should be RESULTS_LIST
    if not (user_state and user_state.handler == "search" and user_state.step == SearchState.RESULTS_LIST):
        search_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking search pagination. Data: {data}. Clearing state.")
        await edit_or_send_message(client, message.chat.id, message.id, "🔄 Invalid state for pagination. Please return to the Search Menu.", disable_web_page_preview=True)
        await search_command_or_callback(client, callback_query) # Re-display search prompt (uses original callback)
        return

    # Retrieve necessary info from state data: original query and list of result IDs
    original_query = user_state.data.get("query", "")
    result_ids_str = user_state.data.get("result_ids", []) # List of result anime ID strings


    if not original_query or not result_ids_str:
        search_logger.error(f"User {user_id} in RESULTS_LIST state, but missing original query or result IDs in state data: {user_state.data}")
        await edit_or_send_message(client, message.chat.id, message.id, "💔 Error: Search results state data missing. Please try a new search.", disable_web_page_preview=True)
        await MongoDB.clear_user_state(user_id); # Clear corrupted state
        return # Stop

    total_results = len(result_ids_str)
    page_size = config.PAGE_SIZE

    # Validate and adjust target page number
    total_pages = (total_results + page_size - 1) // page_size
    if total_pages == 0: total_pages = 1
    if target_page < 1: target_page = 1
    if target_page > total_pages: target_page = total_pages # Prevent going past last page


    # Calculate which slice of result IDs corresponds to the target page
    start_index = (target_page - 1) * page_size
    end_index = start_index + page_size
    ids_for_page = result_ids_str[start_index:end_index] # Slice the list of IDs

    if not ids_for_page:
         # This could happen if calculated page > total pages and total results is 0
         search_logger.warning(f"No IDs to fetch for search results page {target_page} for user {user_id}.")
         # Display list function will show no results, but bounds check should prevent this.
         # Let's fetch 0 docs.
         anime_docs_on_page: List[Dict] = [] # Empty list

    else:
        # Fetch the anime documents for the IDs on this specific page
        # Need to fetch by _id using $in operator for a list of IDs
        fetch_filter = {"_id": {"$in": [ObjectId(anime_id) for anime_id in ids_for_page]}}
        # Project relevant fields for display
        projection = {"name": 1, "_id": 1, "status": 1, "release_year": 1, "overall_download_count": 1}
        # Sort order? Results were sorted by relevance then name during initial search.
        # Maintaining original order requires custom sort using the list of IDs, or sorting in application.
        # Re-sorting by name A-Z after fetching by $in is simpler.
        anime_docs_on_page = await MongoDB.anime_collection().find(fetch_filter, projection).sort("name", 1).to_list(page_size) # Fetch and sort

        # Optional: Re-sort based on the *original* order in result_ids_str list if fidelity needed
        # order_mapping = {id: i for i, id in enumerate(ids_for_page)}
        # anime_docs_on_page.sort(key=lambda doc: order_mapping.get(str(doc['_id']), len(ids_for_page)))


    search_logger.debug(f"User {user_id} browsing search results page {target_page}. Fetched {len(anime_docs_on_page)} docs.")

    # Store the new page number in the state data
    user_state.data["page"] = target_page
    # Save the updated state with the new page number
    await MongoDB.set_user_state(user_id, "search", SearchState.RESULTS_LIST, data=user_state.data)


    # Display the search results list for the target page.
    # The helper expects the list of document dictionaries for the current page.
    # Need to pass the original query and full filter data structure for header display etc.
    # No, filter data isn't used for search results display text, only original query.
    # Pass the full result IDs list implicitly via state.
    await display_search_results_list(client, message, original_query, anime_docs_on_page, user) # Pass original message to edit


    except Exception as e:
         search_logger.error(f"FATAL error handling search pagination callback {data} for user {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, message.chat.id, message.id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await search_command_or_callback(client, callback_query)

# --- Helper to display "No Results" and Request Option ---
# Called by handle_search_query_text
# Requires User object for premium check
async def display_search_no_results(client: Client, message: Message, query: str, user: User):
    user_id = user.user_id
    chat_id = message.chat.id
    message_id = message.id


    # Message text informs no results and offers the request option explanation.
    menu_text = strings.NO_ANIME_FOUND_SEARCH.format(query=query) + "\n\n"

    buttons = []

    # Add Request this anime button based on user premium status and configured token cost
    request_button_text = None
    request_callback_data = None

    # Premium users can request via a dedicated command (/request) or here for free.
    if user.premium_status != "free":
        request_button_text = strings.SEARCH_NO_MATCHES_REQUEST_BUTTON_PREMIUM.format(query=query)
        # Callback data for requesting anime: request_anime|<anime_name>
        # Handled by the request_handler. It needs the anime name query.
        request_callback_data = f"request_anime{config.CALLBACK_DATA_SEPARATOR}{query}" # Pass the search query as the requested name

    # Free users can request only if the configured REQUEST_TOKEN_COST is > 0 AND they have enough tokens.
    elif config.REQUEST_TOKEN_COST > 0:
         if user.tokens >= config.REQUEST_TOKEN_COST:
              # Free user with enough tokens to make the request
              request_button_text = strings.SEARCH_NO_MATCHES_REQUEST_BUTTON_FREE.format(query=query, cost=config.REQUEST_TOKEN_COST)
              # Callback data needs anime name and token cost is handled in the handler logic.
              request_callback_data = f"request_anime{config.CALLBACK_DATA_SEPARATOR}{query}"
         else:
             # Free user, request costs tokens, but user has insufficient tokens.
             # Display the cost info message from strings, which mentions token earning.
             menu_text += strings.NOT_ENOUGH_TOKENS.format(required_tokens=config.REQUEST_TOKEN_COST, user_tokens=user.tokens) + "\n\n"


    # Add the request button if the user qualifies for the direct button option
    if request_button_text and request_callback_data:
         buttons.append([InlineKeyboardButton(request_button_text, callback_data=request_callback_data)])


    # Add navigation buttons: Back to Search Prompt, Back to Main Menu
    buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="search_awaiting_query")]) # Go back to prompting a new query
    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Main menu


    reply_markup = InlineKeyboardMarkup(buttons)

    # Reply to the user's query message with the no results message and options.
    await message.reply_text(menu_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True)

    # State is SearchState.RESULTS_LIST (even with no results), stays until user action.
