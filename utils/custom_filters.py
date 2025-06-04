from pyrogram import filters
from pyrogram.filters import Filter
from typing import Union, List
import config

class AdminFilter(Filter):
    async def __call__(self, _, message_or_callback_query):
        user_id = message_or_callback_query.from_user.id
        return user_id in config.ADMIN_USER_IDS

class OwnerFilter(Filter):
    async def __call__(self, _, message_or_callback_query):
        if not config.OWNER_ID: # If OWNER_ID is not set, no one is owner
            return False
        user_id = message_or_callback_query.from_user.id
        return user_id == config.OWNER_ID

owner_filter = OwnerFilter()

admin_filter = AdminFilter()

# Custom filter to check if user is premium
class PremiumFilter(Filter):
    async def __call__(self, _, message_or_callback_query):
        from database.operations import get_user # avoid circular import at module level
        user = await get_user(message_or_callback_query.from_user.id)
        return user and user.get('is_premium', False)

premium_filter = PremiumFilter()
