from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup
from pyrogram.enums import ParseMode, ChatType # IMPORTED ChatType
import config
import strings
from utils.keyboard_utils import get_main_menu_keyboard, get_admin_panel_button
from database.operations import add_user_if_not_exists, get_access_token, use_access_token, update_user_tokens, mark_token_expired, get_user
from utils.logger import log_bot_event, LOGGER # Import LOGGER if you add debug prints
from datetime import datetime
# from utils.custom_filters import admin_filter # Not directly used in start_command_handler

# Token verification function (ensure this is exactly as you had it working or from my previous correct version)
async def handle_token_verification(client: Client, user_id: int, access_token_value: str):
    token_doc = await get_access_token(access_token_value)
    if not token_doc:
        return strings.TOKEN_INVALID_MESSAGE

    if token_doc['status'] != 'pending':
        return strings.TOKEN_INVALID_MESSAGE
    
    if token_doc['user_id'] != user_id:
        await log_bot_event(client, f"Token Mismatch: User {user_id} tried to use token {access_token_value} belonging to {token_doc['user_id']}.")
        return "This token does not belong to you."

    if datetime.utcnow() > token_doc['expires_at']:
        await mark_token_expired(token_doc['token_value'])
        await log_bot_event(client, f"Token {access_token_value} for user {user_id} expired on attempt.")
        return strings.TOKEN_INVALID_MESSAGE

    updated_rows = await use_access_token(token_doc['token_value'])
    if updated_rows and updated_rows.modified_count > 0:
        new_balance = await update_user_tokens(user_id, token_doc['tokens_to_grant'])
        await log_bot_event(client, f"User {user_id} redeemed token {access_token_value}, earned {token_doc['tokens_to_grant']} tokens. New balance: {new_balance}")
        return strings.TOKEN_SUCCESS_MESSAGE.format(earned_tokens=token_doc['tokens_to_grant'], new_balance=new_balance)
    else:
        await log_bot_event(client, f"Token {access_token_value} for user {user_id} found pending but failed to update (race condition or already used).")
        return strings.TOKEN_INVALID_MESSAGE

# Function to send the actual start message (photo or text)
async def send_start_message(client: Client, chat_id: int, user_id: int, user_mention: str, reply_to_message_id=None):
    user_db_data = await get_user(user_id)
    token_balance = user_db_data.get('download_tokens', 0) if user_db_data else 0
    is_premium = user_db_data.get('is_premium', False) if user_db_data else False

    start_text = strings.get_start_message(user_mention, token_balance, is_premium)
    reply_markup = get_main_menu_keyboard(token_balance, is_premium)
    
    if user_id in config.ADMIN_USER_IDS: # Add admin button if user is admin
        if reply_markup and reply_markup.inline_keyboard:
            reply_markup.inline_keyboard.append(get_admin_panel_button())
        else: # Should not happen if get_main_menu_keyboard always returns a keyboard
            reply_markup = InlineKeyboardMarkup([get_admin_panel_button()])

    send_args = {
        "chat_id": chat_id,
        "reply_markup": reply_markup,
        "parse_mode": ParseMode.HTML
    }
    # reply_to_message_id is not typically used for direct /start from user, but kept for flexibility
    if reply_to_message_id:
        send_args["reply_to_message_id"] = reply_to_message_id
    
    if config.BOT_IMAGE_URL:
        send_args["caption"] = start_text
        try:
            await client.send_photo(photo=config.BOT_IMAGE_URL, **send_args)
        except Exception as e:
            await log_bot_event(client, f"Failed to send photo on /start: {e}. Sending text fallback.")
            del send_args["caption"] # Remove caption as it's for photo
            send_args["text"] = start_text # Set text for text message
            await client.send_message(**send_args)
    else:
        send_args["text"] = start_text
        await client.send_message(**send_args)


