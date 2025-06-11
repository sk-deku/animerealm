# bot/admin_cmds.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler, # For the broadcast conversation entry
    MessageHandler,
    filters # For broadcast message input
)
from telegram.constants import ParseMode
from datetime import datetime, timedelta
import pytz

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance
from .core_handlers import reply_with_main_menu, check_user_or_add # For convenience

logger = logging.getLogger(__name__)

# Conversation states for broadcast
BROADCAST_MESSAGE, BROADCAST_CONFIRM = range(2)

# --- Helper to get target user ---
async def get_target_user_doc_from_command(command_args: list, context: ContextTypes.DEFAULT_TYPE) -> tuple[dict | None, int | None]:
    """
    Parses command args to get target user ID or username.
    Returns (user_doc, target_user_id)
    """
    if not command_args:
        return None, None

    identifier_str = command_args[0]
    target_user_id_int = None
    user_doc = None

    try:
        target_user_id_int = int(identifier_str)
        user_doc = await anidb.get_user(target_user_id_int)
    except ValueError: # Identifier is likely a username
        # This requires storing usernames and searching by them, which we do
        # but PTB context doesn't directly give user_id from username without more interaction or DB query
        # For simplicity with direct commands, let's rely on admins using user ID mostly
        # Or you could iterate/query users collection by username (can be slow without index)
        # temp_user_doc = await anidb.users_collection.find_one({"username": identifier_str.lstrip('@')}) # Basic example
        # For this version, let's recommend using user ID.
        logger.warning(f"Admin command tried to use username '{identifier_str}'. User ID is preferred for direct commands.")
        # If you want to support usernames effectively, you'd need a robust lookup
        # users = await anidb.users_collection.find({"username": identifier_str.lstrip('@')}).to_list(length=1)
        # user_doc = users[0] if users else None
        # if user_doc:
        #     target_user_id_int = user_doc["telegram_id"]
        # else:
        pass # Stick to ID for now for simplicity in this helper
        
    return user_doc, target_user_id_int


