from motor.motor_asyncio import AsyncIOMotorClient
import config
import logging

LOGGER = logging.getLogger(__name__)

class Database:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Database, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'client'):  # Initialize only once
            try:
                self.client = AsyncIOMotorClient(config.MONGO_URI)
                self.db = self.client[config.DATABASE_NAME]
                LOGGER.info("Successfully connected to MongoDB.")
                
                # Collections
                self.users = self.db.users
                self.access_tokens = self.db.access_tokens
                self.animes = self.db.animes # For anime series metadata
                self.seasons = self.db.seasons # For season metadata, links to anime
                self.episodes = self.db.episodes # For episode files and details, links to season
                self.anime_requests = self.db.anime_requests # For user requests
                self.user_activity = self.db.user_activity # For download logs, token earn logs
                self.bot_settings = self.db.bot_settings # For dynamic config by admin

                # Create indexes (example)
                # It's good practice to create indexes on fields you frequently query or sort by
                # self.users.create_index('user_id', unique=True)
                # self.animes.create_index('title_searchable', unique=False) # For text search
                # self.episodes.create_index('file_unique_id', unique=False)
                
            except Exception as e:
                LOGGER.error(f"Failed to connect to MongoDB: {e}")
                self.client = None
                self.db = None
                raise

    async def test_connection(self):
        if self.client:
            try:
                await self.client.admin.command('ping')
                LOGGER.info("MongoDB ping successful.")
                return True
            except Exception as e:
                LOGGER.error(f"MongoDB ping failed: {e}")
                return False
        return False

    async def get_db_stats(self):
        if self.db is not None:
            try:
                stats = await self.db.command("dbStats")
                data_size_gb = stats.get("dataSize", 0) / (1024 * 1024 * 1024)
                storage_size_gb = stats.get("storageSize", 0) / (1024 * 1024 * 1024)
                return f"Data: {data_size_gb:.2f}GB / Storage: {storage_size_gb:.2f}GB (Objects: {stats.get('objects', 0)})"
            except Exception as e:
                LOGGER.warning(f"Could not retrieve DB stats: {e}")
                return "N/A (Admin privs might be required)"
        return "N/A"

# Initialize the database instance
db = Database()
