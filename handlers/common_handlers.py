# handlers/common_handlers.py
import logging
import traceback
import sys
from datetime import datetime, timezone
from typing import Union
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified

from config import (
    PARSE_MODE, WELCOME_IMAGE_TELEGRAPH_LINK, MAIN_MENU_BUTTONS,
    START_TOKENS, CALLBACK_DATA_SEPARATOR, ADMIN_IDS,
    REQUEST_TOKEN_COST # For checking free user ability to request via profile
)
from strings import (
    WELCOME_MESSAGE, HELP_MESSAGE, ABOUT_BOT_MESSAGE, ERROR_OCCURRED,
    BUTTON_SEARCH, BUTTON_BROWSE, BUTTON_PROFILE, BUTTON_EARN_TOKENS,
    BUTTON_PREMIUM, BUTTON_HELP, BUTTON_HOME, PROFILE_TITLE, PROFILE_FORMAT,
    BUTTON_MANAGE_WATCHLIST, BUTTON_REQ_UNAVAILABLE, BUTTON_REQ_ALREADY_ADDED,
    BUTTON_REQ_NOT_RELEASED, BUTTON_REQ_WILL_ADD_SOON, BUTTON_BACK, CANCEL_ACTION # Import cancel text
)
from database.mongo_db import MongoDB
from database.models import User # Import the User model

db_logger = logging.getLogger("MongoDB") # Get the MongoDB logger instance

# --- Helper Functions for Handlers ---

async def get_user(client: Client, user_id: int) -> Optional[User]:
    """Retrieves user data from DB, creates a new user if they don't exist."""
    user_data = await MongoDB.users_collection().find_one({"user_id": user_id})
    if user_data:
        try:
            # Validate with Pydantic model
            user = User(**user_data)
            return user
        except Exception as e:
            db_logger.error(f"Error validating user data from DB for user {user_id}: {e}")
            # Log or handle corrupted user data gracefully
            return None # Indicate data issue
    else:
        # Create new user
        db_logger.info(f"User {user_id} not found in DB. Creating new user.")
        new_user = User(
            user_id=user_id,
            first_name=(await client.get_users(user_id)).first_name, # Fetch user info
            username=(await client.get_users(user_id)).username, # Fetch username
            tokens=START_TOKENS,
            join_date=datetime.now(timezone.utc) # Use timezone aware datetime
             # Add notification settings with defaults from config here when implementing config more fully
            # For now, minimal fields based on model
        )
        try:
            insert_result = await MongoDB.users_collection().insert_one(new_user.dict(by_alias=True, exclude_none=True))
            db_logger.info(f"New user {user_id} inserted with ID {insert_result.inserted_id}")
            return new_user
        except Exception as e:
            db_logger.error(f"Error inserting new user {user_id} into DB: {e}")
            # Handle potential duplicate key errors or other DB issues during insert
            return None # Indicate creation failure

async def save_user(user: User):
    """Saves updated user data back to DB."""
    try:
        # Use user_id for filtering as it's guaranteed unique by Telegram and indexed in DB
        await MongoDB.users_collection().update_one(
            {"user_id": user.user_id},
            {"$set": user.dict(by_alias=True, exclude_unset=True, exclude={"user_id"})}
             # exclude_unset=True means only update fields that have been explicitly set/changed
             # exclude={"user_id"} prevents updating the user_id itself
        )
    except Exception as e:
        db_logger.error(f"Error saving user data for user {user.user_id}: {e}")
        # Implement retry logic or admin notification for persistent save failures


