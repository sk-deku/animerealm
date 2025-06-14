# handlers/common_handlers.py
import logging
import traceback # For printing detailed error tracebacks
import sys
import asyncio # Needed for sleep in error handling/async operations
from datetime import datetime, timezone # For timezone aware datetimes
from typing import Union, Optional, List
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser # Import User type from pyrogram
from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant # Specific Pyrogram errors
from pyrogram.enums import ParseMode # Import ParseMode for local use if needed

# Import configuration constants
import config
# Also use ADMIN_IDS, OWNER_ID, FILE_STORAGE_CHANNEL_ID implicitly via logic or calls to other handlers
# Specific configs used here: START_TOKENS, WELCOME_IMAGE_TELEGRAPH_LINK, DEFAULT_NOTIFICATION_SETTINGS

# Import string constants for messages and button labels
import strings
from strings import (
    WELCOME_MESSAGE, HELP_MESSAGE, ABOUT_BOT_MESSAGE, ERROR_OCCURRED, DB_ERROR,
    BUTTON_SEARCH, BUTTON_BROWSE, BUTTON_PROFILE, BUTTON_EARN_TOKENS,
    BUTTON_PREMIUM, BUTTON_HELP, BUTTON_HOME, PROFILE_TITLE, PROFILE_FORMAT,
    BUTTON_MANAGE_WATCHLIST, BUTTON_NOTIFICATION_SETTINGS, CANCEL_ACTION, # Import CANCEL_ACTION string
    ACTION_CANCELLED,
    USER_NOT_FOUND_DB, BUTTON_LEADERBOARD, BUTTON_LATEST, BUTTON_POPULAR,
    FILE_SENT_SUCCESS # May use here as a generic confirmation
)

# Import database models and utilities
from database.mongo_db import MongoDB # Access the MongoDB class instance methods
# Import specific DB state management helper functions
from database.mongo_db import get_user_state, set_user_state, clear_user_state

# Import required Pydantic models
from database.models import User, UserState # User model for data handling, UserState for type hinting

# Import modules containing handler functions or routing targets
# Note: Importing modules here allows accessing functions within them for routing
from . import tokens_handler
from . import content_handler
from . import search_handler
from . import browse_handler
from . import download_handler # This file might handle file sending AFTER token/permission check
from . import request_handler
from . import watchlist_handler
from . import premium_handler
# Note: admin_handlers are command-based, don't route plain text/files to them
# Import specific constants/states from handlers that are needed for routing
from .content_handler import ContentState # Import ContentState for routing media/text


# Configure logger for common handlers
common_logger = logging.getLogger(__name__)

# --- Helper Functions ---

async def get_user(client: Client, user_id: int) -> Optional[User]:
    """Retrieves user data from DB, creates a new user if they don't exist."""
    # Use the robust get_user function from database.mongo_db? No, that would create a circular dependency.
    # The user creation logic IS part of the core bot identity/start process, so it belongs in common handlers.
    # common_logger.debug(f"Attempting to get or create user {user_id}") # Too verbose

    user_data = await MongoDB.users_collection().find_one({"user_id": user_id})

    if user_data:
        try:
            # Validate with Pydantic model
            # Ensure notification_settings is present with default structure if missing (migration logic)
            if "notification_settings" not in user_data or not isinstance(user_data["notification_settings"], dict):
                 user_data["notification_settings"] = config.DEFAULT_NOTIFICATION_SETTINGS.copy()

            user = User(**user_data)
            # common_logger.debug(f"Found user {user_id} in DB.")
            return user
        except Exception as e:
            # This might indicate schema evolution without migration or data corruption
            common_logger.error(f"Error validating user data from DB for user {user_id}: {e}", exc_info=True)
            # Returning None signifies that we couldn't get a valid user object.
            return None
    else:
        # User not found, create new user entry
        common_logger.info(f"User {user_id} not found in DB. Creating new user.")
        try:
            # Fetch basic user info from Telegram for first name/username
            telegram_user: TelegramUser = await client.get_users(user_id)
            first_name = telegram_user.first_name
            username = telegram_user.username


            new_user_dict = {
                "user_id": user_id,
                "first_name": first_name,
                "username": username,
                "tokens": config.START_TOKENS,
                "join_date": datetime.now(timezone.utc),
                "notification_settings": config.DEFAULT_NOTIFICATION_SETTINGS.copy() # Apply default settings from config
            }

            # Use the Pydantic model to validate data *before* insertion
            new_user = User(**new_user_dict)
            # Convert to dict for MongoDB insert, using alias for _id and excluding None fields
            new_user_doc_for_insert = new_user.dict(by_alias=True, exclude_none=True)


            insert_result = await MongoDB.users_collection().insert_one(new_user_doc_for_insert)
            common_logger.info(f"New user {user_id} inserted with DB ID {insert_result.inserted_id}")

            # Add the MongoDB-generated _id to the Pydantic model instance if it wasn't set yet
            new_user.id = new_user_dict.get('_id', insert_result.inserted_id) # Retrieve _id set by Mongo


            return new_user
        except Exception as e:
            # Handle potential database errors during insert (e.g., connection failure, schema issues)
            # pymongo might raise specific exceptions on insertion errors
            common_logger.error(f"Error inserting new user {user_id} into DB: {e}", exc_info=True)
            # In case of database errors, we cannot rely on user creation. Return None.
            return None