# --- Admin Panel Main (Placeholder, triggered by callback from core_handlers e.g.) ---
async def admin_panel_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the main admin panel with buttons for various actions."""
    query = update.callback_query
    user = update.effective_user

    if user.id not in settings.ADMIN_IDS:
        if query: await query.answer("Access Denied!", show_alert=True)
        return

    admin_panel_text = f"{strings.EMOJI_ADMIN} <b>Admin Control Panel</b> {strings.EMOJI_ADMIN}\n\nSelect an action:"
    keyboard = [
        [InlineKeyboardButton("🛠️ Manage Content", callback_data="admin_cm_start")], # Triggers content_manager Conversation
        [
            InlineKeyboardButton("➕ Grant Premium", callback_data="admin_action_grant_prem_prompt"),
            InlineKeyboardButton("🚫 Revoke Premium", callback_data="admin_action_revoke_prem_prompt")
        ],
        [
            InlineKeyboardButton("🪙 Add Tokens", callback_data="admin_action_add_tokens_prompt"),
            InlineKeyboardButton("➖ Remove Tokens", callback_data="admin_action_remove_tokens_prompt")
        ],
        [
            InlineKeyboardButton("ℹ️ User Info", callback_data="admin_action_user_info_prompt"),
            InlineKeyboardButton("📊 Bot Stats", callback_data="admin_action_bot_stats")
        ],
        [InlineKeyboardButton("📣 Broadcast Message", callback_data="admin_action_broadcast_start")],
        [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text=admin_panel_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else: # Should ideally always be from callback
        await update.message.reply_html(text=admin_panel_text, reply_markup=reply_markup)


# --- Premium Management ---
async def grant_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not context.args or len(context.args) < 2:
        await update.message.reply_html("<b>Usage:</b> <code>/grant_premium [user_id] [duration_days]</code>\nExample: <code>/grant_premium 123456789 30</code> for 30 days.")
        return

    target_user_doc, target_user_id = await get_target_user_doc_from_command([context.args[0]], context)

    if not target_user_doc:
        await update.message.reply_html(strings.USER_NOT_FOUND_FOR_ADMIN_ACTION.format(identifier=context.args[0]))
        return

    try:
        duration_days = int(context.args[1])
        if duration_days <= 0:
            raise ValueError("Duration must be positive.")
    except ValueError:
        await update.message.reply_html("Invalid duration. Please provide a positive number of days.")
        return

    success, expiry_date = await anidb.grant_premium(target_user_id, duration_days)
    if success and expiry_date:
        expiry_date_str = expiry_date.strftime("%d %b %Y, %H:%M UTC")
        admin_msg = strings.PREMIUM_GRANTED_ADMIN.format(days=duration_days, user_id=target_user_id, expiry_date=expiry_date_str)
        await update.message.reply_html(admin_msg)

        # Notify user
        try:
            user_notif_msg = strings.PREMIUM_GRANTED_USER.format(days=duration_days)
            await context.bot.send_message(chat_id=target_user_id, text=user_notif_msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send premium granted notification to {target_user_id}: {e}")
            await update.message.reply_html(f"{strings.EMOJI_ERROR} User notified of premium, but notification failed to send to them directly.")

        # Log to USER_LOGS_CHANNEL
        if settings.USER_LOGS_CHANNEL_ID:
            log_msg = strings.LOG_PREMIUM_GRANTED.format(
                user_id=target_user_id, user_first_name=target_user_doc.get("first_name", "N/A"),
                days=duration_days, admin_id=user.id, admin_name=user.first_name
            )
            await context.bot.send_message(settings.USER_LOGS_CHANNEL_ID, log_msg, parse_mode=ParseMode.HTML)

    else:
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Failed to grant premium to user <code>{target_user_id}</code>.")

async def revoke_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not context.args:
        await update.message.reply_html("<b>Usage:</b> <code>/revoke_premium [user_id]</code>")
        return

    target_user_doc, target_user_id = await get_target_user_doc_from_command(context.args, context)

    if not target_user_doc:
        await update.message.reply_html(strings.USER_NOT_FOUND_FOR_ADMIN_ACTION.format(identifier=context.args[0]))
        return

    success = await anidb.revoke_premium(target_user_id)
    if success:
        admin_msg = strings.PREMIUM_REVOKED_ADMIN.format(user_id=target_user_id)
        await update.message.reply_html(admin_msg)
        try:
            await context.bot.send_message(chat_id=target_user_id, text=strings.PREMIUM_REVOKED_USER, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send premium revoked notification to {target_user_id}: {e}")

        if settings.USER_LOGS_CHANNEL_ID:
            log_msg = strings.LOG_PREMIUM_REVOKED.format(
                user_id=target_user_id, user_first_name=target_user_doc.get("first_name", "N/A"),
                admin_id=user.id, admin_name=user.first_name
            )
            await context.bot.send_message(settings.USER_LOGS_CHANNEL_ID, log_msg, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Failed to revoke premium for user <code>{target_user_id}</code> or they were not premium.")


# --- Token Management ---
async def add_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not context.args or len(context.args) < 2:
        await update.message.reply_html("<b>Usage:</b> <code>/add_tokens [user_id] [amount]</code>")
        return

    target_user_doc, target_user_id = await get_target_user_doc_from_command([context.args[0]], context)
    if not target_user_doc:
        await update.message.reply_html(strings.USER_NOT_FOUND_FOR_ADMIN_ACTION.format(identifier=context.args[0]))
        return

    try:
        amount = int(context.args[1])
        if amount <= 0: raise ValueError("Amount must be positive for adding.")
    except ValueError:
        await update.message.reply_html("Invalid amount. Please provide a positive number.")
        return

    success = await anidb.update_user_tokens(target_user_id, amount)
    if success:
        updated_target_user_doc = await anidb.get_user(target_user_id) # Fetch again to get new balance
        new_balance = updated_target_user_doc.get("download_tokens", "N/A") if updated_target_user_doc else "N/A"
        admin_msg = strings.TOKENS_ADJUSTED_ADMIN.format(user_id=target_user_id, new_balance=new_balance)
        await update.message.reply_html(admin_msg)
        try:
            await context.bot.send_message(chat_id=target_user_id, text=strings.TOKENS_ADJUSTED_USER.format(new_balance=new_balance), parse_mode=ParseMode.HTML)
        except Exception: pass # Ignore if user blocked bot etc.
    else:
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Failed to add tokens for user <code>{target_user_id}</code>.")

async def remove_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not context.args or len(context.args) < 2:
        await update.message.reply_html("<b>Usage:</b> <code>/remove_tokens [user_id] [amount_to_remove]</code>")
        return

    target_user_doc, target_user_id = await get_target_user_doc_from_command([context.args[0]], context)
    if not target_user_doc:
        await update.message.reply_html(strings.USER_NOT_FOUND_FOR_ADMIN_ACTION.format(identifier=context.args[0]))
        return

    try:
        amount_to_remove = int(context.args[1])
        if amount_to_remove <= 0: raise ValueError("Amount must be positive for removing.")
    except ValueError:
        await update.message.reply_html("Invalid amount. Please provide a positive number.")
        return

    current_tokens = target_user_doc.get("download_tokens", 0)
    if amount_to_remove > current_tokens:
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Cannot remove {amount_to_remove} tokens. User only has {current_tokens}.")
        return

    success = await anidb.update_user_tokens(target_user_id, -amount_to_remove) # Use negative for removal
    if success:
        updated_target_user_doc = await anidb.get_user(target_user_id)
        new_balance = updated_target_user_doc.get("download_tokens", "N/A") if updated_target_user_doc else "N/A"
        admin_msg = strings.TOKENS_ADJUSTED_ADMIN.format(user_id=target_user_id, new_balance=new_balance)
        await update.message.reply_html(admin_msg)
        try:
            await context.bot.send_message(chat_id=target_user_id, text=strings.TOKENS_ADJUSTED_USER.format(new_balance=new_balance), parse_mode=ParseMode.HTML)
        except Exception: pass
    else:
        await update.message.reply_html(f"{strings.EMOJI_ERROR} Failed to remove tokens for user <code>{target_user_id}</code>.")


# --- User Information ---
async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_html("<b>Usage:</b> <code>/user_info [user_id]</code>")
        return

    target_user_doc, target_user_id = await get_target_user_doc_from_command(context.args, context)

    if not target_user_doc:
        await update.message.reply_html(strings.USER_NOT_FOUND_FOR_ADMIN_ACTION.format(identifier=context.args[0]))
        return

    username_str = f"@{target_user_doc['username']}" if target_user_doc.get("username") else "N/A"
    last_name_str = target_user_doc.get("last_name", "") # Older PTB versions might not provide this directly from User obj
    
    premium_expiry_str = "N/A"
    if target_user_doc.get("premium_status") and target_user_doc.get("premium_expiry_date"):
        prem_expiry = target_user_doc["premium_expiry_date"]
        # Convert to IST for display (example) or keep UTC
        # ist = pytz.timezone('Asia/Kolkata')
        # local_expiry_time = prem_expiry.astimezone(ist)
        # premium_expiry_str = local_expiry_time.strftime("%d %b %Y, %I:%M %p %Z")
        premium_expiry_str = prem_expiry.strftime("%d %b %Y, %H:%M UTC")


    info_text = strings.ADMIN_USER_INFO_HEADER.format(user_id=target_user_id)
    info_text += strings.ADMIN_USER_INFO_DETAILS.format(
        first_name=target_user_doc.get("first_name", "N/A"),
        last_name_optional=last_name_str,
        username_optional=username_str,
        user_id=target_user_id,
        tokens=target_user_doc.get("download_tokens", 0),
        is_premium=target_user_doc.get("premium_status", False),
        premium_expiry_date_str=premium_expiry_str,
        join_date_str=target_user_doc.get("join_date", datetime.min).strftime("%d %b %Y"),
        last_active_date_str=target_user_doc.get("last_active_date", datetime.min).strftime("%d %b %Y, %H:%M UTC"),
        watchlist_count=len(target_user_doc.get("watchlist", []))
    )
    await update.message.reply_html(info_text)

# --- Broadcast Message (Conversation) ---
async def broadcast_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the broadcast conversation: asks for the message."""
    query = update.callback_query
    msg_text = "📣 Okay, send me the message you want to broadcast to all users. Use HTML for formatting."

    if query:
        await query.answer()
        await query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="admin_broadcast_cancel")]]))
    else:
        await update.message.reply_html(msg_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_CANCEL_OPERATION, callback_data="admin_broadcast_cancel")]]))
    return BROADCAST_MESSAGE

