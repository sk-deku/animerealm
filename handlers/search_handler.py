from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
import config
import strings
from pyrogram.errors import MessageNotModified
from utils.keyboard_utils import paginate_keyboard
from database.operations import search_animes_db
from utils.logger import log_bot_event
from utils.logger import log_bot_event, LOGGER

SEARCH_STATE = {} # user_id: "awaiting_query"

@Client.on_message(filters.command("search"))
@Client.on_callback_query(filters.regex(r"^search_anime_prompt$"))
async def search_anime_prompt_handler(client: Client, message_or_cb: Message | CallbackQuery):
    is_cb = isinstance(message_or_cb, CallbackQuery)
    user_id = message_or_cb.from_user.id
    
    SEARCH_STATE[user_id] = {"awaiting_query": True} # Set state
    
    if is_cb:
        try:
            await message_or_cb.message.edit_text(strings.SEARCH_PROMPT)
        except MessageNotModified:
            pass
        except Exception as e:
            LOGGER.error(f"Error editing for search_anime_prompt: {e}")
            # Fallback if edit fails
            await message_or_cb.message.reply_text(strings.SEARCH_PROMPT)
        await message_or_cb.answer()
    else:
        await message_or_cb.reply_text(strings.SEARCH_PROMPT)


@Client.on_message(filters.private & filters.text)
async def search_anime_query_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_state = SEARCH_STATE.get(user_id)

    if not user_state or not user_state.get("awaiting_query"):
        from pyrogram import ContinuePropagation
        raise ContinuePropagation 
    
    query = message.text.strip()
    if not query or len(query) < 2:
        await message.reply_text("Search query too short. Please enter at least 2 characters.")
        return 
    
    SEARCH_STATE[user_id]["awaiting_query"] = False # Clear this flag
    SEARCH_STATE[user_id]["last_query"] = query # Store the query for pagination
    await log_bot_event(client, f"User {user_id} searched for: '{query}'")

    await process_search_results(client, message, query, 1)


async def process_search_results(client: Client, original_message_or_cb: Message | CallbackQuery, query: str, page: int):
    animes, total_animes = await search_animes_db(query, page, config.ITEMS_PER_PAGE)

    # Determine if the original context was a CallbackQuery or a Message
    is_callback_context = isinstance(original_message_or_cb, CallbackQuery)
    message_to_interact_with = original_message_or_cb.message if is_callback_context else original_message_or_cb

    no_results_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Try Another Search", callback_data="search_anime_prompt")],
        [InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]
    ])

    if not animes and page == 1:
        no_results_text = strings.SEARCH_NO_RESULTS.format(query=query)
        if is_callback_context:
            try:
                await message_to_interact_with.edit_text(no_results_text, reply_markup=no_results_markup)
            except MessageNotModified: pass
            except Exception as e: LOGGER.error(f"Search no results edit error: {e}")
        else:
            await message_to_interact_with.reply_text(no_results_text, reply_markup=no_results_markup)
        if is_callback_context: await original_message_or_cb.answer() # Answer CB even on no results
        return

    items_data = []
    for anime in animes:
        items_data.append({
            'text': anime.get('title', 'Unknown Anime'),
            'callback_data': f"view_anime:{str(anime['_id'])}"
        })
    
    # For pagination callback, we need to reconstruct the query.
    # Storing it in SEARCH_STATE[user_id]["last_query"] is better.
    # The callback prefix can then be simpler: "search_res_page_"
    # The handler for "search_res_page_" will fetch the query from SEARCH_STATE.
    base_cb_prefix_for_pagination = f"search_res_p" # Simpler prefix, handler will get query from state

    kb = paginate_keyboard(
        items_data, page, config.ITEMS_PER_PAGE, total_animes, base_cb_prefix_for_pagination,
        extra_buttons_bottom=[
            [InlineKeyboardButton("🔍 New Search", callback_data="search_anime_prompt")],
            [InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]
        ],
        items_per_row=1
    )
    
    search_text_results = strings.SEARCH_RESULTS_TEXT.format(query=query) + f" (Page {page})"

    if is_callback_context:
        try:
            await message_to_interact_with.edit_text(search_text_results, reply_markup=kb, parse_mode=ParseMode.HTML)
        except MessageNotModified:
            pass 
        except Exception as e:
            LOGGER.error(f"Error editing search results (CB context): {e}")
            # Fallback: reply if edit fails badly
            await message_to_interact_with.reply_text(search_text_results, reply_markup=kb, parse_mode=ParseMode.HTML)
        await original_message_or_cb.answer() # Answer the callback query
    else: # It's an incoming Message
        await message_to_interact_with.reply_text(search_text_results, reply_markup=kb, parse_mode=ParseMode.HTML)


# Callback for search result pagination
@Client.on_callback_query(filters.regex(r"^search_res_p_(\d+)$")) # Matches "search_res_p_PAGENUMBER"
async def search_results_pagination_handler(client: Client, cb: CallbackQuery):
    page = int(cb.matches[0].group(1))
    user_id = cb.from_user.id
    
    user_state = SEARCH_STATE.get(user_id)
    if not user_state or not user_state.get("last_query"):
        await cb.answer("Search session expired or query not found. Please start a new search.", show_alert=True)
        try: # Try to edit message to guide user
            await cb.message.edit_text("Search session expired. Please use /search again.", 
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 New Search", callback_data="search_anime_prompt")]]))
        except: pass
        return

    query = user_state["last_query"]
    
    await cb.answer(f"Loading page {page} for: '{query[:30]}...'") # Show part of query in answer
    await process_search_results(client, cb, query, page) # Pass cb directly
