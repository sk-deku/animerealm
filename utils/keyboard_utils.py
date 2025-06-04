from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any
import config
import strings # For button texts
from math import ceil
from bson import ObjectId # Important for callback data with ObjectIds
from utils.logger import LOGGER 

def get_skip_button(callback_data_for_skip_action: str):
    return InlineKeyboardButton("↪️ Skip this step", callback_data=callback_data_for_skip_action)
  
def paginate_keyboard(items: List[Dict[str, Any]], # Each item is dict with 'text' and 'callback_data'
                      page: int, 
                      per_page: int, 
                      total_items: int, 
                      base_callback_prefix: str,
                      extra_buttons_top: List[List[InlineKeyboardButton]] = None,
                      extra_buttons_bottom: List[List[InlineKeyboardButton]] = None,
                      items_per_row: int = 2):
    keyboard = []
    if extra_buttons_top:
        keyboard.extend(extra_buttons_top)

    if items:
        row = []
        for i, item in enumerate(items):
            row.append(InlineKeyboardButton(item['text'], callback_data=item['callback_data']))
            if (i + 1) % items_per_row == 0 or i == len(items) - 1:
                keyboard.append(row)
                row = []
        
    # Pagination controls
    if total_items > per_page:
        nav_row = []
        total_pages = ceil(total_items / per_page)
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"{base_callback_prefix}_page_{page-1}"))
        
        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop")) # No operation

        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"{base_callback_prefix}_page_{page+1}"))
        
        if nav_row: # Only add if there are nav buttons
             keyboard.append(nav_row)

    if extra_buttons_bottom:
        keyboard.extend(extra_buttons_bottom)
        
    return InlineKeyboardMarkup(keyboard) if keyboard else None


def get_main_menu_keyboard(user_tokens: int = 0, is_premium: bool = False):
    # Dynamic button texts based on status
    earn_tokens_text = f"💰 Earn Tokens" if is_premium else f"💰 Earn Tokens ({user_tokens} owned)"
    request_anime_text = "🙏 Request Anime" + (" (P)" if not is_premium else "")

    keyboard = [
        [
            InlineKeyboardButton("🔍 Search Anime", callback_data="search_anime_prompt"),
            InlineKeyboardButton("📚 Browse Library", callback_data="browse_main"),
        ],
        [
            InlineKeyboardButton("🆕 New Episodes", callback_data="new_episodes_list"),
            InlineKeyboardButton("🌟 Popular Anime", callback_data="popular_animes_list"),
        ],
        [InlineKeyboardButton("📌 My Watchlist", callback_data="my_watchlist_page_1")],
        [InlineKeyboardButton(earn_tokens_text, callback_data="earn_tokens")],
        [
            InlineKeyboardButton("👑 Premium Access", callback_data="premium_info"),
            InlineKeyboardButton(request_anime_text, callback_data="request_anime_prompt"),
        ],
        [InlineKeyboardButton("⚙️ Settings", callback_data="user_settings")],
        [
            InlineKeyboardButton("📜 All Commands", callback_data="all_commands"),
            InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
            InlineKeyboardButton("ℹ️ About", callback_data="about_bot"),
        ],
        [
            InlineKeyboardButton("💬 Support", url=config.SUPPORT_LINK),
            InlineKeyboardButton("🔔 Updates", url=config.UPDATES_LINK)
        ],
    ]
    # Add admin panel button if user is admin
    # This check should ideally happen in the handler before sending,
    # but we can add a placeholder for it or check context here.
    # For now, let's assume this keyboard is generic and handler filters visibility
    return InlineKeyboardMarkup(keyboard)

def get_admin_panel_button(): # This is used conditionally by handlers
    return [InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel_main")]


def get_common_secondary_keyboard(back_callback="start_menu_cb"): # Changed cb name
    keyboard = [
        [
            InlineKeyboardButton("💬 Support", url=config.SUPPORT_LINK),
            InlineKeyboardButton("🔔 Updates", url=config.UPDATES_LINK)
        ],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data=back_callback)]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- TOKEN ---
