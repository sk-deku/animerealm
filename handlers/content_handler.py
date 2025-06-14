# handlers/content_handler.py
import logging
import asyncio
from typing import Union, List, Dict, Any
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    Document, Video, Photo
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified
)
from bson import ObjectId # Needed for working with MongoDB IDs


import config
import strings

# Import database models and the MongoDB class
# Correct import for state management: import the MongoDB class itself
from database.mongo_db import MongoDB

# No longer import functions directly from database.mongo_db:
# from database.mongo_db import get_user_state, set_user_state, clear_user_state

# Import database models for type hinting and conversion
from database.models import (
    UserState, Anime, Season, Episode, FileVersion, PyObjectId, model_to_mongo_dict
)

# Import fuzzy matching
from fuzzywuzzy import process

# Import necessary helpers from common_handlers if used (get_user, edit_or_send_message)
# Assume get_user and edit_or_send_message are available or imported where needed
# If not imported in common_handlers and meant to be global helpers, they should be elsewhere.
# Re-defining stubs or importing specific from common.
# Example assuming re-defined stubs exist (for self-containment contextually):
async def get_user(client: Client, user_id: int) -> Optional[User]: pass
async def edit_or_send_message(client: Client, chat_id: int, message_id: Optional[int], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = True): pass


content_logger = logging.getLogger(__name__)


class ContentState:
    AWAITING_ANIME_NAME = "awaiting_anime_name"
    AWAITING_POSTER = "awaiting_poster"
    AWAITING_SYNOPSIS = "awaiting_synopsis"
    AWAITING_TOTAL_SEASONS_COUNT = "awaiting_total_seasons_count"
    SELECTING_GENRES = "selecting_genres"
    AWAITING_RELEASE_YEAR = "awaiting_release_year"
    SELECTING_STATUS = "selecting_status"

    MANAGING_ANIME_MENU = "managing_anime_menu"
    MANAGING_SEASONS_LIST = "managing_seasons_list"
    EDITING_NAME_PROMPT = "editing_name_prompt"
    EDITING_SYNOPSIS_PROMPT = "editing_synopsis_prompt"
    EDITING_POSTER_PROMPT = "editing_poster_prompt"
    EDITING_TOTAL_SEASONS_COUNT_PROMPT = "editing_total_seasons_count_prompt"
    EDITING_RELEASE_YEAR_PROMPT = "editing_release_year_prompt"

    MANAGING_EPISODES_LIST = "managing_episodes_list"

    MANAGING_EPISODE_MENU = "managing_episode_menu"

    AWAITING_RELEASE_DATE_INPUT = "awaiting_release_date_input"
    UPLOADING_FILE = "uploading_file"

    SELECTING_METADATA_QUALITY = "selecting_metadata_quality"
    SELECTING_METADATA_AUDIO = "selecting_metadata_audio"
    SELECTING_METADATA_SUBTITLES = "selecting_metadata_subtitles"

    CONFIRM_REMOVE_SEASON = "confirm_remove_season"
    CONFIRM_REMOVE_EPISODE = "confirm_remove_episode"
    SELECT_FILE_VERSION_TO_DELETE = "select_file_version_to_delete"
    CONFIRM_REMOVE_FILE_VERSION = "confirm_remove_file_version"

    ADMIN_ANIME_LIST_VIEW = "admin_anime_list_view"
    CONFIRM_REMOVE_ANIME = "confirm_remove_anime"


async def handle_content_input(client: Client, message: Message, user_state: UserState):
    user_id = message.from_user.id; chat_id = message.chat.id; input_text = message.text.strip(); current_step = user_state.step;
    content_logger.debug(f"Handling text input for admin {user_id} at step: {current_step} with text: '{input_text[:100]}...'");
    try:
        if current_step == ContentState.AWAITING_ANIME_NAME: await handle_awaiting_anime_name_input(client, message, user_state, input_text);
        elif current_step == ContentState.AWAITING_SYNOPSIS: await handle_awaiting_synopsis_input(client, message, user_state, input_text);
        elif current_step == ContentState.AWAITING_TOTAL_SEASONS_COUNT: await handle_awaiting_total_seasons_count_input(client, message, user_state, input_text);
        elif current_step == ContentState.AWAITING_RELEASE_YEAR: await handle_awaiting_release_year_input(client, message, user_state, input_text);
        elif current_step == ContentState.EDITING_NAME_PROMPT: await handle_editing_name_input(client, message, user_state, input_text);
        elif current_step == ContentState.EDITING_SYNOPSIS_PROMPT: await handle_editing_synopsis_input(client, message, user_state, input_text);
        elif current_step == ContentState.EDITING_TOTAL_SEASONS_COUNT_PROMPT: await handle_editing_total_seasons_count_input(client, message, user_state, input_text);
        elif current_step == ContentState.EDITING_RELEASE_YEAR_PROMPT: await handle_editing_release_year_input(client, message, user_state, input_text);
        elif current_step == ContentState.AWAITING_RELEASE_DATE_INPUT: await handle_awaiting_release_date_input(client, message, user_state, input_text);
        else: content_logger.warning(f"Admin {user_id} sent unexpected text input in CM state {current_step}."); await message.reply_text("🤔 That wasn't the input I was expecting.");
    except Exception as e: content_logger.error(f"FATAL error in handle_content_input for {user_id} at step {current_step}: {e}", exc_info=True); await MongoDB.clear_user_state(user_id); await message.reply_text(strings.ERROR_OCCURRED); await manage_content_command(client, message);


async def handle_media_input(client: Client, message: Message, user_state: UserState):
    user_id = message.from_user.id; chat_id = message.chat.id; current_step = user_state.step;
    content_logger.debug(f"Handling media input for admin {user_id} at step: {current_step}.");
    try:
        if current_step == ContentState.AWAITING_POSTER or current_step == ContentState.EDITING_POSTER_PROMPT:
             if message.photo: await handle_awaiting_poster(client, message, user_state);
             else: await message.reply_text("👆 Please send a **photo** for the poster.");
        elif current_step == ContentState.UPLOADING_FILE:
             if message.document or message.video: await handle_episode_file_upload(client, message, user_state, message.document or message.video);
             else: await message.reply_text("⬆️ Please upload the episode file (video or document).");
        else: content_logger.warning(f"Admin {user_id} sent media while in CM state {current_step} which doesn't expect media."); await message.reply_text("🤷 I'm not expecting a file right now.");
    except Exception as e: content_logger.error(f"FATAL error handling media input for {user_id} in CM state {current_state}: {e}", exc_info=True); await MongoDB.clear_user_state(user_id); await message.reply_text(strings.ERROR_OCCURRED); await manage_content_command(client, message);

