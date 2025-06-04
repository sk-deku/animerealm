from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified
import config
import strings
from utils.keyboard_utils import (
    get_browse_main_keyboard, get_az_picker_keyboard, get_genre_picker_keyboard,
    get_status_picker_keyboard, paginate_keyboard, get_anime_detail_keyboard,
    get_seasons_list_keyboard, get_episodes_list_keyboard, get_episode_versions_keyboard
)
from database.operations import (
    get_animes_by_filter, get_anime_by_id, get_seasons_for_anime, 
    get_episodes_for_season, is_in_watchlist, get_episode_versions, 
    get_season_by_id, get_newly_added_animes_or_episodes, get_popular_animes
)
from database.connection import db
from utils.logger import log_bot_event
from utils.logger import LOGGER

# Main Browse Menu
@Client.on_message(filters.command("browse"))
@Client.on_callback_query(filters.regex("^browse_main$"))
async def browse_main_handler(client: Client, message_or_cb):
    if isinstance(message_or_cb, Message):
        await message_or_cb.reply_text(strings.BROWSE_MAIN_TEXT, reply_markup=get_browse_main_keyboard())
    else: # CallbackQuery
        try:
            await message_or_cb.edit_message_text(strings.BROWSE_MAIN_TEXT, reply_markup=get_browse_main_keyboard())
        except MessageNotModified:
            # If the message is already what we want it to be, just pass/answer
            pass 
        except Exception as e:
            # Log other potential errors during edit
            LOGGER.error(f"Error editing message in browse_main_handler: {e}")
            # Optionally, send a new message as a fallback if edit fails critically
            await message_or_cb.message.reply_text(strings.BROWSE_MAIN_TEXT, reply_markup=get_browse_main_keyboard())
        finally:
            await message_or_cb.answer() # Always answer the callback

# A-Z Picker
@Client.on_callback_query(filters.regex(r"^browse_az_picker$"))
async def browse_az_picker_handler(client: Client, cb: CallbackQuery):
    await cb.edit_message_text(strings.BROWSE_AZ_TEXT, reply_markup=get_az_picker_keyboard())
    await cb.answer()

# Genre Picker
@Client.on_callback_query(filters.regex(r"^browse_genre_picker_page_(\d+)$"))
async def browse_genre_picker_handler(client: Client, cb: CallbackQuery):
    page = int(cb.matches[0].group(1))
    await cb.edit_message_text(strings.BROWSE_GENRE_TEXT, reply_markup=get_genre_picker_keyboard(page))
    await cb.answer()

# Status Picker
@Client.on_callback_query(filters.regex(r"^browse_status_picker$"))
async def browse_status_picker_handler(client: Client, cb: CallbackQuery):
    await cb.edit_message_text(strings.BROWSE_STATUS_TEXT, reply_markup=get_status_picker_keyboard())
    await cb.answer()

# Year Picker (Simplified: just text for now, can expand to season buttons later)
@Client.on_callback_query(filters.regex(r"^browse_year_picker$"))
async def browse_year_picker_handler(client: Client, cb: CallbackQuery):
    await cb.edit_message_text(strings.BROWSE_YEAR_TEXT) # User needs to type /browsebyyear YYYY
    await cb.answer("Type /browsebyyear YYYY to filter by year.", show_alert=True)


