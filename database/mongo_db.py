# database/mongo_db.py
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient # Asynchronous driver
from pymongo.errors import ConnectionFailure, OperationFailure
# No longer strictly need synchronous MongoClient here unless for non-async specific tasks
from pymongo.write_concern import WriteConcern # For ensuring write safety
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone # For timezone aware datetimes

# Import constants from config
from config import DB_NAME, STATE_COLLECTION_NAME
# Import models for type hinting, validation, and dictionary conversion
from database.models import UserState, User, Anime, Request, GeneratedToken, FileVersion, PyObjectId, model_to_mongo_dict

# Configure logger for database operations
db_logger = logging.getLogger(__name__)

class MongoDB:
    """
    Singleton class to manage MongoDB connection.
    Uses motor for asyncio compatibility.
    """
    _client: Optional[AsyncIOMotorClient] = None # Asynchronous client instance
    _db = None # Database instance

    @classmethod
    async def connect(cls, uri: str, db_name: str):
        """
        Establishes the asynchronous connection to MongoDB.
        Raises ConnectionFailure, OperationFailure, or other Exceptions on failure.
        """
        if cls._client is not None and cls._db is not None:
            db_logger.info("MongoDB client already connected.")
            # You might add a check here to ensure the connection is still healthy if needed
            try:
                 # A simple async command to check if the connection is responsive
                 await cls._client.admin.command('ping')
                 db_logger.debug("Existing MongoDB connection is healthy.")
                 return
            except Exception as e:
                 db_logger.warning(f"Existing MongoDB connection appears unhealthy: {e}. Attempting to reconnect.", exc_info=True)
                 await cls.close() # Close the unhealthy connection before trying to reconnect
                 cls._client = None # Ensure these are None to force new connection attempt
                 cls._db = None


        db_logger.info("Attempting to connect to MongoDB...")
        try:
            # serverSelectionTimeoutMS: how long the driver will wait to find and connect to servers
            # connectTimeoutMS: how long the driver will wait for the initial TCP connection
            # Add maxPoolSize to limit connection pool size if needed for high concurrency
            # tz_aware=True: Ensure datetime objects from DB are timezone-aware
            # uuidRepresentation='standard': Handle UUIDs consistently (important for ObjectId sometimes, though PyObjectId handles this)
            cls._client = AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=10000, # Increase timeout slightly (e.g., 10 seconds)
                connectTimeoutMS=5000,
                tz_aware=True,
                uuidRepresentation='standard' # Often good practice
            )

            # Get the database instance and set a default write concern (majority recommended for safety)
            cls._db = cls._client.get_database(db_name, write_concern=WriteConcern(w='majority'))
            # Write concern applies to operations via this db object or collections from it


            # Force a simple operation to confirm connection and authentication is working
            # list_collection_names() is a light operation that interacts with the server
            await cls._db.list_collection_names(session=None)
            db_logger.info(f"Successfully connected to MongoDB database: '{db_name}'")

        except (ConnectionFailure, OperationFailure) as e:
            db_logger.critical(f"Failed to connect to MongoDB: {e}", exc_info=True)
            cls._client = None
            cls._db = None
            raise # Re-raise the specific connection/operation error
        except Exception as e:
            db_logger.critical(f"An unexpected error occurred during MongoDB connection: {e}", exc_info=True)
            cls._client = None
            cls._db = None
            raise # Re-raise unexpected errors


    @classmethod
    async def close(cls):
        """Closes the MongoDB connection gracefully."""
        if cls._client:
            db_logger.info("Closing MongoDB connection...")
            try:
                 # MotorClient's close method is synchronous, no await needed here
                 cls._client.close()
                 db_logger.info("MongoDB connection closed.")
            except Exception as e:
                 db_logger.error(f"Error during MongoDB client close: {e}", exc_info=True)
            finally:
                 cls._client = None
                 cls._db = None


    @classmethod
    def get_db(cls):
        """
        Returns the database instance.
        Raises ConnectionFailure if the database connection has not been established.
        """
        if cls._db is None:
            db_logger.error("Attempted database access before successful connection.", exc_info=True)
            raise ConnectionFailure("MongoDB database is not connected.")
        # Check if client is still alive? Or rely on Motor's auto-reconnection + retries?
        # Relying on Motor's internal connection handling is usually preferred.
        return cls._db

    # --- Convenience Methods for Collections ---

    # These methods return Motor Collection instances configured with the default write concern
    @classmethod
    def users_collection(cls):
        return cls.get_db()["users"] # .with_write_concern(WriteConcern(w='majority')) # Optional to apply per collection

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
        """Retrieves the current state for a user, returns as UserState model."""
        try:
            state_doc = await cls.states_collection().find_one({"user_id": user_id})
            if state_doc:
                # Use Pydantic model for validation and structure mapping
                return UserState(**state_doc)
            return None # No state found for this user
        except Exception as e:
            # Log errors related to fetching or validating state data
            db_logger.error(f"Error fetching or validating user state for user {user_id}: {e}", exc_info=True)
            # You might consider specific handling for data corruption vs temporary DB issues
            # For now, treat any error during retrieval as potentially problematic state
            # Could attempt to clear state here? Or let calling handler decide. Returning None might lead to infinite loops.
            # Let's raise a specific exception or return None based on expected behavior.
            # Returning None assumes handlers will check and react (e.g., clearing state on finding None but expecting a state).
            return None # Indicate failure or non-existence


    @classmethod
    async def set_user_state(cls, user_id: int, handler: str, step: str, data: Optional[Dict[str, Any]] = None):
        """Sets or updates the state for a user."""
        # Construct the state data to be written/updated. $set will replace the entire document (except _id) or fields.
        state_doc_update = {
            "user_id": user_id,
            "handler": handler,
            "step": step,
            # Replace the entire 'data' dictionary in the database document
            "data": data if data is not None else {}, # Store an empty dict if no data is provided
            "updated_at": datetime.now(timezone.utc) # Always update the timestamp on modification
        }
        try:
            # Use update_one with upsert=True: If state for this user_id exists, update it; otherwise, insert a new one.
            # $setOnInsert is used to set fields *only* when a new document is inserted (specifically, 'created_at').
            result = await cls.states_collection().update_one(
                {"user_id": user_id}, # Filter: Find the document for this user ID
                {"$set": state_doc_update, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
                upsert=True # Option: Insert if document not found
            )

            # Log based on the outcome of the update_one operation
            if result.upserted_id:
                 db_logger.debug(f"Inserted initial state for user {user_id}: {handler}:{step}. Document ID: {result.upserted_id}")
            elif result.matched_count > 0:
                 # Document for the user_id was found
                 if result.modified_count > 0:
                      db_logger.debug(f"Updated state for user {user_id}: {handler}:{step}. Modified count: {result.modified_count}")
                 else:
                      # Matched count > 0, but modified count == 0. Likely the exact same state and data was already there.
                      db_logger.debug(f"Set state command matched existing state but modified 0 documents for user {user_id} ({handler}:{step}).")
            else:
                 # This shouldn't typically happen with upsert=True, unless user_id exists but update somehow failed without error?
                 db_logger.warning(f"Set state command modified 0 documents and did not upsert for user {user_id} ({handler}:{step}). Unexpected result.")


        except Exception as e:
             # Log any database error during the set state operation
             db_logger.error(f"Failed to set state for user {user_id} ({handler}:{step}): {e}", exc_info=True)
             # In a real app, you might implement retry logic here or alert an admin


    @classmethod
    async def clear_user_state(cls, user_id: int):
        """Removes the state document for a specific user."""
        try:
            result = await cls.states_collection().delete_one({"user_id": user_id})
            # Log whether a state document was actually deleted
            if result.deleted_count > 0:
                db_logger.debug(f"Cleared state for user {user_id}")
            else:
                db_logger.debug(f"No state found to clear for user {user_id}")
        except Exception as e:
            # Log any database error during state clearing
            db_logger.error(f"Failed to clear state for user {user_id}: {e}", exc_info=True)
            # Log the error but don't raise, clearing state failure is often non-critical


    # --- Common Data Interaction Utility Methods ---

    # These are examples of helper methods that handler functions can call to perform common DB tasks.
    # Keeping these here makes handler code cleaner and centralizes DB query logic.

    @classmethod
    async def get_anime_by_id(cls, anime_id: Union[str, ObjectId, PyObjectId]) -> Optional[Anime]:
        """Retrieves a single anime document by its _id, returns as Anime model."""
        try:
            # Ensure the input ID is an ObjectId instance before querying
            if not isinstance(anime_id, ObjectId):
                # Attempt conversion from string or PyObjectId. Will raise if invalid format.
                anime_id = ObjectId(str(anime_id))

            # Find the document by its _id
            anime_doc = await cls.anime_collection().find_one({"_id": anime_id})
            if anime_doc:
                # Convert the retrieved dictionary document into an Anime Pydantic model
                # Pydantic handles mapping '_id' to 'id' due to the alias config
                return Anime(**anime_doc)
            return None # Document not found
        except Exception as e:
            # Log errors, particularly database errors or validation issues
            db_logger.error(f"Failed to get anime by ID {anime_id}: {e}", exc_info=True)
            # Re-raise or return None/False depending on expected behavior. Returning None on error might mask issues.
            # Let's return None on fetch error too, handles both 'not found' and 'db error' cases for simplicity for the caller.
            return None


    @classmethod
    async def add_file_version_to_episode(
        cls,
        anime_id: Union[str, ObjectId, PyObjectId],
        season_number: int,
        episode_number: int,
        file_version: FileVersion
    ) -> bool:
        """Adds a FileVersion subdocument to the files array of a specific episode within an anime."""
        try:
            # Ensure anime_id is an ObjectId
            if not isinstance(anime_id, ObjectId):
                 anime_id = ObjectId(str(anime_id))

            # Build the filter to precisely locate the correct episode
            # Use positional operator ($) with $elemMatch in the filter to target the season AND episode within it
            # Filter needs to match:
            # 1. The anime document by its _id
            # 2. An element in the 'seasons' array matching the season_number
            # 3. An element in the 'episodes' array *within that matching season element* matching the episode_number
            filter_query = {
                 "_id": anime_id,
                 "seasons": { # Look within the seasons array
                     "$elemMatch": { # Find an element in 'seasons' that matches these conditions:
                          "season_number": season_number,
                          "episodes": { # Look within the episodes array of THIS season element
                              "$elemMatch": { # Find an element in 'episodes' that matches this:
                                  "episode_number": episode_number
                              }
                          }
                     }
                 }
            }

            # The update operation needs to target the elements found by the filter using positional operators ($ and $ later on if needed)
            # The first $ refers to the index of the season element found by $elemMatch in the filter
            # The second $ needs careful handling - you often use $[] or specify the full path based on schema design
            # Using positional filters $[] allows targeting multiple array elements within an array.
            # For targeting a specific nested element after using $elemMatch on a parent, it can be simpler if your query uniquely identifies it.
            # The standard $ can sometimes work if $elemMatch guarantees finding only one season element.
            # Let's refine using filtered positional operator $[] which is more robust for nested arrays >= MongoDB 3.6
            # However, the basic $ within $elemMatch context for push/set often works if filter is precise.
            # Simpler $ positional update path assumes the filter targets a single path correctly:
            update_path = "seasons.$.episodes.$.files" # Target files array within matched season AND matched episode
            update_operation = {
                 "$push": {update_path: model_to_mongo_dict(file_version)}, # Append the new FileVersion subdocument dict
                 "$set": {"last_updated_at": datetime.now(timezone.utc)} # Update top-level anime modified date
                 # Should also remove the release_date field from the episode document if adding files
                 # "$unset": { "seasons.$.episodes.$.release_date": "" } # Unset release_date
            }


            result = await cls.anime_collection().update_one(
                filter_query, # Use the constructed filter
                update_operation
                # Array filters might be needed for more complex targeting: arrayFilters=[{"s.$.season_number": season_number}, {"e.$.episode_number": episode_number}] if filter_query logic changes
            )

            # Check if a document was matched AND modified
            if result.matched_count > 0 and result.modified_count > 0:
                 # Success: File version added. Now remove release_date if it exists.
                 # Perform a separate update using $unset for the release_date field in the episode subdocument.
                 # Use the same filter and positional operators
                 await cls.anime_collection().update_one(
                     filter_query,
                     {"$unset": { "seasons.$.episodes.$.release_date": "" }} # Remove release_date field from the specific episode
                 )
                 # Log that release_date was potentially unset if needed
                 db_logger.debug(f"Attempted to unset release_date after adding file version to episode {anime_id}/S{season_number}E{episode_number}.")


            return result.matched_count > 0 # Return True if the anime/episode was found (modification expected)

        except Exception as e:
             db_logger.error(f"Failed to add file version to episode {anime_id}/S{season_number}E{episode_number}: {e}", exc_info=True)
             return False # Database error or document/path not found

    @classmethod
    async def delete_file_version_from_episode(
        cls,
        anime_id: Union[str, ObjectId, PyObjectId],
        season_number: int,
        episode_number: int,
        file_unique_id: str # Use unique ID to identify the file version subdocument
    ) -> bool:
        """Removes a specific FileVersion subdocument from an episode's files array by file_unique_id."""
        try:
             if not isinstance(anime_id, ObjectId):
                  anime_id = ObjectId(str(anime_id))

             # Build the filter to locate the target episode
             filter_query = {
                  "_id": anime_id,
                  "seasons": {
                       "$elemMatch": {
                            "season_number": season_number,
                            "episodes": {
                                 "$elemMatch": {
                                      "episode_number": episode_number
                                 }
                            }
                       }
                   }
             }

             # Use $pull operator within $set to remove an element from the 'files' array based on a condition.
             # $pull operator in a nested array requires matching the path up to the array
             update_operation = {
                  "$pull": { # Use $pull on the files array path
                      "seasons.$.episodes.$.files": { # Path to the array within the matched season and episode
                           "file_unique_id": file_unique_id # Condition to remove element
                           }
                  },
                 "$set": {"last_updated_at": datetime.now(timezone.utc)} # Update top-level anime modified date
             }

             result = await cls.anime_collection().update_one(
                  filter_query,
                  update_operation
             )

             return result.matched_count > 0 and result.modified_count > 0 # True if found and modified

        except Exception as e:
             db_logger.error(f"Failed to delete file version {file_unique_id} from {anime_id}/S{season_number}E{episode_number}: {e}", exc_info=True)
             return False # Database error or document/path/subdocument not found


    @classmethod
    async def increment_download_counts(
        cls,
        user_id: int,
        anime_id: Union[str, ObjectId, PyObjectId],
        # Add specific counters for episode/file if needed
        # season_number: Optional[int] = None,
        # episode_number: Optional[int] = None,
        # file_unique_id: Optional[str] = None
    ):
        """Atomically increments download counts for a user and an anime."""
        try:
            # Increment user's download count
            user_update_result = await cls.users_collection().update_one(
                {"user_id": user_id},
                {"$inc": {"download_count": 1}, "$set": {"last_activity_at": datetime.now(timezone.utc)}} # Track user last activity too
            )
            # Log if user doc not found or not modified unexpectedly
            if user_update_result.matched_count == 0:
                db_logger.warning(f"Attempted to increment download count for user {user_id}, but user not found.")

            # Increment overall anime download count
            if not isinstance(anime_id, ObjectId):
                 anime_id = ObjectId(str(anime_id))

            anime_update_result = await cls.anime_collection().update_one(
                {"_id": anime_id},
                {"$inc": {"overall_download_count": 1}, "$set": {"last_activity_at": datetime.now(timezone.utc)}} # Track anime activity
            )
             # Log if anime doc not found
            if anime_update_result.matched_count == 0:
                db_logger.warning(f"Attempted to increment overall download count for anime {anime_id}, but anime not found.")


            # Implement increment for episode/file level counters here if they exist and are passed.
            # Requires updating the nested episode/file document. Example using filter_query for episode:
            # if season_number is not None and episode_number is not None:
            #    episode_filter = {"_id": anime_id, "seasons.season_number": season_number, "seasons.0.episodes.episode_number": episode_number}
            #    await cls.anime_collection().update_one(
            #         episode_filter,
            #         {"$inc": {"seasons.$.episodes.$.download_count": 1}} # If download_count field is in Episode model
            #    )
            # if file_unique_id is not None:
            #     # More complex update to increment a count inside the specific FileVersion subdocument if a count is added there.
            #     # Might need arrayFilters if multiple file versions match a path.
            #     pass

            db_logger.debug(f"Incremented download counts for user {user_id} and anime {anime_id}")

        except Exception as e:
             # Log but don't block downloads, counter failure is non-critical
             db_logger.error(f"Failed to increment download counts for user {user_id}, anime {anime_id}: {e}", exc_info=True)


    @classmethod
    async def delete_all_data(cls):
        """
        DANGER: Permanently deletes ALL documents from ALL collections in the database.
        Requires a connected database.
        """
        db_logger.warning("!!!! ATTEMPTING PERMANENT DELETION OF ALL DATABASE DATA !!!!")
        if cls._db is None:
             db_logger.critical("Database not connected. Cannot perform delete_all_data operation.")
             return False # Indicate failure


        try:
             collections = await cls.get_db().list_collection_names()
             db_logger.warning(f"Found collections to delete from: {collections}")

             for collection_name in collections:
                 # Skip internal system collections provided by MongoDB
                 if collection_name.startswith('system.') or collection_name == 'admin':
                      db_logger.info(f"Skipping system collection: {collection_name}")
                      continue

                 db_logger.warning(f"Deleting all documents from collection: {collection_name}")
                 # Use delete_many with an empty filter {} to delete all documents in the collection
                 delete_result = await cls.get_db()[collection_name].delete_many({})
                 db_logger.warning(f"Deleted {delete_result.deleted_count} documents from {collection_name}.")

             db_logger.warning("!!!! ALL USER-FACING AND BOT DATABASE DATA PERMANENTLY DELETED !!!!")
             return True # Indicate success

        except Exception as e:
             # Log any errors that occur during the deletion process
             db_logger.critical(f"FATAL ERROR DURING delete_all_data: {e}", exc_info=True)
             return False # Indicate failure


# --- Initialization Function to be called from main.py ---
async def init_db(uri: str):
    """
    Initializes the database connection and creates/ensures necessary indices.
    This function is designed to be called once at bot startup.
    Raises exceptions if connection or critical index creation fails.
    """
    try:
        # Attempt connection using the MongoDB class method
        await MongoDB.connect(uri, DB_NAME)

        # Get the database instance from the connected client
        db = MongoDB.get_db() # This will raise ConnectionFailure if connection failed

        db_logger.info("Creating/Ensuring MongoDB indices...")
        # Define the list of index creation operations (as coroutines using Motor methods)
        # These operations are idempotent - they only create indices if they don't exist.
        index_coroutines = [
            # User collection indices - Speed up lookups by user_id, sorting by tokens/downloads
            db.users_collection().create_index([("user_id", 1)], unique=True), # Telegram user ID must be unique
            db.users_collection().create_index([("tokens", -1)]), # Descending index on tokens
            db.users_collection().create_index([("download_count", -1)]), # Descending index for leaderboard
            db.users_collection().create_index([("premium_status", 1)]), # Ascending index on premium status
            db.users_collection().create_index([("watchlist", 1)]), # Index if querying users by watchlist contents
            db.users_collection().create_index([("join_date", 1)]), # Index for joining date


            # Anime collection indices - Speed up lookups, searches, and filtering
            # Name index: Basic ascending for sorting/exact match. Collation for case-insensitivity (optional).
            # Using strength 2 means case-insensitive but respects accents/diacritics. locale='en' specifies rules.
            # Ensure your MongoDB supports collation.
            db.anime_collection().create_index(
                 [("name", 1)],
                 unique=True,
                 collation={'locale': 'en', 'strength': 2} # Example case-insensitive unique index
            ),
            # Text index for fuzzy search pre-filtering. Needs to be on a string field.
            db.anime_collection().create_index([("name", "text")]),
            db.anime_collection().create_index([("overall_download_count", -1)]), # For Popular anime list (descending)
            db.anime_collection().create_index([("genres", 1)]), # Index for querying/filtering by genre (array elements)
            db.anime_collection().create_index([("release_year", 1)]), # Index for querying/filtering by year
            db.anime_collection().create_index([("status", 1)]), # Index for querying/filtering by status
            # Index for accessing nested files by unique_id (used for deletion, potentially download by file_id if schema was different)
            # This type of multi-key index on a nested array path can be useful but increases index size/write cost.
            db.anime_collection().create_index([("seasons.episodes.files.file_unique_id", 1)]),
            # Index for accessing nested episode release dates if querying/sorting by date is common
            db.anime_collection().create_index([("seasons.episodes.release_date", 1)]),
             # Index for querying specific episodes or seasons quickly using element match conditions
            # Combined index example (advanced): Could index seasons.season_number AND episodes.episode_number IF these are frequently queried TOGETHER for *specific* episodes.
            # db.anime_collection().create_index([("seasons.season_number", 1), ("seasons.episodes.episode_number", 1)]) # May require reshaping schema or careful $elemMatch queries to use effectively.


            # Requests collection indices - Speed up looking up requests by user or status
            db.requests_collection().create_index([("user_id", 1)]),
            db.requests_collection().create_index([("status", 1)]),
            db.requests_collection().create_index([("requested_at", 1)]), # For sorting requests by date

            # Generated Tokens indices - Speed up lookups by token string and cleanup
            db.generated_tokens_collection().create_index([("token_string", 1)], unique=True), # Token string must be unique
            db.generated_tokens_collection().create_index([("generated_by_user_id", 1)]), # To find tokens generated by a user
            db.generated_tokens_collection().create_index([("expires_at", 1), ("is_redeemed", 1)]), # Compound index for finding expired OR redeemed tokens efficiently


            # User State collection indices - Speed up state lookups
            db.states_collection().create_index([("user_id", 1)], unique=True), # Only one state per user allowed
            db.states_collection().create_index([("handler", 1), ("step", 1)]), # Index for querying/filtering by state type and step
            db.states_collection().create_index([("updated_at", 1)]), # For potential background cleanup of old states based on timestamp
        ]

        # Run all index creation operations concurrently using asyncio.gather
        db_logger.info(f"Executing {len(index_coroutines)} index creation tasks...")
        results = await asyncio.gather(*index_coroutines, return_exceptions=True)

        # Check and log results for each index creation operation
        index_failures = False
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                 index_failures = True
                 # Log failure details, including the exception traceback
                 db_logger.error(f"Failed to create index {i} ('{index_coroutines[i].document.get('key')}'): {res}", exc_info=True)
            # You might want to check if the operation successfully *created* vs *ensured* (modified_count, raw result),
            # but create_index itself often handles this detail internally by checking existence first.

        if index_failures:
             db_logger.warning("Some database indices failed to create. Performance or unique constraints might be impacted.")
             # Decide if index failure is critical enough to halt startup.
             # Failure of a UNIQUE index is usually critical. Other index failures might be okay to log and continue.
             # If a unique index failed, the connect step might already throw an error.
             pass # For now, log and continue even if indices fail

        db_logger.info("MongoDB indices checked/created process finished.")

    except ConnectionFailure as e:
        # ConnectionFailure from MongoDB.connect already logged. Re-raise to stop startup.
        raise

    except Exception as e:
         # Catch any other errors during the initialization process (e.g., issue with collection names, logic error)
         db_logger.critical(f"An unexpected error occurred during overall DB initialization process: {e}", exc_info=True)
         raise # Re-raise to be caught by main.py's init_database error handling and halt bot startup


# Note: DB_NAME and STATE_COLLECTION_NAME are imported from config at the top
