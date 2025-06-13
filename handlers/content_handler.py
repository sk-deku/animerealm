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
    FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant,
    AsyncioErrorMessage, BotInlineMessageNotFoundError
)


import config
import strings

from database.mongo_db import MongoDB
from database.mongo_db import get_user_state, set_user_state, clear_user_state
from database.models import (
    UserState, Anime, Season, Episode, FileVersion, PyObjectId, model_to_mongo_dict
)

from fuzzywuzzy import process


async def get_user(client: Client, user_id: int) -> Optional[User]: pass # Assume accessible
async def edit_or_send_message(client: Client, chat_id: int, message_id: Optional[int], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = True): pass # Assume accessible
async def get_anime_by_id(anime_id: Union[str, ObjectId, PyObjectId]) -> Optional[Anime]: pass # Assume accessible via MongoDB class method call
async def display_anime_management_menu(client: Client, message: Message, anime: Anime): pass # Assume accessible


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

    # State for Admin View All Anime list - for pagination
    ADMIN_ANIME_LIST_VIEW = "admin_anime_list_view"
    # State for confirming anime deletion
    CONFIRM_REMOVE_ANIME = "confirm_remove_anime"


async def handle_content_input(client: Client, message: Message, user_state: UserState):
    user_id = message.from_user.id
    chat_id = message.chat.id
    input_text = message.text.strip()
    current_step = user_state.step

    content_logger.debug(f"Handling text input for admin {user_id} at step: {current_step} with text: '{input_text[:100]}...'")

    try:
        if current_step == ContentState.AWAITING_ANIME_NAME:
             await handle_awaiting_anime_name_input(client, message, user_state, input_text)

        elif current_step == ContentState.AWAITING_SYNOPSIS:
             await handle_awaiting_synopsis_input(client, message, user_state, input_text)
        elif current_step == ContentState.AWAITING_TOTAL_SEASONS_COUNT:
             await handle_awaiting_total_seasons_count_input(client, message, user_state, input_text)
        elif current_step == ContentState.AWAITING_RELEASE_YEAR:
             await handle_awaiting_release_year_input(client, message, user_state, input_text)

        elif current_step == ContentState.EDITING_NAME_PROMPT:
             await handle_editing_name_input(client, message, user_state, input_text)
        elif current_step == ContentState.EDITING_SYNOPSIS_PROMPT:
             await handle_editing_synopsis_input(client, message, user_state, input_text)
        elif current_step == ContentState.EDITING_TOTAL_SEASONS_COUNT_PROMPT:
             await handle_editing_total_seasons_count_input(client, message, user_state, input_text)
        elif current_step == ContentState.EDITING_RELEASE_YEAR_PROMPT:
             await handle_editing_release_year_input(client, message, user_state, input_text)

        elif current_step == ContentState.AWAITING_RELEASE_DATE_INPUT:
             await handle_awaiting_release_date_input(client, message, user_state, input_text)

        else:
            content_logger.warning(f"Admin {user_id} sent unexpected text input while in content_management state {current_step}: '{input_text[:100]}...'")
            await message.reply_text("🤔 That wasn't the input I was expecting for this step. Please provide the requested information, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)


    except Exception as e:
         content_logger.error(f"FATAL error in handle_content_input for user {user_id} at step {current_step}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await message.reply_text(strings.ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await manage_content_command(client, message)

async def handle_media_input(client: Client, message: Message, user_state: UserState):
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_step = user_state.step

    content_logger.debug(f"Handling media input for admin {user_id} at step: {current_step} (Photo: {bool(message.photo)}, Doc: {bool(message.document)}, Video: {bool(message.video)})")

    try:
        if current_step == ContentState.AWAITING_POSTER or current_step == ContentState.EDITING_POSTER_PROMPT:
             if message.photo:
                  await handle_awaiting_poster(client, message, user_state)
             else:
                  await message.reply_text("👆 Please send a **photo** to use as the anime poster, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)

        elif current_step == ContentState.UPLOADING_FILE:
             if message.document or message.video:
                  await handle_episode_file_upload(client, message, user_state, message.document or message.video)
             else:
                  await message.reply_text("⬆️ Please upload the episode file (video or document), or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)

        else:
            content_logger.warning(f"Admin {user_id} sent media input ({message.media}) while in content_management state {current_step}, which does not expect media input.")
            await message.reply_text("🤷 I'm not expecting a file or photo right now based on your current action. Please continue with the current step or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)

    except Exception as e:
         content_logger.error(f"FATAL error handling media input for user {user_id} at step {current_step}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await message.reply_text(strings.ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         await manage_content_command(client, message)


@Client.on_message(filters.command("manage_content") & filters.private)
async def manage_content_command(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if user_id not in config.ADMIN_IDS:
        await message.reply_text("🚫 You are not authorized to use this command.", parse_mode=config.PARSE_MODE)
        return

    content_logger.info(f"Admin user {user_id} entered content management.")

    try:
        await clear_user_state(user_id)
        await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU)

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(strings.BUTTON_ADD_NEW_ANIME, callback_data="content_add_new_anime")],
            [InlineKeyboardButton(strings.BUTTON_EDIT_ANIME, callback_data="content_edit_anime_prompt")],
            [InlineKeyboardButton(strings.BUTTON_VIEW_ALL_ANIME, callback_data="content_view_all_anime_list")],

            [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")],
        ])

        await message.reply_text(
            f"**{strings.MANAGE_CONTENT_TITLE}**\n\n{strings.MANAGE_CONTENT_OPTIONS}",
            reply_markup=reply_markup,
            parse_mode=config.PARSE_MODE,
            disable_web_page_preview=True
        )
    except Exception as e:
        content_logger.error(f"Failed to send manage content menu to admin {user_id}: {e}", exc_info=True)
        await message.reply_text(strings.ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


@Client.on_callback_query(filters.regex("^content_(?!toggle|select|done|confirm_remove_file_version$).*") & filters.private)
async def content_main_menu_callbacks(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS:
        await callback_query.answer("🚫 You are not authorized.", show_alert=True)
        return

    content_logger.info(f"Admin {user_id} clicked CM callback: {data}")

    try: await callback_query.answer()
    except Exception: content_logger.warning(f"Failed to answer callback query: {data} from admin {user_id}")


    user_state = await get_user_state(user_id)
    if user_state is None or user_state.handler != "content_management":
         content_logger.warning(f"Admin {user_id} clicked {data} but state is {user_state}. Resetting to main CM menu.")
         await manage_content_command(client, callback_query.message)
         return


    try:
        if data == "content_add_new_anime":
            await set_user_state(user_id, "content_management", ContentState.AWAITING_ANIME_NAME, data={"purpose": "add"})
            await edit_or_send_message(
                 client, chat_id, message_id,
                 strings.ADD_ANIME_NAME_PROMPT.format(),
                 InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
             )

        elif data == "content_edit_anime_prompt":
            await set_user_state(user_id, "content_management", ContentState.AWAITING_ANIME_NAME, data={"purpose": "edit"})
            await edit_or_send_message(
                 client, chat_id, message_id,
                 strings.ADD_ANIME_NAME_PROMPT.format(),
                 InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
             )

        elif data == "content_view_all_anime_list":
             await handle_admin_view_all_anime_list(client, callback_query.message, user_state, 1) # Start on page 1


        elif data == "content_management_main_menu":
            await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU)
            reply_markup = InlineKeyboardMarkup([
                 [InlineKeyboardButton(strings.BUTTON_ADD_NEW_ANIME, callback_data="content_add_new_anime")],
                 [InlineKeyboardButton(strings.BUTTON_EDIT_ANIME, callback_data="content_edit_anime_prompt")],
                 [InlineKeyboardButton(strings.BUTTON_VIEW_ALL_ANIME, callback_data="content_view_all_anime_list")],
                 [InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")],
            ])
            await edit_or_send_message(client, chat_id, message_id, f"**{strings.MANAGE_CONTENT_TITLE}**\n\n{strings.MANAGE_CONTENT_OPTIONS}", reply_markup, disable_web_page_preview=True)


        elif data == "content_cancel":
            await clear_user_state(user_id)
            await edit_or_send_message(client, chat_id, message_id, strings.ACTION_CANCELLED)


        elif data.startswith("content_edit_existing|"):
             anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
             await handle_edit_existing_anime_selection(client, callback_query.message, user_state, anime_id_str)

        elif data.startswith("content_proceed_add_new|"):
            new_anime_name = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
            await handle_proceed_add_new_anime(client, callback_query.message, user_state, new_anime_name)


        elif data.startswith("content_manage_seasons|"):
             anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
             if not user_state.step == ContentState.MANAGING_ANIME_MENU:
                content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking manage seasons. Data: {data}. State data: {user_state.data}")
                await callback_query.message.reply_text("🔄 Invalid state to manage seasons. Please return to the Anime Management Menu.", parse_mode=config.PARSE_MODE)
                return

             await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data={**user_state.data, "anime_id": anime_id_str})
             anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})
             if not anime_doc:
                content_logger.error(f"Anime {anime_id_str} not found for managing seasons (callback) for admin {user_id}. State data: {user_state.data}")
                await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found for season management.", disable_web_page_preview=True)
                await clear_user_state(user_id); return
             await display_seasons_management_menu(client, callback_query.message, Anime(**anime_doc))


        elif data.startswith("content_edit_name|"): await handle_edit_name_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_synopsis|"): await handle_edit_synopsis_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_poster|"): await handle_edit_poster_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_genres|"): await handle_edit_genres_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_year|"): await handle_edit_year_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_status|"): await handle_edit_status_callback(client, callback_query.message, user_state, data)
        elif data.startswith("content_edit_total_seasons_count|"): await handle_edit_total_seasons_count_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_add_new_season|"): await handle_add_new_season_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_remove_season_select|"): await handle_remove_season_select_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_select_season|"): await handle_select_season_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_manage_episode|"): await handle_select_episode_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_add_file_version|"): await handle_add_file_version_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_add_release_date|"): await handle_add_release_date_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_go_next_episode|"): await handle_go_next_episode_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_remove_episode|"): await handle_remove_episode_callback(client, callback_query.message, user_state, data)

        elif data.startswith("content_delete_file_version_select|"): await handle_delete_file_version_select_callback(client, callback_query.message, user_state, data)


        # New handlers for delete anime workflow
        elif data.startswith("content_delete_anime_prompt|"): await handle_delete_anime_prompt(client, callback_query.message, user_state, data)
        elif data.startswith("content_confirm_delete_anime|"): await handle_confirm_delete_anime_callback(client, callback_query.message, user_state, data)


        # Pagination for Admin View All list
        elif data.startswith("content_admin_anime_list_page|"): await handle_admin_view_all_anime_list(client, callback_query.message, user_state, int(data.split(config.CALLBACK_DATA_SEPARATOR)[1]))


        else:
            content_logger.warning(f"Admin {user_id} clicked unhandled content_ callback: {data} in state {user_state.step}. State data: {user_state.data}")
            await callback_query.answer("⚠️ This action is not implemented yet or invalid.", show_alert=False)


    except ValueError as e:
        content_logger.error(f"Invalid callback data format for admin {user_id} clicking {data}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid data received from button. Please try again.", disable_web_page_preview=True)

    except Exception as e:
         content_logger.error(f"FATAL error processing content callback {data} for user {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await manage_content_command(client, callback_query.message)


async def handle_awaiting_anime_name_input(client: Client, message: Message, user_state: UserState, anime_name_input: str):
    user_id = message.from_user.id
    chat_id = message.chat.id

    try:
        anime_name_docs = await MongoDB.anime_collection().find({}, {"name": 1}).to_list(None)
        anime_names_dict = {doc['name']: str(doc['_id']) for doc in anime_name_docs}

        search_results = process.extract(anime_name_input, list(anime_names_dict.keys()), limit=10) # Increased limit

        content_logger.info(f"Fuzzy search for '{anime_name_input}' by admin {user_id} in AWAITING_ANIME_NAME returned {len(search_results)} matches.")

        matching_anime = []
        for name_match, score in search_results:
             if score >= config.FUZZYWUZZY_THRESHOLD:
                 anime_id_str = anime_names_dict[name_match]
                 matching_anime.append({"_id": anime_id_str, "name": name_match, "score": score})

        content_logger.debug(f"Filtered fuzzy search results ({len(matching_anime)}) for admin {user_id}: {matching_anime}")


    except Exception as e:
        content_logger.error(f"Error during fuzzy search for anime name input '{anime_name_input}' by admin {user_id}: {e}", exc_info=True)
        await message.reply_text("💔 Error performing search for existing anime.", parse_mode=config.PARSE_MODE)
        return


    purpose = user_state.data.get("purpose", "add")

    if purpose == "add":
         if matching_anime:
             response_text = strings.ADD_ANIME_NAME_SEARCH_RESULTS.format(name=anime_name_input)
             buttons = []
             for match in matching_anime:
                 buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing{config.CALLBACK_DATA_SEPARATOR}{match['_id']}")])

             encoded_anime_name = anime_name_input # Encoding logic needed if names can be complex
             buttons.append([InlineKeyboardButton(strings.BUTTON_ADD_AS_NEW_ANIME.format(name=anime_name_input), callback_data=f"content_proceed_add_new{config.CALLBACK_DATA_SEPARATOR}{encoded_anime_name}")])

             buttons.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")])

             reply_markup = InlineKeyboardMarkup(buttons)

             await message.reply_text(response_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)


         else:
              await handle_proceed_add_new_anime(client, message, user_state, anime_name_input)


    elif purpose == "edit":
        if matching_anime:
            response_text = f"🔍 Found these anime matching '<code>{anime_name_input}</code>'. Select one to <b><u>edit</u></b>: 👇"
            buttons = []
            for match in matching_anime:
                buttons.append([InlineKeyboardButton(f"✏️ Edit: {match['name']}", callback_data=f"content_edit_existing{config.CALLBACK_DATA_SEPARATOR}{match['_id']}")])

            buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data="content_edit_anime_prompt")])
            buttons.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")])

            reply_markup = InlineKeyboardMarkup(buttons)

            await message.reply_text(response_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)

        else:
             await message.reply_text(
                  f"😔 Couldn't find any anime matching '<code>{anime_name_input}</code>' with confidence above {config.FUZZYWUZZY_THRESHOLD} for editing."
                   "\nPlease try a different name to search for an anime to edit, or type '❌ Cancel'.",
                  parse_mode=config.PARSE_MODE
              )

    else:
        content_logger.error(f"Admin {user_id} sent input in AWAITING_ANIME_NAME state but purpose is {purpose}. State data: {user_state.data}", exc_info=True)
        await message.reply_text("🤷 Invalid state data for this step. Please try again.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)

async def handle_proceed_add_new_anime(client: Client, message: Message, user_state: UserState, anime_name: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id if isinstance(message, Message) else message.message.id


    content_logger.info(f"Admin {user_id} proceeding to add new anime with name: '{anime_name}'.")

    if user_state.handler == "content_management" and user_state.step == ContentState.AWAITING_ANIME_NAME:
        await clear_user_state(user_id)


    await set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={"new_anime_name": anime_name})

    await prompt_for_poster(client, chat_id, anime_name)

    try:
         if isinstance(message, CallbackQuery):
             await message.message.edit_text(
                  f"✅ Okay, adding new anime: <b>{anime_name}</b>\n\nSent prompt for poster.",
                  parse_mode=config.PARSE_MODE
             )
         else:
             await message.reply_text(
                  f"✅ Okay, adding new anime: <b>{anime_name}</b>",
                   parse_mode=config.PARSE_MODE
             )
    except Exception as e:
        content_logger.warning(f"Failed to confirm proceeding add new anime message for admin {user_id}: {e}")


async def handle_edit_existing_anime_selection(client: Client, message: Message, user_state: UserState, anime_id_str: str):
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id # Can be Message or CallbackQuery's message id


     content_logger.info(f"Admin {user_id} selected existing anime ID {anime_id_str} for editing.")

     if user_state.handler == "content_management" and user_state.step == ContentState.AWAITING_ANIME_NAME:
         await clear_user_state(user_id)

     try:
         # Retrieve the anime document
         anime = await MongoDB.get_anime_by_id(anime_id_str)
         if not anime:
             content_logger.error(f"Admin {user_id} tried to edit non-existent anime ID: {anime_id_str} after selection.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Selected anime not found in database.", disable_web_page_preview=True)
             await manage_content_command(client, message)
             return

         content_logger.info(f"Admin {user_id} is now managing anime '{anime.name}' ({anime.id})")

         await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(anime.id), "anime_name": anime.name})

         await display_anime_management_menu(client, message, anime)

     except Exception as e:
          content_logger.error(f"Error loading anime ID {anime_id_str} after selection for admin {user_id}: {e}", exc_info=True)
          await edit_or_send_message(client, chat_id, message_id, "💔 Error loading anime details for editing.", disable_web_page_preview=True)
          await clear_user_state(user_id)

