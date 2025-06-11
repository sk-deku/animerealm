# database/mongo_db.py
import logging
from pymongo import MongoClient, UpdateOne, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import ConnectionFailure, OperationFailure, ConfigurationError, DuplicateKeyError
from datetime import datetime, timedelta, date as DateObject # Import date separately
import pytz # For timezone-aware datetime objects
from bson import ObjectId # For querying by ObjectId
from pydantic import ValidationError # To catch Pydantic validation errors

from configs import settings
from .models import ( # Import your Pydantic models
    User as UserModel,
    Anime as AnimeModel,
    Season as SeasonModel,
    Episode as EpisodeModel,
    FileVersion as FileVersionModel,
    AnimeRequest as AnimeRequestModel,
    GeneratedReferralCode as GeneratedReferralCodeModel
)

# Get a logger instance
logger = logging.getLogger(__name__)

class Database:
    _instance = None
    # client: MongoClient = None # Type hint for client
    # db = None # Type hint for db

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'client'): # Ensure __init__ runs only once
            logger.info("Initializing MongoDB connection...")
            try:
                self.client = MongoClient(settings.DATABASE_URL, appname="AnimeRealmBot") # appname for better logging on MongoDB side
                self.client.admin.command('ping') # Verify connection
                logger.info("✅ MongoDB connection successful!")
                self.db = self.client[settings.DATABASE_NAME]

                self.users_collection = self.db["users"]
                self.anime_collection = self.db["anime"]
                self.requests_collection = self.db["anime_requests"] # Changed from "requests" to be more specific
                self.referral_codes_collection = self.db["generated_referral_codes"]
                # self.download_logs_collection = self.db["download_logs"] # If you implement download logging

                self._create_indexes()
            except ConnectionFailure as e:
                logger.critical(f"❌ MongoDB connection failed: {e}")
                raise SystemExit("MongoDB connection error. Bot cannot operate.")
            except ConfigurationError as e:
                logger.critical(f"❌ MongoDB configuration error: {e}. Check DATABASE_URL.")
                raise SystemExit("MongoDB configuration error.")
            except Exception as e:
                logger.critical(f"❌ Unexpected error during MongoDB init: {e}", exc_info=True)
                raise SystemExit("Unexpected MongoDB init error.")

    def _create_indexes(self):
        logger.info("Ensuring database indexes...")
        try:
            self.users_collection.create_index([("telegram_id", ASCENDING)], unique=True, name="telegram_id_idx")
            self.users_collection.create_index([("premium_status", ASCENDING)], name="premium_status_idx")
            self.users_collection.create_index([("watchlist", ASCENDING)], name="watchlist_anime_idx") # For finding users by watchlist item
            self.users_collection.create_index([("last_active_date", DESCENDING)], name="user_last_active_idx")

            self.anime_collection.create_index([("title_english", "text")], name="title_english_text_idx", default_language="english")
            self.anime_collection.create_index([("title_english", ASCENDING)], name="title_english_asc_idx")
            self.anime_collection.create_index([("genres", ASCENDING)], name="genres_idx")
            self.anime_collection.create_index([("status", ASCENDING)], name="status_idx")
            self.anime_collection.create_index([("release_year", DESCENDING)], name="release_year_idx")
            self.anime_collection.create_index([("last_content_update", DESCENDING)], name="anime_last_content_update_idx") # For 'latest'
            self.anime_collection.create_index([("download_count", DESCENDING)], name="download_count_idx")

            self.referral_codes_collection.create_index([("referral_code", ASCENDING)], unique=True, name="referral_code_idx")
            self.referral_codes_collection.create_index([("creator_user_id", ASCENDING)], name="creator_user_id_idx")
            self.referral_codes_collection.create_index([("expiry_date", ASCENDING)], name="ref_code_expiry_idx")

            self.requests_collection.create_index([("user_telegram_id", ASCENDING)], name="req_user_id_idx")
            self.requests_collection.create_index([("status", ASCENDING)], name="req_status_idx")
            logger.info("✅ Database indexes ensured.")
        except OperationFailure as e:
            logger.warning(f"⚠️ Error ensuring indexes (might already exist or permissions issue): {e}")
        except Exception as e:
            logger.error(f"⚠️ Unexpected error during index creation: {e}", exc_info=True)

    # --- User Management ---
    async def add_or_update_user(self, user_id: int, first_name: str, username: Optional[str] = None, referred_by_id: Optional[int] = None) -> dict | None:
        now_utc = datetime.now(pytz.utc)
        today_date_obj = now_utc.date() # For daily reset comparisons
        
        user_doc_from_db = await self.users_collection.find_one({"telegram_id": user_id})

        if not user_doc_from_db: # New user
            initial_tokens = settings.TOKENS_FOR_NEW_USER_DIRECT_START
            if referred_by_id:
                initial_tokens = settings.TOKENS_FOR_NEW_USER_VIA_REFERRAL
            
            new_user_data = {
                "telegram_id": user_id, "first_name": first_name, "username": username,
                "download_tokens": initial_tokens,
                "last_token_earn_reset_date": today_date_obj # Pydantic model expects datetime but stores date() object is fine in mongo
            }
            try:
                user_model = UserModel(**new_user_data) # Validate with Pydantic
                await self.users_collection.insert_one(user_model.model_dump(by_alias=True, exclude_none=True))
                logger.info(f"New user {user_id} ({first_name}) added with {initial_tokens} tokens.")
                # Fetch again to ensure we have the DB state including defaults from Pydantic model
                user_doc_after_insert = await self.users_collection.find_one({"telegram_id": user_id})
                return {"new": True, "tokens_awarded": initial_tokens, "user_doc": UserModel(**user_doc_after_insert)}
            except ValidationError as e:
                logger.error(f"Pydantic validation error for new user {user_id}: {e}")
            except DuplicateKeyError:
                logger.warning(f"User {user_id} already exists (race condition on add?). Will proceed to update.")
                # Fall through to update logic if a race condition led to duplicate key
                user_doc_from_db = await self.users_collection.find_one({"telegram_id": user_id}) # fetch it now
            except Exception as e:
                logger.error(f"DB error adding new user {user_id}: {e}", exc_info=True)
            return None

        # Existing user: update logic
        update_fields = {"last_active_date": now_utc}
        pydantic_user_existing = UserModel(**user_doc_from_db) # Load into Pydantic for comparison and type safety

        if pydantic_user_existing.first_name != first_name: update_fields["first_name"] = first_name
        if pydantic_user_existing.username != username: update_fields["username"] = username # Handles None vs value change
        
        # Daily token earn reset
        last_reset_db = pydantic_user_existing.last_token_earn_reset_date
        if isinstance(last_reset_db, datetime): last_reset_db = last_reset_db.date() # Ensure comparison with date object

        if last_reset_db != today_date_obj:
            update_fields["tokens_earned_today"] = 0
            update_fields["last_token_earn_reset_date"] = today_date_obj # Store as date object

        if update_fields:
            try:
                await self.users_collection.update_one({"telegram_id": user_id}, {"$set": update_fields})
                user_doc_after_update = await self.users_collection.find_one({"telegram_id": user_id})
                return {"new": False, "tokens_awarded": 0, "user_doc": UserModel(**user_doc_after_update)}
            except Exception as e:
                logger.error(f"DB error updating user {user_id}: {e}", exc_info=True)
                return None
        # If no fields to update except implicitly last_active_date (if always set by find_one_and_update)
        return {"new": False, "tokens_awarded": 0, "user_doc": pydantic_user_existing}


    async def get_user(self, user_id: int) -> UserModel | None:
        try:
            user_doc = await self.users_collection.find_one({"telegram_id": user_id})
            if user_doc:
                return UserModel(**user_doc) # Parse into Pydantic model
            return None
        except ValidationError as e:
            logger.error(f"Pydantic validation error fetching user {user_id}: {e} - Data: {user_doc}")
            return None # Or raise/return dict
        except Exception as e:
            logger.error(f"DB error fetching user {user_id}: {e}", exc_info=True)
            return None

    async def update_user_tokens(self, user_id: int, token_change: int) -> bool:
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id}, {"$inc": {"download_tokens": token_change}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"DB error updating tokens for user {user_id}: {e}", exc_info=True)
            return False

    async def grant_premium(self, user_id: int, duration_days: int) -> tuple[bool, Optional[datetime]]:
        now_utc = datetime.now(pytz.utc)
        expiry_date = now_utc + timedelta(days=duration_days)
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id},
                {"$set": {"premium_status": True, "premium_expiry_date": expiry_date}}
            )
            return result.modified_count > 0, expiry_date
        except Exception as e:
            logger.error(f"DB error granting premium to user {user_id}: {e}", exc_info=True)
            return False, None

    async def revoke_premium(self, user_id: int) -> bool:
        # (Implementation as before)
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id},
                {"$set": {"premium_status": False, "premium_expiry_date": None}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"DB error revoking premium for user {user_id}: {e}", exc_info=True)
            return False

    async def check_and_deactivate_expired_premiums(self) -> List[int]:
        now_utc = datetime.now(pytz.utc)
        query = {"premium_status": True, "premium_expiry_date": {"$lt": now_utc}}
        update = {"$set": {"premium_status": False, "premium_expiry_date": None}}
        updated_users_ids = []
        try:
            cursor = self.users_collection.find(query, {"telegram_id": 1})
            async for user in cursor: updated_users_ids.append(user["telegram_id"])
            
            if updated_users_ids:
                result = await self.users_collection.update_many(query, update)
                logger.info(f"Deactivated premium for {result.modified_count} users.")
            return updated_users_ids
        except Exception as e:
            logger.error(f"DB error deactivating expired premiums: {e}", exc_info=True)
            return []
            
    async def update_daily_token_earn(self, user_id: int, tokens_earned_this_time: int) -> bool:
        # Assumes daily reset logic (checking last_token_earn_reset_date) is done BEFORE calling this
        # or that user_doc passed to calling function is up-to-date with reset status.
        # This function just increments `tokens_earned_today`.
        now_date_obj = datetime.now(pytz.utc).date() # This must be stored as DateObject for correct comparison by model
        try:
            # Ensure last_token_earn_reset_date is current date before incrementing
            await self.users_collection.update_one(
                {"telegram_id": user_id},
                {
                    "$inc": {"tokens_earned_today": tokens_earned_this_time},
                    "$set": {"last_token_earn_reset_date": now_date_obj} # Pydantic model will handle date type
                }
            )
            return True
        except Exception as e:
            logger.error(f"DB error updating daily token earn for {user_id}: {e}", exc_info=True)
            return False


    # --- Watchlist ---
    async def add_to_watchlist(self, user_id: int, anime_id_str: str) -> bool:
        # (Implementation as before, anime_id_str is already string)
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id}, {"$addToSet": {"watchlist": anime_id_str}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"DB error adding anime {anime_id_str} to watchlist for user {user_id}: {e}", exc_info=True)
            return False

    async def remove_from_watchlist(self, user_id: int, anime_id_str: str) -> bool:
        # (Implementation as before)
        try:
            result = await self.users_collection.update_one(
                {"telegram_id": user_id}, {"$pull": {"watchlist": anime_id_str}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"DB error removing anime {anime_id_str} from watchlist for user {user_id}: {e}", exc_info=True)
            return False

    async def get_watchlist_animes_details(self, user_id: int, page: int = 1, per_page: int = 5) -> tuple[List[AnimeModel], int]:
        user = await self.get_user(user_id)
        if not user or not user.watchlist:
            return [], 0
        
        watchlist_anime_ids_str = user.watchlist
        total_items = len(watchlist_anime_ids_str)
        
        # Paginate IDs first
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_ids_str = watchlist_anime_ids_str[start_idx:end_idx]

        if not paginated_ids_str:
            return [], total_items # Reached end of list

        try:
            # Convert string IDs to ObjectIds for the $in query
            object_ids_to_fetch = [ObjectId(aid_str) for aid_str in paginated_ids_str]
        except Exception as e: # bson.errors.InvalidId
            logger.error(f"Invalid ObjectId found in watchlist for user {user_id}: {paginated_ids_str}, error: {e}")
            return [], total_items


        anime_details_list = []
        if object_ids_to_fetch:
            try:
                cursor = self.anime_collection.find({"_id": {"$in": object_ids_to_fetch}})
                async for anime_doc in cursor:
                    try:
                        anime_details_list.append(AnimeModel(**anime_doc))
                    except ValidationError as ve:
                        logger.error(f"Pydantic validation error for anime {anime_doc.get('_id')} in watchlist: {ve}")
                # To maintain order from watchlist, sort results based on original paginated_ids_str list order
                # This requires `id` field from Pydantic model which is `_id`
                ordered_details = sorted(anime_details_list, key=lambda x: paginated_ids_str.index(str(x.id)))
                return ordered_details, total_items
            except Exception as e:
                logger.error(f"DB error fetching watchlist anime details for user {user_id}: {e}", exc_info=True)
        
        return [], total_items


    # --- Referral Codes ---
    async def create_referral_code(self, creator_user_id: int, referral_code_str: str, tokens_to_award: int, expiry_date: datetime) -> bool:
        try:
            code_model = GeneratedReferralCodeModel(
                referral_code=referral_code_str,
                creator_user_id=creator_user_id,
                tokens_to_award=tokens_to_award,
                expiry_date=expiry_date.astimezone(pytz.utc) if expiry_date.tzinfo is None else expiry_date # Ensure UTC
            )
            await self.referral_codes_collection.insert_one(code_model.model_dump(by_alias=True, exclude_none=True))
            return True
        except ValidationError as e:
            logger.error(f"Pydantic validation error for referral code {referral_code_str}: {e}")
        except DuplicateKeyError:
            logger.warning(f"Attempted to insert duplicate referral code: {referral_code_str}")
        except Exception as e:
            logger.error(f"DB error creating referral code {referral_code_str}: {e}", exc_info=True)
        return False

    async def get_referral_code(self, referral_code_str: str) -> GeneratedReferralCodeModel | None:
        now_utc = datetime.now(pytz.utc)
        try:
            doc = await self.referral_codes_collection.find_one({
                "referral_code": referral_code_str,
                "is_claimed": False,
                "expiry_date": {"$gte": now_utc}
            })
            return GeneratedReferralCodeModel(**doc) if doc else None
        except ValidationError as e:
            logger.error(f"Pydantic validation error for fetched referral code {referral_code_str}: {e} - Data: {doc}")
        except Exception as e:
            logger.error(f"DB error fetching referral code {referral_code_str}: {e}", exc_info=True)
        return None

    async def claim_referral_code(self, referral_code_str: str, claimed_by_user_id: int) -> bool:
        # (Implementation as before)
        try:
            result = await self.referral_codes_collection.update_one(
                {"referral_code": referral_code_str, "is_claimed": False},
                {"$set": {"is_claimed": True, "claimed_by_user_id": claimed_by_user_id, "claim_date": datetime.now(pytz.utc)}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"DB error claiming referral {referral_code_str} by user {claimed_by_user_id}: {e}", exc_info=True)
            return False

    # --- Anime Content Management (Admin) ---
    async def add_anime(self, anime_data: dict) -> Optional[str]: # Returns new anime ObjectId as string
        try:
            # Ensure `last_content_update` is set if not already
            anime_data.setdefault("last_content_update", datetime.now(pytz.utc))
            anime_model = AnimeModel(**anime_data) # Validate with Pydantic
            # .model_dump() will handle aliases like _id (though not set here for insert) and type conversions
            result = await self.anime_collection.insert_one(anime_model.model_dump(by_alias=True, exclude_none=True))
            return str(result.inserted_id) if result.inserted_id else None
        except ValidationError as e:
            logger.error(f"Pydantic validation error adding anime '{anime_data.get('title_english')}': {e}")
        except Exception as e:
            logger.error(f"DB error adding anime '{anime_data.get('title_english')}': {e}", exc_info=True)
        return None

    async def get_anime_by_id_str(self, anime_id_str: str) -> AnimeModel | None:
        try:
            obj_id = ObjectId(anime_id_str)
            doc = await self.anime_collection.find_one({"_id": obj_id})
            return AnimeModel(**doc) if doc else None
        except ValidationError as e:
            logger.error(f"Pydantic validation error fetching anime {anime_id_str}: {e} - Data: {doc}")
        except (TypeError, ValueError, Exception) as e: # Catches InvalidId from ObjectId too
            if "InvalidId" in str(e): logger.warning(f"Invalid ObjectId string format: {anime_id_str}")
            else: logger.error(f"Error fetching anime by id_str {anime_id_str}: {e}", exc_info=True)
        return None

    async def get_anime_by_title_exact(self, title_english: str) -> AnimeModel | None:
        try:
            doc = await self.anime_collection.find_one({"title_english": {"$regex": f"^{title_english}$", "$options": "i"}})
            return AnimeModel(**doc) if doc else None
        except ValidationError as e:
            logger.error(f"Pydantic error for anime by exact title '{title_english}': {e} - Data: {doc}")
        except Exception as e:
            logger.error(f"DB error fetching anime by exact title '{title_english}': {e}", exc_info=True)
        return None

    async def update_anime_details(self, anime_id_str: str, update_data: dict) -> bool:
        # update_data should contain only fields to be $set. Pydantic not directly used here unless partial models
        try:
            obj_id = ObjectId(anime_id_str)
            # Ensure last_content_update is always updated on any detail change
            update_data.setdefault("last_content_update", datetime.now(pytz.utc))
            result = await self.anime_collection.update_one({"_id": obj_id}, {"$set": update_data})
            return result.modified_count > 0
        except (TypeError, ValueError, Exception) as e:
            if "InvalidId" in str(e): logger.warning(f"Invalid ObjectId for update_anime_details: {anime_id_str}")
            else: logger.error(f"DB error updating anime {anime_id_str}: {e}", exc_info=True)
        return False

    # --- Robust Season/Episode/Version Add/Update Functions (Crucial for CM) ---
    async def add_file_version_to_episode_robust(self, anime_id_str: str, season_num: int, episode_num: int, version_data: dict) -> bool:
        try:
            # Validate version_data with Pydantic model
            file_version_model = FileVersionModel(**version_data)
            version_dict_to_save = file_version_model.model_dump(exclude_none=True)
            obj_id = ObjectId(anime_id_str)

            # Upsert logic: Add season if not exists, add episode if not exists, then push version
            # 1. Ensure Season exists
            season_match_query = {"_id": obj_id, "seasons.season_number": season_num}
            anime_doc = await self.anime_collection.find_one(season_match_query)
            if not anime_doc: # Season does not exist, add it
                new_season_pydantic = SeasonModel(season_number=season_num, episodes=[])
                await self.anime_collection.update_one(
                    {"_id": obj_id},
                    {"$push": {"seasons": new_season_pydantic.model_dump(exclude_none=True)}}
                )
            
            # 2. Ensure Episode exists within the season
            episode_match_query = {"_id": obj_id, "seasons": {"$elemMatch": {"season_number": season_num, "episodes.episode_number": episode_num}}}
            anime_doc_with_ep = await self.anime_collection.find_one(episode_match_query)
            if not anime_doc_with_ep: # Episode does not exist, add it
                new_episode_pydantic = EpisodeModel(episode_number=episode_num, versions=[]) # Start with empty versions, then push actual
                await self.anime_collection.update_one(
                    {"_id": obj_id, "seasons.season_number": season_num},
                    {"$push": {"seasons.$.episodes": new_episode_pydantic.model_dump(exclude_none=True)}}
                )

            # 3. Push the new file version
            result = await self.anime_collection.update_one(
                {"_id": obj_id},
                {"$push": {"seasons.$[s].episodes.$[e].versions": version_dict_to_save}},
                array_filters=[
                    {"s.season_number": season_num},
                    {"e.episode_number": episode_num}
                ]
            )
            if result.modified_count > 0:
                await self.anime_collection.update_one({"_id": obj_id}, {"$set": {"last_content_update": datetime.now(pytz.utc)}})
            return result.modified_count > 0
        except ValidationError as ve:
            logger.error(f"Pydantic validation error for file version (A:{anime_id_str} S:{season_num} E:{episode_num}): {ve}")
        except Exception as e:
            logger.error(f"DB error in add_file_version_robust (A:{anime_id_str} S:{season_num} E:{episode_num}): {e}", exc_info=True)
        return False

    async def add_or_update_episode_data(self, anime_id_str: str, season_num: int, episode_num: int, episode_update_data: dict, only_air_date: bool = False):
        # This function is for setting air_date or adding a basic episode structure.
        # `episode_update_data` for air_date would be {"air_date": datetime_or_tba_str}
        try:
            obj_id = ObjectId(anime_id_str)
            # Validate episode data part
            if 'air_date' in episode_update_data and isinstance(episode_update_data['air_date'], str) and episode_update_data['air_date'].upper() != 'TBA':
                try: # If it's a date string, parse it
                    episode_update_data['air_date'] = datetime.strptime(episode_update_data['air_date'], "%Y-%m-%d").replace(tzinfo=pytz.utc)
                except ValueError:
                    logger.error(f"Invalid date string for air_date: {episode_update_data['air_date']}")
                    return False # Or raise error
            
            # If setting only air_date, versions should be empty array
            if only_air_date:
                episode_update_data["versions"] = []

            # Episode shell based on input - Pydantic will fill defaults if any.
            ep_model_data = {"episode_number": episode_num, **episode_update_data}
            validated_ep_data_for_db = EpisodeModel(**ep_model_data).model_dump(exclude_none=True)


            # Upsert logic: Find season, then find episode. If episode found, $set. If not, $push.
            # If season not found, add season with this episode.
            
            # 1. Ensure Season exists (same as in add_file_version_robust)
            season_match_query = {"_id": obj_id, "seasons.season_number": season_num}
            anime_doc = await self.anime_collection.find_one(season_match_query)
            if not anime_doc:
                new_season_pydantic = SeasonModel(season_number=season_num, episodes=[validated_ep_data_for_db])
                await self.anime_collection.update_one(
                    {"_id": obj_id},
                    {"$push": {"seasons": new_season_pydantic.model_dump(exclude_none=True)}}
                )
                await self.anime_collection.update_one({"_id": obj_id}, {"$set": {"last_content_update": datetime.now(pytz.utc)}})
                return True

            # 2. Season exists. Check if Episode exists.
            episode_match_query = {"_id": obj_id, "seasons": {"$elemMatch": {"season_number": season_num, "episodes.episode_number": episode_num}}}
            anime_doc_with_ep = await self.anime_collection.find_one(episode_match_query)

            if anime_doc_with_ep: # Episode exists, update it (e.g. set air_date and clear versions)
                update_op = {"$set": {}}
                for key, value in validated_ep_data_for_db.items(): # Build the $set dynamically based on input
                    update_op["$set"][f"seasons.$[s].episodes.$[e].{key}"] = value
                
                result = await self.anime_collection.update_one(
                    {"_id": obj_id},
                    update_op,
                    array_filters=[{"s.season_number": season_num}, {"e.episode_number": episode_num}]
                )
            else: # Episode does not exist in the season, add it
                result = await self.anime_collection.update_one(
                    {"_id": obj_id, "seasons.season_number": season_num},
                    {"$push": {"seasons.$.episodes": validated_ep_data_for_db}}
                )
            
            if result.modified_count > 0 or result.upserted_id:
                await self.anime_collection.update_one({"_id": obj_id}, {"$set": {"last_content_update": datetime.now(pytz.utc)}})
            return result.modified_count > 0 or result.upserted_id is not None

        except ValidationError as ve:
            logger.error(f"Pydantic validation error for episode data (A:{anime_id_str} S:{season_num} E:{episode_num}): {ve}")
        except Exception as e:
            logger.error(f"DB error in add_or_update_episode_data (A:{anime_id_str} S:{season_num} E:{episode_num}): {e}", exc_info=True)
        return False


    # --- Anime Search & Browsing ---
    async def search_anime_by_title(self, query: str, page: int = 1, per_page: int = 5) -> tuple[List[AnimeModel], int]:
        # (Implementation as before, but parse results into AnimeModel)
        skip_count = (page - 1) * per_page
        mongo_query = {"$text": {"$search": query}}
        projection = {"score": {"$meta": "textScore"}}
        sort_criteria = [("score", {"$meta": "textScore"}), ("title_english", ASCENDING)]
        
        results_list = []
        total_items = 0
        try:
            cursor = self.anime_collection.find(mongo_query, projection).sort(sort_criteria).skip(skip_count).limit(per_page)
            async for doc in cursor:
                try: results_list.append(AnimeModel(**doc))
                except ValidationError as ve: logger.error(f"Pydantic error for search result anime {doc.get('_id')}: {ve}")
            
            # Count_documents for text search might be slow or behave unexpectedly.
            # For a more accurate count with text search, specific strategies may be needed.
            # Simple count for now.
            total_items = await self.anime_collection.count_documents(mongo_query)
        except Exception as e:
            logger.error(f"DB error searching anime with query '{query}': {e}", exc_info=True)
        return results_list, total_items

    async def get_animes_by_filter(self, filter_criteria: dict, page: int = 1, per_page: int = 5, sort_by: Optional[list] = None) -> tuple[List[AnimeModel], int]:
        # (Implementation as before, parse results into AnimeModel)
        skip_count = (page - 1) * per_page
        sort_criteria = sort_by if sort_by else [("title_english", ASCENDING)]
        results_list = []
        total_items = 0
        try:
            cursor = self.anime_collection.find(filter_criteria).sort(sort_criteria).skip(skip_count).limit(per_page)
            async for doc in cursor:
                try: results_list.append(AnimeModel(**doc))
                except ValidationError as ve: logger.error(f"Pydantic error for filtered anime {doc.get('_id')}: {ve}")
            total_items = await self.anime_collection.count_documents(filter_criteria)
        except Exception as e:
            logger.error(f"DB error fetching animes with filter {filter_criteria}: {e}", exc_info=True)
        return results_list, total_items

    async def get_latest_episodes_anime(self, page: int = 1, per_page: int = 5) -> tuple[List[AnimeModel], int]:
        query = {} # Can add filters e.g. {"status": {"$in": ["Ongoing", "Recently Completed"]}}
        sort_criteria = [("last_content_update", DESCENDING), ("title_english", ASCENDING)]
        return await self.get_animes_by_filter(query, page, per_page, sort_by=sort_criteria)

    async def get_popular_animes(self, page: int = 1, per_page: int = 5) -> tuple[List[AnimeModel], int]:
        query = {}
        sort_criteria = [("download_count", DESCENDING), ("title_english", ASCENDING)]
        return await self.get_animes_by_filter(query, page, per_page, sort_by=sort_criteria)

    async def increment_anime_download_count(self, anime_id_str: str) -> bool:
        # (Implementation as before)
        try:
            obj_id = ObjectId(anime_id_str)
            result = await self.anime_collection.update_one({"_id": obj_id}, {"$inc": {"download_count": 1}})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"DB error incrementing download count for anime {anime_id_str}: {e}", exc_info=True)
            return False
    
    # --- General Admin Fetch / Log Functions ---
    async def get_all_user_ids(self, premium_only: bool = False, active_only_days: int = 0) -> List[int]:
        # (Implementation as before)
        query = {}
        if premium_only: query["premium_status"] = True
        if active_only_days > 0:
            active_since = datetime.now(pytz.utc) - timedelta(days=active_only_days)
            query["last_active_date"] = {"$gte": active_since}
        
        user_ids = []
        try:
            cursor = self.users_collection.find(query, {"telegram_id": 1})
            async for user_doc in cursor: user_ids.append(user_doc["telegram_id"])
        except Exception as e:
            logger.error(f"DB error fetching all user IDs with query {query}: {e}", exc_info=True)
        return user_ids


    async def find_users_for_watchlist_notification(self, anime_id_str: str) -> List[int]:
        # (Implementation as before)
        query = {
            "watchlist": anime_id_str,
            "notification_preferences.watchlist_new_episode": True,
            "is_banned": False
        }
        user_ids = []
        try:
            cursor = self.users_collection.find(query, {"telegram_id": 1})
            async for user_doc in cursor: user_ids.append(user_doc["telegram_id"])
        except Exception as e:
            logger.error(f"DB error finding users for watchlist notif (anime {anime_id_str}): {e}", exc_info=True)
        return user_ids

    async def log_anime_request_to_db(self, user_id: int, user_first_name: str, anime_title: str, is_premium: bool) -> Optional[str]:
        """ Logs a request to the database, returns request_id string or None. """
        try:
            req_model_data = {
                "user_telegram_id": user_id, "user_first_name": user_first_name,
                "anime_title_requested": anime_title, "is_premium_request": is_premium,
                "status": "Pending_In_Channel" # From Literal in Pydantic model
            }
            req_pydantic_instance = AnimeRequestModel(**req_model_data)
            result = await self.requests_collection.insert_one(req_pydantic_instance.model_dump(by_alias=True, exclude_none=True))
            return str(result.inserted_id) if result.inserted_id else None
        except ValidationError as e:
            logger.error(f"Pydantic error logging anime request for user {user_id}: {e}")
        except Exception as e:
            logger.error(f"DB error logging anime request for user {user_id}: {e}", exc_info=True)
        return None

    async def update_request_status_in_db(self, request_id_str: str, new_status: str, admin_name: str = "N/A") -> bool:
        """ Updates the status of a request logged in the DB. new_status must be one of the Literal values."""
        try:
            obj_id = ObjectId(request_id_str)
            # Validate new_status against Pydantic model if needed, or ensure caller sends valid literal
            update_doc = {
                "$set": {
                    "status": new_status,
                    "admin_handler_name": admin_name,
                    "last_updated_date": datetime.now(pytz.utc)
                }
            }
            result = await self.requests_collection.update_one({"_id": obj_id}, update_doc)
            return result.modified_count > 0
        except (TypeError, ValueError, Exception) as e: # Catch InvalidId
            if "InvalidId" in str(e): logger.warning(f"Invalid ObjectId for update_request_status: {request_id_str}")
            else: logger.error(f"DB error updating request status for {request_id_str}: {e}", exc_info=True)
        return False

    # Functions for DELETING content (anime, season, episode, version) would go here.
    # They would use $pull or update operations to remove items from arrays or delete documents.
    # Example:
    async def delete_anime_by_id_str(self, anime_id_str: str) -> bool:
        try:
            obj_id = ObjectId(anime_id_str)
            result = await self.anime_collection.delete_one({"_id": obj_id})
            # Also, potentially remove this anime_id_str from all users' watchlists
            if result.deleted_count > 0:
                await self.users_collection.update_many({}, {"$pull": {"watchlist": anime_id_str}})
                logger.info(f"Deleted anime {anime_id_str} and removed from watchlists.")
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting anime {anime_id_str}: {e}")
            return False
    
    async def delete_season_from_anime(self, anime_id_str: str, season_num: int) -> bool:
        try:
            obj_id = ObjectId(anime_id_str)
            result = await self.anime_collection.update_one(
                {"_id": obj_id},
                {"$pull": {"seasons": {"season_number": season_num}}}
            )
            if result.modified_count > 0:
                await self.anime_collection.update_one({"_id": obj_id}, {"$set": {"last_content_update": datetime.now(pytz.utc)}})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error deleting S{season_num} from anime {anime_id_str}: {e}")
            return False

    async def delete_episode_from_season(self, anime_id_str: str, season_num: int, episode_num: int) -> bool:
        try:
            obj_id = ObjectId(anime_id_str)
            result = await self.anime_collection.update_one(
                {"_id": obj_id, "seasons.season_number": season_num},
                {"$pull": {"seasons.$.episodes": {"episode_number": episode_num}}}
            )
            if result.modified_count > 0:
                await self.anime_collection.update_one({"_id": obj_id}, {"$set": {"last_content_update": datetime.now(pytz.utc)}})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error deleting S{season_num}E{episode_num} from anime {anime_id_str}: {e}")
            return False

    async def delete_file_version_from_episode(self, anime_id_str: str, season_num: int, episode_num: int, file_id_of_version_to_delete: str) -> bool:
        try:
            obj_id = ObjectId(anime_id_str)
            # Pull a specific version object from the versions array based on its file_id
            result = await self.anime_collection.update_one(
                {"_id": obj_id}, # Target document
                {"$pull": {"seasons.$[s].episodes.$[e].versions": {"file_id": file_id_of_version_to_delete}}},
                array_filters=[
                    {"s.season_number": season_num},
                    {"e.episode_number": episode_num}
                ]
            )
            if result.modified_count > 0:
                await self.anime_collection.update_one({"_id": obj_id}, {"$set": {"last_content_update": datetime.now(pytz.utc)}})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error deleting file version ({file_id_of_version_to_delete}) from S{season_num}E{episode_num} of anime {anime_id_str}: {e}")
            return False


# Initialize a single instance of the Database class for the application to use
db = Database()
