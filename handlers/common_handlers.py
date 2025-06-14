# handlers/common_handlers.py
import logging
import traceback
import sys
import asyncio
from datetime import datetime, timezone
from typing import Union, Optional, List
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser
from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant
from pyrogram.enums import ParseMode

import config
import strings

# Import database models and the MongoDB class
# Correct import for state management: import the MongoDB class itself
from database.mongo_db import MongoDB

# No longer import functions directly from database.mongo_db:
# from database.mongo_db import get_user_state, set_user_state, clear_user_state

from database.models import User, UserState


# Import handlers for routing
from . import tokens_handler
from . import content_handler # Handlers need to be imported
from . import search_handler
from . import browse_handler
from . import download_handler
from . import request_handler
from . import watchlist_handler
from . import premium_handler


# Import specific constants/states needed for routing media/text
# These state names should be defined in the handler modules themselves (like content_handler)
try:
    # Access state names from content_handler
    from .content_handler import ContentState
except ImportError:
     # Handle case where content_handler might not be ready/failed to import
     # Define a fallback or ensure the handler import itself succeeds.
     class ContentState: # Define dummy if import fails
          AWAITING_POSTER = "awaiting_poster"
          UPLOADING_FILE = "uploading_file"
     main_logger = logging.getLogger("main")
     main_logger.warning("Could not import ContentState from content_handler. Routing logic might be affected if handler is not fully implemented.", exc_info=True) # Log this potential issue


main_logger = logging.getLogger("main") # Access main logger from main.py setup
common_logger = logging.getLogger(__name__)


async def get_user(client: Client, user_id: int) -> Optional[User]:
    user_data = await MongoDB.users_collection().find_one({"user_id": user_id});
    if user_data:
        try:
            if "notification_settings" not in user_data or not isinstance(user_data["notification_settings"], dict): user_data["notification_settings"] = config.DEFAULT_NOTIFICATION_SETTINGS.copy();
            user = User(**user_data); return user;
        except Exception as e: common_logger.error(f"Error validating user data for user {user_id}: {e}", exc_info=True); return None;
    else:
        common_logger.info(f"User {user_id} not found. Creating new.");
        try:
            try: telegram_user: TelegramUser = await client.get_users(user_id); first_name = telegram_user.first_name; username = telegram_user.username;
            except Exception as e: common_logger.warning(f"Failed to fetch TG info for {user_id}: {e}"); first_name = "User"; username = None;
            new_user_dict = {"user_id": user_id, "first_name": first_name, "username": username, "tokens": config.START_TOKENS, "join_date": datetime.now(timezone.utc), "notification_settings": config.DEFAULT_NOTIFICATION_SETTINGS.copy()};
            new_user = User(**new_user_dict);
            insert_result = await MongoDB.users_collection().insert_one(new_user.dict(by_alias=True, exclude_none=True));
            common_logger.info(f"New user {user_id} inserted with DB ID {insert_result.inserted_id}"); new_user.id = new_user_dict.get('_id', insert_result.inserted_id);
            return new_user;
        except Exception as e: common_logger.error(f"Error inserting new user {user_id}: {e}", exc_info=True); return None;


async def save_user(user: User):
    try:
        update_data = user.dict(by_alias=True, exclude={"user_id"}, exclude_none=True);
        update_result = await MongoDB.users_collection().update_one({"user_id": user.user_id}, {"$set": update_data});
        if update_result.matched_count == 0: common_logger.warning(f"Save user failed: user doc {user.user_id} not found.");
    except Exception as e: common_logger.error(f"Error saving user data for user {user.user_id}: {e}", exc_info=True);


def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [ InlineKeyboardButton(strings.BUTTON_SEARCH, callback_data="menu_search"), InlineKeyboardButton(strings.BUTTON_BROWSE, callback_data="menu_browse"), ],
        [ InlineKeyboardButton(strings.BUTTON_PROFILE, callback_data="menu_profile"), InlineKeyboardButton(strings.BUTTON_EARN_TOKENS, callback_data="menu_earn_tokens"), ],
        [ InlineKeyboardButton(strings.BUTTON_PREMIUM, callback_data="menu_premium"), InlineKeyboardButton(strings.BUTTON_HELP, callback_data="menu_help"), ],
        [ InlineKeyboardButton(strings.BUTTON_LEADERBOARD, callback_data="menu_leaderboard"), InlineKeyboardButton(strings.BUTTON_LATEST, callback_data="menu_latest"), InlineKeyboardButton(strings.BUTTON_POPULAR, callback_data="menu_popular"), ],
    ]; return InlineKeyboardMarkup(buttons);


