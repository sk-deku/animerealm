# handlers/request_handler.py
import logging
import asyncio
from typing import Union, List, Dict, Any, Optional
from pyrogram import Client, filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant
)


import config # Config includes ADMIN_IDS, REQUEST_TOKEN_COST, LOG_CHANNEL_ID
import strings # Strings for messages related to requests

# Import database models and utilities
from database.mongo_db import MongoDB
# Need specific collections: users, requests, anime (to check if added)
from database.mongo_db import get_user_state, set_user_state, clear_user_state # State management


# Import Pydantic models
from database.models import User, Request # User model for tokens, Request model


# Import helpers from common_handlers
from handlers.common_handlers import get_user, edit_or_send_message # Needed helpers
# Need helper for generating user mention for admin messages
from handlers.common_handlers import get_user_mention # Use this helper
# May need to access search handler or browse handler if linking requests to found content
# from . import search_handler
# from . import browse_handler


request_logger = logging.getLogger(__name__)


# --- Request States ---
# handler: "request"
class RequestState:
    # Initial state for user to request anime (from command or search no results)
    AWAITING_ANIME_NAME = "request_awaiting_anime_name" # Waiting for the user to send the anime name

    # States for Admin processing requests (maybe in admin_handlers?)
    # Let's handle admin side here for self-containment for request logic
    # ADMIN_VIEWING_REQUESTS = "admin_viewing_requests" # Admin viewing list of requests
    # ADMIN_REPLYING_TO_REQUEST = "admin_replying_to_request" # Admin prompted for reply


# --- User Request Handler (Command Entry Point) ---

@Client.on_message(filters.command("request") & filters.private)
async def request_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    user = await get_user(client, user_id) # Get user data for premium/token check
    if user is None:
        request_logger.error(f"User {user_id} not found in DB for /request command. DB Error.")
        await message.reply_text(strings.DB_ERROR, parse_mode=config.PARSE_MODE)
        return


    # --- Permission Check ---
    # Free users require tokens IF config.REQUEST_TOKEN_COST > 0
    # Premium users can request for free
    can_request = False
    request_cost = config.REQUEST_TOKEN_COST

    if user.premium_status != "free": # Premium user
         can_request = True
         request_cost = 0 # Free for premium

    elif request_cost > 0: # Free user, check tokens if cost is set
         if user.tokens >= request_cost:
              can_request = True
         # If not enough tokens, user sees message later.

    else: # Free user, cost is 0 (free requests for everyone)
        can_request = True
        request_cost = 0


    # If user does not have permission, inform them
    if not can_request:
         if user.premium_status == "free" and config.REQUEST_TOKEN_COST > 0:
             # Free user with insufficient tokens and cost > 0
              message_text = strings.REQUEST_NOT_ENOUGH_TOKENS.format(
                  required_tokens=request_cost,
                  user_tokens=user.tokens
               )
         # You could add messages for other permission failures if needed
         else:
              # Default if user has somehow blocked free requests, or config error
              message_text = "💔 You do not currently have permission to make requests." # Fallback

         await message.reply_text(message_text, parse_mode=config.PARSE_MODE)
         # Do NOT set state. Request failed at permission stage.
         return


    # --- User Has Permission - Prompt for Anime Name ---
    # Clear any previous user state if they were in a multi-step flow.
    user_state = await MongoDB.get_user_state(user_id)
    if user_state:
        request_logger.debug(f"User {user_id} was in state {user_state.handler}:{user_state.step} entering request. Clearing old state.")
        await MongoDB.clear_user_state(user_id)

    # Set state to AWAITING_ANIME_NAME
    # Store user's request cost and permission context in state data?
    # This is useful so when input is handled, we know it was a paid request.
    await MongoDB.set_user_state(
         user_id, "request", RequestState.AWAITING_ANIME_NAME,
         data={"request_cost": request_cost, "is_premium_request": (user.premium_status != "free")}
     )


    # Send the request prompt message based on user type
    prompt_text = strings.REQUEST_PROMPT_PREMIUM.format() if user.premium_status != "free" else strings.REQUEST_PROMPT_FREE.format(request_token_cost=request_cost, user_tokens=user.tokens) # Use relevant string

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BUTTON_CANCEL, callback_data="request_cancel")]]) # Add Cancel button

    await message.reply_text(prompt_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE, disable_web_page_preview=True)


