# handlers/tokens_handler.py
import logging
import asyncio
import uuid # To generate unique tokens
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import aiohttp # Using aiohttp for async HTTP requests to the shortener API
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import config
from strings import (
    GEN_TOKEN_TITLE, GEN_TOKEN_INSTRUCTIONS,
    BUTTON_GO_TO_TOKEN_LINK, BUTTON_HOW_TO_EARN_TOKENS,
    EARN_TOKENS_TUTORIAL_MESSAGE_TEXT, EARN_TOKENS_TUTORIAL_MESSAGE_LINK_INTRO,
    TOKEN_REDEEMED_SUCCESS, TOKEN_REDEEMED_OWN,
    TOKEN_ALREADY_REDEEMED, TOKEN_EXPIRED, TOKEN_INVALID,
    ERROR_OCCURRED, ACTION_CANCELLED
)
from database.mongo_db import MongoDB
from database.models import User, GeneratedToken
from handlers.common_handlers import get_user, save_user # Import necessary user helpers

# Configure logger for tokens handlers
tokens_logger = logging.getLogger(__name__)

# --- Helper Functions ---

async def shorten_url(long_url: str) -> Optional[str]:
    """
    Uses an external URL shortener API to shorten a given URL.
    Requires config.SHORTENER_API_URL, config.SHORTENER_API_KEY, config.SHORTENER_ENDPOINT.
    Returns the shortened URL string or None on failure.
    """
    if not config.SHORTENER_API_URL or not config.SHORTENER_API_KEY or not config.SHORTENER_ENDPOINT:
        tokens_logger.warning("URL Shortener API configuration is missing. Cannot shorten link.")
        return None # Configuration missing

    try:
        api_endpoint = config.SHORTENER_ENDPOINT.format(
            shortener_api_url=config.SHORTENER_API_URL,
            api_key=config.SHORTENER_API_KEY,
            long_url=long_url # Long URL should often be URL-encoded if not done by the library/API
        )
        # Use aiohttp for asynchronous request
        async with aiohttp.ClientSession() as session:
            async with session.get(api_endpoint) as response:
                if response.status == 200:
                    result = await response.json() # Or response.text() if API returns plain text
                    # --- Update This Parsing Logic for Your API ---
                    shortened_url = result.get("shortenedUrl") # Assuming JSON key 'shortenedUrl'
                    if shortened_url:
                        tokens_logger.info(f"Successfully shortened URL: {long_url} -> {shortened_url}")
                        return shortened_url
                    else:
                        tokens_logger.error(f"Shortener API returned success but no shortened URL in response: {result}")
                        return None
                else:
                    response_text = await response.text()
                    tokens_logger.error(f"Shortener API failed for URL {long_url}. Status: {response.status}, Response: {response_text}")
                    return None
    except Exception as e:
        tokens_logger.error(f"An error occurred during URL shortening API call: {e}")
        return None


# --- Handler Functions ---

