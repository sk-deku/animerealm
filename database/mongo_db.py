# database/mongo_db.py
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient # Asynchronous driver
from pymongo.errors import ConnectionFailure, OperationFailure, ConfigurationError
from pymongo.write_concern import WriteConcern
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone

# Import constants from config
from config import DB_NAME, STATE_COLLECTION_NAME
# Import models for type hinting, validation, and conversion (need model_to_mongo_dict helper)
from database.models import UserState, User, Anime, Request, GeneratedToken, FileVersion, PyObjectId, model_to_mongo_dict


db_logger = logging.getLogger(__name__) # Logger for this module

class MongoDB:
    """
    Singleton class to manage MongoDB connection.
    Uses motor for asyncio compatibility.
    """
    _client: Optional[AsyncIOMotorClient] = None
    _db = None

    @classmethod
    async def connect(cls, uri: str, db_name: str):
        """
        Establishes the asynchronous connection to MongoDB.
        Includes detailed logging.
        Raises ConnectionFailure, OperationFailure, ConfigurationError, or other Exceptions on failure.
        """
        if cls._client is not None and cls._db is not None:
            db_logger.info("MongoDB client appears already connected. Verifying health.")
            try:
                 # A simple async command to check if the connection is responsive (e.g., ping command on admin db)
                 # Accessing client.admin.command requires auth on admin DB, maybe check something simpler.
                 # Getting list of DBs or just db.command('ping') might work if user has rights.
                 # Simpler: Trust motor's internal checks after initial connection unless performance suggests need for proactive health check.
                 # An initial find_one on a collection with timeout might work if it's okay that collection exists.
                 # Let's add a try to do a simple DB command on the selected DB.
                 await cls._db.command('ping') # This requires database to be set and connected

                 db_logger.info("Existing MongoDB connection is healthy (ping successful).")
                 return # Exit, connection is good

            except Exception as e:
                 db_logger.warning(f"Existing MongoDB connection appears unhealthy: {e}. Attempting to reconnect.", exc_info=True)
                 # Don't immediately clear client/db here if just one check failed; maybe Motor handles retry.
                 # Clear client/db ONLY if reconnecting below after connection failure.
                 # If connection *failed* during the initial connection process below, client/db would be None already.
                 pass # Proceed to attempt a new connection if the check failed


        db_logger.info(f"Attempting new connection to MongoDB cluster/server defined by URI (redacted) for database '{db_name}'.")
        try:
            # serverSelectionTimeoutMS: how long the driver will wait to find and connect to servers
            # connectTimeoutMS: how long the driver will wait for the initial TCP connection
            # Specify appName to identify connections in MongoDB logs (optional but good for monitoring)
            cls._client = AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=10000, # Increase timeout slightly (e.g., 10 seconds) for connection readiness
                connectTimeoutMS=5000,          # Timeout for the initial socket connection
                tz_aware=True,                  # Automatically convert BSON datetimes to timezone-aware Python datetimes
                uuidRepresentation='standard',  # Consistent handling of UUIDs
                appname="AnimeRealmBot"         # Identify bot connections in DB logs
            )
            db_logger.debug("AsyncIOMotorClient instance created.")

            # Get the specific database instance.
            # This operation itself does NOT fully establish connection, it sets up the DB object.
            # Set a default write concern (majority recommended for safety and for admin operations like deletion)
            cls._db = cls._client.get_database(db_name, write_concern=WriteConcern(w='majority'))
            db_logger.debug(f"Database instance '{db_name}' obtained with write concern '{WriteConcern(w='majority')}'.")


            # Force an asynchronous operation that requires server interaction to confirm connection and credentials
            # list_collection_names() is relatively lightweight. Add a short timeout specifically for THIS check if it shouldn't hang.
            db_logger.info("Confirming database connection and authentication by listing collections...")
            # Use serverSelectionTimeoutMS from client options implicitly here for server discovery
            await cls._db.list_collection_names(session=None) # Run command without a session explicitly


            db_logger.info(f"Successfully confirmed connection to MongoDB database: '{db_name}'. Ready for operations.")

        except (ConnectionFailure, ConfigurationError, OperationFailure) as e:
            # Catch specific errors during connection or initial command.
            db_logger.critical(f"FATAL MONGODB CONNECTION FAILED: {e}", exc_info=True)
            cls._client = None # Ensure client is None on failure
            cls._db = None # Ensure db is None on failure
            raise # Re-raise to signal fatal error to calling code (main.py)
        except Exception as e:
            # Catch any other unexpected errors during connection setup or initial check.
            db_logger.critical(f"FATAL MONGODB CONNECTION FAILED: An unexpected error occurred: {e}", exc_info=True)
            cls._client = None
            cls._db = None
            raise # Re-raise unexpected errors


    @classmethod
    async def close(cls):
        """Closes the MongoDB connection gracefully."""
        if cls._client:
            db_logger.info("Closing MongoDB connection...")
            try:
                 # MotorClient's close method is synchronous, no await needed here for the method itself.
                 # Ensure all pending async operations on client are finished first before calling sync close?
                 # Rely on Motor's internal cleanup on client close for background pool connections.
                 cls._client.close()
                 db_logger.info("MongoDB connection closed.")
            except Exception as e:
                 db_logger.error(f"Error during MongoDB client close: {e}", exc_info=True)
            finally:
                 cls._client = None
                 cls._db = None # Always reset client/db class variables


    @classmethod
    def get_db(cls):
        """
        Returns the database instance.
        Raises ConnectionFailure if the database connection has not been successfully established.
        """
        if cls._db is None:
            # This indicates code attempted DB access before connect was called or if connect failed.
            db_logger.error("Attempted database access before successful connection was reported.", exc_info=True)
            # This is a programming error if init_db is not awaited/handled in startup.
            raise ConnectionFailure("MongoDB database is not connected or connection failed.")
        # Basic health check? Motor has auto-reconnection built-in. Rely on that for liveness *after* initial connect.
        # Motor also has client.is_connected and client.topology_description.
        # For high robustness, check client.is_connected and connectivity to specific server types.
        # For standard usage, trust Motor's async operations will retry or fail if truly down.
        return cls._db

    # --- Convenience Methods for Collections ---
    # These methods return Motor Collection instances, inheriting default write concern from get_db()
    @classmethod
    def users_collection(cls): return cls.get_db()["users"];
    @classmethod
    def anime_collection(cls): return cls.get_db()["anime"];
    @classmethod
    def requests_collection(cls): return cls.get_db()["requests"];
    @classmethod
    def generated_tokens_collection(cls): return cls.get_db()["generated_tokens"];
    @classmethod
    def states_collection(cls): return cls.get_db()[STATE_COLLECTION_NAME];

    # --- State Management Utility Methods ---
    # Using the UserState model and STATE_COLLECTION_NAME

    @classmethod
    async def get_user_state(cls, user_id: int) -> Optional[UserState]:
        """Retrieves the current state for a user, returns as UserState model. Handles errors gracefully."""
        db_logger.debug(f"Attempting to get state for user {user_id}.")
        try:
            state_doc = await cls.states_collection().find_one({"user_id": user_id});
            if state_doc:
                try:
                    # Use Pydantic model for validation
                    state_instance = UserState(**state_doc);
                    db_logger.debug(f"State found and validated for user {user_id}: {state_instance.handler}:{state_instance.step}");
                    return state_instance;
                except Exception as e:
                    db_logger.error(f"STATE DATA VALIDATION FAILED: Could not validate state data from DB for user {user_id}: {e}", exc_info=True);
                    # Critical state data error. Log, and consider clearing the corrupted state document automatically?
                    # Automated clearing is risky, user might lose process progress. Log and require manual intervention if needed.
                    # Return None indicates state found but invalid/unusable. Handlers must handle None.
                    return None;
            else:
                 db_logger.debug(f"No state found for user {user_id}.");
                 return None; # No state found
        except Exception as e:
            # Log any database driver error during find_one operation
            db_logger.error(f"DATABASE ERROR: Failed to fetch user state from DB for user {user_id}: {e}", exc_info=True);
            # This might be a temporary DB issue. Handlers might retry. Return None or raise a specific DB error?
            # Returning None is consistent with 'not found', requires callers to differentiate failure vs not exist.
            # Let's return None on database error during fetch.
            return None;


    @classmethod
    async def set_user_state(cls, user_id: int, handler: str, step: str, data: Optional[Dict[str, Any]] = None):
        """Sets or updates the state for a user. Handles DB errors."""
        db_logger.debug(f"Attempting to set state for user {user_id} to {handler}:{step} with data keys: {list(data.keys()) if data else 'None'}.");
        # Construct the state data to be written/updated.
        state_doc_update = {
            "user_id": user_id, # Always ensure user_id is in $set for upsert filter
            "handler": handler,
            "step": step,
            "data": data if data is not None else {},
            "updated_at": datetime.now(timezone.utc) # Set timestamp
        };
        try:
            # Use update_one with upsert=True ($set overwrites, $setOnInsert adds fields only if new doc)
            result = await cls.states_collection().update_one(
                {"user_id": user_id},
                {"$set": state_doc_update, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}}, # Set creation time only on new insert
                upsert=True # Insert if document for this user_id doesn't exist
            );

            if result.upserted_id: db_logger.debug(f"Inserted initial state for user {user_id} ({handler}:{step}). Doc ID: {result.upserted_id}");
            elif result.matched_count > 0: db_logger.debug(f"Updated state for user {user_id} ({handler}:{step}). Modified count: {result.modified_count}");
            else: db_logger.warning(f"Set state operation matched 0 documents and did not upsert for user {user_id} ({handler}:{step}). Unexpected result.", exc_info=True);


        except Exception as e:
             db_logger.error(f"DATABASE ERROR: Failed to set state for user {user_id} ({handler}:{step}): {e}", exc_info=True);
             # Handle failure: log, retry internally? Or caller handles? Log is minimum.

    @classmethod
    async def clear_user_state(cls, user_id: int):
        """Removes the state document for a specific user. Handles DB errors."""
        db_logger.debug(f"Attempting to clear state for user {user_id}.");
        try:
            result = await cls.states_collection().delete_one({"user_id": user_id});
            if result.deleted_count > 0: db_logger.debug(f"Cleared state for user {user_id}.");
            else: db_logger.debug(f"No state found to clear for user {user_id}.");
        except Exception as e:
            db_logger.error(f"DATABASE ERROR: Failed to clear state for user {user_id}: {e}", exc_info=True);

    # --- Common Data Interaction Utility Methods (Detailed Logging Added) ---

    @classmethod
    async def get_anime_by_id(cls, anime_id: Union[str, ObjectId, PyObjectId]) -> Optional[Anime]:
        """Retrieves a single anime document by its _id, returns as Anime model. Handles errors."""
        db_logger.debug(f"Attempting to get anime by ID: {anime_id}.");
        try:
            # Ensure input ID is ObjectId type for query
            if not isinstance(anime_id, ObjectId): anime_id_obj = ObjectId(str(anime_id));
            else: anime_id_obj = anime_id;

            anime_doc = await cls.anime_collection().find_one({"_id": anime_id_obj});
            if anime_doc:
                try:
                    anime_instance = Anime(**anime_doc);
                    db_logger.debug(f"Found and validated anime: {anime_instance.name} ({anime_instance.id}).");
                    return anime_instance;
                except Exception as e:
                    db_logger.error(f"ANIME DATA VALIDATION FAILED: Could not validate Anime data for ID {anime_id}: {e}", exc_info=True);
                    return None; # Data corruption/schema mismatch

            db_logger.debug(f"Anime with ID {anime_id} not found in database.");
            return None; # Document not found

        except Exception as e:
            # Catch potential invalid ObjectId string format or database driver error during find
            db_logger.error(f"DATABASE ERROR: Failed to get anime by ID {anime_id}: {e}", exc_info=True);
            return None;

    @classmethod
    async def add_file_version_to_episode(
        cls,
        anime_id: Union[str, ObjectId, PyObjectId],
        season_number: int,
        episode_number: int,
        file_version: FileVersion # Pydantic model instance
    ) -> bool:
        """Adds a FileVersion subdocument to a specific episode's files array. Handles DB errors."""
        db_logger.debug(f"Attempting to add file version '{file_version.file_unique_id}' to {anime_id}/S{season_number}E{episode_number}.");
        try:
            if not isinstance(anime_id, ObjectId): anime_id_obj = ObjectId(str(anime_id));
            else: anime_id_obj = anime_id;

            # Use $elemMatch in filter for precision, positional operator $ for update path.
            filter_query = {
                 "_id": anime_id_obj,
                 "seasons": { "$elemMatch": {"season_number": season_number,
                     "episodes": { "$elemMatch": {"episode_number": episode_number} }
                 }}
            };
            # Update operation adds to files array and updates timestamp, removes release_date.
            update_operation = {
                 "$push": {"seasons.$.episodes.$.files": model_to_mongo_dict(file_version)}, # Add subdocument dictionary
                 "$set": {"last_updated_at": datetime.now(timezone.utc)}, # Update parent timestamp
                 # Remove release_date field from episode subdocument using $unset
                 "$unset": { "seasons.$.episodes.$.release_date": "" } # Unset requires field path and empty string value
            };


            result = await cls.anime_collection().update_one(
                filter_query, update_operation
            );

            if result.matched_count == 0: db_logger.warning(f"Add file version matched 0 documents for {anime_id}/S{season_number}E{episode_number}. Path not found.");
            elif result.modified_count == 0: db_logger.warning(f"Add file version matched {result.matched_count} but modified 0 for {anime_id}/S{season_number}E{episode_number}. Already existed?"); # Pushing always modifies unless array is huge and needs explicit space check?


            db_logger.debug(f"Add file version update result: matched={result.matched_count}, modified={result.modified_count}.");

            return result.matched_count > 0 and result.modified_count > 0; # True if document matched and modified


        except Exception as e:
             db_logger.error(f"DATABASE ERROR: Failed to add file version '{file_version.file_unique_id}' to episode {anime_id}/S{season_number}E{episode_number}: {e}", exc_info=True);
             return False;

    @classmethod
    async def delete_file_version_from_episode(
        cls,
        anime_id: Union[str, ObjectId, PyObjectId],
        season_number: int,
        episode_number: int,
        file_unique_id: str
    ) -> bool:
        """Removes a specific FileVersion subdocument from an episode's files array. Handles DB errors."""
        db_logger.debug(f"Attempting to delete file version with unique_id '{file_unique_id}' from {anime_id}/S{season_number}E{episode_number}.");
        try:
             if not isinstance(anime_id, ObjectId): anime_id_obj = ObjectId(str(anime_id));
             else: anime_id_obj = anime_id;

             filter_query = {
                  "_id": anime_id_obj,
                  "seasons": { "$elemMatch": {"season_number": season_number,
                      "episodes": { "$elemMatch": {"episode_number": episode_number} }
                  }}
             };
             # $pull operator on the files array, inside the matched episode and season.
             update_operation = {
                  "$pull": { "seasons.$.episodes.$.files": {"file_unique_id": file_unique_id} },
                  "$set": {"last_updated_at": datetime.now(timezone.utc)} # Update parent timestamp
             };

             result = await cls.anime_collection().update_one( filter_query, update_operation );

             if result.matched_count == 0: db_logger.warning(f"Delete file version matched 0 documents for {anime_id}/S{season_number}E{episode_number}. Path not found?");
             elif result.modified_count == 0: db_logger.warning(f"Delete file version matched {result.matched_count} but modified 0 for {anime_id}/S{season_number}E{episode_number}. Version '{file_unique_id}' not found?");

             db_logger.debug(f"Delete file version update result: matched={result.matched_count}, modified={result.modified_count}.");


             return result.matched_count > 0 and result.modified_count > 0; # True if document matched and modified


        except Exception as e:
             db_logger.error(f"DATABASE ERROR: Failed to delete file version '{file_unique_id}' from {anime_id}/S{season_number}E{episode_number}: {e}", exc_info=True);
             return False;


    @classmethod
    async def increment_download_counts(
        cls,
        user_id: int,
        anime_id: Union[str, ObjectId, PyObjectId],
    ):
        """Atomically increments download counts for a user and an anime. Logs errors, doesn't raise."""
        db_logger.debug(f"Attempting to increment download counts for user {user_id} and anime {anime_id}.");
        try:
            user_update_result = await cls.users_collection().update_one({"user_id": user_id}, {"$inc": {"download_count": 1}, "$set": {"last_activity_at": datetime.now(timezone.utc)}});
            if user_update_result.matched_count == 0: db_logger.warning(f"Increment user download count matched 0 users for ID {user_id}. User not found.");
            else: db_logger.debug(f"Incremented user download count for {user_id}. Matched: {user_update_result.matched_count}, Modified: {user_update_result.modified_count}.");

            if not isinstance(anime_id, ObjectId): anime_id_obj = ObjectId(str(anime_id)); else: anime_id_obj = anime_id;
            anime_update_result = await cls.anime_collection().update_one({"_id": anime_id_obj}, {"$inc": {"overall_download_count": 1}, "$set": {"last_activity_at": datetime.now(timezone.utc)}});
            if anime_update_result.matched_count == 0: db_logger.warning(f"Increment anime overall download count matched 0 anime for ID {anime_id_obj}. Anime not found.");
            else: db_logger.debug(f"Incremented anime overall download count for {anime_id_obj}. Matched: {anime_update_result.matched_count}, Modified: {anime_update_result.modified_count}.");

        except Exception as e:
             db_logger.error(f"DATABASE ERROR: Failed to increment download counts for user {user_id}, anime {anime_id}: {e}", exc_info=True);
             # Log only, this error is not critical to the user interaction success


    @classmethod
    async def delete_all_data(cls):
        """DANGER: Permanently deletes ALL documents from all collections. Logs progress and errors."""
        db_logger.warning("!!!! ADMIN INITIATED PERMANENT DELETION OF ALL DATABASE DATA !!!!");
        if cls._db is None: db_logger.critical("Database not connected. Cannot perform delete_all_data operation."); return False;

        try:
             collections = await cls.get_db().list_collection_names();
             db_logger.warning(f"Identified collections to delete from: {collections}. Excluding system collections.");

             deletion_success = True
             for collection_name in collections:
                 if collection_name.startswith('system.'): # Skip internal system collections
                      db_logger.debug(f"Skipping system collection: {collection_name}");
                      continue

                 db_logger.warning(f"Attempting to delete all documents from collection: {collection_name}...");
                 try:
                     delete_result = await cls.get_db()[collection_name].delete_many({});
                     db_logger.warning(f"Successfully deleted {delete_result.deleted_count} documents from {collection_name}.");
                 except Exception as e:
                     db_logger.critical(f"COLLECTION DELETION FAILED: Error deleting documents from {collection_name}: {e}", exc_info=True);
                     deletion_success = False # Mark overall operation as failed


             if deletion_success: db_logger.warning("!!!! ALL USER-FACING AND BOT DATABASE DATA PERMANENTLY DELETED REPORTED SUCCESS !!!!");
             else: db_logger.critical("!!!! DATABASE DELETION PROCESS FINISHED WITH ERRORS (CHECK LOGS ABOVE) !!!!");

             return deletion_success;

        except Exception as e:
             db_logger.critical(f"FATAL ERROR DURING delete_all_data execution: {e}", exc_info=True);
             return False;