# --- Handle User Request from Search No Results Button ---
# Catches callbacks: request_anime|<anime_name>
# This is also handled by common_handlers's handle_plain_text_input if user types anime name after /request command? No, that's different state.
# This callback comes from the Search Handler when no results are found and user clicks the request button.
@Client.on_callback_query(filters.regex(f"^request_anime{config.CALLBACK_DATA_SEPARATOR}.*") & filters.private)
async def request_from_search_callback(client: Client, callback_query: CallbackQuery):
     user_id = callback_query.from_user.id
     chat_id = callback_query.message.chat.id
     message_id = callback_query.message.id
     data = callback_query.data # request_anime|<anime_name>

     try: await client.answer_callback_query(message.id) # Answer immediately
     except Exception: request_logger.warning(f"Failed to answer callback query {data} from user {user_id}")


     user = await get_user(client, user_id) # Get user data
     if user is None:
         request_logger.error(f"User {user_id} not found in DB for request from search. DB Error.")
         await edit_or_send_message(client, chat_id, message_id, strings.DB_ERROR, disable_web_page_preview=True)
         return


     # Parse the requested anime name from callback data
     try:
         parts = data.split(config.CALLBACK_DATA_SEPARATOR)
         if len(parts) != 2: raise ValueError("Invalid callback data format for request from search.")
         requested_anime_name = parts[1]

         if not requested_anime_name.strip(): raise ValueError("Empty anime name in callback.") # Avoid empty request

     except ValueError as e:
          request_logger.warning(f"User {user_id} invalid data for request from search callback {data}: {e}. Cannot submit request.")
          await edit_or_send_message(client, chat_id, message_id, "🚫 Invalid anime name in request data.", disable_web_page_preview=True)
          return # Cannot submit request


     # --- Permission Check (Same logic as /request command, but check context - from search no results) ---
     can_request = False
     request_cost = config.REQUEST_TOKEN_COST # Default cost for free users


     if user.premium_status != "free": # Premium user (free request)
          can_request = True
          request_cost = 0 # Free for premium
     elif request_cost > 0: # Free user, check tokens if cost is set
          if user.tokens >= request_cost:
               can_request = True
     # else: Free user, cost is 0 (free requests for everyone via search button)
     elif config.REQUEST_TOKEN_COST == 0:
          can_request = True
          request_cost = 0


     # If user cannot request, inform them based on reason.
     if not can_request:
         if user.premium_status == "free" and config.REQUEST_TOKEN_COST > 0:
              message_text = strings.REQUEST_NOT_ENOUGH_TOKENS.format(required_tokens=request_cost, user_tokens=user.tokens)
         # You could add messages for other permission failures
         else: message_text = "💔 You do not currently have permission to make requests." # Fallback


         await edit_or_send_message(client, chat_id, message_id, message_text, disable_web_page_preview=True)
         # No state needed, request failed.
         return


     # --- User Has Permission - Proceed to Submit Request ---
     # Note: This flow bypasses the AWAITING_ANIME_NAME state because the name is provided in the callback.
     # Proceed directly to request creation logic.
     request_logger.info(f"User {user_id} submitting request for '{requested_anime_name}' (From Search, Cost: {request_cost}).")


     # --- Check if Anime Already Exists ---
     # It came from "No Results" search, but do a more robust check just in case.
     # Fuzzy match again, or direct DB check? Direct check is safer.
     try:
          # Try finding an exact match by name first. Collation for case-insensitivity if available.
         existing_anime_doc = await MongoDB.anime_collection().find_one({"name": requested_anime_name}, collation={'locale': 'en', 'strength': 2})
         if existing_anime_doc:
              # Anime found. Inform user it exists instead of submitting request.
             anime = Anime(**existing_anime_doc) # Use model
             request_logger.info(f"User {user_id} requested '{requested_anime_name}', found existing anime ID {anime.id}.")
             await edit_or_send_message(
                 client, chat_id, message_id,
                 f"✅ Anime '<b>{anime.name}</b>' is already in the database! You can find it here:",
                 parse_mode=config.PARSE_MODE, disable_web_page_preview=True
             )
             # Link to the existing anime's details menu
             await search_handler.display_user_anime_details_menu(client, message, anime) # Reuse display function, requires original message

             return # Stop, request not submitted


     except Exception as e:
         request_logger.error(f"Error checking existing anime for request '{requested_anime_name}' by user {user_id}: {e}", exc_info=True)
         # Don't block request submission if checking fails. Log error and continue to submit.
         pass # Continue to request submission logic

     # --- Create and Submit the Request ---
     # Create a new Request document in database
     try:
         new_request = Request(user_id=user_id, anime_name_requested=requested_anime_name, status="pending") # Use model

         insert_result = await MongoDB.requests_collection().insert_one(new_request.dict()) # Insert as dict


         if insert_result.inserted_id:
              request_logger.info(f"Request {insert_result.inserted_id} submitted for '{requested_anime_name}' by user {user_id}.")
              # --- Deduct Tokens (if Free) and Inform User ---
              if user.premium_status == "free": # Only for free users
                   try:
                        update_result = await MongoDB.users_collection().update_one(
                             {"user_id": user_id, "tokens": {"$gte": request_cost}}, # Filter user & ensure they still have enough tokens (race condition check)
                             {"$inc": {"tokens": -request_cost}} # Atomically decrement tokens
                         )

                        if update_result.matched_count > 0 and update_result.modified_count > 0:
                            request_logger.info(f"User {user_id}: Successfully deducted {request_cost} tokens for request {insert_result.inserted_id}. New balance: {user.tokens - request_cost}.")
                            feedback_message = strings.REQUEST_RECEIVED_USER_CONFIRM_FREE.format(
                                anime_name=requested_anime_name,
                                request_token_cost=request_cost,
                                user_tokens=user.tokens - request_cost # Use updated balance conceptually
                            )

                        elif update_result.matched_count > 0:
                            # User found but tokens not >= cost - implies insufficient tokens *at the time of update*, after check.
                             request_logger.error(f"User {user_id}: Insufficient tokens ({user.tokens}) to deduct {request_cost} during atomic update for request {insert_result.inserted_id}. Race condition?")
                             # This means the user got the "has permission" message but token deduction failed.
                             # Data inconsistency! The request IS submitted. This is bad.
                             # What to do? Inform user something went wrong, ask admin to manually check tokens/request.
                             feedback_message = f"⚠️ Request submitted, but failed to deduct <b>{request_cost}</b> tokens. Contact admin. Request ID: <code>{insert_result.inserted_id}</code>"

                        else: # User document not matched at all? Critical error.
                             request_logger.critical(f"User {user_id} document not found during token deduction for request {insert_result.inserted_id}?!", exc_info=True)
                             feedback_message = f"💔 Request submitted, but a critical error occurred during token deduction. Contact admin. Request ID: <code>{insert_result.inserted_id}</code>"


                   except Exception as e:
                        request_logger.error(f"Error deducting tokens for user {user_id} after submitting request {insert_result.inserted_id}: {e}", exc_info=True)
                        feedback_message = f"💔 Request submitted, but failed to deduct tokens. Contact admin. Request ID: <code>{insert_result.inserted_id}</code>" # Inform user

              else: # Premium User - No token deduction needed
                   feedback_message = strings.REQUEST_RECEIVED_USER_CONFIRM_PREMIUM.format(anime_name=requested_anime_name) # Premium confirmation message


              await edit_or_send_message(client, chat_id, message_id, feedback_message, disable_web_page_preview=True)


              # --- Notify Admins About New Request ---
              await notify_admins_about_request(client, new_request, user) # Call helper function to notify admins


         else: # Insert operation did not yield an inserted_id - indicates insert failure.
             request_logger.critical(f"Request document insert failed for user {user_id}, anime '{requested_anime_name}'. No inserted_id.", exc_info=True)
             await edit_or_send_message(client, chat_id, message_id, "💔 Failed to submit your request. Please try again.", disable_web_page_preview=True)


     except Exception as e:
        # Error during database insertion or pre-check logic
        request_logger.critical(f"FATAL error submitting request for user {user_id}, anime '{requested_anime_name}': {e}", exc_info=True)
        await edit_or_send_message(client, chat_id, message_id, strings.ERROR_OCCURRED, disable_web_page_preview=True)


    # State is managed by calling search handler or it was in a request input state (now completed or cancelled)
    # No state is set or maintained by this specific callback handler.