async def display_anime_management_menu(client: Client, message: Message, anime: Anime):
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id

     menu_text = f"🛠️ <b><u>Managing</u></b> <b>{anime.name}</b> 🛠️\n"

     if anime.synopsis:
         menu_text += f"📚 <b><u>Synopsis</u></b>:<blockquote>{anime.synopsis[:300] + '...' if len(anime.synopsis) > 300 else anime.synopsis}</blockquote>\n"
     if anime.poster_file_id:
         menu_text += "🖼️ Poster is set.\n"
     menu_text += f"🏷️ <b><u>Genres</u></b>: {', '.join(anime.genres) if anime.genres else 'Not set'}\n"
     menu_text += f"🗓️ <b><u>Release Year</u></b>: {anime.release_year if anime.release_year else 'Not set'}\n"
     menu_text += f"🚦 <b><u>Status</u></b>: {anime.status if anime.status else 'Not set'}\n"
     menu_text += f"🌟 <b><u>Total Seasons Declared</u></b>: {anime.total_seasons_declared}\n"
     menu_text += f"📁 Files Uploaded: {sum(len(s.episodes[e_idx].files) for s in anime.seasons for e_idx in range(len(s.episodes)) if s.episodes) if anime.seasons else 0} Versions Total\n"

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

     await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)


