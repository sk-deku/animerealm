from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup # Added InlineKeyboardMarkup for direct use
from pyrogram.enums import ParseMode
import config
import strings
from utils.custom_filters import admin_filter, owner_filter
from utils.keyboard_utils import (
    get_admin_panel_main_keyboard, get_skip_cancel_keyboard, 
    get_admin_bot_config_menu_keyboard, get_admin_manage_premium_keyboard,
    get_admin_edit_content_menu_keyboard, get_admin_delete_content_menu_keyboard
)
from handlers.admin_handler import admin_tasks_data, clear_admin_task, \
                                   DELETE_ALL_CONFIRMATION_TEXT_1 
from utils.logger import log_bot_event, LOGGER, log_admin_action
from utils.keyboard_utils import (
    get_main_menu_keyboard, 
    get_watchlist_keyboard
)
from database.operations import get_user, get_watchlist_animes # For /watchlist and /settings


# --- /new Command (New Episodes) ---
@Client.on_message(filters.command("new"))
async def new_episodes_command_handler(client: Client, message: Message):
    await log_bot_event(client, f"User {message.from_user.id} used /new command.")
    class MockCallbackQuery:
        def __init__(self, msg, data_val):
            self.message = msg
            self.from_user = msg.from_user
            self.data = data_val
        async def answer(self, *args, **kwargs): pass # Mock answer
        async def edit_message_text(self, *args, **kwargs): # Mock edit
            return await self.message.reply_text(*args, **kwargs) # Reply instead of edit for command

    initial_msg = await message.reply_text("Fetching new episodes...")
    mock_cb = MockCallbackQuery(initial_msg, "new_episodes_list") # data needs to match regex
    await new_popular_list_handler(client, mock_cb)


# --- /popular Command ---
@Client.on_message(filters.command("popular"))
async def popular_command_handler(client: Client, message: Message):
    await log_bot_event(client, f"User {message.from_user.id} used /popular command.")
    # Similar to /new, using a mock callback approach for now
    class MockCallbackQuery:
        def __init__(self, msg, data_val):
            self.message = msg
            self.from_user = msg.from_user
            self.data = data_val
        async def answer(self, *args, **kwargs): pass
        async def edit_message_text(self, *args, **kwargs):
            return await self.message.reply_text(*args, **kwargs)

    initial_msg = await message.reply_text("Fetching popular anime...")
    mock_cb = MockCallbackQuery(initial_msg, "popular_animes_list")
    await new_popular_list_handler(client, mock_cb)


# --- /watchlist Command ---
@Client.on_message(filters.command("watchlist"))
async def watchlist_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    await log_bot_event(client, f"User {user_id} used /watchlist command.")
    
    watchlist_items, total_items = await get_watchlist_animes(user_id, page=1, per_page=config.ITEMS_PER_PAGE)
    
    if not watchlist_items:
        await message.reply_text(strings.WATCHLIST_EMPTY, reply_markup=get_main_menu_keyboard()) # Provide a way out
        return
        
    text = strings.WATCHLIST_TEXT
    reply_markup = get_watchlist_keyboard(watchlist_items, 1, total_items, config.ITEMS_PER_PAGE)
    
    await message.reply_text(text, reply_markup=reply_markup)


# --- Main Admin Panel Command ---
@Client.on_message(filters.command(["adminpanel", "admin"]) & admin_filter)
async def admin_panel_command(client: Client, message: Message):
    clear_admin_task(message.from_user.id) # Clear any previous admin task
    await message.reply_text(
        strings.ADMIN_PANEL_TEXT,
        reply_markup=get_admin_panel_main_keyboard()
    )