def get_token_generation_keyboard():
    # ... (same as before, but callback leads to start_menu_cb)
    keyboard = [
        [InlineKeyboardButton(strings.TOKEN_LINK_TEXT, callback_data="generate_shortened_link")],
        [InlineKeyboardButton(strings.TOKEN_HOW_TO_BUTTON_TEXT, url=strings.TOKEN_HOW_TO_URL)],
        [InlineKeyboardButton("⬅️ Back", callback_data="start_menu_cb")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- DOWNLOAD ---
def get_download_confirmation_keyboard(episode_version_id: str | ObjectId): # Use episode version ID
    # Convert ObjectId to str for callback_data
    cb_data_id = str(episode_version_id)
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Download", callback_data=f"dl_confirm_yes:{cb_data_id}"),
            InlineKeyboardButton("❌ No, Cancel", callback_data=f"dl_cancel:{cb_data_id}") # Can be specific to episode
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# utils/keyboard_utils.py

def get_episode_versions_keyboard(versions: List[Dict], 
                                  anime_id_for_context: str | ObjectId, # Needed if season_id isn't enough for "Back to Seasons"
                                  season_id_str_for_back: str | ObjectId | None):
    buttons = []
    anime_id_str = str(anime_id_for_context) # Ensure it's a string

    for version in versions:
        text = f"{version['quality']} {version['audio_type']} ({version['file_size_bytes'] / (1024*1024):.1f}MB)"
        buttons.append([InlineKeyboardButton(text, callback_data=f"dl_epver:{str(version['_id'])}")])
    
    if season_id_str_for_back:
        # Use the shortened callback to go back to the episode list of that season
        buttons.append([InlineKeyboardButton("⬅️ Back to Episodes", callback_data=f"les_S:{str(season_id_str_for_back)}_p1")])
    else:
        # If for some reason season_id_str_for_back is not available,
        # provide a more general back button, e.g., back to seasons of the anime.
        buttons.append([InlineKeyboardButton("⬅️ Back to Seasons", callback_data=f"list_seasons_A:{anime_id_str}")])
    
    buttons.append([InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]) # Always good to have a main menu option
    return InlineKeyboardMarkup(buttons)


# --- ANIME DETAILS & NAVIGATION ---
def get_anime_detail_keyboard(anime_doc: Dict, is_in_watchlist: bool):
    anime_id_str = str(anime_doc['_id'])
    buttons = []
    # Watchlist button
    wl_text = "➖ Remove from Watchlist" if is_in_watchlist else "➕ Add to Watchlist"
    wl_cb = f"wl_rem:{anime_id_str}" if is_in_watchlist else f"wl_add:{anime_id_str}"
    buttons.append([InlineKeyboardButton(wl_text, callback_data=wl_cb)])

    # Seasons button (if seasons exist)
    # This would usually be generated by the handler by checking seasons for this anime
    buttons.append([InlineKeyboardButton("🎬 View Seasons/Episodes", callback_data=f"list_seasons_A:{anime_id_str}")])
    
    buttons.append([InlineKeyboardButton("⬅️ Back (e.g., to search/browse results)", callback_data="go_back_general")]) # Placeholder callback
    buttons.append([InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")])
    return InlineKeyboardMarkup(buttons)

def get_seasons_list_keyboard(seasons: List[Dict], anime_id_str_for_back_button: str | ObjectId):
    buttons = []
    if not seasons:
        buttons.append([InlineKeyboardButton("No seasons found for this anime yet.", callback_data="noop")])
    else:
        for season in seasons:
            title = season.get('title', f"Season {season['season_number']}")
            cb_data = f"les_S:{str(season['_id'])}_p1" # THIS IS THE KEY CALLBACK DATA
            LOGGER.info(f"SEASON BUTTON CB_DATA: {cb_data} for title: {title}") # Log it
            buttons.append([InlineKeyboardButton(title, callback_data=cb_data)])
    
    buttons.append([InlineKeyboardButton("⬅️ Back to Anime Details", callback_data=f"view_anime:{str(anime_id_str_for_back_button)}")])
    return InlineKeyboardMarkup(buttons)      

def get_episodes_list_keyboard(episodes_page: List[Dict], 
                               page: int, total_episodes: int, per_page: int,
                               anime_id: str | ObjectId, season_id: str | ObjectId, season_number: int):
    items_data = []
    anime_id_str = str(anime_id)
    # season_id_str = str(season_id) # Already a string when passed from handler usually

    LOGGER.info(f"get_episodes_list_keyboard: Building keyboard for A:{anime_id_str}, S:{season_id}, SN:{season_number}, Page:{page}")

    for i, ep in enumerate(episodes_page):
        title = ep.get('episode_title')
        ep_num_val = ep.get('episode_number', 'N/A') # Get the value
        ep_num_str = str(ep_num_val) # Convert to string for callback
        
        text_display = f"Ep {ep_num_val}" + (f": {title}" if title and title != f"Episode {ep_num_val}" else "")
        
        # This is the callback for individual episode buttons
        cb_data_episode = f"view_ep_versions_A:{anime_id_str}_SN:{season_number}_EN:{ep_num_str}"
        LOGGER.info(f"  EP BUTTON #{i+1}: Text='{text_display[:30]}...', CB_DATA='{cb_data_episode}' (Length: {len(cb_data_episode.encode('utf-8'))} bytes)")
        
        items_data.append({
            'text': text_display, 
            'callback_data': cb_data_episode
        })

    # This is the base_cb for pagination buttons (Next/Prev)
    # It should only contain the season_id to keep it short
    base_cb_for_pagination = f"les_S:{str(season_id)}" 
    LOGGER.info(f"  PAGINATION BASE_CB: '{base_cb_for_pagination}' (Length: {len(base_cb_for_pagination.encode('utf-8'))} bytes)")
    
    # Back button for the episode list goes back to the list of seasons for the current anime
    back_button_row = [[InlineKeyboardButton("⬅️ Back to Seasons", callback_data=f"list_seasons_A:{anime_id_str}")]]
    
    return paginate_keyboard(items_data, page, per_page, total_episodes, base_cb_for_pagination, items_per_row=1, extra_buttons_bottom=back_button_row)


# --- BROWSE ---
def get_browse_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔤 By A-Z", callback_data="browse_az_picker")],
        [InlineKeyboardButton("🎭 By Genre", callback_data="browse_genre_picker_page_1")],
        [InlineKeyboardButton("📅 By Year/Season", callback_data="browse_year_picker")],
        [InlineKeyboardButton("📊 By Status", callback_data="browse_status_picker")],
        [InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_az_picker_keyboard():
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ#" # # for numbers/symbols
    buttons = []
    row = []
    for i, letter in enumerate(letters):
        row.append(InlineKeyboardButton(letter, callback_data=f"browse_az_list_{letter}_page_1"))
        if (i + 1) % 7 == 0 or i == len(letters) - 1: # 7 buttons per row
            buttons.append(row)
            row = []
    buttons.append([InlineKeyboardButton("⬅️ Back to Browse", callback_data="browse_main")])
    return InlineKeyboardMarkup(buttons)

def get_genre_picker_keyboard(page: int):
    genres = config.SUPPORTED_GENRES
    per_page = 9 # 3x3 grid
    total_pages = ceil(len(genres) / per_page)
    start_index = (page - 1) * per_page
    page_genres = genres[start_index : start_index + per_page]
    
    buttons = []
    row = []
    for i, genre in enumerate(page_genres):
        row.append(InlineKeyboardButton(genre, callback_data=f"browse_genre_list_{genre.replace(' ','-')}_page_1"))
        if (i + 1) % 3 == 0 or i == len(page_genres) - 1:
            buttons.append(row)
            row = []

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"browse_genre_picker_page_{page-1}"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"browse_genre_picker_page_{page+1}"))
    if nav_row:
        buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton("⬅️ Back to Browse", callback_data="browse_main")])
    return InlineKeyboardMarkup(buttons)

def get_status_picker_keyboard():
    buttons = []
    for status in config.SUPPORTED_STATUS:
        buttons.append([InlineKeyboardButton(status, callback_data=f"browse_status_list_{status.replace(' ','-')}_page_1")])
    buttons.append([InlineKeyboardButton("⬅️ Back to Browse", callback_data="browse_main")])
    return InlineKeyboardMarkup(buttons)


# --- WATCHLIST ---
def get_watchlist_keyboard(watchlist_page_items: List[Dict], page: int, total_items: int, per_page: int):
    items_data = []
    for anime in watchlist_page_items:
        items_data.append({
            'text': anime.get('title', 'Unknown Anime'),
            'callback_data': f"view_anime:{str(anime['_id'])}"
        })
    base_cb = "my_watchlist" # for pagination: my_watchlist_page_X
    back_button_row = [[InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]]
    return paginate_keyboard(items_data, page, per_page, total_items, base_cb, items_per_row=1, extra_buttons_bottom=back_button_row)

# --- SETTINGS ---
def get_settings_keyboard(user_settings: dict):
    notif_status = "✅ ON" if user_settings.get('watchlist_notifications', True) else "❌ OFF"
    keyboard = [
        [InlineKeyboardButton(f"Preferred Quality: {user_settings.get('preferred_quality', '720p')}", callback_data="settings_quality")],
        [InlineKeyboardButton(f"Preferred Audio: {user_settings.get('preferred_audio', 'SUB')}", callback_data="settings_audio")],
        [InlineKeyboardButton(f"Watchlist Notifications: {notif_status}", callback_data="settings_toggle_notif")],
        [InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_quality_settings_keyboard(current_quality: str):
    qualities = ["Any", "480p", "720p", "1080p", "Best Available"] # Example
    buttons = []
    for q in qualities:
        prefix = "🔘 " if q == current_quality else "⚪️ "
        buttons.append([InlineKeyboardButton(prefix + q, callback_data=f"set_quality:{q.replace(' ','_')}")])
    buttons.append([InlineKeyboardButton("⬅️ Back to Settings", callback_data="user_settings")])
    return InlineKeyboardMarkup(buttons)

def get_audio_settings_keyboard(current_audio: str):
    audios = ["Any", "SUB", "DUB"] + config.SUPPORTED_AUDIO_TYPES # Could have others like RAW
    audios = sorted(list(set(audios))) # Unique and sorted
    buttons = []
    for a in audios:
        prefix = "🔘 " if a == current_audio else "⚪️ "
        buttons.append([InlineKeyboardButton(prefix + a, callback_data=f"set_audio:{a}")])
    buttons.append([InlineKeyboardButton("⬅️ Back to Settings", callback_data="user_settings")])
    return InlineKeyboardMarkup(buttons)


# --- ADMIN KEYBOARDS ---
def get_admin_panel_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📚 Manage Content ", callback_data="admin_content_start")],
        [
            InlineKeyboardButton("✏️ Edit Content", callback_data="admin_edit_content_menu"), # Leads to another menu
            InlineKeyboardButton("🗑️ Delete Content", callback_data="admin_delete_content_menu") # Leads to another menu
        ],
        [
            InlineKeyboardButton("👑 Manage Premium", callback_data="admin_manage_premium_menu"),
            InlineKeyboardButton("🙏 Manage Requests", callback_data="admin_manage_requests_page_1")
        ],
        [
            InlineKeyboardButton("📊 Bot Stats", callback_data="admin_bot_stats"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_prompt")
        ],
        [InlineKeyboardButton("⚙️ Bot Config", callback_data="admin_bot_config_menu")],
        [InlineKeyboardButton("⬆️ Main User Menu", callback_data="start_menu_cb")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_confirm_keyboard(confirm_callback: str, cancel_callback: str, confirm_text="✅ Confirm", cancel_text="❌ Cancel"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(confirm_text, callback_data=confirm_callback)],
        [InlineKeyboardButton(cancel_text, callback_data=cancel_callback)]
    ])

def get_skip_cancel_keyboard(cancel_callback: str): # For admin input prompts
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↪️ Skip this step", callback_data="admin_input_skip")],
        [InlineKeyboardButton("❌ Cancel Operation", callback_data=cancel_callback)]
    ])

def get_admin_status_keyboard(base_callback_prefix: str):
    buttons = []
    for status in config.SUPPORTED_STATUS:
        buttons.append([InlineKeyboardButton(status, callback_data=f"{base_callback_prefix}:{status.replace(' ','_')}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_add_anime_cancel")]) # General cancel
    return InlineKeyboardMarkup(buttons)

def get_admin_genre_selection_keyboard(selected_genres: List[str], base_callback_prefix: str, done_callback: str):
    buttons = []
    genres = config.SUPPORTED_GENRES
    row = []
    for i, genre in enumerate(genres):
        prefix = "✅ " if genre in selected_genres else "☑️ "
        row.append(InlineKeyboardButton(prefix + genre, callback_data=f"{base_callback_prefix}:{genre.replace(' ','-')}"))
        if (i + 1) % 2 == 0 or i == len(genres) - 1: # 2 buttons per row for genres
            buttons.append(row)
            row = []
    buttons.append([InlineKeyboardButton("🏁 Done Selecting Genres", callback_data=done_callback)])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_add_anime_cancel")])
    return InlineKeyboardMarkup(buttons)

def get_admin_audio_type_keyboard(base_callback_prefix: str, cancel_callback: str):
    buttons = []
    for audio_type in config.SUPPORTED_AUDIO_TYPES:
        buttons.append([InlineKeyboardButton(audio_type, callback_data=f"{base_callback_prefix}:{audio_type}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback)])
    return InlineKeyboardMarkup(buttons)

def get_admin_add_episode_options_keyboard(current_episode_doc_id_str: str, 
                                           next_ep_num_to_suggest: int,
                                           anime_id_for_finish_str: str): 
    keyboard = [
        [InlineKeyboardButton("➕ Add Diff. Version (Same Ep)", callback_data=f"adm_adep_same:{current_episode_doc_id_str}")],
        [InlineKeyboardButton(f"➕ Add Next Episode (Ep {next_ep_num_to_suggest})", 
                              callback_data=f"adm_adep_next:{current_episode_doc_id_str}")],
        [InlineKeyboardButton("🏁 Finish Adding for this Season", callback_data=f"list_seasons_A:{anime_id_for_finish_str}")],
        [InlineKeyboardButton("⬆️ Admin Panel", callback_data="admin_panel_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_manage_premium_keyboard():
    keyboard = [
        [InlineKeyboardButton("👑 Grant Premium", callback_data="admin_grant_premium_prompt_user")],
        [InlineKeyboardButton("🗑️ Revoke Premium", callback_data="admin_revoke_premium_prompt_user")],
        [InlineKeyboardButton("📋 List Premium Users", callback_data="admin_list_premium_users")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_bot_config_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📦 Manage Log Channels", callback_data="admin_config_log_channels")],
        [InlineKeyboardButton("💰 Manage Token System", callback_data="admin_config_token_system")],
        # Add more config options here if needed
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_edit_content_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Anime Details", callback_data="admin_edit_anime_prompt_id")],
        [InlineKeyboardButton("✏️ Edit Season Details (Not Impl.)", callback_data="admin_placeholder")], # TODO
        [InlineKeyboardButton("✏️ Edit Episode File/Details (Not Impl.)", callback_data="admin_placeholder")], # TODO
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_delete_content_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🗑️ Delete Entire Anime Series", callback_data="admin_delete_anime_prompt_id")],
        [InlineKeyboardButton("🗑️ Delete Season (Not Impl.)", callback_data="admin_placeholder")], # TODO
        [InlineKeyboardButton("🗑️ Delete Specific Episode File", callback_data="admin_delete_episode_prompt_id")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_request_management_keyboard(requests_page: List[Dict], page: int, total_requests: int, per_page: int):
    items_data = []
    for req in requests_page:
        req_id_str = str(req['_id'])
        user_id = req.get('user_id', 'N/A')
        text = f"'{req.get('anime_title_requested', 'N/A')}' ({req.get('language_requested','Any')}) - User: {user_id}"
        # Each request button could open a detail view for that request
        items_data.append({
            'text': text,
            'callback_data': f"admin_view_request:{req_id_str}"
        })

    base_cb = "admin_manage_requests"  # for pagination: admin_manage_requests_page_X
    back_button_row = [[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_main")]]

    if not items_data and page == 1: # No pending requests
        no_requests_button = [[InlineKeyboardButton("No pending requests found.", callback_data="noop")]]
        return paginate_keyboard([], 1, 1, 0, base_cb, extra_buttons_top=no_requests_button, extra_buttons_bottom=back_button_row)

    return paginate_keyboard(items_data, page, per_page, total_requests, base_cb, items_per_row=1, extra_buttons_bottom=back_button_row)


def get_single_request_management_keyboard(request_doc: Dict):
    req_id_str = str(request_doc['_id'])
    status = request_doc.get('status', 'N/A')
    buttons = [
        [InlineKeyboardButton(f"Mark as 'Investigating' {'(current)' if status == 'investigating' else ''}", callback_data=f"admin_req_status:{req_id_str}:investigating")],
        [InlineKeyboardButton(f"Mark as 'Fulfilled' {'(current)' if status == 'fulfilled' else ''}", callback_data=f"admin_req_status:{req_id_str}:fulfilled")],
        [InlineKeyboardButton(f"Mark as 'Rejected' {'(current)' if status == 'rejected' else ''}", callback_data=f"admin_req_status:{req_id_str}:rejected")],
        [InlineKeyboardButton(f"Mark as 'Unavailable' {'(current)' if status == 'unavailable' else ''}", callback_data=f"admin_req_status:{req_id_str}:unavailable")],
        [InlineKeyboardButton("⬅️ Back to Requests List", callback_data="admin_manage_requests_page_1")]
    ]
    return InlineKeyboardMarkup(buttons)

def noop_keyboard(): # Placeholder for no operation or acknowledged callbacks
    return InlineKeyboardMarkup([[InlineKeyboardButton("Processed.", callback_data="noop_ack")]])


# --- MANAGE CONTENT FLOW ---
def get_manage_content_search_results_keyboard(search_term: str, existing_animes: List[Dict]):
    keyboard = []
    if existing_animes:
        keyboard.append([InlineKeyboardButton("--- Select Existing Anime ---", callback_data="noop")])
        for anime in existing_animes[:5]: # Show max 5 matches initially
            keyboard.append([InlineKeyboardButton(f"{anime['title']} ({anime.get('year', 'N/A')})", callback_data=f"mc_sel_anime:{str(anime['_id'])}")])
        if len(existing_animes) > 5:
            keyboard.append([InlineKeyboardButton(f"➡️ View All {len(existing_animes)} Matches for '{search_term}'", callback_data=f"mc_view_all_matches:{search_term}")]) # Needs pagination

    keyboard.append([InlineKeyboardButton(f"➕ Add New Anime: '{search_term[:30]}...'", callback_data=f"mc_add_new_anime_confirm:{search_term}")]) # Pass search term as pre-fill
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="mc_cancel_op")])
    return InlineKeyboardMarkup(keyboard)

def get_manage_anime_options_keyboard(anime_id_str: str):
    keyboard = [
        # Seasons will be listed dynamically above/below these by the handler
        [InlineKeyboardButton("➕ Add New Season", callback_data=f"mc_as_prompt_snum:{anime_id_str}")],
        [InlineKeyboardButton("✏️ Edit Anime Details", callback_data=f"mc_edit_anime_meta:{anime_id_str}")],
        # [InlineKeyboardButton("🗑️ Delete This Anime Series", callback_data=f"mc_del_anime_confirm:{anime_id_str}")], # Destructive, use with care
        [InlineKeyboardButton("⬅️ Back to Anime Search", callback_data="mc_start_search")], # Or main admin panel
        [InlineKeyboardButton("⬆️ Admin Panel", callback_data="admin_panel_main")]
    ]
    return InlineKeyboardMarkup(keyboard) # Handler will add season buttons to this

def get_manage_season_options_keyboard(anime_id_str: str, season_id_str: str):
    keyboard = [
        # Episodes will be listed dynamically
        [InlineKeyboardButton("➕ Add File to Next Unadded Ep", callback_data=f"mc_add_file_next_unadded_S:{season_id_str}")],
        [InlineKeyboardButton("✏️ Edit Season Details", callback_data=f"mc_edit_season_meta:{season_id_str}")],
        # [InlineKeyboardButton("🗑️ Delete This Season", callback_data=f"mc_del_season_confirm:{season_id_str}")],
        [InlineKeyboardButton("⬅️ Back to Anime Details", callback_data=f"mc_sel_anime:{anime_id_str}")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_manage_episode_placeholder_options_keyboard(anime_id_str: str, season_id_str: str, episode_db_id_str: str | None, episode_number: int):
    # If episode_db_id_str is None, it's a placeholder that doesn't exist in DB yet.
    # If it exists, it's a placeholder (e.g. status="Not Added Yet")
    callback_base = f"mc_ep_ph_S:{season_id_str}_E:{episode_number}"
    if episode_db_id_str:
        callback_base += f"_ID:{episode_db_id_str}"
        
    keyboard = [
        [InlineKeyboardButton(f"➕ Add File to Ep {episode_number}", callback_data=f"{callback_base}_addfile")],
        [InlineKeyboardButton(f"🗓️ Set Release/Status for Ep {episode_number}", callback_data=f"{callback_base}_setstatus")],
        [InlineKeyboardButton("⬅️ Back to Episodes List", callback_data=f"mc_sel_season_A:{anime_id_str}_S:{season_id_str}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_manage_episode_version_options_keyboard(anime_id_str: str, season_id_str: str, logical_episode_identifier: str, # e.g., S1E1
                                               version_doc_id_str: str):
    keyboard = [
        [InlineKeyboardButton("🔄 Replace File", callback_data=f"mc_epver_replace:{version_doc_id_str}")],
        [InlineKeyboardButton("✏️ Edit Details (Quality/Audio/Title)", callback_data=f"mc_epver_editmeta:{version_doc_id_str}")],
        [InlineKeyboardButton("🗑️ Remove This Version", callback_data=f"mc_epver_remove_confirm:{version_doc_id_str}")],
        [InlineKeyboardButton(f"⬅️ Back to Files for {logical_episode_identifier}", callback_data=f"mc_sel_ep_A:{anime_id_str}_S:{season_id_str}_E:{logical_episode_identifier.split('E')[1]}")], # Assumes E identifier is just number
    ]
    return InlineKeyboardMarkup(keyboard)


def get_dynamic_choice_keyboard(choices: List[str], callback_prefix: str, back_callback: str, items_per_row: int = 2):
    keyboard = []
    row = []
    for i, choice in enumerate(choices):
        # Sanitize choice for callback data if it contains special characters
        cb_choice_val = choice.replace(" ", "_").lower() # Example sanitization
        row.append(InlineKeyboardButton(choice, callback_data=f"{callback_prefix}:{cb_choice_val}"))
        if (i + 1) % items_per_row == 0 or i == len(choices) - 1:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)