async def save_user(user: User):
    """Saves updated user data back to DB."""
    try:
        # Convert Pydantic model to dict, exclude 'user_id' as it's our filter,
        # use exclude_unset=True (if using Pydantic v1.8+) to only update changed fields.
        # exclude_none=True is still useful.
        update_data = user.dict(by_alias=True, exclude={"user_id"}, exclude_none=True) # exclude_unset=True needs check

        # $set operation updates fields in the database document.
        update_result = await MongoDB.users_collection().update_one(
            {"user_id": user.user_id}, # Filter for the user document using Telegram user ID
            {"$set": update_data}
        )
        if update_result.matched_count == 0:
            common_logger.warning(f"Save user failed for user {user.user_id}: document not found.")
            # Maybe user document was deleted? Handle this scenario if possible.
        # elif update_result.modified_count == 0:
            # common_logger.debug(f"Save user modified 0 documents for user {user.user_id}. Data was unchanged.")

    except Exception as e:
        common_logger.error(f"Error saving user data for user {user.user_id}: {e}", exc_info=True)
        # This error might require alerting admin or specific retry logic


# Helper function to create the main menu keyboard (kept for reuse)
def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Creates the main user menu inline keyboard."""
    buttons = [
        [
            InlineKeyboardButton(strings.BUTTON_SEARCH, callback_data="menu_search"),
            InlineKeyboardButton(strings.BUTTON_BROWSE, callback_data="menu_browse"),
        ],
        [
             InlineKeyboardButton(strings.BUTTON_PROFILE, callback_data="menu_profile"),
             InlineKeyboardButton(strings.BUTTON_EARN_TOKENS, callback_data="menu_earn_tokens"),
        ],
        [
             InlineKeyboardButton(strings.BUTTON_PREMIUM, callback_data="menu_premium"),
             InlineKeyboardButton(strings.BUTTON_HELP, callback_data="menu_help"),
        ],
        [
             InlineKeyboardButton(strings.BUTTON_LEADERBOARD, callback_data="menu_leaderboard"),
             InlineKeyboardButton(strings.BUTTON_LATEST, callback_data="menu_latest"),
             InlineKeyboardButton(strings.BUTTON_POPULAR, callback_data="menu_popular"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

# Helper function to format user mention for HTML
def get_user_mention(user: User) -> str:
    """Generates an HTML mention for a user, using first name."""
    # Escape HTML special characters in the first name
    escaped_first_name = user.first_name.replace("&", "&").replace("<", "<").replace(">", ">") if user.first_name else "User"
    return f'<a href="tg://user?id={user.user_id}">{escaped_first_name}</a>'


# Helper to safely edit or send a message
async def edit_or_send_message(client: Client, chat_id: int, message_id: Optional[int], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, disable_web_page_preview: bool = True):
    """Attempts to edit message_id if provided, otherwise sends a new message."""
    try:
        if message_id is not None:
            await client.edit_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=disable_web_page_preview
            )
        else:
            # Send as new message
            await client.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=disable_web_page_preview
            )
    except (MessageIdInvalid, MessageNotModified):
        # If the message ID is invalid (e.g., deleted) or the text/markup is unchanged,
        # send a new message instead of failing.
        common_logger.debug(f"Editing message {message_id} failed for chat {chat_id}. Sending as new.")
        await client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=config.PARSE_MODE,
            disable_web_page_preview=disable_web_page_preview
        )
    except FloodWait as e:
         common_logger.warning(f"FloodWait while sending/editing message for chat {chat_id}: {e.value}")
         await asyncio.sleep(e.value)
         # Retry the original operation or log that it needs manual check? Retry once:
         try:
              if message_id is not None:
                 await client.edit_text(chat_id, message_id, text, reply_markup, config.PARSE_MODE, disable_web_page_preview)
              else:
                  await client.send_message(chat_id, text, reply_markup, config.PARSE_MODE, disable_web_page_preview)
         except Exception as retry_e:
              common_logger.error(f"Retry after FloodWait failed for chat {chat_id}: {retry_e}", exc_info=True)
              # Give up after retry failure
    except Exception as e:
        # Log any other unexpected errors during message handling
        common_logger.error(f"Failed to send/edit message for chat {chat_id}: {e}", exc_info=True)
        # Maybe send a fallback error message if possible? This could loop.
        # Rely on the logging and potential admin alerts.


# --- Handler Functions ---

@Client.on_message(filters.command("start") & filters.private)
@Client.on_callback_query(filters.regex("^menu_home$"))
async def start_command_or_home_callback(client: Client, update: Union[Message, CallbackQuery]):
    """Handles /start command and 'Home' button callback, includes start={token} payload handling."""
    # Determine common information regardless of update type
    user_id = update.from_user.id
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    is_callback = isinstance(update, CallbackQuery)
    # Get message_id to potentially edit. For /start command, we won't edit it initially.
    message_id = update.id if isinstance(update, Message) else update.message.id

    # Get the start payload if it exists from a /start command message
    payload = None
    if isinstance(update, Message):
        payload = update.command[1] if len(update.command) > 1 else None
        # Optional: Delete the original /start message if it had no payload for cleaner chat.
        # If it had a payload, the message serves as context for the redemption result.
        # try:
        #     if payload is None: # Only delete /start command message itself if no payload
        #          await update.delete()
        # except Exception:
        #      common_logger.debug(f"Failed to delete /start command message for user {user_id}.")

    # --- Handle Token Redemption Payload (High Priority) ---
    # If a payload is present with the /start command, process it first.
    if payload:
        common_logger.info(f"User {user_id} received /start with payload: {payload}")
        # Delegate the redemption logic to the tokens handler
        # The handler will return a string key from strings.py indicating the result
        redemption_result_message_key = await tokens_handler.handle_token_redemption(client, user_id, payload)

        # Fetch the user again to get potentially updated token balance and user object
        user = await get_user(client, user_id) # get_user handles creation if needed
        if user is None:
             # If user data is unavailable even after get_user call, a DB error occurred.
             common_logger.error(f"Failed to retrieve or create user {user_id} after token payload attempt.", exc_info=True)
             await edit_or_send_message(client, chat_id, None, DB_ERROR, disable_web_page_preview=True) # Send error as new message
             # We can't even display the main menu reliably without user object. Exit this flow.
             return

        # Construct the appropriate message text based on the redemption result key
        redemption_message_text = ERROR_OCCURRED # Default fallback message
        try:
            # Use getattr to dynamically get the string message from strings module
            redemption_message_text = getattr(strings, redemption_result_message_key)
            # Format the success message with user's tokens if applicable
            if redemption_result_message_key == "TOKEN_REDEEMED_SUCCESS":
                 # User object contains the *updated* token count after redemption logic
                 redemption_message_text = redemption_message_text.format(
                     tokens_earned=config.TOKENS_PER_REDEEM, # Number of tokens credited per completion
                     user_tokens=user.tokens # Current total tokens
                 )
            elif redemption_result_message_key == "TOKEN_REDEEMED_OWN" or redemption_result_message_key == "TOKEN_ALREADY_REDEEMED" or redemption_result_message_key == "TOKEN_EXPIRED":
                 # Format other messages if they have placeholders (currently they don't)
                 pass # No formatting needed for these messages currently

        except AttributeError:
            common_logger.error(f"Invalid redemption result message key '{redemption_result_message_key}' returned by token handler.")
            redemption_message_text = ERROR_OCCURRED # Fallback if the key is wrong

        # Send the redemption result message. Reply to the original /start message if it had a payload.
        # If user clicked an old menu_home *button* with payload state issue? This part expects Message with payload.
        if isinstance(update, Message) and payload is not None:
             await update.reply_text(
                  redemption_message_text,
                  parse_mode=config.PARSE_MODE,
                  disable_web_page_preview=True
             )
        else:
             # Should not happen if logic is correct (payload only on /start Message), but as a safety
             common_logger.warning(f"Attempted to send redemption result outside of /start payload message for user {user_id}. Sending as new message.")
             await client.send_message(
                 chat_id=chat_id,
                 text=redemption_message_text,
                 parse_mode=config.PARSE_MODE,
                 disable_web_page_preview=True
             )


    # --- Display Standard Welcome Message and Main Menu ---
    # This happens on a regular /start without payload, OR after a payload has been processed.
    # Ensure user is available (it should be fetched/created above or during payload handling)
    user = await get_user(client, user_id)
    if user is None:
        common_logger.critical(f"FATAL: Cannot display main menu. User data unavailable for {user_id} even after retry.", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id if is_callback else None, DB_ERROR, disable_web_page_preview=True) # Try to edit or send error
        # The bot is likely in a bad state for this user.
        return


    # Clear any active user state when they return to the main menu.
    # Except if the state is specific to the main menu itself? (e.g., "main_menu:displayed").
    # Simpler: Clear any state except maybe a broad "in_main_flow" state if you used one.
    # For now, entering /start or menu_home clears any previous specific state.
    current_state = await get_user_state(user_id)
    if current_state:
        # Add specific exceptions if needed? Like 'search_active' state? No, clearing all on HOME is cleaner.
         await clear_user_state(user_id)
         common_logger.debug(f"Cleared state {current_state.handler}:{current_state.step} for user {user_id} on return to main menu.")


    # Get the welcome message text and build the main menu keyboard
    welcome_message_text = WELCOME_MESSAGE.format() # Format message, currently no placeholders

    # Construct the keyboard using the helper function
    main_menu_keyboard = create_main_menu_keyboard()


    # Decide whether to edit the existing message (for callback queries from main menu buttons)
    # or send a new message (for the initial /start command).
    target_message_id = message_id if is_callback else None # Edit only if it's a callback

    # Include welcome image if WELCOME_IMAGE_TELEGRAPH_LINK is configured.
    # Sending photo and caption with buttons can be tricky. Safest is send photo, then text+buttons.
    if config.WELCOME_IMAGE_TELEGRAPH_LINK:
        # Try sending the photo first
        try:
            # If it was a callback from the main menu, try to delete the message it was attached to for a cleaner photo send
            if is_callback:
                try: await update.message.delete()
                except Exception: common_logger.debug(f"Failed to delete callback message before sending photo for user {user_id}.")

            await client.send_photo(
                chat_id=chat_id,
                photo=config.WELCOME_IMAGE_TELEGRAPH_LINK # Use the Telegraph link here
                # caption=welcome_message_text, # Could add caption here if the photo send supports parse mode & reply markup well
                # reply_markup=main_menu_keyboard # Might work depending on Pyrogram version/method
            )
             # Then send the text message with the keyboard as a new message after the photo
            await client.send_message(
                chat_id=chat_id,
                text=welcome_message_text, # Send welcome text as main message body
                reply_markup=main_menu_keyboard,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=True
            )


        except Exception as e:
            common_logger.error(f"Failed to send welcome message WITH photo to {chat_id}: {e}", exc_info=True)
            # Fallback: send only text and keyboard if sending photo fails
            common_logger.warning("Falling back to text-only welcome message.")
            await edit_or_send_message(client, chat_id, target_message_id, welcome_message_text, main_menu_keyboard, disable_web_page_preview=True) # Use helper


    else: # No welcome image configured, just send text and keyboard
        await edit_or_send_message(client, chat_id, target_message_id, welcome_message_text, main_menu_keyboard, disable_web_page_preview=True)


    # If it was a callback, ensure it's answered to prevent the 'Loading...' state
    if is_callback:
        try: await update.answer() # Answer the callback query
        except Exception: common_logger.warning(f"Failed to answer menu_home callback query for user {user_id}.")


# Handler for the /help command or 'Help' button callback
@Client.on_message(filters.command("help") & filters.private)
@Client.on_callback_query(filters.regex("^menu_help$"))
async def help_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    """Handles /help command and 'Help' button callback."""
    user_id = update.from_user.id
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    is_callback = isinstance(update, CallbackQuery)
    target_message_id = update.message.id if is_callback else None # ID to edit for callbacks

    # Ensure user exists - Help should be available even if DB fetch is slow, but log issues
    user = await get_user(client, user_id) # User info for potential personalization? Not used currently in HELP.
    if user is None:
         common_logger.error(f"Failed to retrieve or create user {user_id} while processing Help command/callback.", exc_info=True)
         # Decide if Help can still be shown. Yes, help text is static. But maybe indicate potential issues?
         # Send error message AND help? For now, log error and proceed with help display.


    help_message_text = HELP_MESSAGE.format() # Format help message, no placeholders currently

    # Add a back button to the main menu
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home")]
    ])

    # Edit the message if it's a callback, otherwise reply
    await edit_or_send_message(
         client,
         chat_id,
         target_message_id, # Edit for callback, None for message
         help_message_text,
         reply_markup,
         disable_web_page_preview=True
     )

    # If it was a callback, answer it
    if is_callback:
        try: await update.answer() # Answer the callback query
        except Exception: common_logger.warning(f"Failed to answer menu_help callback query for user {user_id}.")


# Handler for the /profile command or 'My Profile' button callback
@Client.on_message(filters.command("profile") & filters.private)
@Client.on_callback_query(filters.regex("^menu_profile$"))
async def profile_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    """Handles /profile command and 'My Profile' button callback."""
    user_id = update.from_user.id
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    is_callback = isinstance(update, CallbackQuery)
    target_message_id = update.message.id if is_callback else None

    # Retrieve user data - Essential for profile
    user = await get_user(client, user_id)
    if user is None:
        # If user data unavailable, inform the user (DB Error) and return
        common_logger.error(f"Failed to retrieve or create user {user_id} while processing Profile command/callback.", exc_info=True)
        await edit_or_send_message(client, chat_id, target_message_id, DB_ERROR, disable_web_page_preview=True)
        if is_callback:
            try: await update.answer(DB_ERROR, show_alert=True)
            except Exception: pass # Ignore failure to answer
        return

    # Prepare profile details string
    # Format premium status more verbosely
    premium_status_str = "Free User"
    if user.premium_status != "free":
         # Look up plan details from config
         plan_details = config.PREMIUM_PLANS.get(user.premium_status)
         if plan_details:
             premium_status_str = f"✨ {plan_details.get('name', user.premium_status.replace('_', ' ').title())} ✨"
             # Add expiry date if available
             if user.premium_expires_at and user.premium_expires_at > datetime.now(timezone.utc):
                  # Format date - requires ensuring user.premium_expires_at is timezone aware
                  expiry_date_str = user.premium_expires_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                  premium_status_str += f" (Expires: {expiry_date_str})"
             elif user.premium_expires_at:
                 premium_status_str += " (Expired)"
         else:
             # Fallback if premium_status is not a recognized plan ID
             premium_status_str = user.premium_status.replace("_", " ").title() # Basic formatting if plan ID not in config

    # Format the profile text
    profile_text = PROFILE_FORMAT.format(
        user_mention=get_user_mention(user), # Use helper for clickable mention
        tokens=user.tokens,
        premium_status=premium_status_str,
        download_count=user.download_count,
        watchlist_count=len(user.watchlist),
        # Placeholders for buttons are handled in reply_markup
    )

    # Create keyboard for profile actions
    reply_markup = InlineKeyboardMarkup([
        [
            # Button to manage watchlist (callback will route to watchlist handler)
            InlineKeyboardButton(BUTTON_MANAGE_WATCHLIST, callback_data="profile_watchlist_menu"), # Define this callback later
        ],
         [
             # Button for notification settings (callback will route to watchlist handler or settings handler)
             # Show current status roughly on button
             # Check if ANY notification type is true
             notify_status == "✅ On" if any(user.notification_settings.values()) else "❌ Off"
             InlineKeyboardButton(
                 BUTTON_NOTIFICATION_SETTINGS.format(status=notify_status),
                 callback_data="profile_notification_settings_menu" # Define this callback later
             ),
         ],
         [
            # Back to main menu button
            InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home"),
         ]
    ])

    # Edit message for callback, send new message for command
    await edit_or_send_message(
         client,
         chat_id,
         target_message_id,
         profile_text,
         reply_markup,
         disable_web_page_preview=True # Disable previews for user mention link if HTML parsing adds it
     )

    # Answer callback if applicable
    if is_callback:
        try: await update.answer()
        except Exception: common_logger.warning(f"Failed to answer menu_profile callback for user {user_id}.")


# Generic message handler for plain text input
# Placed in common_handlers as it's the primary entry point for non-command text
@Client.on_message(filters.text & filters.private & ~filters.command, group=1)
async def handle_plain_text_input(client: Client, message: Message):
    """
    Handles plain text input from users. Routes input based on user's current state
    or treats it as a search query if no active state.
    """
    user_id = message.from_user.id
    text = message.text.strip()
    chat_id = message.chat.id

    common_logger.debug(f"Received plain text from user {user_id}: '{text[:100]}...'")

    # Retrieve user - essential for most operations including state and search cost/limits
    user = await get_user(client, user_id)
    if user is None:
         await message.reply_text(DB_ERROR, parse_mode=config.PARSE_MODE)
         common_logger.error(f"User {user_id} not found/fetch failed on plain text input.")
         return


    # --- Check for cancellation request (Universal Escape Hatch) ---
    if text.lower() == CANCEL_ACTION.lower():
        user_state = await get_user_state(user_id)
        if user_state:
            await clear_user_state(user_id)
            common_logger.info(f"User {user_id} cancelled state {user_state.handler}:{user_state.step}.")
            await message.reply_text(ACTION_CANCELLED, parse_mode=config.PARSE_MODE)
            # Consider re-displaying the relevant menu the user was trying to leave?
            # For simplicity now, just confirm cancellation.
        else:
             common_logger.debug(f"User {user_id} sent cancel text but was not in a state.")
             await message.reply_text("✅ Nothing to cancel.", parse_mode=config.PARSE_MODE)
        return # Stop processing after handling cancel


    # --- Retrieve User State to Determine Context ---
    user_state = await get_user_state(user_id)

    # --- Route Input Based on User State ---
    if user_state:
        # User is in a multi-step process managed by a specific handler
        common_logger.info(f"User {user_id} in state {user_state.handler}:{user_state.step}. Routing text input to {user_state.handler}.")
        try:
            if user_state.handler == "content_management":
                # Route text input to the admin content management handler function
                await content_handler.handle_content_input(client, message, user_state)

            elif user_state.handler == "request":
                 # Route text input to the user request handler function (expects anime name)
                 await request_handler.handle_request_input(client, message, user_state, text)

            # Add more elif blocks here for other handlers that expect text input when in a state
            # elif user_state.handler == "user_settings":
            #    await user_settings_handler.handle_settings_input(client, message, user_state, text)


            else:
                # State exists, but the handler doesn't exist or is not configured to handle text input for this step.
                # This indicates a logic error in state transitions or an outdated state document.
                common_logger.error(f"User {user_id} in state {user_state.handler}:{user_state.step} sent text input, but routing not implemented or state is bad. Clearing state.", exc_info=True)
                await clear_user_state(user_id) # Clear state to prevent user from getting stuck
                await message.reply_text("🤷 Unexpected state. Your previous process was cancelled.", parse_mode=config.PARSE_MODE)


        except Exception as e:
            common_logger.error(f"Error handling routed text input for user {user_id} in state {user_state.handler}:{user_state.step}: {e}", exc_info=True)
            # On unexpected errors during state handling, clear the state and inform user.
            await clear_user_state(user_id)
            await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


    else:
        # --- No Active State - Treat Text Input as a General Query ---
        # Primary action for non-state text input is anime search.
        common_logger.debug(f"User {user_id} has no active state. Treating text as a general query.")
        # Validate if the text looks like a potential search query (e.g., minimum length).
        # Prevent very short inputs triggering search too often.
        if len(text) >= 2: # Require at least 2 characters for a search
             # Route the message to the search handler for text-based search
             await search_handler.handle_search_query_text(client, message, text, user) # Pass user for premium checks in search


        else:
            # Input is too short to be a command, a likely search, or fits any known state.
            common_logger.debug(f"Ignoring short text input '{text}' from user {user_id} with no state.")
            # Optional: Provide a friendly message guiding the user.
            await message.reply_text(
                 "🤔 Hmm, not sure what to do with that input. Use the buttons below to explore AnimeRealm or send a name to search!\n",
                 reply_markup=create_main_menu_keyboard(), # Re-display main menu
                 parse_mode=config.PARSE_MODE,
                 disable_web_page_preview=True
             )


# Handler for media (Photo, Document, Video) inputs that were NOT expected by a specific state handler directly.
# Placed in common_handlers as the initial entry point for all file types.
@Client.on_message((filters.photo | filters.document | filters.video) & filters.private, group=1)
async def handle_media_input(client: Client, message: Message):
    """
    Handles incoming photo, document, or video messages.
    Routes media input based on user's current state, primarily for Admin Content Management uploads.
    Ignores media otherwise.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    common_logger.debug(f"Received media input from user {user_id}: photo={bool(message.photo)}, document={bool(message.document)}, video={bool(message.video)}")

    # User object might be needed for permission checks or logging later
    user = await get_user(client, user_id)
    if user is None:
         await message.reply_text(DB_ERROR, parse_mode=config.PARSE_MODE)
         common_logger.error(f"User {user_id} not found/fetch failed on media input.")
         return


    # Retrieve user state to determine if media input is expected
    user_state = await get_user_state(user_id)

    # Check if the user is currently in a content management state that specifically awaits a file type
    # Currently, only Admin Content Management expects media files.
    if user_state and user_state.handler == "content_management":
         common_logger.info(f"Admin {user_id} in content_management state {user_state.step}. Checking for expected media input.")

         try:
             if user_state.step == ContentState.AWAITING_POSTER:
                 # Expecting a PHOTO for a poster image
                 if message.photo:
                      # Route the message and state to the content handler's specific function
                      await content_handler.handle_awaiting_poster(client, message, user_state)
                 else:
                      # Received non-photo media when expecting a photo poster
                      await message.reply_text("👆 Please send a **photo** to use as the anime poster, or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
                      # State remains AWAITING_POSTER, admin needs to send a photo

             elif user_state.step == ContentState.UPLOADING_FILE:
                  # Expecting a DOCUMENT or VIDEO for an episode file
                  if message.document or message.video: # Check if message contains a document or video
                       # Route the message and state to the content handler's function for file upload
                       await content_handler.handle_episode_file_upload(client, message, user_state)
                  else:
                       # Received a photo or other media when expecting episode file
                       await message.reply_text("⬆️ Please upload the episode file (video or document), or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
                       # State remains UPLOADING_FILE, admin needs to send doc/video

             else:
                 # Admin is in a content management state, but this step does not expect media input.
                 common_logger.warning(f"Admin {user_id} sent media input ({message.media}) while in content management state {user_state.step}, which does not expect media input at this point.")
                 await message.reply_text("🤷 I'm not expecting a file or photo right now based on your current action. Please continue with the current step or type '❌ Cancel'.", parse_mode=config.PARSE_MODE)
                 # State remains the same. User needs to cancel or provide correct input for the state.

         except Exception as e:
            # Log any unexpected errors during the specific file handler function call
            common_logger.error(f"Error handling media input for user {user_id} in content management state {user_state.step}: {e}", exc_info=True)
            # Clear state and inform admin about the error to prevent them getting stuck
            await clear_user_state(user_id)
            await message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


    else:
        # User is not in any recognized state that expects media input. Ignore the file/photo.
        common_logger.debug(f"Ignoring media input from user {user_id} with no active state expecting media.")
        # Optional: Provide a subtle message indicating the media wasn't processed
        # await message.reply_text("Ignoring the file/photo. Please use a command!", parse_mode=config.PARSE_MODE)
        pass # Just silently ignore media if no state expects it

# --- Generic Error Handler for Messages ---
# Catches errors in handlers (if they don't handle their own exceptions) or unhandled message types
# Ensure this runs last by setting a low group ID.
# Acknowledges messages gracefully.
@Client.on_message(filters.private & ~filters.chat(config.ADMIN_IDS), group=-1) # Only reply to non-admin errors here? Or handle for all?
# Let's make it general for private chats for any unhandled message error.
# filters.private is enough, group -1 means lowest priority.
@Client.on_message(filters.private, group=-1)
async def message_error_handler(client: Client, message: Message):
    """
    Catch-all for errors or unhandled messages in private chats.
    Provides a generic fallback message if no specific handler processed the message
    or if an exception wasn't caught locally in a handler.
    Note: This can trigger for *any* private message that wasn't handled elsewhere.
    """
    # Log the details of the unhandled message
    # Avoid logging sensitive data if possible. Log user ID, chat type, message ID, brief content info.
    content_info = f"Text: '{message.text[:100] + '...' if message.text and len(message.text) > 100 else message.text}'" if message.text else f"Media: {message.media}" if message.media else "Other Message Type"
    common_logger.warning(f"Generic message_error_handler caught unhandled message from user {message.from_user.id} in chat {message.chat.id} (ID: {message.id}): {content_info}. Update type: {message.update_type}.")


    # Retrieve user state as this might be related to an input state issue
    user_state = await get_user_state(message.from_user.id)

    # Only reply if it seems like the user was trying to interact and fell through.
    # Avoid replying to every bot status update or forwarded message not relevant.
    # Check if the message type suggests user interaction (text, potentially photo/doc if they sent it outside a state).
    if message.text or message.photo or message.document or message.video:

        # If they are in a state, and it fell through, it's a handler/state routing issue.
        if user_state:
             common_logger.error(f"Unhandled message received while user {message.from_user.id} in state {user_state.handler}:{user_state.step}.", exc_info=True)
             # It might be best to clear the state on such a generic fallback after attempting handlers in group 1.
             await clear_user_state(message.from_user.id) # Clear potentially bad state
             await message.reply_text("💔 An unexpected issue occurred in your current process. It has been cancelled. Please try again from the beginning.", parse_mode=config.PARSE_MODE)

        else:
             # Not in a state, just an unhandled text or file input.
             # If text and handle_plain_text_input didn't route it (e.g., too short, error),
             # or if media and handle_media_input didn't route it.
             # Provide a general hint for interaction.
             # Check if it's a very common ignored pattern before generic reply (e.g. "hi", "hello" could be ignored)
             # Simple check: if the message is short and not a command, avoid triggering.
             if message.text and len(message.text) < 3 and not message.text.startswith('/'):
                  common_logger.debug("Ignoring short non-command text in message_error_handler.")
                  pass # Ignore very short texts falling through

             elif message.text and len(message.text) >= 3: # Assume length indicates potential query
                 # It's text > 2 chars, should have been caught by handle_plain_text_input unless error.
                 # Could re-attempt search logic here? No, just give generic error/prompt.
                 await message.reply_text("🤔 Not sure what to do with that input. Use the buttons below to explore AnimeRealm or send a name to search!", reply_markup=create_main_menu_keyboard(), parse_mode=config.PARSE_MODE)

             # For media, just log that it wasn't handled. A generic reply isn't great for media.
             elif message.media:
                 common_logger.debug(f"Unhandled media in message_error_handler.")
                 pass # Ignore generic media in fallback


    # Any other message type (service message, sticker, poll, etc.) or admin commands falling through, just log.
    # We don't typically need to reply to service messages.
    pass # No reply for other cases

# Generic callback handler (generic_callback_handler) above group=-1 already serves as catch-all for errors too.
