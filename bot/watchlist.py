# bot/watchlist.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from math import ceil

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance
from .core_handlers import check_user_or_add, reply_with_main_menu # For main menu button
from .anime_browser import display_anime_details_and_buttons # To view anime from watchlist

logger = logging.getLogger(__name__)

# --- View Watchlist Command ---
async def view_watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE, page_to_display: int = 1) -> None:
    """Displays the user's watchlist, paginated."""
    user = update.effective_user
    query = update.callback_query # Could be from a button or direct command

    logger.info(f"View watchlist for user {user.id} ({user.first_name}), page: {page_to_display}")

    if query:
        await query.answer()

    user_db_doc = await check_user_or_add(update, context)
    if not user_db_doc:
        return

    # Fetch watchlist anime IDs and then their details (this is in mongo_db.py now)
    # The `get_watchlist_animes_details` should handle fetching the anime documents
    # and total count of items in the watchlist for pagination.
    # We pass the page and RESULTS_PER_PAGE_GENERAL to it.

    # get_watchlist_animes_details(self, user_id: int, page: int = 1, per_page: int = 5):
    watchlist_anime_docs, total_watchlist_items = await anidb.get_watchlist_animes_details(
        user_id=user.id,
        page=page_to_display,
        per_page=settings.RESULTS_PER_PAGE_GENERAL
    )

    if not watchlist_anime_docs and page_to_display == 1:
        text = strings.WATCHLIST_EMPTY
        keyboard = [[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]
        if query:
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_html(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    total_pages = ceil(total_watchlist_items / settings.RESULTS_PER_PAGE_GENERAL)
    header_text = strings.WATCHLIST_HEADER.format(current_page=page_to_display, total_pages=total_pages)

    buttons = []
    for anime in watchlist_anime_docs:
        anime_id_str = str(anime['_id'])
        title = anime.get("title_english", "N/A")[:50]
        if len(anime.get("title_english", "")) > 50: title += "..."
        # Callback to view details: "viewanime_{anime_id}" (handled by anime_browser via main_callback_handler)
        # Callback to remove directly from this list: "wl_rem_list_{anime_id}"
        row = [
            InlineKeyboardButton(f"{strings.EMOJI_TV if anime.get('type') != 'Movie' else strings.EMOJI_MOVIE} {title}", callback_data=f"viewanime_{anime_id_str}"),
            InlineKeyboardButton(f"{strings.EMOJI_DELETE}", callback_data=f"wl_rem_list_{anime_id_str}") # Remove button
        ]
        buttons.append(row)

    pagination_row = []
    if page_to_display > 1:
        pagination_row.append(InlineKeyboardButton(strings.BTN_PREVIOUS_PAGE, callback_data=f"page_watchlist_{page_to_display - 1}"))
    if page_to_display < total_pages:
        pagination_row.append(InlineKeyboardButton(strings.BTN_NEXT_PAGE, callback_data=f"page_watchlist_{page_to_display + 1}"))

    if pagination_row:
        buttons.append(pagination_row)

    buttons.append([InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")])
    reply_markup = InlineKeyboardMarkup(buttons)

    # Editing the message
    target_message = query.message if query else update.message
    try:
        if query:
            await query.edit_message_text(text=header_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            await target_message.reply_html(text=header_text, reply_markup=reply_markup)
    except Exception as e:
        logger.debug(f"Error editing/sending watchlist message: {e}")
        if query: await query.answer() # Still answer if edit fails


# --- Add/Remove Callbacks (from Anime Details page or Watchlist View) ---
async def add_to_watchlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_id_to_add: str) -> None:
    """Handles callback to add anime to watchlist."""
    query = update.callback_query
    user = update.effective_user

    user_db_doc = await check_user_or_add(update, context) # Also refreshes user_db_doc
    if not user_db_doc:
        await query.answer("Error processing request.", show_alert=True)
        return

    # Check watchlist limits
    is_premium = user_db_doc.get("premium_status", False)
    current_watchlist_size = len(user_db_doc.get("watchlist", []))
    limit = settings.MAX_WATCHLIST_ITEMS_PREMIUM if is_premium else settings.MAX_WATCHLIST_ITEMS_FREE

    if current_watchlist_size >= limit:
        limit_msg = strings.WATCHLIST_FULL_PREMIUM.format(limit=limit) if is_premium else strings.WATCHLIST_FULL_FREE.format(limit=limit)
        await query.answer(limit_msg, show_alert=True)
        # Optionally, could refresh the anime details page without changing the button
        return


    anime_doc = await anidb.get_anime_by_id_str(anime_id_to_add)
    if not anime_doc:
        await query.answer("Anime not found.", show_alert=True)
        return

    success = await anidb.add_to_watchlist(user.id, anime_id_to_add)
    if success:
        await query.answer(strings.ADDED_TO_WATCHLIST.format(anime_title=anime_doc.get("title_english", "This anime")), show_alert=False)
        # Refresh the anime details page to show "Remove from Watchlist"
        # We need the full anime_doc to call display_anime_details_and_buttons
        await display_anime_details_and_buttons(update, context, anime_doc)
    else:
        # Check if already in watchlist, if so, anidb.add_to_watchlist might return False (if $addToSet used and it didn't modify)
        # We can re-fetch user_db_doc to be sure, or rely on success flag meaning "it wasn't there and now it is"
        refreshed_user_doc = await anidb.get_user(user.id)
        if anime_id_to_add in refreshed_user_doc.get("watchlist", []):
            await query.answer(strings.ALREADY_IN_WATCHLIST.format(anime_title=anime_doc.get("title_english", "This anime")), show_alert=True)
            # No need to refresh page if already there and button reflects it. But if add was clicked, button should change.
            # Assuming if $addToSet returns 0 modified, it means it's already there.
            await display_anime_details_and_buttons(update, context, anime_doc) # Refresh to ensure button is correct
        else:
            await query.answer("Failed to add to watchlist.", show_alert=True)


async def remove_from_watchlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_id_to_remove: str, from_list_view: bool = False) -> None:
    """Handles callback to remove anime from watchlist."""
    query = update.callback_query
    user = update.effective_user

    await check_user_or_add(update, context) # Ensure user is known

    anime_doc = await anidb.get_anime_by_id_str(anime_id_to_remove) # For title in message
    anime_title_for_msg = anime_doc.get("title_english", "This anime") if anime_doc else "Selected anime"

    success = await anidb.remove_from_watchlist(user.id, anime_id_to_remove)
    if success:
        await query.answer(strings.REMOVED_FROM_WATCHLIST.format(anime_title=anime_title_for_msg), show_alert=False)
        if from_list_view:
            # Refresh the watchlist view
            await view_watchlist_command(update, context, page_to_display=context.user_data.get('current_watchlist_page', 1))
        elif anime_doc : # From anime details page, refresh it
            await display_anime_details_and_buttons(update, context, anime_doc)
        else: # Fallback if anime_doc wasn't found but removal was successful (e.g. anime deleted from main DB)
             await query.edit_message_text(text=strings.REMOVED_FROM_WATCHLIST.format(anime_title=anime_title_for_msg) + "\nAnime details no longer available.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
    else:
        await query.answer(strings.NOT_IN_WATCHLIST.format(anime_title=anime_title_for_msg), show_alert=True)
        # If called from anime details page and it wasn't in watchlist, the button should already be "Add".
        # So, no need to refresh unless button was wrong.
        if anime_doc and not from_list_view:
             await display_anime_details_and_buttons(update, context, anime_doc) # Refresh to ensure correct button state


# This is called by main_callback_handler.py if callback_data is "wl_rem_list_{anime_id}"
async def remove_from_watchlist_list_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_id_to_remove: str) -> None:
    # Store current page for refresh
    # Assuming page info is available in a more robust way for callbacks than user_data sometimes
    # For now, this is a simplified example
    # Typically, the calling message's keyboard for pagination already embeds the current page
    # Here, we assume remove_from_watchlist_callback can handle the refresh correctly
    await remove_from_watchlist_callback(update, context, anime_id_to_remove, from_list_view=True)
