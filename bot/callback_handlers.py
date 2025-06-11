# bot/callback_handlers.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from . import watchlist # Add import
from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance

from . import anime_browser # Import the module
# Import functions from other modules that will handle specific actions
from .core_handlers import reply_with_main_menu, help_command # Re-show main menu or help
from .user_cmds import profile_command, premium_info_command # Show profile or premium info
from .anime_search import search_anime_command_entry # Initiate search
from .anime_browser import browse_start_command, popular_anime_command, latest_anime_command
from .watchlist import view_watchlist_command
from .token_system import get_tokens_info_command # Show how to get tokens
from .admin_cmds import admin_panel_main # If you have a main admin panel triggered by callback

logger = logging.getLogger(__name__)

# --- Main Callback Router ---
async def main_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all generic inline button callback queries."""
    query = update.callback_query
    await query.answer() # Always answer the callback query as soon as possible

    user = update.effective_user
    callback_data = query.data

    logger.info(f"Callback received from {user.id} ({user.first_name}): {callback_data}")

    # --- Core Navigation Callbacks ---
    if callback_data == "core_main_menu":
        await reply_with_main_menu(update, context)
        return
    elif callback_data == "core_help":
        await help_command(update, context) # This will edit the message
        return
    elif callback_data == "core_search":
        # This might start a conversation or prompt for search query
        await query.message.reply_text(strings.SEARCH_PROMPT) # Or edit current message
        # For a conversation based search, this might set a state
        # For now, let's assume it just prompts for text input.
        # The search_conv_handler in main.py will pick up the text message.
        # Or, we can directly invoke the entry point of the search conversation here.
        from .anime_search import SEARCH_INITIATE # Import a constant if search is a conv.
        # This example just edits the message to prompt search
        # await query.edit_message_text(text=strings.SEARCH_PROMPT, reply_markup=None) # Example: clear buttons
        # If search is a command:
        # await context.bot.send_message(user.id, "Please use the /search command followed by your query.")
        # If search is a ConversationHandler, and this callback is meant to START it:
        await query.edit_message_text(text=strings.SEARCH_PROMPT, parse_mode=ParseMode.HTML)
        # We might need a dummy return state for ConversationHandler to start listening
        # For now, relying on the user to send text after this prompt.
        return # Search is usually more complex, often a Conversation.
    elif callback_data == "core_browse":
        await browse_start_command(update, context) # This function will handle message editing
        return
    elif callback_data == "core_popular":
        await popular_anime_command(update, context)
        return
    elif callback_data == "core_latest":
        await latest_anime_command(update, context)
        return
    elif callback_data == "core_my_watchlist":
        await view_watchlist_command(update, context)
        return
    elif callback_data == "core_profile":
        await profile_command(update, context)
        return
    elif callback_data == "core_get_tokens_info":
        await get_tokens_info_command(update, context)
        return
    elif callback_data == "core_premium_info":
        await premium_info_command(update, context)
        return

    # --- Admin Panel Navigation (Example) ---
    if callback_data == "admin_panel_main":
        if user.id in settings.ADMIN_IDS:
            await admin_panel_main(update, context) # This function needs to exist in admin_cmds.py
            return
        else:
            await query.answer("Access Denied!", show_alert=True)
            return

    # --- Pagination Callbacks (Generic Example) ---
    # Expected format: "paginate_{module_or_action}_{page_num}"
    # Example: "paginate_watchlist_2", "paginate_search_results_anime_title_3"
    # Or more specific: "watchlist_page_2", "search_page_3_queryXYZ"
    # This section needs to be robustly designed based on how you structure pagination callback_data
    if callback_data.startswith("page_"): # A generic pagination prefix
        parts = callback_data.split("_")
        try:
            action_type = parts[1] # e.g., 'watchlist', 'search', 'browse_genre'
            page_num = int(parts[-1]) # Last part is page number

            # Store extra info if needed in callback data, e.g. "search_page_THEQUERY_2"
            # For this simple example, we assume context.user_data or chat_data might hold the current query/list state
            # A better way is to pass necessary context in the callback_data itself.
            # Example "searchpage_3_Dragon Ball" where Dragon Ball is URL-encoded or base64
            # "browse_genre_Action_2"

            logger.info(f"Pagination: action={action_type}, page={page_num}, for user {user.id}")

            # You'll need specific handlers for each type of pagination
            if action_type == "watchlist":
                await view_watchlist_command(update, context, page_to_display=page_num)
            elif action_type == "popular":
                await popular_anime_command(update, context, page_to_display=page_num)
            elif action_type == "latest":
                await latest_anime_command(update, context, page_to_display=page_num)
            elif action_type.startswith("browse"): # e.g., "browse_genre_Action_2" or "browse_status_Ongoing_2"
                browse_sub_type = parts[2] # genre or status
                browse_value = parts[3] # Action or Ongoing
                if browse_sub_type == "genre":
                    await anime_browser.browse_by_genre_results(update, context, selected_genre=browse_value, page_to_display=page_num)
                elif browse_sub_type == "status":
                    await anime_browser.browse_by_status_results(update, context, selected_status=browse_value, page_to_display=page_num)
            elif action_type == "search":
                # Search pagination is complex because the query needs to be persisted or passed
                # This part is highly dependent on how search results are handled.
                # Let's assume search_results in anime_search.py can handle a page_to_display param
                # and retrieves the query from context.user_data or callback data
                # e.g., "search_page_{URLENCODED_QUERY}_2"
                query_str = "_".join(parts[2:-1]) # Reconstruct query if it was part of callback_data
                from .anime_search import display_search_results_page # Requires this function
                # This requires that search query or result IDs are stored somewhere (e.g., context.user_data['last_search_query'])
                # to re-fetch the correct page. A better method passes the query or result identifiers in the callback.
                last_search_query = context.user_data.get('last_search_query_for_pagination')
                last_search_results_ids = context.user_data.get('last_search_results_ids_for_pagination')

                if last_search_results_ids: # Paginate based on a list of IDs
                     await anime_search.display_search_results_page_from_ids(update, context,
                                                                             result_ids=last_search_results_ids,
                                                                             current_page=page_num,
                                                                             query_str=last_search_query or "Search Results")
                elif last_search_query: # Re-run search query for the specific page (less ideal)
                    await anime_search.execute_search_and_display(update, context,
                                                                  query_str=last_search_query,
                                                                  page_to_display=page_num)
                else:
                    await query.edit_message_text(text="Sorry, I lost the context for that search. Please try searching again.", reply_markup=None)

            # Add more pagination handlers here based on your callback_data structure
            # e.g., if callback_data is "module_action_value1_value2_page_N"
            else:
                logger.warning(f"Unhandled pagination action_type: {action_type} from data: {callback_data}")
                await query.answer("Sorry, I couldn't process that page request.", show_alert=True)

        except (IndexError, ValueError) as e:
            logger.error(f"Error parsing pagination callback_data '{callback_data}': {e}")
            await query.answer("Error processing pagination.", show_alert=True)
        return

    # --- Request Anime Callbacks (from search 'no results' message) ---
    if callback_data.startswith("reqanime_"):
        anime_title_to_request = callback_data.split("reqanime_", 1)[1] # Extracts the title
        from .anime_requests import handle_request_anime_callback # Needs this function
        await handle_request_anime_callback(update, context, anime_title_to_request)
        return

    # --- Add other specific, non-conversational callback handlers here ---
    # For example, callbacks to add/remove from watchlist if they are simple actions
    # and not part of a larger conversation flow.

    # Example: Watchlist add/remove (if anime_id is in callback_data)
    # This is a very common pattern
    if callback_data.startswith("wl_add_"):
        anime_id_to_add = callback_data.split("wl_add_", 1)[1]
        await watchlist.add_to_watchlist_callback(update, context, anime_id_to_add)
        return
    elif callback_data.startswith("wl_rem_"):
        anime_id_to_remove = callback_data.split("wl_rem_", 1)[1]
        await watchlist.remove_from_watchlist_callback(update, context, anime_id_to_remove)
        return

    # --- Admin actions from request channel ---
    if callback_data.startswith("admin_req_"): # e.g., admin_req_fulfill_REQUESTDBID_USERID
        from .anime_requests import handle_admin_request_channel_action
        await handle_admin_request_channel_action(update, context)
        return


    # --- Download file callback ---
    # Expected format: "dl_{anime_id_str}_{season_num}_{episode_num}_{version_index}"
    # where version_index is the index of the file version in the episode's versions array
    if callback_data.startswith("dl_"):
        from .downloads import handle_download_callback
        await handle_download_callback(update, context)
        return

    logger.warning(f"Unhandled callback_data: {callback_data} from user {user.id}")
    # Default behavior for unhandled callbacks could be an alert or just ignore.
    # await query.answer("This button doesn't do anything yet or is part of a different flow.", show_alert=True) # Can be noisy

    elif callback_data.startswith("wl_add_"):
        anime_id_to_add = callback_data.split("wl_add_", 1)[1]
        await watchlist.add_to_watchlist_callback(update, context, anime_id_to_add) # Already had this
        return
    elif callback_data.startswith("wl_rem_list_"): # New one for direct removal from list
        anime_id_to_remove = callback_data.split("wl_rem_list_", 1)[1]
        await watchlist.remove_from_watchlist_list_view_callback(update, context, anime_id_to_remove)
        return
    elif callback_data.startswith("wl_rem_"): # Original remove, typically from anime details page
        anime_id_to_remove = callback_data.split("wl_rem_", 1)[1]
        # This will call remove_from_watchlist_callback with from_list_view=False (default)
        await watchlist.remove_from_watchlist_callback(update, context, anime_id_to_remove)
        return
    # For pagination of watchlist
    elif callback_data.startswith("page_watchlist_"):
        page_num = int(callback_data.split("_")[-1])
        await watchlist.view_watchlist_command(update, context, page_to_display=page_num)
        return

    elif callback_data.startswith("viewanime_"):
        anime_id = callback_data.split("viewanime_",1)[1]
        await anime_browser.display_anime_details_and_buttons(update, context, anime_id_str=anime_id)
        return
    elif callback_data.startswith("viewseasons_"):
        anime_id = callback_data.split("viewseasons_",1)[1]
        await anime_browser.display_anime_seasons(update, context, anime_id_str=anime_id)
        return
    elif callback_data.startswith("vieweps_"): # "vieweps_{anime_id}_{season_num}"
        _, anime_id, s_num_str = callback_data.split("_")
        await anime_browser.display_season_episodes(update, context, anime_id, int(s_num_str))
        return
    elif callback_data.startswith("viewvers_"): # "viewvers_{anime_id}_{s_num}_{ep_num}"
        _, anime_id, s_num_str, ep_num_str = callback_data.split("_")
        await anime_browser.display_episode_versions(update, context, anime_id, int(s_num_str), int(ep_num_str))
        return
    # For browse specific genre/status lists from browse_start_command menu
    elif callback_data == "browse_select_genre_init":
        await anime_browser.browse_select_genre_init(update, context)
        return
    elif callback_data.startswith("br_sel_genre_page_"): # Genre list pagination
        page = int(callback_data.split("_")[-1])
        await anime_browser.browse_select_genre_init(update, context, page=page)
        return
    elif callback_data.startswith("br_genre_"): # Selected a genre
        await anime_browser.browse_by_genre_results(update, context) # Will parse genre from callback_data
        return
    elif callback_data == "browse_select_status_init":
        await anime_browser.browse_select_status_init(update, context)
        return
    elif callback_data.startswith("br_status_"): # Selected a status
        await anime_browser.browse_by_status_results(update, context) # Will parse status from callback_data
        return
