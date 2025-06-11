### FILENAME: `database/mongo_db.py`

```python
# database/mongo_db.py
import logging
from pymongo import MongoClient, ReturnDocument, errors as mongo_errors
from pymongo.operations import UpdateOne
from datetime import datetime, timedelta
import pytz # For timezone-aware datetime objects if needed, especially for expiry

from configs import settings

logger = logging.getLogger(__name__)

# --- Database Connection ---
try:
    client = MongoClient(settings.DATABASE_URL)
    db = client[settings.DATABASE_NAME]
    logger.info(f"✅ Successfully connected to MongoDB: {settings.DATABASE_NAME}")

    # --- Collections ---
    users_collection = db["users"]
    anime_collection = db["anime"]
    requests_collection = db["requests"] # If you decide to log requests to DB too
    generated_referral_codes_collection = db["generated_referral_codes"]
    
                return {"new": False, "tokens_awarded": 0, "user_doc": user_data} # No tokens awarded for existing user login
            except Exception as e:
                logger.error(f"Error updating user {user_id}: {e}")
                return None


    async def get_user(self, user_id: int):
        """Fetches a user by their Telegram ID."""
        try:
            return await self.users_collection.find_one({"telegram_id": user_id})
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None

    async def update_user_tokens(self, user_id: int, token_change: int):
        """Increments or decrements user tokens. token_change can be positive or negative."""
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id},
                {"$inc": {"download_tokens": token_change}}
            )
            return result.modified_count > 0
        except    # You might want to create indexes here for commonly queried fields
    # Example:
    users_collection.create_index("telegram_id", unique=True)
    anime_collection.create_index([("title_english", "text")], name="anime_title_text_index") # For fuzzy text search
    anime_collection.create_index("genres")
    anime_collection.create_index("status")
    anime_collection.create_index("release_year")
    generated_referral_codes_collection.create_index("referral_code", unique=True)
    generated_referral_codes_collection.create_index("creator_user_id")
    logger.info("MongoDB indexes checked/created.")

except mongo_errors.ConnectionFailure as e:
    logger.critical(f"❌ MongoDB Connection Failure: {e}. Bot cannot operate without database.")
    # In a real scenario, you might want to retry or exit gracefully
    # For now, this will prevent the bot from starting properly if DB is down.
    raise  # Re-raise the exception to halt execution if DB connection fails on startup
except Exception Exception as e:
            logger.error(f"Error updating tokens for user {user_id}: {e}")
            return False

    async def grant_premium(self, user_id: int, duration_days: int):
        """Grants premium status to a user for a specified number of days."""
        now = datetime.now(pytz.utc)
        expiry_date = now + timedelta(days=duration_days)
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id},
                {"$set": {"premium_status": True, "premium_expiry_date": expiry_date}}
            )
            return result.modified_count > 0, expiry_date
        except Exception as e:
            logger.error(f"Error granting premium to user {user_id}: {e}")
            return False, None

    async def revoke_premium(self, user_id: int):
        """Revokes premium status from a user."""
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id},
                {"$set": {"premium_status": False, "premium_expiry_date": None}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error revoking premium for user {user_id}: {e}")
            return False

    async def get_all_user_ids(self, premium as e:
    logger.critical(f"❌ An unexpected error occurred during MongoDB setup: {e}")
    raise


# --- User Management ---
async def add_or_update_user(user_data):
    """
    Adds a new user or updates existing user's first_name, username, last_active_date.
    Initializes tokens for new users.
    Args:
        user_data (telegram.User): Telegram User object.
    Returns:
        dict: The user document from the database.
    """
    now = datetime.utcnow()
    telegram_id = user_data.id
    first_name = user_data.first_name
    username = user_data.username # Can be None

    query = {"telegram_id": telegram_id}
    # Initial values for a new user
    new_user_values = {
        "first_name": first_name,
        "username": username,
        "download_tokens": settings.TOKENS_FOR_NEW_USER_DIRECT_START, # Default tokens
        "premium_status": False,
        "premium_expiry_date": None,
        "watchlist": [],
        "join_date": now,
        "last_active_date": now,
        "tokens_earned_today": 0,
        "last_token_earn_reset_date": now.date() # Store only date part for daily reset logic
    }
    update_values = {
        "$set": {
            "first_name": first_name,
            "username": username,
            "last_active_date": now
        },
        "$setOnInsert": new__only: bool = False, active_only_days: int = 0):
        """Gets all user IDs for broadcasting or other purposes.
           If premium_only is True, returns only premium users.
           If active_only_days > 0, returns users active in last N days.
        """
        query = {}
        if premium_only:
            query["premium_status"] = True
        if active_only_days > 0:
            active_since = datetime.now(pytz.utc) - timedelta(days=active_only_days)
            query["last_active_date"] = {"$gte": active_since}
        
        user_ids = []
        try:
            cursor = self.users_collection.find(query, {"telegram_id": 1})
            async for user_doc in cursor:
                user_ids.append(user_doc["telegram_id"])
            return user_ids
        except Exception as e:
            logger.error(f"Error fetching user IDs: {e}")
            return []

    async def check_and_deactivate_expired_premiums(self):
        """Finds users whose premium has expired and deactivates it."""
        now = datetime.now(pytz.utc)
        query = {"premium_status": True, "premium_expiry_date": {"$lt": now}}
        update = {"$set": {"premium_status": False, "premium_expiry_date": None}}
        updated_users_ids = []
        try:
            # Find users whose premium expired to notify them later if needed
            cursor = self.users_collection.find(query,user_values # These fields are only set if it's a new document
    }

    try:
        user_doc = users_collection.find_one_and_update(
            query,
            update_values,
            upsert=True, # Create if doesn't exist
            return_document=ReturnDocument.AFTER
        )
        return user_doc
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error adding/updating user {telegram_id}: {e}")
        return None

async def get_user(telegram_id: int):
    try:
        return users_collection.find_one({"telegram_id": telegram_id})
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting user {telegram_id}: {e}")
        return None

async def update_user_tokens(telegram_id: int, token_change: int):
    """Increments or decrements user tokens."""
    try:
        result = users_collection.find_one_and_update(
            {"telegram_id": telegram_id},
            {"$inc": {"download_tokens": token_change}},
            return_document=ReturnDocument.AFTER
        )
        return result["download_tokens"] if result else None
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error updating tokens for user {telegram_id}: {e}")
        return None

async def grant_premium_to_user(telegram_id: int, duration_days: int):
    try:
        expiry_date = datetime.utcnow() + timedelta(days=duration_days)
        users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"premium_status": True, "premium_expiry_date": expiry_date}}
 {"telegram_id": 1})
            async for user in cursor:
                updated_users_ids.append(user["telegram_id"])
            
            if updated_users_ids:
                result = await self.users_collection.update_many(query, update)
                logger.info(f"Deactivated premium for {result.modified_count} users whose subscription expired.")
                return updated_users_ids
            return []
        except Exception as e:
            logger.error(f"Error deactivating expired premiums: {e}")
            return []
    
    async def update_daily_token_earn(self, user_id: int, tokens_earned: int):
        now_date = datetime.now(pytz.utc).date()
        try:
            await self.users_collection.update_one(
                {"telegram_id": user_id},
                {"$inc": {"tokens_earned_today": tokens_earned}, "$set": {"last_token_earn_reset_date": now_date}}
            )
            return True
        except Exception as e:
            logger.error(f"Error updating daily token earn for user {user_id}: {e}")
            return False


    # --- Watchlist Management ---
    async def add_to_watchlist(self, user_id: int, anime_id: str): # anime_id is ObjectId as string
        """Adds an anime (by its MongoDB _id string) to a user's watchlist."""
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id},
                {"$addToSet": {"watchlist": anime_id}} # $addToSet prevents duplicates
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error adding anime {anime_id} to watchlist for user {user_id}: {e}")
            return False

    async def remove_from_watchlist(self, user_id: int        )
        return expiry_date
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error granting premium to user {telegram_id}: {e}")
        return None

async def revoke_premium_from_user(telegram_id: int):
    try:
        users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"premium_status": False, "premium_expiry_date": None}}
        )
        return True
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error revoking premium from user {telegram_id}: {e}")
        return False

async def check_and_reset_daily_token_earn_limit(telegram_id: int):
    """Checks if today is a new day compared to last reset, and resets if so.
       Returns the user doc after potential reset.
    """
    today_date = datetime.utcnow().date()
    user = await get_user(telegram_id)
    if not user:
        return None

    last_reset = user.get("last_token_earn_reset_date")
    # If last_reset is already a date object or None
    if last_reset is None or (isinstance(last_reset, datetime) and last_reset.date() < today_date) or \
       (isinstance(last_reset, type(today_date)) and last_reset < today_date) : # Handles both datetime and date obj
        try:
            users_collection.update_one(
                {"telegram_id": telegram_id},
                {"$set": {"tokens_earned_today": 0, "last_token_earn_reset_date": today_date}}
            )
            user["tokens_earned_today"] = 0 # Update in-memory user doc
            user["last_token_earn_reset_date"] = today_date
            logger.info(f"Daily token earn limit reset for user {telegram_id}")
        except mongo_errors., anime_id: str):
        """Removes an anime from a user's watchlist."""
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id},
                {"$pull": {"watchlist": anime_id}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error removing anime {anime_id} from watchlist for user {user_id}: {e}")
            return False

    async def get_watchlist_anime_ids(self, user_id: int):
        """Gets a list of anime _id strings from user's watchlist."""
        user = await self.get_user(user_id)
        return user.get("watchlist", []) if user else []

    async def get_watchlist_animes_details(self, user_id: int, page: int = 1, per_page: int = 5):
        """Gets paginated full anime details for items in a user's watchlist."""
        anime_ids = await self.get_watchlist_anime_ids(user_id)
        if not anime_ids:
            return [], 0 # Empty list, 0 total items
        
        # Convert string IDs to ObjectIds for MongoDB query if necessary
        # from bson import ObjectId
        # object_ids = [ObjectId(aid) for aid in anime_ids]
        # query = {"_id": {"$in": object_ids}}
        # For simplicity if anime_id in watchlist is already _id from anime_collection
        # then the query doesn't need ObjectId conversion here if _id field is directly matched
        # But anime_collection typically stores _id as ObjectId. So conversion *is* usually needed if anime_id in watchlist is stored as string.
        # Assuming anime_id in watchlist is a string representation of ObjectId.

        # Let's assume anime_id is a string, which means you need to getPyMongoError as e:
            logger.error(f"MongoDB error resetting daily token earn limit for user {telegram_id}: {e}")
    return user

async def increment_tokens_earned_today(telegram_id: int, amount: int):
    try:
        users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$inc": {"tokens_earned_today": amount}}
        )
        return True
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error incrementing tokens_earned_today for user {telegram_id}: {e}")
        return False

# --- Watchlist Management ---
async def add_to_watchlist(telegram_id: int, anime_id: str): # Assuming anime_id is ObjectId as string
    try:
        users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$addToSet": {"watchlist": anime_id}} # $addToSet prevents duplicates
        )
        return True
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error adding to watchlist for user {telegram_id}: {e}")
        return False

async def remove_from_watchlist(telegram_id: int, anime_id: str):
    try:
        users_collection.update_one(
            {"telegram_id": telegram_id},
            {"$pull": {"watchlist": anime_id}}
        )
        return True
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error removing from watchlist for user {telegram_id}: {e}")
        return False

async def get_watchlist(telegram_id: int, page: int, limit: int):
    try:
        user_doc = users_collection.find_one(
            {"telegram_id": telegram_id},
            {"watchlist": {"$slice": [(page - 1) * limit, limit]}} # For pagination directly in query
        )
        if user_doc and user_doc.get("watchlist"):
            anime_ids = user_doc["watchlist"]
            # Fetch full anime details for these IDs
            anime_details = list(anime_collection.find({"_id": {"$in": [ObjectId(aid) for aid in anime_ids]}}))
            total_items = await count_watchlist_items(telegram_id) # Need a separate count for total
            return anime_details, total_items
        return [], 0
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting watchlist for user {telegram_id}: {e}")
        return [], 0
    except Exception as e: # Catch ObjectId errors too
        logger.error(f"Error converting watchlist anime_ids for user {telegram_id}: {e}")
        return [], 0


async def count_watchlist_items(telegram_id: int):
    try:
        user_doc = users_collection.find_one({"telegram_id": telegram_id}, {"watchlist": 1})
        return len(user_doc.get("watchlist", [])) if user_doc else 0
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error counting watchlist for user {telegram_id}: {e}")
        return 0

# these ObjectIds or structure schema carefully
        # For this example, let's proceed assuming they can be matched correctly, but in real use, handle ID types.
        
        total_items = len(anime_ids)
        # Fetching details for each ID separately. This is not optimal for large watchlists.
        # A better approach would be one query to anime_collection with $in, then client-side pagination if MongoDB doesn't do skip/limit efficiently on $in with large arrays.
        # Or, denormalize essential anime info into the watchlist array if performance becomes an issue.
        # For now, a simpler, less performant approach:
        
        # This implementation requires that anime_id stored in watchlist IS the string of anime_collection._id
        # And we fetch details based on these. The provided anime_id *IS* string
        paginated_ids = anime_ids[(page - 1) * per_page : page * per_page]
        
        animes_details = []
        if paginated_ids:
            try:
                # To search by _id string, you typically store the string version or use ObjectId correctly
                # Assuming `_id` in `anime_collection` is indeed ObjectId, and `anime_id` in watchlist is string
                # This direct query will not work if anime_id is the _id from anime_collection which is ObjectId type.
                # A common practice is storing ObjectId as a field itself, or _id is always ObjectId type.
                # Let's assume for this query, anime_collection could have a unique `anime_realm_id` as string if _id is always ObjectId.
                # For this function, let's assume we retrieve anime one by one based on `paginated_ids` string.
                
                # If watchlist stores string versions of ObjectIds:
                from bson import ObjectId
                object_ids_to_fetch = [ObjectId(aid_str) for aid_str in paginated_ids]
                cursor = self.anime_collection.find({"_id": {"$in": object_ids_to_fetch}})
                async for anime_doc in cursor:
                    animes_details.append(anime_doc)
                
                # To maintain order from watchlist, you might need to re-order animes_details based on paginated_ids.
                # MongoDB $in does not guarantee order preservation from the $in array.
                ordered_details = sorted(animes_details, key=lambda x: paginated_ids.index(str(x['_id'])))
 --- Anime Content Management ---
from bson.objectid import ObjectId # Import here to avoid circular if used at top level with models

async def add_anime(anime_data: dict):
    """ Adds a new anime. anime_data should match schema. """
    try:
        anime_data["added_date"] = datetime.utcnow()
        anime_data["download_count"] = 0 # Initialize download count
        result = anime_collection.insert_one(anime_data)
        return result.inserted_id
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error adding anime '{anime_data.get('title_english')}': {e}")
        return None

async def get_anime_by_id(anime_id: str):
    try:
        return anime_collection.find_one({"_id": ObjectId(anime_id)})
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting anime by ID {anime_id}: {e}")
        return None
    except Exception as e: # bson.errors.InvalidId
        logger.error(f"Invalid anime ID format {anime_id}: {e}")
        return None


async def find_anime_by_title_fuzzy(title_query: str, limit: int, page: int):
    """
    Searches anime by title_english using MongoDB text search.
    Requires a text index on title_english.
    """
    skip = (page - 1) * limit
    try:
        # Basic text search (less fuzzy than Python's fuzzywuzzy, but good for starts)
        # For more advanced fuzziness, you might query a broader set then filter with fuzzywuzzy in Python
        # or explore MongoDB Atlas Search features.
        cursor = anime_collection.find(
            {"$text": {"$search": title_query}},
            {"score": {"$meta": "textScore"}} # For sorting by relevance
        ).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(limit)
        
        results = list(cursor)
        
        # Get total count for pagination
        # Note: count_documents with $text can be tricky / less efficient.
        # A simpler approach if exact count isn't needed or for smaller datasets:
        # total_count = anime_collection.count_documents({"$text": {"$search": title_query}})
        # For larger datasets, counting after retrieving a slightly larger set and then slicing might be better,
        # or accept that pagination with text search relevance might not show an exact total page count.
        # For now, let's assume we can count based on the query for pagination.
        total_count_query = {"$text": {"$search": title_query}}
        total_count = anime_collection.count_documents(total_count_query)

        return results, total_count
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error finding anime by title '{title_query}': {e}")
        return [], 0

async def update_anime_details(anime_id: str, update_data: dict):
    """ Updates core anime details. """
    try:
        update_data["last_updated_date"] = datetime.utcnow()
        result = anime_collection.update_one(
            {"_id": ObjectId(anime                
                return ordered_details, total_items
            except Exception as e:
                logger.error(f"Error fetching watchlist anime details for user {user_id}: {e}")
                return [], total_items
        return [], total_items

    # --- Referral Code Management ---
    async def create_referral_code(self, creator_user_id: int, referral_code: str, tokens_to_award: int, expiry_date: datetime):
        doc = {
            "referral_code": referral_code,
            "creator_user_id": creator_user_id,
            "tokens_to_award": tokens_to_award,
            "expiry_date": expiry_date, # Should be timezone-aware UTC
            "is_claimed": False,
            "claimed_by_user_id": None,
            "creation_date": datetime.now(pytz.utc)
        }
        try:
            await self.referral_codes_collection.insert_one(doc)
            return True
        except Exception as e:
            logger.error(f"Error creating referral code {referral_code}: {e}")
            return False

    async def get_referral_code(self, referral_code_str: str):
        """Fetches an active, unclaimed referral code."""
        now = datetime.now(pytz.utc)
        try:
            return await self.referral_codes_collection.find_one({
                "referral_code": referral_code_str,
                "is_claimed": False,
                "expiry_date": {"$gte": now} # Ensure it's not expired
            })
        except Exception as e:
            logger.error(f"Error fetching referral code {referral_code_str}: {e}")
            return None

    async def claim_referral_code(self, referral_code_str: str, claimed_by_user_id: int):
        """Marks a referral code as claimed."""
        try:
            result = await self.referral_codes_collection.update_one(
                {"referral_code": referral_code_str, "is_claimed": False}, # Ensure it's not already claimed by race condition
                {"$set": {"is_claimed": True, "claimed_by_user_id": claimed_by_user_id}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error claiming referral code {referral_code_str} by user {claimed_by_user_id}: {e}")
            return False

    # --- Anime Data Management (Admin) ---
    async def add_anime(self, anime_doc: dict):
        """Adds a new anime document."""
        anime_doc["added_date"] = datetime.now(pytz.utc)
        anime_doc["download_count"] = 0 # Initialize download count
        try:
            result = await self.anime_collection.insert_one(anime_doc)
            return str(result.inserted_id) # Return the ID of the newly added anime
        except Exception as e:
            logger.error(f"Error adding anime '{anime_doc.get('title_english')}': {e}")
            return None

    async def get_anime_by_id_str(self, anime_id_str: str):
        """Fetches an anime by its string representation of MongoDB _id."""
        from bson import ObjectId, errors
        try:
            obj_id = ObjectId(anime_id_str)
            return await self.anime_collection.find_one({"_id": obj_id})
        except errors.InvalidId:
            logger.warning(f"Invalid ObjectId string format: {anime_id_str}")
            return None
        except Exception as e:
            logger.error(f"Error fetching anime by id_str {anime_id_str}: {e}")
            return None

    async def_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error updating anime details {anime_id}: {e}")
        return False

async def add_episode_to_season(anime_id: str, season_number: int, episode_data: dict):
    """ Adds an episode to a specific season of an anime. """
    try:
        # Ensure episode_data includes at least episode_number and an empty versions array
        episode_data.setdefault("versions", [])
        result = anime_collection.update_one(
            {"_id": ObjectId(anime_id), "seasons.season_number": season_number},
            {"$push": {"seasons.$.episodes": episode_data}}
        )
        # If season doesn't exist, this won't work directly. Might need to $addToSet for seasons first
        # Or ensure season structure is created when anime is added or when first managing episodes for it.
        return result.modified_count > 0
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error adding episode to anime {anime_id} S{season_number}: {e}")
        return False

async def add_file_version_to_episode(anime_id: str, season_number: int, episode_number: int, version_data: dict):
    """ Adds a file version to a specific episode. """
    try:
        version_data["upload_date"] = datetime.utcnow()
        result = anime_collection.update_one(
            {"_id": ObjectId(anime_id), "seasons.season_number": season_number, "seasons.episodes.episode_number": episode_number},
            {"$push": {"seasons.$[s].episodes.$[e].versions": version_data}},
            array_filters=[
                {"s.season_number": season_number},
                {"e.episode_number": episode_number}
            ]
        )
        return result.modified_count > 0
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error adding file version to anime {anime_id} S{season_number}E{episode_number}: {e}")
        return False

async def set_episode_air_date(anime_id: str, season_number: int, episode_number: int, air_date: datetime | None):
    try:
        result = anime_collection.update_one(
            {"_id": ObjectId(anime_id), "seasons.season_number": season_number, "seasons.episodes.episode_number": episode_number},
            {"$set": {"seasons.$[s].episodes.$[e].air_date": air_date}},
            array_filters=[
                {"s.season_number": season_number},
                {"e.episode_number": episode_number}
            ]
        )
        if air_date and result.modified_count > 0: # If setting an air date, remove files for that episode
            await clear_episode_file_versions(anime_id, season_number, episode_number)
        return result.modified_count > 0
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error setting air date for anime {anime_id} S{season_number}E{episode_number}: {e}")
        return False

async def clear_episode_file_versions(anime_id: str, season_number: int, episode_number: int):
    """Clears all file versions for an episode, useful when setting an air_date."""
    try:
        result = anime_collection.update_one(
            {"_id": ObjectId(anime_id), "seasons.season_number": season_number, "seasons.episodes.episode_number": episode_number},
            {"$set": {"seasons.$[s].episodes.$[e].versions": []}}, # Set versions to empty array
            array_filters=[
                {"s.season_number": season_number},
                {"e.episode_number": episode_number}
            ]
        )
        return result.modified_count > 0
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error clearing file versions for anime {anime_id} S{season_number}E{episode_number}: update_anime_details(self, anime_id_str: str, update_data: dict):
        """Updates core details of an anime."""
        from bson import ObjectId
        obj_id = ObjectId(anime_id_str)
        try:
            result = await self.anime_collection.update_one(
                {"_id": obj_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating anime {anime_id_str}: {e}")
            return False

    async def add_episode_to_season(self, anime_id_str: str, season_number: int, episode_doc: dict):
        """Adds an episode document to a specific season of an anime."""
        from bson import ObjectId
        obj_id = ObjectId(anime_id_str)
        # Ensure versions in episode_doc have upload_date
        if "versions" in episode_doc:
            for version in episode_doc["versions"]:
                version["upload_date"] = datetime.now(pytz.utc)

        try:
            # Check if season exists, if not, create it with the episode
            # This logic needs to be robust, using $push to an existing season's episodes array,
            # or creating the season array element if it's the first episode of that season.

            # Find the anime and the specific season
            anime = await self.anime_collection.find_one({"_id": obj_id, "seasons.season_number": season_number})

            if anime:
                # Season exists, push to its episodes array
                result = await self.anime_collection.update_one(
                    {"_id": obj_id, "seasons.season_number": season_number},
                    {"$push": {"seasons.$.episodes": episode_doc}}
                )
            else:
                # Season does not exist, add it with the new episode
                season_doc = {"season_number": season_number, "episodes": [episode_doc]}
                result = await self.anime_collection.update_one(
                    {"_id": obj_id},
                    {"$push": {"seasons": season_doc}}
                )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error adding episode to S{season_number} of anime {anime_id_str}: {e}")
            return False

    async def add_file_version_to_episode(self, anime_id_str: str, season_number: int, episode_number: int, version_doc: dict):
        from bson import ObjectId
        obj_id = ObjectId(anime_id_str)
        version_doc["upload_date"] = datetime.now(pytz.utc)
        try:
            # This is complex with nested arrays. Query for the specific episode.
            # Then $push to its versions array.
            # Using positional operator $ with arrayFilters for targeted update in nested arrays
            result = await self.anime_collection.update_one(
                {"_id": obj_id, "seasons.season_number": season_number, "seasons.episodes.episode_number": episode_number},
                {"$push": {"seasons.$[s].episodes.$[e].versions": version_doc}},
                array_filters=[
                    {"s.season_number": season_number},
                    {"e.episode_number": episode_number}
                ]
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error adding file version to S{season_number}E{episode_number} of anime {anime_id_str}: {e}")
            return False

    # (Add similar methods for remove_episode, remove_file_version, delete_anime, etc.)

    # --- Anime Search and Browsing ---
    async def search_anime_by_title(self, query: str, page: int = 1, per_page: int = 5):
        """Searches anime by title_english using text index. Case-insensitive."""
        skip_count = (page - 1) * per_page
 {e}")
        return False


async def increment_anime_download_count(anime_id: str):
    try:
        anime_collection.update_one({"_id": ObjectId(anime_id)}, {"$inc": {"download_count": 1}})
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error incrementing download count for anime {anime_id}: {e}")

async def get_popular_anime(limit: int, page: int):
    skip = (page - 1) * limit
    try:
        cursor = anime_collection.find().sort("download_count", -1).skip(skip).limit(limit)
        total_count = anime_collection.count_documents({}) # Count all anime for pagination of popular
        return list(cursor), total_count
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting popular anime: {e}")
        return [], 0

async def get_latest_episodes_anime_ids(limit: int, page: int):
    """
    This is complex. It should ideally find anime that had episodes whose file_versions were recently updated.
    A simpler approach for now: Get recently added *anime series*.
    True latest episodes require tracking episode update timestamps or querying nested arrays effectively.
    
    Simplified: Get anime series sorted by their own last_updated_date or added_date if more episodes were added.
    Let's sort by anime 'last_updated_date' (which admin flow should update when new eps/versions added)
    """
    skip = (page - 1) * limit
    try:
        # This will get recently updated *anime series*, not individual episodes.
        # Getting individual latest episodes correctly with pagination is more involved
        # and might need denormalization or different schema for "latest_episodes" collection.
        cursor = anime_collection.find().sort("last_updated_date", -1).skip(skip).limit(limit)
        total_count = anime_collection.count_documents({})
        return list(cursor), total_count
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting latest anime (series): {e}")
        return [], 0

async def get_anime_by_genre(genre: str, limit: int, page: int):
    skip = (page - 1) * limit
    query = {"genres": genre}
    try:
        cursor = anime_collection.find(query).skip(skip).limit(limit)
        total_count = anime_collection.count_documents(query)
        return list(cursor), total_count
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting anime by genre '{genre}': {e}")
        return [], 0

async def get_anime_by_status(status: str, limit: int, page: int):
    skip = (page - 1) * limit
    query = {"status": status}
    try:
        cursor = anime_collection.find(query).skip(skip).limit(limit)
        total_count = anime_collection.count_documents(query)
        return list(cursor), total_count
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting anime by status '{status}': {e}")
        return [], 0


# --- Referral Code Management ---
async def create_referral_code(creator_user_id: int, referral_code: str, tokens_to_award: int, expiry_datetime: datetime):
    try:
        generated_referral_codes_collection.insert_one({
            "referral_code": referral_code,
            "creator_user_id": creator_user_id,
            "tokens_to_award": tokens_to_award,
            "expiry_date": expiry_datetime,
            "is_claimed": False,
            "claimed_by_user_id": None,
            "creation_date": datetime.utcnow()
        })
        return True
    except mongo_errors.DuplicateKeyError:
        logger.warning(f"Attempted to insert duplicate referral code: {referral_code}")
        return False # Or handle by regenerating code
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error creating referral code {referral_code}: {e}")
        return False

async def get_referral_code_data(referral_code: str):
    try:
        return generated_referral_codes_collection.find_one({"referral_code": referral_code})
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting referral code data {referral_code}: {e}")
        return None

async def mark_referral_code_claimed(referral_code: str, claimed_by_user_id: int):
    try:
        result = generated_referral_codes_collection.update_one(
            {"referral_code": referral_code, "is_claimed": False}, # Ensure it's not already claimed
            {"$set": {"is_claimed": True, "claimed_by_user_id": claimed        try:
            # Using text search (ensure text index on title_english is created)
            # MongoDB text search gives a score, we can sort by it
            cursor = self.anime_collection.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).skip(skip_count).limit(per_page)
            
            # Count total matching documents for pagination
            # The count for a text search is not straightforward without running it again or a different way
            # For simplicity, we might get more results and paginate client-side, or do a separate count.
            # Let's try counting:
            # total_items = await self.anime_collection.count_documents({"$text": {"$search": query}}) # May not be most efficient way

            # To avoid a second query for count with text search, which can be tricky,
            # we often fetch a bit more (e.g., per_page + 1) to see if there's a next page.
            # Or, we make a trade-off. For now, simple count (might be slow):
            
            # Alternative: simpler regex search (case-insensitive) if text search isn't tuned
            # regex_query = {"title_english": {"$regex": query, "$options": "i"}}
            # cursor = self.anime_collection.find(regex_query).skip(skip_count).limit(per_page)
            # total_items = await self.anime_collection.count_documents(regex_query)

            # Let's stick with text search for "fuzzy" capabilities
            results = [doc async for doc in cursor]
            
            # Rough way to get total_items with text search for pagination. This might not be perfectly accurate.
            # A more robust pagination for text search often involves fetching IDs and then details.
            # Or not showing total pages for text search, just prev/next.
            # Let's assume `count_documents` works well enough for now for text search total.
            total_items = await self.anime_collection.count_documents({"$text": {"$search": query}})

            return results, total_items
        except Exception as e:
            logger.error(f"Error searching anime with query '{query}': {e}")
            return [], 0

    async def get_animes_by_filter(self, filter_criteria: dict, page: int = 1, per_page: int = 5, sort_by: list | None = None):
        """Generic function to get anime by various filters with pagination and sorting."""
        skip_count = (page - 1) * per_page
        if sort_by is None:
            sort_by = [("title_english", ASCENDING)] # Default sort

        try:
            cursor = self.anime_collection.find(filter_criteria).sort(sort_by).skip(skip_count).limit(per_page)
            results = [doc async for doc in cursor]
            total_items = await self.anime_collection.count_documents(filter_criteria)
            return results, total_items
        except Exception as e:
            logger.error(f"Error fetching animes with filter {filter_criteria}: {e}")
            return [], 0
            
    async def get_latest_episodes_anime(self, page: int = 1, per_page: int = 5):
        """
        Gets anime that had episodes added/updated recently.
        This is tricky. We need to look at 'upload_date' inside episode versions.
        One way is to unwind, sort, group. Or have a last_episode_update_date at the anime level.
        For simplicity now: get animes sorted by their own 'last_updated_date' if we maintain that.
        If we don't maintain 'last_updated_date' on anime doc when episodes are added:
        This function needs to be a complex aggregation or this feature might need re-thinking.
        
        Let's assume an `anime_doc["last_content_update"]` field that is set on the anime document
        whenever a new episode or version is added.
        """
        query = {} # Potentially filter by status like 'Ongoing'
        sort_criteria = [("last_content_update", DESCENDING), ("title_english", ASCENDING)]
        return await self.get_animes_by_filter(query, page, per_page, sort_by=sort_criteria)

    async def get_popular_animes(_by_user_id}}
        )
        return result.modified_count > 0 # True if successfully marked
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error marking referral code {referral_code} as claimed: {e}")
        return False

# --- Admin Specific DB Functions ---
async def get_all_user_ids():
    """ Returns a list of all telegram_ids for broadcasting. """
    try:
        cursor = users_collection.find({}, {"telegram_id": 1, "_id": 0})
        return [doc["telegram_id"] for doc in cursor]
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error getting all user IDs for broadcast: {e}")
        return []

async def count_total_users():
    try:
        return users_collection.count_documents({})
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error counting total users: {e}")
        return 0

async def count_premium_users():
    try:
        return users_collection.count_documents({"premium_status": True, "premium_expiry_date": {"$gte": datetime.utcnow()}})
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error counting premium users: {e}")
        return 0

# (Add more admin stat functions as needed, e.g., total anime, total downloads, etc.)

# --- Request Logging (Optional, as main log is to channel) ---
async def log_anime_request_to_db(user_id: int, user_first_name: str, anime_title: str, is_premium: bool):
    """ Logs a request to the database. """
    if not settings.REQUEST_CHANNEL_ID: # If channel logging is primary, DB log might be optional
        pass # Or decide if DB log is always wanted

    try:
        requests_collection.insert_one({
            "user_telegram_id": user_id,
            "user_first_name": user_first_name,
            "anime_title_requested": anime_title,
            "is_premium_request": is_premium,
            "request_date": datetime.utcnow(),
            "status": "Pending_In_Channel" # Initial status
        })
        return True
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error logging anime request for user {user_id}: {e}")
        return False

async def update_request_status_in_db(request_db_id_str: str, new_status: str, admin_name: str):
    """ Updates the status of a request logged in the DB, if using DB for requests. """
    if not request_db_id_str: return False # If requests aren't stored with IDs in DB
    try:
        requests_collection.update_one(
            {"_id": ObjectId(request_db_id_str)},
            {"$set": {"status": new_status, "admin_handler_name": admin_name, "last_updated_date": datetime.utcnow()}}
        )
        return True
    except mongo_errors.PyMongoError as e:
        logger.error(f"MongoDB error updating request status for {request_db_id_str}: {e}")
        return False
    except Exception as e: # bson.errors.InvalidId
        logger.error(f"Invalid request ID format for DB update {request_db_id_str}: {e}")
        return False

# IMPORTANT: Ensure your anime data insertion for seasons and episodes creates the correct nested structure.
# For example, when adding a new anime, the 'seasons' array might be initialized like:
# anime_data["seasons"] = [{"season_number": i, "episodes": []} for i in range(1, num_seasons + 1)]
