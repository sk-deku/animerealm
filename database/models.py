# database/models.py
from pydantic import BaseModel, Field, HttpUrl, field_validator, PositiveInt, validator
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime
from bson import ObjectId # For ObjectId handling if you expose it

# Pydantic helper for MongoDB's ObjectId
# You can use this if you need to serialize ObjectIds as strings
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, _: Any): # Changed handler_deprecated to _
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema): # Replaced with new Pydantic v2 method if needed for schema gen
        field_schema.update(type="string")


# --- Sub-models for nested structures ---

class FileVersion(BaseModel):
    file_id: str
    file_type: Literal["document", "video"]
    resolution: str # Should ideally be from settings.SUPPORTED_RESOLUTIONS but Pydantic enums need direct values
    audio_language: str # From settings.SUPPORTED_AUDIO_LANGUAGES
    subtitle_language: str # From settings.SUPPORTED_SUB_LANGUAGES
    file_size_bytes: int
    upload_date: datetime = Field(default_factory=datetime.utcnow)

class Episode(BaseModel):
    episode_number: PositiveInt
    # episode_title: Optional[str] = None # Removed per earlier plan
    air_date: Optional[datetime | Literal["TBA"]] = None # Store "TBA" string or actual datetime
    versions: List[FileVersion] = Field(default_factory=list)

class Season(BaseModel):
    season_number: PositiveInt
    # season_title: Optional[str] = None # Removed per earlier plan
    episodes: List[Episode] = Field(default_factory=list)

# --- Main Collection Models ---

class User(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None) # For MongoDB _id
    telegram_id: int
    first_name: str
    username: Optional[str] = None
    download_tokens: int = 0
    premium_status: bool = False
    premium_expiry_date: Optional[datetime] = None
    watchlist: List[str] = Field(default_factory=list) # List of anime_id (strings)
    join_date: datetime = Field(default_factory=datetime.utcnow)
    last_active_date: datetime = Field(default_factory=datetime.utcnow)
    tokens_earned_today: int = 0
    last_token_earn_reset_date: datetime = Field(default_factory=lambda: datetime.utcnow().date()) # Stores date object
    notification_preferences: Dict[str, bool] = Field(default_factory=lambda: {"watchlist_new_episode": True, "quality_update": False})
    is_banned: bool = False

    class Config:
        populate_by_name = True # Allows use of Pydantic alias "_id"
        json_encoders = {ObjectId: str} # Serialize ObjectId to str for JSON output
        arbitrary_types_allowed = True # For PyObjectId

class Anime(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    title_english: str
    # title_romaji: Optional[str] = None # If you decide to add other titles
    # title_japanese: Optional[str] = None
    poster_file_id: str # Can be a Telegram file_id or a URL (validated if it's a URL)
    synopsis: str
    genres: List[str] # Values from settings.AVAILABLE_GENRES
    release_year: int
    status: str # Value from settings.AVAILABLE_STATUSES
    anime_type: str = Field(alias="type", default="TV") # Using alias to match DB field 'type'
    # ^ values: "TV", "Movie", "OVA", "Special" - can make Literal
    seasons: List[Season] = Field(default_factory=list)
    added_date: datetime = Field(default_factory=datetime.utcnow)
    last_content_update: datetime = Field(default_factory=datetime.utcnow) # Updated when episodes/versions are added/modified
    download_count: int = 0

    @field_validator('poster_file_id') # Pydantic v2 validator
    @classmethod
    def check_poster_is_url_or_fileid(cls, value: str):
        # Basic check: if it starts with http, assume URL, else assume file_id (which are complex strings)
        if not value.startswith("http") and not value.startswith("https://via.placeholder.com"):
            # Add more sophisticated file_id validation if needed, e.g., length, character set
            # For now, any non-URL string is accepted as a potential file_id.
            pass
        return value

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True

class AnimeRequest(BaseModel): # For optional DB logging of requests
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    user_telegram_id: int
    user_first_name: str # Denormalized for easier viewing
    anime_title_requested: str
    request_date: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["Pending_In_Channel", "Fulfilled_by_admin", "User_Notified_Unavailable", "User_Notified_Not_Released", "Admin_Ignored"]
    is_premium_request: bool
    admin_handler_name: Optional[str] = None # Admin who handled it
    last_updated_date: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True

class GeneratedReferralCode(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    referral_code: str
    creator_user_id: int
    tokens_to_award: int # For the referrer
    expiry_date: datetime # Expiry of the referral opportunity itself
    is_claimed: bool = False
    claimed_by_user_id: Optional[int] = None # User who used this link
    creation_date: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True

# --- Optional: Model for user data in context.user_data (if you want typed context data) ---
class BotUserContextData(BaseModel):
    # Content Management Flow
    cm_flow: Optional[str] = None
    cm_anime_data: Optional[dict] = None # Stores temp anime data being built
    cm_current_anime_id: Optional[str] = None # _id of anime being modified/managed
    cm_selected_genres: Optional[List[str]] = None
    cm_current_season_num: Optional[int] = None
    cm_current_episode_num: Optional[int] = None
    cm_current_file_version_data: Optional[dict] = None # Temp data for one file version
    cm_modify_search_query: Optional[str] = None
    cm_modify_current_page: Optional[int] = None
    cm_mod_current_field: Optional[str] = None # Field being edited in modify flow

    # Search Pagination (example, could be handled differently)
    last_search_query_for_pagination: Optional[str] = None
    # last_search_results_ids_for_pagination: Optional[List[str]] = None # Less used if re-querying

    # Other temporary state for conversations
    # Example: broadcast_message_content: Optional[str] = None

    class Config:
        extra = 'allow' # Allow other keys not defined in model for flexibility in user_data