# LISTING ANIME (Generic handler for A-Z, Genre, Status list pages)
@Client.on_callback_query(filters.regex(r"^browse_(az_list_([A-Z#])|genre_list_([\w-]+)|status_list_([\w-]+))_page_(\d+)$"))
async def browse_list_animes_handler(client: Client, cb: CallbackQuery):
    filter_type_match = cb.matches[0].group(1) # az_list_X or genre_list_X or status_list_X
    page = int(cb.matches[0].group(5)) # The last \d+
    
    filter_dict = {}
    filter_value_display = ""
    base_cb_prefix = ""

    if "az_list_" in filter_type_match:
        letter = cb.matches[0].group(2)
        filter_dict['letter'] = letter
        filter_value_display = f"starting with '{letter}'"
        base_cb_prefix = f"browse_az_list_{letter}"
    elif "genre_list_" in filter_type_match:
        genre_slug = cb.matches[0].group(3)
        genre = genre_slug.replace('-', ' ') # Revert slug
        filter_dict['genre'] = genre
        filter_value_display = f"in genre '{genre}'"
        base_cb_prefix = f"browse_genre_list_{genre_slug}"
    elif "status_list_" in filter_type_match:
        status_slug = cb.matches[0].group(4)
        status = status_slug.replace('-', ' ')
        filter_dict['status'] = status
        filter_value_display = f"with status '{status}'"
        base_cb_prefix = f"browse_status_list_{status_slug}"

    animes, total_animes = await get_animes_by_filter(
        filter_dict, page, config.ITEMS_PER_PAGE
    )

    if not animes and page == 1:
        await cb.edit_message_text(
            strings.BROWSE_NO_ANIME_FOR_FILTER + f" ({filter_value_display})",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Browse", callback_data="browse_main")]])
        )
        await cb.answer()
        return

    items_data = []
    for anime in animes:
        items_data.append({
            'text': anime.get('title', 'Unknown Anime'),
            'callback_data': f"view_anime:{str(anime['_id'])}"
        })
    
    kb = paginate_keyboard(
        items_data, page, config.ITEMS_PER_PAGE, total_animes, base_cb_prefix,
        extra_buttons_bottom=[[InlineKeyboardButton("⬅️ Back to Browse Options", callback_data="browse_main")]],
        items_per_row=1
    )
    
    await cb.edit_message_text(
        f"Anime {filter_value_display} (Page {page}):",
        reply_markup=kb
    )
    await cb.answer()

