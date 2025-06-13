# handlers/download_handler.py
import logging
import asyncio
from typing import Union, List, Dict, Any, Optional
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaDocument, InputMediaVideo # Input types for sending media
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant,
    AsyncioErrorMessage, BotInlineMessageNotFoundError, FileIdInvalid # Errors for file sending
)


import config
import strings

from database.mongo_db import MongoDB
from database.mongo_db import get_user_state, set_user_state, clear_user_state
from database.mongo_db import increment_download_counts
from database.models import User, Anime, Season, Episode, FileVersion

# Import helpers from common_handlers (need get_user) and browse/search (to go back to details)
from handlers.common_handlers import get_user
from handlers.search_handler import display_user_anime_details_menu # Use this helper to go back to details from download menus


download_logger = logging.getLogger(__name__)

# --- Download Workflow States ---
# handler: "download"
class DownloadState:
    SELECTING_EPISODE = "download_selecting_episode" # Displaying episodes list for a season
    SELECTING_VERSION = "download_selecting_version" # Displaying file versions for an episode


# --- User Download Workflow Handlers ---

# Callback triggered when user selects a Season button from the Anime Details menu.
# This is the entry point into the download path after viewing anime details.
@Client.on_callback_query(filters.regex(f"^download_select_season{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def download_select_season_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # download_select_season|<anime_id>|<season_number>

    try: await client.answer_callback_query(message_id, "Loading episodes for season...")
    except Exception: download_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")

    user_state = await MongoDB.get_user_state(user_id)

    # User state should be 'viewing_anime_details' from browse/search handlers OR
    # Could also be returning here from episode/version selection if State isn't strictly enforced
    # Check if in a browse or search state indicating viewing details, and that anime_id matches.
    is_valid_initial_state = (user_state and user_state.step == 'viewing_anime_details' and user_state.data.get('viewing_anime_id') == data.split(config.CALLBACK_DATA_SEPARATOR)[1])

    # Check if returning from download state
    is_valid_return_state = (user_state and user_state.handler == "download" and user_state.step in [DownloadState.SELECTING_EPISODE, DownloadState.SELECTING_VERSION] and user_state.data.get('anime_id') == data.split(config.CALLBACK_DATA_SEPARATOR)[1])

    if not (is_valid_initial_state or is_valid_return_state):
        download_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking select season {data}. State data: {user_state.data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Anime Details menu or main menu.", disable_web_page_preview=True)
        await MongoDB.clear_user_state(user_id);
        return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3: raise ValueError("Invalid callback data format for selecting season.")
        anime_id_str = parts[1]
        season_number = int(parts[2])

        # Ensure anime_id from callback matches state context (if state exists and has it)
        if user_state and user_state.data.get("viewing_anime_id") and user_state.data.get("viewing_anime_id") != anime_id_str:
             download_logger.warning(f"User {user_id} state viewing_anime_id mismatch for select season: {user_state.data.get('viewing_anime_id')} vs callback {anime_id_str}. Data mismatch! Clearing state.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime data mismatch in state. Process cancelled.", disable_web_page_preview=True)
             await MongoDB.clear_user_state(user_id); return


        download_logger.info(f"User {user_id} selecting season {season_number} for anime {anime_id_str} for download.")

        # Fetch the specific season data, projecting only the episodes list and anime name.
        # Use projection with $elemMatch
        filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
        projection = {"name": 1, "seasons.$": 1}

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

        # Validate if anime/season found and episodes list exists
        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0] or not anime_doc["seasons"][0].get("episodes"):
            download_logger.error(f"Anime/Season {anime_id_str}/S{season_number} not found or has no episodes for download for user {user_id}. Doc: {anime_doc}")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime or season not found, or no episodes available.", disable_web_page_preview=True)
             # State needs to return to viewing anime details. Get anime_id from callback data (if not in state).
             # State was viewing_anime_details initially, could keep it.
            # Clear any download-specific states.
            await MongoDB.set_user_state(user_id, user_state.handler, 'viewing_anime_details', data=user_state.data) # Ensure state is back to viewing details if necessary

            # Redisplay anime details menu. Fetch full anime document.
            full_anime = await MongoDB.get_anime_by_id(anime_id_str)
            if full_anime: await display_user_anime_details_menu(client, callback_query.message, full_anime)
            else: # Anime is gone. Return to main menu? Clear state.
                await MongoDB.clear_user_state(user_id); return


            return


        anime_name = anime_doc.get("name", "Anime Name Unknown")
        season_data = anime_doc["seasons"][0]
        episodes = season_data.get("episodes", [])


        # Sort episodes numerically before displaying
        episodes.sort(key=lambda e: e.get("episode_number", 0))

        # --- Transition to Selecting Episode State ---
        # Set state to indicating user is viewing episode list for this season, preserving context.
        # State will be "download", step SELECTING_EPISODE.
        # Need to store anime_id, season_number, and name in state data for going back to episodes list and for later steps.
        await MongoDB.set_user_state(
             user_id, "download", DownloadState.SELECTING_EPISODE,
             data={**user_state.data, "anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_name} # Add/Update context, preserve old state data
         )


        # Display the list of episodes for the selected season to the user.
        await display_user_episode_list(client, callback_query.message, anime_name, season_number, episodes) # Pass message to edit

    except ValueError:
        download_logger.warning(f"User {user_id} invalid season number data in callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid season data in callback.", disable_web_page_preview=True)
        # State should be okay.

    except Exception as e:
        download_logger.error(f"FATAL error handling download_select_season callback {data} for user {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await MongoDB.clear_user_state(user_id);


# Helper to display list of episodes for a season (User View)
# Called from download_select_season_callback and when returning from episode/version view
async def display_user_episode_list(client: Client, message: Message, anime_name: str, season_number: int, episodes: List[Dict]):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;


    menu_text = strings.EPISODE_LIST_TITLE_USER.format(anime_name=anime_name, season_number=season_number) + "\n\n";

    buttons = [];
    if not episodes:
         menu_text += "No episodes found for this season."; # Safety if called with empty list


    # Create buttons for each episode
    for episode_doc in episodes:
         ep_number = episode_doc.get("episode_number");
         if ep_number is None: download_logger.warning(f"User {user_id} found episode document with no episode_number for anime {anime_name} S{season_number}. Skipping display."); continue;

         files = episode_doc.get("files", []);
         release_date = episode_doc.get("release_date");

         ep_label = strings.EPISODE_FORMAT_AVAILABLE_USER.format(episode_number=ep_number);

         if files: ep_label += f" ✅";
         elif isinstance(release_date, datetime):
              formatted_date = release_date.astimezone(timezone.utc).strftime('%Y-%m-%d');
              ep_label = strings.EPISODE_FORMAT_RELEASE_DATE_USER.format(episode_number=ep_number, release_date=formatted_date);
         else: ep_label = strings.EPISODE_FORMAT_NOT_ANNOUNCED_USER.format(episode_number=ep_number);


         user_state = await MongoDB.get_user_state(user_id); # Need state for anime_id context for callback data
         anime_id_str = user_state.data.get("anime_id");

         if not anime_id_str:
              download_logger.error(f"Missing anime_id in state data while displaying user episode list buttons for user {user_id}. State: {user_state.data}. Cannot build buttons.");
              # Buttons remain empty, add error message.
              menu_text += "\n💔 Error building episode buttons."; break; # Add error text and break button loop


         buttons.append([InlineKeyboardButton(ep_label, callback_data=f"download_select_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{ep_number}")]);


    # Add navigation buttons: Back to Seasons List, Back to Main Menu.
    user_state = await MongoDB.get_user_state(user_id);
    anime_id_str = user_state.data.get("anime_id");

    if anime_id_str: # Need anime_id to go back to details/seasons menu
        # Back button returns to seasons list display (needs anime_id) - Calls browse_select_anime
        buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")]));
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]));
    else:
        download_logger.error(f"Missing anime_id in state while building user episode list back button for user {user_id}. State: {user_state.data}");
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]); # Only home button as fallback


    reply_markup = InlineKeyboardMarkup(buttons);

    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True);

    # State is DownloadState.SELECTING_EPISODE.

