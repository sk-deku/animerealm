from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode
import config
import strings
from utils.keyboard_utils import get_main_menu_keyboard # Or a specific "back to premium info"

@Client.on_message(filters.command("premium"))
@Client.on_callback_query(filters.regex(r"^premium_info$"))
async def premium_info_handler(client: Client, message_or_cb):
    is_cb = isinstance(message_or_cb, CallbackQuery)
    message_to_reply = message_or_cb.message if is_cb else message_or_cb

    # For now, this just displays info. Payment is external.
    text = strings.PREMIUM_INFO_TEXT 
    # Add instructions on how to pay or who to contact
    text += "\n\n➡️ To subscribe, please contact our support team or follow instructions on our updates channel." # Example

    reply_markup = InlineKeyboardMarkup([
        # Potentially a button linking to Patreon/Payment Page if you have one
        # [InlineKeyboardButton("💳 Subscribe Now (External Link)", url="YOUR_PAYMENT_LINK_HERE")],
        [InlineKeyboardButton("💬 Contact Support", url=config.SUPPORT_LINK)],
        [InlineKeyboardButton("⬆️ Main Menu", callback_data="start_menu_cb")]
    ])
    
    if is_cb:
        try:
            await message_or_cb.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except: # If msg is photo etc.
             await message_or_cb.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        await message_or_cb.answer()
    else:
        await message_or_cb.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