# Main /start command handler
@Client.on_message(filters.command("start"))
async def start_command_handler(client: Client, message: Message):
    user = message.from_user
    
    # Check if the command is from a group or channel first
    if message.chat.type != ChatType.PRIVATE:
        # For group/channel, ensure user exists in DB for consistent mention, then send group-specific message
        await add_user_if_not_exists(user.id, user.username, user.first_name)
        await message.reply_text(
            f"Hi {user.mention(style='html')}! Please use me in a private chat. Click here: t.me/{config.BOT_USERNAME}?start=group_start_link", # Added a payload to differentiate if needed
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True # Good for t.me links
        )
        return # IMPORTANT: Stop further processing for non-private chats

    # --- Private Chat Logic from here ---
    await add_user_if_not_exists(user.id, user.username, user.first_name) # Ensure user is in DB
    await log_bot_event(client, f"User {user.id} ({user.mention(style='html')}) used /start in PM.", parse_mode_enum=ParseMode.HTML)

    args = message.text.split(maxsplit=1) # Use maxsplit=1 for payload
    payload_message_to_user = None # To store message from token verification

    if len(args) > 1:
        payload = args[1]
        # Avoid processing "group_start_link" as if it's an access token
        if payload != "group_start_link": 
            payload_message_to_user = await handle_token_verification(client, user.id, payload)
        
    # Send the main start message (photo or text) for private chat
    await send_start_message(client, message.chat.id, user.id, user.mention(style="html"))

    # If there was a message from token verification (e.g., success or error), send it AFTER the main start message
    if payload_message_to_user:
        await message.reply_text(payload_message_to_user, parse_mode=ParseMode.HTML)
        

# Callback query handler for "start_menu_cb" (when user clicks "Back to Main Menu" or similar)
@Client.on_callback_query(filters.regex("^start_menu_cb$"))
async def start_menu_callback_handler(client: Client, callback_query: CallbackQuery):
    user = callback_query.from_user
    # Ensure user exists if they somehow trigger this callback without a prior /start
    user_db_data = await get_user(user.id)
    if not user_db_data: 
        await add_user_if_not_exists(user.id, user.username, user.first_name)
        user_db_data = await get_user(user.id) # fetch again
        
    token_balance = user_db_data.get('download_tokens', 0) if user_db_data else 0
    is_premium = user_db_data.get('is_premium', False) if user_db_data else False

    start_text = strings.get_start_message(user.mention(style="html"), token_balance, is_premium)
    reply_markup = get_main_menu_keyboard(token_balance, is_premium)

    if user.id in config.ADMIN_USER_IDS: # Add admin button if user is admin
        if reply_markup and reply_markup.inline_keyboard:
            reply_markup.inline_keyboard.append(get_admin_panel_button())
        else:
            reply_markup = InlineKeyboardMarkup([get_admin_panel_button()])
            
    try:
        current_message_is_photo = bool(callback_query.message.photo)
        target_message_is_photo = bool(config.BOT_IMAGE_URL)

        if current_message_is_photo == target_message_is_photo: # Current and target states are same (photo-to-photo or text-to-text)
            if target_message_is_photo: # Photo to Photo
                await callback_query.edit_message_caption(
                    caption=start_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
                )
            else: # Text to Text
                await callback_query.edit_message_text(
                    text=start_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
                )
        elif target_message_is_photo and not current_message_is_photo: # Text to Photo (current is text, target is photo)
            await callback_query.message.delete() # Delete old text message
            await client.send_photo( # Send new photo message
                chat_id=callback_query.message.chat.id, photo=config.BOT_IMAGE_URL,
                caption=start_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
        elif not target_message_is_photo and current_message_is_photo: # Photo to Text (current is photo, target is text)
            await callback_query.message.delete() # Delete old photo message
            await client.send_message( # Send new text message
                chat_id=callback_query.message.chat.id, text=start_text,
                reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
    except Exception as e:
        await log_bot_event(client, f"Error editing to start_menu (cb): {e}. Sending new.")
        # Fallback: send a new message if editing fails (e.g., message too old)
        await callback_query.message.reply_text("Session might have expired. Here's the main menu again:") # Give context
        await send_start_message(client, callback_query.message.chat.id, user.id, user.mention(style="html"))
    
    await callback_query.answer()


# Handler for "noop" or "go_back_general" callbacks (general utility)
@Client.on_callback_query(filters.regex("^noop") | filters.regex("^go_back_general$"))
async def noop_handler(client: Client, callback_query: CallbackQuery):
    if callback_query.data == "go_back_general":
        await callback_query.answer("Please use the Main Menu button or specific back buttons.", show_alert=True)
    else: # For "noop" or "noop_ack"
        await callback_query.answer() # Just acknowledge the button press