async def broadcast_get_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the broadcast message and asks for confirmation."""
    message_to_broadcast = update.message.text_html # Get HTML formatted message
    context.user_data["broadcast_message_content"] = message_to_broadcast

    confirm_text = strings.BROADCAST_CONFIRM.format(message=message_to_broadcast)
    keyboard = [
        [InlineKeyboardButton(strings.BTN_BROADCAST_SEND, callback_data="admin_broadcast_send_confirm")],
        [InlineKeyboardButton(strings.BTN_BROADCAST_CANCEL, callback_data="admin_broadcast_cancel_confirm")]
    ]
    await update.message.reply_html(text=confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return BROADCAST_CONFIRM

async def broadcast_send_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends the broadcast message to all users after admin confirmation."""
    query = update.callback_query
    await query.answer(text=strings.BROADCAST_STARTED)
    await query.edit_message_text(text=strings.BROADCAST_STARTED, reply_markup=None)

    message_content = context.user_data.pop("broadcast_message_content", None)
    if not message_content:
        await context.bot.send_message(query.from_user.id, f"{strings.EMOJI_ERROR} Broadcast message not found. Please start again.")
        return ConversationHandler.END

    all_user_ids = await anidb.get_all_user_ids() # Add filters here if needed (e.g. active users)
    
    successful_sends = 0
    failed_sends = 0

    # Sending messages one by one can be slow and hit rate limits.
    # For large user bases, consider background tasks or sending in batches with delays.
    for user_id in all_user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_content, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            successful_sends += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user_id}: {e}")
            failed_sends += 1
        await asyncio.sleep(0.1) # Small delay to avoid hitting limits too quickly

    completion_message = strings.BROADCAST_COMPLETE.format(success_count=successful_sends, failure_count=failed_sends)
    await context.bot.send_message(query.from_user.id, completion_message)
    logger.info(f"Broadcast completed: Sent to {successful_sends}, Failed for {failed_sends}")
    return ConversationHandler.END

