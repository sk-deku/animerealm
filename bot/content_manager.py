# bot/content_manager.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from telegram.constants import ParseMode
from datetime import datetime
import pytz
from bson import ObjectId # For validating ObjectIds from callbacks

from configs import settings, strings
from database.mongo_db import db as anidb
from .core_handlers import reply_with_main_menu

logger = logging.getLogger(__name__)

# --- Conversation States for Content Management ---
# Main Menu / Selection
CM_MAIN_MENU, \
CM_MODIFY_ASK_SEARCH_TERM, CM_MODIFY_SHOW_SEARCH_RESULTS, CM_MODIFY_SELECTED_ANIME_MENU, \
CM_DELETE_ASK_SEARCH_TERM, CM_DELETE_SHOW_SEARCH_RESULTS, CM_DELETE_CONFIRM = range(7)

# Add New Anime Flow (continues from previous range)
CM_ADD_TITLE, CM_ADD_POSTER, CM_ADD_SYNOPSIS, \
CM_ADD_SELECT_GENRES, CM_ADD_SELECT_STATUS, CM_ADD_RELEASE_YEAR, \
CM_ADD_NUM_SEASONS = range(7, 14)

# Season & Episode Management (shared)
CM_MANAGE_SEASON_MENU, CM_EPISODE_NUMBER, \
CM_EPISODE_FILE_OR_DATE, CM_EPISODE_SEND_FILE, \
CM_EPISODE_SELECT_RESOLUTION, CM_EPISODE_SELECT_AUDIO, CM_EPISODE_SELECT_SUB, \
CM_EPISODE_SET_RELEASE_DATE = range(14, 22)

# Modify Existing Anime Core Details (continues from previous range)
CM_MODIFY_CORE_DETAILS_MENU, CM_MODIFY_FIELD_SELECT_TITLE, CM_MODIFY_FIELD_RECEIVE_NEW_TITLE, \
CM_MODIFY_FIELD_SELECT_SYNOPSIS, CM_MODIFY_FIELD_RECEIVE_NEW_SYNOPSIS, \
CM_MODIFY_FIELD_SELECT_POSTER, CM_MODIFY_FIELD_RECEIVE_NEW_POSTER, \
CM_MODIFY_FIELD_SELECT_GENRES, CM_MODIFY_FIELD_TOGGLE_GENRE, CM_MODIFY_FIELD_GENRES_DONE, \
CM_MODIFY_FIELD_SELECT_STATUS, \
CM_MODIFY_FIELD_SELECT_YEAR, CM_MODIFY_FIELD_RECEIVE_NEW_YEAR = range(22, 35)


# --- Helper: Build Genre Selection Keyboard ---
def build_genre_selection_keyboard(selected_genres: list = None, callback_prefix: str = "cm_genre_") -> InlineKeyboardMarkup:
    if selected_genres is None: selected_genres = []
    buttons = []
    row = []
    for genre_display_name in settings.AVAILABLE_GENRES:
        genre_key = genre_display_name.split(' ')[0] # Use first word as key
        text = f"{strings.EMOJI_SUCCESS} {genre_display_name}" if genre_display_name in selected_genres else genre_display_name
        row.append(InlineKeyboardButton(text, callback_data=f"{callback_prefix}{genre_key}"))
        if len(row) >= settings.GENRE_BUTTONS_PER_ROW:
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton(f"{strings.EMOJI_SUCCESS} Done Selecting Genres", callback_data=f"{callback_prefix}done")])
    buttons.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_modify_details_menu")]) # Contextual cancel
    return InlineKeyboardMarkup(buttons)

# --- Helper: Build Status Selection Keyboard ---
def build_status_selection_keyboard(callback_prefix: str = "cm_status_") -> InlineKeyboardMarkup:
    buttons = []
    for status_display_name in settings.AVAILABLE_STATUSES:
        status_key = status_display_name.split(' ')[0]
        buttons.append([InlineKeyboardButton(status_display_name, callback_data=f"{callback_prefix}{status_key}")])
    buttons.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_modify_details_menu")])
    return InlineKeyboardMarkup(buttons)


# --- Clear CM Context ---
def clear_cm_context(context: ContextTypes.DEFAULT_TYPE):
    keys_to_pop = [k for k in context.user_data.keys() if k.startswith('cm_')]
    for k in keys_to_pop: context.user_data.pop(k, None)
    logger.debug("Cleared cm_ context from user_data.")

