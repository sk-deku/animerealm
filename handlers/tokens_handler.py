# handlers/tokens_handler.py
import logging
import asyncio
import uuid # To generate unique tokens
from datetime import datetime, timedelta, timezone # Use timezone aware datetimes
from typing import Optional, Dict, Any, Union
import aiohttp # Using aiohttp for async HTTP requests to the shortener API
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import config # Import config for API keys, expiry, etc.
from strings import (
    GEN_TOKEN_TITLE, GEN_TOKEN_INSTRUCTIONS,
    BUTTON_GO_TO_TOKEN_LINK, BUTTON_HOW_TO_EARN_TOKENS,
    EARN_TOKENS_TUTORIAL_MESSAGE_TEXT, EARN_TOKENS_TUTORIAL_MESSAGE_LINK_INTRO,
    TOKEN_REDEEMED_SUCCESS, TOKEN_REDEEMED_OWN,
    TOKEN_ALREADY_REDEEMED, TOKEN_EXPIRED, TOKEN_INVALID,
    ERROR_OCCURRED,
    BUTTON_BACK # For tutorial navigation
)

from database.mongo_db import MongoDB # Access the MongoDB class instance methods
from database.models import User, GeneratedToken # Import models
# get_user, save_user might be imported from common_handlers if used, but for tokens $inc is better
# from handlers.common_handlers import get_user # If you need to fetch the user model after $inc

# Configure logger for tokens handlers
tokens_logger = logging.getLogger(__name__)

# --- Helper Functions ---

async def shorten_url(long_url: str) -> Optional[str]:
    """
    Uses an external URL shortener API to shorten a given URL.
    Requires config.SHORTENER_API_URL, config.SHORTENER_API_KEY, config.SHORTENER_ENDPOINT.
    Returns the shortened URL string or None on failure or if config is missing.

    **IMPORTANT:** Adapt the aiohttp request and response parsing below to
    match the specific API documentation of your chosen URL shortener service.
    """
    if not config.SHORTENER_API_URL or not config.SHORTENER_API_KEY or not config.SHORTENER_ENDPOINT:
        tokens_logger.error("URL Shortener API configuration is incomplete. Cannot shorten link.")
        # No config to log sensitive details here. Error is clear.
        return None # Configuration missing or incomplete

    try:
        # Construct the API endpoint URL using format string from config.SHORTENER_ENDPOINT
        # You might need to URL-encode the long_url depending on the API. aiohttp usually handles basic encoding for query params.
        api_endpoint = config.SHORTENER_ENDPOINT.format(
            shortener_site_url=config.SHORTENER_API_URL,
            api_key=config.SHORTENER_API_KEY,
            long_url=long_url # The long URL to be shortened
        )
        tokens_logger.debug(f"Calling shortener API: {api_endpoint.replace(config.SHORTENER_API_KEY, '***')}") # Log API call without key

        # Use aiohttp for asynchronous request
        async with aiohttp.ClientSession() as session:
            async with session.get(api_endpoint) as response:
                if response.status == 200:
                    # --- BEGIN: Adapt Response Parsing Logic for Your API ---
                    # This part is highly dependent on the SHORTENER_API's response format (JSON, text, XML, etc.)
                    # Example assuming JSON response with a 'shortenedUrl' key:
                    try:
                         result = await response.json()
                         # Adapt this based on YOUR API's success structure
                         # Example check: is there a status/code indicating success?
                         # Example success: {"url":{"status":7,"shortLink":"https:\/\/cutt.ly\/HwS8XpS"}} for Cuttly with status 7
                         # Check API documentation!

                         # Placeholder logic: assuming success means JSON is parseable and has a specific key or structure
                         # If using Cuttly, might need to check result['url']['status'] and result['url']['shortLink']
                         shortened_url = None
                         if 'url' in result and isinstance(result['url'], dict) and 'shortLink' in result['url']: # Cuttly Example
                              if result['url'].get('status') == 7: # Cuttly Status 7 is success
                                   shortened_url = result['url']['shortLink']
                         # Example for a simpler API that might just return {"short": "...", "long": ...}
                         # if 'short' in result: shortened_url = result['short']

                         if shortened_url:
                              tokens_logger.info(f"Successfully shortened URL: {long_url} -> {shortened_url}")
                              return shortened_url
                         else:
                             response_text = await response.text() # Get response text if JSON parsing failed or key missing
                             tokens_logger.error(f"Shortener API returned 200 but no valid shortened URL in response. Result: {result}. Raw: {response_text}. Check API response format.", exc_info=True)
                             return None

                    except aiohttp.ContentTypeError:
                        # API didn't return JSON, might be plain text
                        response_text = await response.text()
                        # If your API returns plain text shortened URL, parse it here
                        tokens_logger.info(f"Shortener API returned 200 with non-JSON content: {response_text}. Check API documentation.")
                        # If the response IS the URL, return response_text directly:
                        # return response_text.strip() if response_text else None
                        return None # Defaulting to None if not expecting plain text URL directly


                    except Exception as parse_e:
                         # Error during JSON parsing or accessing keys
                         response_text_fallback = await response.text()
                         tokens_logger.error(f"Error parsing Shortener API response for URL {long_url}: {parse_e}. Raw Response: {response_text_fallback}", exc_info=True)
                         return None

                    # --- END: Adapt Response Parsing Logic for Your API ---

                else:
                    # API returned non-200 status code (e.g., 400, 401, 404, 500)
                    response_text = await response.text() # Get response body for debugging
                    tokens_logger.error(f"Shortener API failed for URL {long_url}. Status: {response.status}, Response: {response_text}. Check API key/endpoint/limits.", exc_info=True)
                    return None
    except aiohttp.ClientConnectorError as e:
         # Connection error (e.g., network issues, API endpoint not reachable)
         tokens_logger.error(f"Shortener API connection error for URL {long_url}: {e}. Is the SHORTENER_SITE_URL correct and reachable?", exc_info=True)
         return None
    except Exception as e:
        tokens_logger.error(f"An unexpected error occurred during URL shortening API call for {long_url}: {e}", exc_info=True)
        return None