# --- View Anime Details & Navigate Seasons/Episodes (common, can be called from search too) ---
@Client.on_callback_query(filters.regex(r"^view_anime:(\w+)$"))
async def view_anime_details_handler(client: Client, cb: CallbackQuery):
    anime_id_str = cb.matches[0].group(1)
    anime = await get_anime_by_id(anime_id_str)

    if not anime:
        await cb.answer("Anime not found.", show_alert=True)
        await cb.message.delete() # Or edit to an error
        return

    user_id = cb.from_user.id
    in_watchlist = await is_in_watchlist(user_id, anime['_id'])

    poster = anime.get('poster_url')
    caption = strings.ANIME_DETAIL_TEXT.format(
        title=anime.get('title', 'N/A'),
        year=anime.get('year', 'N/A'),
        status=anime.get('status', 'N/A'),
        original_title=anime.get('original_title', 'N/A'),
        genres=', '.join(anime.get('genres', [])),
        synopsis=anime.get('synopsis', 'N/A')
    )
    reply_markup = get_anime_detail_keyboard(anime, in_watchlist)

    # Editing logic for photo/text
    current_message_is_photo = bool(cb.message.photo)
    target_message_is_photo = bool(poster)
    try:
        if current_message_is_photo == target_message_is_photo:
            if target_message_is_photo:
                if cb.message.photo.file_id != poster: # If poster URL changed, re-send media
                    await cb.edit_message_media(InputMediaPhoto(media=poster, caption=caption), reply_markup=reply_markup)
                else: # Just edit caption
                    await cb.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            else: # Text to Text
                await cb.edit_message_text(text=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        elif target_message_is_photo and not current_message_is_photo: # Text to Photo
            await cb.message.delete()
            await client.send_photo(cb.message.chat.id, photo=poster, caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        elif not target_message_is_photo and current_message_is_photo: # Photo to Text
             await cb.message.delete()
             await client.send_message(cb.message.chat.id, text=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        await log_bot_event(client, f"Error viewing anime {anime_id_str}: {e}. Sending new.")
        # Fallback to sending new message
        if poster:
            await cb.message.reply_photo(photo=poster, caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            await cb.message.reply_text(caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^list_seasons_A:(\w+)$"))
async def list_seasons_for_anime_handler(client: Client, cb: CallbackQuery):
    anime_id_str = cb.matches[0].group(1)
    anime = await get_anime_by_id(anime_id_str)
    if not anime:
        await cb.answer("Anime not found.", show_alert=True); return

    seasons = await get_seasons_for_anime(anime['_id'])
    text = f"<b>{anime['title']}</b> - Seasons:\n"
    if not seasons:
        text += "\n" + strings.NO_SEASONS_TEXT
    
    kb = get_seasons_list_keyboard(seasons, anime_id_str)
    await cb.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^les_S:(?P<S_ID>\w+)_p(?P<PAGE>\d+)$"))
async def list_episodes_for_season_handler(client: Client, cb: CallbackQuery):
    LOGGER.info(f"LIST_EPISODES_HANDLER TRIGGERED! Callback data: {cb.data}")
    
    season_id_str = cb.matches[0].group("S_ID")
    page = int(cb.matches[0].group("PAGE"))

    season = await get_season_by_id(season_id_str)
    if not season:
        await cb.answer("Season not found.", show_alert=True)
        try: await cb.message.delete()
        except: pass
        return

    # CORRECTLY GET ANIME_ID FROM THE SEASON DOCUMENT
    anime_object_id_from_season = season.get('anime_id') # This is an ObjectId
    if not anime_object_id_from_season:
        await cb.answer("Critical error: Season document is missing anime_id.", show_alert=True)
        LOGGER.error(f"Season doc {season_id_str} is missing anime_id: {season}")
        return
    
    anime_id_str = str(anime_object_id_from_season) # Convert ObjectId to string for use

    anime = await get_anime_by_id(anime_id_str) # Fetch anime using the retrieved ID
    if not anime:
        await cb.answer("Associated Anime not found.", show_alert=True)
        LOGGER.error(f"Could not find anime with ID {anime_id_str} from season {season_id_str}")
        return
    
    episodes, total_episodes = await get_episodes_for_season(season['_id'], page, config.ITEMS_PER_PAGE)
    
    season_title_disp = season.get('title', f"Season {season['season_number']}")
    text = strings.SEASON_EPISODES_TEXT.format(anime_title=anime['title'], season_number=season_title_disp)
    
    final_kb = None # Initialize keyboard variable
    if not episodes and page == 1:
        text += "\n\n" + strings.NO_EPISODES_IN_SEASON_TEXT
        final_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Seasons", callback_data=f"list_seasons_A:{anime_id_str}")]])
    else:
        final_kb = get_episodes_list_keyboard(
            episodes, page, total_episodes, config.ITEMS_PER_PAGE, 
            anime_id_str, # Pass the correctly retrieved anime_id_str
            season_id_str, 
            season['season_number']
        )

    if not final_kb: # Safety net if keyboard generation somehow fails
        final_kb = InlineKeyboardMarkup([[InlineKeyboardButton("Error loading episodes.", callback_data="noop")]])
        LOGGER.error(f"Keyboard generation failed in list_episodes_for_season_handler for S:{season_id_str} A:{anime_id_str}")

    try:
        await cb.edit_message_text(text, reply_markup=final_kb, parse_mode=ParseMode.HTML)
    except MessageNotModified:
        LOGGER.info(f"MessageNotModified in list_episodes_for_season for S:{season_id_str} A:{anime_id_str}")
        pass
    except Exception as e:
        LOGGER.error(f"Error editing message in list_episodes_for_season: {e}", exc_info=True)
        # Fallback reply
        await cb.message.reply_text("Could not load episodes. Please try navigating back.")
    finally:
        await cb.answer()


@Client.on_callback_query(filters.regex(r"^view_ep_versions_A:(?P<A_ID>\w+)_SN:(?P<S_NUM>\d+)_EN:(?P<E_NUM>\d+)$"))
async def view_episode_versions_handler(client: Client, cb: CallbackQuery):
    LOGGER.info(f"VIEW_EP_VERSIONS_HANDLER TRIGGERED! Callback data: {cb.data}")
    anime_id_str = cb.matches[0].group("A_ID")
    season_number = int(cb.matches[0].group("S_NUM"))
    episode_number = int(cb.matches[0].group("E_NUM"))

    anime = await get_anime_by_id(anime_id_str)
    if not anime: 
        await cb.answer("Anime not found.", True)
        try: await cb.message.delete()
        except: pass
        return

    versions = await get_episode_versions(anime['_id'], season_number, episode_number)

    # Find the season_id to pass for the "Back to Episodes" button
    season_doc = await db.seasons.find_one({'anime_id': anime['_id'], 'season_number': season_number})
    season_id_for_back_button = str(season_doc['_id']) if season_doc else None

    if not versions:
        no_files_text = "No downloadable files found for this episode."
        no_files_kb_buttons = []
        if season_id_for_back_button:
            no_files_kb_buttons.append([InlineKeyboardButton("⬅️ Back to Episodes", callback_data=f"les_S:{season_id_for_back_button}_p1")])
        else: # Fallback if season somehow not found
            no_files_kb_buttons.append([InlineKeyboardButton("⬅️ Back to Seasons", callback_data=f"list_seasons_A:{anime_id_str}")])
        no_files_kb_buttons.append([InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")])
        
        try:
            await cb.edit_message_text(no_files_text, reply_markup=InlineKeyboardMarkup(no_files_kb_buttons))
        except MessageNotModified: pass
        except Exception as e: LOGGER.error(f"Error editing for no versions: {e}")
        await cb.answer("No files available.", show_alert=True)
        return

    ep_title_display = versions[0].get('episode_title', f"Episode {episode_number}")
    
    text = strings.EPISODE_VERSIONS_TEXT.format(
        anime_title=anime['title'], s_num=season_number, e_num=episode_number, ep_title=ep_title_display
    )
    
    kb = get_episode_versions_keyboard(versions, anime_id_str, season_id_for_back_button)
    
    try:
        await cb.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except MessageNotModified: pass
    except Exception as e: LOGGER.error(f"Error editing for episode versions: {e}")
    await cb.answer()

# New Episodes & Popular (Simplified List View)
@Client.on_callback_query(filters.regex(r"^(new_episodes_list|popular_animes_list)$"))
async def new_popular_list_handler(client: Client, cb: CallbackQuery):
    list_type = cb.data.split('_list')[0] # new_episodes or popular_animes
    
    results = []
    text_header = ""

    if list_type == "new_episodes":
        # This currently returns episodes with anime_info populated
        raw_results = await get_newly_added_animes_or_episodes(limit=20, type="episodes")
        text_header = "🆕 Recently Added Episodes:"
        for item in raw_results:
            anime_title = item['anime_info'].get('title', 'Unknown Anime')
            ep_title = item.get('episode_title', f"Ep {item['episode_number']}")
            # To make it clickable, need a way to navigate to the episode version selection.
            # This means our `view_ep_versions` callback needs enough info or we create a direct view link.
            # For now, just display text. Proper nav is complex.
            results.append({
                'text': f"{anime_title} S{item['season_number']}E{item['episode_number']}: {ep_title} ({item['quality']} {item['audio_type']})",
                # CB: view_ep_versions_A:{anime_id}_SN:{s_num}_EN:{e_num}
                'callback_data': f"view_ep_versions_A:{str(item['anime_id'])}_SN:{item['season_number']}_EN:{item['episode_number']}"
            })

    elif list_type == "popular_animes":
        raw_results = await get_popular_animes(limit=10)
        text_header = "🌟 Popular Anime (by downloads):"
        for anime in raw_results:
            results.append({
                'text': f"{anime.get('title', 'N/A')} (DLs: {anime.get('download_count', 0)})",
                'callback_data': f"view_anime:{str(anime['_id'])}"
            })
            
    if not results:
        await cb.edit_message_text(f"No {list_type.replace('_',' ')} found at the moment.", 
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]]))
        await cb.answer()
        return
        
    # Using paginate_keyboard for consistency, even if not paginated yet for these simple lists
    kb = paginate_keyboard(results, 1, len(results), len(results), "noop_base", items_per_row=1,
                           extra_buttons_bottom=[[InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]])
    
    await cb.edit_message_text(text_header, reply_markup=kb)
    await cb.answer()