@Client.on_message(filters.command("gen_token") & filters.private)
@Client.on_callback_query(filters.regex("^menu_earn_tokens$"))
async def generate_token_link_handler(client: Client, update: Union[Message, CallbackQuery]):
    """Handles the /gen_token command and 'Earn Tokens' button callback."""
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    user_id = update.from_user.id
    is_callback = isinstance(update, CallbackQuery)

    user = await get_user(client, user_id)
    if user is None:
         if is_callback: await update.answer(ERROR_OCCURRED, show_alert=True)
         else: await update.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         return # Cannot proceed without user data

    # Generate a unique token
    unique_token = str(uuid.uuid4()) # Using UUID as a unique token string

    # Construct the Telegram start link that the shortener will redirect to
    long_telegram_link = config.REDEEM_LINK_PATTERN_TELEGRAM.format(
        bot_username=client.me.username, # Get bot's username
        token=unique_token
    )

    # Attempt to shorten the link
    shortened_url = await shorten_url(long_telegram_link)

    if shortened_url is None:
        # If shortening failed (API config missing or error), maybe inform admin and user
        # For now, fail gracefully and inform user.
        error_msg = "💔 Sorry, unable to generate the token link right now. The shortening service is not available."
        tokens_logger.error(f"Failed to generate token link for user {user_id} - Shortener failed.")
        if is_callback: await update.answer(error_msg, show_alert=True)
        else: await update.reply_text(error_msg, parse_mode=config.PARSE_MODE)
        return

    # Calculate token expiry time
    expiry_datetime = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_LINK_EXPIRY_HOURS)

    # Save the generated token in the database
    try:
        new_generated_token = GeneratedToken(
            token_string=unique_token,
            generated_by_user_id=user_id,
            expires_at=expiry_datetime,
            created_at=datetime.now(timezone.utc)
        )
        await MongoDB.generated_tokens_collection().insert_one(new_generated_token.dict(by_alias=True, exclude_none=True))
        tokens_logger.info(f"Generated and saved token {unique_token} for user {user_id}, expires at {expiry_datetime}")
    except Exception as e:
        tokens_logger.error(f"Failed to save generated token {unique_token} for user {user_id}: {e}")
        # If DB save fails, maybe the link shouldn't be given to the user?
        error_msg = "💔 Failed to save token details in the database. Please try again later."
        if is_callback: await update.answer(error_msg, show_alert=True)
        else: await update.reply_text(error_msg, parse_mode=config.PARSE_MODE)
        return # Do not proceed if saving token failed

    # Create inline keyboard with the shortened link button and tutorial button
    keyboard_buttons = [
        [InlineKeyboardButton(BUTTON_GO_TO_TOKEN_LINK, url=shortened_url)],
        [InlineKeyboardButton(BUTTON_HOW_TO_EARN_TOKENS, callback_data="tokens_tutorial")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    # Format the instructional message
    instruction_message = GEN_TOKEN_INSTRUCTIONS.format(expiry_hours=config.TOKEN_LINK_EXPIRY_HOURS)


    # Send or edit the message with the generated link and buttons
    try:
        if is_callback:
            # Edit the existing message (usually the main menu)
            await update.message.edit_text(
                f"**{GEN_TOKEN_TITLE}**\n\n{instruction_message}", # Combine title and instructions
                reply_markup=reply_markup,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=True # Important for links
            )
            await update.answer() # Acknowledge the callback
        else:
             # Reply to the command
             await update.reply_text(
                f"**{GEN_TOKEN_TITLE}**\n\n{instruction_message}",
                reply_markup=reply_markup,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=True
             )
    except (MessageIdInvalid, MessageNotModified):
         # If edit fails, send as a new message
         await client.send_message(
            chat_id=chat_id,
            text=f"**{GEN_TOKEN_TITLE}**\n\n{instruction_message}",
            reply_markup=reply_markup,
            parse_mode=config.PARSE_MODE,
            disable_web_page_preview=True
         )
         if is_callback:
             await update.answer("Cannot edit message. Sending token link as new message.", show_alert=False)
    except Exception as e:
         tokens_logger.error(f"Failed to send/edit generate token message for user {user_id}: {e}")
         if is_callback: await update.answer(ERROR_OCCURRED, show_alert=True)
         else: await update.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


# Handler for the "How to Earn" tutorial button
@Client.on_callback_query(filters.regex("^tokens_tutorial$"))
async def tokens_tutorial_callback(client: Client, callback_query: CallbackQuery):
    """Handles the 'How to Earn Tokens' tutorial button."""
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id

    tutorial_message_text = ""
    reply_markup = None

    if config.HOW_TO_EARN_TUTORIAL_LINK:
        # Send message with link to external tutorial (Telegraph/YouTube)
        tutorial_message_text = EARN_TOKENS_TUTORIAL_MESSAGE_LINK_INTRO.format()
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 Watch Tutorial", url=config.HOW_TO_EARN_TUTORIAL_LINK)],
            [InlineKeyboardButton(BUTTON_BACK, callback_data="menu_earn_tokens")] # Back button
        ])
    else:
        # Send text-based tutorial
        tutorial_message_text = EARN_TOKENS_TUTORIAL_MESSAGE_TEXT.format(tokens_earned=config.TOKENS_PER_REDEEM)
        reply_markup = InlineKeyboardMarkup([
             [InlineKeyboardButton(BUTTON_BACK, callback_data="menu_earn_tokens")] # Back button
        ])


    try:
        await callback_query.message.edit_text(
             tutorial_message_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True
         )
        await callback_query.answer() # Acknowledge callback
    except (MessageIdInvalid, MessageNotModified):
         await client.send_message(
              chat_id=chat_id,
              text=tutorial_message_text,
              reply_markup=reply_markup,
              parse_mode=config.PARSE_MODE,
              disable_web_page_preview=True
         )
         await callback_query.answer("Cannot edit message. Sending tutorial as new message.", show_alert=False)
    except Exception as e:
        tokens_logger.error(f"Failed to send token tutorial message to user {user_id}: {e}")
        await callback_query.answer(ERROR_OCCURRED, show_alert=True)
        await callback_query.message.edit_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


