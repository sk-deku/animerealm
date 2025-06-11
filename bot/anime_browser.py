# bot/anime_browser.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackQueryHandler # For internal navigation if not part of a conv.
from telegram.constants import ParseMode
from math import ceil # For calculating total pages

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance
from .core_handlers import check_user_or_add, reply_with_main_menu # For check and main menu button

logger = logging.getLogger(__name__)

# --- Helper to build pagination ---
def build_pagination_keyboard(current_page: int, total_pages: int, callback_data_prefix: str, extra_args: str = "") -> list:
    """
    Builds a row of pagination buttons.
    callback_data_prefix: e.g., "page_popular", "page_browse_genre_Action"
    extra_args: any additional static info needed in callback, prepended to page number
                e.g., if prefix is "page_browse_genre", extra_args could be "Action"
                so callback becomes "page_browse_genre_Action_{page_num}"
    """
    row = []
    if current_page > 1:
        row.append(InlineKeyboardButton(strings.BTN_PREVIOUS_PAGE, callback_data=f"{callback_data_prefix}{extra_args}_{current_page - 1}"))
    if current_page < total_pages:
        row.append(InlineKeyboardButton(strings.BTN_NEXT_PAGE, callback_data=f"{callback_data_prefix}{extra_args}_{current_page + 1}"))
    return row

# --- Display Anime Details, Seasons, Episodes, Versions (Core Display Logic) ---