def create_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Creates the main menu inline keyboard."""
    buttons = [
        [
            InlineKeyboardButton(BUTTON_SEARCH, callback_data="menu_search"),
            InlineKeyboardButton(BUTTON_BROWSE, callback_data="menu_browse"),
        ],
        [
             InlineKeyboardButton(BUTTON_PROFILE, callback_data="menu_profile"),
             InlineKeyboardButton(BUTTON_EARN_TOKENS, callback_data="menu_earn_tokens"),
        ],
        [
             InlineKeyboardButton(BUTTON_PREMIUM, callback_data="menu_premium"),
             InlineKeyboardButton(BUTTON_HELP, callback_data="menu_help"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

# Helper function to get an embeddable user mention
def get_user_mention(user: User) -> str:
    """Generates an HTML mention for a user."""
    # Escape characters in the user's first name for HTML parse mode
    escaped_first_name = user.first_name.replace("&", "&").replace("<", "<").replace(">", ">")
    return f'<a href="tg://user?id={user.user_id}">{escaped_first_name}</a>'


# --- Handler Functions ---

@Client.on_message(filters.command("start"))
@Client.on_callback_query(filters.regex("^menu_home$"))
async def start_command_or_home_callback(client: Client, update: Union[Message, CallbackQuery]):
    """Handles /start command and 'Home' button callback."""
    # Determine the user ID and chat ID based on whether it's a message or callback
    if isinstance(update, Message):
        user_id = update.from_user.id
        chat_id = update.chat.id
        is_callback = False
    else: # It's a CallbackQuery
        user_id = update.from_user.id
        chat_id = update.message.chat.id
        is_callback = True
        # For callbacks, extract token if present (handled by tokens_handler)
        # The actual token redemption logic is in tokens_handler.py

    # Ensure the user exists in the database, create if new
    user = await get_user(client, user_id)
    if user is None:
         # Failed to get or create user. Logged inside get_user.
         # Inform the user gracefully if possible
         if is_callback:
              await update.answer("Sorry, failed to fetch your profile data.", show_alert=True)
              await update.message.edit_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
         else:
               await update.reply_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
         return


    welcome_message_text = WELCOME_MESSAGE.format() # Format message with any placeholders if needed

    # Include welcome image if configured
    if WELCOME_IMAGE_TELEGRAPH_LINK:
        # Sending with a photo requires the message to be separate
        # We can't combine caption with reply_markup on the photo directly in pyrogram's send_photo
        # Or send the photo first, then send the message/keyboard after.
        # For now, let's send text+keyboard. Sending photo first:
        try:
            # Delete the callback message first if it's a callback from the main menu
            if is_callback:
                try:
                    await update.message.delete()
                except (MessageIdInvalid, MessageNotModified): # Message might be old or already deleted
                    pass # Ignore if delete fails

            # Send the photo. Pyrogram might caption with Welcome message based on Photo methods
            # Using a simpler approach: send photo, then send text+keyboard message
            await client.send_photo(chat_id, WELCOME_IMAGE_TELEGRAPH_LINK)
            # Then send the text and keyboard
            sent_message = await client.send_message(
                 chat_id=chat_id,
                 text=welcome_message_text,
                 reply_markup=create_main_menu_keyboard(),
                 parse_mode=PARSE_MODE,
                 disable_web_page_preview=True # Often good to disable previews for links
             )


        except Exception as e:
            logging.error(f"Failed to send welcome message with photo to {chat_id}: {e}")
            # Fallback to sending text-only message with keyboard
            try:
                 # Ensure old callback message is edited/deleted first if possible
                 if is_callback:
                      try:
                            await update.message.edit_text(
                                 welcome_message_text,
                                 reply_markup=create_main_menu_keyboard(),
                                 parse_mode=PARSE_MODE,
                                 disable_web_page_preview=True
                             )
                      except (MessageIdInvalid, MessageNotModified):
                           # Fallback to sending new message if edit fails
                           await client.send_message(
                                chat_id=chat_id,
                                text=welcome_message_text,
                                reply_markup=create_main_menu_keyboard(),
                                parse_mode=PARSE_MODE,
                                disable_web_page_preview=True
                            )

                 else: # Initial /start message
                     await update.reply_text(
                          welcome_message_text,
                          reply_markup=create_main_menu_keyboard(),
                          parse_mode=PARSE_MODE,
                          disable_web_page_preview=True
                     )

            except Exception as fallback_e:
                 logging.error(f"Failed to send welcome message (fallback text-only) to {chat_id}: {fallback_e}")
                 # Last resort, inform the user something is wrong
                 if is_callback:
                     await update.answer("Failed to load the main menu.", show_alert=True)
                     await update.message.edit_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
                 else:
                     await update.reply_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)


    else: # No welcome image configured, just send text and keyboard
        try:
             # If it's a callback from the main menu buttons, edit the previous message
             if is_callback:
                 await update.message.edit_text(
                     welcome_message_text,
                     reply_markup=create_main_menu_keyboard(),
                     parse_mode=PARSE_MODE,
                     disable_web_page_preview=True
                 )
             else: # Initial /start command
                 await update.reply_text(
                     welcome_message_text,
                     reply_markup=create_main_menu_keyboard(),
                     parse_mode=PARSE_MODE,
                     disable_web_page_preview=True
                 )
        except (MessageIdInvalid, MessageNotModified):
             # Message might be too old to edit, send as a new message
             await client.send_message(
                  chat_id=chat_id,
                  text=welcome_message_text,
                  reply_markup=create_main_menu_keyboard(),
                  parse_mode=PARSE_MODE,
                  disable_web_page_preview=True
             )
        except Exception as e:
            logging.error(f"Failed to send text-only welcome message to {chat_id}: {e}")
            if is_callback:
                 await update.answer("Failed to load the main menu.", show_alert=True)
                 await update.message.edit_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
            else:
                 await update.reply_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)


# Handler for the /help command or 'Help' button callback
@Client.on_message(filters.command("help") & filters.private)
@Client.on_callback_query(filters.regex("^menu_help$"))
async def help_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    """Handles /help command and 'Help' button callback."""
    chat_id, message_id = (update.chat.id, update.id) if isinstance(update, Message) else (update.message.chat.id, update.message.id)
    is_callback = isinstance(update, CallbackQuery)

    help_message_text = HELP_MESSAGE.format() # Format message

    # Add a back button to the main menu
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home")]
    ])

    try:
        if is_callback:
            await update.message.edit_text(
                 help_message_text,
                 reply_markup=reply_markup,
                 parse_mode=PARSE_MODE,
                 disable_web_page_preview=True
             )
            await update.answer() # Acknowledge the callback
        else:
             await update.reply_text(
                  help_message_text,
                  reply_markup=reply_markup,
                  parse_mode=PARSE_MODE,
                  disable_web_page_preview=True
              )
    except (MessageIdInvalid, MessageNotModified):
        # If message is too old to edit, send as a new message
        await client.send_message(
            chat_id=chat_id,
            text=help_message_text,
            reply_markup=reply_markup,
            parse_mode=PARSE_MODE,
            disable_web_page_preview=True
        )
        if is_callback:
            await update.answer("Cannot edit message. Sending help as a new message.", show_alert=False)
    except Exception as e:
        logging.error(f"Failed to send help message to {chat_id}: {e}")
        if is_callback:
            await update.answer(ERROR_OCCURRED, show_alert=True)
            await update.message.edit_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
        else:
             await update.reply_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)


# Handler for the /profile command or 'My Profile' button callback
@Client.on_message(filters.command("profile") & filters.private)
@Client.on_callback_query(filters.regex("^menu_profile$"))
async def profile_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    """Handles /profile command and 'My Profile' button callback."""
    chat_id, message_id = (update.chat.id, update.id) if isinstance(update, Message) else (update.message.chat.id, update.message.id)
    user_id = update.from_user.id
    is_callback = isinstance(update, CallbackQuery)

    user = await get_user(client, user_id)
    if user is None:
        # Error retrieving or creating user - handled in get_user
        if is_callback:
              await update.answer("Sorry, failed to load your profile.", show_alert=True)
              await update.message.edit_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
        else:
              await update.reply_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
        return

    # Prepare profile details string
    profile_text = PROFILE_FORMAT.format(
        user_name=get_user_mention(user),
        tokens=user.tokens,
        premium_status=user.premium_status.replace("_", " ").title(), # Format premium status
        download_count=user.download_count,
        watchlist_count=len(user.watchlist),
        manage_watchlist_button="" # Placeholder - Add button to keyboard instead
    )

    # Create keyboard for profile actions
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(BUTTON_MANAGE_WATCHLIST, callback_data="profile_watchlist"),
        ],
         [
            # Maybe add more profile options later? e.g., "Notification Settings"
         ],
         [
            InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home"),
         ]
    ])

    try:
        if is_callback:
            await update.message.edit_text(
                 profile_text,
                 reply_markup=reply_markup,
                 parse_mode=PARSE_MODE,
                 disable_web_page_preview=True
            )
            await update.answer() # Acknowledge callback
        else:
             await update.reply_text(
                 profile_text,
                 reply_markup=reply_markup,
                 parse_mode=PARSE_MODE,
                 disable_web_page_preview=True
             )
    except (MessageIdInvalid, MessageNotModified):
        # If message is too old to edit, send as a new message
         await client.send_message(
            chat_id=chat_id,
            text=profile_text,
            reply_markup=reply_markup,
            parse_mode=PARSE_MODE,
            disable_web_page_preview=True
         )
         if is_callback:
             await update.answer("Cannot edit message. Sending profile as a new message.", show_alert=False)

    except Exception as e:
         logging.error(f"Failed to send profile message to {chat_id}: {e}")
         if is_callback:
            await update.answer(ERROR_OCCURRED, show_alert=True)
            await update.message.edit_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
         else:
            await update.reply_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)

# Generic callback handler for unsupported or basic 'answer' callbacks
# This helps acknowledge button presses that don't have a dedicated handler yet
@Client.on_callback_query(filters.regex("^menu_|^profile_") & ~filters.regex("^menu_home$|^menu_help$|^menu_profile$|^menu_earn_tokens$|^menu_premium$|^menu_search$|^menu_browse$|^profile_watchlist$")) # Exclude handlers that have dedicated functions
async def basic_callback_answer(client: Client, callback_query: CallbackQuery):
     """Acknowledges button presses that aren't fully handled yet."""
     # This will prevent the "Loading..." indicator hanging for the user
     logging.info(f"Acknowledging callback query: {callback_query.data} from user {callback_query.from_user.id}")
     await callback_query.answer("Feature not fully implemented yet!", show_alert=False) # Show a toast notification

