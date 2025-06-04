from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message
import strings # For FEATURE_NOT_IMPLEMENTED string

# This list will shrink as more features are fully implemented.
# We mainly keep it for Callbacks that might not have an immediate handler
# or if some complex commands are introduced.
UNIMPLEMENTED_CALLBACK_PREFIXES = [
    "my_watchlist_placeholder", # This will have its own handler later
    "popular_placeholder", # now has popular_animes_list
    # "help_page_placeholder", # use /help command instead or integrate with All Commands
]

# Catch-all for known placeholder callbacks
@Client.on_callback_query(filters.regex(f"^({'|'.join(UNIMPLEMENTED_CALLBACK_PREFIXES)})$"))
async def placeholder_callback_handler(client: Client, callback_query: CallbackQuery):
    feature_name = callback_query.data.replace("_placeholder", "").replace("_", " ").title()
    await callback_query.answer(strings.FEATURE_NOT_IMPLEMENTED.format(feature_name=feature_name), show_alert=True)


# Placeholder for some general commands that might not have specific button flows yet
UNIMPLEMENTED_COMMANDS = [
    "help", # Currently shown in All Commands text, could have a more detailed message
    # Add other commands if you want a placeholder message for them
]

@Client.on_message(filters.command(UNIMPLEMENTED_COMMANDS))
async def unimplemented_command_handler(client: Client, message: Message):
    command_name = message.text.split()[0].lstrip('/').title()
    await message.reply_text(strings.FEATURE_NOT_IMPLEMENTED.format(feature_name=f"'{command_name}' command details"))
