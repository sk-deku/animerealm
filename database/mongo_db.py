# database/mongo_db.py
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure
from typing import Optional, List, Dict, Any
# Make the database name available for use in this file
from config import DB_NAME

from database.models import UserState # Import the State model
from config import DB_NAME # Ensure DB_NAME is available


# Configure logger for database operations
db_logger = logging.getLogger(__name__)

class MongoDB:
    """
    Singleton class to manage MongoDB connection.
    Uses motor for asyncio compatibility.
    """
    _client: Optional[AsyncIOMotorClient] = None
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
            # which includes finding servers in a replica set and checking their health.
            # It's part of the overall connection process.
            cls._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000) # 5-second timeout
            # The ping command is part of serverSelectionTimeoutMS logic and is run internally.
            # Explicitly getting database instance can trigger the connection attempt.
            cls._db = cls._client[db_name]
            # Another check, like listing collections, can force interaction to verify connection
            # Using a list command with a very short timeout after initial connection should be fast if successful
            await cls._db.list_collection_names(session=None) # list_collection_names is coroutine for Motor
            db_logger.info(f"Successfully connected to MongoDB database: '{db_name}'")

        except ConnectionFailure as e:
            db_logger.critical(f"Failed to connect to MongoDB at URI: {uri}. Error: {e}")
            cls._client = None # Ensure client is None on failure
            cls._db = None
            # Consider re-raising or handling appropriately in calling function
            raise ConnectionFailure(f"Failed to connect to MongoDB: {e}")
        except OperationFailure as e:
            db_logger.critical(f"MongoDB Operation Failure (e.g., auth): {e}")
            cls._client = None
            cls._db = None
            raise OperationFailure(f"MongoDB Operation Failure: {e}")
        except Exception as e:
            db_logger.critical(f"An unexpected error occurred during MongoDB connection: {e}")
            cls._client = None
            cls._db = None
            raise Exception(f"Unexpected error during MongoDB connection: {e}")
        pass # Existing implementation remains
    

    @classmethod
    async def close(cls):
        """Closes the MongoDB connection."""
        if cls._client:
            db_logger.info("Closing MongoDB connection...")
            cls._client.close()
            cls._client = None
            cls._db = None
            db_logger.info("MongoDB connection closed.")
        pass # Existing implementation remains
        
    @classmethod
    def get_db(cls):
        """Returns the database instance. Raises error if not connected."""
        if cls._db is None:
            db_logger.error("Database is not connected.")
            # Handle this error gracefully in handlers, perhaps asking user to try again or notify admin
            raise ConnectionFailure("MongoDB database is not connected.")
        return cls._db
        pass # Existing implementation remains
        
    # --- Convenience Methods for Collections ---

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
        return cls.get_db()["user_states"] # Use a distinct name for the collection
        