# Error handler for messages
@Client.on_message(filters.private, group=-1) # Process errors after other handlers, group=-1 ensures lowest priority
async def message_error_handler(client: Client, message: Message):
    """Catches unhandled messages or errors in message processing."""
    # If a message falls through all filters/handlers, it lands here.
    # This could mean the user sent plain text that wasn't a command or search query
    # or that an unexpected error occurred during processing.

    # Simple reply for now if it's not a specific command/query that got caught earlier.
    # You could prompt user to use commands or search.

    # If the user just sent random text after the welcome message
    # And it wasn't meant as a search query (handled by search handler),
    # maybe guide them back to using buttons/commands.

    # This generic handler might need refinement depending on how free-form text is used.
    # For now, it's more for catching unhandled errors *during* command/query processing
    # or for general logging.
    pass # Placeholder for now. Actual unhandled text processing should be in specific handlers


# Error handler for callback queries
@Client.on_callback_query(group=-1) # Process errors after other handlers
async def callback_error_handler(client: Client, callback_query: CallbackQuery):
    """Catches errors during callback query processing."""
    logging.error(f"Error processing callback query from user {callback_query.from_user.id}: {callback_query.data}")
    traceback.print_exc() # Print the full traceback for debugging

    try:
        await callback_query.answer(ERROR_OCCURRED, show_alert=True)
        # Optional: Edit the message to show the error text, but be careful not to lose original content if possible
        # await callback_query.message.edit_text(ERROR_OCCURRED, parse_mode=PARSE_MODE)
    except FloodWait as e:
        logging.warning(f"FloodWait while answering callback: {e.value}")
        await asyncio.sleep(e.value)
        # Retry answering, or just let it fail silently after timeout
    except MessageNotModified:
        # Attempted to edit the message with the exact same text/reply_markup
        pass # This is not an error, just ignored
    except Exception as e:
        logging.error(f"Failed to answer callback query or edit message after error: {e}")
        # If even answering fails, there's not much more we can do programmatically


# Add an error handler for general unhandled exceptions in event loop? Pyrogram might handle some of this.
# If you notice the bot crashing unexpectedly without hitting these handlers, you might need a broader catch.
