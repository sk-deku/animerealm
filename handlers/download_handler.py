# handlers/download_handler.py
import logging
import asyncio
from typing import Union, List, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaDocument, InputMediaVideo # Types for sending media using file_id
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant,
    AsyncioErrorMessage, BotInlineMessageNotFoundError, FileIdInvalid # Specific Pyrogram errors
)


import config
import strings

from database.mongo_db import MongoDB
from database.mongo_db import get_user_state, set_user_state, clear_user_state # State management
from database.mongo_db import increment_download_counts # Helper to update counters
from database.models import User, Anime, Season, Episode, FileVersion # Import models


async def get_user(client: Client, user_id: int) -> Optional[User]: pass # Assume accessible
async def edit_or_send_message(client: Client, chat_id: int, message_id: Optional[int], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = True): pass


download_logger = logging.getLogger(__name__)

# --- Download Workflow States ---
# handler: "download"
class DownloadState:
    # Initial states when viewing details managed by browse/search handlers:
    # - browse_handler: viewing_anime_details
    # - search_handler: viewing_anime_details
    # Data includes: "viewing_anime_id"

    # States within the download path initiated from anime details:
    SELECTING_SEASON = "download_selecting_season" # Implicit within 'viewing_anime_details', display seasons
    SELECTING_EPISODE = "download_selecting_episode" # Displaying episodes for a selected season
    SELECTING_VERSION = "download_selecting_version" # Displaying file versions for a selected episode


# --- User Download Workflow Handlers ---

