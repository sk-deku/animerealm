# bot/anime_search.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler, # For selecting search result
    filters
)
from telegram.constants import ParseMode
from urllib.parse import quote_plus # For encoding query in callback_data if needed

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance
from .core_handlers import check_user_or_add, reply_with_main_menu
from .anime_browser import display_anime_seasons # Re-use for displaying seasons after selection

logger = logging.getLogger(__name__)

# Conversation states
ASK_SEARCH_QUERY, DISPLAY_SEARCH_RESULTS = range(2)

# Constant to indicate this conversation path for callbacks or external triggers
SEARCH_INITIATE = "initiate_search_conversation"


async def search_anime_command_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Entry point for /search [query] or direct search conversation start."""
    user = update.effective_user
    logger.info(f"Search command entry by {user.id} ({user.first_name}), args: {context.args}")

    user_db_doc = await check_user_or_add(update, context)
    if not user_db_doc: return ConversationHandler.END

    if context.args: # Query provided directly with /search command
        query_str = " ".join(context.args)
        await execute_search_and_display(update, context, query_str)
        return ConversationHandler.END # End conversation as search is direct
    else: # No query, start conversation to ask for it
        if update.callback_query: # From "Search Anime" button
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text=strings.SEARCH_PROMPT,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="search_cancel")]]))
        else: # From /search command without args
            await update.message.reply_html(
                text=strings.SEARCH_PROMPT,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="search_cancel")]]))
        return ASK_SEARCH_QUERY


async def ask_search_query_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """If user needs to search again from results view or after a bad query."""
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=strings.SEARCH_PROMPT,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="search_cancel")]]))
    return ASK_SEARCH_QUERY


async def received_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Receives the search query text from the user."""
    user = update.effective_user
    query_str = update.message.text.strip()
    logger.info(f"Search query '{query_str}' received from {user.id} ({user.first_name})")

    if not query_str or len(query_str) < 2: # Basic validation
        await update.message.reply_html("Please enter a valid search term (at least 2 characters).")
        return ASK_SEARCH_QUERY # Ask again

    await execute_search_and_display(update, context, query_str)
    return DISPLAY_SEARCH_RESULTS # Stay in a state to handle selection or pagination


async def execute_search_and_display(update: Update, context: ContextTypes.DEFAULT_TYPE, query_str: str, page_to_display: int = 1):
    """Executes the search and calls the display function."""
    # Store query for potential pagination via text input (though button pagination is better)
    context.user_data['last_search_query_for_pagination'] = query_str # For callback_handler general pagination
    
    # Message to show while searching
    if update.message: # If it's a new message starting search
        searching_msg = await update.message.reply_html(f"{strings.EMOJI_LOADING} Searching for '<code>{query_str}</code>'...")
    else: # If from pagination or other callback, use context.bot.send_message or edit previous
        searching_msg = None # Will be handled by display_search_results_page if editing

    # Perform database search
    # results, total_count = await anidb.search_anime_by_title(query_str, page=page_to_display, per_page=settings.RESULTS_PER_PAGE_GENERAL)
    # Using the regex based one if text search is not robust enough or for simpler fuzziness:
    # `anidb.search_anime_by_title_regex` would need to be created in mongo_db.py
    # For now, stick with the text search from `anidb`.
    
    # This example assumes `search_anime_by_title` (MongoDB text search) is implemented in `mongo_db.py`
    results_docs, total_count = await anidb.search_anime_by_title(
        query=query_str,
        page=page_to_display,
        per_page=settings.RESULTS_PER_PAGE_GENERAL
    )

    if searching_msg: # If we sent a "Searching..." message, delete it
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=searching_msg.message_id)
        except Exception as e:
            logger.debug(f"Could not delete 'Searching...' message: {e}")

    await display_search_results_page(update, context, results_docs, total_count, query_str, page_to_display)


def build_search_results_keyboard(results_docs: list, query_str: str, current_page: int, total_pages: int, total_results: int) -> InlineKeyboardMarkup:
    keyboard = []
    if not results_docs:
        return InlineKeyboardMarkup([[InlineKeyboardButton("No results. Try another search?", callback_data="search_ask_again")]])

    for anime in results_docs:
        # Callback data to select an anime: "search_select_{anime_id}"
        anime_id_str = str(anime['_id'])
        button_text = f"{strings.EMOJI_TV if anime.get('type') != 'Movie' else strings.EMOJI_MOVIE} {anime['title_english'][:50]}" # Truncate long titles
        if len(anime['title_english']) > 50: button_text += "..."
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"search_select_{anime_id_str}")])

    # Pagination buttons
    pagination_row = []
    if current_page > 1:
        # Pass encoded query for stateless pagination if desired: "search_page_{URLENCODED_QUERY}_{page_num-1}"
        # For simplicity with context.user_data for now: "page_search_{page_num-1}"
        pagination_row.append(InlineKeyboardButton(strings.BTN_PREVIOUS_PAGE, callback_data=f"page_search_{current_page - 1}"))

    if current_page < total_pages:
        pagination_row.append(InlineKeyboardButton(strings.BTN_NEXT_PAGE, callback_data=f"page_search_{current_page + 1}"))
    
    if pagination_row:
        keyboard.append(pagination_row)

    # Option to search again or cancel
    keyboard.append([
        InlineKeyboardButton("🔎 Search Again", callback_data="search_ask_again"),
        InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="search_cancel")
    ])
    return InlineKeyboardMarkup(keyboard)

