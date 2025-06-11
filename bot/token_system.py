# bot/token_system.py
import logging
import uuid
import asyncio # For async HTTP requests
import aiohttp # For making HTTP requests to the shortener API
from urllib.parse import urlencode # For query parameters if needed by shortener

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from datetime import datetime, timedelta
import pytz

from configs import settings, strings
from database.mongo_db import db as anidb # Assuming anidb is your Database instance
from .core_handlers import check_user_or_add

logger = logging.getLogger(__name__)

# --- Helper to make API call to shortener (remains the same as before) ---
async def shorten_url_api(long_url: str) -> str | None:
    """
    Shortens a URL using the configured shortener API.
    Returns the shortened URL or None if an error occurs.
    This needs to be adapted based on the specific shortener's API documentation.
    """
    if not settings.SHORTENER_API_URL or not settings.SHORTENER_API_KEY:
        logger.warning("Shortener API URL or Key not configured. Skipping URL shortening.")
        return long_url # Return original URL if shortener not configured

    api_request_url = f"{settings.SHORTENER_API_URL}?api={settings.SHORTENER_API_KEY}&url={long_url}"
    logger.debug(f"Attempting to shorten URL. API call to: {settings.SHORTENER_API_URL} (API key redacted for logging, URL: {long_url})")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_request_url) as response: # Assuming GET request for Linkshortify based on common patterns
                response.raise_for_status()
                try:
                    data = await response.json()
                    logger.debug(f"Shortener API JSON response: {data}")
                    # Adapt to Linkshortify's specific success JSON structure
                    if data.get("status") == "success" and data.get("shortenedUrl"):
                        return data["shortenedUrl"]
                    elif data.get("error") == 0 and data.get("short"):
                        return data["short"]
                    elif "short_url" in data:
                        return data["short_url"]
                    elif "result_url" in data: # Another common key
                         return data["result_url"]
                    else: # Attempt to read as text if JSON structure is unknown or failed
                        logger.warning(f"Shortener API success response but unexpected JSON structure: {data}")
                        raw_text_response = await response.text(errors='ignore') # Read as text, ignore decode errors for now
                        if raw_text_response and raw_text_response.strip().startswith("http"):
                            logger.info(f"Got plain text URL from shortener: {raw_text_response.strip()}")
                            return raw_text_response.strip()
                        logger.error(f"Shortener API returned unusable JSON and no plain text URL: {data}")
                        return long_url
                except aiohttp.ContentTypeError:
                    shortened_url_text = await response.text(errors='ignore')
                    logger.debug(f"Shortener API TEXT response: {shortened_url_text}")
                    if shortened_url_text and shortened_url_text.strip().startswith("http"):
                        return shortened_url_text.strip()
                    else:
                        logger.error(f"Shortener API returned non-URL plain text: {shortened_url_text}")
                        return long_url
                except Exception as json_e: # Catch other JSON parsing related errors
                    logger.error(f"Error processing shortener JSON response: {json_e}")
                    raw_text_response = await response.text(errors='ignore') # Try text again
                    if raw_text_response and raw_text_response.strip().startswith("http"):
                        return raw_text_response.strip()
                    return long_url

    except aiohttp.ClientError as e:
        logger.error(f"ClientError calling shortener API ({settings.SHORTENER_API_URL}): {e}")
        return long_url
    except Exception as e:
        logger.error(f"Unexpected error during URL shortening: {e}", exc_info=True)
        return long_url