# --- Entry Point Handler ---
@Client.on_message(filters.command("manage_content") & filters.private)
async def manage_content_command(client: Client, message: Message):
    user_id = message.from_user.id; chat_id = message.chat.id;
    if user_id not in config.ADMIN_IDS: await message.reply_text("🚫 You are not authorized."); return;
    content_logger.info(f"Admin {user_id} entered CM.");
    try:
        await MongoDB.clear_user_state(user_id); await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={});
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_ADD_NEW_ANIME, callback_data="content_add_new_anime")], [InlineKeyboardButton(strings.BUTTON_EDIT_ANIME, callback_data="content_edit_anime_prompt")], [InlineKeyboardButton(strings.BUTTON_VIEW_ALL_ANIME, callback_data="content_view_all_anime_list")], [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")],]);
        await message.reply_text(f"**{strings.MANAGE_CONTENT_TITLE}**\n\n{strings.MANAGE_CONTENT_OPTIONS}", reply_markup=reply_markup, parse_mode=config.PARSE_MODE);
    except Exception as e: content_logger.error(f"Failed to send CM menu to {user_id}: {e}", exc_info=True); await message.reply_text(strings.ERROR_OCCURRED);


@Client.on_callback_query(filters.regex("^content_(?!toggle|select|done|confirm_remove_file_version$).*") & filters.private)
async def content_main_menu_callbacks(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id; data = callback_query.data;
    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 Unauthorized."); return;
    try: await callback_query.answer(); except Exception: content_logger.warning(f"Failed to answer callback {data} from {user_id}.");
    user_state = await MongoDB.get_user_state(user_id);
    if user_state is None or user_state.handler != "content_management": content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking {data}. Resetting."); await manage_content_command(client, callback_query.message); return;

    try:
        if data == "content_add_new_anime": await MongoDB.set_user_state(user_id, "content_management", ContentState.AWAITING_ANIME_NAME, data={"purpose": "add"}); await edit_or_send_message(client, chat_id, message_id, strings.ADD_ANIME_NAME_PROMPT, InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]));
        elif data == "content_edit_anime_prompt": await MongoDB.set_user_state(user_id, "content_management", ContentState.AWAITING_ANIME_NAME, data={"purpose": "edit"}); await edit_or_send_message(client, chat_id, message_id, strings.ADD_ANIME_NAME_PROMPT, InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]));
        elif data == "content_view_all_anime_list": await handle_admin_view_all_anime_list(client, callback_query.message, user_state, 1);
        elif data == "content_management_main_menu": await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU); reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_ADD_NEW_ANIME, callback_data="content_add_new_anime")], [InlineKeyboardButton(strings.BUTTON_EDIT_ANIME, callback_data="content_edit_anime_prompt")], [InlineKeyboardButton(strings.BUTTON_VIEW_ALL_ANIME, callback_data="content_view_all_anime_list")], [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")],]); await edit_or_send_message(client, chat_id, message_id, f"**{strings.MANAGE_CONTENT_TITLE}**\n\n{strings.MANAGE_CONTENT_OPTIONS}", reply_markup, disable_web_page_preview=True);
        elif data == "content_cancel": await MongoDB.clear_user_state(user_id); await edit_or_send_message(client, chat_id, message_id, strings.ACTION_CANCELLED);
        elif data.startswith("content_edit_existing|"): anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; await handle_edit_existing_anime_selection(client, callback_query.message, user_state, anime_id_str);
        elif data.startswith("content_proceed_add_new|"): new_anime_name = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; await handle_proceed_add_new_anime(client, callback_query.message, user_state, new_anime_name);
        elif data.startswith("content_manage_seasons|"):
             anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; if not user_state.step == ContentState.MANAGING_ANIME_MENU: content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step} clicking manage seasons {data}. State data: {user_state.data}"); await callback_query.message.reply_text("🔄 Invalid state.", parse_mode=config.PARSE_MODE); return;
             await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data={**user_state.data, "anime_id": anime_id_str});
             anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1});
             if not anime_doc: content_logger.error(f"Anime {anime_id_str} not found for CM by {user_id}."); await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found."); await MongoDB.clear_user_state(user_id); return;
             await display_seasons_management_menu(client, callback_query.message, Anime(**anime_doc));
        elif data.startswith("content_edit_name|"): await handle_edit_name_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_edit_synopsis|"): await handle_edit_synopsis_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_edit_poster|"): await handle_edit_poster_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_edit_genres|"): await handle_edit_genres_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_edit_year|"): await handle_edit_year_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_edit_status|"): await handle_edit_status_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_edit_total_seasons_count|"): await handle_edit_total_seasons_count_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_add_new_season|"): await handle_add_new_season_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_remove_season_select|"): await handle_remove_season_select_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_confirm_remove_season|"): await handle_confirm_remove_season_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_select_season|"): await handle_select_season_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_manage_episode|"): await handle_select_episode_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_add_file_version|"): await handle_add_file_version_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_add_release_date|"): await handle_add_release_date_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_go_next_episode|"): await handle_go_next_episode_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_remove_episode|"): await handle_remove_episode_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_delete_file_version_select|"): await handle_delete_file_version_select_callback(client, callback_query.message, user_state, data);
        elif data.startswith("content_delete_anime_prompt|"): await handle_delete_anime_prompt(client, callback_query.message, user_state, data);
        else: content_logger.warning(f"Admin {user_id} clicked unhandled content_ callback {data} in state {user_state.step}. State data: {user_state.data}"); await callback_query.answer("⚠️ This action is not implemented yet or invalid.", show_alert=False);

    except ValueError as e: content_logger.error(f"Invalid callback data for {user_id} clicking {data}: {e}", exc_info=True); await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid data.", disable_web_page_preview=True);
    except Exception as e: content_logger.error(f"FATAL error processing content callback {data} for {user_id}: {e}", exc_info=True); await MongoDB.clear_user_state(user_id); await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED); await manage_content_command(client, callback_query.message);