# --- Edit Anime ---
@Client.on_message(filters.command("editanime") & admin_filter)
async def edit_anime_command(client: Client, message: Message):
    user_id = message.from_user.id
    clear_admin_task(user_id)
    # Args can be used to directly pass anime_id if desired: /editanime <anime_id>
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        anime_id_to_edit = args[1].strip()
        # Directly proceed if anime_id is provided, or prompt if not.
        # For now, let's assume we always prompt for ID via text input state.
        admin_tasks_data[user_id] = {'task': 'edit_anime', 'step': 'anime_id_to_edit', 'data': {}}
        prompt_msg = f"You want to edit anime with ID: `{anime_id_to_edit}`. Send this ID again to confirm, or send a different ID."
        # This is a bit clunky, better to just go to the prompt.
        # The admin_text_input_handler for 'edit_anime':'anime_id_to_edit' expects the ID as input.
        await message.reply_text(
            f"Enter the <b>Anime ID</b> to edit (e.g., from DB or a future /listanimes command):",
            reply_markup=get_skip_cancel_keyboard("admin_edit_content_menu"), # Back to edit menu
            parse_mode=ParseMode.HTML
        )

    else: # No anime_id provided in command
        admin_tasks_data[user_id] = {'task': 'edit_anime', 'step': 'anime_id_to_edit', 'data': {}}
        await message.reply_text(
            "Enter the <b>Anime ID</b> to edit:",
            reply_markup=get_skip_cancel_keyboard("admin_edit_content_menu"),
            parse_mode=ParseMode.HTML
        )

# --- Delete Anime ---
@Client.on_message(filters.command("deleteanime") & admin_filter)
async def delete_anime_command(client: Client, message: Message):
    user_id = message.from_user.id
    clear_admin_task(user_id)
    admin_tasks_data[user_id] = {'task': 'delete_anime', 'step': 'anime_id_to_delete', 'data': {}}
    await message.reply_text(
        "Enter the <b>Anime ID</b> to delete (WARNING: This is destructive!):",
        reply_markup=get_skip_cancel_keyboard("admin_delete_content_menu"),
        parse_mode=ParseMode.HTML
    )

# --- Delete Episode File ---
@Client.on_message(filters.command("deleteepisode") & admin_filter)
async def delete_episode_command(client: Client, message: Message):
    user_id = message.from_user.id
    clear_admin_task(user_id)
    admin_tasks_data[user_id] = {'task': 'delete_episode', 'step': 'episode_id_to_delete', 'data': {}}
    await message.reply_text(
        "Enter the <b>Episode File ID</b> (the MongoDB _id of the episode document) to delete:",
        reply_markup=get_skip_cancel_keyboard("admin_delete_content_menu"),
        parse_mode=ParseMode.HTML
    )

# --- Grant Premium ---
@Client.on_message(filters.command("grantpremium") & admin_filter)
async def grant_premium_command(client: Client, message: Message):
    user_id = message.from_user.id
    clear_admin_task(user_id)
    # Optionally parse args: /grantpremium <user_id_or_username> <days>
    args = message.text.split(maxsplit=2) # command, target, days
    if len(args) == 3:
        target_identifier = args[1].strip()
        try:
            duration_days = int(args[2].strip())
            if duration_days <= 0:
                await message.reply_text("Duration must be a positive number of days.")
                return

            # We can directly call the confirmation logic if args are valid
            # This would bypass the admin_text_input_handler for this part
            # For consistency, let's still use the state machine
            admin_tasks_data[user_id] = {
                'task': 'grant_premium', 
                'step': 'user_identifier_prefilled', # Special step
                'data': {'target_identifier': target_identifier, 'duration_days_prefilled': duration_days}
            }
            # The admin_text_input_handler needs to be adapted for 'user_identifier_prefilled'
            # For now, simpler: always prompt.
            admin_tasks_data[user_id] = {'task': 'grant_premium', 'step': 'user_identifier', 'data': {}}
            await message.reply_text(
                "Enter User ID or @Username to grant premium to:",
                reply_markup=get_skip_cancel_keyboard("admin_grant_premium_cancel")
            )
            LOGGER.info(f"Admin {user_id} initiated /grantpremium. Prompting for user.")

        except ValueError:
            await message.reply_text("Invalid duration. Please provide a number for days. Usage: `/grantpremium <user_id_or_@username> <days>` or just `/grantpremium` to be prompted.")
            return
    else: # Not enough args, prompt normally
        admin_tasks_data[user_id] = {'task': 'grant_premium', 'step': 'user_identifier', 'data': {}}
        await message.reply_text(
            "Enter User ID or @Username to grant premium to:",
            reply_markup=get_skip_cancel_keyboard("admin_grant_premium_cancel")
        )
        LOGGER.info(f"Admin {user_id} initiated /grantpremium. Prompting for user.")