# --- /gen_tokens Command (User generates their referral link & gets info) ---
async def generate_and_show_token_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Allows users to generate their referral link to earn tokens and provides info.
    Replaces separate /get_tokens and /gen_token_link.
    """
    user = update.effective_user
    query = update.callback_query # Could be triggered by a callback, though now it's a direct command

    logger.info(f"/gen_tokens command or callback for {user.id} ({user.first_name})")

    user_db_doc = await check_user_or_add(update, context) # Ensures user exists and daily limits are reset if new day
    if not user_db_doc: return

    # Check daily earn limit.
    now_utc = datetime.now(pytz.utc)
    # Ensure daily limit reset logic (this might be slightly redundant if check_user_or_add handles it perfectly, but safe)
    if user_db_doc.get("last_token_earn_reset_date") != now_utc.date():
        await anidb.users_collection.update_one(
            {"telegram_id": user.id},
            {"$set": {"tokens_earned_today": 0, "last_token_earn_reset_date": now_utc.date()}}
        )
        user_db_doc["tokens_earned_today"] = 0 # Update in-memory for this check

    if user_db_doc.get("tokens_earned_today", 0) >= settings.DAILY_TOKEN_EARN_LIMIT_PER_USER:
        message_text = strings.DAILY_TOKEN_LIMIT_REACHED.format(limit=settings.DAILY_TOKEN_EARN_LIMIT_PER_USER)
        # Add tutorial link to this message too
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(strings.BTN_HOW_TO_EARN_TUTORIAL, url=settings.HOW_TO_EARN_TOKENS_TUTORIAL_LINK)],
            [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]
        ])
        if query:
            await query.answer(text="Daily earn limit reached.", show_alert=True)
            await query.edit_message_text(message_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_html(message_text, reply_markup=keyboard)
        return

    # Acknowledge user before API call if from callback
    if query:
        await query.answer(f"{strings.EMOJI_LOADING} Generating your link...")

    # Generate unique referral code
    unique_part = str(uuid.uuid4().hex)[:8]
    referral_code = f"ref_{user.id}_{unique_part}"

    expiry_datetime = now_utc + timedelta(hours=settings.TOKEN_LINK_ACTIVE_HOURS)

    # Store in database
    code_created = await anidb.create_referral_code(
        creator_user_id=user.id,
        referral_code=referral_code,
        tokens_to_award=settings.TOKENS_AWARDED_PER_REFERRAL,
        expiry_date=expiry_datetime
    )

    if not code_created:
        err_msg = f"{strings.EMOJI_ERROR} Could not generate a unique referral link at this time. Please try again later."
        if query:
            # await query.answer("Error generating link.", show_alert=True) # Already answered
            await query.edit_message_text(err_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        else:
            await update.message.reply_html(err_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]]))
        return

    # Construct the t.me link
    long_telegram_link = f"https://t.me/{settings.BOT_USERNAME}?start={referral_code}"

    # Shorten the URL
    shortened_url = await shorten_url_api(long_telegram_link)
    if not shortened_url or shortened_url == long_telegram_link: # If shortener fails or not configured
        shortened_url = long_telegram_link # Use the original t.me link
        logger.warning(f"URL Shortening did not produce a different URL for {long_telegram_link}, using original link.")


    # Combine informational text with the generated link message
    info_text_header = strings.GET_TOKENS_INFO.format(
        tokens_per_referral=settings.TOKENS_AWARDED_PER_REFERRAL,
        tokens_for_new_user_referral=settings.TOKENS_FOR_NEW_USER_VIA_REFERRAL,
        daily_token_limit=settings.DAILY_TOKEN_EARN_LIMIT_PER_USER
    )
    link_generated_text_part = strings.TOKEN_LINK_GENERATED_MESSAGE.format(
        tokens_to_award=settings.TOKENS_AWARDED_PER_REFERRAL,
        link_active_hours=settings.TOKEN_LINK_ACTIVE_HOURS # This is about the t.me link referral validity from DB
    )

    final_message = f"{info_text_header}\n\n{link_generated_text_part}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(strings.BTN_SHARE_THIS_LINK, url=shortened_url)],
        [InlineKeyboardButton(strings.BTN_HOW_TO_EARN_TUTORIAL, url=settings.HOW_TO_EARN_TOKENS_TUTORIAL_LINK)],
        [InlineKeyboardButton(strings.BTN_BACK_TO_MAIN_MENU, callback_data="core_main_menu")]
    ])
    
    # Log generation
    if settings.USER_LOGS_CHANNEL_ID:
        expiry_time_str = expiry_datetime.strftime("%Y-%m-%d %H:%M:%S %Z")
        log_msg = strings.LOG_TOKEN_LINK_GENERATED.format(
            user_id=user.id, user_first_name=user.first_name,
            referral_code=referral_code, expiry_time_str=expiry_time_str
        )
        await context.bot.send_message(settings.USER_LOGS_CHANNEL_ID, log_msg, parse_mode=ParseMode.HTML)

    if query: # If called from a callback (e.g. "gen_referral_link_now" that was on old /get_tokens)
        await query.edit_message_text(text=final_message, reply_markup=keyboard, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    elif update.message:
        await update.message.reply_html(text=final_message, reply_markup=keyboard, disable_web_page_preview=True)