@Client.on_callback_query(filters.regex(f"^download_select_episode{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def download_select_episode_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id; data = callback_query.data;

    try: await client.answer_callback_query(message_id, "Loading download options...");
    except Exception: download_logger.warning(f"Failed to answer callback query {data} from user {user_id}.");

    user_state = await MongoDB.get_user_state(user_id);

    if not (user_state and user_state.handler == "download" and user_state.step == DownloadState.SELECTING_EPISODE):
        download_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking select episode {data}. State data: {user_state.data}. Clearing state.");
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Episode List menu or main menu.", disable_web_page_preview=True);
        await MongoDB.clear_user_state(user_id); return;


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 4: raise ValueError("Invalid callback data format.");
        anime_id_str = parts[1]; season_number = int(parts[2]); episode_number = int(parts[3]);

        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number:
             download_logger.warning(f"User {user_id} state anime/season mismatch for select episode: {user_state.data.get('anime_id')}/S{user_state.data.get('season_number')} vs callback {anime_id_str}/S{season_number}. State data: {user_state.data}. Updating state data.");
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number}); # Update state data


        download_logger.info(f"User {user_id} selecting Episode {episode_number} from anime {anime_id_str}/S{season_number} for download.");

        filter_query = {"_id": ObjectId(anime_id_str)};
        projection = {
            "name": 1,
             "seasons": {
                  "$elemMatch": {
                       "season_number": season_number,
                       "episodes": {
                            "$elemMatch": {
                                "episode_number": episode_number,
                           }
                       }
                  }
             }
         }; # Project the specific episode (with files/date fields implicitly projected via $)


        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection);

        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0] or not anime_doc["seasons"][0].get("episodes") or not anime_doc["seasons"][0]["episodes"][0]:
             download_logger.error(f"Anime/Season/Episode {anime_id_str}/S{season_number}E{episode_number} not found for download options for user {user_id}. Doc: {anime_doc}");
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Episode not found or data missing.", disable_web_page_preview=True);
             filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number};
             projection_season_episodes = {"name": 1, "seasons.$": 1};
             anime_doc_season = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes);
             if anime_doc_season and anime_doc_season.get("seasons") and anime_doc_season["seasons"][0]:
                 anime_name_for_list = anime_doc_season.get("name", "Anime Name Unknown"); episodes_list = anime_doc_season["seasons"][0].get("episodes", []); episodes_list.sort(key=lambda e: e.get("episode_number", 0));
                 await display_user_episode_list(client, callback_query.message, anime_name_for_list, season_number, episodes_list);
             else:
                 download_logger.error(f"Failed to fetch anime/season after episode not found for user {user_id}. Cannot re-display."); await edit_or_send_message(client, chat_id, message_id, "💔 Error loading episode list.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id);

            return;

        anime_name = anime_doc.get("name", "Anime Name Unknown");
        try:
             episode_data_proj = anime_doc["seasons"][0]["episodes"][0];
        except (KeyError, IndexError) as e:
            download_logger.error(f"Error accessing deeply nested episode data in projected document for user {user_id} {data}: {e}. Doc: {anime_doc}", exc_info=True);
            await edit_or_send_message(client, chat_id, message_id, "💔 Error accessing episode data. Cannot display download options.", disable_web_page_preview=True);
            filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}; projection_season_episodes = {"name": 1, "seasons.$": 1}; anime_doc_episode = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes);
            if anime_doc_episode and anime_doc_episode.get("seasons") and anime_doc_episode["seasons"][0]: anime_name_for_list = anime_doc_episode.get("name", "Anime Name Unknown"); episodes_list = anime_doc_episode["seasons"][0].get("episodes", []); episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None); if episode_doc: await display_user_version_list(client, callback_query.message, anime_name_for_list, season_number, episode_number, episode_doc.get("files", []), episode_doc.get("release_date")); else: episodes_list.sort(key=lambda e: e.get("episode_number", 0)); await display_user_episode_list(client, callback_query.message, anime_name_for_list, season_number, episodes_list);
            else: download_logger.error(f"Failed to fetch anime/season after episode data access error for user {user_id}. Cannot re-display."); await edit_or_send_message(client, chat_id, message_id, "💔 Error loading episode list.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id); return;
            return;

        files = episode_data_proj.get("files", []); release_date = episode_data_proj.get("release_date");

        await MongoDB.set_user_state(user_id, "download", DownloadState.SELECTING_VERSION, data={**user_state.data, "anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number, "anime_name": anime_name, "file_versions": files}); # Store file versions list in state data


        await display_user_version_list(client, callback_query.message, anime_name, season_number, episode_number, files, release_date);


    except ValueError: download_logger.warning(f"User {user_id} invalid episode data in callback: {data}"); await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid episode data in callback.", disable_web_page_preview=True);
    except Exception as e:
         download_logger.error(f"FATAL error handling download_select_episode callback {data} for user {user_id}: {e}", exc_info=True);
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
         await MongoDB.clear_user_state(user_id);

async def display_user_version_list(client: Client, message: Message, anime_name: str, season_number: int, episode_number: int, file_versions: List[Dict], release_date: Optional[datetime]):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;

    menu_text = f"📥 <b><u>Download Options for</u></b> <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> 👇\n\n"; buttons = [];
    user_state = await MongoDB.get_user_state(user_id); if not user_state or user_state.handler != "download": download_logger.error(f"Unexpected state while displaying user version list for {user_id}: {user_state}. State data: {user_state.data}"); return; # Must be in download handler for this context
    anime_id_str = user_state.data.get('anime_id');


    if file_versions:
         menu_text += f"<b><u>Available Versions</u></b>:\n";
         for i, file_ver_dict in enumerate(file_versions):
             quality = file_ver_dict.get('quality_resolution', 'Unknown Quality'); size_bytes = file_ver_dict.get('file_size_bytes', 0); audio_langs = file_ver_dict.get('audio_languages', []); subs_langs = file_ver_dict.get('subtitle_languages', []); file_id = file_ver_dict.get('file_id'); file_unique_id = file_ver_dict.get('file_unique_id', None);
             formatted_size = f"{size_bytes / (1024 * 1024):.2f} MB" if size_bytes > 0 else "0 MB"; if size_bytes >= 1024 * 1024 * 1024: formatted_size = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB";
             audio_str = ', '.join(audio_langs) if audio_langs else 'N/A'; subs_str = ', '.join(subs_langs) if subs_langs else 'None';

             menu_text += f"<b>{i+1}.</b> <b>{quality}</b> ({formatted_size}) 🎧 {audio_str} 📝 {subs_str}\n";

             if file_id and file_unique_id:
                  button_label = strings.BUTTON_DOWNLOAD_FILE_USER.format(size=formatted_size);
                  buttons.append([InlineKeyboardButton(button_label, callback_data=f"download_confirm_send{config.CALLBACK_DATA_SEPARATOR}{file_unique_id}")]));

             else: download_logger.error(f"File version dictionary missing file_id or unique_id for {anime_name} S{season_number}E{episode_number}. Cannot create download button.");


    elif isinstance(release_date, datetime): formatted_date = release_date.astimezone(timezone.utc).strftime('%Y-%m-%d'); menu_text += f"⏳ This episode is scheduled for release on: <b>{formatted_date}</b>.\n\nCheck back later!";
    else: menu_text += "❓ No file versions or release date set for this episode yet.\n\n";

    if user_state and user_state.handler == "download":
         if anime_id_str and season_number is not None:
             buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"download_select_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}")]));
         else: download_logger.error(f"Missing anime/season context in state while building version list back button for user {user_id}. State: {user_state.data}"); buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="browse_main_menu")])); # Fallback

         buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]));
    else: buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]));


    reply_markup = InlineKeyboardMarkup(buttons); await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True);