async def display_anime_details_and_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_doc: dict, came_from_watchlist: bool = False):
    """
    Displays the core details of an anime and main action buttons.
    This will be called after an anime is selected from search, browse, watchlist etc.
    It will edit the existing message.
    """
    query = update.callback_query # This function is typically called from a callback

    user_db_doc = await check_user_or_add(update, context) # Ensure user is checked/added
    if not user_db_doc: return

    title = anime_doc.get("title_english", "N/A")
    synopsis = anime_doc.get("synopsis", "No synopsis available.")
    if len(synopsis) > 700: # Telegram caption/message limit for media is 1024. Keep synopsis shorter.
        synopsis = synopsis[:700] + "..."
    release_year = anime_doc.get("release_year", "N/A")
    status = anime_doc.get("status", "N/A")
    genres = ", ".join(anime_doc.get("genres", ["N/A"]))
    poster_file_id = anime_doc.get("poster_file_id", settings.ANIME_POSTER_PLACEHOLDER_URL) # Use placeholder if missing

    anime_id_str = str(anime_doc['_id'])

    text = strings.ANIME_DETAILS_MESSAGE.format(
        title_english=title,
        release_year=release_year,
        status=status,
        genres_list=genres,
        synopsis=synopsis
    )

    is_in_watchlist = anime_id_str in user_db_doc.get("watchlist", [])
    watchlist_button_text = strings.BTN_REMOVE_FROM_WATCHLIST if is_in_watchlist else strings.BTN_ADD_TO_WATCHLIST
    watchlist_callback = f"wl_rem_{anime_id_str}" if is_in_watchlist else f"wl_add_{anime_id_str}"

    keyboard_buttons = [
        [InlineKeyboardButton(strings.BTN_VIEW_SEASONS, callback_data=f"viewseasons_{anime_id_str}")],
        [InlineKeyboardButton(watchlist_button_text, callback_data=watchlist_callback)],
        [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")] # Or a more contextual back
    ]
    # Add a "Back to Search Results / Browse List" button if context available
    # e.g., context.user_data.get('came_from_search_query') or 'came_from_browse_genre'

    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    try:
        if poster_file_id and not poster_file_id.startswith("http"): # It's a Telegram file_id
            if query:
                # To change media, we need to delete and send new, or use edit_message_media if possible.
                # PTB's edit_message_media is a bit tricky with text+markup changes sometimes.
                # Simplest is to delete previous text message and send new with photo.
                await query.message.delete()
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=poster_file_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            else: # From a command (less likely for this function)
                 await update.message.reply_photo(
                    photo=poster_file_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                 )
        else: # URL or placeholder
            media = InputMediaPhoto(media=poster_file_id, caption=text, parse_mode=ParseMode.HTML)
            if query and query.message.photo: # If current message has a photo, try to edit media
                 await query.edit_message_media(media=media, reply_markup=reply_markup)
            elif query: # Current message is text, edit to photo
                 await query.message.delete() # Delete old text message
                 await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=poster_file_id, # Use original URL here
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                 )
            else: # From command
                await update.message.reply_photo(
                    photo=poster_file_id, # Use original URL here
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Error displaying anime details for {anime_id_str} (poster: {poster_file_id}): {e}", exc_info=True)
        # Fallback to text message if photo fails
        if query:
            try:
                await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            except Exception as e2:
                 logger.error(f"Fallback text display failed for {anime_id_str}: {e2}")
        elif update.message:
             await update.message.reply_html(text=text, reply_markup=reply_markup)


async def display_anime_seasons(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_doc: dict | None = None, anime_id_str: str | None = None):
    """Displays seasons for a selected anime. Edits the message."""
    query = update.callback_query
    if query: await query.answer()

    if not anime_doc and anime_id_str:
        anime_doc = await anidb.get_anime_by_id_str(anime_id_str)

    if not anime_doc:
        err_msg = f"{strings.EMOJI_ERROR} Could not retrieve anime details."
        if query: await query.edit_message_text(err_msg)
        else: await update.message.reply_html(err_msg)
        return

    anime_id_str_actual = str(anime_doc['_id']) # Ensure we use the actual _id string
    title = anime_doc.get("title_english", "N/A")
    seasons = anime_doc.get("seasons", [])

    if not seasons:
        msg = f"🎬 <b>{title}</b>\n\n{strings.EMOJI_INFO} No seasons or episodes found for this anime yet."
        kb = [[InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Anime Details", callback_data=f"viewanime_{anime_id_str_actual}")],
              [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]
        if query: await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        else: await update.message.reply_html(msg, reply_markup=InlineKeyboardMarkup(kb))
        return

    text = strings.SEASONS_LIST_PROMPT.format(anime_title=title, current_page=1, total_pages=1) # Simple pagination for now if many seasons
    
    buttons = []
    row = []
    for season in sorted(seasons, key=lambda s: s.get("season_number", 0)):
        s_num = season.get("season_number", "N/A")
        # Callback "viewepisodes_{anime_id}_{season_num}"
        row.append(InlineKeyboardButton(f"{strings.BTN_SEASON_PREFIX}{s_num}", callback_data=f"vieweps_{anime_id_str_actual}_{s_num}"))
        if len(row) >= settings.SEASON_LIST_BUTTONS_PER_ROW:
            buttons.append(row)
            row = []
    if row: # Add remaining buttons
        buttons.append(row)

    buttons.append([InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Anime Details", callback_data=f"viewanime_{anime_id_str_actual}")])
    buttons.append([InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")])
    reply_markup = InlineKeyboardMarkup(buttons)

    if query:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else: # Should ideally be from a callback
        await update.message.reply_html(text=text, reply_markup=reply_markup)


async def display_season_episodes(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_id_str: str, season_num: int):
    """Displays episodes for a selected season. Edits the message."""
    query = update.callback_query
    if query: await query.answer()

    anime_doc = await anidb.get_anime_by_id_str(anime_id_str)
    if not anime_doc:
        err_msg = f"{strings.EMOJI_ERROR} Could not retrieve anime details."
        if query: await query.edit_message_text(err_msg)
        else: await update.message.reply_html(err_msg)
        return

    title = anime_doc.get("title_english", "N/A")
    selected_season = None
    for s in anime_doc.get("seasons", []):
        if s.get("season_number") == season_num:
            selected_season = s
            break

    if not selected_season or not selected_season.get("episodes"):
        msg = f"🎞️ <b>{title} - Season {season_num}</b>\n\n{strings.EMOJI_INFO} No episodes found for this season yet."
        kb = [[InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Seasons", callback_data=f"viewseasons_{anime_id_str}")],
              [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]
        if query: await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        else: await update.message.reply_html(msg, reply_markup=InlineKeyboardMarkup(kb))
        return

    # Basic pagination for episodes could be added here if a season has >50-100 episodes
    episodes = sorted(selected_season.get("episodes", []), key=lambda e: e.get("episode_number", 0))
    text = strings.EPISODES_LIST_PROMPT.format(anime_title=title, season_num=season_num, current_page=1, total_pages=1)

    buttons = []
    row = []
    for episode in episodes:
        ep_num = episode.get("episode_number", "N/A")
        ep_name = strings.EPISODE_ENTRY_FORMAT.format(ep_num=f"{ep_num:02d}") # Ensures EP 01, EP 02 etc.
        
        # Check for air date if no versions
        if not episode.get("versions") and episode.get("air_date"):
            air_date_obj = episode["air_date"]
            if isinstance(air_date_obj, datetime): # Ensure it's a datetime object
                 # Format date. If timezone aware, convert, else assume UTC.
                air_date_str = air_date_obj.strftime("%d %b %Y") if air_date_obj else "TBA"
                ep_name += strings.EPISODE_AIR_DATE_NOTICE.format(air_date=air_date_str)
            else: # If air_date is string "TBA"
                ep_name += strings.EPISODE_AIR_DATE_NOTICE.format(air_date="TBA")

        elif not episode.get("versions") and not episode.get("air_date"):
             ep_name += strings.EPISODE_NOT_YET_ANNOUNCED


        # Callback "viewvers_{anime_id}_{s_num}_{ep_num}"
        row.append(InlineKeyboardButton(ep_name, callback_data=f"viewvers_{anime_id_str}_{season_num}_{ep_num}"))
        if len(row) >= settings.EPISODE_LIST_BUTTONS_PER_ROW:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Seasons", callback_data=f"viewseasons_{anime_id_str}")])
    buttons.append([InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")])
    reply_markup = InlineKeyboardMarkup(buttons)

    if query:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text=text, reply_markup=reply_markup)


async def display_episode_versions(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_id_str: str, season_num: int, episode_num: int):
    """Displays file versions for a selected episode. Edits the message."""
    query = update.callback_query
    if query: await query.answer()
    
    user_db_doc = await check_user_or_add(update, context) # For premium check
    if not user_db_doc: return

    is_premium_user = user_db_doc.get("premium_status", False)

    anime_doc = await anidb.get_anime_by_id_str(anime_id_str)
    if not anime_doc:
        # handle error
        return

    title = anime_doc.get("title_english", "N/A")
    selected_episode_data = None
    for s in anime_doc.get("seasons", []):
        if s.get("season_number") == season_num:
            for ep in s.get("episodes", []):
                if ep.get("episode_number") == episode_num:
                    selected_episode_data = ep
                    break
            break
    
    if not selected_episode_data or not selected_episode_data.get("versions"):
        air_date_notice = ""
        if selected_episode_data and selected_episode_data.get("air_date"):
            air_date_obj = selected_episode_data["air_date"]
            if isinstance(air_date_obj, datetime):
                 air_date_str = air_date_obj.strftime("%d %b %Y") if air_date_obj else "TBA"
                 air_date_notice = strings.EPISODE_AIR_DATE_NOTICE.format(air_date=air_date_str)
            else:
                 air_date_notice = strings.EPISODE_AIR_DATE_NOTICE.format(air_date="TBA")

        elif selected_episode_data and not selected_episode_data.get("air_date"):
            air_date_notice = strings.EPISODE_NOT_YET_ANNOUNCED


        msg = f"💾 <b>{title} - S{season_num}EP{episode_num:02d}</b>\n\n{strings.EMOJI_INFO} No download versions available for this episode yet. {air_date_notice}"
        kb = [[InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Episodes", callback_data=f"vieweps_{anime_id_str}_{season_num}")],
              [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]
        if query: await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        else: await update.message.reply_html(msg, reply_markup=InlineKeyboardMarkup(kb))
        return

    premium_note = strings.PREMIUM_RESOLUTION_NOTE_PREMIUM_USER if is_premium_user else strings.PREMIUM_RESOLUTION_NOTE_FREE_USER
    text = strings.VERSIONS_LIST_PROMPT.format(anime_title=title, season_num=season_num, episode_num=f"{episode_num:02d}", premium_resolution_note=premium_note)

    buttons = []
    versions = sorted(selected_episode_data.get("versions", []), key=lambda v: settings.SUPPORTED_RESOLUTIONS.index(v.get("resolution", "0p")) if v.get("resolution") in settings.SUPPORTED_RESOLUTIONS else 99) # Sort by resolution order

    for idx, version in enumerate(versions):
        res = version.get("resolution", "N/A")
        audio = version.get("audio_language", "").split(" ")[0] # Get first word e.g. Japanese
        sub = version.get("subtitle_language", "").split(" ")[0]
        size_bytes = version.get("file_size_bytes", 0)
        size_mb = round(size_bytes / (1024 * 1024), 1) if size_bytes else "N/A"

        button_text = strings.VERSION_BUTTON_FORMAT.format(resolution=res, audio_lang=audio, sub_lang=sub, file_size_mb=size_mb)
        
        # Callback: "dl_{anime_id_str}_{s_num}_{ep_num}_{version_index_in_db_array}"
        # Storing version_idx is okay if array order is stable. Or store file_id of version.
        # Let's use version_idx for simplicity. `downloads.py` will use this index to get file_id.
        dl_callback = f"dl_{anime_id_str}_{season_num}_{episode_num}_{idx}"

        # Restrict download if free user and resolution is premium only
        can_download = True
        if not is_premium_user and res in settings.PREMIUM_ONLY_RESOLUTIONS:
            button_text = f"👑 {button_text} (Premium)"
            # Make button link to /premium info instead of download
            dl_callback = "core_premium_info" # Redirects to premium info
            can_download = False # Though not strictly needed if callback changed

        buttons.append([InlineKeyboardButton(button_text, callback_data=dl_callback)])


    buttons.append([InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Episodes (S{season_num})", callback_data=f"vieweps_{anime_id_str}_{season_num}")])
    buttons.append([InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")])
    reply_markup = InlineKeyboardMarkup(buttons)

    if query:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text=text, reply_markup=reply_markup)


# --- Generic List Display with Pagination ---
async def display_generic_anime_list(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                     anime_docs: list, total_count: int, current_page: int,
                                     header_text_template: str, callback_data_prefix_for_pagination: str,
                                     list_identifier_for_pagination: str = "", # e.g. Genre name, status name
                                     empty_list_message: str = "No anime found for this selection.",
                                     back_button_cb: str = "core_main_menu",
                                     back_button_text: str = strings.BTN_BACK_TO_MAIN_MENU):
    """
    A generic function to display a paginated list of anime.
    `header_text_template` should accept {current_page}, {total_pages}.
    `callback_data_prefix_for_pagination` is like "page_popular" or "page_browse_genre".
    `list_identifier_for_pagination` is added if needed, like "Action" for genre, making it "page_browse_genre_Action".
    """
    query = update.callback_query
    if query: await query.answer()

    if not anime_docs and current_page == 1:
        keyboard = [[InlineKeyboardButton(f"{strings.EMOJI_BACK} Back", callback_data=back_button_cb)]]
        if query : await query.edit_message_text(text=empty_list_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        else: await update.message.reply_html(text=empty_list_message, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    total_pages = ceil(total_count / settings.RESULTS_PER_PAGE_GENERAL)
    header = header_text_template.format(current_page=current_page, total_pages=total_pages)

    buttons = []
    for anime in anime_docs:
        title = anime.get("title_english", "N/A")[:50] # Truncate
        if len(anime.get("title_english", "")) > 50: title += "..."
        anime_id_str = str(anime['_id'])
        # Callback to view this specific anime: "viewanime_{anime_id}"
        buttons.append([InlineKeyboardButton(f"{strings.EMOJI_TV if anime.get('type') != 'Movie' else strings.EMOJI_MOVIE} {title}", callback_data=f"viewanime_{anime_id_str}")])

    pagination_row = build_pagination_keyboard(current_page, total_pages, callback_data_prefix_for_pagination, extra_args=f"_{list_identifier_for_pagination}" if list_identifier_for_pagination else "")
    if pagination_row:
        buttons.append(pagination_row)

    buttons.append([InlineKeyboardButton(back_button_text, callback_data=back_button_cb)])
    reply_markup = InlineKeyboardMarkup(buttons)

    # Editing the message (common case for browse, popular, latest flows)
    target_message = query.message if query else update.message
    try:
        if query:
            await query.edit_message_text(text=header, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else: # Direct command
            await target_message.reply_html(text=header, reply_markup=reply_markup)
    except Exception as e:
        logger.debug(f"Error editing message for generic list: {e}")
        if query: await query.answer()


# --- Browse Command Handlers ---
async def browse_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the browse flow: asks to browse by Genre or Status."""
    query = update.callback_query
    if query: await query.answer()

    await check_user_or_add(update, context) # Ensure user is known

    keyboard = [
        [InlineKeyboardButton(strings.BTN_BROWSE_BY_GENRE, callback_data="browse_select_genre_init")],
        [InlineKeyboardButton(strings.BTN_BROWSE_BY_STATUS, callback_data="browse_select_status_init")],
        [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = strings.BROWSE_MAIN_PROMPT

    if query:
        await query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text=msg_text, reply_markup=reply_markup)

async def browse_select_genre_init(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> None:
    """Displays genres for selection (paginated if many genres)."""
    query = update.callback_query
    if query: await query.answer()
    
    # Simple pagination for genres themselves if settings.AVAILABLE_GENRES is huge.
    # For now, let's assume it fits on one reasonable display. If not, this needs pagination for genres list.
    genres = settings.AVAILABLE_GENRES
    
    # Let's add pagination for genres just in case it becomes very long.
    per_page = 15 # Genres per page
    total_genres = len(genres)
    total_pages = ceil(total_genres / per_page)
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    genres_to_display = genres[start_index:end_index]


    text = strings.BROWSE_SELECT_GENRE.format(current_page=page, total_pages=total_pages)
    buttons = []
    row = []
    for genre in genres_to_display:
        # Callback "browse_genre_GENRENAME"
        row.append(InlineKeyboardButton(genre, callback_data=f"br_genre_{genre.split(' ')[0]}")) # Use first word of genre as key
        if len(row) >= settings.GENRE_BUTTONS_PER_ROW:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    pagination_cb_prefix = "br_sel_genre_page" # Callback for genre list pagination
    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(strings.BTN_PREVIOUS_PAGE, callback_data=f"{pagination_cb_prefix}_{page-1}"))
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(strings.BTN_NEXT_PAGE, callback_data=f"{pagination_cb_prefix}_{page+1}"))
    if pagination_row:
        buttons.append(pagination_row)


    buttons.append([InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Browse Options", callback_data="core_browse")])
    reply_markup = InlineKeyboardMarkup(buttons)
    if query: await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else: await update.message.reply_html(text=text, reply_markup=reply_markup)


async def browse_by_genre_results(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_genre: str | None = None, page_to_display: int = 1):
    """Displays anime for the selected genre."""
    query = update.callback_query
    if query: await query.answer()

    if not selected_genre and query: # Genre from callback_data
        selected_genre_key = query.data.split("br_genre_",1)[1]
        # Find the full genre name from settings using the key (first word)
        for g_full in settings.AVAILABLE_GENRES:
            if g_full.startswith(selected_genre_key):
                selected_genre = g_full
                break
        if not selected_genre:
             logger.error(f"Could not map genre key {selected_genre_key} back to full genre name.")
             await query.edit_message_text("Error finding that genre. Please try again.")
             return


    anime_docs, total_count = await anidb.get_animes_by_filter(
        filter_criteria={"genres": selected_genre},
        page=page_to_display,
        per_page=settings.RESULTS_PER_PAGE_GENERAL,
        sort_by=[("title_english", 1)]
    )
    await display_generic_anime_list(
        update, context, anime_docs, total_count, page_to_display,
        header_text_template=strings.BROWSE_RESULTS_HEADER.format(category_name=f"Genre: {selected_genre}", current_page="{current_page}", total_pages="{total_pages}"),
        callback_data_prefix_for_pagination="page_browse_genre",
        list_identifier_for_pagination=selected_genre.split(' ')[0], # Pass key for callback
        empty_list_message=f"No anime found in genre: <b>{selected_genre}</b>.",
        back_button_cb="browse_select_genre_init", # Back to genre selection
        back_button_text=f"{strings.EMOJI_BACK} Back to Genres"
    )

async def browse_select_status_init(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int =1) -> None:
    """Displays statuses for selection."""
    query = update.callback_query
    if query: await query.answer()
    
    statuses = settings.AVAILABLE_STATUSES
    text = strings.BROWSE_SELECT_STATUS.format(current_page=1, total_pages=1) # Statuses usually few
    buttons = []
    for status_val in statuses:
        # Callback "browse_status_STATUSNAME"
        buttons.append([InlineKeyboardButton(status_val, callback_data=f"br_status_{status_val.split(' ')[0]}")]) # Use first word

    buttons.append([InlineKeyboardButton(f"{strings.EMOJI_BACK} Back to Browse Options", callback_data="core_browse")])
    reply_markup = InlineKeyboardMarkup(buttons)
    if query: await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else: await update.message.reply_html(text=text, reply_markup=reply_markup)


async def browse_by_status_results(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_status: str | None = None, page_to_display: int = 1):
    """Displays anime for the selected status."""
    query = update.callback_query
    if query: await query.answer()

    if not selected_status and query:
        selected_status_key = query.data.split("br_status_",1)[1]
        for s_full in settings.AVAILABLE_STATUSES:
            if s_full.startswith(selected_status_key):
                selected_status = s_full
                break
        if not selected_status:
             logger.error(f"Could not map status key {selected_status_key} back to full status name.")
             await query.edit_message_text("Error finding that status. Please try again.")
             return

    anime_docs, total_count = await anidb.get_animes_by_filter(
        filter_criteria={"status": selected_status},
        page=page_to_display,
        per_page=settings.RESULTS_PER_PAGE_GENERAL,
        sort_by=[("title_english", 1)]
    )
    await display_generic_anime_list(
        update, context, anime_docs, total_count, page_to_display,
        header_text_template=strings.BROWSE_RESULTS_HEADER.format(category_name=f"Status: {selected_status}", current_page="{current_page}", total_pages="{total_pages}"),
        callback_data_prefix_for_pagination="page_browse_status",
        list_identifier_for_pagination=selected_status.split(' ')[0],
        empty_list_message=f"No anime found with status: <b>{selected_status}</b>.",
        back_button_cb="browse_select_status_init",
        back_button_text=f"{strings.EMOJI_BACK} Back to Statuses"
    )

# --- /popular and /latest Command Handlers ---
async def popular_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE, page_to_display: int = 1) -> None:
    await check_user_or_add(update, context)
    anime_docs, total_count = await anidb.get_popular_animes(page=page_to_display, per_page=settings.RESULTS_PER_PAGE_GENERAL)
    await display_generic_anime_list(
        update, context, anime_docs, total_count, page_to_display,
        header_text_template=strings.POPULAR_ANIME_HEADER,
        callback_data_prefix_for_pagination="page_popular",
        empty_list_message="Looks like nothing is popular right now!",
        back_button_cb="core_main_menu"
    )

async def latest_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE, page_to_display: int = 1) -> None:
    """
    Displays 'latest' anime. The definition of latest (new series vs new episodes)
    is determined by `anidb.get_latest_episodes_anime`.
    """
    await check_user_or_add(update, context)
    anime_docs, total_count = await anidb.get_latest_episodes_anime(page=page_to_display, per_page=settings.RESULTS_PER_PAGE_GENERAL)
    await display_generic_anime_list(
        update, context, anime_docs, total_count, page_to_display,
        header_text_template=strings.LATEST_UPDATES_HEADER,
        callback_data_prefix_for_pagination="page_latest",
        empty_list_message="No new updates found at the moment.",
        back_button_cb="core_main_menu"
    )