# Callback triggered when user selects a Season button from the Anime Details menu.
# This is the entry point into the season/episode/file selection sequence for download.
# Catches callbacks: download_select_season|<anime_id>|<season_number>
@Client.on_callback_query(filters.regex(f"^download_select_season{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def download_select_season_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message containing the season buttons
    data = callback_query.data # download_select_season|<anime_id>|<season_number>

    try: await client.answer_callback_query(message.id, "Loading episodes for season...")
    except Exception: download_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")

    user_state = await MongoDB.get_user_state(user_id)

    # User state should be 'viewing_anime_details' from browse/search handlers.
    # Also, the anime_id in state data should match the callback data.
    if not (user_state and user_state.step == 'viewing_anime_details' and user_state.data.get('viewing_anime_id') == data.split(config.CALLBACK_DATA_SEPARATOR)[1]):
        download_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking select season {data}. State data: {user_state.data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Anime Details menu or main menu.", disable_web_page_preview=True)
        await MongoDB.clear_user_state(user_id);
        return


    try:
        # Parse anime_id and season_number from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3: raise ValueError("Invalid callback data format for selecting season.")
        anime_id_str = parts[1]
        season_number = int(parts[2])

        # Ensure anime_id from callback matches state context
        if user_state.data.get("viewing_anime_id") != anime_id_str:
            download_logger.warning(f"User {user_id} state viewing_anime_id mismatch for select season: {user_state.data.get('viewing_anime_id')} vs callback {anime_id_str}. Data mismatch!")
             # Mismatch in this sensitive flow means potential issue. Clear state.
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime data mismatch in state. Process cancelled.", disable_web_page_preview=True)
            await MongoDB.clear_user_state(user_id);
            return


        download_logger.info(f"User {user_id} selecting season {season_number} for anime {anime_id_str} for download.")

        # Fetch the specific anime document, projecting only the needed season and its episodes.
        filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
        projection = {"name": 1, "seasons.$": 1} # Project name and the matched season

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

        # Validate if anime/season found and episodes list exists
        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0] or not anime_doc["seasons"][0].get("episodes"):
            download_logger.error(f"Anime/Season {anime_id_str}/S{season_number} not found or has no episodes for download for user {user_id}. Doc: {anime_doc}")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime or season not found, or no episodes available.", disable_web_page_preview=True)
             # State is 'viewing_anime_details'. Keep it? Or go back to details menu.
             # Go back to anime details menu for safety. Fetch the full anime doc.
            full_anime = await MongoDB.get_anime_by_id(anime_id_str)
            if full_anime: await search_handler.display_user_anime_details_menu(client, callback_query.message, full_anime)
            else: await MongoDB.clear_user_state(user_id); return


            return # Stop

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        season_data = anime_doc["seasons"][0] # The matched season data
        episodes = season_data.get("episodes", []) # The episodes list from the season


        # Sort episodes numerically
        episodes.sort(key=lambda e: e.get("episode_number", 0))

        # --- Transition to Selecting Episode State ---
        # State indicates we are viewing episode list for a season, preserve context (anime_id, season_number, name).
        await MongoDB.set_user_state(
             user_id,
             "download", # New handler state
             DownloadState.SELECTING_EPISODE,
             data={"anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_name}
         )


        # Display the list of episodes for the selected season to the user.
        await display_user_episode_list(client, callback_query.message, anime_name, season_number, episodes) # Pass message to edit


    except ValueError:
        download_logger.warning(f"User {user_id} invalid season number data in callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid season data in callback.", disable_web_page_preview=True)
        # State remains 'viewing_anime_details'.

    except Exception as e:
        download_logger.error(f"FATAL error handling download_select_season callback {data} for user {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await MongoDB.clear_user_state(user_id);


# Helper to display list of episodes for a season (User View)
# Called from download_select_season_callback and after action in episode view that returns here (e.g., deleting file? Not applicable for user. Back button from version select)
async def display_user_episode_list(client: Client, message: Message, anime_name: str, season_number: int, episodes: List[Dict]):
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id # Message containing the episode list


    menu_text = strings.EPISODE_LIST_TITLE_USER.format(anime_name=anime_name, season_number=season_number) + "\n\n"

    buttons = []
    if not episodes:
         # Should not happen if logic above checks for episodes, but safety.
         menu_text += "No episodes found for this season."
         # Add Back button
         # Get anime_id from state data to return to anime details menu
         user_state = await MongoDB.get_user_state(user_id) # Get state for context
         anime_id_str = user_state.data.get("anime_id")

         buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"download_select_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}")]) # Go back to seasons list for THIS anime
         buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])
         reply_markup = InlineKeyboardMarkup(buttons)
         await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)
         return


    # Create buttons for each episode
    for episode_doc in episodes: # Episode data as dicts from DB/Pydantic
         ep_number = episode_doc.get("episode_number")
         # Skip invalid entries
         if ep_number is None:
              download_logger.warning(f"User {user_id} found episode document with no episode_number for anime {anime_name} S{season_number}. Skipping display.")
              continue

         # Determine episode status for button label (Available, Release Date, Not Announced)
         files = episode_doc.get("files", []) # Files list of dicts
         release_date = episode_doc.get("release_date") # Datetime or None/missing

         ep_label = strings.EPISODE_FORMAT_AVAILABLE_USER.format(episode_number=ep_number) # Base label "🎬 EPXX"

         if files:
              ep_label += f" ✅" # Indicator if files exist
         elif isinstance(release_date, datetime): # Check if it's a datetime object
              formatted_date = release_date.astimezone(timezone.utc).strftime('%Y-%m-%d') # Format date
              ep_label = strings.EPISODE_FORMAT_RELEASE_DATE_USER.format(episode_number=ep_number, release_date=formatted_date) # Full date label
         else: # Neither files nor release date
              ep_label = strings.EPISODE_FORMAT_NOT_ANNOUNCED_USER.format(episode_number=ep_number) # Full 'Not Announced' label


         # Callback data to select this episode for version/date view: download_select_episode|<anime_id>|<season>|<ep>
         # Needs anime_id from state context, as message.message only has message_id not originating button data always
         user_state = await MongoDB.get_user_state(user_id) # Get state for anime_id context
         anime_id_str = user_state.data.get("anime_id") # Anime ID must be in state

         if not anime_id_str:
              download_logger.error(f"Missing anime_id in state data while displaying user episode list for user {user_id}. State: {user_state.data}")
              await edit_or_send_message(client, chat_id, message_id, "💔 Error loading episode list context. Please try again.", disable_web_page_preview=True)
              await MongoDB.clear_user_state(user_id); return # Critical error


         buttons.append([InlineKeyboardButton(ep_label, callback_data=f"download_select_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{ep_number}")])


    # Add navigation buttons: Back to Seasons List, Back to Main Menu.
    user_state = await MongoDB.get_user_state(user_id) # Get state for context
    anime_id_str = user_state.data.get("anime_id") # Ensure anime_id is in state
    if not anime_id_str:
        download_logger.error(f"Missing anime_id in state data while building buttons for user episode list for user {user_id}. State: {user_state.data}")
        # Add only basic back to menu buttons if context is broken
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])
    else:
        # Back button returns to seasons list display (needs original anime_id)
        # Need to trigger the handler browse_select_anime|<anime_id> to re-display details with season options
        # The browse_select_anime handler needs anime_id in the callback.
        # It requires passing the original anime_id from the state data.
        buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")]) # Pass anime ID back to browse handler


        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Main menu

    reply_markup = InlineKeyboardMarkup(buttons)

    # Edit the season selection message to display this episode list.
    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)

    # State is DownloadState.SELECTING_EPISODE, stays until user selects episode or navigates back/home.


