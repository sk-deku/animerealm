# database/models.py
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone # Import timezone aware datetime
from pydantic import BaseModel, Field # Add Field for _id alias mapping
from bson import ObjectId # For working with MongoDB ObjectIds


# --- Custom ObjectId handling for Pydantic ---
# Allows Pydantic to validate and serialize MongoDB ObjectIds
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate_id

    @classmethod
    def validate_id(cls, v):
        if not isinstance(v, ObjectId):
             if not ObjectId.is_valid(str(v)):
                 raise ValueError("Invalid ObjectId")
             return ObjectId(str(v))
        return v # Already an ObjectId

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema: Dict[str, Any]):
        field_schema.update(type="string")


# --- Data Models ---

# Model for File Versions within an episode (Nested in Episode)
class FileVersion(BaseModel):
    # Note: File versions don't need their own ObjectId, they are subdocuments in an array
    file_id: str
    file_unique_id: str # Use file_unique_id for tracking across different messages
    file_name: str
    file_size_bytes: int
    quality_resolution: str # e.g., "1080p", "720p"
    audio_languages: List[str] = Field(default_factory=list)
    subtitle_languages: List[str] = Field(default_factory=list)
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # When this version was added


# Model for Episodes within a season (Nested in Season)
class Episode(BaseModel):
    # Note: Episodes don't need their own ObjectId in the array
    episode_number: int # e.g., 1, 2, 3
    release_date: Optional[datetime] = None # If episode is scheduled but file not available
    files: List[FileVersion] = Field(default_factory=list) # List of available file versions (qualities/languages)

    # Pydantic validation can check constraints like unique episode number within the season list (requires a root validator or outer logic)

    class Config:
        arbitrary_types_allowed = True # Allow custom types like PyObjectId if needed in nested models
        json_encoders = {ObjectId: str, datetime: lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()} # How to encode to JSON

# Model for Seasons within an anime (Nested in Anime)
class Season(BaseModel):
    # Note: Seasons don't strictly need their own ObjectId in the array unless you require stable IDs for array elements (advanced use case)
    season_number: int # e.g., 1, 2, 3
    episode_count_declared: Optional[int] = None # Admin-set count of expected episodes
    episodes: List[Episode] = Field(default_factory=list) # Array of Episode objects


    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()}

# Model for Anime entry (Top Level Collection)
class Anime(BaseModel):
    # Using PyObjectId for the _id field, aliased to 'id' for easier Python access
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str # Anime name, unique (indexed)
    poster_file_id: Optional[str] = None # Telegram file_id of the poster image
    synopsis: Optional[str] = None
    total_seasons_declared: int = 0 # Total number of seasons as declared by admin
    genres: List[str] = Field(default_factory=list) # List of genres
    release_year: Optional[int] = None
    status: str = "Unknown" # e.g., "Ongoing", "Completed", "Movie", "OVA"
    seasons: List[Season] = Field(default_factory=list) # Array of Season objects

    # Stats
    overall_download_count: int = 0 # Total files downloaded across all episodes of this anime series
    # Track download count per episode for Popular Episodes? Could add `download_count` to Episode model.

    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Timestamp of last update


    class Config:
        allow_population_by_field_name = True # Allow instantiation with 'id' as well as '_id'
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()} # How to encode to JSON


# Model for User entry (Top Level Collection)
class User(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: int # Telegram User ID (Unique Index needed)
    username: Optional[str] = None # Telegram username (@...)
    first_name: Optional[str] = None # Telegram first name
    tokens: int = 0 # Download tokens balance
    premium_status: str = "free" # e.g., "free", "basic_monthly", "pro_yearly", etc.
    premium_expires_at: Optional[datetime] = None # Timestamp when premium expires
    watchlist: List[PyObjectId] = Field(default_factory=list) # List of Anime _id s (as PyObjectId)
    download_count: int = 0 # Total files downloaded by THIS user

    is_banned: bool = False # Ban status
    join_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # When the user first started the bot

    notification_settings: Dict[str, bool] = Field(default_factory=dict) # Dictionary of notification preferences


    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()}


# Model for Anime Request entry (Top Level Collection)
class Request(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: int # Telegram User ID of the requester
    anime_name_requested: str # The name they requested
    status: str = "pending" # e.g., "pending", "unavailable", "added", "not_released", "will_add_soon"
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Timestamp of the request
    admin_notes: Optional[str] = None # Optional notes added by an admin (e.g., why it's unavailable)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()}


# Model for Generated Token entry (for the link redemption - Top Level Collection)
class GeneratedToken(BaseModel):
     id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
     token_string: str # The unique token used in the start payload
     generated_by_user_id: int # The user who generated this token FOR THEMSELVES
     is_redeemed: bool = False
     redeemed_at: Optional[datetime] = None # Timestamp when redeemed
     expires_at: datetime # Timestamp when the link expires
     created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Timestamp when generated


     class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()}


# Model for tracking User State in multi-step processes (Top Level Collection)
class UserState(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: int # Telegram User ID (Unique Index needed)
    handler: str # e.g., "content_management", "request", "search_filter_selection"
    step: str    # e.g., "awaiting_anime_name", "selecting_genres", "awaiting_release_date_input"
    data: Dict[str, Any] = Field(default_factory=dict) # Dictionary to store any necessary temporary data for the state
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) # Track how long user has been in this state


    # Helper method to update the state instance - helpful but state changes also need DB save
    # def update_state(self, handler: str, step: str, data: Dict[str, Any] = None):
    #     self.handler = handler
    #     self.step = step
    #     if data is not None:
    #          self.data.update(data)
    #     self.updated_at = datetime.now(timezone.utc)


    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda dt: dt.replace(tzinfo=timezone.utc).isoformat()}


# Helper function to convert a Pydantic model instance to a dictionary suitable for MongoDB insert/update
# Uses by_alias=True to map 'id' back to '_id' if present, exclude_none=True to remove fields with None (cleaner documents)
# exclude_unset=True (requires Pydantic v1.8+) to exclude fields not explicitly set - good for updates
def model_to_mongo_dict(model: BaseModel, update: bool = False) -> Dict[str, Any]:
    # exclude={"id"} prevents serializing Pydantic's internal 'id' if it wasn't the original _id from DB.
    # However, when using `by_alias=True`, if 'id' corresponds to '_id' and it's set, it will be included as '_id'.
    # exclude_unset=True is good for updates to only send fields that changed.
    # We often build a dictionary manually or use update_one with $set directly rather than converting whole model for updates.
    # This is best used for *initial insert* or *inserting subdocuments*.

    # Use model.model_dump(by_alias=True, exclude_none=True) for Pydantic V2+
    # Use model.dict(by_alias=True, exclude_none=True) for Pydantic V1.x
    # Add exclude_unset=True if needed for partial updates (careful with required fields)
    return model.dict(by_alias=True, exclude_none=True)