async def display_search_results_page(update: Update, context: ContextTypes.DEFAULT_TYPE, results_docs: list, total_count: int, query_str: str, current_page: int):
    """Displays a single page of search results."""
    user = update.effective_user
    
    # Store result IDs for stateless pagination via callback_handler.py, if desired
    # context.user_data['last_search_results_ids_for_pagination'] = [str(doc['_id']) for doc in results_docs_on_this_page_only]
    # This method is actually harder because then `callback_handler.py` pagination needs to fetch these details again.
    # The current `page_search_{page_num}` in callback_handler re-runs the search with new page_num and `last_search_query_for_pagination`.
    # Let's keep `last_search_query_for_pagination` for use in callback_handler.

    if not results_docs and current_page == 1:
        no_results_text = strings.SEARCH_NO_RESULTS.format(query=query_str)
        # Offer to request this anime
        # Callback "reqanime_THE_ANIME_TITLE" will be handled by main_callback_handler
        request_button_callback = f"reqanime_{quote_plus(query_str)}" # Ensure title is URL-safe for callback
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{strings.EMOJI_REQUEST} Request '{query_str[:30]}…'?", callback_data=request_button_callback)],
            [InlineKeyboardButton("Try Another Search", callback_data="search_ask_again")],
            [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="search_cancel")]
        ])
        
        # Determine how to reply (edit or send new)
        target_message = update.callback_query.message if update.callback_query else update.message
        if target_message:
            try:
                if update.callback_query: # From pagination or "search again"
                    await update.callback_query.edit_message_text(text=no_results_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                else: # From initial search query
                    await target_message.reply_html(text=no_results_text, reply_markup=keyboard)
            except Exception as e: # Catch "message is not modified"
                logger.debug(f"Error sending/editing 'no results' message: {e}")
                if update.callback_query: await update.callback_query.answer()
        return

    total_pages = (total_count + settings.RESULTS_PER_PAGE_GENERAL - 1) // settings.RESULTS_PER_PAGE_GENERAL
    results_text = strings.SEARCH_RESULTS_HEADER.format(query=query_str, current_page=current_page, total_pages=total_pages)
    
    # Removed list of animes from text, they will be in buttons
    # for anime in results_docs:
    #     results_text += f"\n🎬 <b>{anime['title_english']}</b> ({anime.get('release_year', 'N/A')})"

    keyboard = build_search_results_keyboard(results_docs, query_str, current_page, total_pages, total_count)
    
    # Determine how to reply
    target_message = update.callback_query.message if update.callback_query else update.message # from pagination vs direct search
    if target_message:
        try:
            if update.callback_query: # Editing for pagination or "search again"
                 await update.callback_query.edit_message_text(text=results_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            else: # Replying for initial search
                 await target_message.reply_html(text=results_text, reply_markup=keyboard)
        except Exception as e: # Catch "message is not modified"
            logger.debug(f"Error sending/editing search results: {e}")
            if update.callback_query: await update.callback_query.answer()


async def selected_anime_from_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles when a user selects an anime from the search results."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    anime_id_str = query.data.split("search_select_", 1)[1]
    logger.info(f"User {user.id} selected anime ID {anime_id_str} from search.")

    anime_doc = await anidb.get_anime_by_id_str(anime_id_str)
    if not anime_doc:
        await query.edit_message_text(f"{strings.EMOJI_ERROR} Sorry, could not retrieve details for that anime. It might have been removed.",
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        return ConversationHandler.END # End search conversation

    # Transition to displaying anime seasons/details
    # This function is from anime_browser.py, re-used here
    # It expects an `update` (can pass the query directly), context, and anime_doc
    await display_anime_seasons(update, context, anime_doc) # display_anime_seasons will edit the message

    # After selecting an anime, the search specific conversation might end,
    # and season/episode browsing becomes a new flow (or uses generic callbacks)
    return ConversationHandler.END # Or a different state if search leads into a more complex flow


async def search_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the search conversation."""
    query = update.callback_query
    if query:
        await query.answer()
        # Message edit is handled by reply_with_main_menu now
    
    # Clean up any search-specific user_data
    context.user_data.pop('last_search_query_for_pagination', None)
    context.user_data.pop('last_search_results_ids_for_pagination', None)

    await reply_with_main_menu(update, context, message_text=strings.OPERATION_CANCELLED + " Search cancelled.")
    return ConversationHandler.END


# --- Conversation Handler for Search ---
def get_search_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("search", search_anime_command_entry), # Allows /search [query] or just /search
            CallbackQueryHandler(search_anime_command_entry, pattern="^core_search$"), # From main menu
            CallbackQueryHandler(ask_search_query_again, pattern="^search_ask_again$") # From results to search again
        ],
        states={
            ASK_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_search_query)],
            DISPLAY_SEARCH_RESULTS: [ # This state is mainly to catch callbacks for selection/pagination
                CallbackQueryHandler(selected_anime_from_search, pattern="^search_select_"),
                # Pagination is handled by the main_callback_handler pattern="^page_search_"
            ]
            # No explicit state for pagination buttons if handled by generic callback_handler and re-triggering execute_search_and_display
        },
        fallbacks=[
            CallbackQueryHandler(search_cancel, pattern="^search_cancel$"),
            CommandHandler("cancel", search_cancel) # General cancel within this conversation
        ],
        map_to_parent={ # If search is part of a larger conversation flow (not in this case)
            ConversationHandler.END: ConversationHandler.END # Or the state to return to
        },
        # You might want to use `per_user=True, per_chat=True` for ConversationHandler if states collide
    )