# Callback triggered when user selects an Episode button from the Episodes list.
# Leads to displaying file versions available for that episode or status.
# Catches callbacks: download_select_episode|<anime_id>|<season_number>|<episode_number>
@Client.on_callback_query(filters.regex(f"^download_select_episode{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def download_select_episode_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message containing the episode buttons
    data = callback_query.data # download_select_episode|<anime_id>|<season>|<ep>

    try: await client.answer_callback_query(message.id, "Loading download options...")
    except Exception: download_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")

    user_state = await MongoDB.get_user_state(user_id)

    # State should be DownloadState.SELECTING_EPISODE
    if not (user_state and user_state.handler == "download" and user_state.step == DownloadState.SELECTING_EPISODE):
        download_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking select episode {data}. State data: {user_state.data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please return to the Episode List menu or main menu.", disable_web_page_preview=True)
        await MongoDB.clear_user_state(user_id); return


    try:
        # Parse anime_id, season_number, episode_number from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for selecting episode.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        # Ensure context data in state matches callback data for robustness
        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number:
             download_logger.warning(f"User {user_id} state anime/season mismatch for select episode: {user_state.data.get('anime_id')}/S{user_state.data.get('season_number')} vs callback {anime_id_str}/S{season_number}. State data: {user_state.data}. Updating state data.")
             # Update state data to match callback action context.
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number})
             await MongoDB.set_user_state(user_id, user_state.handler, user_state.step, data=user_state.data)


        download_logger.info(f"User {user_id} selecting Episode {episode_number} from anime {anime_id_str}/S{season_number} for download.")


        # Fetch the specific episode document to get its files and release_date.
        # Need to navigate nested structure. Project specific episode's details.
        filter_query = {"_id": ObjectId(anime_id_str)}
        projection = {
            "name": 1, # Project anime name
             "seasons": {
                  "$elemMatch": { # Find the season
                       "season_number": season_number,
                       "episodes": { # Find the episode within the season
                            "$elemMatch": {
                                "episode_number": episode_number
                                # Project only the needed episode fields: files, release_date
                                # Using $elemMatch projection only on a single path
                           }
                       }
                  }
             }
         }

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)


        # Validate if anime/season/episode found and episode data available
        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0] or not anime_doc["seasons"][0].get("episodes") or not anime_doc["seasons"][0]["episodes"][0]:
             download_logger.error(f"Anime/Season/Episode {anime_id_str}/S{season_number}E{episode_number} not found for download options for user {user_id}. Doc: {anime_doc}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Episode not found or data missing.", disable_web_page_preview=True)
             # State is SELECTING_EPISODE. Go back to episode list display.
             # Needs to re-fetch episodes list for the season.
             filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection_season_episodes = {"name": 1, "seasons.$": 1}
             anime_doc_season = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes)
             if anime_doc_season and anime_doc_season.get("seasons") and anime_doc_season["seasons"][0]:
                  anime_name_for_list = anime_doc_season.get("name", "Anime Name Unknown")
                  episodes_list = anime_doc_season["seasons"][0].get("episodes", [])
                  episodes_list.sort(key=lambda e: e.get("episode_number", 0)) # Sort
                  # State remains SELECTING_EPISODE
                  await display_user_episode_list(client, callback_query.message, anime_name_for_list, season_number, episodes_list)

             else:
                 download_logger.error(f"Failed to fetch anime/season to re-display list after episode not found for user {user_id}. Cannot re-display list.")
                 await edit_or_send_message(client, chat_id, message_id, "💔 Error loading episode list.", disable_web_page_preview=True)
                 await MongoDB.clear_user_state(user_id); # Clear state
                 return


            return # Stop execution

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        # Access the specific episode document from the nested projection results
        try:
             episode_data_proj = anime_doc["seasons"][0]["episodes"][0] # The deeply nested episode doc with files/date projected
             # Use Pydantic model to get defaults and potentially validate? No, already doing that for inserts.
             # Work with the dictionary directly as display function expects dict.
        except (KeyError, IndexError) as e:
            download_logger.error(f"Error accessing deeply nested episode data in projected document for {anime_id_str}/S{season_number}E{episode_number} for user {user_id}: {e}. Doc: {anime_doc}", exc_info=True)
            await edit_or_send_message(client, chat_id, message_id, "💔 Error accessing episode data. Cannot display download options.", disable_web_page_preview=True)
            # Go back to episode list view.
            filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
            projection_season_episodes = {"name": 1, "seasons.$": 1}
            anime_doc_season = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes)
            if anime_doc_season and anime_doc_season.get("seasons") and anime_doc_season["seasons"][0]:
                 anime_name_for_list = anime_doc_season.get("name", "Anime Name Unknown")
                 episodes_list = anime_doc_season["seasons"][0].get("episodes", [])
                 episodes_list.sort(key=lambda e: e.get("episode_number", 0)) # Sort
                 # State remains SELECTING_EPISODE
                 await display_user_episode_list(client, callback_query.message, anime_name_for_list, season_number, episodes_list)

            else:
                 download_logger.error(f"Failed to fetch anime/season after episode data access error for user {user_id}. Cannot re-display list.")
                 await edit_or_send_message(client, chat_id, message_id, "💔 Error loading episode list.", disable_web_page_preview=True)
                 await MongoDB.clear_user_state(user_id);
                 return


            return # Stop execution

        files = episode_data_proj.get("files", []) # Files list of dicts
        release_date = episode_data_proj.get("release_date") # Datetime or None/missing


        # --- Transition to Selecting Version State ---
        # Set state to SELECTING_VERSION, storing specific episode context and file versions list if available.
        # This allows displaying file versions and checking their details without re-fetching.
        await MongoDB.set_user_state(
             user_id,
             "download",
             DownloadState.SELECTING_VERSION, # State is now selecting file version
             data={
                 "anime_id": anime_id_str,
                 "season_number": season_number,
                 "episode_number": episode_number,
                 "anime_name": anime_name,
                 "file_versions": files # Store list of files
                 # If there's a release date but no files, maybe store that info too? No, logic checks file list first.
             }
         )

        # Display download options / file versions for the selected episode.
        await display_user_version_list(client, callback_query.message, anime_name, season_number, episode_number, files, release_date)


    except ValueError:
        download_logger.warning(f"User {user_id} invalid episode data in callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid episode data in callback.", disable_web_page_preview=True)
        # State is SELECTING_EPISODE, should stay.


    except Exception as e:
         download_logger.error(f"FATAL error handling download_select_episode callback {data} for user {user_id}: {e}", exc_info=True)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await MongoDB.clear_user_state(user_id);