async def handle_awaiting_anime_name_input(client: Client, message: Message, user_state: UserState, anime_name_input: str):
    user_id = message.from_user.id; chat_id = message.chat.id;
    try:
        anime_name_docs = await MongoDB.anime_collection().find({}, {"name": 1}).to_list(None);
        anime_names_dict = {doc['name']: str(doc['_id']) for doc in anime_name_docs};
        search_results = process.extract(anime_name_input, list(anime_names_dict.keys()), limit=10); content_logger.info(f"Fuzzy search for '{anime_name_input}' by {user_id} in AWAITING_ANIME_NAME returned {len(search_results)} matches.");
        matching_anime = []; for name_match, score in search_results: if score >= config.FUZZYWUZZY_THRESHOLD: anime_id_str = anime_names_dict.get(name_match); if anime_id_str: matching_anime.append({"_id": anime_id_str, "name": name_match, "score": score}); content_logger.debug(f"Filtered fuzzy search ({len(matching_anime)}) for {user_id}: {matching_anime}");
    except Exception as e: content_logger.error(f"Error during fuzzy search for anime name '{anime_name_input}' by {user_id}: {e}", exc_info=True); await message.reply_text("💔 Error performing search."); return;

    purpose = user_state.data.get("purpose", "add");
    if purpose == "add":
         if matching_anime: response_text = strings.ADD_ANIME_NAME_SEARCH_RESULTS.format(name=anime_name_input); buttons = []; for match in matching_anime: buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing{config.CALLBACK_DATA_SEPARATOR}{match['_id']}")]); encoded_anime_name = anime_name_input; buttons.append([InlineKeyboardButton(strings.BUTTON_ADD_AS_NEW_ANIME.format(name=anime_name_input), callback_data=f"content_proceed_add_new{config.CALLBACK_DATA_SEPARATOR}{encoded_anime_name}")]); buttons.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]); reply_markup = InlineKeyboardMarkup(buttons); await message.reply_text(response_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE);
         else: await handle_proceed_add_new_anime(client, message, user_state, anime_name_input);
    elif purpose == "edit":
        if matching_anime: response_text = f"🔍 Found these anime matching '<code>{anime_name_input}</code>'. Select one to <b><u>edit</u></b>: 👇"; buttons = []; for match in matching_anime: buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing{config.CALLBACK_DATA_SEPARATOR}{match['_id']}")]); buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="content_edit_anime_prompt")]); buttons.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]); reply_markup = InlineKeyboardMarkup(buttons); await message.reply_text(response_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE);
        else: await message.reply_text(f"😔 Couldn't find any anime matching '<code>{anime_name_input}</code>' for editing. Please try a different name or type '❌ Cancel'.", parse_mode=config.PARSE_MODE);
    else: content_logger.error(f"Admin {user_id} in AWAITING_ANIME_NAME with invalid purpose: {purpose}.", exc_info=True); await message.reply_text("🤷 Invalid state data."); await MongoDB.clear_user_state(user_id);

async def handle_proceed_add_new_anime(client: Client, message: Message, user_state: UserState, anime_name: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id if isinstance(message, Message) else message.message.id;
    content_logger.info(f"Admin {user_id} proceeding to add new anime with name: '{anime_name}'.");
    if user_state.handler == "content_management" and user_state.step == ContentState.AWAITING_ANIME_NAME: await MongoDB.clear_user_state(user_id);
    await MongoDB.set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={"new_anime_name": anime_name});
    await prompt_for_poster(client, chat_id, anime_name);
    try: if isinstance(message, CallbackQuery): await message.message.edit_text(f"✅ Adding: <b>{anime_name}</b>\n\nSent prompt for poster."); else: await message.reply_text(f"✅ Okay, adding: <b>{anime_name}</b>", parse_mode=config.PARSE_MODE);
    except Exception as e: content_logger.warning(f"Failed confirm message for {user_id}: {e}");


async def handle_edit_existing_anime_selection(client: Client, message: Message, user_state: UserState, anime_id_str: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
     content_logger.info(f"Admin {user_id} selected existing ID {anime_id_str} for editing.");
     if user_state.handler == "content_management" and user_state.step == ContentState.AWAITING_ANIME_NAME: await MongoDB.clear_user_state(user_id);
     try:
         anime = await MongoDB.get_anime_by_id(anime_id_str);
         if not anime: content_logger.error(f"Admin {user_id} tried to edit non-existent ID: {anime_id_str} after selection."); await edit_or_send_message(client, chat_id, message_id, "💔 Anime not found."); await manage_content_command(client, message); return;
         content_logger.info(f"Admin {user_id} managing anime '{anime.name}' ({anime.id}).");
         await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(anime.id), "anime_name": anime.name});
         await display_anime_management_menu(client, message, anime);
     except Exception as e: content_logger.error(f"Error loading anime {anime_id_str} for {user_id}: {e}", exc_info=True); await edit_or_send_message(client, chat_id, message_id, "💔 Error loading details."); await MongoDB.clear_user_state(user_id);






