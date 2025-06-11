# bot/user_cmds.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from datetime import datetime
import pytz

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance
from .core_handlers import check_user_or_add, reply_with_main_menu # For main menu button

logger = logging.getLogger(__name__)

# --- /profile Command ---
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's profile: tokens, premium status, watchlist summary."""
    user = update.effective_user
    logger.info(f"Profile command/callback for {user.id} ({user.first_name})")

    user_db_doc = await check_user_or_add(update, context) # Ensure user exists and doc is fresh
    if not user_db_doc:
        # Error already sent by check_user_or_add
        return

    tokens = user_db_doc.get("download_tokens", 0)
    is_premium = user_db_doc.get("premium_status", False)
    premium_expiry = user_db_doc.get("premium_expiry_date") # This is UTC datetime object
    watchlist_count = len(user_db_doc.get("watchlist", []))

    premium_status_message = strings.PREMIUM_INACTIVE_MESSAGE
    if is_premium and premium_expiry:
        # Convert UTC expiry to a more readable local timezone if desired, or keep as UTC
        # For simplicity, just format the UTC date
        # To convert to Indian Standard Time (IST) for display:
        # ist = pytz.timezone('Asia/Kolkata')
        # local_expiry_time = premium_expiry.astimezone(ist)
        # expiry_date_str = local_expiry_time.strftime("%d %b %Y, %I:%M %p %Z")
        expiry_date_str = premium_expiry.strftime("%d %b %Y, %H:%M UTC") # Keep it simple for now
        premium_status_message = strings.PREMIUM_ACTIVE_MESSAGE.format(expiry_date=expiry_date_str)
    elif is_premium and not premium_expiry: # Should not happen, but handle
        premium_status_message = f"<b>Active</b> {strings.EMOJI_SUCCESS} (No expiry date set - contact admin)"


    profile_text = strings.PROFILE_INFO.format(
        user_first_name=user.first_name,
        user_id=user.id,
        tokens=tokens,
        premium_status_message=premium_status_message,
        watchlist_count=watchlist_count,
        BOT_USERNAME=settings.BOT_USERNAME # Ensure BOT_USERNAME is accessible for the link
    )

    keyboard = InlineKeyboardMarkup([
        # [InlineKeyboardButton(f"{strings.EMOJI_WATCHLIST} View Watchlist ({watchlist_count})", callback_data="core_my_watchlist")],
        [InlineKeyboardButton(strings.BTN_GET_TOKENS, callback_data="core_get_tokens_info")],
        [InlineKeyboardButton(strings.BTN_PREMIUM, callback_data="core_premium_info")],
        [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=profile_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_html(
            text=profile_text,
            reply_markup=keyboard
        )

# --- /premium Command ---
async def premium_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays information about premium plans and how to upgrade."""
    user = update.effective_user
    logger.info(f"Premium info command/callback for {user.id} ({user.first_name})")

    # Ensure user exists for any potential context
    user_db_doc = await check_user_or_add(update, context)
    if not user_db_doc:
        return

    max_watchlist_premium = settings.MAX_WATCHLIST_ITEMS_PREMIUM

    premium_text = strings.PREMIUM_INFO_HEADER
    premium_text += strings.PREMIUM_BENEFITS.format(max_watchlist_premium=max_watchlist_premium)
    premium_text += "\n\n💰 <b>Available Plans (INR):</b>\n"

    plan_buttons = []
    for duration_days, plan_details in settings.PREMIUM_PLANS_INR.items():
        plan_icon = strings.EMOJI_PREMIUM # Default icon
        if duration_days == 7: plan_icon = "✨"
        elif duration_days == 30: plan_icon = "🌟"
        elif duration_days == 90: plan_icon = "💎"

        premium_text += strings.PREMIUM_PLAN_ENTRY.format(
            plan_icon=plan_icon,
            display_name=plan_details["display_name"],
            price_inr=plan_details["price_inr"],
            duration_days=plan_details["duration_days"], # Use the key directly
            savings_text=plan_details["savings_text"]
        )
        # Create a button that directly opens chat with the admin (example)
        # Or a button that sends a specific message/payload if you have a more automated flow start
        # For manual payment, a direct contact button is simplest.
        contact_text = f"Buy {plan_details['display_name']} (₹{plan_details['price_inr']})"
        admin_contact_url = f"https://t.me/{settings.CONTACT_ADMIN_USERNAME_FOR_PREMIUM}?text=Hi!%20I'm%20interested%20in%20the%20{plan_details['display_name'].replace('<b>','').replace('</b>','').replace('<i>','').replace('</i>','').replace('✨','').replace('🌟','').replace('💎','').strip().replace(' ','%20')}%20(₹{plan_details['price_inr']})."
        plan_buttons.append([InlineKeyboardButton(
            f"{plan_icon} Buy {plan_details['display_name']} - ₹{plan_details['price_inr']}",
            url=admin_contact_url
        )])


    premium_text += strings.PREMIUM_CONTACT_INSTRUCTION.format(
        contact_admin_username=settings.CONTACT_ADMIN_USERNAME_FOR_PREMIUM
    )

    keyboard_layout = plan_buttons # Add generated plan buttons
    keyboard_layout.append([InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")])
    keyboard = InlineKeyboardMarkup(keyboard_layout)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=premium_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True # Good practice if links are present
        )
    else:
        await update.message.reply_html(
            text=premium_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
