from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode
from bson import ObjectId
import config
import strings
from utils.keyboard_utils import get_main_menu_keyboard # or a specific "back"
from database.operations import get_user, add_anime_request
from utils.logger import log_bot_event, log_request_event
from utils.custom_filters import premium_filter # For premium-only requests

REQUEST_STATE = {} # user_id: {'step': 'title'/'language', 'anime_title': 'XYZ'}

@Client.on_message(filters.command("request"))
@Client.on_callback_query(filters.regex(r"^request_anime_prompt$"))
async def request_anime_prompt_handler(client: Client, message_or_cb):
    is_cb = isinstance(message_or_cb, CallbackQuery)
    user = message_or_cb.from_user
    message_to_reply = message_or_cb.message if is_cb else message_or_cb

    user_data = await get_user(user.id)
    if not user_data or not user_data.get('is_premium', False):
        if is_cb: await message_or_cb.answer(strings.REQUEST_PREMIUM_ONLY, show_alert=True)
        await message_to_reply.reply_text(strings.REQUEST_PREMIUM_ONLY, parse_mode=ParseMode.HTML, 
                                          reply_markup=(get_main_menu_keyboard() if is_cb else None) ) # Edit if CB
        return

    REQUEST_STATE[user.id] = {'step': 'title'}
    prompt_text = strings.REQUEST_PROMPT_TITLE
    
    if is_cb:
        await message_or_cb.edit_message_text(prompt_text, parse_mode=ParseMode.HTML)
        await message_or_cb.answer()
    else:
        await message_or_cb.reply_text(prompt_text, parse_mode=ParseMode.HTML)


@Client.on_message(filters.private & filters.text)
async def request_text_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in REQUEST_STATE:
        raise ContinuePropagation # Not a request input

    state = REQUEST_STATE[user_id]
    current_step = state.get('step')
    text = message.text.strip()

    if current_step == 'title':
        if not text or len(text) < 3:
            await message.reply_text("Anime title too short. Please provide a more specific title.")
            return # Keep in 'title' step
        
        state['anime_title'] = text
        state['step'] = 'language'
        await message.reply_text(strings.REQUEST_PROMPT_LANGUAGE.format(anime_title=text), parse_mode=ParseMode.HTML)

    elif current_step == 'language':
        if not text:
            await message.reply_text("Please specify a preferred language (e.g., SUB English, DUB, Any).")
            return # Keep in 'language' step

        requested_language = text
        anime_title_requested = state.get('anime_title', 'Unknown Title') # Safety
        
        # Submit the request
        try:
            request_id = await add_anime_request(user_id, anime_title_requested, requested_language)
            success_msg = strings.REQUEST_SUBMITTED.format(
                anime_title=anime_title_requested, 
                language=requested_language,
                request_id=str(request_id) # Display request ID to user
            )
            await message.reply_text(success_msg, parse_mode=ParseMode.HTML, reply_markup=get_main_menu_keyboard()) # Back to main menu

            # Log to admin channel
            log_admin_msg = (f"🆕 New Anime Request:\n"
                             f"User: {message.from_user.mention(style='html')} (ID: {user_id})\n"
                             f"Anime Title: <b>{anime_title_requested}</b>\n"
                             f"Language: {requested_language}\n"
                             f"DB Request ID: `{str(request_id)}`\n"
                             f"Status: PENDING")
            await log_request_event(client, log_admin_msg, parse_mode="HTML")

        except Exception as e:
            await message.reply_text(strings.SOMETHING_WENT_WRONG + " Could not submit your request.")
            await log_bot_event(client, f"Error submitting anime request for user {user_id}: {e}")
        
        del REQUEST_STATE[user_id] # Clear state

    else: # Should not happen
        del REQUEST_STATE[user_id]
        raise ContinuePropagation