# --- Revoke Premium ---
@Client.on_message(filters.command("revokepremium") & admin_filter)
async def revoke_premium_command(client: Client, message: Message):
    user_id = message.from_user.id
    clear_admin_task(user_id)
    admin_tasks_data[user_id] = {'task': 'revoke_premium', 'step': 'user_identifier', 'data': {}}
    await message.reply_text(
        "Enter User ID or @Username to revoke premium from:",
        reply_markup=get_skip_cancel_keyboard("admin_revoke_premium_cancel")
    )

# --- List Premium Users ---
@Client.on_message(filters.command("listpremiumusers") & admin_filter)
async def list_premium_users_command(client: Client, message: Message):
    clear_admin_task(message.from_user.id)
    # This calls a direct action, not a multi-step task
    from handlers.admin_handler import admin_list_premium_users_cb # Import the callback func
    
    # We need to simulate a CallbackQuery object or adapt admin_list_premium_users_cb
    # Simpler: Re-implement the core logic here for a message command
    from database.operations import get_premium_users # Import directly
    prem_users = await get_premium_users()
    if not prem_users:
        await message.reply_text("No premium users found.")
        return

    text = "👑 **Premium Users List (via command):**\n\n"
    for u in prem_users:
        mention = f"@{u['username']}" if u.get('username') else f"ID: {u['user_id']}"
        expiry = u['premium_expiry_date'].strftime('%Y-%m-%d %H:%M UTC') if u.get('premium_expiry_date') else 'N/A'
        text += f"  - {mention} (Expires: {expiry})\n"
    
    # Handle long messages
    if len(text) > 4096:
        # Send as multiple messages or file (not implemented here for brevity)
        await message.reply_text("Premium user list is too long to display directly. Feature to send as file needed.")
    else:
        await message.reply_text(text, parse_mode=ParseMode.HTML)


# --- Bot Stats ---
@Client.on_message(filters.command("botstats") & admin_filter)
async def bot_stats_command(client: Client, message: Message):
    clear_admin_task(message.from_user.id)
    from handlers.admin_handler import admin_bot_stats_cb # Import the callback func
    # Similar to listpremiumusers, adapt or call directly if possible.
    # For now, let's re-implement simply for messages:
    from database.operations import (
        get_total_users_count, get_premium_users_count, get_anime_count, 
        get_episode_count_all_versions, get_total_downloads_recorded
    )
    from database.connection import db as database_instance # Direct import
    from datetime import datetime, timezone # Direct import

    total_u = await get_total_users_count()
    prem_u = await get_premium_users_count()
    anime_c = await get_anime_count()
    episode_v_c = await get_episode_count_all_versions()
    total_dl = await get_total_downloads_recorded()
    db_s = await database_instance.get_db_stats()
    
    current_utc_time = datetime.now(timezone.utc)
    uptime_delta = current_utc_time - client.start_time 
    uptime_str = str(uptime_delta).split('.')[0]


    stats_text = f"""📊 **Bot Statistics (via command):**
<blockquote>
Total Users: {total_u}
Premium Users: {prem_u} ({prem_u/total_u*100 if total_u else 0:.1f}%)

Total Anime Series: {anime_c}
Total Episode Files (versions): {episode_v_c}
Total Downloads Logged: {total_dl}

Database Status: {db_s}
Bot Uptime: {uptime_str} (approx since last start) 
</blockquote>
    """
    await message.reply_text(stats_text, parse_mode=ParseMode.HTML)

# --- Broadcast ---
@Client.on_message(filters.command("broadcast") & admin_filter)
async def broadcast_command(client: Client, message: Message):
    user_id = message.from_user.id
    clear_admin_task(user_id)
    
    # Check if message to broadcast is provided: /broadcast <message_text>
    message_to_broadcast_arg = message.text.split(maxsplit=1)
    if len(message_to_broadcast_arg) > 1:
        actual_message = message_to_broadcast_arg[1].strip()
        admin_tasks_data[user_id] = {
            'task': 'broadcast', 
            'step': 'confirm_broadcast', # Go directly to confirmation
            'data': {'broadcast_message': actual_message}
        }
        await message.reply_text(
            "<b>Confirm Broadcast Message:</b>\n\n" + actual_message + "\n\nSend this to all users?",
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_confirm_keyboard("admin_broadcast_execute", "admin_broadcast_cancel"),
            disable_web_page_preview=True
        )
    else: # Prompt for message
        admin_tasks_data[user_id] = {'task': 'broadcast', 'step': 'message_text', 'data': {}}
        await message.reply_text(
            "Enter the message to broadcast to all users. Supports HTML.",
            reply_markup=get_skip_cancel_keyboard("admin_broadcast_cancel")
        )