async def display_anime_management_menu(client: Client, message: Message, anime: Anime):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
     menu_text = f"🛠️ <b><u>Managing</u></b> <b>{anime.name}</b> 🛠️\n";
     if anime.synopsis: menu_text += f"📚 <b><u>Synopsis</u></b>:<blockquote>{anime.synopsis[:300] + '...' if len(anime.synopsis) > 300 else anime.synopsis}</blockquote>\n";
     if anime.poster_file_id: menu_text += "🖼️ Poster set.\n";
     menu_text += f"🏷️ <b><u>Genres</u></b>: {', '.join(anime.genres) if anime.genres else 'Not set'}\n";
     menu_text += f"🗓️ <b><u>Release Year</u></b>: {anime.release_year if anime.release_year else 'Not set'}\n"
     menu_text += f"🚦 <b><u>Status</u></b>: {anime.status if anime.status else 'Not set'}\n"
     menu_text += f"🌟 <b><u>Total Seasons Declared</u></b>: {anime.total_seasons_declared}\n"
     # Count actual files - iterate seasons and episodes arrays
     actual_files_count = 0
     if anime.seasons:
          for season_doc in anime.seasons: # season_doc is Pydantic model here
               if season_doc.episodes:
                    for episode_doc in season_doc.episodes: # episode_doc is Pydantic model
                         if episode_doc.files:
                              actual_files_count += len(episode_doc.files) # files is list of FileVersion models


     menu_text += f"📁 Files Uploaded: {actual_files_count} Versions Total\n"
     menu_text += f"\n👇 Select an option to edit details or manage content structure:"

     buttons = [
         [InlineKeyboardButton(strings.BUTTON_MANAGE_SEASONS_EPISODES, callback_data=f"content_manage_seasons{config.CALLBACK_DATA_SEPARATOR}{anime.id}")],
         [
            InlineKeyboardButton(strings.BUTTON_EDIT_NAME, callback_data=f"content_edit_name{config.CALLBACK_DATA_SEPARATOR}{anime.id}"),
            InlineKeyboardButton(strings.BUTTON_EDIT_SYNOPSIS, callback_data=f"content_edit_synopsis{config.CALLBACK_DATA_SEPARATOR}{anime.id}")
         ],
         [
            InlineKeyboardButton(strings.BUTTON_EDIT_POSTER, callback_data=f"content_edit_poster{config.CALLBACK_DATA_SEPARATOR}{anime.id}"),
            InlineKeyboardButton(strings.BUTTON_EDIT_GENRES, callback_data=f"content_edit_genres{config.CALLBACK_DATA_SEPARATOR}{anime.id}")
         ],
         [
            InlineKeyboardButton(strings.BUTTON_EDIT_YEAR, callback_data=f"content_edit_year{config.CALLBACK_DATA_SEPARATOR}{anime.id}"),
            InlineKeyboardButton(strings.BUTTON_EDIT_STATUS, callback_data=f"content_edit_status{config.CALLBACK_DATA_SEPARATOR}{anime.id}")
         ],
         [InlineKeyboardButton(strings.BUTTON_EDIT_TOTAL_SEASONS, callback_data=f"content_edit_total_seasons_count{config.CALLBACK_DATA_SEPARATOR}{anime.id}")],
         [InlineKeyboardButton("💀 Delete This Anime", callback_data=f"content_delete_anime_prompt{config.CALLBACK_DATA_SEPARATOR}{anime.id}")],
         [InlineKeyboardButton(strings.BUTTON_BACK, callback_data="content_view_all_anime_list")],
         [InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")],
         [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")],
     ]
     reply_markup = InlineKeyboardMarkup(buttons)

     await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True)


async def handle_awaiting_poster(client: Client, message: Message, user_state: UserState):
    user_id = message.from_user.id; chat_id = message.chat.id;
    file_id = message.photo[-1].file_id;
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")); purpose = user_state.data.get("purpose", "add");
    content_logger.info(f"Admin {user_id} provided poster photo ({file_id}) for '{anime_name}' in AWAITING_POSTER state (Purpose: {purpose}).");
    if purpose == "add":
        user_state.data["poster_file_id"] = file_id; await MongoDB.set_user_state(user_id, "content_management", ContentState.AWAITING_SYNOPSIS, data=user_state.data);
        await prompt_for_synopsis(client, chat_id, anime_name);
        await message.reply_text(f"🖼️ Poster received! Now send the **<u>Synopsis</u>** for {anime_name}.", parse_mode=config.PARSE_MODE);
    elif purpose == "edit":
         anime_id_str = user_state.data.get("anime_id");
         if not anime_id_str: content_logger.error(f"Admin {user_id} in EDIT AWAITING_POSTER missing anime_id."); await message.reply_text("💔 Error: Anime ID missing. Cannot update poster."); await MongoDB.clear_user_state(user_id); return;
         try:
             update_result = await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"poster_file_id": file_id, "last_updated_at": datetime.now(timezone.utc)}});
             if update_result.matched_count > 0 and update_result.modified_count > 0: content_logger.info(f"Admin {user_id} updated poster for {anime_id_str}."); await message.reply_text("✅ Poster updated!", parse_mode=config.PARSE_MODE);
             elif update_result.matched_count > 0: content_logger.info(f"Admin {user_id} sent poster for {anime_id_str} but was unchanged."); await message.reply_text("✅ Poster appears unchanged.", parse_mode=config.PARSE_MODE);
             else: content_logger.error(f"Anime {anime_id_str} not found for update by {user_id}."); await message.reply_text("💔 Anime not found for update."); await MongoDB.clear_user_state(user_id); return;
             updated_anime = await MongoDB.get_anime_by_id(anime_id_str);
             if updated_anime: await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name}); await asyncio.sleep(1); await display_anime_management_menu(client, message, updated_anime);
             else: content_logger.error(f"Failed to fetch updated anime {anime_id_str} for {user_id}."); await message.reply_text("💔 Updated poster, failed to load menu. Navigate back."); await manage_content_command(client, message);
         except Exception as e: content_logger.error(f"Error updating poster for {anime_id_str} by {user_id}: {e}", exc_info=True); await message.reply_text("💔 Error updating poster.");
    else: content_logger.error(f"Admin {user_id} in AWAITING_POSTER state with invalid purpose: {purpose}.", exc_info=True); await message.reply_text("🤷 Unexpected data in state."); await MongoDB.clear_user_state(user_id);


async def prompt_for_synopsis(client: Client, chat_id: int, anime_name: str):
    prompt_text = strings.ADD_ANIME_SYNOPSIS_PROMPT.format(anime_name=anime_name); reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]);
    try: await client.send_message(chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE);
    except Exception as e: content_logger.error(f"Failed to send synopsis prompt to {chat_id}: {e}", exc_info=True);


async def handle_awaiting_synopsis_input(client: Client, message: Message, user_state: UserState, synopsis_text: str):
    user_id = message.from_user.id; chat_id = message.chat.id; current_step = user_state.step;
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")); anime_id_str = user_state.data.get("anime_id");
    content_logger.info(f"Admin {user_id} provided synopsis text (step {current_step}) for '{anime_name}': '{synopsis_text[:100]}...'");

    if current_step == ContentState.AWAITING_SYNOPSIS:
        user_state.data["synopsis"] = synopsis_text; await MongoDB.set_user_state(user_id, "content_management", ContentState.AWAITING_TOTAL_SEASONS_COUNT, data=user_state.data);
        await prompt_for_total_seasons_count(client, chat_id, anime_name); await message.reply_text(f"📝 Synopsis received. Send **<u>Total Seasons</u>**.", parse_mode=config.PARSE_MODE);
    elif current_step == ContentState.EDITING_SYNOPSIS_PROMPT:
        if not anime_id_str: content_logger.error(f"Admin {user_id} in EDITING_SYNOPSIS_PROMPT missing anime_id."); await message.reply_text("💔 Error: Anime ID missing."); await MongoDB.clear_user_state(user_id); return;
        try:
            update_result = await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"synopsis": synopsis_text, "last_updated_at": datetime.now(timezone.utc)}});
            if update_result.matched_count > 0 and update_result.modified_count > 0: content_logger.info(f"Admin {user_id} updated synopsis for {anime_id_str}."); await message.reply_text("✅ Synopsis updated!", parse_mode=config.PARSE_MODE);
            elif update_result.matched_count > 0: content_logger.info(f"Admin {user_id} sent synopsis for {anime_id_str} but unchanged."); await message.reply_text("✅ Synopsis unchanged.");
            else: content_logger.error(f"Anime {anime_id_str} not found for update by {user_id}."); await message.reply_text("💔 Anime not found."); await MongoDB.clear_user_state(user_id); return;
            updated_anime = await MongoDB.get_anime_by_id(anime_id_str); if updated_anime: await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name}); await asyncio.sleep(1); await display_anime_management_menu(client, message, updated_anime);
            else: content_logger.error(f"Failed fetch {anime_id_str} after synopsis update for {user_id}."); await message.reply_text("💔 Updated synopsis, failed to load menu."); await manage_content_command(client, message);
        except Exception as e: content_logger.error(f"Error updating synopsis for {anime_id_str} by {user_id}: {e}", exc_info=True); await message.reply_text("💔 Error updating synopsis.");
    else: content_logger.error(f"Admin {user_id} sent synopsis in unexpected state {current_step}.", exc_info=True); await message.reply_text("🤷 Unexpected state."); await MongoDB.clear_user_state(user_id);