# Function called from common_handlers.py when /start {token} is received
async def handle_token_redemption(client: Client, user_id: int, token_string: str) -> str:
    """
    Handles the logic when a user starts the bot with a token payload.
    This function is called by start_command_or_home_callback in common_handlers.py.
    Returns a string key indicating the redemption result message to be sent.
    """
    tokens_logger.info(f"User {user_id} attempting to redeem token payload: {token_string}")

    # Find the generated token in the database
    # Query for a token that matches the string AND hasn't been redeemed
    generated_token_doc = await MongoDB.generated_tokens_collection().find_one(
        {"token_string": token_string, "is_redeemed": False}
    )

    if generated_token_doc is None:
        # Check if it exists but was already redeemed or is invalid string
        # Could also check for tokens with this string but is_redeemed: True to give a specific message
        existing_but_used = await MongoDB.generated_tokens_collection().find_one({"token_string": token_string})
        if existing_but_used:
             return "TOKEN_ALREADY_REDEEMED" # It existed but was used
        else:
             return "TOKEN_INVALID" # Never existed

    # Use Pydantic model to work with the token data
    try:
         generated_token = GeneratedToken(**generated_token_doc)
    except Exception as e:
         tokens_logger.error(f"Error validating generated token data from DB for token {token_string}: {e}")
         return ERROR_OCCURRED # Should ideally return a specific db error key

    # Check if the token has expired
    if generated_token.expires_at < datetime.now(timezone.utc):
        # Mark the token as expired (and implicitly redeemed == True) in DB to prevent future attempts
        try:
            await MongoDB.generated_tokens_collection().update_one(
                {"_id": generated_token.id},
                {"$set": {"is_redeemed": True}} # Mark as used (expired)
            )
        except Exception as e:
             tokens_logger.error(f"Failed to update expired token {generated_token.token_string}: {e}")
             # Log but continue, user still gets expired message

        tokens_logger.info(f"Token {token_string} expired for user {user_id}.")
        return "TOKEN_EXPIRED"

    # Check if the user attempting to redeem is the one who generated it (Corrected Logic)
    if generated_token.generated_by_user_id != user_id:
        tokens_logger.warning(f"User {user_id} attempted to redeem token {token_string} generated by {generated_token.generated_by_user_id}. Flow issue?")
        # Returning "TOKEN_REDEEMED_OWN" seems closest based on our revised strings, indicating it's not for this user
        return "TOKEN_REDEEMED_OWN" # This message now means "this isn't your link"

    # --- Redemption is Valid ---
    # Mark the token as redeemed in the database
    try:
        update_result = await MongoDB.generated_tokens_collection().update_one(
            {"_id": generated_token.id, "is_redeemed": False}, # Crucially, ensure it's still not redeemed
            {"$set": {"is_redeemed": True, "redeemed_at": datetime.now(timezone.utc)}}
        )

        if update_result.matched_count == 0:
            # This is a race condition edge case - someone else (or another process) redeemed it milliseconds before
            tokens_logger.warning(f"Race condition: Token {token_string} was already marked as redeemed before update attempt by user {user_id}.")
            return "TOKEN_ALREADY_REDEEMED"

    except Exception as e:
        tokens_logger.error(f"Failed to mark token {token_string} as redeemed for user {user_id}: {e}")
        return ERROR_OCCURRED # Indicate database error

    # Credit the user's token balance
    user = await get_user(client, user_id) # Get user data to update their tokens
    if user is None:
         tokens_logger.error(f"Could not retrieve user {user_id} to credit tokens after redeeming token {token_string}.")
         # Token is marked redeemed, but user didn't get tokens. Needs admin intervention.
         # Log a critical alert.
         return ERROR_OCCURRED # Database error retrieving user

    try:
         update_result = await MongoDB.users_collection().update_one(
             {"user_id": user_id},
             {"$inc": {"tokens": config.TOKENS_PER_REDEEM}} # Atomically increase tokens
         )

         if update_result.matched_count > 0:
            tokens_logger.info(f"Successfully credited {config.TOKENS_PER_REDEEM} tokens to user {user_id} via token {token_string}. New token balance: {user.tokens + config.TOKENS_PER_REDEEM}")
            # Update the user object we have in memory with the new token count BEFORE returning the success message key
            user.tokens += config.TOKENS_PER_REDEEM
            return "TOKEN_REDEEMED_SUCCESS"
         else:
             tokens_logger.error(f"Failed to credit tokens to user {user_id} using $inc after token redemption. User doc not found?")
             # Log critical, might need manual token adjustment for this user
             return ERROR_OCCURRED # Indicate error in user update

    except Exception as e:
         tokens_logger.error(f"Failed to update user tokens using $inc for user {user_id} after token redemption: {e}")
         return ERROR_OCCURRED # Indicate database error


# You might also need admin handlers in admin_handlers.py to manage user tokens:
# /add_tokens <user_id> <amount>
# /remove_tokens <user_id> <amount>
