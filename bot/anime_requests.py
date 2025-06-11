# bot/anime_requests.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler # For potential request confirmation flow
from telegram.constants import ParseMode
from urllib.parse import unquote_plus # To decode anime title from callback_data

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance
from .core_handlers import check_user_or_add

logger = logging.getLogger(__name__)

# Conversation states for free user request confirmation (if made more complex)
# For now, it's a simple one-step confirmation or direct request.
# (No conversation handler defined here yet, but states for potential expansion)
CONFIRM_FREE_REQUEST = range(1)


# --- User Command to Request Anime (Premium) ---
async def request_anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /request [Anime Title] for premium users."""
    user = update.effective_user
    logger.info(f"Request command from premium user {user.id} ({user.first_name}), args: {context.args}")

    user_db_doc = await check_user_or_add(update, context)
    if not user_db_doc: return

    if not user_db_doc.get("premium_status", False):
        await update.message.reply_html(f"{strings.EMOJI_ERROR} The <code>/request</code> command is for {strings.EMOJI_PREMIUM}Premium users only. You can request anime via the button after a search if it's not found (costs tokens).")
        return

    if not context.args:
        await update.message.reply_html("Please provide the English title of the anime you want to request.\n<b>Usage:</b> <code>/request [Anime Title]</code>")
        return

    anime_title_requested = " ".join(context.args)

    # Directly process and send premium user's request
    await process_and_send_request(update, context, user_db_doc, anime_title_requested)


# --- Callback for Free User Request (from Search "No Results") ---
async def handle_request_anime_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_title_from_search: str) -> None:
    """
    Handles when a free user clicks the 'Request "Anime Title"?' button
    after a search yields no results.
    `anime_title_from_search` is decoded from callback_data.
    """
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    logger.info(f"Request callback for anime '{anime_title_from_search}' by free user {user.id}")

    user_db_doc = await check_user_or_add(update, context)
    if not user_db_doc: return

    if user_db_doc.get("premium_status", False): # Should not happen if button shown to free user, but check
        await process_and_send_request(update, context, user_db_doc, anime_title_from_search)
        return

    # Free user: Check token cost
    token_cost = settings.FREE_USER_REQUEST_TOKEN_COST
    current_tokens = user_db_doc.get("download_tokens", 0)

    if current_tokens < token_cost:
        await query.edit_message_text(
            text=strings.NOT_ENOUGH_TOKENS.format(required_tokens=token_cost, current_tokens=current_tokens) +
                 f"\n\nEarn more tokens via /gen_tokens or go /premium for free requests!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]) # Or back to search
        )
        return

    # Ask for confirmation (modifies the existing message)
    # Callback format: "req_confirm_yes_THE_TITLE" or "req_confirm_no"
    confirm_text = strings.REQUEST_PROMPT_FREE_CONFIRM.format(anime_title=anime_title_from_search, token_cost=token_cost)
    yes_callback = f"req_conf_yes_{anime_title_from_search}" # Title might need encoding if it has special chars
    no_callback = "req_conf_no" # Generic no, or specific to this anime: req_conf_no_{anime_title_from_search}

    keyboard = [
        [InlineKeyboardButton(strings.BTN_CONFIRM_REQUEST, callback_data=yes_callback)],
        [InlineKeyboardButton(strings.BTN_CANCEL_REQUEST, callback_data=no_callback)]
    ]
    await query.edit_message_text(text=confirm_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    # This doesn't use ConversationHandler; next action comes via new callbacks.


# --- Confirmation Handling for Free User Request ---
async def handle_free_request_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 'Yes' or 'No' from free user request confirmation."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    callback_data = query.data

    user_db_doc = await check_user_or_add(update, context)
    if not user_db_doc: return

    if callback_data.startswith("req_conf_yes_"):
        anime_title_to_request = callback_data.split("req_conf_yes_", 1)[1]
        anime_title_to_request = unquote_plus(anime_title_to_request) # Decode if encoded

        token_cost = settings.FREE_USER_REQUEST_TOKEN_COST
        current_tokens = user_db_doc.get("download_tokens", 0)

        if current_tokens < token_cost: # Double check tokens
            await query.edit_message_text(
                text=strings.NOT_ENOUGH_TOKENS.format(required_tokens=token_cost, current_tokens=current_tokens),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]])
            )
            return

        # Deduct tokens
        await anidb.update_user_tokens(user.id, -token_cost)
        await query.edit_message_text(text=strings.TOKENS_DEDUCTED.format(tokens_cost=token_cost) + "\n" + strings.EMOJI_LOADING + " Submitting your request...") # Clear buttons temporarily
        
        # Process and send the request
        await process_and_send_request(update, context, user_db_doc, anime_title_to_request, from_callback_edit_msg=True)

    elif callback_data == "req_conf_no": # Or "req_conf_no_{anime_title}"
        await query.edit_message_text(text=strings.OPERATION_CANCELLED + " Anime request cancelled.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        # Optionally, could take them back to search input or search results.
    else:
        logger.warning(f"Unhandled free request confirmation callback: {callback_data}")


# --- Core Logic to Process and Send Request to Admin Channel ---
async def process_and_send_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_db_doc: dict, anime_title: str, from_callback_edit_msg: bool = False):
    """
    Formats the request and sends it to the admin request channel.
    Notifies the user.
    """
    user = update.effective_user
    is_premium = user_db_doc.get("premium_status", False)

    # Log to DB (optional, if you want detailed tracking beyond channel)
    # request_db_id = await anidb.log_anime_request(user.id, user.first_name, anime_title, is_premium)
    # For now, let's simplify and rely on channel log primarily.
    request_db_id_placeholder_for_cb = f"{user.id}_{datetime.utcnow().timestamp()}" # Unique ID for callback if no DB ID

    request_text_to_channel = strings.REQUEST_SENT_TO_ADMIN_CHANNEL.format(
        anime_title=anime_title,
        user_id=user.id,
        user_first_name=user.first_name,
        is_premium_status="Yes" if is_premium else "No"
    )

    # Admin action buttons for the request channel message
    # Callback data needs user_id and ideally a unique request identifier (e.g. from DB, or anime_title)
    # "admin_req_ACTION_USERID_REQUESTIDENTIFIER"
    # REQUESTIDENTIFIER can be anime_title (URL encoded) or a generated ID
    encoded_title = quote_plus(anime_title)
    admin_keyboard = [
        [
            InlineKeyboardButton("✅ Fulfilled", callback_data=f"admin_req_fulfill_{user.id}_{encoded_title}"),
            InlineKeyboardButton("⚠️ Unavailable", callback_data=f"admin_req_unavailable_{user.id}_{encoded_title}")
        ],
        [
            InlineKeyboardButton("⏳ Not Released", callback_data=f"admin_req_notreleased_{user.id}_{encoded_title}"),
            InlineKeyboardButton("🗑️ Ignore", callback_data=f"admin_req_ignore_{user.id}_{encoded_title}")
        ]
    ]
    reply_markup_admin = InlineKeyboardMarkup(admin_keyboard)

    try:
        if settings.REQUEST_CHANNEL_ID:
            await context.bot.send_message(
                chat_id=settings.REQUEST_CHANNEL_ID,
                text=request_text_to_channel,
                reply_markup=reply_markup_admin,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Request for '{anime_title}' by {user.id} sent to request channel.")
        else:
            logger.warning("REQUEST_CHANNEL_ID not set. Cannot forward anime request.")
            # Notify admin directly if channel not set? Or just fail silently for user.
            # For now, we assume user gets success message even if channel fails, unless we check return.

        # Notify user of success
        user_success_msg = strings.REQUEST_SENT_SUCCESS.format(anime_title=anime_title)
        if from_callback_edit_msg and update.callback_query: # From a free user request confirmation
             await update.callback_query.edit_message_text(text=user_success_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        elif update.message: # From /request command by premium user
             await update.message.reply_html(text=user_success_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))

    except Exception as e:
        logger.error(f"Error sending request to channel or notifying user: {e}", exc_info=True)
        err_msg = f"{strings.EMOJI_ERROR} Failed to submit your request due to a server error. Please try again later."
        if from_callback_edit_msg and update.callback_query:
            await update.callback_query.edit_message_text(text=err_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        elif update.message:
            await update.message.reply_html(text=err_msg)


# --- Admin Handling of Request Channel Callbacks ---
async def handle_admin_request_channel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles callbacks from admins in the request channel."""
    query = update.callback_query
    admin_user = update.effective_user # Admin who clicked the button

    if admin_user.id not in settings.ADMIN_IDS:
        await query.answer("This action is for Admins only.", show_alert=True)
        return

    await query.answer() # Acknowledge callback immediately
    callback_data = query.data # e.g., "admin_req_fulfill_TARGETUSERID_ANIMETITLEENCODED"
    
    parts = callback_data.split("_")
    action = parts[2]
    target_user_id = int(parts[3])
    anime_title_encoded = "_".join(parts[4:]) # In case title had underscores after encoding
    anime_title_decoded = unquote_plus(anime_title_encoded)

    logger.info(f"Admin {admin_user.id} chose action '{action}' for request: User={target_user_id}, Title='{anime_title_decoded}'")

    user_notification_message = None
    admin_channel_feedback_message_suffix = ""

    if action == "fulfill":
        user_notification_message = strings.USER_NOTIF_REQUEST_FULFILLED.format(anime_title=anime_title_decoded)
        admin_channel_feedback_message_suffix = strings.REQUEST_ADMIN_REPLY_FULFILLED.format(admin_name=admin_user.first_name)
    elif action == "unavailable":
        user_notification_message = strings.USER_NOTIF_REQUEST_UNAVAILABLE.format(anime_title=anime_title_decoded)
        admin_channel_feedback_message_suffix = strings.REQUEST_ADMIN_REPLY_UNAVAILABLE.format(admin_name=admin_user.first_name)
    elif action == "notreleased":
        user_notification_message = strings.USER_NOTIF_REQUEST_NOT_RELEASED.format(anime_title=anime_title_decoded)
        admin_channel_feedback_message_suffix = strings.REQUEST_ADMIN_REPLY_NOT_RELEASED.format(admin_name=admin_user.first_name)
    elif action == "ignore":
        # No notification to user for "ignore"
        admin_channel_feedback_message_suffix = strings.REQUEST_ADMIN_REPLY_IGNORED.format(admin_name=admin_user.first_name)
    else:
        logger.warning(f"Unknown admin request action: {action}")
        return

    # Send notification to the original requesting user (if action isn't 'ignore')
    if user_notification_message:
        try:
            await context.bot.send_message(chat_id=target_user_id, text=user_notification_message, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send request update notification to user {target_user_id}: {e}")
            admin_channel_feedback_message_suffix += f"\n{strings.EMOJI_ERROR} (Failed to notify user)"

    # Edit the message in the admin request channel to show the action taken
    original_message_text = query.message.text_html # Get original text with HTML
    new_text_for_admin_channel = f"{original_message_text}\n\n---\n<b>Action Taken:</b> {admin_channel_feedback_message_suffix}"
    
    try: # Remove the inline keyboard from the message in the request channel
        await query.edit_message_text(text=new_text_for_admin_channel, reply_markup=None, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to edit message in request channel: {e}")
        # Could be "message is not modified" if admin clicks same button twice quickly.
        # Or if the message is too old for editing.

    # Optional: Update status in DB if requests are logged there
    # request_db_id = ... (if you have it from callback_data or original message)
    # if request_db_id:
    #    await anidb.update_request_status(request_db_id, new_status=action.capitalize(), admin_name=admin_user.first_name)
