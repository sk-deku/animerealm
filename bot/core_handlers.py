# bot/core_handlers.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes, ConversationHandler
from telegram.ext import Application, CommandHandler
from telegram.constants import ParseMode
from datetime import datetime, timedelta
import pytz # For timezone awareness if needed

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance

logger = logging.getLogger(__name__)

# --- Helper Functions ---
def build_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Builds the main menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton(strings.BTN_SEARCH, callback_data="core_search"),
            InlineKeyboardButton(strings.BTN_BROWSE, callback_data="core_browse")
        ],
        [
            InlineKeyboardButton(strings.BTN_POPULAR, callback_data="core_popular"),
            InlineKeyboardButton(strings.BTN_LATEST, callback_data="core_latest")
        ],
        [
            InlineKeyboardButton(strings.BTN_MY_WATCHLIST, callback_data="core_my_watchlist"),
            InlineKeyboardButton(strings.BTN_PROFILE, callback_data="core_profile")
        ],
        [
            InlineKeyboardButton(strings.BTN_GET_TOKENS, callback_data="core_get_tokens_info"),
            InlineKeyboardButton(strings.BTN_PREMIUM, callback_data="core_premium_info")
        ],
        [InlineKeyboardButton(strings.BTN_HELP, callback_data="core_help")]
    ]
    # Example of adding an admin-only button to main menu if user is admin
    if user_id in settings.ADMIN_IDS:
        keyboard.append([InlineKeyboardButton(f"{strings.EMOJI_ADMIN} Admin Panel", callback_data="admin_panel_main")])
    return InlineKeyboardMarkup(keyboard)

async def reply_with_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str = None):
    """Sends or edits a message to show the main menu."""
    user = update.effective_user
    if not message_text:
        message_text = strings.WELCOME_MESSAGE.format(user_first_name=user.first_name)

    keyboard = build_main_menu_keyboard(user.id)
    if update.callback_query: # If called from a callback, edit the message
        try:
            await update.callback_query.edit_message_text(
                text=message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML # Ensure parse mode is HTML
            )
        except Exception as e: # Handle "message is not modified" or other errors
            logger.debug(f"Error editing message for main menu (may be unmodified): {e}")
            await update.callback_query.answer() # Acknowledge callback anyway
            # If edit failed catastrophically, try sending a new one
            if "message to edit not found" in str(e).lower() or "message is not modified" not in str(e).lower() :
                 await context.bot.send_message(
                    chat_id=user.id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML
                )

    else: # If called from a command, send a new message
        await update.message.reply_html(
            text=message_text,
            reply_markup=keyboard
        )