async def broadcast_cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the broadcast conversation."""
    query = update.callback_query
    context.user_data.pop("broadcast_message_content", None)
    if query:
        await query.answer()
        await query.edit_message_text(strings.OPERATION_CANCELLED + " Broadcast cancelled.")
        await reply_with_main_menu(update, context) # Or admin panel if exists
    else: # Should not happen if flow is correct
        await update.message.reply_html(strings.OPERATION_CANCELLED + " Broadcast cancelled.")
    return ConversationHandler.END

# Function to get the broadcast conversation handler (to be added in main.py)
def get_broadcast_conv_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", broadcast_start_command, filters=filters.User(settings.ADMIN_IDS)),
            CallbackQueryHandler(broadcast_start_command, pattern="^admin_action_broadcast_start$")
        ],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_get_message)],
            BROADCAST_CONFIRM: [
                CallbackQueryHandler(broadcast_send_confirmed, pattern="^admin_broadcast_send_confirm$"),
            ]
        },
        fallbacks=[
            CallbackQueryHandler(broadcast_cancel_conv, pattern="^admin_broadcast_cancel(_confirm)?$"),
            CommandHandler("cancel", broadcast_cancel_conv) # General cancel for admins within conversation
        ],
        map_to_parent={ # If this conversation is part of a larger admin panel conversation
            ConversationHandler.END: ConversationHandler.END # Or a specific state to return to
        },
        # Allow re-entry if needed or persistent conversation data
    )


# --- Bot Statistics ---
async def bot_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query: await query.answer()

    total_users = await anidb.users_collection.count_documents({})
    # This requires `premium_expiry_date` to be set for active premium users
    # And we must ensure `check_expired_premiums_job` runs to clear status for expired ones
    active_premium_users = await anidb.users_collection.count_documents({
        "premium_status": True,
        "premium_expiry_date": {"$gte": datetime.now(pytz.utc)}
    })
    total_anime_count = await anidb.anime_collection.count_documents({})
    # Total downloads requires a download log or sum of download_count on anime
    # Simplistic total_downloads if anime collection tracks it (can be very large number)
    # This is an aggregation, can be slow. Better to maintain a separate counter or sample.
    # total_downloads_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$download_count"}}}]
    # total_downloads_result = list(await anidb.anime_collection.aggregate(total_downloads_pipeline).to_list(length=1))
    # total_downloads = total_downloads_result[0]['total'] if total_downloads_result else 0
    # For now, let's skip the heavy total_downloads sum
    total_downloads = "N/A (Aggregation Intensive)"

    stats_text = f"""{strings.EMOJI_ADMIN} <b>Bot Statistics</b> {strings.EMOJI_ADMIN}

👤 <b>Total Users:</b> <code>{total_users}</code>
💎 <b>Active Premium Users:</b> <code>{active_premium_users}</code>
🎬 <b>Total Anime Series:</b> <code>{total_anime_count}</code>
💾 <b>Total Downloads (Overall):</b> <code>{total_downloads}</code> 

<i>More detailed stats can be added.</i>
"""
    # Note: 'total_downloads' would require summing up 'download_count' from all anime, or better, a separate counter.

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]])
    if settings.ADMIN_IDS and update.effective_user.id in settings.ADMIN_IDS: # Or back to admin panel
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(f"{strings.EMOJI_ADMIN} Back to Admin Panel", callback_data="admin_panel_main")]])


    if query:
        await query.edit_message_text(text=stats_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_html(text=stats_text, reply_markup=reply_markup)