@Client.on_callback_query(filters.regex(f"^download_confirm_send{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def download_confirm_send_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id; data = callback_query.data;

    try: await client.answer_callback_query(message_id, "Checking permissions...");
    except Exception: download_logger.warning(f"Failed to answer callback query {data} from user {user_id}.");


    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "download" and user_state.step == DownloadState.SELECTING_VERSION):
        download_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking download button {data}. State data: {user_state.data}. Clearing state.");
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for downloading. Please navigate back to select content.", disable_web_page_preview=True);
        await MongoDB.clear_user_state(user_id); return;


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 2: raise ValueError("Invalid callback data format."); file_unique_id = parts[1];

        anime_id_str = user_state.data.get("anime_id"); season_number = user_state.data.get("season_number"); episode_number = user_state.data.get("episode_number");
        anime_name = user_state.data.get("anime_name");

        if not all([anime_id_str, season_number is not None, episode_number is not None]):
             download_logger.error(f"User {user_id} clicking download button {data} but missing anime/season/ep context from state data {user_state.step}: {user_state.data}");
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing context data from state for download. Please select episode again.", disable_web_page_preview=True);
             if anime_id_str and season_number is not None: await display_user_episode_list(client, callback_query.message, anime_name or "Anime", season_number, []); # Retry episode list display
             else: await MongoDB.clear_user_state(user_id);
             return;


        download_logger.info(f"User {user_id} requesting download of file unique ID {file_unique_id} for {anime_id_str}/S{season_number}E{episode_number}. State data: {user_state.data}");


        filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number };
        projection = {
            "name": 1,
             "seasons": {
                  "$elemMatch": {
                       "season_number": season_number,
                       "episodes": {
                            "$elemMatch": {
                                 "episode_number": episode_number,
                                 "files": { "$elemMatch": {"file_unique_id": file_unique_id} }
                           }
                      }
                 }
            }
         };

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection);


        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0] or not anime_doc["seasons"][0].get("episodes") or not anime_doc["seasons"][0]["episodes"][0] or not anime_doc["seasons"][0]["episodes"][0].get("files") or not anime_doc["seasons"][0]["episodes"][0]["files"][0]:
             download_logger.error(f"File version {file_unique_id} not found for download for user {user_id} at {anime_id_str}/S{season_number}E{episode_number}. Doc: {anime_doc}");
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Download file version not found in database.", disable_web_page_preview=True);
             filter_query_episode = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}; projection_episode = {"name": 1, "seasons.$": 1}; anime_doc_episode = await MongoDB.anime_collection().find_one(filter_query_episode, projection_episode);
             if anime_doc_episode and anime_doc_episode.get("seasons") and anime_doc_episode["seasons"][0]: episodes_list = anime_doc_episode["seasons"][0].get("episodes", []); episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None); if episode_doc: await display_user_version_list(client, callback_query.message, anime_doc_episode.get("name", "Anime Name"), season_number, episode_number, episode_doc.get("files", []), episode_doc.get("release_date")); else: episodes_list.sort(key=lambda e: e.get("episode_number", 0)); await display_user_episode_list(client, callback_query.message, anime_doc_episode.get("name", "Anime Name"), season_number, episodes_list);
             else: download_logger.error(f"Failed to fetch anime/season after file version not found for user {user_id}. Cannot re-display."); await edit_or_send_message(client, chat_id, message_id, "💔 Error loading download options.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id);
             return;

        try: file_version_data_proj = anime_doc["seasons"][0]["episodes"][0]["files"][0]; file_version_data = FileVersion(**file_version_data_proj);
        except (KeyError, IndexError) as e:
             download_logger.error(f"Error accessing deeply nested file version data in projected document for user {user_id} {data}: {e}. Doc: {anime_doc}", exc_info=True); await edit_or_send_message(client, chat_id, message_id, "💔 Error accessing file data for download.", disable_web_page_preview=True); filter_query_episode = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}; projection_episode = {"name": 1, "seasons.$": 1}; anime_doc_episode = await MongoDB.anime_collection().find_one(filter_query_episode, projection_episode); if anime_doc_episode and anime_doc_episode.get("seasons") and anime_doc_episode["seasons"][0]: anime_name_for_list = anime_doc_episode.get("name", "Anime Name Unknown"); episodes_list = anime_doc_episode["seasons"][0].get("episodes", []); episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None); if episode_doc: await display_user_version_list(client, callback_query.message, anime_name_for_list, season_number, episode_number, episode_doc.get("files", []), episode_doc.get("release_date")); else: episodes_list.sort(key=lambda e: e.get("episode_number", 0)); await display_user_episode_list(client, callback_query.message, anime_name_for_list, season_number, episodes_list); else: download_logger.error(f"Failed to fetch anime/season after file data access error for user {user_id}. Cannot re-display."); await edit_or_send_message(client, chat_id, message_id, "💔 Error loading download options.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id); return;
            return;

        user = await get_user(client, user_id);
        if user is None:
            download_logger.error(f"Failed to get user {user_id} for download permission check. DB Error."); await edit_or_send_message(client, chat_id, message_id, strings.DB_ERROR, disable_web_page_preview=True); return;

        has_permission = False; required_tokens = config.TOKENS_PER_REDEEM;
        if user.premium_status != "free": has_permission = True; request_cost = 0; download_logger.debug(f"User {user_id} is Premium. Allowing download for {file_unique_id}.");
        else:
            if user.tokens >= required_tokens: has_permission = True; download_logger.debug(f"User {user_id} is Free, has {user.tokens} tokens. Allowing download for {file_unique_id}. Cost: {required_tokens} tokens.");
            else: has_permission = False; download_logger.info(f"User {user_id} is Free, has {user.tokens} tokens. Insufficient tokens ({required_tokens}) for download of {file_unique_id}.");
            # If not enough tokens, display message here:
            if not has_permission: await edit_or_send_message(client, chat_id, message_id, strings.NOT_ENOUGH_TOKENS.format(required_tokens=required_tokens, user_tokens=user.tokens), disable_web_page_preview=True);


        if has_permission:
             try: await callback_query.message.edit_text(strings.FILE_BEING_SENT, parse_mode=config.PARSE_MODE);
             except (MessageIdInvalid, MessageNotModified) as e: download_logger.warning(f"Failed to edit message {message_id} with FILE_BEING_SENT for user {user_id}: {e}. Sending as new."); await client.send_message(chat_id, strings.FILE_BEING_SENT, parse_mode=config.PARSE_MODE);
             except FloodWait as e: download_logger.warning(f"FloodWait sending FILE_BEING_SENT for user {user_id} (retry in {e.value}s): {e}"); await asyncio.sleep(e.value); try: await client.send_message(chat_id, strings.FILE_BEING_SENT, parse_mode=config.PARSE_MODE); except Exception: pass;


             try:
                 mime_type = file_version_data.mime_type or ""; is_video = mime_type.startswith('video/') or (file_version_data.file_name and any(file_version_data.file_name.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm']));
                 if is_video: sent_media = await client.send_video(chat_id=chat_id, video=file_version_data.file_id, parse_mode=config.PARSE_MODE);
                 else: sent_media = await client.send_document(chat_id=chat_id, document=file_version_data.file_id, file_name=file_version_data.file_name or f"{anime_name} S{season_number}E{episode_number:02d}.dat", parse_mode=config.PARSE_MODE);

                 download_logger.info(f"User {user_id} successfully sent file version {file_unique_id} ({file_version_data.file_id}).");
                 await client.send_message(chat_id, strings.FILE_SENT_SUCCESS, parse_mode=config.PARSE_MODE);

                 if user.premium_status == "free":
                     try: await MongoDB.users_collection().update_one({"user_id": user_id}, {"$inc": {"tokens": -required_tokens}}); download_logger.info(f"User {user_id}: Deducted {required_tokens} tokens for {file_unique_id}.");
                     except Exception as e: download_logger.error(f"Failed to deduct tokens from user {user_id} after download of {file_unique_id}: {e}", exc_info=True);

                 await MongoDB.increment_download_counts(user_id=user_id, anime_id=anime_id_str);

             except FileIdInvalid:
                  download_logger.error(f"Invalid File ID stored in DB for unique ID {file_unique_id} for {anime_id_str}/S{season_number}E{episode_number} requested by {user_id}. DB File ID: {file_version_data.file_id}.", exc_info=True);
                  await client.send_message(chat_id, "💔 Error sending file: The file ID appears invalid or expired.", parse_mode=config.PARSE_MODE);
             except FloodWait as e:
                  download_logger.warning(f"FloodWait while sending file for user {user_id} (retry in {e.value}s) for {file_unique_id}: {e}");
                  await client.send_message(chat_id, f"🚦 Too many requests! Please wait {e.value} seconds and try downloading again.", parse_mode=config.PARSE_MODE);
                  await asyncio.sleep(e.value); # Optional: Add small delay before exiting the FloodWait scope
             except Exception as e:
                  download_logger.error(f"Failed to send file version {file_unique_id} for {anime_id_str}/S{season_number}E{episode_number} to user {user_id}: {e}", exc_info=True);
                  await client.send_message(chat_id, strings.FILE_SEND_ERROR, parse_mode=config.PARSE_MODE);


        else: pass


    except ValueError: download_logger.warning(f"User {user_id} invalid file unique ID in download confirmation callback: {data}"); await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid download data.", disable_web_page_preview=True);
    except Exception as e:
        download_logger.error(f"FATAL error handling download_confirm_send callback {data} for user {user_id}: {e}", exc_info=True);
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
        await MongoDB.clear_user_state(user_id);
