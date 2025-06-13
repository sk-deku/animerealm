# database/mongo_db.py
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient # Asynchronous driver
from pymongo.errors import ConnectionFailure, OperationFailure
from pymongo import MongoClient # Standard driver (can be used for sync tasks if needed, e.g., init indices - though async is better)
from pymongo.write_concern import WriteConcern
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone # For timezone aware datetimes

# Import constants from config
from config import DB_NAME, STATE_COLLECTION_NAME
# Import models for type hinting and potential validation/conversion
from database.models import UserState, User, Anime, Request, GeneratedToken, PyObjectId

# Configure logger for database operations
db_logger = logging.getLogger(__name__)

class MongoDB:
    """
    Singleton class to manage MongoDB connection.
    Uses motor for asyncio compatibility.
    """
    _client: Optional[AsyncIOMotorClient] = None # Asynchronous client
    _db = None

    @classmethod
    async def connect(cls, uri: str, db_name: str):
        """Establishes the asynchronous connection to MongoDB."""
        if cls._client is not None and cls._db is not None:
            db_logger.info("MongoDB client already connected.")
            return

        db_logger.info("Attempting to connect to MongoDB...")
        try:
            # serverSelectionTimeoutMS controls how long the driver will wait for server selection
            cls._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True, uuidRepresentation='standard') # 5-second timeout, timezone-aware, standard UUID

            # The ping command is implicitly run by serverSelectionTimeoutMS logic.
            # Explicitly getting database instance can trigger the connection attempt.
            # Apply a default write concern? e.g., WriteConcern(w='majority') for safety
            # Use w=majority to ensure writes are acknowledged by majority of replica set members
            cls._db = cls._client.get_database(db_name, write_concern=WriteConcern(w='majority'))
            # We can use write_concern=WriteConcern(w='majority') or write_concern='majority'


            # Force an interaction to verify connection and credentials
            # A simple list_collection_names with a short timeout
            await cls._db.list_collection_names(session=None)
            db_logger.info(f"Successfully connected to MongoDB database: '{db_name}'")

        except ConnectionFailure as e:
            db_logger.critical(f"Failed to connect to MongoDB at URI: {uri}. Error: {e}", exc_info=True)
            cls._client = None # Ensure client is None on failure
            cls._db = None
            raise ConnectionFailure(f"Failed to connect to MongoDB: {e}")
        except OperationFailure as e:
            # Includes authentication errors, authorization errors etc.
            db_logger.critical(f"MongoDB Operation Failure (e.g., auth/permissions): {e}", exc_info=True)
            cls._client = None
            cls._db = None
            raise OperationFailure(f"MongoDB Operation Failure: {e}")
        except Exception as e:
            db_logger.critical(f"An unexpected error occurred during MongoDB connection: {e}", exc_info=True)
            cls._client = None
            cls._db = None
            raise Exception(f"Unexpected error during MongoDB connection: {e}")


    @classmethod
    async def close(cls):
        """Closes the MongoDB connection."""
        if cls._client:
            db_logger.info("Closing MongoDB connection...")
            # MotorClient close is synchronous
            try:
                 cls._client.close()
                 db_logger.info("MongoDB connection closed.")
            except Exception as e:
                 db_logger.error(f"Error during MongoDB client close: {e}")
            finally:
                 cls._client = None
                 cls._db = None


    @classmethod
    def get_db(cls):
        """Returns the database instance. Raises error if not connected."""
        if cls._db is None:
            db_logger.error("Attempted database access before connection.", exc_info=True)
            raise ConnectionFailure("MongoDB database is not connected.")
        return cls._db

    # --- Convenience Methods for Collections ---

    # These methods return Motor Collection instances
    @classmethod
    def users_collection(cls):
        return cls.get_db()["users"]

    @classmethod
    def anime_collection(cls):
        return cls.get_db()["anime"]

    @classmethod
    def requests_collection(cls):
        return cls.get_db()["requests"]

    @classmethod
    def generated_tokens_collection(cls):
        return cls.get_db()["generated_tokens"]

    @classmethod
    def states_collection(cls):
        return cls.get_db()[STATE_COLLECTION_NAME] # Use collection name from config

    # --- State Management Utility Methods (Using the UserState model) ---

    @classmethod
    async def get_user_state(cls, user_id: int) -> Optional[UserState]:
        """Retrieves the current state for a user."""
        state_doc = await cls.states_collection().find_one({"user_id": user_id})
        if state_doc:
            try:
                # Use Pydantic model for validation and structure
                return UserState(**state_doc)
            except Exception as e:
                db_logger.error(f"Error validating user state data from DB for user {user_id}: {e}", exc_info=True)
                # Consider backing up corrupted state document and deleting original if critical
                # await cls.states_collection().insert_one({... backup logic ...})
                # await cls.states_collection().delete_one({"_id": state_doc["_id"]})
                return None # Indicate corrupted state
        return None # No state found


    @classmethod
    async def set_user_state(cls, user_id: int, handler: str, step: str, data: Dict[str, Any] = None):
        """Sets or updates the state for a user."""
        # Construct the update dictionary
        state_doc_update = {
            "user_id": user_id, # Always ensure user_id is in $set for upsert
            "handler": handler,
            "step": step,
            # Merge data carefully: $set will replace the entire 'data' dictionary.
            # If you need to update specific keys *within* 'data' atomically,
            # you'd need a more complex update query ($set on data.key) or fetch-modify-save pattern
            # which is susceptible to race conditions without transactions/findAndModify.
            # For now, let's assume `data` dictionary is set entirely for each state.
            "data": data if data is not None else {},
            "updated_at": datetime.now(timezone.utc)
        }
        try:
            # Use update_one with upsert=True. $set replaces existing fields or adds new ones.
            # $setOnInsert sets fields *only* if a new document is inserted.
            # Set the created_at timestamp only on initial insert.
            result = await cls.states_collection().update_one(
                {"user_id": user_id}, # Filter for the user
                {"$set": state_doc_update, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
                upsert=True # Create document if it doesn't exist
            )
            if result.upserted_id:
                 db_logger.debug(f"Inserted initial state for user {user_id}: {handler}:{step}")
            elif result.matched_count > 0:
                 db_logger.debug(f"Updated state for user {user_id}: {handler}:{step}")
            else:
                 db_logger.warning(f"Set state command modified 0 documents for user {user_id} ({handler}:{step}). Match error?")


        except Exception as e:
             db_logger.error(f"Failed to set state for user {user_id} ({handler}:{step}): {e}", exc_info=True)
             # Handle failure - inform admin/user or retry


    @classmethod
    async def clear_user_state(cls, user_id: int):
        """Removes the state for a user."""
        try:
            result = await cls.states_collection().delete_one({"user_id": user_id})
            if result.deleted_count > 0:
                db_logger.debug(f"Cleared state for user {user_id}")
            else:
                db_logger.debug(f"No state found to clear for user {user_id}")
        except Exception as e:
            db_logger.error(f"Failed to clear state for user {user_id}: {e}", exc_info=True)
            # Log error, inform admin if persistent issue


    # --- Advanced Data Access / Update Methods ---
    # You could add specific async methods here for common complex DB operations
    # e.g., get_anime_by_id(anime_id: PyObjectId) -> Optional[Anime]
    # e.g., add_file_version_to_episode(anime_id: PyObjectId, season_number: int, episode_number: int, file_version: FileVersion)

    @classmethod
    async def get_anime_by_id(cls, anime_id: Union[str, ObjectId, PyObjectId]) -> Optional[Anime]:
        """Retrieves a single anime document by its _id, returns as Anime model."""
        try:
            # Ensure anime_id is an ObjectId instance
            if not isinstance(anime_id, ObjectId):
                anime_id = ObjectId(str(anime_id)) # Handle string or PyObjectId

            anime_doc = await cls.anime_collection().find_one({"_id": anime_id})
            if anime_doc:
                return Anime(**anime_doc)
            return None
        except Exception as e:
            db_logger.error(f"Failed to get anime by ID {anime_id}: {e}", exc_info=True)
            return None # Database error


    @classmethod
    async def add_file_version_to_episode(
        cls,
        anime_id: Union[str, ObjectId, PyObjectId],
        season_number: int,
        episode_number: int,
        file_version: FileVersion
    ) -> bool:
        """Adds a FileVersion subdocument to a specific episode."""
        try:
            if not isinstance(anime_id, ObjectId):
                 anime_id = ObjectId(str(anime_id))

            # Use $push operator to append the new FileVersion subdocument to the episodes.$.files array
            result = await cls.anime_collection().update_one(
                {"_id": anime_id, "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}, # Match the specific episode
                {"$push": {"seasons.$.episodes.$.files": file_version.dict()},
                 "$set": {"last_updated_at": datetime.now(timezone.utc)}} # Also update top-level last_updated_at
            )
            # Check if a document was matched and modified
            return result.matched_count > 0 and result.modified_count > 0

        except Exception as e:
             db_logger.error(f"Failed to add file version to episode {anime_id}/S{season_number}E{episode_number}: {e}", exc_info=True)
             return False # Database error or document not found

    @classmethod
    async def delete_file_version_from_episode(
        cls,
        anime_id: Union[str, ObjectId, PyObjectId],
        season_number: int,
        episode_number: int,
        file_unique_id: str
    ) -> bool:
        """Removes a FileVersion subdocument from a specific episode by file_unique_id."""
        try:
             if not isinstance(anime_id, ObjectId):
                  anime_id = ObjectId(str(anime_id))

             # Use $pull operator to remove the specific FileVersion subdocument from the array
             result = await cls.anime_collection().update_one(
                  {"_id": anime_id, "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}, # Match the specific episode
                  {"$pull": {"seasons.$.episodes.$.files": {"file_unique_id": file_unique_id}}} # Remove the subdocument with matching unique_id
             )
             return result.matched_count > 0 and result.modified_count > 0

        except Exception as e:
             db_logger.error(f"Failed to delete file version {file_unique_id} from {anime_id}/S{season_number}E{episode_number}: {e}", exc_info=True)
             return False


    @classmethod
    async def increment_download_counts(
        cls,
        user_id: int,
        anime_id: Union[str, ObjectId, PyObjectId],
        # Optionally, increment download count per episode/file version if tracked
        # season_number: int,
        # episode_number: int,
        # file_version_unique_id: str
    ):
        """Atomically increments download counts for a user and an anime."""
        try:
            if not isinstance(anime_id, ObjectId):
                 anime_id = ObjectId(str(anime_id))

            # Atomically increment user's download count
            await cls.users_collection().update_one(
                {"user_id": user_id},
                {"$inc": {"download_count": 1}}
            )

            # Atomically increment overall anime download count
            await cls.anime_collection().update_one(
                {"_id": anime_id},
                {"$inc": {"overall_download_count": 1}}
            )
             # Optionally, increment download counts within nested episodes/files
             # await cls.anime_collection().update_one(...)

            db_logger.debug(f"Incremented download count for user {user_id} and anime {anime_id}")

        except Exception as e:
             db_logger.error(f"Failed to increment download counts for user {user_id}, anime {anime_id}: {e}", exc_info=True)
             # This is not critical, just log and continue


    @classmethod
    async def delete_all_data(cls):
        """DANGER: Permanently deletes ALL documents from all collections."""
        db_logger.warning("!!!! PERMANENTLY DELETING ALL DATABASE DATA !!!!")
        try:
             collections = await cls.get_db().list_collection_names()
             db_logger.warning(f"Found collections: {collections}")
             for collection_name in collections:
                 if collection_name in ['system.indexes']: # Skip internal collections
                      continue
                 db_logger.warning(f"Deleting all documents from collection: {collection_name}")
                 # Use delete_many with an empty filter {} to delete all documents
                 delete_result = await cls.get_db()[collection_name].delete_many({})
                 db_logger.warning(f"Deleted {delete_result.deleted_count} documents from {collection_name}.")

             db_logger.warning("!!!! ALL DATABASE DATA PERMANENTLY DELETED !!!!")
             return True # Indicate success
        except Exception as e:
             db_logger.critical(f"FATAL ERROR DURING delete_all_data: {e}", exc_info=True)
             return False # Indicate failure


# --- Initialization Function to be called from main.py ---
async def init_db(uri: str):
    """Calls the connect method and creates/ensures indices."""
    try:
        # Attempt connection
        await MongoDB.connect(uri, DB_NAME)

        # Create indices for commonly queried fields for performance
        db = MongoDB.get_db()

        db_logger.info("Creating/Ensuring MongoDB indices...")
        index_coroutines = [
            # User collection indices
            db.users_collection().create_index([("user_id", 1)], unique=True),
            db.users_collection().create_index([("tokens", -1)]), # For potential sorting
            db.users_collection().create_index([("download_count", -1)]), # For leaderboard
            db.users_collection().create_index([("premium_status", 1)]),

            # Anime collection indices
            db.anime_collection().create_index([("name", 1)], unique=True, collation={'locale': 'en', 'strength': 2}), # Case-insensitive unique index if locale='en', strength=2
            db.anime_collection().create_index([("name", "text")]), # Text index for basic text search (used by fuzzy search primarily to narrow down)
            db.anime_collection().create_index([("overall_download_count", -1)]), # For popular anime (descending)
            db.anime_collection().create_index([("genres", 1)]),
            db.anime_collection().create_index([("release_year", 1)]),
            db.anime_collection().create_index([("status", 1)]),
            # Consider sparse index for optional fields if many documents lack them?
            # Example for querying anime by subdocument content efficiently - only needed if those queries are common
            # db.anime_collection().create_index([("seasons.episodes.files.file_unique_id", 1)]), # Can help finding an episode by a specific file ID/Unique ID
            # db.anime_collection().create_index([("seasons.episodes.release_date", 1)]), # Index if filtering/sorting by release date often

            # Requests collection indices
            db.requests_collection().create_index([("user_id", 1)]),
            db.requests_collection().create_index([("status", 1)]),
            db.requests_collection().create_index([("anime_name_requested", 1)]), # Or text index if searching requests by name often

            # Generated Tokens indices
            db.generated_tokens_collection().create_index([("token_string", 1)], unique=True),
            db.generated_tokens_collection().create_index([("generated_by_user_id", 1)]),
            db.generated_tokens_collection().create_index([("expires_at", 1), ("is_redeemed", 1)]), # For efficiently finding expired/unused tokens

            # User State collection index
            db.states_collection().create_index([("user_id", 1)], unique=True), # Ensure only one state per user
            db.states_collection().create_index([("handler", 1), ("step", 1)]), # For querying by state handler and step
            db.states_collection().create_index([("updated_at", 1)]), # For potential state timeout cleanup based on last update
        ]

        # Run index creation in background, gather results, log errors
        results = await asyncio.gather(*index_coroutines, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                 # Log index creation failures but don't necessarily halt startup
                 # unless the index is absolutely critical (e.g., unique index).
                 # pymongo's create_index by default attempts idempotently.
                 db_logger.warning(f"Failed to create index: {res}")

        db_logger.info("MongoDB indices checked/created.")


    except ConnectionFailure as e:
        # Connection failure is handled and logged inside the connect method
        db_logger.critical("Database connection failed during initialization.", exc_info=True)
        # Let the calling function in main.py handle the critical exit based on ConnectionFailure

    except Exception as e:
         db_logger.critical(f"An unexpected error occurred during DB initialization tasks (indices, etc.): {e}", exc_info=True)
         # Let the calling function handle the critical exit
         raise # Re-raise the exception to be caught by main.py's init_database error handling