# --- Entry Point & Main Menu ---
async def manage_content_start(update: Update, context: ContextTypes.DEFAULT_TYPE, called_from_cancel: bool = False) -> int:
    query = update.callback_query
    if query: await query.answer()

    if not called_from_cancel: # Don't clear if just coming back from cancel, state might be needed
        clear_cm_context(context)

    keyboard = [
        [InlineKeyboardButton(strings.BTN_CM_ADD_ANIME, callback_data="cm_start_add_new")],
        [InlineKeyboardButton(strings.BTN_CM_MODIFY_ANIME, callback_data="cm_start_modify_existing")],
        [InlineKeyboardButton(strings.BTN_CM_DELETE_ANIME, callback_data="cm_start_delete_anime")],
        [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="cm_end_conversation")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = strings.ADMIN_CONTENT_MAIN_MENU

    if query and not called_from_cancel : # Don't edit if called from a message command or if returning from cancel without specific message
         await query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif update.message: # From /manage_content command
        await update.message.reply_html(text=msg_text, reply_markup=reply_markup)
    elif query and called_from_cancel: # if called from cancel and it was a query, assume message needs update
        try: # Try to edit, might fail if context lost, then send new
             await query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except:
             await context.bot.send_message(update.effective_chat.id, text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    return CM_MAIN_MENU


# --- === ADD NEW ANIME FLOW (Largely same as before) === ---
async def cm_start_add_new_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    context.user_data['cm_flow'] = 'add' # Indicate current flow
    context.user_data['cm_anime_data'] = {}
    context.user_data['cm_selected_genres'] = []
    await query.edit_message_text(
        text=strings.CM_PROMPT_ANIME_TITLE_ENG,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_ADD_TITLE

async def cm_receive_anime_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title_eng = update.message.text.strip()
    if not title_eng:
        await update.message.reply_html("Title cannot be empty. Please try again.")
        return CM_ADD_TITLE

    existing_anime = await anidb.get_anime_by_title_exact(title_eng)
    if existing_anime:
        await update.message.reply_html(
            f"{strings.EMOJI_ERROR} An anime titled '<b>{title_eng}</b>' already exists (ID: <code>{existing_anime['_id']}</code>).\n"
            f"You can modify the existing one, or use a different title for a new entry.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{strings.EMOJI_EDIT} Modify This Anime", callback_data=f"cm_force_mod_existing_{existing_anime['_id']}")],
                [InlineKeyboardButton("🔄 Use Different Title", callback_data="cm_add_title_retry_cb")],
                [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]
            ])
        )
        return CM_ADD_TITLE # Or a specific state to handle choice

    context.user_data['cm_anime_data']['title_english'] = title_eng
    await update.message.reply_html(
        text=strings.CM_PROMPT_POSTER.format(anime_title=title_eng),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_ADD_POSTER

async def cm_add_title_retry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed
    query = update.callback_query; await query.answer()
    await query.edit_message_text(text=strings.CM_PROMPT_ANIME_TITLE_ENG,
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_ADD_TITLE


async def cm_receive_anime_poster(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Same as before)
    anime_title = context.user_data['cm_anime_data'].get('title_english', 'this anime')
    poster_file_id = None

    if update.message.photo:
        context.user_data['cm_anime_data']['poster_file_id'] = update.message.photo[-1].file_id
    elif update.message.text and update.message.text.strip().lower() == 'skip':
        context.user_data['cm_anime_data']['poster_file_id'] = settings.ANIME_POSTER_PLACEHOLDER_URL
    elif update.message.text and update.message.text.strip().startswith('http'):
        context.user_data['cm_anime_data']['poster_file_id'] = update.message.text.strip()
    else:
        await update.message.reply_html("Invalid input. Send image, URL, or 'skip'.")
        return CM_ADD_POSTER
    
    await update.message.reply_html(
        text=strings.CM_PROMPT_SYNOPSIS.format(anime_title=anime_title),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_ADD_SYNOPSIS

async def cm_receive_anime_synopsis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Same as before)
    synopsis = update.message.text.strip()
    context.user_data['cm_anime_data']['synopsis'] = "No synopsis." if synopsis.lower() == 'skip' else synopsis
    anime_title = context.user_data['cm_anime_data'].get('title_english', 'this anime')
    keyboard = build_genre_selection_keyboard(context.user_data.get('cm_selected_genres', []), callback_prefix="cm_add_genre_")
    await update.message.reply_html(text=strings.CM_PROMPT_SELECT_GENRES.format(anime_title=anime_title), reply_markup=keyboard)
    return CM_ADD_SELECT_GENRES

async def cm_add_toggle_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed for add flow
    query = update.callback_query; await query.answer()
    genre_key = query.data.split("cm_add_genre_", 1)[1]
    full_genre = next((g for g in settings.AVAILABLE_GENRES if g.startswith(genre_key)), None)
    if not full_genre: return CM_ADD_SELECT_GENRES
    
    selected_genres = context.user_data.get('cm_selected_genres', [])
    if full_genre in selected_genres: selected_genres.remove(full_genre)
    else: selected_genres.append(full_genre)
    context.user_data['cm_selected_genres'] = selected_genres
    await query.edit_message_reply_markup(reply_markup=build_genre_selection_keyboard(selected_genres, callback_prefix="cm_add_genre_"))
    return CM_ADD_SELECT_GENRES

async def cm_add_genre_selection_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed for add flow
    query = update.callback_query; await query.answer()
    selected_genres = context.user_data.get('cm_selected_genres', [])
    if not selected_genres:
        await query.answer("Please select at least one genre.", show_alert=True)
        return CM_ADD_SELECT_GENRES
    context.user_data['cm_anime_data']['genres'] = selected_genres
    anime_title = context.user_data['cm_anime_data'].get('title_english', 'this anime')
    await query.edit_message_text(
        text=strings.CM_PROMPT_SELECT_STATUS.format(anime_title=anime_title),
        reply_markup=build_status_selection_keyboard(callback_prefix="cm_add_status_")
    )
    return CM_ADD_SELECT_STATUS

async def cm_add_receive_anime_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed for add flow
    query = update.callback_query; await query.answer()
    status_key = query.data.split("cm_add_status_", 1)[1]
    full_status = next((s for s in settings.AVAILABLE_STATUSES if s.startswith(status_key)), None)
    if not full_status: return CM_ADD_SELECT_STATUS
    context.user_data['cm_anime_data']['status'] = full_status
    anime_title = context.user_data['cm_anime_data'].get('title_english', 'this anime')
    await query.edit_message_text(
        text=strings.CM_PROMPT_RELEASE_YEAR.format(anime_title=anime_title),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_ADD_RELEASE_YEAR

async def cm_receive_release_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Same as before, ensure correct state return based on flow)
    year_str = update.message.text.strip()
    try:
        year = int(year_str)
        if not (1900 < year < datetime.now().year + 10): raise ValueError("Year out of range.")
        context.user_data['cm_anime_data']['release_year'] = year
    except ValueError:
        await update.message.reply_html("Invalid year (e.g., 2023).")
        return CM_ADD_RELEASE_YEAR if context.user_data.get('cm_flow') == 'add' else CM_MODIFY_FIELD_RECEIVE_NEW_YEAR
    
    current_flow = context.user_data.get('cm_flow')
    if current_flow == 'add':
        anime_title = context.user_data['cm_anime_data'].get('title_english', 'this anime')
        await update.message.reply_html(
            text=strings.CM_PROMPT_NUM_SEASONS.format(anime_title=anime_title),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
        return CM_ADD_NUM_SEASONS
    elif current_flow == 'modify_year': # from modify flow
        anime_id = context.user_data.get('cm_current_anime_id')
        success = await anidb.update_anime_details(anime_id, {"release_year": year, "last_content_update": datetime.now(pytz.utc)})
        msg = f"{strings.EMOJI_SUCCESS} Release year updated to {year}." if success else f"{strings.EMOJI_ERROR} Failed to update year."
        await update.message.reply_html(msg)
        return await cm_show_modify_core_details_menu(update, context, called_internally=True) # Go back to modify menu


async def cm_receive_num_seasons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Same as ADD NEW ANIME flow before)
    num_seasons_str = update.message.text.strip(); num_seasons = 0
    try: num_seasons = int(num_seasons_str)
    except: pass
    if not (0 < num_seasons <= 50):
        await update.message.reply_html("Invalid number of seasons (1-50).")
        return CM_ADD_NUM_SEASONS

    anime_data = context.user_data['cm_anime_data']
    anime_data['seasons'] = [{"season_number": i, "episodes": []} for i in range(1, num_seasons + 1)]
    anime_data['type'] = "TV" if num_seasons > 0 and anime_data.get("status", "").startswith("Ongoing") or anime_data.get("status", "").startswith("Completed") else anime_data.get("status", "Movie").split(" ")[0]

    anime_data["last_content_update"] = datetime.now(pytz.utc)
    inserted_id = await anidb.add_anime(anime_data)

    if not inserted_id:
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Failed to save anime data.")
        return await cm_cancel_operation(update, context, "cm_cancel_op_back_to_cm_main")

    context.user_data['cm_current_anime_id'] = str(inserted_id)
    context.user_data['cm_current_season_num'] = 1
    context.user_data['cm_flow'] = 'manage_episodes' # For episode management flow

    await update.message.reply_html(
        strings.CM_ANIME_ADDED_SUCCESS.format(anime_title=anime_data['title_english']) + "\n" +
        strings.CM_NOW_MANAGE_SEASONS_EPISODES.format(anime_title=anime_data['title_english']),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(strings.BTN_CM_MANAGE_SEASONS_EPISODES, callback_data="cm_goto_season_episode_mgmt")],
            [InlineKeyboardButton(f"{strings.EMOJI_SUCCESS} Finish & Exit CM", callback_data="cm_end_conversation")]
        ]))
    return CM_MANAGE_SEASON_MENU

# --- === MODIFY EXISTING ANIME FLOW === ---