# --- Handle Text Input for Request (from common_handlers) ---
# Called by common_handlers.handle_plain_text_input when user_state.handler == "request" and step is AWAITING_ANIME_NAME
async def handle_request_input(client: Client, message: Message, user_state: UserState, anime_name_input: str):
     """
     Handles user text input when in the request state (AWAITING_ANIME_NAME).
     Submits the request.
     Called by common_handlers.handle_plain_text_input.
     """
     user_id = message.from_user.id
     chat_id = message.chat.id
     message_id = message.id

     # Ensure state is AWAITING_ANIME_NAME (already done by common_handlers routing)
     # Ensure required context (cost, is_premium) is in state data
     request_cost = user_state.data.get("request_cost", config.REQUEST_TOKEN_COST) # Get cost from state data
     is_premium_request = user_state.data.get("is_premium_request", False) # Get premium status context


     if not anime_name_input.strip():
         # User sent empty text when expecting anime name.
         request_logger.warning(f"User {user_id} sent empty text for request name.")
         await message.reply_text("Please send the **<u>name</u>** of the anime you want to request.", parse_mode=config.PARSE_MODE)
         # State remains AWAITING_ANIME_NAME. User needs to send text again.
         return

     requested_anime_name = anime_name_input.strip()

     request_logger.info(f"User {user_id} submitting request for '{requested_anime_name}' (Input method, Cost: {request_cost}).")

     # --- Clear AWAITING_ANIME_NAME state ---
     # State is now effectively transitioning OUT of awaiting input.
     await MongoDB.clear_user_state(user_id) # Clear the input state


     # --- Check if Anime Already Exists (Do NOT use this if Search No Results implies check done) ---
     # If coming from /request command, need to check for existing anime first.
     # If coming from search no results, this check was already performed before offering button.
     # How to distinguish? State data again! Add 'source' to state data in /request command?
     # Let's simplify: Always check for existing anime when processing the typed input, as this path is for /request command where no prior check happened.
     try:
         existing_anime_doc = await MongoDB.anime_collection().find_one({"name": requested_anime_name}, collation={'locale': 'en', 'strength': 2})
         if existing_anime_doc:
             # Anime found. Inform user it exists instead of submitting request.
             anime = Anime(**existing_anime_doc)
             request_logger.info(f"User {user_id} requested '{requested_anime_name}', found existing anime ID {anime.id}. From text input.")
             await message.reply_text(
                  f"✅ Anime '<b>{anime.name}</b>' is already in the database! You can find it here:",
                 parse_mode=config.PARSE_MODE
             )
             # Link to the existing anime's details menu
             await search_handler.display_user_anime_details_menu(client, message, anime) # Needs original message
             return # Stop, request not submitted

     except Exception as e:
         request_logger.error(f"Error checking existing anime for text input request '{requested_anime_name}' by user {user_id}: {e}", exc_info=True)
         # Don't block request submission if checking fails. Log error and continue.
         pass # Continue to request submission logic


     # --- Check Permissions (Re-verify based on state data) ---
     can_submit = False
     # Premium status context should be in state data from initial prompt
     is_premium = user_state.data.get("is_premium_request", False)

     if is_premium: # Premium user (cost was 0 from state data)
          can_submit = True
          request_cost_actual = 0 # Use the cost recorded in state data

     elif request_cost > 0: # Free user, check tokens again for safety + use state data cost
          # Fetch user again for current token count (needed for accurate message formatting)
          user = await get_user(client, user_id) # Get current user document
          if user is None:
               request_logger.error(f"User {user_id} not found in DB during request submission from text input. DB Error.")
               await message.reply_text(strings.DB_ERROR, parse_mode=config.PARSE_MODE); return
          # Use cost from state data. Check actual current token count against it.
          request_cost_actual = user_state.data.get("request_cost", config.REQUEST_TOKEN_COST)
          if user.tokens >= request_cost_actual:
              can_submit = True
          else: # Insufficient tokens
              message_text = strings.REQUEST_NOT_ENOUGH_TOKENS.format(required_tokens=request_cost_actual, user_tokens=user.tokens)
              await message.reply_text(message_text, parse_mode=config.PARSE_MODE); return # Fail


     else: # Free user, cost is 0 (free requests for everyone via text input too)
          can_submit = True
          request_cost_actual = 0 # Use cost from state data (should be 0)


     if not can_submit: # Should be covered by checks above, but safety
         request_logger.error(f"Request submission triggered for user {user_id} '{requested_anime_name}' but permission check failed unexpectedly.")
         await message.reply_text("💔 You do not currently have permission to make requests.", parse_mode=config.PARSE_MODE); return


     # --- Create and Submit the Request (Same logic as from Search Callback) ---
     try:
         new_request = Request(user_id=user_id, anime_name_requested=requested_anime_name, status="pending") # Use model

         insert_result = await MongoDB.requests_collection().insert_one(new_request.dict())


         if insert_result.inserted_id:
             request_logger.info(f"Request {insert_result.inserted_id} submitted for '{requested_anime_name}' by user {user_id}.")
             # --- Deduct Tokens (if Free) ---
             if not is_premium: # Only for free users who had a token cost
                 try:
                     # Need to ensure user exists again, or use find_one_and_update
                      user_before_deduct = await MongoDB.users_collection().find_one({"user_id": user_id})
                      if user_before_deduct and user_before_deduct.get("tokens", 0) >= request_cost_actual: # Final check
                           update_result = await MongoDB.users_collection().update_one(
                               {"user_id": user_id, "tokens": {"$gte": request_cost_actual}},
                               {"$inc": {"tokens": -request_cost_actual}}
                           )
                           if update_result.matched_count > 0 and update_result.modified_count > 0:
                               request_logger.info(f"User {user_id}: Successfully deducted {request_cost_actual} tokens for request {insert_result.inserted_id}.")
                               # Fetch user again for updated balance for confirmation message?
                               updated_user_doc = await MongoDB.users_collection().find_one({"user_id": user_id})
                               user_tokens_after = updated_user_doc.get("tokens", user_before_deduct.get("tokens", 0) - request_cost_actual)

                               feedback_message = strings.REQUEST_RECEIVED_USER_CONFIRM_FREE.format(
                                anime_name=requested_anime_name,
                                request_token_cost=request_cost_actual,
                                user_tokens=user_tokens_after # Use updated balance
                               )

                           else: # Match but no modify - tokens insufficient now?
                               request_logger.error(f"User {user_id}: Insufficient tokens at atomic update time for request {insert_result.inserted_id}! Race condition?")
                               feedback_message = f"⚠️ Request submitted, but failed to deduct <b>{request_cost_actual}</b> tokens. Contact admin. Request ID: <code>{insert_result.inserted_id}</code>"
                           await message.reply_text(feedback_message, parse_mode=config.PARSE_MODE) # Reply after token deduction

                      else: # User doc not found OR did not have enough tokens *just now*
                           request_logger.error(f"User {user_id} doc missing or insufficient tokens during request token deduct pre-check (text input flow). Cost: {request_cost_actual}", exc_info=True)
                           # Request is submitted, but deduction failed.
                           feedback_message = f"⚠️ Request submitted, but failed to deduct tokens. Contact admin. Request ID: <code>{insert_result.inserted_id}</code>"
                           await message.reply_text(feedback_message, parse_mode=config.PARSE_MODE)

                 except Exception as e:
                      request_logger.error(f"Error deducting tokens for user {user_id} after submitting request {insert_result.inserted_id} (text input flow): {e}", exc_info=True)
                      feedback_message = f"💔 Request submitted, but failed to deduct tokens. Contact admin. Request ID: <code>{insert_result.inserted_id}</code>"
                      await message.reply_text(feedback_message, parse_mode=config.PARSE_MODE) # Reply error message


             else: # Premium User - confirmation
                  feedback_message = strings.REQUEST_RECEIVED_USER_CONFIRM_PREMIUM.format(anime_name=requested_anime_name)
                  await message.reply_text(feedback_message, parse_mode=config.PARSE_MODE) # Reply confirmation


             # --- Notify Admins About New Request ---
             # Re-fetch user to get mention formatting.
             user = await get_user(client, user_id) # Get user data (guaranteed to exist)
             await notify_admins_about_request(client, new_request, user)


         else:
             request_logger.critical(f"Request document insert failed for user {user_id}, anime '{requested_anime_name}' from text input. No inserted_id.", exc_info=True)
             await message.reply_text("💔 Failed to submit your request. Please try again.", parse_mode=config.PARSE_MODE)


     except Exception as e:
        request_logger.critical(f"FATAL error submitting request for user {user_id}, anime '{requested_anime_name}' from text input: {e}", exc_info=True)
        await message.reply_text(strings.ERROR_OCCURRED, parse_mode=config.PARSE_MODE)