async def prompt_for_total_seasons_count(client: Client, chat_id: int, anime_name: str):
    prompt_text = strings.ADD_ANIME_SEASONS_PROMPT.format(anime_name=anime_name); reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]);
    try: await client.send_message(chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE);
    except Exception as e: content_logger.error(f"Failed to send seasons prompt to {chat_id}: {e}", exc_info=True);

async def handle_awaiting_total_seasons_count_input(client: Client, message: Message, user_state: UserState, count_text: str):
    user_id = message.from_user.id; chat_id = message.chat.id; current_step = user_state.step;
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")); anime_id_str = user_state.data.get("anime_id");
    content_logger.info(f"Admin {user_id} provided seasons count ({count_text}) for '{anime_name}' at step {current_step}.");

    try: seasons_count = int(count_text); if seasons_count < 0: raise ValueError("Negative count not allowed");
    except ValueError: await message.reply_text("🚫 Send a **<u>non-negative number</u>**.", parse_mode=config.PARSE_MODE); return;

    if current_step == ContentState.AWAITING_TOTAL_SEASONS_COUNT:
        user_state.data["total_seasons_declared"] = seasons_count; await MongoDB.set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data=user_state.data);
        await prompt_for_genres(client, chat_id, anime_name, user_state.data.get("selected_genres", [])); await message.reply_text(f"📺 Seasons (<b>{seasons_count}</b>) received. Select **<u>Genres</u>**.", parse_mode=config.PARSE_MODE);
    elif current_step == ContentState.EDITING_TOTAL_SEASONS_COUNT_PROMPT:
        if not anime_id_str: content_logger.error(f"Admin {user_id} in EDITING_TOTAL missing anime_id."); await message.reply_text("💔 Error: Anime ID missing."); await MongoDB.clear_user_state(user_id); return;
        try:
            update_result = await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"total_seasons_declared": seasons_count, "last_updated_at": datetime.now(timezone.utc)}});
            if update_result.matched_count > 0 and update_result.modified_count > 0: content_logger.info(f"Admin {user_id} updated seasons for {anime_id_str} to {seasons_count}."); await message.reply_text(f"✅ Total seasons updated to **<u>{seasons_count}</u>**!", parse_mode=config.PARSE_MODE);
            elif update_result.matched_count > 0: content_logger.info(f"Admin {user_id} sent seasons for {anime_id_str} but unchanged."); await message.reply_text(f"✅ Total seasons count is already <b>{seasons_count}</b>.", parse_mode=config.PARSE_MODE);
            else: content_logger.error(f"Anime {anime_id_str} not found for update by {user_id}."); await message.reply_text("💔 Anime not found for update."); await MongoDB.clear_user_state(user_id); return;
            updated_anime = await MongoDB.get_anime_by_id(anime_id_str); if updated_anime: await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name}); await asyncio.sleep(1); await display_anime_management_menu(client, message, updated_anime);
            else: content_logger.error(f"Failed fetch {anime_id_str} after seasons update for {user_id}."); await message.reply_text("💔 Updated seasons, failed to load menu."); await manage_content_command(client, message);
        except Exception as e: content_logger.error(f"Error updating seasons for {anime_id_str} by {user_id}: {e}", exc_info=True); await message.reply_text("💔 Error updating total seasons.");
    else: content_logger.error(f"Admin {user_id} sent seasons count in unexpected state {current_step}.", exc_info=True); await message.reply_text("🤷 Unexpected state data."); await MongoDB.clear_user_state(user_id);

async def prompt_for_genres(client: Client, chat_id: int, anime_name: str, current_selection: List[str]):
    prompt_text = strings.ADD_ANIME_GENRES_PROMPT.format(anime_name=anime_name); genres_presets = config.INITIAL_GENRES; buttons = [];
    for genre in genres_presets: is_selected = genre in current_selection; button_text = f"✅ {genre}" if is_selected else f"⬜ {genre}"; buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}{genre}"));
    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)];
    keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Genres"), callback_data="content_genres_done"), InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]);
    reply_markup = InlineKeyboardMarkup(keyboard_rows);
    try: await client.send_message(chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True);
    except Exception as e: content_logger.error(f"Failed to send genres prompt to {chat_id}: {e}", exc_info=True);

@Client.on_callback_query(filters.regex(f"^content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_toggle_genre_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id; data = callback_query.data;
    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 Unauthorized."); return; try: await callback_query.answer(); except Exception: content_logger.warning(f"Failed to answer callback {data} from {user_id}.");
    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_GENRES): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please restart.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id); await manage_content_command(client, callback_query.message); return;

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 2: raise ValueError("Invalid callback data format."); genre_to_toggle = parts[1];
        selected_genres = user_state.data.get("selected_genres", []);
        if genre_to_toggle not in config.INITIAL_GENRES: content_logger.warning(f"Admin {user_id} attempted toggle non-preset genre: {genre_to_toggle}."); await callback_query.answer("🚫 Invalid genre option."); return;
        if genre_to_toggle in selected_genres: selected_genres.remove(genre_to_toggle); content_logger.debug(f"Admin {user_id} unselected genre: {genre_to_toggle}");
        else: selected_genres.append(genre_to_toggle); content_logger.debug(f"Admin {user_id} selected genre: {genre_to_toggle}");
        selected_genres.sort(); user_state.data["selected_genres"] = selected_genres;
        await MongoDB.set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data=user_state.data);
        genres_presets = config.INITIAL_GENRES; buttons = []; for genre in genres_presets: is_selected = genre in selected_genres; button_text = f"✅ {genre}" if is_selected else f"⬜ {genre}"; buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}{genre}"));
        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)];
        keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Genres"), callback_data="content_genres_done"), InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]);
        reply_markup = InlineKeyboardMarkup(keyboard_rows);
        try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup); except MessageNotModified: pass; except FloodWait as e: content_logger.warning(f"FloodWait editing buttons for {user_id}: {e.value}"); await asyncio.sleep(e.value); try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup); except Exception as retry_e: content_logger.error(f"Retry failed for {user_id}: {retry_e}", exc_info=True);
    except Exception as e: content_logger.error(f"FATAL error handling toggle genre callback {data} for {user_id}: {e}", exc_info=True); await MongoDB.clear_user_state(user_id); try: await callback_query.answer(strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);


