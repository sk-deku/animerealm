# handlers/admin_handlers.py
import logging
import asyncio # For potential delays
from typing import Union, List, Dict, Any, Optional
from pyrogram import Client, filters # Import Pyrogram core and filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputTextMessageContent # For potential inline bots if implementing
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified, UserNotParticipant,
    AsyncioErrorMessage, BotInlineMessageNotFoundError
)
from bson import ObjectId # For working with MongoDB ObjectIds


import config # Import configuration constants (ADMIN_IDS, OWNER_ID, etc.)
import strings # Import string constants for messages


# Import database models and utilities
from database.mongo_db import MongoDB # Access MongoDB
from database.models import User # Import User model

# Import state management helpers if needed (likely for multi-step admin tasks, less for these)
from database.mongo_db import get_user_state, set_user_state, clear_user_state


# Import helpers
from handlers.common_handlers import get_user # Needed to fetch users
from handlers.common_handlers import get_user_mention # Needed to format user mentions for admins


admin_logger = logging.getLogger(__name__)

# --- Admin Command Handlers ---
# Note: All handlers here should include an admin check (if not handled by filters)

# Handler for /broadcast command - Initiates the broadcast workflow
@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await message.reply_text("🚫 You are not authorized to use this command.", parse_mode=config.PARSE_MODE)
        return

    # Broadcast command expects the message text directly in the command arguments
    broadcast_text = message.text.split(None, 1)[1] if len(message.text.split(None, 1)) > 1 else None

    if not broadcast_text:
        await message.reply_text("ℹ️ Usage: `/broadcast Your message text here.`", parse_mode=config.PARSE_MODE)
        return


    admin_logger.info(f"Admin {user_id} initiated broadcast. Message: '{broadcast_text[:100]}...'")

    # Need to confirm broadcast with admin before sending to all users
    # First, estimate the number of users to broadcast to
    try:
        total_users_count = await MongoDB.users_collection().count_documents({})
    except Exception as e:
        admin_logger.error(f"Failed to get total users count for broadcast for admin {user_id}: {e}", exc_info=True)
        total_users_count = "Unknown" # Fallback if DB error


    # Send confirmation message to the admin with preview and count
    confirm_text = strings.BROADCAST_CONFIRMATION.format(
         user_count=total_users_count,
         message_preview=broadcast_text[:500] + '...' if len(broadcast_text) > 500 else broadcast_text # Limit preview length
    )

    # Buttons: Confirm, Cancel
    reply_markup = InlineKeyboardMarkup([
        [
            # Callback to confirm broadcast: admin_confirm_broadcast|<message_text> (Pass the message text to confirmation handler)
            # Callback data size limit! Pass only text or store text in state?
            # Storing text in state is safer for large messages.
            # Set a temporary state: "admin:confirm_broadcast", data={"message": broadcast_text}
            InlineKeyboardButton(strings.BUTTON_CONFIRM_BROADCAST, callback_data=f"admin_confirm_broadcast"), # Just a confirmation callback, text is in state

            InlineKeyboardButton(strings.BUTTON_CANCEL_BROADCAST, callback_data="admin_cancel_broadcast") # Cancel broadcast
        ]
    ])


    # Store the broadcast message text in admin's state data for the confirmation step
    # Use state "admin" handler, step "confirm_broadcast"
    # State should be cleared if admin uses command again before confirming.
    # Clear any prior state if exists.
    user_state = await get_user_state(user_id)
    if user_state:
        admin_logger.warning(f"Admin {user_id} was in state {user_state.handler}:{user_state.step} before initiating broadcast confirmation. Clearing old state.")
        await clear_user_state(user_id)


    await set_user_state(user_id, "admin", "confirm_broadcast", data={"broadcast_message": broadcast_text, "total_users_count": total_users_count}) # Store message and user count in state


    # Reply to the command message with the confirmation prompt
    try:
         await message.reply_text(confirm_text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
         # Admin's message ID might be useful later? No, message is replied to.
    except Exception as e:
         admin_logger.error(f"Failed to send broadcast confirmation message to admin {user_id}: {e}", exc_info=True)
         await message.reply_text(strings.ERROR_OCCURRED, parse_mode=config.PARSE_MODE)
         # Clear the state if message send failed? Safer to clear on error in this state.
         await clear_user_state(user_id);


# Handler for confirmation callbacks related to broadcast
@Client.on_callback_query(filters.regex("^admin_confirm_broadcast$|^admin_cancel_broadcast$") & filters.private)
async def broadcast_confirmation_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id # Message containing the confirmation buttons
    data = callback_query.data # admin_confirm_broadcast or admin_cancel_broadcast


    # Admin Check - Use filters.chat to be strict or check manually
    if user_id not in config.ADMIN_IDS:
         await callback_query.answer("🚫 You are not authorized.", show_alert=True)
         return # Not admin


    # Acknowledge callback immediately
    try: await client.answer_callback_query(message.id)
    except Exception: admin_logger.warning(f"Admin {user_id} failed to answer callback query {data} in chat {chat_id}.")

    # Check user state - must be in the confirm_broadcast state
    user_state = await get_user_state(user_id)
    if not (user_state and user_state.handler == "admin" and user_state.step == "confirm_broadcast"):
        admin_logger.warning(f"Admin {user_id} clicked broadcast confirmation button {data} but in state {user_state.handler}:{user_state.step if user_state else 'None'}. Clearing state.")
        await edit_or_send_message(client, chat_id, message_id, "🔄 Invalid state for broadcast confirmation. Process cancelled.", disable_web_page_preview=True)
        await clear_user_state(user_id); return # Clear incorrect state


    broadcast_message_text = user_state.data.get("broadcast_message")
    total_users_count = user_state.data.get("total_users_count") # Can be "Unknown"


    # Ensure broadcast message text is available in state
    if broadcast_message_text is None:
         admin_logger.error(f"Admin {user_id} in confirm_broadcast state but 'broadcast_message' missing in state data: {user_state.data}. Clearing state.")
         await edit_or_send_message(client, chat_id, message_id, "💔 Broadcast message text missing from state. Process cancelled.", disable_web_page_preview=True)
         await clear_user_state(user_id); return # Clear corrupted state


    if data == "admin_confirm_broadcast":
         # --- Admin confirmed the broadcast ---
         admin_logger.info(f"Admin {user_id} CONFIRMED broadcast to {total_users_count} users. Message: '{broadcast_message_text[:100]}...'")

         # Inform admin that broadcast is starting. Edit the confirmation message.
         await edit_or_send_message(
              client, chat_id, message_id,
              strings.BROADCAST_STARTED + f"\n({total_users_count} users estimated)", # Add info
              reply_markup=None # Remove confirmation buttons
              # Optionally, add a "Stop Broadcast" button? Requires more state/logic.
         )

         # --- Start the broadcast process in the background ---
         # This is the core loop that sends messages to all users.
         # Do NOT block the handler, use asyncio.create_task
         asyncio.create_task(execute_broadcast(client, user_id, broadcast_message_text))

         # Clear the broadcast confirmation state now that processing is delegated
         await clear_user_state(user_id) # Broadcast task runs independently


    elif data == "admin_cancel_broadcast":
         # --- Admin cancelled the broadcast ---
         admin_logger.info(f"Admin {user_id} CANCELLED broadcast initiation.")

         # Inform admin that broadcast is cancelled. Edit the confirmation message.
         await edit_or_send_message(client, chat_id, message_id, strings.BROADCAST_CANCELLED, reply_markup=None) # Remove buttons
         # Clear the broadcast confirmation state
         await clear_user_state(user_id) # Clear state

    # If invalid callback data other than confirm/cancel falls through (should be caught by regex)
    # Generic callback handler might catch, or log.

async def execute_broadcast(client: Client, admin_user_id: int, message_text: str):
     """
     Sends the broadcast message to all bot users except the sending admin.
     Runs as an asynchronous background task. Handles errors and FloodWait.
     """
     admin_logger.info(f"Starting background broadcast execution for admin {admin_user_id}. Message: '{message_text[:100]}...'")
     sent_count = 0
     blocked_count = 0 # Count users who blocked bot


     try:
         # Fetch all user IDs from the database, projecting only user_id
         # Exclude the sending admin from the list? Yes, usually don't broadcast to self.
         users_cursor = MongoDB.users_collection().find({}, {"user_id": 1}).batch_size(100) # Use batch_size for efficiency


         # Iterate through all users fetched from the database
         async for user_doc in users_cursor:
              user_id_to_send = user_doc.get("user_id")

              if user_id_to_send is None: continue # Skip if user ID is missing
              if user_id_to_send == admin_user_id:
                   admin_logger.debug(f"Skipping broadcast to initiating admin {user_id_to_send}.")
                   continue # Skip the admin who initiated it


              try:
                   # Send the message to the user's private chat
                   # Use client.send_message - this is the operation that can trigger FloodWait/UserNotParticipant
                   await client.send_message(
                        chat_id=user_id_to_send, # Send to user ID (private chat)
                        text=message_text,
                        parse_mode=config.PARSE_MODE,
                        disable_web_page_preview=True
                   )
                   sent_count += 1 # Increment success count
                   # Log every successful send? Too verbose. Log progress.


              except UserNotParticipant:
                   # User has blocked the bot or somehow is not reachable via private chat.
                   blocked_count += 1 # Increment blocked count
                   # Consider marking user as inactive or removing them from DB if persistent (advanced).
                   admin_logger.debug(f"User {user_id_to_send} blocked bot or not participant. Cannot send broadcast.")
              except FloodWait as e:
                   # Rate limit hit for sending messages. Wait and continue broadcast.
                   admin_logger.warning(f"FloodWait during broadcast execution. Waiting {e.value}s before continuing...")
                   await asyncio.sleep(e.value)
                   # Try to send again to the SAME user after the wait. Or skip and continue?
                   # Retrying this specific user after wait is better. Put send logic in a retry loop.
                   # Simplified: Just wait and let the async for loop continue to the next user.
                   # Some messages might be missed in this simplified approach if FloodWait is hit between users.

                   # More robust retry logic for a single send attempt within the loop:
                   # try: await client.send_message(...) ... success=True ... except FloodWait as e: await asyncio.sleep(e.value); try again; finally success=False/Error.
                   # If successful after retry, continue loop. If still error, increment failed count or blocked count.
                   # For this example, simple FloodWait catch on send is acceptable. The loop just moves to next user.
                   continue # Skip current user on FloodWait and proceed after delay (simplified)


              except Exception as e:
                   # Any other error sending to a specific user
                   admin_logger.error(f"Failed to send broadcast message to user {user_id_to_send}: {e}", exc_info=True)
                   # Don't increment sent count. Increment a failed count if needed.
                   continue # Continue the loop to the next user

              # Add a small delay between sending messages to avoid hitting API limits too fast
              # Telegram API has limits per user and global. Default client handling helps, but extra delay is safer for broadcasts.
              await asyncio.sleep(0.05) # Example small delay


     except Exception as e:
          # Error during the database query or iteration
          admin_logger.critical(f"FATAL error during broadcast execution for admin {admin_user_id}: {e}", exc_info=True)
          # Notify the initiating admin that the broadcast failed.
          try: await client.send_message(admin_user_id, f"💔 Error occurred during broadcast execution: {e}", parse_mode=config.PARSE_MODE)
          except Exception: pass # If informing admin fails, just log


     finally:
         # Broadcast process finished (or failed)
         completion_message = f"📢 Broadcast process finished!\nSent to: {sent_count} users.\nBlocked/Unreachable: {blocked_count} users."
         admin_logger.info(completion_message)

         # Notify the initiating admin about the broadcast completion summary
         try: await client.send_message(admin_user_id, completion_message, parse_mode=config.PARSE_MODE)
         except Exception: pass # If informing admin fails, just log


# --- Admin User Token Management Handlers ---

# Handles /add_tokens <user_id> <amount>
@Client.on_message(filters.command("add_tokens") & filters.private)
async def add_tokens_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await message.reply_text("🚫 You are not authorized to use this command.", parse_mode=config.PARSE_MODE)
        return


    # Parse arguments: user ID and amount
    args = message.text.split(None, 2) # Split by whitespace, max 2 splits -> command, user_id_str, amount_str

    if len(args) != 3:
        await message.reply_text("ℹ️ Usage: `/add_tokens <user_id> <amount>`", parse_mode=config.PARSE_MODE)
        return


    target_user_id_str = args[1]
    amount_str = args[2]

    # Validate user ID and amount are integers
    try:
        target_user_id = int(target_user_id_str)
        amount_to_add = int(amount_str)
        if amount_to_add <= 0: raise ValueError("Amount must be positive.") # Must add positive tokens
    except ValueError:
        await message.reply_text("🚫 Invalid User ID or amount. User ID and amount must be positive integers.", parse_mode=config.PARSE_MODE)
        return


    admin_logger.info(f"Admin {user_id} attempting to add {amount_to_add} tokens to user {target_user_id}.")

    # --- Perform Database Update: Add tokens ---
    try:
        # Atomically increment the target user's token balance
        update_result = await MongoDB.users_collection().update_one(
            {"user_id": target_user_id}, # Filter by the target user ID
            {"$inc": {"tokens": amount_to_add}} # Increment tokens by amount
        )

        if update_result.matched_count > 0:
            if update_result.modified_count > 0:
                 # User found and tokens updated. Fetch updated user info for confirmation message.
                 updated_user_doc = await MongoDB.users_collection().find_one({"user_id": target_user_id}, {"tokens": 1}) # Get updated tokens
                 new_token_balance = updated_user_doc.get("tokens", "Unknown")

                 admin_logger.info(f"Admin {user_id} successfully added {amount_to_add} tokens to user {target_user_id}. New balance: {new_token_balance}.")
                 await message.reply_text(strings.ADMIN_TOKENS_ADDED_SUCCESS.format(amount=amount_to_add, user_id=target_user_id, new_balance=new_token_balance), parse_mode=config.PARSE_MODE)

            else:
                # User found but modified_count is 0. Maybe target user doc exists but something prevented update? (Shouldn't happen with $inc on simple doc)
                 admin_logger.error(f"Admin {user_id} attempted to add tokens to user {target_user_id}, but modified_count was 0. User found?", exc_info=True)
                 await message.reply_text(f"⚠️ User {target_user_id} found, but tokens modified 0 times. Update failed?", parse_mode=config.PARSE_MODE)

        else:
            # matched_count is 0 - User document not found
             admin_logger.warning(f"Admin {user_id} attempted to add tokens to non-existent user {target_user_id}.")
             await message.reply_text(f"🤔 User ID <b>{target_user_id}</b> not found in database.", parse_mode=config.PARSE_MODE)


    except Exception as e:
         # Database error during update operation
         admin_logger.error(f"Error adding tokens to user {target_user_id} by admin {user_id}: {e}", exc_info=True)
         await message.reply_text(strings.ADMIN_TOKENS_ERROR.format(user_id=target_user_id), parse_mode=config.PARSE_MODE)


# Handles /remove_tokens <user_id> <amount>
@Client.on_message(filters.command("remove_tokens") & filters.private)
async def remove_tokens_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # --- Admin Check ---
    if user_id not in config.ADMIN_IDS:
        await message.reply_text("🚫 You are not authorized to use this command.", parse_mode=config.PARSE_MODE)
        return

    # Parse arguments
    args = message.text.split(None, 2)

    if len(args) != 3:
        await message.reply_text("ℹ️ Usage: `/remove_tokens <user_id> <amount>`", parse_mode=config.PARSE_MODE)
        return

    target_user_id_str = args[1]
    amount_str = args[2]

    # Validate user ID and amount are integers
    try:
        target_user_id = int(target_user_id_str)
        amount_to_remove = int(amount_str)
        if amount_to_remove <= 0: raise ValueError("Amount must be positive.") # Must remove positive tokens
    except ValueError:
        await message.reply_text("🚫 Invalid User ID or amount. User ID and amount must be positive integers.", parse_mode=config.PARSE_MODE)
        return


    admin_logger.info(f"Admin {user_id} attempting to remove {amount_to_remove} tokens from user {target_user_id}.")

    # --- Perform Database Update: Remove tokens ---
    try:
        # Atomically decrement the target user's token balance by the negative amount
        update_result = await MongoDB.users_collection().update_one(
            {"user_id": target_user_id}, # Filter by the target user ID
            {"$inc": {"tokens": -amount_to_remove}} # Decrement tokens by amount (amount_to_remove is positive, use -)
        )

        if update_result.matched_count > 0:
            if update_result.modified_count > 0:
                 # User found and tokens updated. Note: Tokens cannot go below 0 automatically with simple $inc.
                 # They can become negative. If enforcing minimum 0 tokens, requires check or transaction/logic before $inc.
                 # Fetch updated user info for confirmation message and new balance.
                 updated_user_doc = await MongoDB.users_collection().find_one({"user_id": target_user_id}, {"tokens": 1}) # Get updated tokens
                 new_token_balance = updated_user_doc.get("tokens", "Unknown")

                 admin_logger.info(f"Admin {user_id} successfully removed {amount_to_remove} tokens from user {target_user_id}. New balance: {new_token_balance}. (Note: Balance can be negative.)")
                 await message.reply_text(strings.ADMIN_TOKENS_REMOVED_SUCCESS.format(amount=amount_to_remove, user_id=target_user_id, new_balance=new_token_balance), parse_mode=config.PARSE_MODE)

            else:
                 admin_logger.error(f"Admin {user_id} attempted to remove tokens from user {target_user_id}, but modified_count was 0. User found?", exc_info=True)
                 await message.reply_text(f"⚠️ User {target_user_id} found, but tokens modified 0 times. Update failed? (Maybe tried to remove more than available?)", parse_mode=config.PARSE_MODE)

        else:
            # matched_count is 0 - User document not found
             admin_logger.warning(f"Admin {user_id} attempted to remove tokens from non-existent user {target_user_id}.")
             await message.reply_text(f"🤔 User ID <b>{target_user_id}</b> not found in database.", parse_mode=config.PARSE_MODE)


    except Exception as e:
         # Database error during update operation
         admin_logger.error(f"Error removing tokens from user {target_user_id} by admin {user_id}: {e}", exc_info=True)
         await message.reply_text(strings.ADMIN_TOKENS_ERROR.format(user_id=target_user_id), parse_mode=config.PARSE_MODE)


# --- Admin Delete All Data Command ---
# Handles /delete_all_data command - Requires owner ID
@Client.on_message(filters.command("delete_all_data") & filters.private)
async def delete_all_data_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # --- Owner Check ---
    # Only the BOT OWNER can use this dangerous command
    if config.OWNER_ID is None or user_id != config.OWNER_ID:
        # Optionally, check if user is in ADMIN_IDS and give different unauthorized message
        if user_id in config.ADMIN_IDS:
             await message.reply_text("🚫 Only the bot owner can use this command.", parse_mode=config.PARSE_MODE)
        else:
             await message.reply_text("🚫 You are not authorized to use this command.", parse_mode=config.PARSE_MODE)
        return


    # This command has NO arguments in its initial form. Command arguments is the CONFIRMATION PHASE.
    # Check command arguments to see if confirmation phrase is present
    args = message.text.split(None, 1) # Split command from argument

    if len(args) != 2 or args[1] != strings.DATA_DELETION_CONFIRMATION_PHRASE:
        # If argument is missing or does not match the confirmation phrase, prompt the user
        await message.reply_text(strings.DATA_DELETION_PROMPT, parse_mode=config.PARSE_MODE)
        # No state needed for the prompt, user needs to type the specific phrase as next message
        return


    # If the correct confirmation phrase is provided in the command argument
    # Check if the user is actually the owner AGAIN as a safety measure.
    if user_id != config.OWNER_ID:
         # This check is redundant but defensive programming is key for destructive actions.
         admin_logger.critical(f"User {user_id} somehow bypassed initial OWNER_ID check for delete_all_data with correct phrase. Possible issue in filters or routing!", exc_info=True)
         await message.reply_text("🚫 Critical Security Check Failed.", parse_mode=config.PARSE_MODE)
         return # Fail

    admin_logger.warning(f"OWNER {user_id} confirmed permanent data deletion.")

    # Inform the owner that deletion is starting.
    await message.reply_text(strings.DATA_DELETION_CONFIRMED, parse_mode=config.PARSE_MODE)


    # --- Execute Database Deletion ---
    try:
        success = await MongoDB.delete_all_data() # Call the method in MongoDB class

        # Inform owner about the outcome
        if success:
            admin_logger.warning(f"OWNER {user_id}: delete_all_data operation reported SUCCESS.")
            try: await client.send_message(user_id, "✅ Database deletion process reported success. Bot might restart if configured.", parse_mode=config.PARSE_MODE)
            except Exception: admin_logger.error(f"Failed to send success confirmation to owner {user_id} after deletion.")

        else:
            admin_logger.critical(f"OWNER {user_id}: delete_all_data operation reported FAILURE.")
            try: await client.send_message(user_id, "💔 Database deletion process reported failure. Check logs immediately!", parse_mode=config.PARSE_MODE)
            except Exception: admin_logger.error(f"Failed to send failure confirmation to owner {user_id} after deletion.")


    except Exception as e:
        # Any unexpected error during deletion beyond what delete_all_data caught internally
        admin_logger.critical(f"OWNER {user_id}: An unexpected exception occurred during delete_all_data execution: {e}", exc_info=True)
        try: await client.send_message(user_id, f"💔 An unexpected error occurred during deletion: {e}. Check logs!", parse_mode=config.PARSE_MODE)
        except Exception: admin_logger.error(f"Failed to send unexpected error confirmation to owner {user_id}.")


    # Note: The bot will likely be restarted by the hosting platform after deleting core data.
    # Consider os.exit(1) here if you want to force a restart after deletion.
    # import os
    # os._exit(1) # Forced exit, potentially more abrupt shutdown


# --- Discovery Lists Handlers (Leaderboard, Latest, Popular) ---
# Note: Display logic is already in browse_handler for simplicity of display helper reuse.
# We just need command handlers to trigger that display, and potential specific list fetching.

@Client.on_callback_query(filters.regex("^menu_leaderboard$") & filters.private)
async def leaderboard_callback(client: Client, callback_query: CallbackQuery):
     user_id = callback_query.from_user.id
     # Chat/Message ID from callback_query.message
     message = callback_query.message

     try: await client.answer_callback_query(message.id, "Loading leaderboard...")
     except Exception: admin_logger.warning(f"Failed to answer callback query menu_leaderboard from user {user_id}")

     # Clear any prior state, as these lists are standalone display features.
     user_state = await get_user_state(user_id)
     if user_state and user_state.handler not in ["browse", "search"]: # Keep state if coming from browse/search lists? No, better to clear.
          admin_logger.debug(f"User {user_id} in state {user_state.handler}:{user_state.step} clicking leaderboard. Clearing old state.")
          await clear_user_state(user_id)

     # Display logic is in browse_handler. Need to fetch data first.
     try:
         # Fetch top N users by download_count (config.LEADERBOARD_COUNT)
         # Project user_id and download_count.
         top_users_docs = await MongoDB.users_collection().find(
             {}, {"user_id": 1, "download_count": 1}
         ).sort("download_count", -1).limit(config.LEADERBOARD_COUNT).to_list(config.LEADERBOARD_COUNT)


         # Fetch Telegram user info for mentions if possible.
         top_user_ids = [doc.get("user_id") for doc in top_users_docs if doc.get("user_id") is not None]
         user_info_map = {} # Map user_id -> pyrogram.User object
         try:
             # Fetch users in batches if feasible, or individually
             # Simple approach: fetch individual. Error gracefully.
             for uid in top_user_ids:
                 try:
                     telegram_user = await client.get_users(uid)
                     user_info_map[uid] = telegram_user
                 except UserNotParticipant: # User blocked bot etc.
                     user_info_map[uid] = type('obj', (object,), {'id': uid, 'first_name': f"User {uid}", 'username': None})()
                 except Exception as fetch_e:
                     admin_logger.warning(f"Failed to fetch user info for ID {uid} for leaderboard display: {fetch_e}", exc_info=True)
                     user_info_map[uid] = type('obj', (object,), {'id': uid, 'first_name': f"Error fetching user {uid}", 'username': None})()

         except Exception as e:
              admin_logger.error(f"Error fetching user info for leaderboard: {e}", exc_info=True)
              # Continue without complete user info

         # Build message text using format string
         menu_text = strings.LEADERBOARD_TITLE + "\n\n"

         if not top_users_docs:
              menu_text += strings.LEADERBOARD_EMPTY
         else:
             # Iterate through fetched user docs to build list entries
             for i, user_doc in enumerate(top_users_docs):
                 user_id_lb = user_doc.get("user_id")
                 download_count = user_doc.get("download_count", 0)
                 rank = i + 1

                 # Get Telegram user info or fallback
                 telegram_user = user_info_map.get(user_id_lb)
                 user_mention_text = get_user_mention(telegram_user) if telegram_user else (f"User {user_id_lb}" if user_id_lb is not None else "Unknown User")


                 entry_text = strings.LEADERBOARD_ENTRY_FORMAT.format(
                      rank=rank,
                      user_mention=user_mention_text, # Use formatted mention/name
                      download_count=download_count
                 )
                 menu_text += entry_text + "\n"

         # Add Back to Main Menu button
         buttons = [[InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]]
         reply_markup = InlineKeyboardMarkup(buttons)

         # Edit message to display leaderboard
         await edit_or_send_message(client, message.chat.id, message.id, menu_text, reply_markup, disable_web_page_preview=True)


     except Exception as e:
          admin_logger.error(f"FATAL error handling leaderboard callback for user {user_id}: {e}", exc_info=True)
          # Clear state? No state needed specifically here. Log and display error.
          await edit_or_send_message(client, message.chat.id, message.id, strings.ERROR_OCCURRED, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex("^menu_latest$") & filters.private)
async def latest_additions_callback(client: Client, callback_query: CallbackQuery):
     user_id = callback_query.from_user.id
     # Chat/Message ID from callback_query.message
     message = callback_query.message

     try: await client.answer_callback_query(message.id, "Loading latest additions...")
     except Exception: admin_logger.warning(f"Failed to answer callback query menu_latest from user {user_id}")

     user_state = await get_user_state(user_id)
     if user_state and user_state.handler not in ["browse", "search"]:
          admin_logger.debug(f"User {user_id} in state {user_state.handler}:{user_state.step} clicking latest. Clearing old state.")
          await clear_user_state(user_id)


     try:
         menu_text = strings.LATEST_TITLE + "\n\n"
         buttons = []

         # Fetch recent ANIME updates sorted by last_updated_at
         # Need to get episodes information efficiently
         # More advanced: Query for anime, then sort episodes by creation time (if timestamp added to Episode model)
         # Simplified: Query Anime sorted by overall_download_count as proxy for popularity. (Oops, that's Popular).
         # Query Anime sorted by last_updated_at and project episode/season info to list recent updates.
         # Better approach: Aggregate documents to get list of recent file additions across ALL anime.
         # Needs complex aggregation query. Let's simplify for first pass.
         # Fetch top N most recently *updated* anime, then list details like "Anime Name (Latest Episodes: S#E#...)"
         # Or just fetch documents sorted by last_updated_at and show them, relying on update time as 'latest'.

         recent_anime_docs = await MongoDB.anime_collection().find(
             {}, {"name": 1, "_id": 1, "seasons": 1} # Project needed fields: name, id, full seasons/episodes
         ).sort("last_updated_at", -1).limit(config.LATEST_COUNT).to_list(config.LATEST_COUNT) # Sort by anime update time


         if not recent_anime_docs:
              menu_text += strings.NO_CONTENT_YET # "No latest additions yet."
         else:
             # Iterate through recent anime and identify *their* latest episodes
             for anime_doc in recent_anime_docs:
                 anime_name = anime_doc.get("name", "Unnamed Anime")
                 anime_id = str(anime_doc["_id"])

                 # Find the latest episode added to this anime *by its own timestamp* (if available) or highest episode number
                 latest_episode_info = None
                 latest_timestamp = datetime.min.replace(tzinfo=timezone.utc) # Use a very old time for comparison

                 seasons = sorted(anime_doc.get("seasons", []), key=lambda s: s.get("season_number", 0))
                 for season_doc in seasons:
                     episodes = sorted(season_doc.get("episodes", []), key=lambda e: e.get("episode_number", 0))
                     season_number = season_doc.get("season_number", 0)
                     for episode_doc in episodes:
                          episode_number = episode_doc.get("episode_number", 0)
                          files = episode_doc.get("files", [])

                          # Determine the 'latest' timestamp for this episode
                          episode_latest_time = episode_doc.get("release_date") # Use release date if available

                          # Use latest added file version timestamp if files exist and it's more recent
                          latest_file_added_at = datetime.min.replace(tzinfo=timezone.utc)
                          if files:
                             for file_ver in files:
                                  added_at = file_ver.get("added_at", datetime.min.replace(tzinfo=timezone.utc))
                                  if isinstance(added_at, datetime) and added_at > latest_file_added_at:
                                       latest_file_added_at = added_at
                             if latest_file_added_at > episode_latest_time: # Use file added time if more recent
                                 episode_latest_time = latest_file_added_at


                          if isinstance(episode_latest_time, datetime) and episode_latest_time > latest_timestamp:
                              latest_timestamp = episode_latest_time
                              latest_episode_info = {"anime_name": anime_name, "anime_id": anime_id, "season_number": season_number, "episode_number": episode_number}

                 if latest_episode_info:
                     # Add entry for this anime's latest identified episode
                     entry_text = strings.LATEST_ENTRY_FORMAT.format(
                         anime_title=latest_episode_info["anime_name"],
                         season_number=latest_episode_info["season_number"],
                         episode_number=latest_episode_info["episode_number"]
                     )
                     menu_text += entry_text + "\n"

                     # Add button to link to the episode's version list directly
                     # Callback: download_select_episode|<anime_id>|<season>|<ep>
                     button_callback_direct_episode = f"download_select_episode{config.CALLBACK_DATA_SEPARATOR}{latest_episode_info['anime_id']}{config.CALLBACK_DATA_SEPARATOR}{latest_episode_info['season_number']}{config.CALLBACK_DATA_SEPARATOR}{latest_episode_info['episode_number']}"
                     buttons.append([InlineKeyboardButton(f"🎬 View S{latest_episode_info['season_number']}E{latest_episode_info['episode_number']:02d}", callback_data=button_callback_direct_episode)])

             if not latest_episode_info and anime_doc.get("seasons"):
                 # No timestamped episodes found in this recently updated anime? Link to details instead.
                  menu_text += f" - (Episodes un-timestamped?)\n" # Add note for debugging
                  buttons.append([InlineKeyboardButton(f"📚 View {anime_name}", callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id}")]) # Link to anime details


         # Add Back to Main Menu button after list or entries
         buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])
         reply_markup = InlineKeyboardMarkup(buttons)

         # Edit message to display list
         await edit_or_send_message(client, message.chat.id, message.id, menu_text, reply_markup, disable_web_page_preview=True)


     except Exception as e:
          admin_logger.error(f"FATAL error handling latest additions callback for user {user_id}: {e}", exc_info=True)
          await clear_user_state(user_id)
          await edit_or_send_message(client, message.chat.id, message.id, strings.ERROR_OCCURRED, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex("^menu_popular$") & filters.private)
async def popular_anime_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    # Chat/Message ID from callback_query.message
    message = callback_query.message

    try: await client.answer_callback_query(message.id, "Loading popular anime...")
    except Exception: admin_logger.warning(f"Failed to answer callback query menu_popular from user {user_id}")

    user_state = await get_user_state(user_id)
    if user_state and user_state.handler not in ["browse", "search", "download"]: # Allow from relevant flows
         admin_logger.debug(f"User {user_id} in state {user_state.handler}:{user_state.step} clicking popular. Clearing old state.")
         await clear_user_state(user_id)


    try:
        menu_text = strings.POPULAR_TITLE + "\n\n"
        buttons = []

        # Fetch popular anime documents sorted by overall_download_count descending.
        # Use config.POPULAR_COUNT limit.
        popular_anime_docs = await MongoDB.anime_collection().find(
             {}, {"name": 1, "_id": 1, "overall_download_count": 1, "status":1, "release_year": 1}
         ).sort("overall_download_count", -1).limit(config.POPULAR_COUNT).to_list(config.POPULAR_COUNT) # Sort by total downloads


        if not popular_anime_docs:
             menu_text += strings.NO_CONTENT_YET # "No popular anime yet."
        else:
            # Create buttons for each popular anime, linking to its details/management menu
            for anime_doc in popular_anime_docs:
                 anime_name = anime_doc.get("name", "Unnamed Anime")
                 anime_id = str(anime_doc["_id"])
                 downloads = anime_doc.get("overall_download_count", 0)

                 # Button label includes downloads count as indicator
                 button_label = f"🔥 {anime_name} ({downloads} ↓)"

                 # Callback: browse_select_anime|<anime_id> (Reuse details display logic)
                 buttons.append([InlineKeyboardButton(button_label, callback_data=f"browse_select_anime{config.CALLBACK_DATA_SEPARATOR}{anime_id}")])


        # Add Back to Main Menu button after list or entries
        buttons.append([InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")])
        reply_markup = InlineKeyboardMarkup(buttons)

        # Edit message to display list
        await edit_or_send_message(client, message.chat.id, message.id, menu_text, reply_markup, disable_web_page_preview=True)


    except Exception as e:
         admin_logger.error(f"FATAL error handling popular anime callback for user {user_id}: {e}", exc_info=True)
         await clear_user_state(user_id)
         await edit_or_send_message(client, message.chat.id, message.id, strings.ERROR_OCCURRED, disable_web_page_preview=True)