# Callback to cancel request input
@Client.on_callback_query(filters.regex("^request_cancel$") & filters.private)
async def cancel_request_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    data = callback_query.data

    if user_id not in config.ADMIN_IDS: # Allow cancelling by any user if in request state
        # Optional check: Ensure user is actually in AWAITING_ANIME_NAME state before cancelling.
        # user_state = await MongoDB.get_user_state(user_id)
        # if not (user_state and user_state.handler == "request" and user_state.step == RequestState.AWAITING_ANIME_NAME):
        #     await client.answer_callback_query(message_id, "You are not in a request process.", show_alert=False); return
        pass # Allow cancel button anytime it's present in request-related prompts


    try: await client.answer_callback_query(message.id, strings.ACTION_CANCELLED)
    except Exception: request_logger.warning(f"Failed to answer callback query {data} from user {user_id}.")

    await MongoDB.clear_user_state(user_id) # Clear the request input state
    await edit_or_send_message(client, chat_id, message_id, strings.ACTION_CANCELLED, reply_markup=None, disable_web_page_preview=True) # Edit message with confirmation


    request_logger.info(f"User {user_id} cancelled anime request input.")
    # After cancelling request, user might want to go back to main menu.
    # How to prompt them? Add a button "Return to main menu"?
    # Just let the cancellation confirmation stand. They can use /start.

