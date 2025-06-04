from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode
import config
import strings
from utils.keyboard_utils import get_token_generation_keyboard
from utils.shortener import shorten_link
from database.operations import add_user_if_not_exists, create_access_token, can_earn_tokens, record_token_earn
from utils.logger import log_bot_event

@Client.on_message(filters.command(["gen_token", "get_token", "earn_tokens"]))
@Client.on_callback_query(filters.regex("^earn_tokens$")) # Combined filter for command and callback
async def earn_tokens_prompt_handler(client: Client, message_or_callback_query):
    is_callback = isinstance(message_or_callback_query, CallbackQuery)
    
    if is_callback:
        user = message_or_callback_query.from_user
        message = message_or_callback_query.message
        await message_or_callback_query.answer()
    else:
        user = message_or_callback_query.from_user
        message = message_or_callback_query

    await add_user_if_not_exists(user.id, user.username, user.first_name)
    
    if not await can_earn_tokens(user.id): # Check daily limit BEFORE showing gen button
        await message.reply_text(strings.TOKEN_DAILY_LIMIT_REACHED, parse_mode=ParseMode.HTML)
        return

    text = strings.GEN_TOKEN_MESSAGE.format(
        tokens_to_earn=config.TOKENS_PER_BYPASS,
        expiry_hours=config.TOKEN_EXPIRY_HOURS,
        daily_limit=config.TOKENS_PER_BYPASS # Assuming one token generation counts as one "earn"
        # If TOKENS_PER_BYPASS in config means # of links per day, this daily_limit needs to come from config
    )
    reply_markup = get_token_generation_keyboard()

    if is_callback:
        try:
            await message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            await log_bot_event(client, f"Error editing message in earn_tokens_prompt_handler (cb): {e}")
            await message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML) # Fallback
    else:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

@Client.on_callback_query(filters.regex(r"^generate_shortened_link$"))
async def generate_shortened_link_handler(client: Client, callback_query: CallbackQuery):
    user = callback_query.from_user
    
    if not await can_earn_tokens(user.id): # Re-check, user might spam button
        await callback_query.answer(strings.TOKEN_DAILY_LIMIT_REACHED, show_alert=True)
        # Optionally edit message to reflect this
        try:
            await callback_query.message.edit_text(strings.TOKEN_DAILY_LIMIT_REACHED, parse_mode=ParseMode.HTML)
        except: pass
        return

    await callback_query.answer("Generating your link, please wait...", show_alert=False)

    access_token = await create_access_token(user.id)
    if not access_token:
        await callback_query.message.edit_text("❌ Could not generate an access token. Please try again later.")
        await log_bot_event(client, f"Failed to create access_token for user {user.id}")
        return

    deep_link_url = f"https://t.me/{config.BOT_USERNAME}?start={access_token}"
    shortened_url = await shorten_link(deep_link_url)

    if not shortened_url:
        await callback_query.message.edit_text(
            "❌ Could not shorten the link. Please try again later or contact support.\n"
            f"You can use this direct link: {deep_link_url}",
            disable_web_page_preview=True
        )
        await log_bot_event(client, f"Failed to shorten link {deep_link_url} for user {user.id}")
        return
    
    # After successfully generating a link, record that they used one "earn attempt" for the day
    await record_token_earn(user.id) # This increments tokens_earned_today

    current_text_intro = strings.GEN_TOKEN_MESSAGE.split('🔗 Click the button below')[0]
    updated_text = (
        f"{current_text_intro}"
        f"🔗 **Your Link:** {shortened_url}\n\n"
        "Visit the link above. After completing the steps, you'll be redirected back to me to claim your tokens!\n"
        f"Remember, this link is for you ({user.mention(style='html')}) and will grant <b>{config.TOKENS_PER_BYPASS}</b> tokens."
    )
    
    # Update keyboard to remove the "Generate" button or change it to "Get Another Link (if allowed)"
    # For now, re-using the same keyboard; the earn_tokens_prompt_handler will re-check limit.
    await callback_query.message.edit_text(
        updated_text,
        reply_markup=get_token_generation_keyboard(), 
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )
    await log_bot_event(client, f"User {user.id} generated token link {shortened_url} (raw: {deep_link_url})")