async def check_user_or_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """
    Checks if the user exists in DB. If not, adds them.
    Handles referral code logic if present in start_payload.
    Returns the user document from DB.
    """
    user = update.effective_user
    start_payload = context.args[0] if context.args else None # For deep linking ?start=payload
    user_doc = await anidb.get_user(user.id)
    new_user_just_added = False

    # Log new user for stats if they don't exist
    if not user_doc:
        new_user_just_added = True
        logger.info(f"New user detected: {user.id} ({user.first_name})")
        # Logic to handle referral code if `start_payload` is a referral code
        referral_code_data = None
        referred_by_user_id = None
        referrer_name_for_log = "N/A"

        if start_payload and start_payload.startswith("ref_"): # Assuming referral codes start with "ref_"
            code_str = start_payload
            referral_code_data = await anidb.get_referral_code(code_str)
            if referral_code_data:
                # Ensure the user starting is not the creator of the code
                if referral_code_data["creator_user_id"] == user.id:
                    logger.info(f"User {user.id} tried to use their own referral code {code_str}. Ignoring referral.")
                    referral_code_data = None # Invalidate self-referral
                else:
                    referred_by_user_id = referral_code_data["creator_user_id"]
                    # Get referrer name for logging
                    referrer_user_doc = await anidb.get_user(referred_by_user_id)
                    if referrer_user_doc:
                        referrer_name_for_log = referrer_user_doc.get("first_name", "Unknown Referrer")

        # Add user to DB (add_or_update_user will handle tokens based on referral)
        add_result = await anidb.add_or_update_user(
            user_id=user.id,
            first_name=user.first_name,
            username=user.username,
            referred_by=referred_by_user_id # Pass referrer if any
        )
        if not add_result:
            await update.effective_message.reply_text(strings.GENERAL_ERROR + " (DB User Add)")
            return None
        user_doc = add_result["user_doc"] # Get the newly created/updated user doc

        # Process referral reward if successful & user was actually new
        if referral_code_data and referred_by_user_id and add_result.get("new"): # Ensure only new users trigger referral reward
            can_award_referrer = True
            referrer_user_doc = await anidb.get_user(referred_by_user_id)

            if referrer_user_doc:
                # Check referrer's daily earn limit
                now_date_utc = datetime.now(pytz.utc).date()
                if referrer_user_doc.get("last_token_earn_reset_date") != now_date_utc:
                     await anidb.users_collection.update_one( # Reset if different day
                        {"telegram_id": referred_by_user_id},
                        {"$set": {"tokens_earned_today": 0, "last_token_earn_reset_date": now_date_utc}}
                    )
                     referrer_user_doc["tokens_earned_today"] = 0 # Update in-memory for next check

                if referrer_user_doc.get("tokens_earned_today", 0) >= settings.DAILY_TOKEN_EARN_LIMIT_PER_USER:
                    can_award_referrer = False
                    logger.info(f"Referrer {referred_by_user_id} reached daily token limit. No reward for this referral.")
                    # Optionally notify referrer they reached limit, or just silently skip reward

            if can_award_referrer:
                await anidb.update_user_tokens(referred_by_user_id, settings.TOKENS_AWARDED_PER_REFERRAL)
                await anidb.update_daily_token_earn(referred_by_user_id, settings.TOKENS_AWARDED_PER_REFERRAL)
                await anidb.claim_referral_code(code_str, user.id) # Mark code as claimed

                # Notify referrer
                try:
                    await context.bot.send_message(
                        chat_id=referred_by_user_id,
                        text=strings.TOKEN_EARNED_NOTIFICATION_REFERRER.format(
                            tokens_awarded=settings.TOKENS_AWARDED_PER_REFERRAL,
                            new_user_name=user.first_name
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to send referral reward notification to {referred_by_user_id}: {e}")

                # Log successful referral token award
                if settings.USER_LOGS_CHANNEL_ID:
                    log_msg = strings.LOG_TOKEN_AWARDED_REFERRER.format(
                        referrer_id=referred_by_user_id,
                        referrer_name=referrer_name_for_log,
                        tokens_awarded=settings.TOKENS_AWARDED_PER_REFERRAL,
                        new_user_id=user.id,
                        new_user_name=user.first_name
                    )
                    await context.bot.send_message(settings.USER_LOGS_CHANNEL_ID, log_msg, parse_mode=ParseMode.HTML)


        # Send welcome message and log to channel for new user
        if add_result.get("new"): # Ensure these actions are only for genuinely new users added to DB
            tokens_given_to_new_user = add_result.get("tokens_awarded", 0)
            if referred_by_user_id:
                await update.effective_message.reply_text(
                    strings.TOKEN_AWARDED_NEW_USER_REFERRAL.format(tokens_awarded=tokens_given_to_new_user)
                )
                if settings.USER_LOGS_CHANNEL_ID:
                    log_msg = strings.LOG_NEW_USER_REFERRAL.format(
                        user_id=user.id, user_first_name=user.first_name, tokens_awarded=tokens_given_to_new_user,
                        referrer_id=referred_by_user_id, referrer_name=referrer_name_for_log
                    )
                    await context.bot.send_message(settings.USER_LOGS_CHANNEL_ID, log_msg, parse_mode=ParseMode.HTML)
            else:
                await update.effective_message.reply_text(
                    strings.TOKEN_AWARDED_NEW_USER_DIRECT.format(tokens_awarded=tokens_given_to_new_user)
                )
                if settings.USER_LOGS_CHANNEL_ID:
                    log_msg = strings.LOG_NEW_USER_DIRECT.format(
                        user_id=user.id, user_first_name=user.first_name, tokens_awarded=tokens_given_to_new_user
                    )
                    await context.bot.send_message(settings.USER_LOGS_CHANNEL_ID, log_msg, parse_mode=ParseMode.HTML)

    else: # Existing user, just update last_active_date and reset daily token earn if needed
        # This update logic is now inside add_or_update_user if `not user_data` part fails (i.e user exists)
        # So we just ensure we have the latest doc.
        update_result = await anidb.add_or_update_user(user.id, user.first_name, user.username) # This will update last_active & reset daily limit if needed
        if update_result:
            user_doc = update_result["user_doc"]
        else:
            await update.effective_message.reply_text(strings.GENERAL_ERROR + " (DB User Update)")
            return None


    # Handle specific start payloads if not referral code, e.g., viewing watchlist directly
    if start_payload and not start_payload.startswith("ref_") and new_user_just_added is False: # Only process for existing users if not a referral for new user
        if start_payload == "view_watchlist":
            from bot.watchlist import view_watchlist_command # Avoid circular import at top
            await view_watchlist_command(update, context)
            return user_doc # Return early as watchlist command handles its own reply

        # Add more specific payload handlers here:
        # if start_payload.startswith("view_anime_"):
        #   anime_id_str = start_payload.split("_")[2]
        #   await display_anime_details(update, context, anime_id_str) # example function
        #   return ConversationHandler.END # or specific state

    return user_doc


# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command, registers new users, processes referral links."""
    user = update.effective_user
    logger.info(f"/start command from {user.id} ({user.first_name}), payload: {context.args}")

    user_db_doc = await check_user_or_add(update, context)
    if not user_db_doc:
        # Error already sent by check_user_or_add
        return

    # Check for specific start payloads that aren't referrals and aren't handled inside check_user_or_add
    # Most general start just shows main menu if no specific payload was actioned
    # Example deep link payloads (other than referral) should return early if they handled the reply in check_user_or_add
    await reply_with_main_menu(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the help message."""
    user = update.effective_user
    logger.info(f"/help command from {user.id} ({user.first_name})")

    if user.id in settings.ADMIN_IDS:
        help_text = strings.HELP_MESSAGE_GENERAL + "\n\n" + strings.HELP_MESSAGE_ADMIN
    else:
        help_text = strings.HELP_MESSAGE_GENERAL

    if update.callback_query:
        await update.callback_query.edit_message_text(text=help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        await update.callback_query.answer()
    else:
        await update.message.reply_html(text=help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current action or conversation."""
    user = update.effective_user
    logger.info(f"Cancel command invoked by {user.id} ({user.first_name})")
    query = update.callback_query

    current_conv_handler_state = context.user_data.pop('_current_conversation_state', None) # If you track states this way

    if query:
        await query.answer(text=strings.OPERATION_CANCELLED)
        # Try to edit the message to show main menu or a simple cancel confirmation
        try:
            # Send new message instead of editing, because callback might be from a temporary message.
            # Editing may fail if original message content has drastically changed or was from a different flow.
            # await query.edit_message_text(text=strings.OPERATION_CANCELLED, reply_markup=build_main_menu_keyboard(user.id))
            await context.bot.send_message(user.id, text=strings.OPERATION_CANCELLED)
            await reply_with_main_menu(update, context) # Show main menu
        except Exception as e:
            logger.debug(f"Could not edit message on cancel from callback: {e}")
            await context.bot.send_message(user.id, strings.OPERATION_CANCELLED)
            await reply_with_main_menu(update, context) # Show main menu

    elif update.message:
        await update.message.reply_html(text=strings.OPERATION_CANCELLED)
        await reply_with_main_menu(update, context) # Show main menu

    # Clear conversation-specific user_data if needed
    # (this depends on how your conversation handlers store temporary data)
    # for key in list(context.user_data.keys()):
    #     if key.startswith("conv_"): # Example prefix for conversation data
    #         del context.user_data[key]

    return ConversationHandler.END # This tells any active ConversationHandler to end


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # For user-facing error message (optional, can be too noisy)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(strings.GENERAL_ERROR + " Our team has been notified.")
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

    # Optionally, send error details to admin/developer chat if configured
    # dev_chat_id = settings.DEVELOPER_CHAT_ID
    # if dev_chat_id:
    #     tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    #     tb_string = "".join(tb_list)
    #     error_message = (
    #         f"An exception was raised while handling an update\n"
    #         f"<pre>update = {html.escape(json.dumps(update.to_dict(), indent=2, ensure_ascii=False))}</pre>\n\n"
    #         f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
    #         f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
    #         f"<pre>{html.escape(tb_string)}</pre>"
    #     )
    #     # Split message if too long for Telegram
    #     for i in range(0, len(error_message), 4096):
    #         await context.bot.send_message(chat_id=dev_chat_id, text=error_message[i:i+4096], parse_mode=ParseMode.HTML)


# In bot/core_handlers.py
def register_handlers(application: Application):
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_error_handler(error_handler)
    # (Add job queue scheduling here if not done in main_ptb_bot_loop directly)
    logger.info("Core handlers registered.")


# --- Job Queue Callbacks ---
async def check_expired_premiums_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job to check for and deactivate expired premium memberships."""
    logger.info("Running job: Checking for expired premium memberships...")
    now = datetime.now(pytz.utc) # Use timezone-aware datetime
    
    # Query for users whose premium is active but expiry date is in the past
    expired_users_ids = await anidb.check_and_deactivate_expired_premiums()

    if expired_users_ids:
        logger.info(f"Deactivated premium for {len(expired_users_ids)} users.")
        for user_id in expired_users_ids:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"{strings.EMOJI_PREMIUM} Your Premium membership has expired. You can renew it via /premium."
                )
            except Exception as e:
                logger.error(f"Failed to send premium expiry notification to user {user_id}: {e}")
    else:
        logger.info("No expired premium memberships found to deactivate.")
