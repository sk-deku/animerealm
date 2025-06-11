# bot/content_manager.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from telegram.constants import ParseMode
from bson import ObjectId # For generating new anime _id if needed, though MongoDB does it
from datetime import datetime
import pytz

from configs import settings, strings
from database.mongo_db import db as anidb
from .core_handlers import reply_with_main_menu # For cancelling

logger = logging.getLogger(__name__)

# --- Conversation States ---
# Main Menu for Content Management
CM_MAIN_MENU = 0

# Adding New Anime Flow
CM_ADD_ANIME_TITLE_ENG = 1
CM_ADD_ANIME_POSTER = 2
CM_ADD_ANIME_SYNOPSIS = 3
CM_ADD_ANIME_GENRES = 4
CM_ADD_ANIME_STATUS = 5
CM_ADD_ANIME_RELEASE_YEAR = 6
CM_ADD_ANIME_NUM_SEASONS = 7
# (States for adding episodes/versions would follow)
CM_MANAGE_SEASONS_FOR_ANIME = 8 # After anime base info added, or when modifying
CM_MANAGE_EPISODES_FOR_SEASON = 9
CM_ADD_EPISODE_NUMBER = 10
CM_ADD_EPISODE_FILE_OR_DATE = 11
CM_ADD_EPISODE_SEND_FILE = 12
CM_ADD_EPISODE_FILE_RESOLUTION = 13
CM_ADD_EPISODE_FILE_AUDIO = 14
CM_ADD_EPISODE_FILE_SUB = 15
CM_ADD_EPISODE_RELEASE_DATE = 16


# Modifying Existing Anime Flow
CM_MODIFY_SELECT_ANIME = 20
CM_MODIFY_ANIME_OPTIONS = 21 # What to modify: details, seasons, etc.
CM_MODIFY_ANIME_DETAIL_SELECT = 22 # Which detail: title, poster etc.
CM_MODIFY_ANIME_DETAIL_INPUT = 23 # New value for the detail

# (Deletion states would be separate or integrated carefully)


# --- Helper to clear CM data from context.user_data ---
def clear_cm_user_data(context: ContextTypes.DEFAULT_TYPE):
    keys_to_pop = [k for k in context.user_data if k.startswith("cm_")]
    for key in keys_to_pop:
        context.user_data.pop(key, None)
    logger.debug("Cleared content management specific user_data.")