# --- Admin Request Management ---
# (Moved here for self-containment, could also be in admin_handlers.py)

# This function is called after a new request is successfully saved
async def notify_admins_about_request(client: Client, request: Request, user: User):
     """Sends a notification message about a new request to the configured admin log channel."""
     admin_log_channel_id = config.LOG_CHANNEL_ID

     if not admin_log_channel_id:
         request_logger.warning("LOG_CHANNEL_ID is not configured. Cannot send new request notification to admins.")
         return # Cannot send notification if no channel ID


     # Format message for admins
     # Use user mention helper from common_handlers.
     requester_mention = get_user_mention(user) # User Pydantic model is needed by helper


     message_text = strings.REQUEST_NOTIFICATION_ADMIN.format(
          user_name=user.first_name or user.username or str(user.user_id), # Display name preference order
          user_id=user.user_id,
          anime_name=request.anime_name_requested,
     )

     # Add reply buttons for admins to respond (send response via bot)
     # Callback data should link back to THIS request ID and the predefined reply action
     # e.g., admin_reply_request|<request_id>|<action>
     buttons = [
         [
             InlineKeyboardButton(strings.BUTTON_REQ_UNAVAILABLE, callback_data=f"admin_reply_request{config.CALLBACK_DATA_SEPARATOR}{str(request.id)}{config.CALLBACK_DATA_SEPARATOR}unavailable"),
             InlineKeyboardButton(strings.BUTTON_REQ_ALREADY_ADDED, callback_data=f"admin_reply_request{config.CALLBACK_DATA_SEPARATOR}{str(request.id)}{config.CALLBACK_DATA_SEPARATOR}already_added"),
         ],
         [
              InlineKeyboardButton(strings.BUTTON_REQ_NOT_RELEASED, callback_data=f"admin_reply_request{config.CALLBACK_DATA_SEPARATOR}{str(request.id)}{config.CALLBACK_DATA_SEPARATOR}not_released"),
             InlineKeyboardButton(strings.BUTTON_REQ_WILL_ADD_SOON, callback_data=f"admin_reply_request{config.CALLBACK_DATA_SEPARATOR}{str(request.id)}{config.CALLBACK_DATA_SEPARATOR}will_add_soon"), # Added 'Will Add Soon'
         ]
         # Optional: Add a button to mark as DONE/FULFILLED once anime is added
         # [InlineKeyboardButton("✅ Mark Fulfilled (Manual)", callback_data=f"admin_mark_request_fulfilled{config.CALLBACK_DATA_SEPARATOR}{str(request.id)})"] # Admin would manually mark once anime is added

     ]

     reply_markup = InlineKeyboardMarkup(buttons)


     # Send the notification to the admin log channel
     try:
         sent_message = await client.send_message(
             chat_id=admin_log_channel_id,
             text=message_text,
             reply_markup=reply_markup,
             parse_mode=config.PARSE_MODE,
             disable_web_page_preview=True # Ensure user mention doesn't cause large preview
         )
         # Store the message ID of this notification? Can link reply actions back to this message for context/editing?
         # Yes, very useful to edit the admin message to show it's processed. Store in request doc or pass via callback.
         # Store message ID in the Request document for later reference.
         await MongoDB.requests_collection().update_one(
             {"_id": request.id},
             {"$set": {"admin_message_id": sent_message.id}} # Add message_id field to Request model! (or dynamic dict update)
         )

         request_logger.info(f"Sent request notification message {sent_message.id} to admin channel {admin_log_channel_id} for request {request.id}.")


     except UserNotParticipant:
          request_logger.critical(f"Bot is not an admin or participant in the configured LOG_CHANNEL_ID {admin_log_channel_id}. Cannot send request notification.")
          # Log a critical error, maybe fallback to sending message to OWNER_ID?

     except Exception as e:
        # Log any other error sending to channel
        request_logger.critical(f"Failed to send new request notification to admin channel {admin_log_channel_id}: {e}", exc_info=True)
        # Log the request details separately if notification failed, maybe to file/console log.


