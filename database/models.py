# database/models.py
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, root_validator
from bson import ObjectId # For working with MongoDB ObjectIds

# --- Custom ObjectId handling for Pydantic ---
# Allows Pydantic to validate and serialize MongoDB ObjectIds
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate_id

    @classmethod
    def validate_id(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema: Dict[str, Any]):
        field_schema.update(type="string")


# --- Data Models ---

# Model for File Versions within an episode
class FileVersion(BaseModel):
    file_id: str
    file_unique_id: str
    file_name: str
    file_size_bytes: int
    quality_resolution: str
    audio_languages: List[str] = Field(default=[])
    subtitle_languages: List[str] = Field(default=[])
    added_at: datetime = Field(default_factory=datetime.utcnow)

# Model for Episodes within a season
class Episode(BaseModel):
    episode_number: int
    release_date: Optional[datetime] = None # Only if no files
    files: List[FileVersion] = Field(default=[]) # List of available file versions

    # Custom validator to ensure either release_date OR files exist, not both.
    # Or handle the case where neither exists (interpreted as not announced)
    # @root_validator(pre=True)
    # def check_release_or_files(cls, values):
    #     release_date = values.get('release_date')
    #     files = values.get('files')
    #     if release_date is not None and files:
    #          # In our logic, adding files clears release date, so this might be caught during insert,
    #          # but validation here can be an extra safety.
    #          # If you enforce ONE OR THE OTHER, uncomment below and adjust logic
    #          # raise ValueError("An episode cannot have both a release date and files.")
    #          pass # Our current model allows this briefly before release date is cleared

    class Config:
        # Allows population by field name as well as alias.
        # If using _id, alias = "_id"
        allow_population_by_field_name = True


# Model for Seasons within an anime
class Season(BaseModel):
    season_number: int
    episode_count_declared: Optional[int] = None # Admin-set count
    episodes: List[Episode] = Field(default=[])

# Model for Anime entry
class Anime(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id") # Map Pydantic 'id' to MongoDB '_id'
    name: str
    poster_file_id: Optional[str] = None # Telegraph link might also be used
    synopsis: Optional[str] = None
    total_seasons_declared: int
    genres: List[str] = Field(default=[])
    release_year: Optional[int] = None
    status: str
    seasons: List[Season] = Field(default=[]) # Array of Season objects
    overall_download_count: int = 0 # Track total downloads for popularity
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str} # How to encode ObjectId when converting to JSON/Dict


# Model for User entry
class User(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: int # Telegram User ID
    username: Optional[str] = None
    first_name: Optional[str] = None
    tokens: int = 0 # Download tokens
    premium_status: str = "free" # e.g., "free", "basic_monthly", "pro_yearly"
    premium_expires_at: Optional[datetime] = None # Expiry for premium
    watchlist: List[PyObjectId] = Field(default=[]) # List of Anime _id s
    download_count: int = 0 # Total files downloaded by this user
    is_banned: bool = False
    join_date: datetime = Field(default_factory=datetime.utcnow)
    notification_settings: Dict[str, bool] # See DEFAULT_NOTIFICATION_SETTINGS in config


    class Config:
        json_encoders = {ObjectId: str}


# Model for Request entry
class Request(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: int
    anime_name_requested: str
    status: str = "pending" # e.g., "pending", "unavailable", "added", "not_released", "will_add_soon"
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    admin_notes: Optional[str] = None # Admin reply text or notes

    class Config:
        json_encoders = {ObjectId: str}

# Model for Generated Token entry (for the link redemption)
class GeneratedToken(BaseModel):
     id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
     token_string: str # The unique token used in the start payload
     generated_by_user_id: int # The user who generated this token for themselves
     is_redeemed: bool = False
     redeemed_at: Optional[datetime] = None
     expires_at: datetime
     created_at: datetime = Field(default_factory=datetime.utcnow)

     class Config:
        json_encoders = {ObjectId: str}


# Helper function to convert a Pydantic model to a dictionary suitable for MongoDB insert
def model_to_mongo_dict(model: BaseModel) -> Dict[str, Any]:
    # exclude={"id"} because Pydantic 'id' is just an alias for _id
    # and we want pymongo/motor to handle _id generation if not provided.
    # If _id IS provided (as PyObjectId), it will be included and pymongo uses it.
    return model.dict(by_alias=True, exclude_none=True)