async def cm_start_modify_existing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    context.user_data['cm_flow'] = 'modify' # Indicate current flow
    await query.edit_message_text(text=strings.CM_SELECT_ANIME_TO_MODIFY,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_MODIFY_ASK_SEARCH_TERM

async def cm_receive_modify_search_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query_str = update.message.text.strip()
    if not query_str or len(query_str) < 2:
        await update.message.reply_html("Please enter a longer search term.")
        return CM_MODIFY_ASK_SEARCH_TERM
    
    context.user_data['cm_modify_search_query'] = query_str
    
    searching_msg = await update.message.reply_html(f"{strings.EMOJI_LOADING} Searching for '<code>{query_str}</code>' to modify...")
    results_docs, total_count = await anidb.search_anime_by_title(
        query=query_str, page=1, per_page=settings.RESULTS_PER_PAGE_GENERAL # Show first page
    )
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=searching_msg.message_id)

    if not results_docs:
        await update.message.reply_html(
            strings.CM_NO_ANIME_FOUND_FOR_MODIFY.format(query=query_str),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Try Different Search", callback_data="cm_mod_search_again_cb")],
                [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]
            ]))
        return CM_MODIFY_SHOW_SEARCH_RESULTS # Or back to ask term
    
    context.user_data['cm_modify_current_page'] = 1
    # Build keyboard for results
    buttons = []
    for anime in results_docs:
        buttons.append([InlineKeyboardButton(anime['title_english'][:60], callback_data=f"cm_mod_select_{anime['_id']}")])
    # Add pagination if total_count > per_page (omitted for brevity here, similar to search pagination)
    buttons.append([InlineKeyboardButton("🔄 Search Again", callback_data="cm_mod_search_again_cb")])
    buttons.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")])
    
    await update.message.reply_html(
        f"Search results for '<code>{query_str}</code>'. Select an anime to modify:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CM_MODIFY_SHOW_SEARCH_RESULTS

async def cm_mod_search_again_cb(update:Update, context:ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    await query.edit_message_text(text=strings.CM_SELECT_ANIME_TO_MODIFY,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_MODIFY_ASK_SEARCH_TERM


async def cm_selected_anime_for_modification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    anime_id_str = query.data.split("cm_mod_select_", 1)[1]
    
    if not ObjectId.is_valid(anime_id_str):
        await query.edit_message_text("Invalid anime ID selected. Please try searching again.",
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Search Again", callback_data="cm_mod_search_again_cb")]]))
        return CM_MODIFY_SHOW_SEARCH_RESULTS

    anime_doc = await anidb.get_anime_by_id_str(anime_id_str)
    if not anime_doc:
        await query.edit_message_text(f"{strings.EMOJI_ERROR} Anime not found. It might have been deleted.",
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Search Again", callback_data="cm_mod_search_again_cb")]]))
        return CM_MODIFY_SHOW_SEARCH_RESULTS

    context.user_data['cm_current_anime_id'] = anime_id_str
    context.user_data['cm_anime_data'] = anime_doc # Load existing data
    context.user_data['cm_selected_genres'] = anime_doc.get('genres', []) # Load existing genres

    msg_text = f"Selected for modification: <b>{anime_doc['title_english']}</b>\nWhat would you like to do?"
    keyboard = [
        [InlineKeyboardButton(f"{strings.EMOJI_EDIT} Modify Core Details", callback_data="cm_mod_core_details_menu")],
        [InlineKeyboardButton(f"🎬 Manage Seasons/Episodes", callback_data="cm_mod_manage_episodes_menu")],
        [InlineKeyboardButton("⬅️ Back to Search Results", callback_data="cm_mod_back_to_search_results_cb")], # Needs to reshow search list
        [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]
    ]
    await query.edit_message_text(text=msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CM_MODIFY_SELECTED_ANIME_MENU

async def cm_mod_back_to_search_results_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # This should ideally re-trigger cm_receive_modify_search_term with the stored query and page
    query = update.callback_query; await query.answer()
    query_str = context.user_data.get('cm_modify_search_query', "previous search")
    current_page = context.user_data.get('cm_modify_current_page', 1)

    # Simplified: go back to asking search term
    await query.edit_message_text(text=strings.CM_SELECT_ANIME_TO_MODIFY,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_MODIFY_ASK_SEARCH_TERM

async def cm_mod_core_details_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed
    return await cm_show_modify_core_details_menu(update, context)

async def cm_show_modify_core_details_menu(update:Update, context:ContextTypes.DEFAULT_TYPE, called_internally:bool=False) -> int:
    # (Shows menu: Edit Title, Synopsis, Poster, Genres, Status, Year)
    # Each button will lead to a new state e.g. CM_MODIFY_FIELD_SELECT_TITLE
    query = update.callback_query
    if query and not called_internally: await query.answer()

    anime_title = context.user_data.get('cm_anime_data', {}).get('title_english', 'Selected Anime')
    text = f"Modifying core details for: <b>{anime_title}</b>\nSelect field to edit:"
    keyboard = [
        [InlineKeyboardButton("📝 Title", callback_data="cm_mod_field_title")],
        [InlineKeyboardButton("📜 Synopsis", callback_data="cm_mod_field_synopsis")],
        [InlineKeyboardButton("🖼️ Poster", callback_data="cm_mod_field_poster")],
        [InlineKeyboardButton("📚 Genres", callback_data="cm_mod_field_genres")],
        [InlineKeyboardButton(f"{strings.EMOJI_TV} Status", callback_data="cm_mod_field_status")],
        [InlineKeyboardButton("🗓️ Release Year", callback_data="cm_mod_field_year")],
        [InlineKeyboardButton("⬅️ Back to Anime Mod Menu", callback_data="cm_mod_back_to_anime_menu_cb")],
        [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query and not called_internally:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif update.message or called_internally: # If from a message (e.g. after text input) or internal call
         # If called_internally might be from query, need to use query.message.reply or query.edit_message_text
         if update.callback_query and called_internally: # E.g. came back here from editing year
             await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
         else: # From normal message reply or new message after some edit action.
             await context.bot.send_message(update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
             if update.message: await update.message.delete() # clean up admin's command message
    
    return CM_MODIFY_CORE_DETAILS_MENU

async def cm_mod_back_to_anime_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # This should essentially recall cm_selected_anime_for_modification with current context
    query = update.callback_query; await query.answer()
    # Re-show the menu for the currently selected anime
    anime_title = context.user_data.get('cm_anime_data', {}).get('title_english', 'Selected Anime')
    msg_text = f"Selected for modification: <b>{anime_title}</b>\nWhat would you like to do?"
    keyboard = [
        [InlineKeyboardButton(f"{strings.EMOJI_EDIT} Modify Core Details", callback_data="cm_mod_core_details_menu")],
        [InlineKeyboardButton(f"🎬 Manage Seasons/Episodes", callback_data="cm_mod_manage_episodes_menu")],
        [InlineKeyboardButton("⬅️ Back to Search Results", callback_data="cm_mod_back_to_search_results_cb")],
        [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]
    ]
    await query.edit_message_text(text=msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CM_MODIFY_SELECTED_ANIME_MENU


# Placeholder handlers for each field modification
async def cm_mod_field_ask_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE, field_name: str, prompt_text: str, next_state: int) -> int:
    query = update.callback_query; await query.answer()
    context.user_data['cm_mod_current_field'] = field_name
    await query.edit_message_text(
        text=prompt_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_modify_details_menu")]])
    )
    return next_state

async def cm_mod_field_title_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await cm_mod_field_ask_new_value(update, context, "title_english", "Enter new English Title:", CM_MODIFY_FIELD_RECEIVE_NEW_TITLE)

async def cm_mod_field_synopsis_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await cm_mod_field_ask_new_value(update, context, "synopsis", "Enter new Synopsis (or 'skip'):", CM_MODIFY_FIELD_RECEIVE_NEW_SYNOPSIS)

async def cm_mod_field_poster_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await cm_mod_field_ask_new_value(update, context, "poster_file_id", "Send new Poster image, URL, or 'skip':", CM_MODIFY_FIELD_RECEIVE_NEW_POSTER)

async def cm_mod_field_year_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cm_flow'] = 'modify_year' # To direct cm_receive_release_year correctly
    return await cm_mod_field_ask_new_value(update, context, "release_year", "Enter new Release Year (YYYY):", CM_MODIFY_FIELD_RECEIVE_NEW_YEAR) # Reuses a receiver from add


async def cm_mod_receive_new_text_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # For title, synopsis, year
    new_value = update.message.text.strip()
    field_to_update = context.user_data.pop('cm_mod_current_field', None)
    anime_id = context.user_data.get('cm_current_anime_id')

    if not all([field_to_update, anime_id]): # Should not happen
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Error: Context lost. Please restart.")
        return await cm_cancel_operation(update, context, "cm_cancel_op_back_to_cm_main")

    if field_to_update == 'synopsis' and new_value.lower() == 'skip': new_value = "No synopsis available."
    elif field_to_update == 'title_english' and not new_value : # Title cannot be empty
        await update.message.reply_html("Title cannot be empty. Please try again or cancel.")
        context.user_data['cm_mod_current_field'] = field_to_update # Put it back for retry
        return update.message.text.strip() # What state to return to? This needs rethinking or one state per field input.

    success = await anidb.update_anime_details(anime_id, {field_to_update: new_value, "last_content_update": datetime.now(pytz.utc)})
    msg = f"{strings.EMOJI_SUCCESS} {field_to_update.replace('_', ' ').capitalize()} updated." if success else f"{strings.EMOJI_ERROR} Failed to update {field_to_update}."
    await update.message.reply_html(msg) # This reply comes after user input
    # Need to re-show the modify core details menu by calling cm_show_modify_core_details_menu
    # However, this function is expecting an update from a callback, not a message.
    # We should design these input receivers to directly call the next display state.
    # For now, manually create a mock callback update object (hacky) or make cm_show_modify_core_details_menu more flexible
    # This indicates a flow design issue - modifying core details should likely be more states in conversation
    # A quick fix is to call cm_show_modify_core_details_menu with an indication it's internal.
    return await cm_show_modify_core_details_menu(update, context, called_internally=True)


async def cm_mod_receive_new_poster(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Similar to cm_receive_anime_poster but for modify flow
    anime_id = context.user_data.get('cm_current_anime_id')
    new_poster_val = None
    if update.message.photo: new_poster_val = update.message.photo[-1].file_id
    elif update.message.text and update.message.text.strip().lower() == 'skip': new_poster_val = settings.ANIME_POSTER_PLACEHOLDER_URL
    elif update.message.text and update.message.text.strip().startswith('http'): new_poster_val = update.message.text.strip()
    else:
        await update.message.reply_html("Invalid input. Send image, URL, or 'skip'.")
        # How to return to correct state CM_MODIFY_FIELD_RECEIVE_NEW_POSTER? Requires specific state.
        # This highlights need for dedicated states for each mod field input. For now:
        return await cm_show_modify_core_details_menu(update, context, called_internally=True)

    success = await anidb.update_anime_details(anime_id, {"poster_file_id": new_poster_val, "last_content_update": datetime.now(pytz.utc)})
    msg = f"{strings.EMOJI_SUCCESS} Poster updated." if success else f"{strings.EMOJI_ERROR} Failed to update poster."
    await update.message.reply_html(msg)
    return await cm_show_modify_core_details_menu(update, context, called_internally=True)


async def cm_mod_field_genres_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    # cm_selected_genres should be pre-loaded when anime was selected for modification
    keyboard = build_genre_selection_keyboard(context.user_data.get('cm_selected_genres', []), callback_prefix="cm_mod_g_toggle_")
    await query.edit_message_text(
        text=f"Editing genres for <b>{context.user_data.get('cm_anime_data',{}).get('title_english','Selected Anime')}</b>. Tap to toggle, then 'Done'.",
        reply_markup=keyboard, parse_mode=ParseMode.HTML)
    return CM_MODIFY_FIELD_TOGGLE_GENRE

async def cm_mod_field_toggle_genre_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed
    query = update.callback_query; await query.answer()
    genre_key = query.data.split("cm_mod_g_toggle_", 1)[1]
    full_genre = next((g for g in settings.AVAILABLE_GENRES if g.startswith(genre_key)), None)
    if not full_genre: return CM_MODIFY_FIELD_TOGGLE_GENRE

    selected_genres = context.user_data.get('cm_selected_genres', [])
    if full_genre in selected_genres: selected_genres.remove(full_genre)
    else: selected_genres.append(full_genre)
    context.user_data['cm_selected_genres'] = selected_genres
    await query.edit_message_reply_markup(reply_markup=build_genre_selection_keyboard(selected_genres, callback_prefix="cm_mod_g_toggle_"))
    return CM_MODIFY_FIELD_TOGGLE_GENRE

async def cm_mod_field_genres_done_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed
    query = update.callback_query; await query.answer()
    selected_genres = context.user_data.get('cm_selected_genres', [])
    if not selected_genres:
        await query.answer("Please select at least one genre.", show_alert=True); return CM_MODIFY_FIELD_TOGGLE_GENRE
    
    anime_id = context.user_data.get('cm_current_anime_id')
    success = await anidb.update_anime_details(anime_id, {"genres": selected_genres, "last_content_update": datetime.now(pytz.utc)})
    msg = f"{strings.EMOJI_SUCCESS} Genres updated." if success else f"{strings.EMOJI_ERROR} Failed to update genres."
    # Can't edit message AND then show another menu directly easily, so send new then show menu
    await query.edit_message_text(text=msg, parse_mode=ParseMode.HTML) # Send confirmation
    return await cm_show_modify_core_details_menu(update, context, called_internally=True) # Go back to modify menu (as a new message)

async def cm_mod_field_status_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    await query.edit_message_text(
        text=f"Select new status for <b>{context.user_data.get('cm_anime_data',{}).get('title_english','Selected Anime')}</b>:",
        reply_markup=build_status_selection_keyboard(callback_prefix="cm_mod_s_select_"), parse_mode=ParseMode.HTML)
    return CM_MODIFY_FIELD_SELECT_STATUS # A new state or reuse if actions distinct

async def cm_mod_receive_new_status(update:Update, context:ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    status_key = query.data.split("cm_mod_s_select_",1)[1]
    full_status = next((s for s in settings.AVAILABLE_STATUSES if s.startswith(status_key)), None)
    if not full_status: return await cm_show_modify_core_details_menu(update, context, called_internally=True) # Error case
    
    anime_id = context.user_data.get('cm_current_anime_id')
    success = await anidb.update_anime_details(anime_id, {"status": full_status, "last_content_update": datetime.now(pytz.utc)})
    msg = f"{strings.EMOJI_SUCCESS} Status updated to {full_status}." if success else f"{strings.EMOJI_ERROR} Failed to update status."
    await query.edit_message_text(text=msg, parse_mode=ParseMode.HTML)
    return await cm_show_modify_core_details_menu(update, context, called_internally=True)


# --- Re-use Season & Episode Management for Modify Flow ---
async def cm_mod_manage_episodes_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed
    # Called when admin chooses "Manage Seasons/Episodes" for an existing anime.
    # Sets context and transitions to CM_MANAGE_SEASON_MENU
    query = update.callback_query; await query.answer()
    context.user_data['cm_flow'] = 'manage_episodes'
    context.user_data['cm_current_season_num'] = 1 # Default to S1 or first available season
    # Load anime doc to check seasons.
    anime_doc = await anidb.get_anime_by_id_str(context.user_data['cm_current_anime_id'])
    if anime_doc and anime_doc.get("seasons"):
        context.user_data['cm_current_season_num'] = anime_doc["seasons"][0]["season_number"] # First season
    
    return await cm_goto_season_episode_mgmt(update, context) # Re-use the handler

async def cm_goto_season_episode_mgmt(update: Update, context: ContextTypes.DEFAULT_TYPE, called_from_finish_ep: bool = False) -> int: # Added param
    query = update.callback_query
    if query and not called_from_finish_ep : await query.answer()

    anime_id = context.user_data.get('cm_current_anime_id')
    current_season_num_from_ctx = context.user_data.get('cm_current_season_num', 1)

    if not anime_id: # Error case
        msg = f"{strings.EMOJI_ERROR} No anime is currently selected for episode management. Please restart from the main Content Management menu."
        keyboard_err = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]])
        if query: await query.edit_message_text(text=msg, reply_markup=keyboard_err, parse_mode=ParseMode.HTML)
        else: await update.message.reply_html(text=msg, reply_markup=keyboard_err)
        return CM_MAIN_MENU


    anime_doc = await anidb.get_anime_by_id_str(anime_id)
    if not anime_doc:
        msg = f"{strings.EMOJI_ERROR} Selected anime (ID: {anime_id}) not found in DB. It might have been deleted."
        if query: await query.edit_message_text(text=msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
        else: await update.message.reply_html(text=msg)
        return CM_MAIN_MENU

    anime_title = anime_doc.get("title_english", "Selected Anime")
    
    # Season selection buttons for context switching
    seasons_in_anime = sorted(anime_doc.get("seasons", []), key=lambda s: s.get("season_number", 0))
    current_season_num = current_season_num_from_ctx # Use what's in context as the primary working season
    
    # Verify if current_season_num is valid for this anime, else default
    if not any(s['season_number'] == current_season_num for s in seasons_in_anime) and seasons_in_anime:
        current_season_num = seasons_in_anime[0]['season_number']
        context.user_data['cm_current_season_num'] = current_season_num
    elif not seasons_in_anime : # No seasons exist yet, implies might be first time or error.
        # This state should be typically after seasons are defined.
        # If no seasons (e.g., just created anime and admin chose "Finish"), this menu makes less sense without an "Add Season" option.
        # Let's assume for this menu, seasons *should* exist if modifying episodes for it.
        # If in 'add' flow and just defined X seasons, start with S1.
         if context.user_data.get('cm_flow') == 'add': # Newly added, just got N seasons.
            current_season_num = 1
            context.user_data['cm_current_season_num'] = 1
         else: # Modify flow, but no seasons
            msg = f"<b>{anime_title}</b> has no seasons defined yet. You might need to add them first or modify anime structure." # TODO Add "Add Season"
            if query: await query.edit_message_text(text=msg,parse_mode=ParseMode.HTML)
            else: await update.message.reply_html(text=msg)
            return CM_MODIFY_SELECTED_ANIME_MENU # Back to modify anime options

    msg_text = strings.CM_SEASON_PROMPT.format(season_num=current_season_num, anime_title=anime_title)
    season_data = next((s for s in seasons_in_anime if s["season_number"] == current_season_num), None)
    num_episodes_in_season = len(season_data["episodes"]) if season_data else 0
    msg_text += f"\nCurrently managing <b>Season {current_season_num}</b> (<i>{num_episodes_in_season} episodes</i>)."

    keyboard = [
        [InlineKeyboardButton(f"{strings.EMOJI_UPLOAD} Add Episode to S{current_season_num}", callback_data="cm_ep_add_new_prompt")],
        # TODO: Edit/Delete Episode for S{current_season_num} (requires listing episodes first)
        # [InlineKeyboardButton(f"{strings.EMOJI_LIST} List/Edit Episodes for S{current_season_num}", callback_data=f"cm_ep_list_s_{current_season_num}")],
    ]

    if len(seasons_in_anime) > 1:
        # Build season switcher
        season_switcher_row = []
        for s_doc in seasons_in_anime:
            s_num = s_doc['season_number']
            prefix = "➡️ S" if s_num == current_season_num else "S"
            season_switcher_row.append(InlineKeyboardButton(f"{prefix}{s_num}", callback_data=f"cm_switch_season_{s_num}"))
        keyboard.append(season_switcher_row)

    # TODO: Add button for "Add New Season to this Anime" (for modify flow)
    # TODO: Add button for "Delete Current Season S{X}" (with confirm)

    original_flow_end_button_cb = "cm_end_conversation" # default
    if context.user_data.get('cm_flow') == 'modify':
        original_flow_end_button_cb = "cm_mod_back_to_anime_menu_cb" # Back to Modify Options for THIS anime

    keyboard.append([InlineKeyboardButton(f"{strings.EMOJI_SUCCESS} Done with Episodes", callback_data=original_flow_end_button_cb)])
    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]) # Full cancel
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Smart reply/edit
    if query:
        try: await query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception: # If message not modified or error, send new (e.g. after text input)
            await context.bot.send_message(query.message.chat_id, text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif update.message :
        await update.message.reply_html(text=msg_text, reply_markup=reply_markup)
    return CM_MANAGE_SEASON_MENU

async def cm_ep_add_new_prompt_num(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    s_num = context.user_data.get('cm_current_season_num', 'N/A')
    await query.edit_message_text(
        text=strings.CM_EPISODE_PROMPT_NUM.format(season_num=s_num),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_season_menu")]])
    )
    return CM_EPISODE_NUMBER


async def cm_ep_add_new_ep_num_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    s_num = context.user_data.get('cm_current_season_num', 'N/A')
    await query.edit_message_text(
        text=strings.CM_EPISODE_PROMPT_NUM.format(season_num=s_num),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_season_menu")]])
    )
    return CM_EPISODE_NUMBER


# --- Shared SEASON & EPISODE MANAGEMENT (from previous response, ensure paths correct) ---
# Functions like cm_goto_season_episode_mgmt, cm_ep_add_new_prompt_num etc.
# These will need to be robust to the 'cm_flow' ('add' or 'modify' or 'manage_episodes')
# and current_anime_id to load/save correctly.
# The cancel operations also need to route back correctly. E.g., cm_cancel_op_back_to_season_menu should work.
# (Code for these shared parts from previous iteration is assumed here)
# ... cm_goto_season_episode_mgmt, cm_ep_add_new_prompt_num ... cm_ep_set_release_date_receive ...


async def cm_switch_working_season(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    new_season_num = int(query.data.split("cm_switch_season_",1)[1])
    context.user_data['cm_current_season_num'] = new_season_num
    # Clear episode context when switching season
    context.user_data.pop('cm_current_episode_num', None)
    context.user_data.pop('cm_current_file_version_data', None)
    return await cm_goto_season_episode_mgmt(update, context) # Re-display season menu for new current season

# Remaining EPISODE handlers are largely the same as first iteration
# Ensure cancel buttons in these flows correctly point back, e.g., to CM_MANAGE_SEASON_MENU state via callback like `cm_cancel_op_back_to_season_menu`
# For example, after `cm_ep_receive_sub_lang_and_save_version` success, options should lead back correctly.
# `cm_ep_done_with_season` -> `cm_goto_season_episode_mgmt` which re-evaluates flow.

async def cm_ep_add_new_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Renamed to avoid clash
    query = update.callback_query
    await query.answer()
    s_num = context.user_data.get('cm_current_season_num', 'N/A')
    await query.edit_message_text(
        text=strings.CM_EPISODE_PROMPT_NUM.format(season_num=s_num),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_season_menu")]])
    )
    return CM_EPISODE_NUMBER
# (CM_EPISODE_NUMBER, CM_EPISODE_FILE_OR_DATE, ... CM_EPISODE_SET_RELEASE_DATE handlers from previous code)
# (cm_ep_receive_number, cm_ep_handle_choice_file_or_date, cm_ep_receive_file etc.)
# ... These detailed sub-flow handlers would be here, but for brevity in this single response,
# please refer to their logic in the previous provided code for `content_manager.py`.
# Crucial: Ensure their state transitions and cancel callbacks are contextual.



async def cm_ep_receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ep_num_str = update.message.text.strip()
    try:
        ep_num = int(ep_num_str)
        if ep_num <= 0: raise ValueError("Episode number must be positive.")
    except ValueError:
        await update.message.reply_html("Invalid episode number. Please enter a positive integer.")
        return CM_EPISODE_NUMBER
    
    context.user_data['cm_current_episode_num'] = ep_num
    # Clear previous file version data if any for new episode
    context.user_data.pop('cm_current_file_version_data', None)

    anime_title = "Selected Anime" # Get from context.user_data if needed
    s_num = context.user_data.get('cm_current_season_num', 'N/A')

    # Check if episode already exists for this season
    anime_id = context.user_data.get('cm_current_anime_id')
    if anime_id:
        anime_doc = await anidb.get_anime_by_id_str(anime_id)
        if anime_doc:
            anime_title = anime_doc.get("title_english", "Selected Anime")
            season_data = next((s for s in anime_doc.get("seasons", []) if s["season_number"] == s_num), None)
            if season_data:
                existing_ep = next((e for e in season_data.get("episodes", []) if e["episode_number"] == ep_num), None)
                if existing_ep:
                    await update.message.reply_html(
                        f"{strings.EMOJI_ERROR} Episode {ep_num} already exists in S{s_num} for this anime.\n"
                        f"You can modify it or choose a different episode number.",
                        reply_markup=InlineKeyboardMarkup([
                            # [InlineKeyboardButton(f"{EMOJI_EDIT} Modify EP {ep_num}", callback_data=f"cm_ep_force_modify_{ep_num}")],
                            [InlineKeyboardButton("🔄 Try Different EP Number", callback_data="cm_ep_add_new_ep_num_retry")],
                            [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_season_menu")]
                         ])
                    )
                    return CM_EPISODE_NUMBER # Stay in state or specific error state

    text = strings.CM_EPISODE_FILE_OR_DATE.format(
        season_num=s_num,
        episode_num=ep_num,
        anime_title=anime_title
    )
    keyboard = [
        [InlineKeyboardButton(strings.BTN_CM_ADD_EPISODE_FILES, callback_data="cm_ep_choice_add_files")],
        [InlineKeyboardButton(strings.BTN_CM_SET_RELEASE_DATE, callback_data="cm_ep_choice_set_date")],
        [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_season_menu")]
    ]
    await update.message.reply_html(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
    return CM_EPISODE_FILE_OR_DATE


async def cm_ep_handle_choice_file_or_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data # "cm_ep_choice_add_files" or "cm_ep_choice_set_date"

    s_num = context.user_data.get('cm_current_season_num', 'N/A')
    ep_num = context.user_data.get('cm_current_episode_num', 'N/A')
    anime_title = "Selected Anime" # Get from context

    if choice == "cm_ep_choice_add_files":
        context.user_data['cm_current_file_version_data'] = {} # Init for this version
        await query.edit_message_text(
            text=strings.CM_PROMPT_SEND_FILE.format(s_num=s_num, ep_num=ep_num, anime_title=anime_title),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_ep_choice")]])
        )
        return CM_EPISODE_SEND_FILE
    elif choice == "cm_ep_choice_set_date":
        await query.edit_message_text(
            text=strings.CM_PROMPT_RELEASE_DATE.format(s_num=s_num, ep_num=ep_num),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_ep_choice")]])
        )
        return CM_EPISODE_SET_RELEASE_DATE
    return CM_EPISODE_FILE_OR_DATE # Should not happen

# Placeholder for CM_EPISODE_SEND_FILE logic and subsequent states (resolution, audio, sub)
# These would follow a similar pattern: receive input, store in context.user_data['cm_current_file_version_data'], prompt for next.
# Finally, when all version data is collected, it would be added to the episode in DB.

async def cm_ep_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_id = None
    file_type = None
    file_size = 0

    if update.message.document:
        file_id = update.message.document.file_id
        file_type = "document"
        file_size = update.message.document.file_size
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = "video"
        file_size = update.message.video.file_size
    else:
        await update.message.reply_html("Invalid file type. Please send a video or document file.")
        return CM_EPISODE_SEND_FILE

    context.user_data['cm_current_file_version_data'] = {
        "file_id": file_id,
        "file_type": file_type,
        "file_size_bytes": file_size
    }

    # Prompt for resolution
    buttons = []
    row = []
    for res in settings.SUPPORTED_RESOLUTIONS:
        row.append(InlineKeyboardButton(res, callback_data=f"cm_ep_file_res_{res}"))
        if len(row) >= 3: # Example button layout
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_ep_choice")])

    await update.message.reply_html(
        text=strings.CM_PROMPT_RESOLUTION,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CM_EPISODE_SELECT_RESOLUTION


async def cm_ep_receive_resolution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    res = query.data.split("cm_ep_file_res_",1)[1]
    context.user_data['cm_current_file_version_data']['resolution'] = res

    # Prompt for audio lang
    buttons = []
    row = []
    for lang in settings.SUPPORTED_AUDIO_LANGUAGES:
        row.append(InlineKeyboardButton(lang, callback_data=f"cm_ep_file_audio_{lang.split(' ')[0]}"))
        if len(row) >= 2: # Example button layout
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_ep_choice")])


    await query.edit_message_text(
        text=strings.CM_PROMPT_AUDIO_LANG,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )
    return CM_EPISODE_SELECT_AUDIO

async def cm_ep_receive_audio_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang_key = query.data.split("cm_ep_file_audio_",1)[1]
    
    full_lang_name = next((l for l in settings.SUPPORTED_AUDIO_LANGUAGES if l.startswith(lang_key)), lang_key) # Find full name
    context.user_data['cm_current_file_version_data']['audio_language'] = full_lang_name


    # Prompt for sub lang
    buttons = []
    row = []
    for lang in settings.SUPPORTED_SUB_LANGUAGES:
        row.append(InlineKeyboardButton(lang, callback_data=f"cm_ep_file_sub_{lang.split(' ')[0]}"))
        if len(row) >= 2: # Example button layout
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_ep_choice")])


    await query.edit_message_text(
        text=strings.CM_PROMPT_SUB_LANG,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )
    return CM_EPISODE_SELECT_SUB

async def cm_ep_add_another_version(update:Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    s_num = context.user_data.get('cm_current_season_num', 'N/A')
    ep_num = context.user_data.get('cm_current_episode_num', 'N/A')
    anime_title = "Selected Anime" # Get from context

    context.user_data['cm_current_file_version_data'] = {} # Init for new version
    await query.edit_message_text(
        text=strings.CM_PROMPT_SEND_FILE.format(s_num=s_num, ep_num=ep_num, anime_title=anime_title),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_season_menu")]])
    )
    return CM_EPISODE_SEND_FILE

async def cm_ep_add_next_ep_for_season(update:Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    current_ep_num = context.user_data.get('cm_current_episode_num', 0)
    context.user_data['cm_current_episode_num'] = current_ep_num + 1 # Tentatively set next
    
    s_num = context.user_data.get('cm_current_season_num', 'N/A')
    # Directly prompt for the new (next) episode number to confirm or change
    await query.edit_message_text(
        text=strings.CM_EPISODE_PROMPT_NUM.format(season_num=s_num) + f"\n(Suggested next: EP {current_ep_num+1})",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_season_menu")]])
    )
    return CM_EPISODE_NUMBER


async def cm_ep_set_release_date_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives release date and saves episode with only this info."""
    date_str = update.message.text.strip().upper()
    s_num = context.user_data.get('cm_current_season_num')
    ep_num = context.user_data.get('cm_current_episode_num')
    anime_id = context.user_data.get('cm_current_anime_id')

    air_date = None
    if date_str != "TBA":
        try:
            air_date = datetime.strptime(date_str, "%Y-%m-%d")
            air_date = pytz.utc.localize(air_date) # Make it timezone aware (UTC)
        except ValueError:
            await update.message.reply_html("Invalid date format. Please use YYYY-MM-DD or type 'TBA'.")
            return CM_EPISODE_SET_RELEASE_DATE

    episode_data = {
        "episode_number": ep_num,
        "air_date": air_date if date_str != "TBA" else "TBA", # Store string "TBA" or datetime obj
        "versions": []
    }
    
    # Robust function needed in DB to add/update episode with this data
    success = await anidb.add_or_update_episode_data(anime_id, s_num, ep_num, episode_data, only_air_date=True)

    if success:
        await anidb.anime_collection.update_one({"_id": ObjectId(anime_id)}, {"$set": {"last_content_update": datetime.now(pytz.utc)}})
        display_date = date_str if date_str == "TBA" else air_date.strftime("%Y-%m-%d")
        msg = strings.CM_RELEASE_DATE_SET.format(s_num=s_num, ep_num=ep_num, date=display_date)
        # Options: add next episode, finish season
        keyboard = [
            [InlineKeyboardButton(strings.BTN_CM_NEXT_EPISODE, callback_data="cm_ep_add_next_ep_for_season")],
            [InlineKeyboardButton(strings.BTN_CM_FINISH_SEASON_EPISODES, callback_data="cm_ep_done_with_season")]
        ]
        await update.message.reply_html(msg, reply_markup=InlineKeyboardMarkup(keyboard))
        return CM_MANAGE_SEASON_MENU # Back to season management menu or options after adding
    else:
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Failed to set release date. DB error.")
        return CM_MANAGE_SEASON_MENU


async def cm_ep_receive_sub_lang_and_save_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    lang_key = query.data.split("cm_ep_file_sub_",1)[1]
    full_lang_name = next((l for l in settings.SUPPORTED_SUB_LANGUAGES if l.startswith(lang_key)), lang_key)
    context.user_data['cm_current_file_version_data']['subtitle_language'] = full_lang_name

    anime_id = context.user_data.get('cm_current_anime_id')
    s_num = context.user_data.get('cm_current_season_num')
    ep_num = context.user_data.get('cm_current_episode_num')
    version_data_to_save = context.user_data.pop('cm_current_file_version_data', None)

    if not all([anime_id, s_num is not None, ep_num is not None, version_data_to_save]): # s_num, ep_num can be 0
        await query.edit_message_text(f"{strings.EMOJI_ERROR} Context data missing. Cannot save. Restart CM.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_end_conversation")]]))
        return ConversationHandler.END

    version_data_to_save['upload_date'] = datetime.now(pytz.utc)
    success = await anidb.add_file_version_to_episode_robust(anime_id, s_num, ep_num, version_data_to_save)

    if success:
        await anidb.anime_collection.update_one({"_id": ObjectId(anime_id)}, {"$set": {"last_content_update": datetime.now(pytz.utc)}})
        text = strings.CM_FILE_VERSION_ADDED.format(s_num=s_num, ep_num=ep_num) + "\n" + strings.CM_OPTIONS_AFTER_VERSION_ADD
        keyboard = [
            [InlineKeyboardButton(strings.BTN_CM_ADD_ANOTHER_VERSION, callback_data="cm_ep_add_another_v_cb")],
            [InlineKeyboardButton(strings.BTN_CM_NEXT_EPISODE, callback_data="cm_ep_add_next_ep_cb")],
            [InlineKeyboardButton(strings.BTN_CM_FINISH_SEASON_EPISODES, callback_data="cm_ep_done_w_season_cb")],
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_text(f"{strings.EMOJI_ERROR} Failed to save file version to DB.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_season_menu")]]))
    return CM_MANAGE_SEASON_MENU # Return to season menu to handle options

async def cm_ep_add_another_v_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Same as cm_ep_add_another_version from before)
    return await cm_ep_add_another_version(update, context)

async def cm_ep_add_next_ep_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # (Same as cm_ep_add_next_ep_for_season from before)
    return await cm_ep_add_next_ep_for_season(update, context)

async def cm_ep_done_w_season_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # This just goes back to the season/episode management main screen
    query = update.callback_query; await query.answer()
    return await cm_goto_season_episode_mgmt(update, context, called_from_finish_ep=True)


# --- === DELETE ANIME FLOW (Placeholders) === ---
async def cm_start_delete_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    context.user_data['cm_flow'] = 'delete'
    await query.edit_message_text(text="Enter title of anime to search for deletion:",
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_cancel_op_back_to_cm_main")]]))
    return CM_DELETE_ASK_SEARCH_TERM

# ... Handlers for CM_DELETE_ASK_SEARCH_TERM, CM_DELETE_SHOW_SEARCH_RESULTS, CM_DELETE_CONFIRM ...
# CM_DELETE_SHOW_SEARCH_RESULTS will show list of anime with callback "cm_del_confirm_{anime_id}"
# CM_DELETE_CONFIRM will show "Are you sure..." and then execute DB delete.


# --- === GENERAL CANCEL & END === ---
async def cm_cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE, called_from_state_fallback:bool=False, specific_cancel_target:str=None) -> int:
    query = update.callback_query
    # Only answer query if it's actually from a query and not called by general fallback.
    if query and not called_from_state_fallback: await query.answer(strings.OPERATION_CANCELLED)
    elif update.message and called_from_state_fallback: # called by /cancel command as fallback
        await update.message.reply_html(strings.OPERATION_CANCELLED)


    cancel_target_cb = specific_cancel_target if specific_cancel_target else (query.data if query else "cm_cancel_op_back_to_cm_main")

    if cancel_target_cb == "cm_cancel_op_back_to_season_menu":
        # context.user_data.pop('cm_current_episode_num', None) # Clean episode specific state
        # context.user_data.pop('cm_current_file_version_data', None)
        return await cm_goto_season_episode_mgmt(update, context)
    elif cancel_target_cb == "cm_cancel_op_back_to_ep_choice":
        s_num = context.user_data.get('cm_current_season_num'); ep_num = context.user_data.get('cm_current_episode_num')
        # Rebuild and show "Add Files or Set Release Date" for current ep
        # (This implies a function to show that specific screen)
        # For simplicity now, let's go up one level higher for this generic cancel
        # return await some_function_to_show_ep_choice_menu(update, context)
        # Fallback to season menu if too complex:
        return await cm_goto_season_episode_mgmt(update, context) # Or a state that displays file_or_date choice
    elif cancel_target_cb == "cm_cancel_op_back_to_modify_details_menu":
        return await cm_show_modify_core_details_menu(update, context, called_internally=True)
    elif cancel_target_cb == "cm_cancel_op_back_to_cm_main" or cancel_target_cb == "cm_cancel_op": # default cancel
        return await manage_content_start(update, context, called_from_cancel=True)

    # If it was a generic /cancel from a command message fallback
    if update.message and called_from_state_fallback:
        return await manage_content_start(update, context, called_from_cancel=True)
    
    return CM_MAIN_MENU # Fallback state

async def cm_end_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query: await query.answer()
    clear_cm_context(context)
    await reply_with_main_menu(update, context, message_text=f"{strings.EMOJI_SUCCESS} Content management ended.")
    return ConversationHandler.END


# --- Get Conversation Handler ---
def get_manage_content_conv_handler() -> ConversationHandler:
    async def general_cancel_from_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await cm_cancel_operation(update, context, called_from_state_fallback=True, specific_cancel_target="cm_cancel_op_back_to_cm_main")

    return ConversationHandler(
        entry_points=[
            CommandHandler("manage_content", manage_content_start, filters=filters.User(settings.ADMIN_IDS) & ~filters.ChatType.CHANNEL),
            CallbackQueryHandler(manage_content_start, pattern="^admin_cm_start$")
        ],
        states={
            CM_MAIN_MENU: [
                CallbackQueryHandler(cm_start_add_new_anime, pattern="^cm_start_add_new$"),
                CallbackQueryHandler(cm_start_modify_existing, pattern="^cm_start_modify_existing$"),
                CallbackQueryHandler(cm_start_delete_anime, pattern="^cm_start_delete_anime$"),
            ],
            # Add Flow
            CM_ADD_TITLE: [ MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_anime_title),
                            CallbackQueryHandler(cm_add_title_retry_cb, pattern="^cm_add_title_retry_cb$"),
                            CallbackQueryHandler(cm_selected_anime_for_modification, pattern="^cm_force_mod_existing_")], # Go to modify if exists
            CM_ADD_POSTER: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), cm_receive_anime_poster)],
            CM_ADD_SYNOPSIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_anime_synopsis)],
            CM_ADD_SELECT_GENRES: [ CallbackQueryHandler(cm_add_toggle_genre, pattern="^cm_add_genre_(?!done)"),
                                   CallbackQueryHandler(cm_add_genre_selection_done, pattern="^cm_add_genre_done$")],
            CM_ADD_SELECT_STATUS: [CallbackQueryHandler(cm_add_receive_anime_status, pattern="^cm_add_status_")],
            CM_ADD_RELEASE_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_release_year)],
            CM_ADD_NUM_SEASONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_num_seasons)],

            # Modify Flow
            CM_MODIFY_ASK_SEARCH_TERM: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_modify_search_term)],
            CM_MODIFY_SHOW_SEARCH_RESULTS: [
                CallbackQueryHandler(cm_selected_anime_for_modification, pattern="^cm_mod_select_"),
                CallbackQueryHandler(cm_mod_search_again_cb, pattern="^cm_mod_search_again_cb$")
                # Add pagination callbacks for modify search results if implemented
            ],
            CM_MODIFY_SELECTED_ANIME_MENU: [
                CallbackQueryHandler(cm_mod_core_details_menu_cb, pattern="^cm_mod_core_details_menu$"),
                CallbackQueryHandler(cm_mod_manage_episodes_menu_cb, pattern="^cm_mod_manage_episodes_menu$"),
                CallbackQueryHandler(cm_mod_back_to_search_results_cb, pattern="^cm_mod_back_to_search_results_cb$")
            ],
            CM_MODIFY_CORE_DETAILS_MENU: [ # Menu for which field to edit
                CallbackQueryHandler(cm_mod_field_title_select, pattern="^cm_mod_field_title$"),
                CallbackQueryHandler(cm_mod_field_synopsis_select, pattern="^cm_mod_field_synopsis$"),
                CallbackQueryHandler(cm_mod_field_poster_select, pattern="^cm_mod_field_poster$"),
                CallbackQueryHandler(cm_mod_field_genres_select, pattern="^cm_mod_field_genres$"),
                CallbackQueryHandler(cm_mod_field_status_select, pattern="^cm_mod_field_status$"),
                CallbackQueryHandler(cm_mod_field_year_select, pattern="^cm_mod_field_year$"),
                CallbackQueryHandler(cm_mod_back_to_anime_menu_cb, pattern="^cm_mod_back_to_anime_menu_cb$"), # Back to mod anime menu
            ],
            # Individual field edit input states for Modify (each would get a MessageHandler or specific callback)
            CM_MODIFY_FIELD_RECEIVE_NEW_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_mod_receive_new_text_field)],
            CM_MODIFY_FIELD_RECEIVE_NEW_SYNOPSIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_mod_receive_new_text_field)],
            CM_MODIFY_FIELD_RECEIVE_NEW_POSTER: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), cm_mod_receive_new_poster)],
            CM_MODIFY_FIELD_TOGGLE_GENRE: [ # After selecting "Genres" from modify menu
                CallbackQueryHandler(cm_mod_field_toggle_genre_action, pattern="^cm_mod_g_toggle_(?!done)"),
                CallbackQueryHandler(cm_mod_field_genres_done_action, pattern="^cm_mod_g_toggle_done$")
            ],
            CM_MODIFY_FIELD_SELECT_STATUS: [ # After selecting "Status" from modify menu -> shows status buttons
                 CallbackQueryHandler(cm_mod_receive_new_status, pattern="^cm_mod_s_select_")
            ],
            CM_MODIFY_FIELD_RECEIVE_NEW_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_release_year)], # Reuses from add


            # Shared Season/Episode Management
            CM_MANAGE_SEASON_MENU: [
                CallbackQueryHandler(cm_goto_season_episode_mgmt, pattern="^cm_goto_season_episode_mgmt$"),
                CallbackQueryHandler(cm_ep_add_new_prompt, pattern="^cm_ep_add_new_prompt$"), # Renamed from cm_ep_add_new
                CallbackQueryHandler(cm_switch_working_season, pattern="^cm_switch_season_"),
                CallbackQueryHandler(cm_ep_add_another_v_cb, pattern="^cm_ep_add_another_v_cb$"), # After saving a version
                CallbackQueryHandler(cm_ep_add_next_ep_cb, pattern="^cm_ep_add_next_ep_cb$"),     # "
                CallbackQueryHandler(cm_ep_done_w_season_cb, pattern="^cm_ep_done_w_season_cb$"),# "
                 # Callbacks to return to main anime mod menu or end CM conversation entirely from here
                CallbackQueryHandler(cm_mod_back_to_anime_menu_cb, pattern="^cm_mod_back_to_anime_menu_cb$"),

            ],
            CM_EPISODE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_ep_receive_number),
                                CallbackQueryHandler(cm_ep_add_new_ep_num_retry, pattern="^cm_ep_add_new_ep_num_retry$")], # if retry num
            CM_EPISODE_FILE_OR_DATE: [CallbackQueryHandler(cm_ep_handle_choice_file_or_date, pattern="^cm_ep_choice_")],
            CM_EPISODE_SEND_FILE: [MessageHandler(filters.VIDEO | filters.Document, cm_ep_receive_file)],
            CM_EPISODE_SELECT_RESOLUTION: [CallbackQueryHandler(cm_ep_receive_resolution, pattern="^cm_ep_file_res_")],
            CM_EPISODE_SELECT_AUDIO: [CallbackQueryHandler(cm_ep_receive_audio_lang, pattern="^cm_ep_file_audio_")],
            CM_EPISODE_SELECT_SUB: [CallbackQueryHandler(cm_ep_receive_sub_lang_and_save_version, pattern="^cm_ep_file_sub_")],
            CM_EPISODE_SET_RELEASE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_ep_set_release_date_receive)],

            # Delete Flow (Placeholders)
            CM_DELETE_ASK_SEARCH_TERM: [], # MessageHandler
            CM_DELETE_SHOW_SEARCH_RESULTS: [], # CallbackQueryHandler for selection
            CM_DELETE_CONFIRM: [], # CallbackQueryHandler for "Yes/No"
        },
        fallbacks=[
            CallbackQueryHandler(cm_cancel_operation, pattern="^cm_cancel_op"), # Most generic cancel in CM
            CallbackQueryHandler(cm_cancel_operation, pattern="^cm_cancel_op_back_to_season_menu$"),
            CallbackQueryHandler(cm_cancel_operation, pattern="^cm_cancel_op_back_to_ep_choice$"),
            CallbackQueryHandler(cm_cancel_operation, pattern="^cm_cancel_op_back_to_modify_details_menu$"),
            CallbackQueryHandler(cm_cancel_operation, pattern="^cm_cancel_op_back_to_cm_main$"),
            CallbackQueryHandler(cm_end_conversation, pattern="^cm_end_conversation$"),
            CommandHandler("cancel", general_cancel_from_command) # Command to break out of conversation fully
        ],
        persistent=False,
        name="content_management_conversation",
        allow_reentry=True
    )