# Helper to display available file versions or status for an episode (User View)
# Called from download_select_episode_callback and potentially after a download attempt returns here
async def display_user_version_list(client: Client, message: Message, anime_name: str, season_number: int, episode_number: int, file_versions: List[Dict], release_date: Optional[datetime]):
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id

    menu_text = f"📥 <b><u>Download Options for</u></b> <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> 👇\n\n"

    buttons = []
    if file_versions:
         menu_text += f"<b><u>Available Versions</u></b>:\n"
         # Create buttons for each file version
         for i, file_ver_dict in enumerate(file_versions):
             # Format version details for display in the message list
             quality = file_ver_dict.get('quality_resolution', 'Unknown Quality')
             size_bytes = file_ver_dict.get('file_size_bytes', 0)
             audio_langs = file_ver_dict.get('audio_languages', [])
             subs_langs = file_ver_dict.get('subtitle_languages', [])
             file_id = file_ver_dict.get('file_id') # Get Telegram file_id
             # Note: file_unique_id is needed for internal tracking/deletion, but file_id is for sending.

             # Format file size
             formatted_size = f"{size_bytes / (1024 * 1024):.2f} MB" if size_bytes > 0 else "0 MB"
             if size_bytes >= 1024 * 1024 * 1024: formatted_size = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
             audio_str = ', '.join(audio_langs) if audio_langs else 'N/A'
             subs_str = ', '.join(subs_langs) if subs_langs else 'None'

             # Display full details list above buttons.
             menu_text += f"<b>{i+1}.</b> <b>{quality}</b> ({formatted_size}) 🎧 {audio_str} 📝 {subs_str}\n"


             # Create a button for each downloadable file version
             # Button label shows key details + size. Callback needs anime_id, season, ep, AND file_unique_id to select version.
             # Using file_id directly in callback is problematic as it changes/expires. Use unique_id from DB.
             file_unique_id = file_ver_dict.get("file_unique_id", "missing_unique_id") # Get unique_id for callback
             if file_id and file_unique_id != "missing_unique_id": # Only create button if file_id exists
                  button_label = strings.BUTTON_DOWNLOAD_FILE_USER.format(size=formatted_size) # Use format from strings
                  # Callback: download_confirm_send|<anime_id>|<season>|<ep>|<file_unique_id>
                  buttons.append([InlineKeyboardButton(button_label, callback_data=f"download_confirm_send{config.CALLBACK_DATA_SEPARATOR}{file_unique_id}")]) # Only need unique ID


             else:
                  # File_id or unique_id missing for a version in DB - data error
                  download_logger.error(f"File version dictionary missing file_id or unique_id for {anime_name} S{season_number}E{episode_number}. Cannot create download button.")
                  # User sees the list entry but no button for this item. Inform user? "Error creating button"?
                  # Added to list display already, so this isn't visible unless specific error handling added.


     elif isinstance(release_date, datetime): # Has a release date but no files
          formatted_date = release_date.astimezone(timezone.utc).strftime('%Y-%m-%d')
          menu_text += f"⏳ This episode is scheduled for release on: <b>{formatted_date}</b>.\n\nCheck back later!" # Inform user


     else: # No files and no release date
         menu_text += "❓ No file versions or release date set for this episode yet.\n\n"
         # Maybe prompt user to request? Handled in search no results. Here just inform unavailability.


    # Add navigation buttons: Back to Episode List, Back to Main Menu
    user_state = await MongoDB.get_user_state(user_id) # Get state for context
    if user_state and user_state.handler == "download":
         # Back button returns to episode list for this season (needs anime_id, season_number)
         anime_id_str = user_state.data.get("anime_id")
         season_number_state = user_state.data.get("season_number")

         if anime_id_str and season_number_state is not None:
             buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"download_select_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number_state}")]) # Go back to episode list
         else:
              # Context missing in state for going back to episode list. Safety fallback.
              download_logger.error(f"Missing anime/season context in state data while building version list back button for user {user_id}. State: {user_state.data}")
              buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")]) # Try go back to anime details if ID exists


         buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]) # Main menu

    else: # State is unexpected when displaying versions menu? Log and just add Home.
        download_logger.error(f"Unexpected state when displaying user version list for {user_id}: {user_state}. State data: {user_state.data}")
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])


    reply_markup = InlineKeyboardMarkup(buttons)


    # Edit the episode selection message to display this version list.
    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)

    # State is DownloadState.SELECTING_VERSION, stays until user selects a version, cancels, or navigates back/home.