def get_user_mention(user: User) -> str:
    escaped_first_name = user.first_name.replace("&", "&").replace("<", "<").replace(">", ">") if user.first_name else "User";
    return f'<a href="tg://user?id={user.user_id}">{escaped_first_name}</a>';


async def edit_or_send_message(client: Client, chat_id: int, message_id: Optional[int], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = True):
    try:
        if message_id is not None: await client.edit_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=disable_web_page_preview);
        else: await client.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=disable_web_page_preview);
    except (MessageIdInvalid, MessageNotModified):
        common_logger.debug(f"Editing message {message_id} failed for chat {chat_id}. Sending as new."); await client.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=disable_web_page_preview);
    except FloodWait as e: common_logger.warning(f"FloodWait sending/editing msg for {chat_id}: {e.value}"); await asyncio.sleep(e.value); try: if message_id is not None: await client.edit_text(chat_id, message_id, text, reply_markup, config.PARSE_MODE, disable_web_page_preview); else: await client.send_message(chat_id, text, reply_markup, config.PARSE_MODE, disable_web_page_preview); except Exception as retry_e: common_logger.error(f"Retry after FloodWait failed for {chat_id}: {retry_e}", exc_info=True);
    except Exception as e: common_logger.error(f"Failed to send/edit message for chat {chat_id}: {e}", exc_info=True);


# --- Handler Functions ---

@Client.on_message(filters.command("start") & filters.private)
@Client.on_callback_query(filters.regex("^menu_home$"))
async def start_command_or_home_callback(client: Client, update: Union[Message, CallbackQuery]):
    user_id = update.from_user.id; chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id; is_callback = isinstance(update, CallbackQuery); message_id = update.id if isinstance(update, Message) else update.message.id;
    payload = None; if isinstance(update, Message) and len(update.command) > 1: payload = update.command[1];

    if payload:
        common_logger.info(f"User {user_id} received /start with payload: {payload}");
        # Calls handle_token_redemption which is an async function in tokens_handler
        redemption_result_message_key = await tokens_handler.handle_token_redemption(client, user_id, payload);
        user = await get_user(client, user_id); if user is None: common_logger.error(f"Failed to get user {user_id} after token payload.", exc_info=True); await edit_or_send_message(client, chat_id, None, strings.DB_ERROR); return;

        redemption_message_text = strings.ERROR_OCCURRED;
        try:
            redemption_message_text = getattr(strings, redemption_result_message_key);
            if redemption_result_message_key == "TOKEN_REDEEMED_SUCCESS": redemption_message_text = redemption_message_text.format(tokens_earned=config.TOKENS_PER_REDEEM, user_tokens=user.tokens);
        except AttributeError: common_logger.error(f"Invalid redemption result message key '{redemption_result_message_key}' returned by token handler.");
        if isinstance(update, Message) and payload is not None: await update.reply_text(redemption_message_text, parse_mode=config.PARSE_MODE);
        else: common_logger.warning(f"Attempted to send redemption result outside of /start payload message for user {user_id}. Sending as new message."); await client.send_message(chat_id=chat_id, text=redemption_message_text, parse_mode=config.PARSE_MODE);

    user = await get_user(client, user_id);
    if user is None: common_logger.critical(f"FATAL: Cannot display main menu. User data unavailable for {user_id}.", exc_info=True); await edit_or_send_message(client, chat_id, message_id if is_callback else None, strings.DB_ERROR); return;

    current_state = await MongoDB.get_user_state(user_id);
    if current_state:
         common_logger.debug(f"Cleared state {current_state.handler}:{current_state.step} for user {user_id} on return to main menu.");
         await MongoDB.clear_user_state(user_id);


    welcome_message_text = strings.WELCOME_MESSAGE.format();
    main_menu_keyboard = create_main_menu_keyboard();
    target_message_id = message_id if is_callback else None;

    if config.WELCOME_IMAGE_TELEGRAPH_LINK:
        try:
            if is_callback: try: await update.message.delete(); except Exception: common_logger.debug(f"Failed to delete callback message for user {user_id}.");
            await client.send_photo(chat_id=chat_id, photo=config.WELCOME_IMAGE_TELEGRAPH_LINK);
            await client.send_message(chat_id=chat_id, text=welcome_message_text, reply_markup=main_menu_keyboard, parse_mode=config.PARSE_MODE, disable_web_page_preview=True);
        except Exception as e: common_logger.error(f"Failed to send welcome message WITH photo to {chat_id}: {e}", exc_info=True); common_logger.warning("Falling back to text-only welcome message."); await edit_or_send_message(client, chat_id, target_message_id, welcome_message_text, main_menu_keyboard);

    else: await edit_or_send_message(client, chat_id, target_message_id, welcome_message_text, main_menu_keyboard);

    if is_callback: try: await update.answer(); except Exception: common_logger.warning(f"Failed to answer menu_home callback for user {user_id}.");