# Handler for admin clicking a predefined reply button on a request notification
# Catches callbacks: admin_reply_request|<request_id>|<action>
@Client.on_callback_query(filters.regex(f"^admin_reply_request{config.CALLBACK_DATA_SEPARATOR}.*{config.CALLBACK_DATA_SEPARATOR}.*") & filters.chat(config.ADMIN_IDS)) # Only trigger for messages in admin channels
async def admin_reply_to_request_callback(client: Client, callback_query: CallbackQuery):
     user_id = callback_query.from_user.id # Admin user who clicked
     chat_id = callback_query.message.chat.id # The admin channel chat ID
     message_id = callback_query.message.id # The message in the admin channel
     data = callback_query.data # admin_reply_request|<request_id>|<action>


     # Ensure user is an admin (already filtered by filters.chat, but redundant check doesn't hurt)
     if user_id not in config.ADMIN_IDS:
          await client.answer_callback_query(message.id, "🚫 You are not authorized to reply to requests.", show_alert=True)
          return


     # Answer callback
     try: await client.answer_callback_query(message.id, "Sending reply to user...")
     except Exception: request_logger.warning(f"Admin {user_id} failed to answer callback query {data} in admin channel.")


     try:
         # Parse callback data
         parts = data.split(config.CALLBACK_DATA_SEPARATOR)
         if len(parts) != 3: raise ValueError("Invalid callback data format for admin request reply.")
         request_id_str = parts[1] # The ID of the request document
         action = parts[2]       # The reply action string (e.g., 'unavailable')

         # Find the request document in DB by ID
         request_doc = await MongoDB.requests_collection().find_one({"_id": ObjectId(request_id_str)})
         if not request_doc:
             request_logger.error(f"Admin {user_id} tried to reply to non-existent request ID {request_id_str} from message {message_id}. Channel: {chat_id}.")
             await client.edit_message_text(
                  chat_id=chat_id, message_id=message_id, # Edit the notification message
                  text=f"⚠️ Error: Request {request_id_str} not found in DB.", # Update text
                  parse_mode=config.PARSE_MODE, reply_markup=None # Remove buttons
             )
             return

         # Convert to Request model
         request = Request(**request_doc)

         # Check if request is already processed (status is not pending)
         if request.status != "pending":
              await client.answer_callback_query(message.id, "Request already processed.", show_alert=True) # Alert admin
              # Optional: Edit the message to reflect the current status accurately? Or leave it as is.
              # For now, just alert admin.
              return

         # Find the user who made the request to send them a reply message
         requester_user = await get_user(client, request.user_id) # Use get_user helper (handles non-existence gracefully)
         if requester_user is None:
              request_logger.error(f"Requester user {request.user_id} not found in DB when admin {user_id} replying to request {request.id}. Cannot send reply.")
              # Still update the request status, but inform admin that user not found
              await client.edit_message_text(
                   chat_id=chat_id, message_id=message_id,
                   text=f"⚠️ Error: Requester User {request.user_id} not found. Could not send direct reply.\n\n" + message_id, # Add original message back
                   parse_mode=config.PARSE_MODE, reply_markup=None # Remove buttons
              )
             # Update request status in DB to show it was processed, but note error
              await MongoDB.requests_collection().update_one(
                   {"_id": request.id},
                   {"$set": {"status": "user_not_found", "admin_notes": f"Reply '{action}' selected, but requester user {request.user_id} not found in DB."}}
              )

              return


         # --- Construct the Admin Reply Message for the User ---
         # Map action string to a reply string from strings.py (defined by admin actions)
         # e.g., 'unavailable' -> BUTTON_REQ_UNAVAILABLE -> Reply with "Anime requested is unavailable." (Need reply text for each button)
         # Let's use dedicated strings for the reply text itself, matching action key.
         # Strings needed: REPLY_UNAVAILABLE, REPLY_ALREADY_ADDED, REPLY_NOT_RELEASED, REPLY_WILL_ADD_SOON
         reply_string_key = f"REPLY_{action.upper()}" # e.g., "REPLY_UNAVAILABLE"
         admin_reply_text_for_user = getattr(strings, reply_string_key, f"Admin replied: {action.replace('_', ' ')}.") # Get reply string, fallback if key missing

         # Format reply text for user, including requested anime name
         reply_for_user_message = strings.USER_REQUEST_RESPONSE.format(
              anime_name=request.anime_name_requested,
              admin_response=admin_reply_text_for_user
         )

         # --- Send the Reply Message to the User ---
         try:
             await client.send_message(
                  chat_id=request.user_id, # Send to the user who made the request
                  text=reply_for_user_message,
                  parse_mode=config.PARSE_MODE,
                  disable_web_page_preview=True # For safety with URLs
              )
             request_logger.info(f"Admin {user_id} replied '{action}' to user {request.user_id} for request {request.id}. Reply message sent.")

             # --- Update the Request Document Status in Database ---
             # Set status and add admin notes/action
             await MongoDB.requests_collection().update_one(
                  {"_id": request.id}, # Filter for the request
                  {"$set": {"status": action, "admin_notes": f"Admin {user_id} selected: '{action}'. Sent user reply."}} # Set status and add log note
             )
             request_logger.debug(f"Updated status of request {request.id} to '{action}'.")


             # --- Edit the Admin Channel Notification Message ---
             # Remove reply buttons and update message text to show it was processed
             try:
                 admin_user_mention = f'<a href="tg://user?id={user_id}">{callback_query.from_user.first_name.replace("&", "&").replace("<", "<").replace(">", ">") if callback_query.from_user.first_name else f"Admin {user_id}"}</a>'
                 processed_text = f"✅ Processed by {admin_user_mention}: Reply '{action}' sent to User {request.user_id}\n\n"
                 # Fetch the original message text (before buttons were added)
                 original_message_text = request_doc.get("original_admin_notification_text", "") # Add this field to Request model on insert
                 if original_message_text: processed_text += original_message_text
                 else: processed_text += f"Original Request ({request.anime_name_requested})" # Fallback

                 # To avoid race conditions and complex message updates, sometimes fetching original is simplest.
                 # Re-using the original text from the notification message *before* adding buttons might be safer if message ID stored.
                 # Or rebuild original notification message + added processed info.
                 # Fetch the notification message itself:
                 try:
                     notification_message = await client.get_messages(chat_id, message_id)
                     original_notification_text = notification_message.text # Get the text content
                 except Exception as get_msg_e:
                      request_logger.warning(f"Failed to fetch admin notification message {message_id} in chat {chat_id} to update status: {get_msg_e}")
                      original_notification_text = f"Original Request ({request.anime_name_requested})" # Fallback text content


                 processed_text = f"✅ Processed by {admin_user_mention}: Reply '{action}' sent.\n\n" + original_notification_text # Combine

                 await client.edit_message_text(
                     chat_id=chat_id, message_id=message_id,
                     text=processed_text, # Updated message text
                     parse_mode=config.PARSE_MODE,
                     reply_markup=None # Remove the inline buttons
                 )
             except Exception as edit_e:
                 request_logger.error(f"Failed to edit admin notification message {message_id} in chat {chat_id} after processing request {request.id}: {edit_e}", exc_info=True)
                 # Admin might not see the status update clearly, but the action IS done. Log.


         else: # Send message failed
              request_logger.error(f"Failed to send admin reply '{action}' message to user {request.user_id} for request {request.id}.")
              # Update request status but indicate failure to send user reply
              await MongoDB.requests_collection().update_one(
                   {"_id": request.id},
                   {"$set": {"status": f"replied_{action}_send_failed", "admin_notes": f"Admin {user_id} selected: '{action}', but failed to send user reply message."}}
              )
              # Edit admin message to show processing happened but reply failed
              admin_user_mention = f'<a href="tg://user?id={user_id}">{callback_query.from_user.first_name or f"Admin {user_id}"}</a>'
              processed_text = f"⚠️ Processed by {admin_user_mention}: Reply '{action}' **FAILED TO SEND** to User {request.user_id}\n\n" + f"Original Request ({request.anime_name_requested})"
              try: await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=processed_text, parse_mode=config.PARSE_MODE, reply_markup=None)
              except Exception as edit_e: request_logger.error(f"Failed to edit admin notification message after reply send failure: {edit_e}", exc_info=True)


     except ValueError:
         request_logger.warning(f"Admin {user_id} invalid callback data format for reply to request: {data}")
         await client.answer_callback_query(message.id, "🚫 Invalid data in callback.", show_alert=False)


     except Exception as e:
         # Error during admin reply processing
         request_logger.critical(f"FATAL error handling admin_reply_request callback {data} for admin {user_id}: {e}", exc_info=True)
         await client.answer_callback_query(message.id, strings.ERROR_OCCURRED, show_alert=True)
         # Attempt to edit the message to indicate processing failed or resulted in error state.
         admin_user_mention = f'<a href="tg://user?id={user_id}">{callback_query.from_user.first_name or f"Admin {user_id}"}</a>'
         processed_text = f"💔 Processing Error for Admin {admin_user_mention}: Check logs!\n\nOriginal Request: {request_doc.get('anime_name_requested', 'Unnamed Request')}" # Use raw doc data if model creation failed

         try: await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=processed_text, parse_mode=config.PARSE_MODE, reply_markup=None)
         except Exception as edit_e: request_logger.error(f"Failed to edit admin notification message after FATAL error: {edit_e}", exc_info=True)


# Note: admin_mark_request_fulfilled callback handler would be needed if implemented.
# This would change status in DB to "fulfilled", log it, and update admin message.