async def handle_awaiting_poster(client: Client, message: Message, user_state: UserState):
    user_id = message.from_user.id
    chat_id = message.chat.id

    file_id = message.photo[-1].file_id
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime"))
    purpose = user_state.data.get("purpose", "add")

    content_logger.info(f"Admin {user_id} provided poster photo ({file_id}) for '{anime_name}' in AWAITING_POSTER state (Purpose: {purpose}).")


    if purpose == "add":
        user_state.data["poster_file_id"] = file_id

        await set_user_state(user_id, "content_management", ContentState.AWAITING_SYNOPSIS, data=user_state.data)

        await prompt_for_synopsis(client, chat_id, anime_name)

        await message.reply_text(f"🖼️ Poster received! Now send the **<u>Synopsis</u>** for this anime ({anime_name}).", parse_mode=config.PARSE_MODE)


    elif purpose == "edit":
         anime_id_str = user_state.data.get("anime_id")
         if not anime_id_str:
             content_logger.error(f"Admin {user_id} in EDIT purpose AWAITING_POSTER state but missing anime_id.")
             await message.reply_text("💔 Error: Anime ID missing from state data for poster edit. Process cancelled.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return


         try:
             update_result = await MongoDB.anime_collection().update_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"$set": {"poster_file_id": file_id, "last_updated_at": datetime.now(timezone.utc)}}
             )

             if update_result.matched_count > 0 and update_result.modified_count > 0:
                  content_logger.info(f"Admin {user_id} successfully updated poster for anime {anime_id_str}.")
                  await message.reply_text("✅ Poster updated!", parse_mode=config.PARSE_MODE)

                  updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                  if updated_anime:
                       await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                       await asyncio.sleep(1)
                       await display_anime_management_menu(client, message, updated_anime)
                  else:
                       content_logger.error(f"Failed to fetch updated anime {anime_id_str} after poster update for admin {user_id}. Cannot display menu.")
                       await message.reply_text("💔 Updated poster, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                       await manage_content_command(client, message)

             elif update_result.matched_count > 0:
                 content_logger.info(f"Admin {user_id} sent poster for {anime_id_str} but it was unchanged (modified_count=0).")
                 await message.reply_text("✅ Poster appears unchanged. No update needed.", parse_mode=config.PARSE_MODE)
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await asyncio.sleep(1)
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                     content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change poster edit for admin {user_id}.")
                     await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                     await manage_content_command(client, message)


         except Exception as e:
              content_logger.error(f"Error updating poster for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
              await message.reply_text("💔 Error updating poster.", parse_mode=config.PARSE_MODE)


    else:
         content_logger.error(f"Admin {user_id} in AWAITING_POSTER state with invalid purpose: {purpose}. State data: {user_state.data}")
         await message.reply_text("🤷 Unexpected data in state. Your process was cancelled.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id)

async def prompt_for_synopsis(client: Client, chat_id: int, anime_name: str):
    prompt_text = strings.ADD_ANIME_SYNOPSIS_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
    try:
        await client.send_message(
             chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send synopsis prompt to chat {chat_id}: {e}", exc_info=True)

async def handle_awaiting_synopsis_input(client: Client, message: Message, user_state: UserState, synopsis_text: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_step = user_state.step

    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime"))
    anime_id_str = user_state.data.get("anime_id")


    content_logger.info(f"Admin {user_id} provided synopsis text (step {current_step}) for '{anime_name}': '{synopsis_text[:100]}...'")

    if current_step == ContentState.AWAITING_SYNOPSIS:
        user_state.data["synopsis"] = synopsis_text

        await set_user_state(user_id, "content_management", ContentState.AWAITING_TOTAL_SEASONS_COUNT, data=user_state.data)

        await prompt_for_total_seasons_count(client, chat_id, anime_name)

        await message.reply_text(f"📝 Synopsis received. Now send the **<u>Total Number of Seasons</u>** for {anime_name}.", parse_mode=config.PARSE_MODE)


    elif current_step == ContentState.EDITING_SYNOPSIS_PROMPT:
        if not anime_id_str:
            content_logger.error(f"Admin {user_id} in EDITING_SYNOPSIS_PROMPT state but missing anime_id in state data.")
            await message.reply_text("💔 Error: Anime ID missing from state data for synopsis edit. Process cancelled.", parse_mode=config.PARSE_MODE)
            await clear_user_state(user_id); return

        try:
            update_result = await MongoDB.anime_collection().update_one(
                {"_id": ObjectId(anime_id_str)},
                {"$set": {"synopsis": synopsis_text, "last_updated_at": datetime.now(timezone.utc)}}
            )

            if update_result.matched_count > 0 and update_result.modified_count > 0:
                content_logger.info(f"Admin {user_id} successfully updated synopsis for anime {anime_id_str}.")
                await message.reply_text("✅ Synopsis updated!", parse_mode=config.PARSE_MODE)

                updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                if updated_anime:
                    await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                    await asyncio.sleep(1)
                    await display_anime_management_menu(client, message, updated_anime)

                else:
                    content_logger.error(f"Failed to fetch updated anime {anime_id_str} after synopsis update for admin {user_id}.")
                    await message.reply_text("💔 Updated synopsis, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                    await manage_content_command(client, message)


            elif update_result.matched_count > 0:
                 content_logger.info(f"Admin {user_id} sent synopsis for {anime_id_str} but it was unchanged (modified_count=0).")
                 await message.reply_text("✅ Synopsis appears unchanged. No update needed.", parse_mode=config.PARSE_MODE)
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await asyncio.sleep(1)
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change synopsis edit for admin {user_id}.")
                      await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)


        except Exception as e:
             content_logger.error(f"Error updating synopsis for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
             await message.reply_text("💔 Error updating synopsis.", parse_mode=config.PARSE_MODE)


    else:
        content_logger.error(f"Admin {user_id} sent synopsis input in unexpected state {current_step}.")
        await message.reply_text("🤷 Unexpected state data for this step. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)


async def prompt_for_total_seasons_count(client: Client, chat_id: int, anime_name: str):
    prompt_text = strings.ADD_ANIME_SEASONS_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
    try:
        await client.send_message(
             chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send total seasons count prompt to chat {chat_id}: {e}", exc_info=True)

async def handle_awaiting_total_seasons_count_input(client: Client, message: Message, user_state: UserState, count_text: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_step = user_state.step

    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime"))
    anime_id_str = user_state.data.get("anime_id")

    content_logger.info(f"Admin {user_id} provided seasons count input ({count_text}) for '{anime_name}' at step {current_step}.")


    try:
        seasons_count = int(count_text)
        if seasons_count < 0: raise ValueError("Negative count not allowed")

    except ValueError:
        await message.reply_text("🚫 Please send a valid **<u>non-negative number</u>** for the total seasons count, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        return

    if current_step == ContentState.AWAITING_TOTAL_SEASONS_COUNT:
        user_state.data["total_seasons_declared"] = seasons_count

        await set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data=user_state.data)

        await prompt_for_genres(client, chat_id, anime_name, user_state.data.get("selected_genres", []))

        await message.reply_text(f"📺 Total seasons (<b>{seasons_count}</b>) received. Now select the **<u>Genres</u>** for {anime_name}.", parse_mode=config.PARSE_MODE)


    elif current_step == ContentState.EDITING_TOTAL_SEASONS_COUNT_PROMPT:
        if not anime_id_str:
             content_logger.error(f"Admin {user_id} in EDITING_TOTAL_SEASONS_COUNT_PROMPT state but missing anime_id.")
             await message.reply_text("💔 Error: Anime ID missing from state data for seasons count edit. Process cancelled.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return


        try:
            update_result = await MongoDB.anime_collection().update_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"$set": {"total_seasons_declared": seasons_count, "last_updated_at": datetime.now(timezone.utc)}}
             )

            if update_result.matched_count > 0 and update_result.modified_count > 0:
                 content_logger.info(f"Admin {user_id} successfully updated total_seasons_declared for anime {anime_id_str} to {seasons_count}.")
                 await message.reply_text(f"✅ Total seasons updated to **<u>{seasons_count}</u>**!", parse_mode=config.PARSE_MODE)

                 updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if updated_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                     await asyncio.sleep(1)
                     await display_anime_management_menu(client, message, updated_anime)
                 else:
                      content_logger.error(f"Failed to fetch updated anime {anime_id_str} after seasons count update for admin {user_id}.")
                      await message.reply_text("💔 Updated total seasons, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)


            elif update_result.matched_count > 0:
                 content_logger.info(f"Admin {user_id} sent total seasons count for {anime_id_str} but it was unchanged (modified_count=0).")
                 await message.reply_text(f"✅ Total seasons count is already <b>{seasons_count}</b>. No update needed.", parse_mode=config.PARSE_MODE)
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await asyncio.sleep(1)
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change seasons count edit for admin {user_id}.")
                      await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)

        except Exception as e:
            content_logger.error(f"Error updating total seasons count for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
            await message.reply_text("💔 Error updating total seasons count.", parse_mode=config.PARSE_MODE)


    else:
        content_logger.error(f"Admin {user_id} sent seasons count input in unexpected state {current_step}.")
        await message.reply_text("🤷 Unexpected state data for this step. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)


async def prompt_for_genres(client: Client, chat_id: int, anime_name: str, current_selection: List[str]):
    prompt_text = strings.ADD_ANIME_GENRES_PROMPT.format(anime_name=anime_name)
    genres_presets = config.INITIAL_GENRES

    buttons = []
    for genre in genres_presets:
        is_selected = genre in current_selection
        button_text = f"✅ {genre}" if is_selected else f"⬜ {genre}"
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}{genre}"))


    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    keyboard_rows.append([
        InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Genres"), callback_data="content_genres_done"),
        InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        await client.send_message(
             chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True
         )
    except Exception as e:
        content_logger.error(f"Failed to send genres selection prompt to chat {chat_id}: {e}", exc_info=True)

@Client.on_callback_query(filters.regex(f"^content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_toggle_genre_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: content_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")


    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_GENRES):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking genre toggle {data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting genres. Please restart the process.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for toggling genre.")
        genre_to_toggle = parts[1]

        selected_genres = user_state.data.get("selected_genres", [])


        if genre_to_toggle not in config.INITIAL_GENRES:
             content_logger.warning(f"Admin {user_id} attempted to toggle non-preset genre: {genre_to_toggle}.")
             await callback_query.answer("🚫 Invalid genre option.", show_alert=False)
             return

        if genre_to_toggle in selected_genres: selected_genres.remove(genre_to_toggle)
        else: selected_genres.append(genre_to_toggle)

        selected_genres.sort()

        user_state.data["selected_genres"] = selected_genres
        await set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data=user_state.data)


        genres_presets = config.INITIAL_GENRES
        buttons = []
        for genre in genres_presets:
            is_selected = genre in selected_genres
            button_text = f"✅ {genre}" if is_selected else f"⬜ {genre}"
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_genre{config.CALLBACK_DATA_SEPARATOR}{genre}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

        keyboard_rows.append([
             InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Genres"), callback_data="content_genres_done"),
             InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        try:
             await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        except MessageNotModified: pass
        except FloodWait as e:
            content_logger.warning(f"FloodWait while editing genre buttons for admin {user_id} (retry in {e.value}s): {e}")
            await asyncio.sleep(e.value)
            try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
            except Exception as retry_e: content_logger.error(f"Retry after FloodWait failed editing genre buttons for admin {user_id} (msg {message_id}): {retry_e}", exc_info=True)

    except Exception as e:
         content_logger.error(f"FATAL error handling content_toggle_genre callback {data} for admin {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         try: await callback_query.answer(strings.ERROR_OCCURRED, show_alert=True); except Exception: pass
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED) # Reply error as new message?

@Client.on_callback_query(filters.regex("^content_genres_done$") & filters.private)
async def handle_genres_done_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Genres selected. Proceeding...")
    except Exception: common_logger.warning(f"Failed to answer callback query content_genres_done from admin {user_id}.")


    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_GENRES):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking Done Genres. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Your previous process was cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    selected_genres = user_state.data.get("selected_genres", [])
    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime Name Unknown"))
    anime_id_str = user_state.data.get("anime_id")
    purpose = user_state.data.get("purpose", "add")

    content_logger.info(f"Admin {user_id} finished selecting genres ({purpose} purpose) for '{anime_name}': {selected_genres}")

    if purpose == "add":
        user_state.data["genres"] = selected_genres

        await set_user_state(user_id, "content_management", ContentState.AWAITING_RELEASE_YEAR, data=user_state.data)

        await prompt_for_release_year(client, chat_id, anime_name)

        try:
            await callback_query.message.edit_text(
                 f"🏷️ Genres saved: <b>{', '.join(selected_genres) if selected_genres else 'None'}</b>.\n\n🗓️ Now send the **<u>Release Year</u>** for {anime_name}.",
                 parse_mode=config.PARSE_MODE
             )
        except Exception as e:
             content_logger.warning(f"Failed to edit message after genres done (add flow) for admin {user_id}: {e}")
             await client.send_message(chat_id, f"✅ Genres saved. Please send the **<u>Release Year</u>** for {anime_name}.", parse_mode=config.PARSE_MODE)


    elif purpose == "edit":
        if not anime_id_str:
             content_logger.error(f"Admin {user_id} in SELECTING_GENRES (edit) state but missing anime_id in state data.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime ID missing from state data for genre edit. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return

        try:
            update_result = await MongoDB.anime_collection().update_one(
                {"_id": ObjectId(anime_id_str)},
                {"$set": {"genres": selected_genres, "last_updated_at": datetime.now(timezone.utc)}}
            )

            if update_result.matched_count > 0 and update_result.modified_count > 0:
                 content_logger.info(f"Admin {user_id} successfully updated genres for anime {anime_id_str}.")
                 await callback_query.message.edit_text(f"✅ Genres updated to: <b>{', '.join(selected_genres) if selected_genres else 'None'}</b>!", parse_mode=config.PARSE_MODE)

                 updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if updated_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                     await asyncio.sleep(1)
                     await display_anime_management_menu(client, callback_query.message, updated_anime)

                 else:
                     content_logger.error(f"Failed to fetch updated anime {anime_id_str} after genre update for admin {user_id}.")
                     await client.send_message(chat_id, "💔 Updated genres, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                     await manage_content_command(client, callback_query.message)

            elif update_result.matched_count > 0:
                 content_logger.info(f"Admin {user_id} sent genres for {anime_id_str} but it was unchanged (modified_count=0).")
                 await callback_query.message.edit_text(f"✅ Genres appear unchanged. No update needed.", parse_mode=config.PARSE_MODE)
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                      await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                      await asyncio.sleep(1)
                      await display_anime_management_menu(client, callback_query.message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change genre edit for admin {user_id}.")
                      await client.send_message(chat_id, "🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, callback_query.message)

        except Exception as e:
             content_logger.error(f"Error updating genres for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
             await client.send_message(chat_id, "💔 Error updating genres.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id)

    else:
        content_logger.error(f"Admin {user_id} finished genre selection with invalid purpose in state data: {purpose}. State data: {user_state.data}")
        await edit_or_send_message(client, chat_id, message_id, "🤷 Unexpected data in state. Your process was cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id)


async def prompt_for_release_year(client: Client, chat_id: int, anime_name: str):
    prompt_text = strings.ADD_ANIME_YEAR_PROMPT.format(anime_name=anime_name)
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
    try:
        await client.send_message(
             chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE
         )
    except Exception as e:
        content_logger.error(f"Failed to send release year prompt to chat {chat_id}: {e}", exc_info=True)

async def handle_awaiting_release_year_input(client: Client, message: Message, user_state: UserState, year_text: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_step = user_state.step

    anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime"))
    anime_id_str = user_state.data.get("anime_id")


    content_logger.info(f"Admin {user_id} provided release year input ({year_text}) for '{anime_name}' at step {current_step}.")

    try:
        release_year = int(year_text)

    except ValueError:
        await message.reply_text("🚫 Please send a valid **<u>year</u>** (e.g., 2024), or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
        return

    if current_step == ContentState.AWAITING_RELEASE_YEAR:
        user_state.data["release_year"] = release_year

        await set_user_state(user_id, "content_management", ContentState.SELECTING_STATUS, data=user_state.data)

        await prompt_for_status(client, chat_id, anime_name)

        await message.reply_text(f"🗓️ Release year (<b>{release_year}</b>) saved. Now select the **<u>Status</u>** for {anime_name}.", parse_mode=config.PARSE_MODE)


    elif current_step == ContentState.EDITING_RELEASE_YEAR_PROMPT:
        if not anime_id_str:
             content_logger.error(f"Admin {user_id} in EDITING_RELEASE_YEAR_PROMPT state but missing anime_id.")
             await message.reply_text("💔 Error: Anime ID missing from state data for year edit. Process cancelled.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return

        try:
            update_result = await MongoDB.anime_collection().update_one(
                 {"_id": ObjectId(anime_id_str)},
                 {"$set": {"release_year": release_year, "last_updated_at": datetime.now(timezone.utc)}}
             )

            if update_result.matched_count > 0 and update_result.modified_count > 0:
                 content_logger.info(f"Admin {user_id} successfully updated release year for anime {anime_id_str} to {release_year}.")
                 await message.reply_text(f"✅ Release year updated to **__{release_year}__**!", parse_mode=config.PARSE_MODE)

                 updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if updated_anime:
                      await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                      await asyncio.sleep(1)
                      await display_anime_management_menu(client, message, updated_anime)
                 else:
                      content_logger.error(f"Failed to fetch updated anime {anime_id_str} after year update for admin {user_id}.")
                      await message.reply_text("💔 Updated release year, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)


            elif update_result.matched_count > 0:
                 content_logger.info(f"Admin {user_id} sent release year for {anime_id_str} but it was unchanged (modified_count=0).")
                 await message.reply_text(f"✅ Release year is already <b>{release_year}</b>. No update needed.", parse_mode=config.PARSE_MODE)
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await asyncio.sleep(1)
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change year edit for admin {user_id}.")
                      await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)

        except Exception as e:
            content_logger.error(f"Error updating release year for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
            await message.reply_text("💔 Error updating release year.", parse_mode=config.PARSE_MODE)


    else:
        content_logger.error(f"Admin {user_id} sent year input in unexpected state {current_step}.")
        await message.reply_text("🤷 Unexpected state data for this step. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id)


async def prompt_for_status(client: Client, chat_id: int, anime_name: str, current_selection: Optional[str] = None):
    prompt_text = strings.ADD_ANIME_STATUS_PROMPT.format(anime_name=anime_name)
    status_presets = config.ANIME_STATUSES

    buttons = []
    for status in status_presets:
         button_text = f"✅ {status}" if current_selection and status == current_selection else status
         buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_select_status{config.CALLBACK_DATA_SEPARATOR}{status}"))

    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        await client.send_message(
             chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True
         )
    except Exception as e:
        content_logger.error(f"Failed to send status selection prompt to chat {chat_id}: {e}", exc_info=True)

@Client.on_callback_query(filters.regex(f"^content_select_status{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_select_status_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: content_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")


    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_STATUS):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking status select {data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting status. Please restart the process.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for selecting status.")
        selected_status = parts[1]

        if selected_status not in config.ANIME_STATUSES:
             content_logger.warning(f"Admin {user_id} attempted to select non-preset status: {selected_status}.")
             await callback_query.answer("🚫 Invalid status option.", show_alert=False)
             await edit_or_send_message(client, chat_id, message_id, f"🚫 Invalid status option selected: {selected_status}.", disable_web_page_preview=True);
             return


        user_state.data["status"] = selected_status; # Store selected status
        anime_name = user_state.data.get("new_anime_name", user_state.data.get("anime_name", "Anime"));
        anime_id_str = user_state.data.get("anime_id");
        purpose = user_state.data.get("purpose", "add");


        content_logger.info(f"Admin {user_id} selected status '{selected_status}' ({purpose} purpose) for '{anime_name}'.")

        if purpose == "add":
            new_anime_data_dict = {
                 "name": user_state.data.get("new_anime_name"),
                 "poster_file_id": user_state.data.get("poster_file_id"),
                 "synopsis": user_state.data.get("synopsis"),
                 "total_seasons_declared": user_state.data.get("total_seasons_declared", 0),
                 "genres": user_state.data.get("genres", []),
                 "release_year": user_state.data.get("release_year"),
                 "status": user_state.data.get("status"), # Status from state data
                 "seasons": [],
                 "overall_download_count": 0,
                 "last_updated_at": datetime.now(timezone.utc)
            }

            if not new_anime_data_dict.get("name") or not new_anime_data_dict.get("status"):
                content_logger.error(f"Admin {user_id} finished add flow, but missing name or status in state data! Data: {user_state.data}")
                await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing critical data to create anime. Process cancelled.", disable_web_page_preview=True)
                await clear_user_state(user_id); return

            try:
                new_anime = Anime(**new_anime_data_dict)
            except Exception as e:
                content_logger.error(f"Error validating Anime model from state data for admin {user_id}: {e}. Data: {new_anime_data_dict}", exc_info=True)
                await edit_or_send_message(client, chat_id, message_id, "💔 Error validating anime data structure. Process cancelled.", disable_web_page_preview=True)
                await clear_user_state(user_id); return

            try:
                insert_result = await MongoDB.anime_collection().insert_one(new_anime.dict(by_alias=True, exclude_none=True))
                new_anime_id = insert_result.inserted_id
                content_logger.info(f"Successfully added new anime '{new_anime.name}' (ID: {new_anime_id}) by admin {user_id}.")

                await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(new_anime_id), "anime_name": new_anime.name})

                await edit_or_send_message(client, chat_id, message_id, f"🎉 Anime <b><u>{new_anime.name}</u></b> added successfully! 🎉\nYou can now add seasons and episodes. 👇", disable_web_page_preview=True);
                await asyncio.sleep(1)

                created_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(new_anime_id)})
                if created_anime_doc:
                    created_anime = Anime(**created_anime_doc)
                    await display_anime_management_menu(client, callback_query.message, created_anime)
                else:
                    content_logger.error(f"Failed to retrieve newly created anime {new_anime_id} after insertion for admin {user_id}. Cannot display management menu.", exc_info=True)
                    await client.send_message(chat_id, "💔 Added anime successfully, but failed to load its management menu. Please navigate manually from the Content Management main menu.", parse_mode=config.PARSE_MODE)
                    await manage_content_command(client, callback_query.message)


            except Exception as e:
                 content_logger.critical(f"CRITICAL: Error inserting new anime document after status selection for admin {user_id}: {e}. State data: {user_state.data}", exc_info=True)
                 await edit_or_send_message(client, chat_id, message_id, "💔 A critical database error occurred while saving the new anime data. All collected details were lost. Please try again.", disable_web_page_preview=True)
                 await clear_user_state(user_id);
                 await manage_content_command(client, callback_query.message)


        elif purpose == "edit":
            if not anime_id_str:
                content_logger.error(f"Admin {user_id} in SELECTING_STATUS (edit) state but missing anime_id in state data.")
                await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime ID missing from state data for status edit. Process cancelled.", disable_web_page_preview=True)
                await clear_user_state(user_id); return


            try:
                update_result = await MongoDB.anime_collection().update_one(
                    {"_id": ObjectId(anime_id_str)},
                    {"$set": {"status": selected_status, "last_updated_at": datetime.now(timezone.utc)}}
                )

                if update_result.matched_count > 0 and update_result.modified_count > 0:
                     content_logger.info(f"Admin {user_id} successfully updated status for anime {anime_id_str} to '{selected_status}'.")
                     await callback_query.message.edit_text(f"✅ Status updated to: **<u>{selected_status}</u>**!", parse_mode=config.PARSE_MODE)

                     updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                     if updated_anime:
                         await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                         await asyncio.sleep(1)
                         await display_anime_management_menu(client, callback_query.message, updated_anime)

                     else:
                         content_logger.error(f"Failed to fetch updated anime {anime_id_str} after status update for admin {user_id}. Cannot display menu.")
                         await client.send_message(chat_id, "💔 Updated status, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                         await manage_content_command(client, callback_query.message)


                elif update_result.matched_count > 0:
                     content_logger.info(f"Admin {user_id} selected status for {anime_id_str} but it was unchanged (modified_count=0).")
                     await callback_query.message.edit_text(f"✅ Status is already <b>{selected_status}</b>. No update needed.", parse_mode=config.PARSE_MODE)
                     current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                     if current_anime:
                         await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                         await asyncio.sleep(1)
                         await display_anime_management_menu(client, callback_query.message, current_anime)

                     else:
                          content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change status edit for admin {user_id}.")
                          await client.send_message(chat_id, "🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                          await manage_content_command(client, callback_query.message)


            except Exception as e:
                content_logger.error(f"Error updating status for anime {anime_id_str} by admin {user_id}: {e}", exc_info=True)
                await client.send_message(chat_id, "💔 Error updating status.", parse_mode=config.PARSE_MODE)
                await clear_user_state(user_id)

        else:
             content_logger.error(f"Admin {user_id} finished status selection with invalid purpose in state data: {purpose}. State data: {user_state.data}")
             await edit_or_send_message(client, chat_id, message_id, "🤷 Unexpected data in state. Your process was cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id)


    except Exception as e:
        content_logger.error(f"FATAL error handling content_select_status callback {data} for admin {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await clear_user_state(user_id);
        await manage_content_command(client, callback_query.message);

@Client.on_callback_query(filters.regex("^content_edit_name\|.*") & filters.private)
async def handle_edit_name_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking edit name. Data: {data}. State data: {user_state.data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing name.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, message); return

     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
         if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id {user_state.data.get('anime_id')} doesn't match callback anime_id {anime_id_str} for editing name.")
             user_state.data["anime_id"] = anime_id_str

         await set_user_state(user_id, "content_management", ContentState.EDITING_NAME_PROMPT, data=user_state.data)

         prompt_text = "✏️ Send the **<u>New Name</u>** for this anime:"
         reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])

         await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
         try: await client.answer_callback_query(message.id)
         except Exception: common_logger.warning(f"Failed to answer callback {data} after message edit for {user_id}")

     except Exception as e:
         content_logger.error(f"Error handling content_edit_name callback for admin {user_id}: {e}", exc_info=True);
         try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass;
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);


async def handle_editing_name_input(client: Client, message: Message, user_state: UserState, new_name: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_id_str = user_state.data.get("anime_id")

    if not anime_id_str:
        content_logger.error(f"Admin {user_id} sent new anime name but missing anime_id in state data (step: {user_state.step}). State data: {user_state.data}")
        await message.reply_text("💔 Error: Anime ID missing from state. Cannot update name. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return

    content_logger.info(f"Admin {user_id} provided new name '{new_name}' for anime ID {anime_id_str} in EDITING_NAME_PROMPT.")

    try:
         update_result = await MongoDB.anime_collection().update_one(
             {"_id": ObjectId(anime_id_str)},
             {"$set": {"name": new_name, "last_updated_at": datetime.now(timezone.utc)}}
         )

         if update_result.matched_count > 0:
             if update_result.modified_count > 0:
                  content_logger.info(f"Admin {user_id} successfully updated name of anime {anime_id_str} to '{new_name}'.")
                  await message.reply_text(f"✅ Name updated to **<u>{new_name}</u>**!", parse_mode=config.PARSE_MODE)

                  updated_anime = await MongoDB.get_anime_by_id(anime_id_str)
                  if updated_anime:
                       await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(updated_anime.id), "anime_name": updated_anime.name})
                       await asyncio.sleep(1)
                       await display_anime_management_menu(client, message, updated_anime)

                  else:
                      content_logger.error(f"Failed to fetch updated anime {anime_id_str} after name update for admin {user_id}.")
                      await message.reply_text("💔 Updated name, but failed to load the management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)

             else:
                 content_logger.info(f"Admin {user_id} sent name for {anime_id_str} but it was unchanged ('{new_name}').")
                 await message.reply_text(f"✅ Name is already **<u>{new_name}</u>**. No update needed.", parse_mode=config.PARSE_MODE)
                 current_anime = await MongoDB.get_anime_by_id(anime_id_str)
                 if current_anime:
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": str(current_anime.id), "anime_name": current_anime.name})
                     await asyncio.sleep(1)
                     await display_anime_management_menu(client, message, current_anime)
                 else:
                      content_logger.error(f"Failed to fetch anime {anime_id_str} to display menu after no-change name edit for admin {user_id}.")
                      await message.reply_text("🔄 No change made. Failed to load management menu. Returning to main menu.", parse_mode=config.PARSE_MODE)
                      await manage_content_command(client, message)

         else:
             content_logger.error(f"Anime ID {anime_id_str} not found during update operation by admin {user_id} in EDITING_NAME_PROMPT.")
             await message.reply_text("💔 Error: Anime not found during update. Please try editing again from the management menu.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id); return

    except Exception as e:
         content_logger.error(f"Error updating anime name {anime_id_str} to '{new_name}' for admin {user_id}: {e}", exc_info=True)
         await message.reply_text("💔 Error updating anime name.", parse_mode=config.PARSE_MODE)


@Client.on_callback_query(filters.regex("^content_edit_synopsis\|.*") & filters.private)
async def handle_edit_synopsis_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking edit synopsis. Data: {data}. State data: {user_state.data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing synopsis.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, message); return

     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
         if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str
         await set_user_state(user_id, "content_management", ContentState.EDITING_SYNOPSIS_PROMPT, data=user_state.data)
         prompt_text = "📝 Send the **<u>New Synopsis</u>** for this anime:"
         reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
         await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
         try: await client.answer_callback_query(message.id)
         except Exception: pass
     except Exception as e:
         content_logger.error(f"Error handling edit synopsis callback {user_id}: {e}", exc_info=True);
         try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass;
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);


@Client.on_callback_query(filters.regex("^content_edit_poster\|.*") & filters.private)
async def handle_edit_poster_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking edit poster. Data: {data}. State data: {user_state.data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing poster.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, message); return

     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
         if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str
         await set_user_state(user_id, "content_management", ContentState.AWAITING_POSTER, data={**user_state.data, "purpose": "edit"})
         prompt_text = "🖼️ Send the **<u>New Poster Image</u>** for this anime:"
         reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
         await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
         try: await client.answer_callback_query(message.id)
         except Exception: pass
     except Exception as e:
         content_logger.error(f"Error handling edit poster callback {user_id}: {e}", exc_info=True);
         try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass;
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);

@Client.on_callback_query(filters.regex("^content_edit_genres\|.*") & filters.private)
async def handle_edit_genres_callback(client: Client, message: Message, user_state: UserState, data: str):
     user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
     if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
     if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking edit genres. Data: {data}. State data: {user_state.data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing genres.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, message); return
     try:
         anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
         if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str

         anime = await MongoDB.get_anime_by_id(anime_id_str)
         if not anime:
             content_logger.error(f"Anime not found {anime_id_str} for genre edit after state check.")
             await client.answer_callback_query(message.id, "💔 Anime not found for genre edit.");
             return


         await set_user_state(user_id, "content_management", ContentState.SELECTING_GENRES, data={**user_state.data, "purpose": "edit", "selected_genres": anime.genres})
         prompt_text = strings.ADD_ANIME_GENRES_PROMPT.format(anime_name=anime.name)
         await client.send_message(chat_id, prompt_text, parse_mode=config.PARSE_MODE)
         await prompt_for_genres(client, chat_id, anime.name, anime.genres)
         try: await client.answer_callback_query(message.id, "Select genres to toggle.");
         except Exception: pass

     except Exception as e: content_logger.error(f"Error handling edit genres callback {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);


@Client.on_callback_query(filters.regex("^content_edit_year\|.*") & filters.private)
async def handle_edit_year_callback(client: Client, message: Message, user_state: UserState, data: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking edit year. Data: {data}. State data: {user_state.data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing year.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, message); return
    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str
        await set_user_state(user_id, "content_management", ContentState.EDITING_RELEASE_YEAR_PROMPT, data=user_state.data)
        prompt_text = "🗓️ Send the **<u>New Release Year</u>** for this anime:"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
        await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
        try: await client.answer_callback_query(message.id)
        except Exception: pass
    except Exception as e:
         content_logger.error(f"Error handling edit year callback {user_id}: {e}", exc_info=True);
         try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass;
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);

@Client.on_callback_query(filters.regex("^content_edit_status\|.*") & filters.private)
async def handle_edit_status_callback(client: Client, message: Message, user_state: UserState, data: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking edit status. Data: {data}. State data: {user_state.data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing status.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, message); return
    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str
        anime = await MongoDB.get_anime_by_id(anime_id_str)
        if not anime:
            content_logger.error(f"Anime not found {anime_id_str} for status edit after state check.")
            await client.answer_callback_query(message.id, "💔 Anime not found for status edit.");
            return

        await set_user_state(user_id, "content_management", ContentState.SELECTING_STATUS, data={**user_state.data, "purpose": "edit", "status": anime.status})
        prompt_text = strings.ADD_ANIME_STATUS_PROMPT.format(anime_name=anime.name)
        await prompt_for_status(client, chat_id, anime.name, anime.status)

        await edit_or_send_message(
            client, chat_id, message_id, f"🚦 Sent status selection menu for {anime.name}...",
             disable_web_page_preview=True
         )
        try: await client.answer_callback_query(message.id, "Select status.");
        except Exception: pass


    except Exception as e:
         content_logger.error(f"Error handling edit status callback {user_id}: {e}", exc_info=True);
         try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass;
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);


@Client.on_callback_query(filters.regex("^content_edit_total_seasons_count\|.*") & filters.private)
async def handle_edit_total_seasons_count_callback(client: Client, message: Message, user_state: UserState, data: str):
    user_id = message.from_user.id; chat_id = message.chat.id; message_id = message.id
    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    if not (user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking edit total seasons count. Data: {data}. State data: {user_state.data}")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for editing total seasons.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, message); return
    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        if user_state.data.get("anime_id") != anime_id_str: user_state.data["anime_id"] = anime_id_str

        await set_user_state(user_id, "content_management", ContentState.EDITING_TOTAL_SEASONS_COUNT_PROMPT, data=user_state.data)
        prompt_text = "🔢 Send the **<u>New Total Number of Seasons</u>** for this anime:"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
        await edit_or_send_message(client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True)
        try: await client.answer_callback_query(message.id)
        except Exception: pass

    except Exception as e: content_logger.error(f"Error handling edit total seasons count callback {user_id}: {e}", exc_info=True); try: await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True); except Exception: pass; await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);

async def display_seasons_management_menu(client: Client, message: Message, anime: Anime):
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id

     anime_id_str = str(anime.id)
     anime_name = anime.name

     seasons = sorted(anime.seasons, key=lambda s: s.season_number)


     menu_text = strings.MANAGE_SEASONS_TITLE.format(anime_name=anime_name) + "\n\n"

     buttons = []
     if not seasons:
          menu_text += "No seasons added yet. Add episodes by setting the Total Episodes count for the season in the Seasons Menu.\n\n"


     for season in seasons:
          season_number = season.season_number
          episodes_list = season.episodes
          ep_count = len(episodes_list)
          declared_count = season.episode_count_declared

          button_label = f"📺 Season {season_number}"
          if declared_count is not None and declared_count > 0:
               button_label += f" ({declared_count} Episodes Declared)"
               if ep_count > 0 and ep_count != declared_count:
                    button_label += f" [{ep_count} Existing]"

          elif ep_count > 0:
               button_label += f" ({ep_count} Episodes)"


          buttons.append([InlineKeyboardButton(button_label, callback_data=f"content_select_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}")])


     next_season_number = (seasons[-1].season_number if seasons else 0) + 1
     buttons.append([InlineKeyboardButton(strings.BUTTON_ADD_NEW_SEASON, callback_data=f"content_add_new_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{next_season_number}")])

     if seasons:
          buttons.append([InlineKeyboardButton("🗑️ Remove a Season", callback_data=f"content_remove_season_select{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")])


     buttons.append([InlineKeyboardButton(strings.BUTTON_BACK_TO_ANIME_LIST_ADMIN, callback_data=f"content_edit_existing{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")]) # Go back to THIS anime management menu
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")])
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])


     reply_markup = InlineKeyboardMarkup(buttons)

     await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(f"^content_manage_seasons{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_manage_seasons_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Loading seasons...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management"):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking manage seasons. Data: {data}. State data: {user_state.data}")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Please navigate from the Content Management main menu.", disable_web_page_preview=True)
        await clear_user_state(user_id); return
        await manage_content_command(client, callback_query.message)

    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id mismatch for manage seasons: {user_state.data.get('anime_id')} vs callback {anime_id_str}. Updating state.")
             user_state.data["anime_id"] = anime_id_str

        await set_user_state(user_id, "content_management", ContentState.MANAGING_SEASONS_LIST, data=user_state.data)


        anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})

        if not anime_doc:
            content_logger.error(f"Anime {anime_id_str} not found for managing seasons for admin {user_id}. State data: {user_state.data}")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found for season management.", disable_web_page_preview=True)
            await clear_user_state(user_id); return
            await manage_content_command(client, callback_query.message)


        anime = Anime(**anime_doc)

        await display_seasons_management_menu(client, callback_query.message, anime)


    except Exception as e:
         content_logger.error(f"FATAL error handling content_manage_seasons callback {data} for admin {user_id}: {e}", exc_info=True)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await clear_user_state(user_id)
         await manage_content_command(client, callback_query.message)

@Client.on_callback_query(filters.regex(f"^content_add_new_season{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_add_new_season_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_SEASONS_LIST):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking add season. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for adding season.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3: raise ValueError("Invalid callback data format for adding season.")
        anime_id_str = parts[1]
        season_to_add = int(parts[2])

        new_season_dict = Season(season_number=season_to_add).dict()

        update_result = await MongoDB.anime_collection().update_one(
            {"_id": ObjectId(anime_id_str)},
            {"$push": {"seasons": new_season_dict}}
        )

        if update_result.matched_count > 0 and update_result.modified_count > 0:
            content_logger.info(f"Admin {user_id} added Season {season_to_add} to anime {anime_id_str}.")
            await callback_query.message.edit_text(f"✅ Added Season **<u>{season_to_add}</u>** to this anime!\n\n🔢 Now send the **<u>Total Number of Episodes</u>** for Season **__{season_to_add}__**.", parse_mode=config.PARSE_MODE)


            await set_user_state(user_id, "content_management", ContentState.AWAITING_TOTAL_SEASONS_COUNT, data={**user_state.data, "managing_season_number": season_to_add, "purpose": "set_episode_count"})

            anime_name = user_state.data.get("anime_name", "Anime")
            prompt_text = strings.ADD_SEASON_EPISODES_PROMPT.format(season_number=season_to_add, anime_name=anime_name)
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])
            await client.send_message(chat_id, prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)

        elif update_result.matched_count > 0:
             content_logger.warning(f"Admin {user_id} clicked add season {season_to_add} for {anime_id_str} but modified_count was 0. Season already exists?")
             await callback_query.message.edit_text(f"⚠️ Failed to add Season **<u>{season_to_add}</u>**. It might already exist.", parse_mode=config.PARSE_MODE)

        else:
             content_logger.error(f"Anime {anime_id_str} not found when admin {user_id} attempted to add season {season_to_add}.", exc_info=True)
             await callback_query.message.edit_text("💔 Error: Anime not found to add season.", parse_mode=config.PARSE_MODE)
             await clear_user_state(user_id);
             await manage_content_command(client, callback_query.message)

    except ValueError: await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid season number data.");
    except Exception as e: content_logger.error(f"FATAL error handling content_add_new_season callback {data} for admin {user_id}: {e}", exc_info=True); await clear_user_state(user_id); await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED); await manage_content_command(client, callback_query.message);

@Client.on_callback_query(filters.regex(f"^content_remove_season_select{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_remove_season_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Select season to remove...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_SEASONS_LIST):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking remove season select. Data: {data}. State data: {user_state.data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting season to remove.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        anime_id_str = data.split(config.CALLBACK_DATA_SEPARATOR)[1]
        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id mismatch for remove season select: {user_state.data.get('anime_id')} vs callback {anime_id_str}. Updating state data.")
             user_state.data["anime_id"] = anime_id_str

        anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})
        if not anime_doc:
            content_logger.error(f"Anime {anime_id_str} not found for removing season for admin {user_id}. State data: {user_state.data}")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found.", disable_web_page_preview=True)
            await clear_user_state(user_id); return


        anime = Anime(**anime_doc)
        seasons = sorted(anime.seasons, key=lambda s: s.season_number)

        if not seasons:
            await edit_or_send_message(client, chat_id, message_id, "🤔 No seasons available to remove for this anime.", disable_web_page_preview=True)
            return

        await set_user_state(user_id, "content_management", ContentState.CONFIRM_REMOVE_SEASON, data=user_state.data)


        menu_text = f"🗑️ <b><u>Remove Season from</u></b> <b>{anime.name}</b> 🗑️\n\n👇 Select the season you want to **<u>permanently remove</u>**: (This will delete all episodes and files in that season!)"

        buttons = []
        for season in seasons:
             season_number = season.season_number
             buttons.append([InlineKeyboardButton(f"❌ Remove Season {season_number}", callback_data=f"content_confirm_remove_season{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}")])


        buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"content_manage_seasons|{anime_id_str}")])
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")])
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])

        reply_markup = InlineKeyboardMarkup(buttons)

        await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)

    except Exception as e:
        content_logger.error(f"FATAL error handling content_remove_season_select callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message);


@Client.on_callback_query(filters.regex(f"^content_confirm_remove_season{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_confirm_remove_season_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Removing season permanently...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.CONFIRM_REMOVE_SEASON):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking confirm remove season final. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for confirming season removal.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 3: raise ValueError("Invalid callback data format for removing season.")
        anime_id_str = parts[1]
        season_number_to_remove = int(parts[2])

        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id mismatch for confirm remove season: {user_state.data.get('anime_id')} vs callback {anime_id_str}. Data mismatch!")
             await edit_or_send_message(client, chat_id, message_id, "💔 Data mismatch. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return


        content_logger.info(f"Admin {user_id} confirming remove Season {season_number_to_remove} from anime {anime_id_str}.")


        update_result = await MongoDB.anime_collection().update_one(
            {"_id": ObjectId(anime_id_str)},
            {"$pull": {"seasons": {"season_number": season_number_to_remove}}}
        )
        await MongoDB.anime_collection().update_one({"_id": ObjectId(anime_id_str)}, {"$set": {"last_updated_at": datetime.now(timezone.utc)}})


        if update_result.matched_count > 0:
             if update_result.modified_count > 0:
                  content_logger.info(f"Admin {user_id} successfully removed Season {season_number_to_remove} from anime {anime_id_str}.")
                  await edit_or_send_message(client, chat_id, message_id, f"✅ Permanently removed Season **<u>{season_number_to_remove}</u>** from this anime.", disable_web_page_preview=True)


                  updated_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})
                  if updated_anime_doc:
                       await display_seasons_management_menu(client, callback_query.message, Anime(**updated_anime_doc))

                  else:
                       content_logger.error(f"Failed to re-fetch anime {anime_id_str} seasons after removal for admin {user_id}.", exc_info=True)
                       await client.send_message(chat_id, "💔 Removed season, but failed to reload the seasons menu.", parse_mode=config.PARSE_MODE)
                       await clear_user_state(user_id);
                       await manage_content_command(client, callback_query.message)

             elif update_result.matched_count > 0:
                 content_logger.warning(f"Admin {user_id} confirmed remove season {season_number_to_remove} for {anime_id_str} but modified_count was 0. Season not found or already removed.")
                 await edit_or_send_message(client, chat_id, message_id, f"⚠️ Season **<u>{season_number_to_remove}</u>** was not found or already removed.", disable_web_page_preview=True)

                 updated_anime_doc = await MongoDB.anime_collection().find_one({"_id": ObjectId(anime_id_str)}, {"seasons": 1, "name": 1})
                 if updated_anime_doc:
                      await display_seasons_management_menu(client, callback_query.message, Anime(**updated_anime_doc))
                 else:
                       content_logger.error(f"Failed to fetch anime {anime_id_str} after failed season removal attempt for admin {user_id}.", exc_info=True)
                       await client.send_message(chat_id, "💔 Season not found. Failed to reload season menu.", parse_mode=config.PARSE_MODE)


        else:
            content_logger.error(f"Anime ID {anime_id_str} not found during remove season update operation by admin {user_id} (Season {season_number_to_remove}).")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found. Cannot remove season.", disable_web_page_preview=True)
            await clear_user_state(user_id);
            await manage_content_command(client, callback_query.message);

    except ValueError:
        content_logger.warning(f"Admin {user_id} invalid callback data format for final remove season: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid data in callback.", disable_web_page_preview=True)

    except Exception as e:
        content_logger.error(f"FATAL error handling content_confirm_remove_season callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message)

async def display_episodes_management_list(client: Client, message: Message, anime_id_str: str, anime_name: str, season_number: int, episodes: List[Dict]):
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id


    menu_text = strings.MANAGE_EPISODES_TITLE.format(anime_name=anime_name, season_number=season_number) + "\n\n"

    buttons = []
    if not episodes:
        menu_text += "No episodes added for this season. Add episodes by setting the Total Episodes count for the season in the Seasons Menu.\n\n"


    for episode in episodes:
         ep_number = episode.get("episode_number")
         if ep_number is None:
             content_logger.warning(f"Admin {user_id} found episode document with no episode_number for {anime_id_str}/S{season_number}. Skipping display.")
             continue

         files = episode.get("files", [])
         release_date = episode.get("release_date")

         ep_label = f"🎬 EP{ep_number:02d}"

         if files:
             ep_label += f" [{strings.EPISODE_STATUS_HAS_FILES}]"
         elif isinstance(release_date, datetime):
              formatted_date = release_date.astimezone(timezone.utc).strftime('%Y-%m-%d')
              ep_label += f" [{strings.EPISODE_STATUS_HAS_DATE.format(date=formatted_date)}]"
         else:
              ep_label += f" [{strings.EPISODE_STATUS_NO_CONTENT}]"


         buttons.append([InlineKeyboardButton(ep_label, callback_data=f"content_manage_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{ep_number}")])


    buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"content_manage_seasons|{anime_id_str}")])

    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")])
    buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])


    reply_markup = InlineKeyboardMarkup(buttons)

    await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex(f"^content_select_episode{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_select_episode_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Loading episode management menu...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODES_LIST):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking select episode. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting episode.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for managing episode.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number:
            content_logger.warning(f"Admin {user_id} state anime/season mismatch for manage episode: {user_state.data.get('anime_id')}/S{user_state.data.get('season_number')} vs callback {anime_id_str}/S{season_number}. Updating state data.")
            user_state.data.update({"anime_id": anime_id_str, "season_number": season_number})
            await set_user_state(user_id, user_state.handler, user_state.step, data=user_state.data)


        content_logger.info(f"Admin {user_id} selected Episode {episode_number} from {anime_id_str}/S{season_number} for management.")

        filter_query = {"_id": ObjectId(anime_id_str)}
        projection = {"name": 1, "seasons": {"$elemMatch": {"season_number": season_number}}}

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0]:
             content_logger.error(f"Anime/Season {anime_id_str}/S{season_number} not found for episode management (manage episode callback) for admin {user_id}.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime or season not found for episode management.", disable_web_page_preview=True)
             await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


        anime_name = anime_doc.get("name", "Anime Name Unknown")
        season_data = anime_doc["seasons"][0]
        episodes_list_of_season = season_data.get("episodes", [])
        current_episode_doc = next((ep for ep in episodes_list_of_season if ep.get("episode_number") == episode_number), None)

        if not current_episode_doc:
             content_logger.error(f"Episode {episode_number} not found in season {season_number} for anime {anime_id_str} for admin {user_id}. Doc: {anime_doc}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Episode not found in season.", disable_web_page_preview=True)

             filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection_season_episodes = {"name": 1, "seasons.$": 1}
             anime_doc_season = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes)
             if anime_doc_season and anime_doc_season.get("seasons") and anime_doc_season["seasons"][0]:
                  episodes_list = anime_doc_season["seasons"][0].get("episodes", [])
                  episodes_list.sort(key=lambda e: e.get("episode_number", 0))
                  await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODES_LIST, data={"anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_doc_season.get("name", "Anime")})

                  await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_doc_season.get("name", "Anime"), season_number, episodes_list)
             else:
                 content_logger.error(f"Failed to fetch anime/season after episode not found for admin {user_id}. Cannot re-display list.")
                 await edit_or_send_message(client, chat_id, message_id, "💔 Error loading episode list.", disable_web_page_preview=True)
                 await clear_user_state(user_id); await manage_content_command(client, callback_query.message);

            return


        await set_user_state(
             user_id, "content_management", ContentState.MANAGING_EPISODE_MENU,
             data={
                 "anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number, "anime_name": anime_name,
             }
         )

        await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, current_episode_doc)

    except ValueError:
        content_logger.warning(f"Admin {user_id} invalid episode number data in callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid episode number data in callback.", disable_web_page_preview=True)

    except Exception as e:
         content_logger.error(f"FATAL error handling content_manage_episode callback {data} for admin {user_id}: {e}", exc_info=True)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await clear_user_state(user_id);
         await manage_content_command(client, callback_query.message);

async def display_episode_management_menu(client: Client, message: Message, anime_name: str, season_number: int, episode_number: int, episode_data: Dict):
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id


     menu_text = f"🛠️ <b><u>Manage Episode</u></b> <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> 🛠️\n\n"

     buttons = []
     files = episode_data.get("files", [])
     release_date = episode_data.get("release_date")

     user_state = asyncio.run(get_user_state(user_id))
     anime_id_str = user_state.data.get('anime_id')
     if not anime_id_str:
         content_logger.error(f"Missing anime_id in state data while displaying episode menu for admin {user_id}. State: {user_state.data}")
         await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing anime ID in state. Cannot display menu.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, message); return


     if files:
         menu_text += f"📥 <b><u>Available Versions</u></b>:\n"
         for i, file_ver_dict in enumerate(files):
              quality = file_ver_dict.get('quality_resolution', 'Unknown Quality')
              size_bytes = file_ver_dict.get('file_size_bytes', 0)
              audio_langs = file_ver_dict.get('audio_languages', [])
              subs_langs = file_ver_dict.get('subtitle_languages', [])

              formatted_size = f"{size_bytes / (1024 * 1024):.2f} MB" if size_bytes > 0 else "0 MB"
              if size_bytes >= 1024 * 1024 * 1024: formatted_size = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
              audio_str = ', '.join(audio_langs) if audio_langs else 'N/A'
              subs_str = ', '.join(subs_langs) if subs_langs else 'None'


              menu_text += f"  <b>{i+1}.</b> <b>{quality}</b> ({formatted_size}) 🎧 {audio_str} 📝 {subs_str}\n"

         buttons = [
             [InlineKeyboardButton(strings.BUTTON_ADD_OTHER_VERSION.format(episode_number=episode_number), callback_data=f"content_add_file_version{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
             [InlineKeyboardButton(strings.BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number + 1}")],
             [InlineKeyboardButton(strings.BUTTON_DELETE_FILE_VERSION_SELECT, callback_data=f"content_delete_file_version_select{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
         ]

     elif isinstance(release_date, datetime):
          formatted_date = release_date.astimezone(timezone.utc).strftime('%Y-%m-%d')
          menu_text = f"🛠️ <b><u>Manage Episode</u></b> <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> 🛠️\n\n"
          menu_text += strings.EPISODE_OPTIONS_WITH_RELEASE_DATE_ADMIN.format(release_date=formatted_date) + "\n\n"


          buttons = [
             [InlineKeyboardButton(strings.BUTTON_ADD_EPISODE_FILE, callback_data=f"content_add_file_version{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
             [InlineKeyboardButton(strings.BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number + 1}")],
             [InlineKeyboardButton(strings.BUTTON_REMOVE_EPISODE.format(episode_number=episode_number), callback_data=f"content_remove_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
          ]
     else:
         menu_text = f"🛠️ <b><u>Manage Episode</u></b> <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> 🛠️\n\n"
         menu_text += f"❓ No files or release date set yet for this episode.\n\n"

         buttons = [
             [InlineKeyboardButton(strings.BUTTON_ADD_EPISODE_FILE, callback_data=f"content_add_file_version{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
             [InlineKeyboardButton(strings.BUTTON_ADD_RELEASE_DATE, callback_data=f"content_add_release_date{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
             [InlineKeyboardButton(strings.BUTTON_NEXT_EPISODE.format(next_episode_number=episode_number + 1), callback_data=f"content_go_next_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number + 1}")],
             [InlineKeyboardButton(strings.BUTTON_REMOVE_EPISODE.format(episode_number=episode_number), callback_data=f"content_remove_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")],
         ]


     buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"content_select_season{config.CALLBACK_DATA_SEPARATOR}{user_state.data.get('anime_id')}{config.CALLBACK_DATA_SEPARATOR}{season_number}")])
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")])
     buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])


     reply_markup = InlineKeyboardMarkup(buttons)

     await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)

@Client.on_callback_query(filters.regex(f"^content_add_release_date{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_add_release_date_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODE_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking add release date. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for adding release date.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for release date.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for add release date: {user_state.data} vs callback {data}. Updating state data.")
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number})
             await set_user_state(user_id, user_state.handler, user_state.step, data=user_state.data)


        anime_name = user_state.data.get("anime_name", "Anime")


        await set_user_state(user_id, "content_management", ContentState.AWAITING_RELEASE_DATE_INPUT, data=user_state.data)

        prompt_text = strings.PROMPT_RELEASE_DATE.format(episode_number=episode_number, anime_name=anime_name)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])

        await edit_or_send_message(
            client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True
        )

    except Exception as e:
        content_logger.error(f"Error handling content_add_release_date callback for admin {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await clear_user_state(user_id)

async def handle_awaiting_release_date_input(client: Client, message: Message, user_state: UserState, date_text: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    anime_id_str = user_state.data.get("anime_id")
    season_number = user_state.data.get("season_number")
    episode_number = user_state.data.get("episode_number")
    anime_name = user_state.data.get("anime_name", "Anime")


    if not all([anime_id_str, season_number is not None, episode_number is not None]):
        content_logger.error(f"Admin {user_id} sent date input but missing required state data: {user_state.data}. State: {user_state.step}")
        await message.reply_text("💔 Error: Missing episode context from state data for release date input. Process cancelled.", parse_mode=config.PARSE_MODE)
        await clear_user_state(user_id); return


    content_logger.info(f"Admin {user_id} provided release date input '{date_text}' for {anime_name} S{season_number}E{episode_number} in state {user_state.step}.")


    try:
        release_date_obj = datetime.strptime(date_text, '%d/%m/%Y').replace(tzinfo=timezone.utc)

        filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}
        update_operation = {
             "$set": {
                  "seasons.$.episodes.$.release_date": release_date_obj,
                  "last_updated_at": datetime.now(timezone.utc)
             },
             "$unset": {"seasons.$.episodes.$.files": ""}
        }

        update_result = await MongoDB.anime_collection().update_one(
            filter_query, update_operation
        )

        if update_result.matched_count > 0:
             if update_result.modified_count > 0:
                  content_logger.info(f"Admin {user_id} set release date for {anime_id_str}/S{season_number}E{episode_number}. Removed files if any.")
                  await message.reply_text(strings.RELEASE_DATE_SET_SUCCESS.format(episode_number=episode_number, release_date=date_text), parse_mode=config.PARSE_MODE)

                  filter_query_episode = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}
                  projection_episode = {"name": 1, "seasons.$": 1} # Project matched season

                  anime_doc = await MongoDB.anime_collection().find_one(filter_query_episode, projection_episode)

                  if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
                       anime_name_for_menu = anime_doc.get("name", "Anime Name Unknown")
                       season_data = anime_doc["seasons"][0]
                       episodes_list = season_data.get("episodes", [])
                       updated_episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None)

                       if updated_episode_doc:
                           updated_state_data = {k: v for k, v in user_state.data.items() if k != "temp_input"} # Remove temp input from state
                           await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODE_MENU, data=updated_state_data)
                           await asyncio.sleep(1)
                           await display_episode_management_menu(client, message, anime_name_for_menu, season_number, episode_number, updated_episode_doc)

                       else:
                            content_logger.error(f"Failed to find updated episode doc after setting release date for admin {user_id}.")
                            await message.reply_text("💔 Set release date, but failed to load episode management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                            await clear_user_state(user_id); await manage_content_command(client, message);

                  else:
                       content_logger.error(f"Failed to fetch anime/season/episode after setting release date for admin {user_id}.")
                       await message.reply_text("💔 Set release date, but failed to reload episode menu.", parse_mode=config.PARSE_MODE)
                       await clear_user_state(user_id); await manage_content_command(client, message);


             elif update_result.matched_count > 0:
                  content_logger.warning(f"Admin {user_id} set release date for {anime_id_str}/S{season_number}E{episode_number} but modified_count was 0. Same date or no files?")
                  await message.reply_text("⚠️ Release date update modified 0 documents. Episode not found, same date, or no files to remove?", parse_mode=config.PARSE_MODE)
                  # State is AWAITING_RELEASE_DATE_INPUT. Admin can re-enter date or cancel.

             else:
                 content_logger.error(f"Anime/Season/Episode {anime_id_str}/S{season_number}E{episode_number} not found during release date update by admin {user_id}.")
                 await message.reply_text("💔 Error: Episode not found for release date update.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id); await manage_content_command(client, message);

    except ValueError:
        await message.reply_text(strings.INVALID_DATE_FORMAT, parse_mode=config.PARSE_MODE)

    except Exception as e:
         content_logger.error(f"Error handling release date input for admin {user_id}: {e}", exc_info=True)
         await message.reply_text("💔 Error saving release date.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id)

@Client.on_callback_query(filters.regex(f"^content_go_next_episode{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_go_next_episode_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Going to next episode...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management"):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step if user_state else 'None'} clicking next episode. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for going to next episode.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return

    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for next episode.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        next_episode_number = int(parts[3])

        filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
        projection = {"name": 1, "seasons.$": 1}

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0]:
             content_logger.error(f"Anime/Season {anime_id_str}/S{season_number} not found while attempting to go to next episode {next_episode_number} for admin {user_id}.")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime or season not found.", disable_web_page_preview=True)
             await clear_user_state(user_id); return

        anime_name = anime_doc.get("name", "Anime Name Unknown")
        season_data = anime_doc["seasons"][0]
        episodes = season_data.get("episodes", [])

        target_episode_doc = next((ep for ep in episodes if ep.get("episode_number") == next_episode_number), None)

        if target_episode_doc:
             content_logger.info(f"Admin {user_id} going to next episode: {anime_name} S{season_number}E{next_episode_number}.")

             await set_user_state(
                  user_id, "content_management", ContentState.MANAGING_EPISODE_MENU,
                  data={
                      "anime_id": anime_id_str, "season_number": season_number, "episode_number": next_episode_number, "anime_name": anime_name,
                      "temp_upload": None, "temp_metadata": None # Clear temp data from previous episode add if any
                  }
              )

             await display_episode_management_menu(client, callback_query.message, anime_name, season_number, next_episode_number, target_episode_doc)

        else:
             content_logger.info(f"Admin {user_id} attempted to go to non-existent episode E{next_episode_number} for {anime_name} S{season_number}. Assuming end of season.")
             await edit_or_send_message(client, chat_id, message_id, f"🎬 You've reached the end of Season <b><u>{season_number}</u></b>'s episodes.", parse_mode=config.PARSE_MODE)

             filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection_season_episodes = {"name": 1, "seasons.$": 1}
             anime_doc_season = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes)

             if anime_doc_season and anime_doc_season.get("seasons") and anime_doc_season["seasons"][0]:
                  episodes_list = anime_doc_season["seasons"][0].get("episodes", [])
                  episodes_list.sort(key=lambda e: e.get("episode_number", 0))
                  await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODES_LIST, data={"anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_doc_season.get("name", "Anime")})

                  await asyncio.sleep(1)
                  await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_doc_season.get("name", "Anime Name"), season_number, episodes_list)
             else:
                  content_logger.error(f"Failed to fetch anime/season to re-display list after going past last ep for admin {user_id}.")
                  await edit_or_send_message(client, chat_id, message_id, "💔 Failed to reload episodes list.", disable_web_page_preview=True)
                  await clear_user_state(user_id); await manage_content_command(client, callback_query.message);

    except ValueError:
        content_logger.warning(f"Admin {user_id} invalid episode number data in callback: {data}")
        await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid episode number data in callback.", disable_web_page_preview=True)

    except Exception as e:
         content_logger.error(f"FATAL error handling content_go_next_episode callback {data} for admin {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await manage_content_command(client, callback_query.message);


@Client.on_callback_query(filters.regex(f"^content_add_file_version{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_add_file_version_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODE_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking add file version. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for adding file version.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for add file version.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for add file version: {user_state.data} vs callback {data}. Updating state data.")
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number})
             await set_user_state(user_id, user_state.handler, user_state.step, data=user_state.data)


        anime_name = user_state.data.get("anime_name", "Anime")


        await set_user_state(user_id, "content_management", ContentState.UPLOADING_FILE, data=user_state.data)

        prompt_text = strings.ADD_FILE_PROMPT.format(episode_number=episode_number, season_number=season_number, anime_name=anime_name)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")]])

        await edit_or_send_message(
            client, chat_id, message_id, prompt_text, reply_markup, disable_web_page_preview=True
        )

    except Exception as e:
        content_logger.error(f"Error handling content_add_file_version callback for admin {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await clear_user_state(user_id)

async def handle_episode_file_upload(client: Client, message: Message, user_state: UserState, file_obj: Union[Document, Video]):
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_id = message.id


    anime_id_str = user_state.data.get("anime_id")
    season_number = user_state.data.get("season_number")
    episode_number = user_state.data.get("episode_number")
    anime_name = user_state.data.get("anime_name", "Anime Name Unknown")

    if not all([anime_id_str, season_number is not None, episode_number is not None]):
         content_logger.error(f"Admin {user_id} uploaded episode file but missing critical episode context from state {user_state.step}: {user_state.data}")
         await message.reply_text("💔 Error: Missing episode context from state data for file upload. Process cancelled.", parse_mode=config.PARSE_MODE)
         await clear_user_state(user_id);
         await manage_content_command(client, message); return


    content_logger.info(f"Admin {user_id} uploaded episode file ({file_obj.file_id}, {file_obj.file_size} bytes) for {anime_name} S{season_number}E{episode_number} in UPLOADING_FILE.")

    temp_upload_data = {
        "file_id": file_obj.file_id,
        "file_unique_id": file_obj.file_unique_id,
        "file_name": file_obj.file_name or f"EP{episode_number:02d}_File_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "file_size_bytes": file_obj.file_size,
        "mime_type": file_obj.mime_type,
        "duration": getattr(file_obj, 'duration', None),
        "width": getattr(file_obj, 'width', None),
        "height": getattr(file_obj, 'height', None),
        "added_at": datetime.now(timezone.utc),
    }

    user_state.data["temp_upload"] = temp_upload_data
    user_state.data["temp_metadata"] = {
         "quality_resolution": None,
         "audio_languages": [],
         "subtitle_languages": []
     }

    await set_user_state(user_id, "content_management", ContentState.UPLOADING_FILE, data=user_state.data)

    await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_QUALITY, data=user_state.data)


    await message.reply_text(f"✅ File received for Episode {episode_number:02d}!\n\nLoading metadata selection...", parse_mode=config.PARSE_MODE)

    await prompt_for_metadata_quality(client, chat_id)

async def prompt_for_metadata_quality(client: Client, chat_id: int):
    prompt_text = strings.ADD_FILE_METADATA_PROMPT_BUTTONS.format()
    qualities = config.QUALITY_PRESETS

    buttons = []
    for quality in qualities:
         buttons.append(InlineKeyboardButton(quality, callback_data=f"content_select_quality{config.CALLBACK_DATA_SEPARATOR}{quality}"))

    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    keyboard_rows.append([InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        await client.send_message(
             chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True
         )
    except Exception as e:
        content_logger.error(f"Failed to send quality prompt to chat {chat_id}: {e}", exc_info=True)

@Client.on_callback_query(filters.regex(f"^content_select_quality{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_select_quality_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: common_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_QUALITY):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking quality select {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting quality.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for selecting quality.")
        selected_quality = parts[1]

        if selected_quality not in config.QUALITY_PRESETS:
             content_logger.warning(f"Admin {user_id} selected non-preset quality: {selected_quality}. Saving anyway.")
             await callback_query.answer("⚠️ Non-preset quality selected. Saving anyway.", show_alert=False)


        user_state.data["temp_metadata"] = user_state.data.get("temp_metadata", {})
        user_state.data["temp_metadata"]["quality_resolution"] = selected_quality; # Store

        await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_AUDIO, data=user_state.data)


        audio_prompt_text = f"🎧 Quality selected: <b><u>{selected_quality}</u></b>.\n\n" + strings.PROMPT_AUDIO_LANGUAGES_BUTTONS;
        await client.send_message(chat_id, audio_prompt_text, parse_mode=config.PARSE_MODE);
        await prompt_for_metadata_audio(client, chat_id, []);

        try:
             await callback_query.message.edit_text(f"✅ Quality selected: <b><u>{selected_quality}</u></b>.", parse_mode=config.PARSE_MODE, reply_markup=None)
        except MessageNotModified: pass
        except Exception as e:
             content_logger.warning(f"Failed to edit quality select message after quality chosen for admin {user_id}: {e}")


    except Exception as e:
        content_logger.error(f"FATAL error handling content_select_quality callback {data} for admin {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await clear_user_state(user_id);
        await manage_content_command(client, callback_query.message);

async def prompt_for_metadata_audio(client: Client, chat_id: int, current_selection: List[str]):
    prompt_text = strings.PROMPT_AUDIO_LANGUAGES_BUTTONS
    languages = config.AUDIO_LANGUAGES_PRESETS

    buttons = []
    for lang in languages:
        is_selected = lang in current_selection
        button_text = f"🎧 {lang}" if is_selected else f"⬜ {lang}"
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_audio{config.CALLBACK_DATA_SEPARATOR}{lang}"))

    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    keyboard_rows.append([
        InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Audio Languages"), callback_data="content_audio_done"),
        InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        await client.send_message(
             chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True
         )
    except Exception as e:
        content_logger.error(f"Failed to send audio languages prompt to chat {chat_id}: {e}", exc_info=True)

@Client.on_callback_query(filters.regex(f"^content_toggle_audio{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_toggle_audio_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: content_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_AUDIO):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking audio toggle {data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting audio.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for toggling audio language.")
        language_to_toggle = parts[1]

        user_state.data["temp_metadata"] = user_state.data.get("temp_metadata", {})
        selected_audio_languages = user_state.data["temp_metadata"].get("audio_languages", [])

        if language_to_toggle not in config.AUDIO_LANGUAGES_PRESETS:
             content_logger.warning(f"Admin {user_id} attempted to toggle non-preset audio: {language_to_toggle}.")
             await callback_query.answer("🚫 Invalid audio option.", show_alert=False)
             return

        if language_to_toggle in selected_audio_languages: selected_audio_languages.remove(language_to_toggle)
        else: selected_audio_languages.append(language_to_toggle)

        selected_audio_languages.sort()

        user_state.data["temp_metadata"]["audio_languages"] = selected_audio_languages;
        await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_AUDIO, data=user_state.data);

        audio_languages_presets = config.AUDIO_LANGUAGES_PRESETS
        buttons = []
        for lang in audio_languages_presets:
            is_selected = lang in selected_audio_languages
            button_text = f"🎧 {lang}" if is_selected else f"⬜ {lang}"
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_audio{config.CALLBACK_DATA_SEPARATOR}{lang}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

        keyboard_rows.append([
             InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Audio Languages"), callback_data="content_audio_done"),
             InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        try:
             await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        except MessageNotModified: pass
        except FloodWait as e:
            content_logger.warning(f"FloodWait while editing audio buttons for admin {user_id} (retry in {e.value}s): {e}")
            await asyncio.sleep(e.value)
            try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
            except Exception as retry_e: content_logger.error(f"Retry failed editing audio buttons for admin {user_id} (msg {message_id}): {retry_e}", exc_info=True)

    except Exception as e:
        content_logger.error(f"FATAL error handling content_toggle_audio callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        try: await callback_query.answer(strings.ERROR_OCCURRED, show_alert=True); except Exception: pass;
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);


@Client.on_callback_query(filters.regex("^content_audio_done$") & filters.private)
async def handle_audio_done_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Audio languages selected. Proceeding to subtitles...")
    except Exception: common_logger.warning(f"Failed to answer callback query content_audio_done from admin {user_id}.")


    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_AUDIO):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking Done Audio. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Your previous process was cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    temp_metadata = user_state.data.get("temp_metadata", {})
    selected_audio_languages = temp_metadata.get("audio_languages", [])
    content_logger.info(f"Admin {user_id} finished selecting audio languages: {selected_audio_languages}")

    await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_SUBTITLES, data=user_state.data)

    subtitle_prompt_text = f"🎧 Audio Languages saved: <b>{', '.join(selected_audio_languages) if selected_audio_languages else 'None'}</b>.\n\n" + strings.PROMPT_SUBTITLE_LANGUAGES_BUTTONS;

    await client.send_message(chat_id, subtitle_prompt_text, parse_mode=config.PARSE_MODE);
    await prompt_for_metadata_subtitles(client, chat_id, []);

    try:
         await callback_query.message.edit_text(f"✅ Audio Languages saved: <b>{', '.join(selected_audio_languages) if selected_audio_languages else 'None'}</b>.", parse_mode=config.PARSE_MODE, reply_markup=None);
    except MessageNotModified: pass
    except Exception as e: content_logger.warning(f"Failed to edit message after audio done for admin {user_id}: {e}")


    except Exception as e:
        content_logger.error(f"FATAL error handling content_audio_done callback for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);
        await manage_content_command(client, callback_query.message)


async def prompt_for_metadata_subtitles(client: Client, chat_id: int, current_selection: List[str]):
    prompt_text = strings.PROMPT_SUBTITLE_LANGUAGES_BUTTONS
    languages = config.SUBTITLE_LANGUAGES_PRESETS

    buttons = []
    for lang in languages:
        is_selected = lang in current_selection
        button_text = f"📝 {lang}" if is_selected else f"⬜ {lang}"
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_subtitle{config.CALLBACK_DATA_SEPARATOR}{lang}"))

    keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

    keyboard_rows.append([
        InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Subtitle Languages"), callback_data="content_subtitles_done"),
        InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    try:
        await client.send_message(
             chat_id=chat_id, text=prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True
         )
    except Exception as e:
        content_logger.error(f"Failed to send subtitle languages prompt to chat {chat_id}: {e}", exc_info=True)

@Client.on_callback_query(filters.regex(f"^content_toggle_subtitle{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_toggle_subtitle_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id)
    except Exception: common_logger.warning(f"Failed to answer callback query {data} from admin {user_id}.")

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_SUBTITLES):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking subtitle toggle {data}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting subtitles.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for toggling subtitle language.")
        language_to_toggle = parts[1]

        user_state.data["temp_metadata"] = user_state.data.get("temp_metadata", {})
        selected_subtitle_languages = user_state.data["temp_metadata"].get("subtitle_languages", [])


        if language_to_toggle not in config.SUBTITLE_LANGUAGES_PRESETS:
             content_logger.warning(f"Admin {user_id} attempted to toggle non-preset subtitle: {language_to_toggle}.")
             await callback_query.answer("🚫 Invalid subtitle option.", show_alert=False)
             return

        if language_to_toggle in selected_subtitle_languages: selected_subtitle_languages.remove(language_to_toggle)
        else: selected_subtitle_languages.append(language_to_toggle)

        selected_subtitle_languages.sort()

        user_state.data["temp_metadata"]["subtitle_languages"] = selected_subtitle_languages;
        await set_user_state(user_id, "content_management", ContentState.SELECTING_METADATA_SUBTITLES, data=user_state.data);


        subtitle_languages_presets = config.SUBTITLE_LANGUAGES_PRESETS
        buttons = []
        for lang in subtitle_languages_presets:
            is_selected = lang in selected_subtitle_languages
            button_text = f"📝 {lang}" if is_selected else f"⬜ {lang}"
            buttons.append(InlineKeyboardButton(button_text, callback_data=f"content_toggle_subtitle{config.CALLBACK_DATA_SEPARATOR}{lang}"))

        keyboard_rows = [buttons[i:i + config.MAX_BUTTONS_PER_ROW] for i in range(0, len(buttons), config.MAX_BUTTONS_PER_ROW)]

        buttons_done_cancel = [
             InlineKeyboardButton(strings.BUTTON_METADATA_DONE_SELECTING.format(metadata_type="Subtitle Languages"), callback_data="content_subtitles_done"),
             InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="content_cancel")
        ]
        keyboard_rows.append(buttons_done_cancel)

        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        try:
             await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        except MessageNotModified: pass
        except FloodWait as e:
            content_logger.warning(f"FloodWait while editing subtitle buttons for admin {user_id} (retry in {e.value}s): {e}")
            await asyncio.sleep(e.value)
            try: await client.edit_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
            except Exception as retry_e: content_logger.error(f"Retry failed editing subtitle buttons for admin {user_id} (msg {message_id}): {retry_e}", exc_info=True)

    except Exception as e:
        content_logger.error(f"FATAL error handling content_toggle_subtitle callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        try: await callback_query.answer(strings.ERROR_OCCURRED, show_alert=True); except Exception: pass;
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True);

@Client.on_callback_query(filters.regex("^content_subtitles_done$") & filters.private)
async def handle_subtitles_done_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Subtitle languages selected. Saving file version...")
    except Exception: common_logger.warning(f"Failed to answer callback query content_subtitles_done from admin {user_id}.")


    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECTING_METADATA_SUBTITLES):
        content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking Done Subtitles. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state. Your previous process was cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    temp_upload_data = user_state.data.get("temp_upload")
    temp_metadata = user_state.data.get("temp_metadata")

    anime_id_str = user_state.data.get("anime_id")
    season_number = user_state.data.get("season_number")
    episode_number = user_state.data.get("episode_number")

    if not all([temp_upload_data, temp_metadata, anime_id_str, season_number is not None, episode_number is not None]):
        content_logger.error(f"Admin {user_id} finished metadata selection but missing required data from state for saving file version: temp_upload={bool(temp_upload_data)}, temp_metadata={bool(temp_metadata)}, context_ids={all([anime_id_str, season_number is not None, episode_number is not None])}. State data: {user_state.data}")
        await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing required data from state to save file version. Process cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); return


    selected_quality = temp_metadata.get("quality_resolution")
    selected_audio_languages = temp_metadata.get("audio_languages", [])
    selected_subtitle_languages = temp_metadata.get("subtitle_languages", [])

    if not selected_quality or not isinstance(selected_audio_languages, list) or not isinstance(selected_subtitle_languages, list):
        content_logger.error(f"Admin {user_id} finished metadata, but collected metadata structure is invalid. Temp metadata: {temp_metadata}")
        await edit_or_send_message(client, chat_id, message_id, "💔 Error: Invalid metadata collected. File version not saved. Process cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); return


    file_version_data_dict = {
         "file_id": temp_upload_data.get("file_id"),
         "file_unique_id": temp_upload_data.get("file_unique_id"),
         "file_name": temp_upload_data.get("file_name", "Unnamed File"),
         "file_size_bytes": temp_upload_data.get("file_size_bytes", 0),
         "quality_resolution": selected_quality,
         "audio_languages": selected_audio_languages,
         "subtitle_languages": selected_subtitle_languages,
         "added_at": datetime.now(timezone.utc),
     }

    try:
         new_file_version = FileVersion(**file_version_data_dict)
         content_logger.debug(f"Admin {user_id} built FileVersion model: {new_file_version.dict()}")
    except Exception as e:
        content_logger.error(f"Error creating FileVersion model for admin {user_id} before save: {e}. Data: {file_version_data_dict}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, "💔 Error validating file data before saving. File version not saved. Process cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); return


    try:
        success = await MongoDB.add_file_version_to_episode(
            anime_id=anime_id_str, season_number=season_number, episode_number=episode_number, file_version=new_file_version
        )

        if success:
            content_logger.info(f"Admin {user_id} successfully added file version ({new_file_version.quality_resolution}, {new_file_version.file_unique_id}) to {anime_id_str}/S{season_number}E{episode_number}.")
            await edit_or_send_message(
                 client, chat_id, message_id,
                 strings.FILE_ADDED_SUCCESS.format(
                     episode_number=episode_number,
                     quality=new_file_version.quality_resolution,
                     audio=', '.join(new_file_version.audio_languages) if new_file_version.audio_languages else 'N/A',
                     subs=', '.join(new_file_version.subtitle_languages) if new_file_version.subtitle_languages else 'None'
                 ), disable_web_page_preview=True
            )


            filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}
            projection = {"name": 1, "seasons.$": 1}

            anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

            if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
                 anime_name_for_menu = anime_doc.get("name", "Anime Name Unknown")
                 season_data = anime_doc["seasons"][0]
                 episodes_list = season_data.get("episodes", [])
                 updated_episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None)

                 if updated_episode_doc:
                     updated_state_data = {k: v for k, v in user_state.data.items() if k not in ["temp_upload", "temp_metadata"]}
                     await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODE_MENU, data=updated_state_data)
                     await asyncio.sleep(1)
                     await display_episode_management_menu(client, callback_query.message, anime_name_for_menu, season_number, episode_number, updated_episode_doc)

                 else:
                      content_logger.error(f"Failed to find updated episode document after saving file version for admin {user_id}. Anime ID: {anime_id_str}, S:{season_number}, E:{episode_number}.", exc_info=True)
                      await client.send_message(chat_id, "💔 Saved file, but failed to load episode management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                      await clear_user_state(user_id);
                      await manage_content_command(client, callback_query.message)


            else:
                 content_logger.critical(f"FATAL: Failed to fetch anime/season document after saving file version for admin {user_id}: {anime_id_str}/S{season_number}.", exc_info=True)
                 await client.send_message(chat_id, "💔 Saved file version, but a critical error occurred reloading data. Please navigate manually from Content Management menu.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id);
                 await manage_content_command(client, callback_query.message)

        else:
             content_logger.error(f"Failed to find episode {anime_id_str}/S{season_number}E{episode_number} to push file version. Modified 0 docs. Admin {user_id}.", exc_info=True)
             await edit_or_send_message(client, chat_id, message_id, "⚠️ Failed to add file version to episode. Episode path not found in database.", disable_web_page_preview=True)
             await clear_user_state(user_id);
             await manage_content_command(client, callback_query.message);


    except Exception as e:
        content_logger.critical(f"FATAL error handling content_subtitles_done callback for admin {user_id}: {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await clear_user_state(user_id)
        await manage_content_command(client, callback_query.message)


@Client.on_callback_query(filters.regex(f"^content_delete_file_version_select{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_delete_file_version_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Select file version to remove...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_EPISODE_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking delete file select. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for selecting file version to remove.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 4: raise ValueError("Invalid callback data format for deleting file version selection.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])

        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for delete file select: {user_state.data} vs callback {data}. Updating state data.")
             user_state.data.update({"anime_id": anime_id_str, "season_number": season_number, "episode_number": episode_number})
             await set_user_state(user_id, user_state.handler, user_state.step, data=user_state.data)


        filter_query = {"_id": ObjectId(anime_id_str)}
        projection = {"name": 1,
                      "seasons": {
                           "$elemMatch": {
                                "season_number": season_number,
                                "episodes": {
                                     "$elemMatch": {
                                          "episode_number": episode_number,
                                          "files": 1
                                     }
                                 }
                          }
                      }
                  }

        anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

        if not anime_doc or not anime_doc.get("seasons") or not anime_doc["seasons"][0] or not anime_doc["seasons"][0].get("episodes") or not anime_doc["seasons"][0]["episodes"][0]:
             content_logger.error(f"Anime/Season/Episode not found for deleting file version {anime_id_str}/S{season_number}E{episode_number} for admin {user_id}. Or no episodes array/data. Doc: {anime_doc}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Episode not found or no files available for deletion.", disable_web_page_preview=True)
             filter_query_season = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection_season_episodes = {"name": 1, "seasons.$": 1}
             anime_doc_season = await MongoDB.anime_collection().find_one(filter_query_season, projection_season_episodes)
             if anime_doc_season and anime_doc_season.get("seasons") and anime_doc_season["seasons"][0]:
                  episodes_list = anime_doc_season["seasons"][0].get("episodes", [])
                  episodes_list.sort(key=lambda e: e.get("episode_number", 0))
                  await set_user_state(user_id, "content_management", ContentState.MANAGING_EPISODES_LIST, data={"anime_id": anime_id_str, "season_number": season_number, "anime_name": anime_doc_season.get("name", "Anime")})

                  await display_episodes_management_list(client, callback_query.message, anime_id_str, anime_doc_season.get("name", "Anime Name"), season_number, episodes_list)
             else:
                 content_logger.error(f"Failed to fetch anime/season after episode not found for file delete for admin {user_id}. Cannot re-display list.")
                 await edit_or_send_message(client, chat_id, message_id, "💔 Error loading episode list.", disable_web_page_preview=True)
                 await clear_user_state(user_id); await manage_content_command(client, callback_query.message);

            return

        anime_name = anime_doc.get("name", "Anime Name Unknown")

        try:
             episode_data_proj = anime_doc["seasons"][0]["episodes"][0]
             files = episode_data_proj.get("files", [])
        except (KeyError, IndexError) as e:
            content_logger.error(f"Error accessing deeply nested files list in projected document for {anime_id_str}/S{season_number}E{episode_number} for admin {user_id}: {e}. Doc: {anime_doc}", exc_info=True)
            await edit_or_send_message(client, chat_id, message_id, "💔 Error accessing file data. Cannot display versions for deletion.", disable_web_page_preview=True)
            await handle_select_episode_callback(client, callback_query.message, user_state, f"content_manage_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")

            return

        if not files:
            content_logger.warning(f"Admin {user_id} attempted to delete file version but no files found for {anime_id_str}/S{season_number}E{episode_number}.")
            await edit_or_send_message(client, chat_id, message_id, "🤔 No file versions found for this episode to remove.", disable_web_page_preview=True)

            await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, current_episode_doc if 'current_episode_doc' in locals() else {})

            return


        await set_user_state(
             user_id, "content_management", ContentState.SELECT_FILE_VERSION_TO_DELETE,
             data={**user_state.data, "file_versions": files}
        )


        menu_text = f"🗑️ <b><u>Delete File Version</u></b> 🗑️\n\nSelect the version you want to **<u>permanently remove</u>** for <b>{anime_name}</b> - S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b>:"
        buttons = []

        for i, file_ver_dict in enumerate(files):
            quality = file_ver_dict.get('quality_resolution', 'Unknown Quality')
            size_bytes = file_ver_dict.get('file_size_bytes', 0)
            audio_langs = file_ver_dict.get('audio_languages', [])
            subs_langs = file_ver_dict.get('subtitle_languages', [])
            file_unique_id = file_ver_dict.get('file_unique_id', None)

            if file_unique_id is None:
                content_logger.error(f"File version dictionary in DB/state missing file_unique_id for {anime_id_str}/S{season_number}E{episode_number} index {i}. Skipping button.")
                continue

            formatted_size = f"{size_bytes / (1024 * 1024):.2f} MB" if size_bytes > 0 else "0 MB"
            if size_bytes >= 1024 * 1024 * 1024: formatted_size = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
            audio_str = ', '.join(audio_langs) if audio_langs else 'N/A'
            subs_str = ', '.join(subs_langs) if subs_langs else 'None'

            button_label = f"❌ {quality} ({formatted_size}) 🎧 {audio_str} 📝 {subs_str}"

            buttons.append([InlineKeyboardButton(button_label, callback_data=f"content_confirm_remove_file_version{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}{config.CALLBACK_DATA_SEPARATOR}{file_unique_id}")])


        buttons.append([InlineKeyboardButton(strings.BUTTON_BACK, callback_data=f"content_manage_episode{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}")])

        reply_markup = InlineKeyboardMarkup(buttons)


        await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)


    except ValueError:
         content_logger.warning(f"Admin {user_id} invalid callback data format for delete file version select: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid data in callback.", disable_web_page_preview=True)

    except Exception as e:
        content_logger.error(f"FATAL error handling content_delete_file_version_select callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message);


@Client.on_callback_query(filters.regex(f"^content_confirm_remove_file_version{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_confirm_remove_file_version_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Removing file version permanently...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.SELECT_FILE_VERSION_TO_DELETE):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking confirm remove file version. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for confirming file version removal.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 5: raise ValueError("Invalid callback data format for confirming file version removal.")
        anime_id_str = parts[1]
        season_number = int(parts[2])
        episode_number = int(parts[3])
        file_unique_id_to_remove = parts[4]

        if user_state.data.get("anime_id") != anime_id_str or user_state.data.get("season_number") != season_number or user_state.data.get("episode_number") != episode_number:
             content_logger.warning(f"Admin {user_id} state data mismatch for final remove file version: {user_state.data} vs callback {data}. Data mismatch!")
             await edit_or_send_message(client, chat_id, message_id, "💔 Data mismatch. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return


        content_logger.info(f"Admin {user_id} confirming remove file version {file_unique_id_to_remove} from {anime_id_str}/S{season_number}E{episode_number}.")


        success = await MongoDB.delete_file_version_from_episode(
            anime_id=anime_id_str,
            season_number=season_number,
            episode_number=episode_number,
            file_unique_id=file_unique_id_to_remove
        )


        if success:
             content_logger.info(f"Admin {user_id} successfully removed file version {file_unique_id_to_remove} from {anime_id_str}/S{season_number}E{episode_number}.")
             await edit_or_send_message(client, chat_id, message_id, strings.FILE_DELETED_SUCCESS, disable_web_page_preview=True)

             updated_state_data = {k: v for k, v in user_state.data.items() if k != "file_versions"}
             await set_user_state(
                  user_id, "content_management", ContentState.MANAGING_EPISODE_MENU, data={**updated_state_data}
              )

             filter_query = {"_id": ObjectId(anime_id_str), "seasons.season_number": season_number}
             projection = {"name": 1, "seasons.$": 1}

             anime_doc = await MongoDB.anime_collection().find_one(filter_query, projection)

             if anime_doc and anime_doc.get("seasons") and anime_doc["seasons"][0]:
                  anime_name = anime_doc.get("name", "Anime Name Unknown")
                  season_data = anime_doc["seasons"][0]
                  episodes_list = season_data.get("episodes", [])
                  updated_episode_doc = next((ep for ep in episodes_list if ep.get("episode_number") == episode_number), None)

                  if updated_episode_doc:
                       await asyncio.sleep(1)
                       await display_episode_management_menu(client, callback_query.message, anime_name, season_number, episode_number, updated_episode_doc)
                  else:
                       content_logger.error(f"Failed to find updated episode document after removing file version for admin {user_id}. Anime ID: {anime_id_str}, S:{season_number}, E:{episode_number}. Cannot display menu.")
                       await client.send_message(chat_id, "💔 Removed file version, but failed to load episode management menu. Please navigate back.", parse_mode=config.PARSE_MODE)
                       await clear_user_state(user_id);
                       await manage_content_command(client, callback_query.message);

             else:
                 content_logger.critical(f"FATAL: Failed to fetch anime/season document after removing file version for admin {user_id}: {anime_id_str}/S{season_number}.", exc_info=True)
                 await client.send_message(chat_id, "💔 Removed file version, but a critical error occurred reloading data. Please navigate manually from Content Management menu.", parse_mode=config.PARSE_MODE)
                 await clear_user_state(user_id);
                 await manage_content_command(client, callback_query.message);

        else:
            content_logger.warning(f"Admin {user_id} confirmed remove file version {file_unique_id_to_remove} but DB modified 0 docs. Version not found?")
            await edit_or_send_message(client, chat_id, message_id, "⚠️ File version was not found or already removed.", disable_web_page_preview=True)
            episode_context_callback_data = f"content_delete_file_version_select{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}{config.CALLBACK_DATA_SEPARATOR}{season_number}{config.CALLBACK_DATA_SEPARATOR}{episode_number}"
            await handle_delete_file_version_select_callback(client, callback_query.message, user_state, episode_context_callback_data)


    except ValueError:
         content_logger.warning(f"Admin {user_id} invalid callback data format for confirm remove file version: {data}")
         await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid data in callback.", disable_web_page_preview=True)

    except Exception as e:
         content_logger.critical(f"FATAL error handling content_confirm_remove_file_version callback {data} for admin {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await manage_content_command(client, callback_query.message)

# --- Implement Admin View All Anime List ---

# Callback from main CM menu: content_view_all_anime_list or pagination
@Client.on_callback_query(filters.regex("^content_view_all_anime_list") & filters.private)
@Client.on_callback_query(filters.regex(f"^content_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_admin_view_all_anime_list(client: Client, callback_query: CallbackQuery, user_state: UserState, page: int = 1):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return

    is_pagination_callback = data.startswith("content_admin_anime_list_page|")
    if is_pagination_callback:
         try: page = int(data.split(config.CALLBACK_DATA_SEPARATOR)[1])
         except ValueError: page = 1 # Default to page 1 if invalid

    content_logger.info(f"Admin {user_id} viewing all anime list, page {page}.")
    try: await client.answer_callback_query(message.id, f"Loading page {page}...")
    except Exception: content_logger.warning(f"Failed to answer callback query: {data} from admin {user_id}")


    # Ensure state is correct - could be from main CM menu or pagination
    await set_user_state(user_id, "content_management", ContentState.ADMIN_ANIME_LIST_VIEW, data={**user_state.data, "page": page})


    try:
        # Fetch all anime documents (or count for pagination)
        total_anime_count = await MongoDB.anime_collection().count_documents({})
        total_pages = (total_anime_count + config.PAGE_SIZE - 1) // config.PAGE_SIZE # Calculate total pages
        if page < 1: page = 1 # Ensure page is not less than 1
        if page > total_pages and total_pages > 0: page = total_pages # Ensure page is not more than total pages

        # Fetch anime documents for the current page, projecting needed fields
        skip_count = (page - 1) * config.PAGE_SIZE
        # Project only relevant fields for the list display (name, maybe counts, status, year?)
        anime_docs_on_page = await MongoDB.anime_collection().find({}, {"name": 1, "status": 1, "release_year": 1, "overall_download_count": 1}).sort("name", 1).skip(skip_count).limit(config.PAGE_SIZE).to_list(config.PAGE_SIZE) # Sort by name A-Z


        menu_text = f"📚 <b><u>Admin View All Anime</u></b> ({total_anime_count} total) 📚\n"
        if total_anime_count > 0:
             menu_text += f"Page <b>{page}</b> / <b>{total_pages}</b>\n\n"

        buttons = []
        if not anime_docs_on_page:
            menu_text += "No anime found in the database."

        # Create buttons for each anime on the current page to select for editing
        for anime_doc in anime_docs_on_page:
             # Display format: "Anime Name (Status, Year) [Downloads]"
             anime_name = anime_doc.get("name", "Unnamed Anime")
             status = anime_doc.get("status", "Unknown")
             year = anime_doc.get("release_year", "Unknown Year")
             downloads = anime_doc.get("overall_download_count", 0)
             anime_id_str = str(anime_doc["_id"]) # Get the ID

             button_label = f"✏️ {anime_name} ({status}, {year}) [{downloads} ↓]"

             # Callback to select this anime for editing: content_edit_existing|<anime_id> (Reuse handler)
             buttons.append([InlineKeyboardButton(button_label, callback_data=f"content_edit_existing{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")])


        # Add pagination buttons
        pagination_buttons = []
        if page > 1:
            pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_PREVIOUS_PAGE, callback_data=f"content_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}{page - 1}"))
        if page < total_pages:
             pagination_buttons.append(InlineKeyboardButton(strings.BUTTON_NEXT_PAGE, callback_data=f"content_admin_anime_list_page{config.CALLBACK_DATA_SEPARATOR}{page + 1}"))
        if pagination_buttons: # Only add if there are pagination buttons
             buttons.append(pagination_buttons)

        # Add Navigation buttons: Back to main CM menu, Home Bot Menu
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME_ADMIN_MENU, callback_data="content_management_main_menu")])
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])


        reply_markup = InlineKeyboardMarkup(buttons)


        await edit_or_send_message(client, chat_id, message_id, menu_text, reply_markup, disable_web_page_preview=True)


    except Exception as e:
         content_logger.error(f"FATAL error handling content_view_all_anime_list (page {page}) for admin {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id) # Clear state on error
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await manage_content_command(client, callback_query.message); # Offer to restart CM


# --- Implement Delete Anime (Confirmation and Final Deletion) ---

# Callback: content_delete_anime_prompt|<anime_id> (from display_anime_management_menu)
@Client.on_callback_query(filters.regex(f"^content_delete_anime_prompt{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_delete_anime_prompt(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Delete This Anime button, prompts for confirmation."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Initiating deletion confirmation...")
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be MANAGING_ANIME_MENU
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.MANAGING_ANIME_MENU):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking delete anime prompt. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for deleting anime.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse anime_id
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for delete anime prompt.")
        anime_id_str = parts[1]

         # Ensure callback data matches state context
        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id mismatch for delete anime prompt: {user_state.data.get('anime_id')} vs callback {anime_id_str}. Data mismatch!")
             # Decide how to handle this: log, abort, or update state data to trust callback
             user_state.data["anime_id"] = anime_id_str # Update state data to match callback action ID


        # Fetch anime name for confirmation message
        anime = await MongoDB.get_anime_by_id(anime_id_str)
        if not anime:
            content_logger.error(f"Anime {anime_id_str} not found for deletion prompt for admin {user_id}.")
            await edit_or_send_message(client, chat_id, message_id, "💔 Error: Anime not found for deletion.", disable_web_page_preview=True)
            # State is MANAGING_ANIME_MENU, likely okay to stay there, maybe re-display menu
            await display_anime_management_menu(client, callback_query.message, anime) # Will fetch again and display
            return


        # --- Set the state to CONFIRM_REMOVE_ANIME ---
        await set_user_state(user_id, "content_management", ContentState.CONFIRM_REMOVE_ANIME, data={**user_state.data, "anime_id": anime_id_str, "anime_name": anime.name}) # Store name and ID for final delete step


        # Display confirmation message and buttons
        confirm_text = f"💀 **<u>PERMANENTLY Delete Anime</u>** 💀\n\nAre you absolutely sure you want to **<u>permanently delete</u>** the anime: <b>{anime.name}</b>?\n\n<b>THIS WILL DELETE ALL SEASONS, EPISODES, FILE VERSIONS, AND RELATED DATA FOR THIS ANIME. THIS CANNOT BE UNDONE.</b>"

        buttons = [
            [InlineKeyboardButton(f"✅ Yes, Delete '{anime.name}' PERMANENTLY", callback_data=f"content_confirm_delete_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")], # New callback for final confirmation
            [InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data=f"content_cancel_delete_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id_str}")], # Specific cancel for this
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        # Edit the management menu message to show confirmation
        await edit_or_send_message(client, chat_id, message_id, confirm_text, reply_markup, disable_web_page_preview=True)


    except Exception as e:
         content_logger.error(f"FATAL error handling content_delete_anime_prompt callback {data} for admin {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id) # Clear state on error
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await manage_content_command(client, callback_query.message); # Offer to restart CM


# Callback for final confirmation of anime deletion
# Catches callbacks content_confirm_delete_anime|<anime_id>
@Client.on_callback_query(filters.regex(f"^content_confirm_delete_anime{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_confirm_delete_anime_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin confirming permanent anime deletion."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, "Deleting anime permanently...") # Indicate ongoing process
    except Exception: pass


    user_state = await get_user_state(user_id)
    # State should be CONFIRM_REMOVE_ANIME
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.CONFIRM_REMOVE_ANIME):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking confirm delete anime final. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for finalizing anime deletion.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return


    try:
        # Parse anime_id from callback data
        parts = data.split(config.CALLBACK_DATA_SEPARATOR)
        if len(parts) != 2: raise ValueError("Invalid callback data format for confirming anime removal.")
        anime_id_str = parts[1]

        # Ensure callback data matches state context
        if user_state.data.get("anime_id") != anime_id_str:
             content_logger.warning(f"Admin {user_id} state anime_id mismatch for final remove anime: {user_state.data.get('anime_id')} vs callback {anime_id_str}. Data mismatch!")
             await edit_or_send_message(client, chat_id, message_id, "💔 Data mismatch. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return # Clear broken state

        content_logger.info(f"Admin {user_id} confirming remove anime {anime_id_str} ('{user_state.data.get('anime_name', 'Unnamed')}') PERMANENTLY.")

        # --- Perform the database deletion ---
        # Delete the entire anime document by its _id
        delete_result = await MongoDB.anime_collection().delete_one({"_id": ObjectId(anime_id_str)})

        if delete_result.deleted_count > 0:
            content_logger.info(f"Admin {user_id} successfully deleted anime {anime_id_str}.")
            await edit_or_send_message(client, chat_id, message_id, f"✅ Permanently deleted anime: <b>{user_state.data.get('anime_name', 'Unnamed Anime')}</b>.", disable_web_page_preview=True)

            # --- Return to the main Content Management Menu ---
            # Clear the confirmation state and any anime-specific context data
            await clear_user_state(user_id) # Clears CONFIRM_REMOVE_ANIME state

            # Re-display the main content management menu as a final step.
            await manage_content_command(client, callback_query.message)


        else: # Matched count is 0 - Anime not found (already deleted?)
            content_logger.warning(f"Admin {user_id} clicked confirm remove anime {anime_id_str} but deleted_count was 0. Anime not found or already removed?")
            await edit_or_send_message(client, chat_id, message_id, "⚠️ Anime was not found or already removed.", disable_web_page_preview=True)
            # Return to main CM menu, as the anime they were trying to delete is gone.
            await clear_user_state(user_id) # Clear confirmation state
            await manage_content_command(client, callback_query.message); # Go to main CM menu

    except Exception as e:
         content_logger.critical(f"FATAL error handling content_confirm_delete_anime callback {data} for admin {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
         await manage_content_command(client, callback_query.message)


# Callback to cancel anime deletion confirmation, routes back to anime management menu
# Catches callbacks content_cancel_delete_anime|<anime_id>
@Client.on_callback_query(filters.regex(f"^content_cancel_delete_anime{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def handle_cancel_delete_anime_callback(client: Client, callback_query: CallbackQuery):
    """Handles admin clicking Cancel during anime deletion confirmation."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data # content_cancel_delete_anime|<anime_id>

    if user_id not in config.ADMIN_IDS: await client.answer_callback_query(message.id, "🚫 Unauthorized."); return
    try: await client.answer_callback_query(message.id, strings.ACTION_CANCELLED) # Toast
    except Exception: pass

    user_state = await get_user_state(user_id)
    # State should be CONFIRM_REMOVE_ANIME
    if not (user_state and user_state.handler == "content_management" and user_state.step == ContentState.CONFIRM_REMOVE_ANIME):
         content_logger.warning(f"Admin {user_id} in unexpected state {user_state.handler}:{user_state.step} clicking cancel delete anime. Data: {data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for cancelling anime deletion.", disable_web_page_preview=True)
         await clear_user_state(user_id); await manage_content_command(client, callback_query.message); return

    try:
        # Clear the CONFIRM_REMOVE_ANIME state
        # Return to the MANAGING_ANIME_MENU state
        # Get anime context from state data (anime_id, anime_name)
        anime_id_str = user_state.data.get("anime_id")
        anime_name = user_state.data.get("anime_name")

        if not anime_id_str:
             content_logger.error(f"Admin {user_id} cancelling anime delete, but missing anime ID context from state: {user_state.data}. State: {user_state.step}")
             await edit_or_send_message(client, chat_id, message_id, "💔 Error: Missing anime context in state data to return to menu. Process cancelled.", disable_web_page_preview=True)
             await clear_user_state(user_id); return


        # Reset state to MANAGING_ANIME_MENU, preserving anime context
        await set_user_state(user_id, "content_management", ContentState.MANAGING_ANIME_MENU, data={"anime_id": anime_id_str, "anime_name": anime_name})

        # Fetch the current anime data to redisplay the management menu.
        anime = await MongoDB.get_anime_by_id(anime_id_str)

        if anime:
             await edit_or_send_message(client, chat_id, message_id, strings.ACTION_CANCELLED, parse_mode=config.PARSE_MODE) # Edit previous message to confirm cancel
             await asyncio.sleep(1) # Short delay
             await display_anime_management_menu(client, callback_query.message, anime) # Use the message from callback for editing

        else:
            content_logger.error(f"Anime {anime_id_str} not found after cancelling deletion for admin {user_id}.")
            await edit_or_send_message(client, chat_id, message_id, "💔 Cancelled, but original anime not found to return to menu. Please navigate back.", disable_web_page_preview=True)
            await clear_user_state(user_id)
            await manage_content_command(client, callback_query.message) # Offer to restart CM


    except Exception as e:
        content_logger.error(f"FATAL error handling content_cancel_delete_anime callback {data} for admin {user_id}: {e}", exc_info=True)
        await clear_user_state(user_id)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
        await manage_content_command(client, callback_query.message)