@Client.on_message(filters.command("help") & filters.private)
@Client.on_callback_query(filters.regex("^menu_help$"))
async def help_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    user_id = update.from_user.id; chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id; is_callback = isinstance(update, CallbackQuery); target_message_id = update.message.id if is_callback else None;
    user = await get_user(client, user_id); if user is None: common_logger.error(f"Failed to get user {user_id} for Help.", exc_info=True); # Continue without user
    help_message_text = strings.HELP_MESSAGE.format();
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]]);

    await edit_or_send_message(client, chat_id, target_message_id, help_message_text, reply_markup, disable_web_page_preview=True);

    if is_callback: try: await update.answer(); except Exception: common_logger.warning(f"Failed to answer menu_help callback for user {user_id}.");


@Client.on_message(filters.command("profile") & filters.private)
@Client.on_callback_query(filters.regex("^menu_profile$"))
async def profile_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    user_id = update.from_user.id; chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id; is_callback = isinstance(update, CallbackQuery); target_message_id = update.message.id if is_callback else None;
    user = await get_user(client, user_id);
    if user is None: common_logger.error(f"Failed to get user {user_id} for Profile.", exc_info=True); await edit_or_send_message(client, chat_id, target_message_id, strings.DB_ERROR); return;

    premium_status_str = "Free User";
    if user.premium_status != "free":
         plan_details = config.PREMIUM_PLANS.get(user.premium_status);
         if plan_details:
             premium_status_str = f"✨ {plan_details.get('name', user.premium_status.replace('_', ' ').title())} ✨";
             if user.premium_expires_at and user.premium_expires_at > datetime.now(timezone.utc):
                  expiry_date_str = user.premium_expires_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC');
                  premium_status_str += f" (Expires: {expiry_date_str})";
             elif user.premium_expires_at: premium_status_str += " (Expired)";
         else: premium_status_str = user.premium_status.replace('_', ' ').title();


    profile_text = strings.PROFILE_FORMAT.format(
        user_mention=get_user_mention(user),
        tokens=user.tokens, premium_status=premium_status_str, download_count=user.download_count,
        watchlist_count=len(user.watchlist)
    );

    reply_markup = InlineKeyboardMarkup([
        [ InlineKeyboardButton(strings.BUTTON_MANAGE_WATCHLIST, callback_data="profile_watchlist_menu"), ],
         [ InlineKeyboardButton(strings.BUTTON_NOTIFICATION_SETTINGS.format(status="View/Edit"), callback_data="profile_notification_settings_menu"), ],
         [ InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home"), ]
    ]);

    await edit_or_send_message(client, chat_id, target_message_id, profile_text, reply_markup, disable_web_page_preview=True);
    if is_callback: try: await update.answer(); except Exception: common_logger.warning(f"Failed to answer menu_profile callback for user {user_id}.");


# Generic callback handler for any callback that hasn't been matched. Placed at a low priority group (-1).
@Client.on_callback_query(group=-1)
async def generic_callback_handler(client: Client, callback_query: CallbackQuery):
     user_id = callback_query.from_user.id; data = callback_query.data; message = callback_query.message; chat_id = message.chat.id;
     user_state = await MongoDB.get_user_state(user_id);
     if user_state: common_logger.warning(f"User {user_id} in state {user_state.handler}:{user_state.step} clicked unhandled callback {data}.");
     else: common_logger.warning(f"User {user_id} clicked unhandled callback {data} (No active state).");

     try:
          await callback_query.answer("⚠️ Action not recognized or unavailable.", show_alert=False); # Toast
     except Exception as e: common_logger.error(f"Failed to answer callback {data} for {user_id}: {e}", exc_info=True);

# Generic handler for text input not caught by command filters. Group=1.
@Client.on_message(filters.text & filters.private & ~filters.command, group=1)
async def handle_plain_text_input(client: Client, message: Message):
    user_id = message.from_user.id; text = message.text.strip(); chat_id = message.chat.id;
    common_logger.debug(f"Received plain text from user {user_id}: '{text[:100]}...'");

    user = await get_user(client, user_id);
    if user is None: await message.reply_text(strings.DB_ERROR); common_logger.error(f"User {user_id} not found/fetch failed on plain text input."); return;

    if text.lower() == strings.CANCEL_ACTION.lower():
        user_state = await MongoDB.get_user_state(user_id);
        if user_state: common_logger.info(f"User {user_id} cancelled state {user_state.handler}:{user_state.step}."); await MongoDB.clear_user_state(user_id); await message.reply_text(strings.ACTION_CANCELLED);
        else: common_logger.debug(f"User {user_id} sent cancel but was not in a state."); await message.reply_text("✅ Nothing to cancel.");
        return;

    user_state = await MongoDB.get_user_state(user_id);

    if user_state:
        common_logger.info(f"User {user_id} in state {user_state.handler}:{user_state.step}. Routing text input.");
        try:
            if user_state.handler == "content_management": await content_handler.handle_content_input(client, message, user_state);
            elif user_state.handler == "request": await request_handler.handle_request_input(client, message, user_state, text);
            else: common_logger.error(f"User {user_id} in unrecognized state {user_state.handler}:{user_state.step} with text input."); await MongoDB.clear_user_state(user_id); await message.reply_text("🤷 Unexpected state. Your process was cancelled.");
        except Exception as e: common_logger.error(f"Error handling routed text input for {user_id} in state {user_state.handler}:{user_state.step}: {e}", exc_info=True); await MongoDB.clear_user_state(user_id); await message.reply_text(strings.ERROR_OCCURRED);

    else:
        common_logger.debug(f"User {user_id} has no state. Treating text as general query.");
        if len(text) >= 2: search_handler.handle_search_query_text(client, message, text, user); # search_handler takes over, potentially async tasks within it. No await here as handle_search... calls send/reply itself.
        else: common_logger.debug(f"Ignoring short text '{text}' from {user_id} with no state."); await message.reply_text("🤔 Not sure what that means. Use buttons or send a name to search! 👇", reply_markup=create_main_menu_keyboard());

# Handler for media (Photo, Document, Video) inputs. Group=1.
@Client.on_message((filters.photo | filters.document | filters.video) & filters.private, group=1)
async def handle_media_input(client: Client, message: Message):
    user_id = message.from_user.id; chat_id = message.chat.id;
    common_logger.debug(f"Received media input from user {user_id}.");
    user = await get_user(client, user_id); if user is None: await message.reply_text(strings.DB_ERROR); return;

    user_state = await MongoDB.get_user_state(user_id);
    if user_state and user_state.handler == "content_management":
         common_logger.info(f"Admin {user_id} in content_management state {user_state.step}. Routing media input.");
         try:
             if user_state.step == content_handler.ContentState.AWAITING_POSTER or user_state.step == content_handler.ContentState.EDITING_POSTER_PROMPT:
                  if message.photo: await content_handler.handle_awaiting_poster(client, message, user_state);
                  else: await message.reply_text("👆 Please send a **photo** for the poster.");
             elif user_state.step == content_handler.ContentState.UPLOADING_FILE:
                  if message.document or message.video: await content_handler.handle_episode_file_upload(client, message, user_state, message.document or message.video);
                  else: await message.reply_text("⬆️ Please upload the episode file (video or document).");
             else: common_logger.warning(f"Admin {user_id} sent media while in CM state {user_state.step} which doesn't expect media."); await message.reply_text("🤷 I'm not expecting a file right now.");
         except Exception as e: common_logger.error(f"Error handling media input for {user_id} in CM state {user_state.step}: {e}", exc_info=True); await MongoDB.clear_user_state(user_id); await message.reply_text(strings.ERROR_OCCURRED);

    else: common_logger.debug(f"Ignoring media from {user_id} with no expected state.");

# Catch-all for errors or unhandled messages. Group=-1.
@Client.on_message(filters.private, group=-1)
async def message_error_handler(client: Client, message: Message):
    content_info = f"Text: '{message.text[:100] + '...' if message.text and len(message.text) > 100 else message.text}'" if message.text else f"Media: {message.media}" if message.media else "Other Message Type";
    common_logger.warning(f"Generic message_error_handler caught unhandled msg from {message.from_user.id} in {message.chat.id}: {content_info}. Update type: {message.update_type}.");

    user_state = await MongoDB.get_user_state(message.from_user.id);
    if user_state: common_logger.error(f"Unhandled message while {message.from_user.id} in state {user_state.handler}:{user_state.step}.", exc_info=True); await MongoDB.clear_user_state(message.from_user.id); await message.reply_text("💔 Issue in current process. It was cancelled.");
    elif message.text and len(message.text) >= 3: # Short texts already filtered
         common_logger.debug("Unhandled text message, assumed fell through filters."); # Prompt might already be handled by handle_plain_text_input