# --- Entry Point: /manage_content or Admin Panel Button ---
async def manage_content_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the main Content Management menu for admins."""
    query = update.callback_query
    user = update.effective_user

    if user.id not in settings.ADMIN_IDS:
        if query: await query.answer("Access Denied!", show_alert=True)
        # No reply if from command by non-admin as filters in main.py handle it.
        return ConversationHandler.END

    if query:
        await query.answer()

    clear_cm_user_data(context) # Clear any previous CM session data

    text = strings.ADMIN_CONTENT_MAIN_MENU
    keyboard = [
        [InlineKeyboardButton(strings.BTN_CM_ADD_ANIME, callback_data="cm_action_add_new")],
        [InlineKeyboardButton(strings.BTN_CM_MODIFY_ANIME, callback_data="cm_action_modify_existing")],
        # [InlineKeyboardButton(strings.BTN_CM_DELETE_ANIME, callback_data="cm_action_delete_anime")], # Deletion is complex
        [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text=text, reply_markup=reply_markup)
    return CM_MAIN_MENU


# --- === ADD NEW ANIME FLOW === ---

# Start Add New Anime
async def cm_start_add_new_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["cm_current_flow"] = "add_new"
    context.user_data["cm_anime_data"] = {} # Initialize dict to store anime info

    await query.edit_message_text(
        text=strings.CM_PROMPT_ANIME_TITLE_ENG,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")]]))
    return CM_ADD_ANIME_TITLE_ENG

# Receive English Title
async def cm_receive_title_eng(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title_eng = update.message.text.strip()
    if not title_eng or len(title_eng) < 2:
        await update.message.reply_html("Title seems too short. Please provide a valid English title.")
        return CM_ADD_ANIME_TITLE_ENG # Stay in current state

    # Check for existing anime with same title to prevent duplicates (optional, but good)
    existing_anime = await anidb.get_anime_by_title_exact(title_eng)
    if existing_anime:
        await update.message.reply_html(
            f"{strings.EMOJI_ERROR} An anime with the title '<b>{title_eng}</b>' already exists (ID: <code>{existing_anime['_id']}</code>).\n"
            f"Please use a different title or modify the existing one."
        )
        # Offer buttons to modify existing or cancel
        kb = [[InlineKeyboardButton("📝 Modify Existing", callback_data=f"cm_action_direct_modify_{existing_anime['_id']}")] ,
              [InlineKeyboardButton("↩️ Enter Different Title", callback_data="cm_retry_add_title_eng")],
              [InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")]]
        await update.message.reply_html("What would you like to do?", reply_markup=InlineKeyboardMarkup(kb))
        return CM_ADD_ANIME_TITLE_ENG # Or a new state for handling duplicates


    context.user_data["cm_anime_data"]["title_english"] = title_eng
    logger.info(f"CM: Received title_english: {title_eng}")

    await update.message.reply_html(
        text=strings.CM_PROMPT_POSTER,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")]]))
    return CM_ADD_ANIME_POSTER

async def cm_retry_add_title_eng(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        text=strings.CM_PROMPT_ANIME_TITLE_ENG,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")]]))
    return CM_ADD_ANIME_TITLE_ENG


# Receive Poster (Photo or URL or Skip)
async def cm_receive_poster(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    poster_file_id = None
    if update.message.photo:
        poster_file_id = update.message.photo[-1].file_id # Largest photo
        logger.info(f"CM: Received poster as photo: {poster_file_id}")
    elif update.message.text:
        text_input = update.message.text.strip().lower()
        if text_input == "skip":
            poster_file_id = settings.ANIME_POSTER_PLACEHOLDER_URL # Use placeholder
            logger.info("CM: Poster skipped, using placeholder.")
        elif text_input.startswith("http"):
            poster_file_id = update.message.text.strip() # Store URL
            logger.info(f"CM: Received poster as URL: {poster_file_id}")
        else:
            await update.message.reply_html("Invalid input. Please send a photo, a valid URL, or type 'skip'.")
            return CM_ADD_ANIME_POSTER

    context.user_data["cm_anime_data"]["poster_file_id"] = poster_file_id

    await update.message.reply_html(
        text=strings.CM_PROMPT_SYNOPSIS,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")]]))
    return CM_ADD_ANIME_SYNOPSIS

# Receive Synopsis
async def cm_receive_synopsis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    synopsis = update.message.text.strip()
    if synopsis.lower() == "skip":
        synopsis = "No synopsis available."
    elif not synopsis or len(synopsis) < 10:
        await update.message.reply_html("Synopsis seems too short. Please provide a valid synopsis or type 'skip'.")
        return CM_ADD_ANIME_SYNOPSIS

    context.user_data["cm_anime_data"]["synopsis"] = synopsis
    logger.info(f"CM: Received synopsis.") # Avoid logging full synopsis to keep logs cleaner

    # Prepare Genre Selection
    context.user_data["cm_selected_genres"] = [] # Initialize for multi-select
    genres_kb = build_genre_selection_keyboard(context.user_data["cm_selected_genres"])
    anime_title = context.user_data["cm_anime_data"].get("title_english", "this anime")
    await update.message.reply_html(
        text=strings.CM_PROMPT_SELECT_GENRES.format(anime_title=anime_title),
        reply_markup=genres_kb)
    return CM_ADD_ANIME_GENRES


def build_genre_selection_keyboard(selected_genres_list: list) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for genre in settings.AVAILABLE_GENRES:
        genre_key = genre.split(" ")[0] # Use first word as key, as used in other places
        is_selected = genre in selected_genres_list
        button_text = f"{strings.EMOJI_SUCCESS if is_selected else ''} {genre}"
        # Callback "cm_genre_toggle_GENREKEY"
        row.append(InlineKeyboardButton(button_text, callback_data=f"cm_genre_toggle_{genre_key}"))
        if len(row) >= settings.GENRE_BUTTONS_PER_ROW: # Adjust as needed
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(f"{strings.EMOJI_SUCCESS} Done Selecting Genres", callback_data="cm_genre_done")])
    buttons.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")])
    return InlineKeyboardMarkup(buttons)

# Handle Genre Toggle
async def cm_toggle_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    genre_key_toggled = query.data.split("cm_genre_toggle_", 1)[1]

    # Find full genre name from key
    full_genre_name = None
    for g in settings.AVAILABLE_GENRES:
        if g.startswith(genre_key_toggled):
            full_genre_name = g
            break
    
    if not full_genre_name:
        logger.warning(f"CM: Toggled genre key '{genre_key_toggled}' not found in AVAILABLE_GENRES.")
        return CM_ADD_ANIME_GENRES # Stay, something is wrong

    selected_genres = context.user_data.get("cm_selected_genres", [])
    if full_genre_name in selected_genres:
        selected_genres.remove(full_genre_name)
    else:
        selected_genres.append(full_genre_name)
    context.user_data["cm_selected_genres"] = selected_genres

    genres_kb = build_genre_selection_keyboard(selected_genres)
    anime_title = context.user_data["cm_anime_data"].get("title_english", "this anime")
    await query.edit_message_text(
        text=strings.CM_PROMPT_SELECT_GENRES.format(anime_title=anime_title) + f"\n\n<i>Selected: {', '.join(selected_genres) if selected_genres else 'None'}</i>",
        reply_markup=genres_kb,
        parse_mode=ParseMode.HTML)
    return CM_ADD_ANIME_GENRES # Stay in genre selection state

# Done Selecting Genres, Move to Status
async def cm_genres_done_select_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    selected_genres = context.user_data.get("cm_selected_genres", [])
    if not selected_genres:
        await query.answer("Please select at least one genre.", show_alert=True)
        # Resend genre selection (or just do nothing and wait for user to click done with selections)
        # For simplicity, if they click done without selection, we let it proceed to status, and they can cancel/restart
        # Better: keep them in genre selection until at least one is picked or they explicitly skip genres.
        # For now, allowing no genres to be selected.
        pass

    context.user_data["cm_anime_data"]["genres"] = selected_genres
    logger.info(f"CM: Selected genres: {selected_genres}")

    # Prepare Status Selection
    status_buttons = []
    for status_val in settings.AVAILABLE_STATUSES:
        status_key = status_val.split(" ")[0]
        status_buttons.append([InlineKeyboardButton(status_val, callback_data=f"cm_status_select_{status_key}")])
    status_buttons.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")])
    
    anime_title = context.user_data["cm_anime_data"].get("title_english", "this anime")
    await query.edit_message_text(
        text=strings.CM_PROMPT_SELECT_STATUS.format(anime_title=anime_title),
        reply_markup=InlineKeyboardMarkup(status_buttons),
        parse_mode=ParseMode.HTML)
    return CM_ADD_ANIME_STATUS

# Receive Status Selection
async def cm_receive_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    status_key_selected = query.data.split("cm_status_select_", 1)[1]

    full_status_name = None
    for s_val in settings.AVAILABLE_STATUSES:
        if s_val.startswith(status_key_selected):
            full_status_name = s_val
            break

    if not full_status_name:
        logger.error(f"CM: Status key '{status_key_selected}' not found.")
        await query.answer("Invalid status selection. Please try again.", show_alert=True)
        return CM_ADD_ANIME_STATUS

    context.user_data["cm_anime_data"]["status"] = full_status_name
    logger.info(f"CM: Selected status: {full_status_name}")
    anime_title = context.user_data["cm_anime_data"].get("title_english", "this anime")
    await query.edit_message_text(
        text=strings.CM_PROMPT_RELEASE_YEAR.format(anime_title=anime_title),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")]]),
        parse_mode=ParseMode.HTML)
    return CM_ADD_ANIME_RELEASE_YEAR

# Receive Release Year
async def cm_receive_release_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        year_str = update.message.text.strip()
        if not (year_str.isdigit() and len(year_str) == 4 and 1900 < int(year_str) <= datetime.now().year + 5): # Basic validation
            raise ValueError
        year = int(year_str)
    except ValueError:
        await update.message.reply_html("Invalid year. Please enter a 4-digit year (e.g., 2023).")
        return CM_ADD_ANIME_RELEASE_YEAR

    context.user_data["cm_anime_data"]["release_year"] = year
    logger.info(f"CM: Received release_year: {year}")

    await update.message.reply_html(
        text=strings.CM_PROMPT_NUM_SEASONS,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")]]))
    return CM_ADD_ANIME_NUM_SEASONS

# Receive Number of Seasons and Finalize Anime Base Info
async def cm_receive_num_seasons_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        num_seasons_str = update.message.text.strip()
        num_seasons = int(num_seasons_str)
        if not (0 < num_seasons <= 50): # Max 50 seasons reasonable limit
             raise ValueError("Number of seasons out of range (1-50).")
    except ValueError:
        await update.message.reply_html("Invalid input. Please enter a number for seasons (e.g., 1 or 3).")
        return CM_ADD_ANIME_NUM_SEASONS

    logger.info(f"CM: Received num_seasons: {num_seasons}")

    # Prepare season structure
    seasons_data = []
    for i in range(1, num_seasons + 1):
        seasons_data.append({"season_number": i, "episodes": []}) # Initialize with empty episodes

    final_anime_data = context.user_data.get("cm_anime_data", {})
    final_anime_data["seasons"] = seasons_data
    final_anime_data["added_date"] = datetime.now(pytz.utc)
    final_anime_data["last_updated_date"] = datetime.now(pytz.utc) # For newly added anime
    final_anime_data["download_count"] = 0
    # Additional default fields: type (TV, Movie etc - could be asked earlier)
    # final_anime_data.setdefault("type", "TV") # Ask type if it's not same as status

    # --- SAVE TO DATABASE ---
    inserted_id = await anidb.add_anime(final_anime_data)

    if inserted_id:
        anime_title = final_anime_data.get("title_english", "The anime")
        success_msg = strings.CM_ANIME_ADDED_SUCCESS.format(anime_title=anime_title) + \
                      f"\nDatabase ID: <code>{inserted_id}</code>"
        
        # Store anime_id for next step (managing episodes)
        context.user_data["cm_current_anime_id"] = str(inserted_id) # Store as string
        context.user_data["cm_current_anime_title"] = anime_title
        context.user_data["cm_total_seasons_for_current_anime"] = num_seasons
        context.user_data["cm_current_season_num_managing"] = 1 # Start with season 1 for episode management

        # Options after saving base info
        keyboard = [
            [InlineKeyboardButton(f"🎬 Manage Episodes for S1", callback_data="cm_eps_manage_s1")],
            # [InlineKeyboardButton(f"✏️ Edit '{anime_title[:20]}…' Details", callback_data=f"cm_action_direct_modify_{inserted_id}")], # Modify this newly added
            [InlineKeyboardButton(f"{strings.EMOJI_UPLOAD} Add Another Anime", callback_data="cm_action_add_new")],
            [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="cm_action_cancel_main")]
        ]
        await update.message.reply_html(success_msg, reply_markup=InlineKeyboardMarkup(keyboard))
        # Clear specific anime data but keep current_anime_id etc. for episode management
        context.user_data.pop("cm_anime_data", None)
        context.user_data.pop("cm_selected_genres", None)
        return CM_MANAGE_SEASONS_FOR_ANIME # Go to state to manage this new anime's seasons/episodes

    else:
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Failed to save anime to database. Please check logs or try again.")
        # Go back to main CM menu or allow retry? For now, back to main.
        await manage_content_start(update, context) # This will clear cm_user_data
        return CM_MAIN_MENU


# --- === Episode Management Flow (Simplified stubs, needs full implementation) === ---
async def cm_start_episode_management_for_season(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    # Extract anime_id and season_num from callback_data (e.g., "cm_eps_manage_s{season_num}")
    # Or from context.user_data if it's set after adding anime
    anime_id = context.user_data.get("cm_current_anime_id")
    current_season_num = context.user_data.get("cm_current_season_num_managing", 1) # Default or from callback

    if query.data.startswith("cm_eps_manage_s"):
        try:
            current_season_num = int(query.data.split("cm_eps_manage_s")[1])
            context.user_data["cm_current_season_num_managing"] = current_season_num
        except:
            logger.error(f"CM: Failed to parse season number from callback: {query.data}")
            # Fallback or error

    if not anime_id:
        await query.edit_message_text(f"{strings.EMOJI_ERROR} No anime context found. Please select an anime first.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="cm_action_cancel_main")]]))
        return CM_MAIN_MENU

    anime_title = context.user_data.get("cm_current_anime_title", "Selected Anime")

    # Placeholder for episode management UI for this season
    text = f"Managing Episodes for <b>{anime_title} - Season {current_season_num}</b>.\nWhat do you want to do?"
    keyboard = [
        [InlineKeyboardButton(f"{strings.EMOJI_UPLOAD} Add New Episode", callback_data=f"cm_ep_add_new_{anime_id}_{current_season_num}")],
        # [InlineKeyboardButton(f"{EMOJI_LIST} View/Edit Episodes", callback_data=f"cm_ep_view_edit_{anime_id}_{current_season_num}")],
        # Add buttons for next/prev season for this anime
    ]
    total_seasons = context.user_data.get("cm_total_seasons_for_current_anime", 0)
    season_nav_row = []
    if current_season_num > 1:
        season_nav_row.append(InlineKeyboardButton(f"{strings.EMOJI_BACK} Prev Season (S{current_season_num-1})", callback_data=f"cm_eps_manage_s{current_season_num-1}"))
    if total_seasons > 0 and current_season_num < total_seasons:
        season_nav_row.append(InlineKeyboardButton(f"Next Season (S{current_season_num+1}) {strings.EMOJI_NEXT}", callback_data=f"cm_eps_manage_s{current_season_num+1}"))
    if season_nav_row:
        keyboard.append(season_nav_row)

    keyboard.append([InlineKeyboardButton("Done with this Anime's Episodes", callback_data="cm_eps_done_all_seasons")])
    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_main")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CM_MANAGE_EPISODES_FOR_SEASON


async def cm_prompt_add_episode_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    # Extract anime_id and season_num from callback f"cm_ep_add_new_{anime_id}_{current_season_num}"
    try:
        _, _, anime_id_str, season_num_str = query.data.split("_")
        context.user_data["cm_ep_current_anime_id"] = anime_id_str
        context.user_data["cm_ep_current_season_num"] = int(season_num_str)
        context.user_data["cm_ep_data"] = {} # For current episode being added
    except Exception as e:
        logger.error(f"Error parsing callback for add new episode: {query.data} - {e}")
        await query.edit_message_text("Error. Please try again.")
        return CM_MANAGE_SEASONS_FOR_ANIME # Go back a step

    anime_title = context.user_data.get("cm_current_anime_title", "")
    s_num = context.user_data["cm_ep_current_season_num"]
    await query.edit_message_text(
        text=strings.CM_EPISODE_PROMPT_NUM.format(season_num=s_num) + f" for {anime_title} S{s_num}.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to S{s_num} Menu", callback_data=f"cm_eps_manage_s{s_num}")]]))
    return CM_ADD_EPISODE_NUMBER

# ... more states for episode file details, similar to anime details flow ...
# ... (CM_ADD_EPISODE_FILE_OR_DATE, CM_ADD_EPISODE_SEND_FILE, RESOLUTION, AUDIO, SUB, RELEASE_DATE) ...
# ... These would collect details for `episode_doc` and then `anidb.add_episode_to_season()`
# ... or `anidb.add_file_version_to_episode()`


# --- Cancellation and Fallbacks ---
async def cm_cancel_sub_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels a sub-flow (like adding anime details) and returns to CM Main Menu."""
    query = update.callback_query
    if query: await query.answer()
    logger.info("CM: Sub-flow cancelled by admin.")
    # Clear cm_anime_data and cm_selected_genres from user_data
    clear_cm_user_data(context) # Clears all cm_ prefixed data
    
    # Go back to the main CM menu
    # Need to call manage_content_start to rebuild its message and buttons
    await manage_content_start(update, context)
    return CM_MAIN_MENU