# --- Initialization Function to be called from main.py ---
async def init_db(uri: str):
    """Calls the connect method and optionally sets up indices."""
    try:
        # Attempt connection
        await MongoDB.connect(uri, DB_NAME) # Use DB_NAME from config

        # Optional: Create indices for commonly queried fields for performance
        # Indices should be created ONCE ideally on deployment or init
        db = MongoDB.get_db() # Get the connected DB instance

        # Create index coroutines
        index_coroutines = [
            # User collection indices
            db["users"].create_index([("user_id", 1)], unique=True),
            db["users"].create_index([("tokens", -1)]), # For leaderboard
            db["users"].create_index([("download_count", -1)]), # For leaderboard
            db["users"].create_index([("premium_status", 1)]),

            # Anime collection indices
            db["anime"].create_index([("name", 1)], unique=True), # Case-sensitive index
            db["anime"].create_index([("name", "text")]), # Text index for search (less ideal than fuzzy, but can help)
            db["anime"].create_index([("overall_download_count", -1)]), # For popular anime
            db["anime"].create_index([("genres", 1)]),
            db["anime"].create_index([("release_year", 1)]),
            db["anime"].create_index([("status", 1)]),
            # Indexes on subdocuments/arrays require careful consideration,
            # e.g., anime.seasons.episodes.files might be better queried
            # by iterating through the anime document itself.
            # If we often search specifically for a file_id, an index like this *could* help,
            # but might impact write performance if files array is large:
            # db["anime"].create_index([("seasons.episodes.files.file_id", 1)]), # Consider this only if queries warrant it.

            # Requests collection indices
            db["requests"].create_index([("user_id", 1)]),
            db["requests"].create_index([("status", 1)]),
            db["requests"].create_index([("anime_name_requested", 1)]),

            # Generated Tokens indices
            db["generated_tokens"].create_index([("token_string", 1)], unique=True),
            db["generated_tokens"].create_index([("generated_by_user_id", 1)]),
            db["generated_tokens"].create_index([("expires_at", 1), ("is_redeemed", 1)]), # For cleaning up expired/used tokens efficiently
        ]

        # Run index creation in background if needed
        db_logger.info("Creating/Ensuring MongoDB indices...")
        results = await asyncio.gather(*index_coroutines, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                 db_logger.warning(f"Failed to create index {i}: {res}")
        db_logger.info("MongoDB indices checked/created.")


    except ConnectionFailure:
        # Connection failure handled and logged inside connect method
        db_logger.critical("Database connection failed during initialization.")
        # Optionally, you could set a global flag here to indicate DB is down
    except Exception as e:
         db_logger.critical(f"An error occurred during DB initialization tasks (indices, etc.): {e}")
         # Handle other init failures


    # --- State Management Utility Methods ---

    @classmethod
    async def get_user_state(cls, user_id: int) -> Optional[UserState]:
        """Retrieves the current state for a user."""
        state_doc = await cls.states_collection().find_one({"user_id": user_id})
        if state_doc:
            try:
                return UserState(**state_doc)
            except Exception as e:
                db_logger.error(f"Error validating user state data from DB for user {user_id}: {e}")
                # Optionally delete potentially corrupted state? Risky.
                return None # Indicate corrupted state
        return None # No state found


    @classmethod
    async def set_user_state(cls, user_id: int, handler: str, step: str, data: Dict[str, Any] = None):
        """Sets or updates the state for a user."""
        state_doc = {
            "user_id": user_id,
            "handler": handler,
            "step": step,
            "data": data if data is not None else {},
            "updated_at": datetime.now(timezone.utc)
        }
        try:
            # Use upsert=True: if state for this user_id exists, update; otherwise, insert.
            # Setting upsert=True handles initial creation and subsequent updates.
            await cls.states_collection().update_one(
                {"user_id": user_id},
                {"$set": state_doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
                upsert=True
            )
            db_logger.debug(f"Set state for user {user_id}: {handler}:{step}")
        except Exception as e:
             db_logger.error(f"Failed to set state for user {user_id} ({handler}:{step}): {e}")
             # Handle failure - potentially critical

    @classmethod
    async def clear_user_state(cls, user_id: int):
        """Removes the state for a user."""
        try:
            await cls.states_collection().delete_one({"user_id": user_id})
            db_logger.debug(f"Cleared state for user {user_id}")
        except Exception as e:
            db_logger.error(f"Failed to clear state for user {user_id}: {e}")
            # Log error, maybe inform admin if persistent issue

# --- Initialization Function to be called from main.py ---
async def init_db(uri: str):
    """Calls the connect method and optionally sets up indices."""
    try:
        # Attempt connection
        await MongoDB.connect(uri, DB_NAME) # Use DB_NAME from config

        # Optional: Create indices
        db = MongoDB.get_db()

        db_logger.info("Creating/Ensuring MongoDB indices...")
        index_coroutines = [
            # ... existing indices for users, anime, requests, generated_tokens ...

            # New: User State collection index
            db["user_states"].create_index([("user_id", 1)], unique=True), # Ensure only one state per user
            db["user_states"].create_index([("handler", 1), ("step", 1)]), # For querying by state

        ]
        results = await asyncio.gather(*index_coroutines, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                 db_logger.warning(f"Failed to create index {i}: {res}")
        db_logger.info("MongoDB indices checked/created.")

    except ConnectionFailure:
        # Connection failure handled and logged inside connect method
        db_logger.critical("Database connection failed during initialization.")
        # Global flag could be set here to indicate DB is down if needed

    except Exception as e:
         db_logger.critical(f"An error occurred during DB initialization tasks (indices, etc.): {e}")
         # Handle other init failures

# DB_NAME is imported from config at the top