# Function to calculate download tokens per file size if implementing complex token system
# async def calculate_tokens_for_file(file_size_bytes: int) -> int:
#     # Placeholder - simple 1 token per file currently based on config
#     return config.TOKENS_PER_REDEEM # Or different config value for download cost


# --- Handler Functions ---

@Client.on_message(filters.command("gen_token") & filters.private)
@Client.on_callback_query(filters.regex("^menu_earn_tokens$"))
async def generate_token_link_handler(client: Client, update: Union[Message, CallbackQuery]):
    """Handles the /gen_token command and 'Earn Tokens' button callback."""
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    user_id = update.from_user.id
    is_callback = isinstance(update, CallbackQuery)
    message_id = update.id if isinstance(update, Message) else update.message.id

    user = await MongoDB.users_collection().find_one({"user_id": user_id})
    if user is None:
         # This case should ideally not happen due to get_user on /start, but as a safeguard
         if is_callback: await update.answer(ERROR_OCCURRED, show_alert=True)
         else: await update.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE);
         return # Cannot proceed without user data

    tokens_logger.info(f"User {user_id} initiated token link generation.")

    # Check for and potentially clear any lingering user state
    user_state = await get_user_state(user_id)
    if user_state:
         common_logger.warning(f"User {user_id} was in state {user_state.handler}:{user_state.step} before generating token. Clearing state.")
         await clear_user_state(user_id)


    # Generate a unique token (UUID recommended)
    unique_token = str(uuid.uuid4())

    # Construct the Telegram start link that the shortener will redirect to
    # This uses the bot's current username (safer than hardcoding)
    try:
        bot_username = client.me.username
    except Exception as e:
        tokens_logger.error(f"Failed to get bot username to construct token link: {e}")
        error_msg = "💔 Sorry, cannot generate token link right now. Failed to get bot username."
        if is_callback: await update.answer(error_msg, show_alert=True)
        else: await update.reply_text(error_msg, parse_mode=config.PARSE_MODE);
        return

    long_telegram_link = config.REDEEM_LINK_PATTERN_TELEGRAM.format(
        bot_username=bot_username,
        token=unique_token
    )

    # Attempt to shorten the link using the configured API
    shortened_url = await shorten_url(long_telegram_link)

    if shortened_url is None:
        # If shortening failed (API config missing or error), inform the user
        error_msg = "💔 Sorry, unable to generate the token link right now. The link shortening service is not available."
        tokens_logger.error(f"Failed to generate token link for user {user_id} - Shortener failed.")
        if is_callback: await update.answer(error_msg, show_alert=True)
        else: await update.reply_text(error_msg, parse_mode=config.PARSE_MODE);
        return

    # Calculate token expiry time (timezone-aware)
    expiry_datetime = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_LINK_EXPIRY_HOURS)

    # Save the generated token in the database
    try:
        new_generated_token = GeneratedToken(
            token_string=unique_token,
            generated_by_user_id=user_id, # Associate the token with the user who generated it
            expires_at=expiry_datetime,
            created_at=datetime.now(timezone.utc)
        )
        await MongoDB.generated_tokens_collection().insert_one(new_generated_token.dict(by_alias=True, exclude_none=True))
        tokens_logger.info(f"Generated and saved token {unique_token} for user {user_id}, expires at {expiry_datetime.isoformat()}.")
    except Exception as e:
        # This could be a database error (e.g., connection issues, permission problems)
        tokens_logger.error(f"Failed to save generated token {unique_token} for user {user_id}: {e}", exc_info=True)
        error_msg = "💔 Failed to save token details in the database. Please try again later."
        if is_callback: await update.answer(error_msg, show_alert=True)
        else: await update.reply_text(error_msg, parse_mode=config.PARSE_MODE);
        return # Do not proceed if saving token failed


    # Create inline keyboard with the shortened link button and tutorial button
    keyboard_buttons = [
        [InlineKeyboardButton(BUTTON_GO_TO_TOKEN_LINK, url=shortened_url)], # Open the shortened URL
    ]
    # Add tutorial button only if tutorial text is available or a link is configured
    if config.HOW_TO_EARN_TUTORIAL_LINK or strings.EARN_TOKENS_TUTORIAL_MESSAGE_TEXT:
        keyboard_buttons.append([InlineKeyboardButton(BUTTON_HOW_TO_EARN_TOKENS, callback_data="tokens_tutorial")])

    # Add a Back button to the main menu? Users might want to leave this screen.
    keyboard_buttons.append([InlineKeyboardButton(BUTTON_HOME, callback_data="menu_home")])

    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    # Format the instructional message with details like tokens earned and expiry
    instruction_message = GEN_TOKEN_INSTRUCTIONS.format(
        tokens_earned=config.TOKENS_PER_REDEEM, # How many tokens are earned per completion
        expiry_hours=config.TOKEN_LINK_EXPIRY_HOURS
        # You could also add the formatted expiry date here
        # formatted_expiry_date = expiry_datetime.astimezone(timezone.localzone()).strftime('%Y-%m-%d %H:%M %Z') # Needs pytz for local timezone or specific handling
        # Add this to string format: expires: {formatted_expiry_date}
    )


    # Send or edit the message to display the generated link and options
    # If it was a command, send a new reply message. If callback, edit the menu message.
    try:
        if is_callback:
            # Edit the message that contained the button (e.g., the main menu or previous token menu)
            await update.message.edit_text(
                f"**{GEN_TOKEN_TITLE}**\n\n{instruction_message}",
                reply_markup=reply_markup,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=True # Important for URL buttons
            )
            await update.answer() # Acknowledge the callback query
        else:
             # If invoked via command, send a new reply
             await update.reply_text(
                f"**{GEN_TOKEN_TITLE}**\n\n{instruction_message}",
                reply_markup=reply_markup,
                parse_mode=config.PARSE_MODE,
                disable_web_page_preview=True
             )
    except (MessageIdInvalid, MessageNotModified):
         # Message could be too old to edit, send as a new message fallback
         await client.send_message(
              chat_id=chat_id,
              text=f"**{GEN_TOKEN_TITLE}**\n\n{instruction_message}",
              reply_markup=reply_markup,
              parse_mode=config.PARSE_MODE,
              disable_web_page_preview=True
         )
         if is_callback:
              try: await update.answer("Cannot edit message. Sending token link as a new message.", show_alert=False)
              except Exception: pass # Ignore answer failures


    except Exception as e:
         # Generic error during message sending/editing
         tokens_logger.error(f"Failed to send/edit generate token message for user {user_id}: {e}", exc_info=True)
         if is_callback: await update.answer(ERROR_OCCURRED, show_alert=True)
         else: await update.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE);