# --- Handle Download Confirmation / File Sending ---
# Callback triggered when user clicks a Download button on a specific version.
# This handler performs permission checks (premium/tokens) and sends the file.
# Catches callbacks: download_confirm_send|<file_unique_id>
@Client.on_callback_query(filters.regex(f"^download_confirm_send{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def download_confirm_send_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message containing the download buttons
    data = callback_query.data # download_confirm_send|<file_unique_id>

    # Answer immediately to prevent loading, indicate checking permissions.
    try: await client.answer_callback_query(message.id, "Checking permissions...")
    except Exception: download_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")


    user_state = await MongoDB.get_user_state(user_id)

    # State should be DownloadState.SELECTING_VERSION when clicking a download button.
    # Ensure necessary context (anime_id, season, ep, name) is in state data from previous steps.
    if not (user_state and user_state.handler == "download" and user_state.step == DownloadState.SELECTING_VERSION):
        download_logger.warning(f"User {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking download button {data}. State data: {user_state.data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for downloading. Please navigate back to select content.", disable_web_page_preview=True)
        await MongoDB.clear_user_state(user_id); return


    try:
        # Parse the file_unique_id from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for confirming download.")
        file_unique_id = parts[1]

        # Get the anime ID, season, episode context from state data to locate the file in DB
        anime_id_str = user_state.data.get("anime_id")
        season_number = user_state.data.get("season_number")
        episode_number = user_state.data.get("episode_number")
        anime_name = user_state.data.get("anime_name")

        if not all([anime_id_str, season_number is not None, episode_number is not None]):
             download_logger.error(f"User {user_id} clicking download button {data} but missing anime/season/ep context from state data {user_state.step}: {user_state.data}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing context data from state for download. Please select episode again.", disable_web_page_preview=True)
             # State is SELECTING_VERSION, could leave it, but redirect to episode list is better.
             # Needs season_number from state, but validate its presence.
             if anime_id_str and season_number is not None: # Need minimum context to go back to episode list
                  await display_user_episode_list(client, callback_query.message, anime_name or "Anime", season_number, []) # Display empty list? No, fetch current episode list.
             else: await MongoDB.clear_user_state(user_id); return # Cannot go back, clear state


             return


        download_logger.info(f"User {user_id} requesting download of file unique ID {file_unique_id} for {anime_id_str}/S{season_number}E{episode_number}.")


        # --- Retrieve File Details and User Data ---
        # Fetch the episode document that contains the specific file version using a filter and projection/elemMatch.
        filter_query = {
             "_id": ObjectId(anime_id_str),
             "seasons": { "$elemMatch": {"season_number": season_number,
                 "episodes": { "$elemMatch": {"episode_number": episode_number} }
             }}
        }
        projection = {
            "name": 1, # Project name for logging/messages
             "seasons": {
                  "$elemMatch": { # Project matched season
                       "season_number": season_number,
                       "episodes": {
                            "$elemMatch": {
                                 "episode_number": episode_number,
                                 "files": { "$elemMatch": {"file_unique_id": file_unique_id} } # Project only the matching file version
                           }
                      }
                 }
            }
         }

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)


        # Validate if anime/season/episode/file version was found
        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0] or not anime_doc["seasons"][0].get("episodes") or not anime_doc["seasons"][0]["episodes"][0] or not anime_doc["seasons"][0]["episodes"][0].get("files") or not anime_doc["seasons"][0]["episodes"][0]["files"][0]:
             download_logger.error(f"File version {file_unique_id} not found for download for user {user_id} at {anime_id_str}/S{season_number}E{episode_number}. Doc: {anime_doc}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Download file version not found in database.", disable_web_page_preview=True)
             # State is SELECTING_VERSION. Go back to episode view.
             filter_query_episode = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection_episode = {"name": 1, "seasons.$": 1}
             anime_doc_episode = await MongoDB.anime_collection().find_one(filter_query_episode, projection_episode)
             if anime_doc_episode and anime_doc_episode.get("seasons") and anime_doc_episode["seasons"][0]:
                 episodes_list = anime_doc_episode["seasons"][0].get("episodes", [])
                 episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None) # Find specific episode again
                 if episode_doc: await display_user_version_list(client, callback_query.message, anime_doc_episode.get("name", "Anime Name"), season_number, episode_number, episode_doc.get("files", []), episode_doc.get("release_date")) # Redisplay version list

                 else: # Episode gone? Go back to episodes list.
                     episodes_list.sort(key=lambda e: e.get("episode_number", 0))
                     await display_user_episode_list(client, callback_query.message, anime_doc_episode.get("name", "Anime Name"), season_number, episodes_list)

             else:
                  download_logger.error(f"Failed to fetch anime/season after file version not found for user {user_id}. Cannot re-display.")
                  await edit_or_send_message(client, chat_id, message_id, "💔 Error loading download options.", disable_web_page_preview=True)
                  await MongoDB.clear_user_state(user_id);
                  return

            return # Stop execution

        # Access the found file version dictionary using nested structure from projection/elemMatch result
        try:
             # Structure is {"_id":..., "name":..., "seasons": [{"season_number":..., "episodes": [{"episode_number":..., "files":[{"file_id":..., etc.}]}]}]}
             file_version_data_proj = anime_doc["seasons"][0]["episodes"][0]["files"][0] # The deeply nested single matched file version doc
             file_version_data = FileVersion(**file_version_data_proj) # Convert to Pydantic model for easy access

        except (KeyError, IndexError) as e:
             download_logger.error(f"Error accessing deeply nested file version data in projected document for user {user_id} {data}: {e}. Doc: {anime_doc}", exc_info=True)
             await edit_or_send_message(client, chat_id, message_id, "💔 Error accessing file data for download.", disable_web_page_preview=True)
             # State is SELECTING_VERSION. Go back to episode view.
             filter_query_episode = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection_episode = {"name": 1, "seasons.$": 1}
             anime_doc_episode = await MongoDB.anime_collection().find_one(filter_query_episode, projection_episode)
             if anime_doc_episode and anime_doc_episode.get("seasons") and anime_doc_episode["seasons"][0]:
                  anime_name_for_list = anime_doc_episode.get("name", "Anime Name Unknown")
                  episodes_list = anime_doc_episode["seasons"][0].get("episodes", [])
                  episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None)
                  if episode_doc: await display_user_version_list(client, callback_query.message, anime_name_for_list, season_number, episode_number, episode_doc.get("files", []), episode_doc.get("release_date"))
                  else: # Episode gone? Go back to episodes list.
                     episodes_list.sort(key=lambda e: e.get("episode_number", 0))
                     await display_user_episode_list(client, callback_query.message, anime_name_for_list, season_number, episodes_list)
             else:
                 download_logger.error(f"Failed to fetch anime/season after file data access error for user {user_id}. Cannot re-display.")
                 await edit_or_send_message(client, chat_id, message_id, "💔 Error loading download options.", disable_web_page_preview=True)
                 await MongoDB.clear_user_state(user_id);
                 return

             return # Stop execution


        # User should already be fetched in common handlers or entry points, but get current just in case permissions changed.
        user = await get_user(client, user_id) # Use the common helper to get current user data (incl. tokens/premium)
        if user is None:
            download_logger.error(f"Failed to get user {user_id} for download permission check. DB Error.")
            await edit_or_send_message(client, chat_id, message_id, strings.DB_ERROR, disable_web_page_preview=True)
            # State is SELECTING_VERSION, likely okay to stay.
            return


        # --- Permission Check (Premium vs Tokens) ---
        has_permission = False
        required_tokens = 1 # Default tokens needed per file download (based on string format, can make configurable)

        if user.premium_status != "free": # User is Premium
            has_permission = True
            download_logger.debug(f"User {user_id} is Premium. Allowing download for {file_unique_id}.")
            # No token deduction for premium users

        else: # Free User - Check Token Balance
             # Required tokens per file is hardcoded to 1 for string formatting, use config if variable cost per file is needed
            required_tokens = config.TOKENS_PER_REDEEM # Reusing this config for download cost? Or separate? Strings suggest 1 token = 1 file download. Let's stick to 1 fixed for now.
            if user.tokens >= required_tokens:
                 has_permission = True
                 download_logger.debug(f"User {user_id} is Free, has {user.tokens} tokens. Allowing download for {file_unique_id}. Cost: {required_tokens} tokens.")

            else:
                 has_permission = False
                 download_logger.info(f"User {user_id} is Free, has {user.tokens} tokens. Insufficient tokens ({required_tokens}) for download of {file_unique_id}.")
                 # Display insufficient tokens message
                 await edit_or_send_message(client, chat_id, message_id, strings.NOT_ENOUGH_TOKENS.format(required_tokens=required_tokens, user_tokens=user.tokens), disable_web_page_preview=True)
                 # State is SELECTING_VERSION, user can earn tokens and come back.

        # --- If User Has Permission, Send File ---
        if has_permission:
             # Send file loading message to the user. Edit the previous version list message.
             try: await callback_query.message.edit_text(strings.FILE_BEING_SENT, parse_mode=config.PARSE_MODE)
             except (MessageIdInvalid, MessageNotModified) as e:
                  download_logger.warning(f"Failed to edit message {message_id} with FILE_BEING_SENT for user {user_id}: {e}. Sending as new.")
                  await client.send_message(chat_id, strings.FILE_BEING_SENT, parse_mode=config.PARSE_MODE) # Send as new message
             except FloodWait as e:
                  download_logger.warning(f"FloodWait sending FILE_BEING_SENT for user {user_id} (retry in {e.value}s): {e}")
                  await asyncio.sleep(e.value)
                  try: await client.send_message(chat_id, strings.FILE_BEING_SENT, parse_mode=config.PARSE_MODE)
                  except Exception: pass # Give up on loading message

             # --- Perform the file sending using file_id ---
             # Telegram Bot API supports sending files by file_id.
             # The file_id must belong to a file previously uploaded by THIS bot OR stored on Telegram servers and accessible.
             # Our admin file upload saves the file_id received by the bot itself.
             # Use client.send_document or client.send_video based on mime_type if possible, or default to send_document.
             try:
                 # Get mime_type to decide method
                 mime_type = file_version_data.mime_type or ""
                 # Assume common video mime types can use send_video, otherwise use send_document
                 is_video = mime_type.startswith('video/') or (file_version_data.file_name and any(file_version_data.file_name.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm']))

                 if is_video:
                      # Sending video by file_id
                     # Caption optional. Duration, dimensions optional.
                     sent_media = await client.send_video(
                         chat_id=chat_id,
                         video=file_version_data.file_id,
                         # caption=f"{anime_name} S{season_number}E{episode_number:02d} ({file_version_data.quality_resolution})", # Optional caption
                         # duration=file_version_data.duration, # If stored
                         # width=file_version_data.width, # If stored
                         # height=file_version_data.height, # If stored
                         parse_mode=config.PARSE_MODE # For caption if used
                         # Need to handle cases where bot needs to send file from storage channel first to get fresh file_id? Pyrogram handles this.
                     )
                 else: # Default to send_document for documents, audio, etc.
                      # Sending document by file_id
                      sent_media = await client.send_document(
                         chat_id=chat_id,
                         document=file_version_data.file_id,
                         # caption=f"{anime_name} S{season_number}E{episode_number:02d} ({file_version_data.quality_resolution})", # Optional caption
                         file_name=file_version_data.file_name or f"{anime_name} S{season_number}E{episode_number:02d}.dat", # Suggest a filename
                         parse_mode=config.PARSE_MODE # For caption if used
                     )

                 # --- File Sent Successfully ---
                 download_logger.info(f"User {user_id} successfully sent file version {file_unique_id} ({file_version_data.file_id}).")
                 await client.send_message(chat_id, strings.FILE_SENT_SUCCESS, parse_mode=config.PARSE_MODE) # Send confirmation message

                 # --- Deduct Tokens (if not Premium) and Increment Download Counters ---
                 if user.premium_status == "free":
                     try:
                         # Atomically decrement user's token balance using $inc
                         # User model has current token balance BEFORE decrement, for logging.
                         await MongoDB.users_collection().update_one(
                             {"user_id": user_id},
                             {"$inc": {"tokens": -required_tokens}} # Decrement by required_tokens (e.g., 1)
                         )
                         download_logger.info(f"User {user_id}: Deducted {required_tokens} tokens. Old balance: {user.tokens}.")
                         # user.tokens -= required_tokens # Update in-memory user object for potential later use or display
                     except Exception as e:
                          download_logger.error(f"Failed to deduct tokens from user {user_id} after download of {file_unique_id}: {e}", exc_info=True)
                          # This is a database error. Log it. Alert admin? Token consistency issue.
                          # Don't fail the user interaction flow over token deduction failure usually.


                 # Increment overall download count for the user and the anime
                 await MongoDB.increment_download_counts(user_id=user_id, anime_id=anime_id_str)
                 # Could pass episode/file unique ID to update counts on those subdocuments too if needed


             except FileIdInvalid:
                  # The file_id stored in DB is invalid (corrupted, deleted by Telegram).
                  download_logger.error(f"Invalid File ID stored in DB for unique ID {file_unique_id} for {anime_id_str}/S{season_number}E{episode_number} requested by {user_id}. DB File ID: {file_version_data.file_id}.", exc_info=True)
                  await client.send_message(chat_id, "💔 Error sending file: The file ID appears invalid or expired.", parse_mode=config.PARSE_MODE)
                  # This is a data issue in the database. Maybe mark this file version as invalid in DB? Log critical alert.
                  # Admin should check database data integrity.

             except FloodWait as e:
                  download_logger.warning(f"FloodWait while sending file for user {user_id} (retry in {e.value}s) for {file_unique_id}: {e}")
                  # Telegram API limit reached for sending files. Inform user and ask them to try again later.
                  # State is SELECTING_VERSION. Keep it.
                  await client.send_message(chat_id, f"🚦 Too many requests! Please wait {e.value} seconds and try downloading again.", parse_mode=config.PARSE_MODE)
                  # Do NOT clear state. User can click download again after wait.


             except Exception as e:
                  # Generic error during file sending
                  download_logger.error(f"Failed to send file version {file_unique_id} for {anime_id_str}/S{season_number}E{episode_number} to user {user_id}: {e}", exc_info=True)
                  await client.send_message(chat_id, strings.FILE_SEND_ERROR, parse_mode=config.PARSE_MODE) # Generic send error

             # --- Regardless of success/failure after permission check, keep state ---
             # User stays in SELECTING_VERSION state, can try sending same file again (if error occurred),
             # or go back to select different episode/version, or navigate away.


        else:
             # Permission check failed (Insufficient tokens for Free user)
             # Message about insufficient tokens is handled above. State remains SELECTING_VERSION.
             pass # Do nothing further if permission fails


    except ValueError:
        download_logger.warning(f"User {user_id} invalid file unique ID in download confirmation callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid download data.", disable_web_page_preview=True)
        # State is SELECTING_VERSION, stay.


    except Exception as e:
        download_logger.error(f"FATAL error handling download_confirm_send callback {data} for user {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await MongoDB.clear_user_state(user_id);

# Note: The state is NOT cleared after a successful download! User remains on the version selection screen.
# They can download other versions, go back to the episode list, or navigate elsewhere using buttons.