@Client.on_callback_query(filters.regex("^content_genres_done$") & filters.private)
async def handle_genres_done_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id;
    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 Unauthorized."); return; try: await callback_query.answer("Genres selected. Proceeding..."); except Exception: content_logger.warning(f"Failed answer callback content_genres_done for {user_id}.");
    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_GENRES): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please restart."); await MongoDB.clear_user_state(user_id); await manage_content_command(client, callback_query.message); return;
    selected_genres = user_state.data.get("selected_genres", []); anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime Name Unknown")); anime_id_str = user_state.data.get("anime_id"); purpose = user_state.data.get("purpose", "add");
    content_logger.info(f"Admin {user_id} finished selecting genres ({purpose}) for '{anime_name}': {selected_genres}");

    if purpose == "add":
        user_state.data["genres"] = selected_genres; await MongoDB.set_user_state(user_id, "content_management", ContentState.AWAITING_RELEASE_YEAR, data=user_state.data);
        await prompt_for_release_year(client, chat_id, anime_name);
        try: await callback_query.message.edit_text(f"🏷️ Genres saved: <b>{', '.join(selected_genres) if selected_genres else 'None'}</b>. Send **<u>Release Year</u>**.", parse_mode=config.PARSE_MODE); except Exception as e: content_logger.warning(f"Failed edit message after genres done for {user_id}: {e}"); await client.send_message(chat_id, f"✅ Genres saved. Send **<u>Release Year</u>**.", parse_mode=config.PARSE_MODE);
    elif purpose == "edit":
        if not anime_id_str: content_logger.error(f"Admin {user_id} in SELECTING_GENRES (edit) missing anime_id."); await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime ID missing."); await MongoDB.clear_user_state(user_id); return;
        try:
            update_result = await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"genres": selected_genres, "last_updated_at": datetime.now(timezone.utc)}});
            if update_result.matched_count > 0 and update_result.modified_count > 0: content_logger.info(f"Admin {user_id} updated genres for {anime_id_str}."); await callback_query.message.edit_text(f"✅ Genres updated: <b>{', '.join(selected_genres) if selected_genres else 'None'}</b>!", parse_mode=config.PARSE_MODE);
            elif update_result.matched_count > 0: content_logger.info(f"Admin {user_id} sent genres for {anime_id_str} but unchanged."); await callback_query.message.edit_text(f"✅ Genres unchanged.", parse_mode=config.PARSE_MODE);
            else: content_logger.error(f"Anime {anime_id_str} not found for update by {user_id}."); await message.reply_text("💔 Anime not found for update."); await MongoDB.clear_user_state(user_id); return;
            updated_anime = await MongoDB.get_anime_by_id(anime_id_str); if updated_anime: await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name}); await asyncio.sleep(1); await display_anime_management_menu(client, callback_query.message, updated_anime);
            else: content_logger.error(f"Failed fetch {anime_id_str} after genres update for {user_id}."); await client.send_message(chat_id, "💔 Updated genres, failed to load menu.", parse_mode=config.PARSE_MODE); await manage_content_command(client, callback_query.message);
        except Exception as e: content_logger.error(f"Error updating genres for {anime_id_str} by {user_id}: {e}", exc_info=True); await client.send_message(chat_id, "💔 Error updating genres."); await MongoDB.clear_user_state(user_id);

    else: content_logger.error(f"Admin {user_id} finished genre selection with invalid purpose: {purpose}.", exc_info=True); await edit_or_send_message(client, chat_id, message_id, "🤷 Unexpected data.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id);


async def prompt_for_release_year(client: Client, chat_id: int, anime_name: str):
    prompt_text = strings.ADD_ANIME_YEAR_PROMPT.format(anime_name=anime_name); reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]);
    try: await client.send_message(chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE);
    except Exception as e: content_logger.error(f"Failed to send year prompt to {chat_id}: {e}", exc_info=True);

async def handle_awaiting_release_year_input(client: Client, message: Message, user_state: UserState, year_text: str):
    user_id = message.from_user.id; chat_id = message.chat.id; current_step = user_state.step;
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime")); anime_id_str = user_state.data.get("anime_id");
    content_logger.info(f"Admin {user_id} provided release year ({year_text}) for '{anime_name}' at step {current_step}.");

    try: release_year = int(year_text); if not (1000 <= release_year <= datetime.now().year + 5): raise ValueError("Year out of range"); # Basic year check
    except ValueError: await message.reply_text("🚫 Send a **<u>valid year</u>** (e.g., 2024).", parse_mode=config.PARSE_MODE); return;

    if current_step == ContentState.AWAITING_RELEASE_YEAR:
        user_state.data["release_year"] = release_year; await MongoDB.set_user_state(user_id, "content_management", ContentState.SELECTING_STATUS, data=user_state.data);
        await prompt_for_status(client, chat_id, anime_name); await message.reply_text(f"🗓️ Year (<b>{release_year}</b>) received. Select **<u>Status</u>**.", parse_mode=config.PARSE_MODE);
    elif current_step == ContentState.EDITING_RELEASE_YEAR_PROMPT:
        if not anime_id_str: content_logger.error(f"Admin {user_id} in EDITING_RELEASE_YEAR_PROMPT missing anime_id."); await message.reply_text("💔 Error: Anime ID missing."); await MongoDB.clear_user_state(user_id); return;
        try:
            update_result = await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"release_year": release_year, "last_updated_at": datetime.now(timezone.utc)}});
            if update_result.matched_count > 0 and update_result.modified_count > 0: content_logger.info(f"Admin {user_id} updated year for {anime_id_str} to {release_year}."); await message.reply_text(f"✅ Year updated to **<u>{release_year}</u>**!", parse_mode=config.PARSE_MODE);
            elif update_result.matched_count > 0: content_logger.info(f"Admin {user_id} sent year for {anime_id_str} but unchanged."); await message.reply_text(f"✅ Year is already <b>{release_year}</b>.");
            else: content_logger.error(f"Anime {anime_id_str} not found for update by {user_id}."); await message.reply_text("💔 Anime not found."); await MongoDB.clear_user_state(user_id); return;
            updated_anime = await MongoDB.get_anime_by_id(anime_id_str); if updated_anime: await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name}); await asyncio.sleep(1); await display_anime_management_menu(client, message, updated_anime);
            else: content_logger.error(f"Failed fetch {anime_id_str} after year update for {user_id}."); await message.reply_text("💔 Updated year, failed to load menu."); await manage_content_command(client, message);
        except Exception as e: content_logger.error(f"Error updating year for {anime_id_str} by {user_id}: {e}", exc_info=True); await message.reply_text("💔 Error updating year.");
    else: content_logger.error(f"Admin {user_id} sent year in unexpected state {current_step}.", exc_info=True); await message.reply_text("🤷 Unexpected state."); await MongoDB.clear_user_state(user_id);


async def prompt_for_status(client: Client, chat_id: int, anime_name: str, current_selection: Optional[str] = None):
    prompt_text = strings.ADD_ANIME_STATUS_PROMPT.format(anime_name=anime_name); status_presets = config.ANIME_STATUSES; buttons = [];
    for status in status_presets: button_text = f"✅ {status}" if current_selection and status == current_selection else status; buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_select_status{config.CALLBACK_DATA_SEPARATOR}{status}"));
    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]; keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]);
    reply_markup = InlineKeyboardMarkup(keyboard_rows);
    try: await client.send_message(chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True);
    except Exception as e: content_logger.error(f"Failed to send status prompt to {chat_id}: {e}", exc_info=True);