# Handler for the "How to Earn" tutorial button
@Client.on_callback_query(filters.regex("^tokens_tutorial$") & filters.private)
async def tokens_tutorial_callback(client: Client, callback_query: CallbackQuery):
    """Handles the 'How to Earn Tokens' tutorial button."""
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id
    message_id = callback_query.message.id # ID of the message to edit

    # Acknowledge the callback immediately
    try: await callback_query.answer()
    except Exception: tokens_logger.warning(f"Failed to answer callback query: tokens_tutorial from user {user_id}")

    tutorial_message_text = ""
    reply_markup = None

    if config.HOW_TO_EARN_TUTORIAL_LINK:
        # Display a link to the external tutorial
        tutorial_message_text = EARN_TOKENS_TUTORIAL_MESSAGE_LINK_INTRO.format()
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 Watch Tutorial", url=config.HOW_TO_EARN_TUTORIAL_LINK)],
            [InlineKeyboardButton(BUTTON_BACK, callback_data="menu_earn_tokens")] # Back button to the generate token screen
        ])
    else:
        # Display text-based tutorial
        tutorial_message_text = EARN_TOKENS_TUTORIAL_MESSAGE_TEXT.format(tokens_earned=config.TOKENS_PER_REDEEM)
        reply_markup = InlineKeyboardMarkup([
             [InlineKeyboardButton(BUTTON_BACK, callback_data="menu_earn_tokens")] # Back button to the generate token screen
        ])

    # Edit the message to display the tutorial content and keyboard
    try:
        await callback_query.message.edit_text(
             tutorial_message_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True # Disable preview for any potential links in text
         )
    except (MessageIdInvalid, MessageNotModified):
         # If editing failed (message too old/already edited), send as a new message
         await client.send_message(
              chat_id=chat_id,
              text=tutorial_message_text,
              reply_markup=reply_markup,
              parse_mode=config.PARSE_MODE,
              disable_web_page_preview=True
         )
         try: await callback_query.answer("Cannot edit message. Sending tutorial as a new message.", show_alert=False)
         except Exception: pass # Ignore answer failures


    except Exception as e:
        tokens_logger.error(f"Failed to send token tutorial message to user {user_id}: {e}", exc_info=True)
        await callback_query.message.reply_text(ERROR_OCCURRED, parse_mode=config.PARSE_MODE) # Reply error as new message