async def cm_cancel_to_bot_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels entire Content Management and returns to bot's main menu."""
    query = update.callback_query
    if query: await query.answer()
    logger.info("CM: Entire Content Management cancelled by admin.")
    clear_cm_user_data(context)
    
    await reply_with_main_menu(update, context, message_text=strings.OPERATION_CANCELLED + " Content management exited.")
    return ConversationHandler.END


# --- Modify Anime (Very Basic Stubs) ---
async def cm_start_modify_anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚧 Modifying existing anime: Please enter the English title of the anime to modify:",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="cm_action_cancel_sub")]]))
    return CM_MODIFY_SELECT_ANIME

# Further modify states would be complex and similar in pattern to ADD.


# --- Conversation Handler Definition ---
def get_manage_content_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("manage_content", manage_content_start, filters=filters.User(settings.ADMIN_IDS)),
            CallbackQueryHandler(manage_content_start, pattern="^cm_admin_panel_manage_content$") # If from an admin panel
        ],
        states={
            CM_MAIN_MENU: [
                CallbackQueryHandler(cm_start_add_new_anime, pattern="^cm_action_add_new$"),
                CallbackQueryHandler(cm_start_modify_anime, pattern="^cm_action_modify_existing$"),
                # Add handler for delete action pattern
                CallbackQueryHandler(cm_cancel_to_bot_main_menu, pattern="^cm_action_cancel_main$")
            ],
            # Add New Anime Flow
            CM_ADD_ANIME_TITLE_ENG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_title_eng),
                CallbackQueryHandler(cm_retry_add_title_eng, pattern="^cm_retry_add_title_eng$"),
            ],
            CM_ADD_ANIME_POSTER: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), cm_receive_poster)],
            CM_ADD_ANIME_SYNOPSIS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_synopsis)],
            CM_ADD_ANIME_GENRES: [
                CallbackQueryHandler(cm_toggle_genre, pattern="^cm_genre_toggle_"),
                CallbackQueryHandler(cm_genres_done_select_status, pattern="^cm_genre_done$")
            ],
            CM_ADD_ANIME_STATUS: [CallbackQueryHandler(cm_receive_status, pattern="^cm_status_select_")],
            CM_ADD_ANIME_RELEASE_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_release_year)],
            CM_ADD_ANIME_NUM_SEASONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cm_receive_num_seasons_and_save)],

            # Episode Management (after new anime or modify)
            CM_MANAGE_SEASONS_FOR_ANIME: [ # This state can be entered after adding anime, or when modifying
                CallbackQueryHandler(cm_start_episode_management_for_season, pattern="^cm_eps_manage_s[0-9]+$"), # e.g. cm_eps_manage_s1
                CallbackQueryHandler(cm_start_add_new_anime, pattern="^cm_action_add_new$"), # Option to add another anime
                # cm_eps_done_all_seasons: if they are done with current anime, go back to CM_MAIN_MENU
                CallbackQueryHandler(manage_content_start, pattern="^cm_eps_done_all_seasons$")
            ],
            CM_MANAGE_EPISODES_FOR_SEASON: [ # Inside specific season management
                 CallbackQueryHandler(cm_prompt_add_episode_number, pattern="^cm_ep_add_new_"), # e.g. cm_ep_add_new_ANIMEID_SEASONNUM
                 CallbackQueryHandler(cm_start_episode_management_for_season, pattern="^cm_eps_manage_s[0-9]+$"), # Back to season select (or this anime's other seasons)
            ],
            CM_ADD_EPISODE_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, None), # Placeholder: cm_receive_episode_number
                # Back button handler needs to go to previous relevant state (e.g. CM_MANAGE_EPISODES_FOR_SEASON)
            ],
            # ... Other episode states (files, dates, versions) ...

            # Modify Existing Anime Flow (stubs)
            CM_MODIFY_SELECT_ANIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, None)], # Placeholder: cm_receive_anime_to_modify_title

            # Universal cancel for sub-flows (within add/modify)
            # Add CallbackQueryHandler(cm_cancel_sub_flow, pattern="^cm_action_cancel_sub$") to applicable states
        },
        fallbacks=[
            # General cancel commands that can be used at most states
            CallbackQueryHandler(cm_cancel_to_bot_main_menu, pattern="^cm_action_cancel_main$"), # Typically from CM_MAIN_MENU
            CallbackQueryHandler(cm_cancel_sub_flow, pattern="^cm_action_cancel_sub$"), # From deep inside a flow
            CommandHandler("cancel_cm", cm_cancel_to_bot_main_menu, filters=filters.User(settings.ADMIN_IDS)) # Admin can type /cancel_cm
        ],
        persistent=False, # True if you want states to persist across bot restarts (requires persistence setup)
        name="content_management_conversation", # For debugging
        # per_user=True, per_chat=True, # Recommended for complex conversations
    )