@Client.on_callback_query(filters.regex(f"^content_select_status{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_select_status_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id; chat_id = callback_query.message.chat.id; message_id = callback_query.message.id; data = callback_query.data;
    if user_id not in config.ADMIN_IDS: await callback_query.answer("🚫 Unauthorized."); return; try: await callback_query.answer(); except Exception: content_logger.warning(f"Failed to answer callback {data} for {user_id}.");
    user_state = await MongoDB.get_user_state(user_id);
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_STATUS): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state."); await MongoDB.clear_user_state(user_id); await manage_content_command(client, callback_query.message); return;
    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR); if len(parts) != 2: raise ValueError("Invalid callback data format."); selected_status = parts[1];
        if selected_status not in config.ANIME_STATUSES:
             content_logger.warning(f"Admin {user_id} attempted to select non-preset status: {selected_status}.");
             await callback_query.answer("🚫 Invalid status option."); # Use toast
             # Do not clear state or re-prompt, user just needs to click a valid button
             return # Stop processing this invalid selection


        # Store the selected status in user's state data.
        user_state.data["status"] = selected_status; # Store selected status

        # Get context (anime name, ID, purpose)
        anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime"));
        anime_id_str = user_state.data.get("anime_id");
        purpose = user_state.data.get("purpose", "add");

        content_logger.info(f"Admin {user_id} selected status '{selected_status}' ({purpose}) for '{anime_name}'.");

        # --- Proceed based on purpose (Add New vs Edit Existing) ---
        if purpose == "add":
            # Add New Anime flow - Create and Insert the New Anime Document into Database.
            # Collect all data from state.data: name, poster_file_id, synopsis, total_seasons_declared, genres, release_year, status
            new_anime_data_dict = {
                 "name": user_state.data.get("new_anime_name"),
                 "poster_file_id": user_state.data.get("poster_file_id"),
                 "synopsis": user_state.data.get("synopsis"),
                 "total_seasons_declared": user_state.data.get("total_seasons_declared", 0),
                 "genres": user_state.data.get("genres", []),
                 "release_year": user_state.data.get("release_year"),
                 "status": user_state.data.get("status"), # Status should be in state data now
                 "seasons": [], # Always start empty for new anime, added later
                 "overall_download_count": 0,
                 "last_updated_at": datetime.now(timezone.utc)
            };
            # Validate minimum required fields
            if not new_anime_data_dict.get("name") or not new_anime_data_dict.get("status"):
                content_logger.error(f"Admin {user_id} finished add flow, missing name or status in state! Data: {user_state.data}");
                await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing critical data to create anime. Process cancelled."); await MongoDB.clear_user_state(user_id); return;

            # Use Pydantic model to validate data structure before inserting
            try: new_anime = Anime(**new_anime_data_dict);
            except Exception as e: content_logger.error(f"Error validating Anime model for {user_id}: {e}. Data: {new_anime_data_dict}", exc_info=True); await edit_or_send_message(client, chat_id, message_id, "💔 Error validating data structure."); await MongoDB.clear_user_state(user_id); return;

            # Insert the new anime document into the database
            try:
                insert_result = await MongoDB.anime_collection().insert_one(model_to_mongo_dict(new_anime)); # Use helper
                new_anime_id = insert_result.inserted_id; content_logger.info(f"Successfully added new anime '{new_anime.name}' (ID: {new_anime_id}) by {user_id}.");

                # --- Transition to Managing the Newly Created Anime ---
                # Clear the multi-step ADD NEW state. Set state to managing THIS anime.
                await MongoDB.clear_user_state(user_id); # Clear old state
                await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(new_anime_id), "anime_name": new_anime.name});

                # Confirm addition message
                await edit_or_send_message(client, chat_id, message_id, f"🎉 Anime <b><u>{new_anime.name}</u></b> added successfully! 🎉\nYou can now add seasons and episodes. 👇", parse_mode=config.PARSE_MODE);
                await asyncio.sleep(1); # Short delay

                # Fetch the newly created anime to display management menu (safer than using potentially incomplete model)
                created_anime = await MongoDB.get_anime_by_id(str(new_anime_id));
                if created_anime: await display_anime_management_menu(client, callback_query.message, created_anime);
                else: content_logger.error(f"Failed to retrieve newly created anime {new_anime_id} after insertion for {user_id}. Cannot display menu.", exc_info=True); await client.send_message(chat_id, "💔 Added anime, but failed to load its management menu. Please navigate manually from the Content Management main menu.", parse_mode=config.PARSE_MODE); await manage_content_command(client, callback_query.message); # Offer to restart

            except Exception as e:
                 content_logger.critical(f"CRITICAL: Error inserting new anime doc after status for {user_id}: {e}. State: {user_state.data}", exc_info=True);
                 await edit_or_send_message(client, chat_id, message_id, "💔 A critical database error occurred while saving. Data lost. Try again.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id); await manage_content_command(client, callback_query.message);


        elif purpose == "edit":
            # Edit Existing Anime flow - Update the EXISTING anime document's status.
            if not anime_id_str: content_logger.error(f"Admin {user_id} in SELECTING_STATUS (edit) missing anime_id."); await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime ID missing."); await MongoDB.clear_user_state(user_id); return;
            try:
                update_result = await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"status": selected_status, "last_updated_at": datetime.now(timezone.utc)}});
                if update_result.matched_count > 0 and update_result.modified_count > 0: content_logger.info(f"Admin {user_id} updated status for {anime_id_str} to '{selected_status}'."); await callback_query.message.edit_text(f"✅ Status updated to: **<u>{selected_status}</u>**!", parse_mode=config.PARSE_MODE);
                elif update_result.matched_count > 0: content_logger.info(f"Admin {user_id} selected status for {anime_id_str} but unchanged."); await callback_query.message.edit_text(f"✅ Status is already <b>{selected_status}</b>.", parse_mode=config.PARSE_MODE);
                else: content_logger.error(f"Anime {anime_id_str} not found for update by {user_id}."); await message.reply_text("💔 Anime not found for update."); await MongoDB.clear_user_state(user_id); return;
                updated_anime = await MongoDB.get_anime_by_id(anime_id_str); if updated_anime: await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name}); await asyncio.sleep(1); await display_anime_management_menu(client, callback_query.message, updated_anime);
                else: content_logger.error(f"Failed fetch {anime_id_str} after status update for {user_id}."); await client.send_message(chat_id, "💔 Updated status, failed to load menu. Navigate back.", parse_mode=config.PARSE_MODE); await manage_content_command(client, callback_query.message);
            except Exception as e: content_logger.error(f"Error updating status for {anime_id_str} by {user_id}: {e}", exc_info=True); await client.send_message(chat_id, "💔 Error updating status.", parse_mode=config.PARSE_MODE); await MongoDB.clear_user_state(user_id);

    else: content_logger.error(f"Admin {user_id} finished status selection invalid purpose: {purpose}.", exc_info=True); await edit_or_send_message(client, chat_id, message_id, "🤷 Unexpected data.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id);

    except Exception as e: content_logger.error(f"FATAL error handling select status callback {data} for {user_id}: {e}", exc_info=True); await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED); await MongoDB.clear_user_state(user_id); await manage_content_command(client, callback_query.message);


