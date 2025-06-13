# handlers/premium_handler.py
import logging
import asyncio
from typing import Union, List, Dict, Any # Import type hints
from pyrogram import Client, filters # Import Pyrogram core and filters
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.errors import (
    FloodWait, MessageIdInvalid, MessageNotModified # Specific errors
)

# Import config constants for premium plans
import config
# Import strings constants for messages
import strings

# Import database models and utilities (User needed to maybe display current status?)
from database.mongo_db import MongoDB # Access MongoDB
from database.models import User # Import User model
from database.mongo_db import get_user_state # State management if needed (unlikely for simple display)

# Import helpers
from handlers.common_handlers import get_user, edit_or_send_message # Needed helpers


premium_logger = logging.getLogger(__name__)

# --- Premium States (Simple Display) ---
# handler: "premium"
class PremiumState:
    VIEWING_INFO = "premium_viewing_info" # Displaying premium information


# --- Entry Point for Premium Info ---

@Client.on_callback_query(filters.regex("^menu_premium$") & filters.private)
@Client.on_message(filters.command("premium") & filters.private)
async def premium_info_command_or_callback(client: Client, update: Union[Message, CallbackQuery]):
    user_id = update.from_user.id
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    message_id = update.id if isinstance(update, Message) else update.message.id
    is_callback = isinstance(update, CallbackQuery)

    try:
         # Answer callback if it is one
         if is_callback: await client.answer_callback_query(message.id)
     except Exception: premium_logger.warning(f"Failed to answer callback menu_premium from user {user_id}")


    # Optional: Get user to maybe display current premium status at the top
    user = await MongoDB.users_collection().find_one({"user_id": user_id}) # Get user doc
    if user is None:
         premium_logger.error(f"User {user_id} not found in DB during premium info access.")
         await edit_or_send_message(client, chat_id, message_id if is_callback else None, strings.DB_ERROR, disable_web_page_preview=True)
         return


    # No specific state needed unless navigating through plans, but a viewing state can be useful
    user_state = await MongoDB.get_user_state(user_id)
    # Clear previous state unless already viewing premium info?
    if user_state and not (user_state.handler == "premium" and user_state.step == PremiumState.VIEWING_INFO):
         premium_logger.debug(f"User {user_id} in state {user_state.handler}:{user_state.step} clicking premium. Clearing old state.")
         await MongoDB.clear_user_state(user_id)

    # Set or ensure viewing info state
    await MongoDB.set_user_state(user_id, "premium", PremiumState.VIEWING_INFO, data={})


    # Build the premium information message
    menu_text = strings.PREMIUM_INFO_TITLE + "\n\n" + strings.PREMIUM_INFO_HEADER.format() + "\n" # Start with header


    # Iterate through premium plans defined in config
    premium_plans = config.PREMIUM_PLANS # Get dictionary of plans
    if not premium_plans:
         menu_text += "😔 No premium plans are currently configured.\n\n"
    else:
         # Sort plans by some criteria (e.g., duration, price?) or display order if keys have a pattern.
         # Let's sort by keys alphabetically for consistency.
         plan_ids = sorted(premium_plans.keys())

         for plan_id in plan_ids:
              plan_details = premium_plans[plan_id] # Get plan dictionary

              # Format plan details
              features_list = plan_details.get("features", [])
              formatted_features = ""
              if features_list:
                   # Use blockquote for bullet points in HTML
                   formatted_features = "<blockquote>" + "<br>".join([f"• {feature}" for feature in features_list]) + "</blockquote>"

              plan_text = strings.PREMIUM_PLAN_FORMAT.format(
                   plan_name=plan_details.get("name", plan_id.replace('_', ' ').title()), # Plan name, fallback to formatted ID
                   price=plan_details.get("price", "Price unknown"),
                   duration=plan_details.get("duration_days", "Unknown") if plan_details.get("duration_days") is not None else "Unlimited", # Handle unlimited duration? Or specific display
                   features_list=formatted_features,
                   description=plan_details.get("description", "")
              )
              menu_text += plan_text + "\n---\n" # Add plan info + separator


         # Add general purchase instructions using placeholder
         # Combine instructions for all plans if needed, or put specific info in each plan's 'payment_info' field.
         # Sticking to a single block for general instructions here, drawing from first plan as example placeholder.
         first_plan_details = premium_plans.get(plan_ids[0]) if plan_ids else None
         if first_plan_details and first_plan_details.get("payment_info"):
             menu_text += strings.PREMIUM_PURCHASE_INSTRUCTIONS.format(
                 payment_info=first_plan_details.get("payment_info") # Use payment info from first plan example
                 # You might want to format specific payment info for EACH plan or have generic text
             )

    # Add Navigation buttons: Back to Main Menu
    buttons = [[InlineKeyboardButton(strings.BUTTON_HOME, callback_data="menu_home")]]
    reply_markup = InlineKeyboardMarkup(buttons)

    # Display the premium info message and keyboard.
    # If coming from command, reply. If from callback, edit.
    target_message_id = message_id if is_callback else None
    await edit_or_send_message(client, chat_id, target_message_id, menu_text, reply_markup, disable_web_page_preview=True)

    # State is now "premium":"viewing_info", stays until user navigates away.