# --- Set Channel ---
@Client.on_message(filters.command("setchannel") & admin_filter)
async def set_channel_command(client: Client, message: Message):
    user_id = message.from_user.id
    clear_admin_task(user_id)
    
    args = message.text.split(maxsplit=2) # /setchannel <type> <channel_id>
    if len(args) == 3:
        channel_type = args[1].strip().lower()
        channel_id_str = args[2].strip()

        valid_types = ['request_log', 'file_log', 'bot_log']
        if channel_type not in valid_types:
            await message.reply_text(f"Invalid channel type. Valid types: {', '.join(valid_types)}")
            return
        
        try:
            channel_id_val = int(channel_id_str)
            # Directly attempt to set and test
            from database.operations import set_bot_setting # Direct import
            from utils.logger import log_admin_action # Direct import

            LOGGER.info(f"Admin {user_id} attempting to set {channel_type}_channel_id to {channel_id_val} via command.")
            await client.send_message(channel_id_val, f"📝 Test message from bot for {channel_type} logging setup (via command).")
            await set_bot_setting(f"{channel_type}_channel_id", channel_id_val)
            setattr(config, f"{channel_type.upper()}_CHANNEL_ID", channel_id_val) # Update live config
            
            success_msg = f"✅ {channel_type.replace('_',' ').title()} channel ID set to {channel_id_val}. Test message sent."
            await message.reply_text(success_msg)
            await log_admin_action(client, message.from_user.mention(style="html"), "Config Update (Command)", f"{channel_type} set to {channel_id_val}")

        except ValueError:
            await message.reply_text("Channel ID must be a number.")
        except Exception as e:
            await message.reply_text(f"Error setting channel ID: {e}. Ensure bot is admin and ID is correct.")
    else:
        # If not all args provided, guide to use the admin panel button
        await message.reply_text(
            "Usage: `/setchannel <type> <channel_id>` (e.g., `/setchannel bot_log -100...`)\n"
            "Or use the 'Bot Config' -> 'Manage Log Channels' buttons in the /admin panel.",
            reply_markup=get_admin_bot_config_menu_keyboard() # Or admin_panel_main
        )

# --- DELETE ALL DATA (Owner Only) ---
@Client.on_message(filters.command("delete_all_data") & owner_filter)
async def delete_all_data_command(client: Client, message: Message): # Renamed from _start_cmd to avoid confusion
    if not config.OWNER_ID:
        await message.reply_text("This command is disabled because OWNER_ID is not configured.")
        return

    user_id = message.from_user.id
    clear_admin_task(user_id) # Clear any previous tasks
    admin_tasks_data[user_id] = {
        'task': 'delete_all_data',
        'step': 'confirm_1',
        'data': {}
    }
    await message.reply_text(DELETE_ALL_CONFIRMATION_TEXT_1, parse_mode=ParseMode.MARKDOWN)
    await log_admin_action(client, message.from_user.mention(style="html"), "Initiated /delete_all_data", "First confirmation requested.")

# Placeholder for /managerequests command (could open the callback view)
@Client.on_message(filters.command("managerequests") & admin_filter)
async def manage_requests_command(client: Client, message: Message):
    clear_admin_task(message.from_user.id)
    from handlers.admin_handler import admin_manage_requests_cb # Import the callback func
    
    # To call a callback handler, we need to simulate a CallbackQuery.
    # This is complex. It's often easier to just direct them to use the button
    # or replicate the initial part of the callback handler's logic.

    # For now, just point them to the button or replicate the first page display:
    from database.operations import get_pending_anime_requests # Direct import
    requests, total_reqs = await get_pending_anime_requests(1, config.ITEMS_PER_PAGE)
    
    if not requests: # page 1
        await message.reply_text(
            "No pending anime requests found.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel_main")]])
        )
        return

    kb = get_request_management_keyboard(requests, 1, total_reqs, config.ITEMS_PER_PAGE)
    await message.reply_text(
        strings.REQUEST_MANAGEMENT_TEXT + " (Page 1)",
        reply_markup=kb
    )