# --- Token Redemption Logic (/start {token} Payload) ---

# This async function is called from common_handlers.start_command_or_home_callback
# when a '/start' command includes a payload.
async def handle_token_redemption(client: Client, user_id: int, token_string: str) -> str:
    """
    Handles the logic when a user starts the bot with a token payload from a link.
    Returns a string key (from strings.py) indicating the redemption result.
    """
    tokens_logger.info(f"User {user_id} attempting to redeem token payload: {token_string}")

    # Check if the user exists in the database (they should, /start handler creates them)
    user_doc = await MongoDB.users_collection().find_one({"user_id": user_id})
    if user_doc is None:
        tokens_logger.error(f"User {user_id} attempted to redeem token but was not found in DB after /start.")
        # This indicates a more serious issue in user creation flow.
        return ERROR_OCCURRED # Indicate a database error

    # Find the generated token in the database that matches the string AND is not redeemed
    # Add a filter for 'generated_by_user_id': This token must be the one generated by THIS user
    generated_token_doc = await MongoDB.generated_tokens_collection().find_one(
        {"token_string": token_string, "is_redeemed": False, "generated_by_user_id": user_id}
    )

    if generated_token_doc is None:
        # Token not found, OR it was found but isn't associated with *this* user OR already redeemed/invalidated by time/deletion.
        # We need to distinguish between "invalid" and "already used".
        # First check if *any* token with this string existed and was generated by THIS user:
        existing_but_used = await MongoDB.generated_tokens_collection().find_one({"token_string": token_string, "generated_by_user_id": user_id})
        if existing_but_used:
            # It was generated by this user, but is_redeemed must be True or it expired implicitly (though we mark redeemed on expiry too).
            return "TOKEN_ALREADY_REDEEMED" # Use this message key to indicate it was used/invalidated

        else:
            # The token string doesn't exist AT ALL, OR it exists but was generated by a *different* user.
            # According to corrected flow, only the generator redeems it. So if another user gets this far,
            # it's likely an error in understanding or workflow, or someone else forwarding a personal link.
            # The simplest approach for this corrected flow is to treat any link used by non-generator as "invalid for this user".
            return "TOKEN_INVALID" # Use "invalid" for any token not belonging to or available to THIS user.


    # If generated_token_doc is found, the token exists, belongs to this user, and is not yet redeemed.
    # Use Pydantic model for cleaner access to token data
    try:
         generated_token = GeneratedToken(**generated_token_doc)
         # Validate model (implicitly done by ** expansion if strict is used or model has validation)
    except Exception as e:
         tokens_logger.error(f"Error validating generated token data from DB for token {token_string}: {e}", exc_info=True)
         # Indicate a data integrity issue or DB error during fetch/parse
         return ERROR_OCCURRED # Should ideally be a more specific DB error key


    # Check if the token has expired based on its expires_at time
    if generated_token.expires_at < datetime.now(timezone.utc):
        # The token is valid but has expired.
        # Mark the token as redeemed in DB to prevent future attempts on this string
        try:
            await MongoDB.generated_tokens_collection().update_one(
                {"_id": generated_token.id, "is_redeemed": False}, # Double check state
                {"$set": {"is_redeemed": True, "redeemed_at": datetime.now(timezone.utc)}} # Mark as used (expired) with timestamp
            )
            tokens_logger.info(f"Token {token_string} expired for user {user_id}. Marked as redeemed.")
        except Exception as e:
             tokens_logger.error(f"Failed to update expired token {generated_token.token_string} state for user {user_id}: {e}", exc_info=True)
             # Log this but still return the expired message key to the user.


        return "TOKEN_EXPIRED"

    # --- Redemption is Valid ---
    # The token is valid, not expired, not redeemed, and belongs to this user.
    # Mark the token as redeemed in the database *before* crediting tokens (minimize race window where user could redeem twice quickly)
    try:
        update_result = await MongoDB.generated_tokens_collection().update_one(
            {"_id": generated_token.id, "is_redeemed": False}, # Crucially, ensure it's still not redeemed (handle race condition)
            {"$set": {"is_redeemed": True, "redeemed_at": datetime.now(timezone.utc)}}
        )

        if update_result.matched_count == 0:
            # This means the token document matching _id and is_redeemed: False was not found.
            # Very likely a race condition: the token was already marked redeemed by another rapid attempt by the same user.
            tokens_logger.warning(f"Race condition detected: Token {token_string} was already marked as redeemed just before the update for user {user_id}.")
            return "TOKEN_ALREADY_REDEEMED" # Indicate it was just used

    except Exception as e:
        tokens_logger.error(f"Failed to mark token {token_string} as redeemed for user {user_id}: {e}", exc_info=True)
        # Log critical failure as user completed flow but token not marked. Manual review needed.
        return ERROR_OCCURRED # Indicate database error


    # Credit the user's token balance using an atomic increment operation
    try:
         # Get the current user document to know their starting balance (optional, for logging/message formatting)
         # Doing an atomic $inc doesn't require knowing the previous value
         user_update_result = await MongoDB.users_collection().update_one(
             {"user_id": user_id},
             {"$inc": {"tokens": config.TOKENS_PER_REDEEM}, "$set": {"last_updated_at": datetime.now(timezone.utc)}} # Also update last activity timestamp
         )

         if user_update_result.matched_count > 0 and user_update_result.modified_count > 0:
            tokens_logger.info(f"Successfully credited {config.TOKENS_PER_REDEEM} tokens to user {user_id} via token {token_string}.")

            # Re-fetch the user document to get their *new* token balance for the success message
            updated_user_doc = await MongoDB.users_collection().find_one({"user_id": user_id})
            new_token_balance = updated_user_doc.get("tokens", user_doc.get("tokens", 0) + config.TOKENS_PER_REDEEM) # Fallback

            # Return the success key
            return "TOKEN_REDEEMED_SUCCESS"

         else:
             # This shouldn't happen if user_doc was found earlier unless another process deleted the user document?
             tokens_logger.critical(f"Failed to credit tokens to user {user_id} using $inc after token redemption. User document modified 0 times? Manual review needed for token {token_string}.", exc_info=True)
             # Log critical, user completed flow but didn't get tokens.
             return ERROR_OCCURRED # Indicate failure in user update


    except Exception as e:
         # Error during the atomic update of user tokens
         tokens_logger.critical(f"Failed to update user tokens using $inc for user {user_id} after token redemption of token {token_string}: {e}", exc_info=True)
         # Log critical. Token marked redeemed, user did not get tokens.
         return ERROR_OCCURRED # Indicate database error


# Note: Admin token management (/add_tokens, /remove_tokens) should be in admin_handlers.py
# as they are admin utilities acting on user data.