@Client.on_callback_query(filters.regex("^content_edit_name\|.*") & filters.private)
async def handle_edit_name_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message_id, "🚫 Unauthorized."); return;
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id); await manage_content_command(client, message); return;
     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str;
         await MongoDB.set_user_state(user_id, "content_management", ContentState.EDITING_NAME_PROMPT, data=user_state.data);
         prompt_text = "✏️ Send the **<u>New Name</u>** for this anime:"; reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]);
         await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True);
         try: await client.answer_callback_query(message_id); except Exception: pass;
     except Exception as e: content_logger.error(f"Error handling edit name callback for {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message_id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

async def handle_editing_name_input(client: Client, message: Message, user_state: UserState, new_name: str):
    user_id = message.from_user.id; chat_id = message.chat.id; anime_id_str = user_state.data.get("anime_id");
    if not anime_id_str: content_logger.error(f"Admin {user_id} sent new name but missing anime_id."); await message.reply_text("💔 Error: Anime ID missing."); await MongoDB.clear_user_state(user_id); return;
    content_logger.info(f"Admin {user_id} provided new name '{new_name}' for {anime_id_str} in EDITING_NAME_PROMPT.");
    try:
         update_result = await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"name": new_name, "last_updated_at": datetime.now(timezone.utc)}});
         if update_result.matched_count > 0:
             if update_result.modified_count > 0: content_logger.info(f"Admin {user_id} updated name for {anime_id_str} to '{new_name}'."); await message.reply_text(f"✅ Name updated to **<u>{new_name}</u>**!");
             else: content_logger.info(f"Admin {user_id} sent name for {anime_id_str} but unchanged."); await message.reply_text(f"✅ Name is already <b>{new_name}</b>.");
         else: content_logger.error(f"Anime {anime_id_str} not found for update by {user_id}."); await message.reply_text("💔 Anime not found for update."); await MongoDB.clear_user_state(user_id); return;
         updated_anime = await MongoDB.get_anime_by_id(anime_id_str); if updated_anime: await MongoDB.set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name}); await asyncio.sleep(1); await display_anime_management_menu(client, message, updated_anime);
         else: content_logger.error(f"Failed fetch {anime_id_str} after name update for {user_id}."); await message.reply_text("💔 Updated name, failed to load menu. Navigate back."); await manage_content_command(client, message);
    except Exception as e: content_logger.error(f"Error updating name for {anime_id_str} by {user_id}: {e}", exc_info=True); await message.reply_text("💔 Error updating name.");

@Client.on_callback_query(filters.regex("^content_edit_synopsis\|.*") & filters.private)
async def handle_edit_synopsis_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message_id, "🚫 Unauthorized."); return;
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id); await manage_content_command(client, message); return;
     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str;
         await MongoDB.set_user_state(user_id, "content_management", ContentState.EDITING_SYNOPSIS_PROMPT, data=user_state.data);
         prompt_text = "📝 Send the **<u>New Synopsis</u>** for this anime:"; reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]);
         await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True);
         try: await client.answer_callback_query(message_id); except Exception: pass;
     except Exception as e: content_logger.error(f"Error handling edit synopsis callback for {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message_id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

@Client.on_callback_query(filters.regex("^content_edit_poster\|.*") & filters.private)
async def handle_edit_poster_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message_id, "🚫 Unauthorized."); return;
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state.", disable_web_page_preview=True); await MongoDB.clear_user_state(user_id); await manage_content_command(client, message); return;
     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str;
         await MongoDB.set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={**user_state.data, "purpose": "edit"});
         prompt_text = "🖼️ Send the **<u>New Poster Image</u>** for this anime:"; reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]);
         await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True);
         try: await client.answer_callback_query(message_id); except Exception: pass;
     except Exception as e: content_logger.error(f"Error handling edit poster callback for {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message_id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

@Client.on_callback_query(filters.regex("^content_edit_genres\|.*") & filters.private)
async def handle_edit_genres_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message_id, "🚫 Unauthorized."); return;
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state."); await MongoDB.clear_user_state(user_id); await manage_content_command(client, message); return;
     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str;
         anime = await MongoDB.get_anime_by_id(anime_id_str); if not anime: content_logger.error(f"Anime {anime_id_str} not found for {user_id}."); await client.answer_callback_query(message_id, "💔 Anime not found for genre edit."); return;
         await MongoDB.set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data={**user_state.data, "purpose": "edit", "selected_genres": anime.genres});
         prompt_text = strings.ADD_ANIME_GENRES_PROMPT.format(anime_name=anime.name); await client.send_message(chat_id, prompt_text);
         await prompt_for_genres(client, chat_id, anime.name, anime.genres);
         try: await client.answer_callback_query(message_id, "Select genres to toggle."); except Exception: pass;
     except Exception as e: content_logger.error(f"Error handling edit genres callback for {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message_id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);


@Client.on_callback_query(filters.regex("^content_edit_year\|.*") & filters.private)
async def handle_edit_year_callback(client: Client, message: Message, user_state: UserState, data: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message_id, "🚫 Unauthorized."); return;
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state."); await MongoDB.clear_user_state(user_id); await manage_content_command(client, message); return;
    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str;
        await MongoDB.set_user_state(user_id, "content_management", ContentState.EDITING_RELEASE_YEAR_PROMPT, data=user_state.data);
        prompt_text = "🗓️ Send the **<u>New Release Year</u>** for this anime:"; reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]]);
        await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True);
        try: await client.answer_callback_query(message_id); except Exception: pass;
    except Exception as e: content_logger.error(f"Error handling edit year callback for {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message_id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED);

@Client.on_callback_query(filters.regex("^content_edit_status\|.*") & filters.private)
async def handle_edit_status_callback(client: Client, message: Message, user_state: UserState, data: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id;
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message_id, "🚫 Unauthorized."); return;
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU): content_logger.warning(f"Admin {user_id} unexpected state {user_state.handler}:{user_state.step}. Resetting."); await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state."); await MongoDB.clear_user_state(user_id); await manage_content_command(client, message); return;
    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]; if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str;
        anime = await MongoDB.get_anime_by_id(anime_id_str); if not anime: content_logger.error(f"Anime {anime_id_str} not found for {user_id}."); await client.answer_callback_query(message_id, "💔 Anime not found for status edit."); return;
        await MongoDB.set_user_state(user_id, "content_management", ContentState.SELECTING_STATUS, data={**user_state.data, "