# --- Initialization Function to be called from main.py ---
async def init_db(uri: str):
    """
    Initializes the database connection and creates/ensures necessary indices.
    Handles connection and indexing errors with critical logging and exits.
    """
    main_logger = logging.getLogger("main") # Get main logger for messages going to stdout initially
    db_logger.info("Database initialization sequence started.");

    try:
        # Attempt connection using the MongoDB class method
        db_logger.info("Calling MongoDB.connect to establish connection.");
        await MongoDB.connect(uri, DB_NAME); # Connect method handles logging connection success/failure

        # Connection is successful, get database instance for indexing
        db_logger.info("Database connection reported success by MongoDB.connect. Proceeding to indexing.");
        db = MongoDB.get_db(); # Should not raise ConnectionFailure here if connect succeeded


        db_logger.info("Creating/Ensuring MongoDB indices for performance and constraints...");
        index_coroutines = [
            db.users_collection().create_index([("user_id", 1)], unique=True),
            db.users_collection().create_index([("tokens", -1)]),
            db.users_collection().create_index([("download_count", -1)]),
            db.users_collection().create_index([("premium_status", 1)]),
            db.users_collection().create_index([("watchlist", 1)]),
            db.users_collection().create_index([("join_date", 1)]),

            db.anime_collection().create_index([("name", 1)], unique=True, collation={'locale': 'en', 'strength': 2}), # Case-insensitive unique
            db.anime_collection().create_index([("name", "text")]),
            db.anime_collection().create_index([("overall_download_count", -1)]),
            db.anime_collection().create_index([("genres", 1)]),
            db.anime_collection().create_index([("release_year", 1)]),
            db.anime_collection().create_index([("status", 1)]),
            db.anime_collection().create_index([("seasons.season_number", 1)]), # Index on season number within array
            db.anime_collection().create_index([("seasons.episodes.episode_number", 1)]), # Index on episode number within nested array
            db.anime_collection().create_index([("seasons.episodes.files.file_unique_id", 1)]),
            db.anime_collection().create_index([("seasons.episodes.release_date", 1)]),

            db.requests_collection().create_index([("user_id", 1)]),
            db.requests_collection().create_index([("status", 1)]),
            db.requests_collection().create_index([("requested_at", 1)]),
            db.requests_collection().create_index([("anime_name_requested", 1)]), # Add index on requested name for querying
             # Index for linking admin notification message to request if needed:
             db.requests_collection().create_index([("admin_message_id", 1)]),


            db.generated_tokens_collection().create_index([("token_string", 1)], unique=True),
            db.generated_tokens_collection().create_index([("generated_by_user_id", 1)]),
            db.generated_tokens_collection().create_index([("expires_at", 1), ("is_redeemed", 1)]),

            db.states_collection().create_index([("user_id", 1)], unique=True),
            db.states_collection().create_index([("handler", 1), ("step", 1)]),
            db.states_collection().create_index([("updated_at", 1)]),
        ];

        db_logger.info(f"Executing {len(index_coroutines)} index creation tasks concurrently...");
        # Use asyncio.gather to run all create_index operations in parallel
        # return_exceptions=True prevents gathering from stopping on the first exception.
        results = await asyncio.gather(*index_coroutines, return_exceptions=True);

        # Check results and log specific failures for index creation
        index_failures = False;
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                 index_failures = True;
                 # Log the failure, identify which index if possible using its properties or the original coroutine structure
                 try:
                      index_key = index_coroutines[i].document.get('key') if hasattr(index_coroutines[i], 'document') else f"Index {i}"; # Get index key definition
                      db_logger.error(f"INDEX CREATION FAILED: Index on {index_key} failed with error: {res}", exc_info=True);
                      # Specific error types from pymongo.errors could be caught if detailed handling needed per type
                 except Exception: # Fallback if identifying index fails
                     db_logger.error(f"INDEX CREATION FAILED: Index task {i} failed: {res}", exc_info=True);

        if index_failures:
             db_logger.warning("One or more database indices failed to create. Check logs. Performance or data integrity constraints might be impacted.");
             # Criticality of index failure depends on the index (e.g., unique index failure is critical)
             # If a unique index failed, MongoDB.connect or an earlier create_index might have already raised.
             # Assuming we log warnings here for non-critical index failures.


        db_logger.info("Database indexing process completed.");

    except ConnectionFailure as e:
         # If connect method already failed with ConnectionFailure, it raised, and main() would have caught it and exited.
         # This specific except might catch it again if connect failed in a weird way.
         db_logger.critical(f"FATAL DB INIT FAILED: Database connection failed during initialization (after connect returned): {e}", exc_info=True); # Redundant but safer log
         raise # Re-raise to stop startup in main()

    except OperationFailure as e:
         # Catch OperationFailure from DB interactions during indexing (e.g., permissions)
         db_logger.critical(f"FATAL DB INIT FAILED: Database operation error during indexing: {e}", exc_info=True);
         raise # Re-raise to stop startup in main()

    except Exception as e:
         # Catch any other errors during the entire init_db process (e.g., list comprehension failure, sorting error, gather error handling itself)
         db_logger.critical(f"FATAL DB INIT FAILED: An unexpected error occurred during overall DB initialization process: {e}", exc_info=True);
         raise # Re-raise to be caught by main.py's init_database error handling and halt bot startup
