from .connection import db
from datetime import datetime, timedelta
import uuid
import config
import logging
import re
from pymongo import ReturnDocument, ASCENDING, DESCENDING
from bson import ObjectId # Important for querying by _id

LOGGER = logging.getLogger(__name__)

# Helper for text search (case-insensitive, removing special chars for title matching)
def sanitize_for_search(text: str):
    if not text: return ""
    return re.sub(r'[^\w\s]', '', text).lower().strip()

# --- User Operations ---
async def add_user_if_not_exists(user_id: int, username: str = None, first_name: str = None):
    current_username = username or first_name or f"User_{user_id}" # Get the most current username
    
    # Fields that are set ONLY on insert
    fields_on_insert = {
        'user_id': user_id, # Match field, also set on insert
        'download_tokens': 0,
        'is_premium': False,
        'premium_expiry_date': None,
        'join_date': datetime.utcnow(),
        'watchlist': [],
        'settings': {
            'preferred_quality': '720p',
            'preferred_audio': 'SUB',
            'watchlist_notifications': True
        },
        'last_token_earn_date': None,
        'tokens_earned_today': 0,
        'last_download_date': None,
        'downloads_today': 0,
    }

    # Fields that are updated on every call (match or insert)
    fields_to_set = {
        'username': current_username,
        'first_name': first_name 
    }
    
    
    update_doc = {
        '$setOnInsert': { # Fields that will be set IF a new document is created
            'user_id': user_id,
            'download_tokens': 0,
            'is_premium': False,
            'premium_expiry_date': None,
            'join_date': datetime.utcnow(),
            'watchlist': [],
            'settings': {
                'preferred_quality': '720p',
                'preferred_audio': 'SUB',
                'watchlist_notifications': True
            },
            'last_token_earn_date': None,
            'tokens_earned_today': 0,
            'last_download_date': None,
            'downloads_today': 0,
        },
        '$set': { # Fields that will be set whether new or existing (updates if exists)
            'username': current_username,
            'first_name': first_name
        }
    }

    user = await db.users.find_one_and_update(
        {'user_id': user_id},
        update_doc,
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    #LOGGER.info(f"User {user_id} ({current_username}) ensured/updated in DB.") # Already have this in start_handler
    return user


async def get_user(user_id: int):
    return await db.users.find_one({'user_id': user_id})

async def get_user_by_username(username: str):
    # Telegram usernames are case-insensitive in search
    # Strip @ if present
    clean_username = username.lstrip('@')
    return await db.users.find_one({'username': re.compile(f'^{re.escape(clean_username)}$', re.IGNORECASE)})


async def update_user_tokens(user_id: int, token_change: int):
    user = await db.users.find_one_and_update(
        {'user_id': user_id},
        {'$inc': {'download_tokens': token_change}},
        return_document=ReturnDocument.AFTER
    )
    if not user: # Should be extremely rare if add_user_if_not_exists is used
        LOGGER.error(f"Attempted to update tokens for non-existent user {user_id}")
        return 0
    if user['download_tokens'] < 0: # Ensure tokens don't go negative
        await db.users.update_one({'user_id': user_id}, {'$set': {'download_tokens': 0}})
        return 0
    return user['download_tokens']

async def can_earn_tokens(user_id: int):
    user = await get_user(user_id)
    if not user: return False

    now_datetime = datetime.utcnow() # Use datetime
    today_date = now_datetime.date() # For comparison logic

    last_earn_datetime = user.get('last_token_earn_date') # This will be a datetime object from DB
    tokens_earned_today = user.get('tokens_earned_today', 0)

    if last_earn_datetime and last_earn_datetime.date() == today_date: # Compare date parts
        return tokens_earned_today < config.TOKENS_PER_BYPASS # Assuming TOKENS_PER_BYPASS is daily limit for earning
    else: 
        # Reset for new day, store full datetime
        await db.users.update_one({'user_id': user_id}, {'$set': {'tokens_earned_today': 0, 'last_token_earn_date': now_datetime}})
        return True

async def record_token_earn(user_id: int):
    await db.users.update_one(
        {'user_id': user_id},
        {'$inc': {'tokens_earned_today': 1}, '$set': {'last_token_earn_date': datetime.utcnow()}} # Store full datetime
    )

async def can_download_today(user_id: int):
    user = await get_user(user_id)
    if not user or user['is_premium']:
        return True

    now_datetime = datetime.utcnow()
    today_date = now_datetime.date()

    last_download_datetime = user.get('last_download_date') # datetime from DB
    downloads_today = user.get('downloads_today', 0)

    if last_download_datetime and last_download_datetime.date() == today_date: # Compare date parts
        return downloads_today < config.FREE_USER_DOWNLOAD_LIMIT_PER_DAY
    else:
        await db.users.update_one({'user_id': user_id}, {'$set': {'downloads_today': 0, 'last_download_date': now_datetime}})
        return True

async def record_download(user_id: int, anime_id: ObjectId, episode_id: ObjectId):
    await db.users.update_one(
        {'user_id': user_id},
        {'$inc': {'downloads_today': 1}, '$set': {'last_download_date': datetime.utcnow()}} # Store full datetime
    )
    await db.user_activity.insert_one({
        'user_id': user_id, 'action': 'download', 'anime_id': anime_id,
        'episode_id': episode_id, 'timestamp': datetime.utcnow()
    })


async def update_user_setting(user_id: int, setting_key: str, setting_value):
    return await db.users.update_one(
        {'user_id': user_id},
        {'$set': {f'settings.{setting_key}': setting_value}}
    )

# --- Watchlist Operations ---
async def add_to_watchlist(user_id: int, anime_obj_id: ObjectId):
    # Ensure anime_obj_id is ObjectId
    if not isinstance(anime_obj_id, ObjectId):
        anime_obj_id = ObjectId(anime_obj_id)

    result = await db.users.update_one(
        {'user_id': user_id},
        {'$addToSet': {'watchlist': anime_obj_id}} # $addToSet prevents duplicates
    )
    return result.modified_count > 0

async def remove_from_watchlist(user_id: int, anime_obj_id: ObjectId):
    if not isinstance(anime_obj_id, ObjectId):
        anime_obj_id = ObjectId(anime_obj_id)
    result = await db.users.update_one(
        {'user_id': user_id},
        {'$pull': {'watchlist': anime_obj_id}}
    )
    return result.modified_count > 0

async def get_watchlist_animes(user_id: int, page: int = 1, per_page: int = config.ITEMS_PER_PAGE):
    user = await get_user(user_id)
    if not user or not user.get('watchlist'):
        return [], 0

    anime_ids = user['watchlist']
    total_items = len(anime_ids)
    
    # Paginate the IDs first, then fetch the anime details
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    paginated_anime_ids = anime_ids[start_index:end_index]

    watchlist_animes = await db.animes.find(
        {'_id': {'$in': paginated_anime_ids}}
    ).to_list(length=per_page)
    
    # Maintain original order from watchlist (if MongoDB doesn't guarantee it with $in)
    ordered_animes = sorted(watchlist_animes, key=lambda x: paginated_anime_ids.index(x['_id']))
    return ordered_animes, total_items

async def is_in_watchlist(user_id: int, anime_obj_id: ObjectId):
    if not isinstance(anime_obj_id, ObjectId):
        anime_obj_id = ObjectId(anime_obj_id)
    user = await get_user(user_id)
    return user and anime_obj_id in user.get('watchlist', [])

# --- Access Token Operations ---
async def create_access_token(user_id: int):
    # ... (same as before) ...
    token_value = str(uuid.uuid4()).replace('-', '') # Unique token
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(hours=config.TOKEN_EXPIRY_HOURS)
    
    token_doc = {
        'token_value': token_value,
        'user_id': user_id,
        'tokens_to_grant': config.TOKENS_PER_BYPASS,
        'status': 'pending', # pending, used, expired
        'created_at': created_at,
        'expires_at': expires_at
    }
    await db.access_tokens.insert_one(token_doc)
    LOGGER.info(f"Access token {token_value} created for user {user_id}")
    return token_value


async def get_access_token(token_value: str):
    # ... (same as before) ...
    return await db.access_tokens.find_one({'token_value': token_value})


async def use_access_token(token_value: str):
    # ... (same as before) ...
    return await db.access_tokens.update_one(
        {'token_value': token_value, 'status': 'pending'},
        {'$set': {'status': 'used'}}
    )


async def mark_token_expired(token_value: str):
    # ... (same as before) ...
     await db.access_tokens.update_one(
        {'token_value': token_value, 'status': 'pending'},
        {'$set': {'status': 'expired'}}
    )


# --- Anime Content Operations ---
# - ANIME SERIES -
async def add_anime(title: str, original_title: str, synopsis: str, year: int, status: str, genres: list, poster_url: str, aliases: list, added_by: int):
    # Create a searchable version of title and aliases
    title_searchable = sanitize_for_search(title)
    aliases_searchable = [sanitize_for_search(a) for a in aliases if a]
    
    anime_doc = {
        'title': title,
        'title_searchable': title_searchable,
        'original_title': original_title,
        'synopsis': synopsis,
        'year': year,
        'status': status,
        'genres': genres, # List of strings
        'poster_url': poster_url,
        'aliases': aliases,
        'aliases_searchable': aliases_searchable,
        'added_by_user_id': added_by,
        'added_at': datetime.utcnow(),
        'last_updated_at': datetime.utcnow(),
        'download_count': 0 # For popularity
    }
    result = await db.animes.insert_one(anime_doc)
    return result.inserted_id

async def get_anime_by_id(anime_id: str | ObjectId):
    if isinstance(anime_id, str):
        try:
            anime_id = ObjectId(anime_id)
        except: return None # Invalid ObjectId string
    return await db.animes.find_one({'_id': anime_id})

async def find_anime_by_title(title_query: str):
    # Simple title match first (more precise)
    sanitized_query = sanitize_for_search(title_query)
    # Exact match on searchable title
    anime = await db.animes.find_one({'title_searchable': sanitized_query})
    if anime: return anime
    # Exact match on alias
    anime = await db.animes.find_one({'aliases_searchable': sanitized_query})
    if anime: return anime
    
    # If no exact match, could try regex (more expensive)
    # For now, let's rely on the /search handler for more complex queries
    return None


async def update_anime_metadata(anime_id: ObjectId, update_data: dict):
    update_data['last_updated_at'] = datetime.utcnow()
    if 'title' in update_data:
        update_data['title_searchable'] = sanitize_for_search(update_data['title'])
    if 'aliases' in update_data:
        update_data['aliases_searchable'] = [sanitize_for_search(a) for a in update_data.get('aliases',[]) if a]

    result = await db.animes.update_one({'_id': anime_id}, {'$set': update_data})
    return result.modified_count > 0

async def delete_anime_series(anime_id: ObjectId):
    # This is a major operation. Consider what to do with associated seasons/episodes.
    # Option 1: Delete them too (cascading delete) - complex to manage
    # Option 2: Mark anime as 'deleted' or disassociate (safer)
    # For now, let's just delete the anime doc. Children will be orphaned.
    # A proper solution would involve transactions or a cleanup script.
    anime_delete_result = await db.animes.delete_one({'_id': anime_id})
    if anime_delete_result.deleted_count > 0:
        # Clean up seasons and episodes for this anime
        await db.seasons.delete_many({'anime_id': anime_id})
        await db.episodes.delete_many({'anime_id': anime_id}) # Add anime_id to episodes for this
        return True
    return False

async def search_animes_db(query: str, page: int = 1, per_page: int = config.ITEMS_PER_PAGE):
    sanitized_query = sanitize_for_search(query)
    regex_query = re.compile(sanitized_query, re.IGNORECASE) # Case-insensitive partial match

    # Search in title_searchable, original_title (if exists), aliases_searchable
    search_filter = {
        '$or': [
            {'title_searchable': {'$regex': regex_query}},
            {'original_title': {'$regex': regex_query}}, # Assuming original_title is also somewhat searchable
            {'aliases_searchable': {'$regex': regex_query}}
        ]
    }
    total_items = await db.animes.count_documents(search_filter)
    results = await db.animes.find(search_filter)\
        .skip((page - 1) * per_page)\
        .limit(per_page)\
        .to_list(length=per_page)
    return results, total_items

async def get_animes_by_filter(filter_dict: dict, page: int = 1, per_page: int = config.ITEMS_PER_PAGE, sort_by: str = 'title', sort_order: int = ASCENDING):
    query = {}
    if filter_dict.get('genre'):
        query['genres'] = filter_dict['genre'] # Assumes single genre search
    if filter_dict.get('status'):
        query['status'] = filter_dict['status']
    if filter_dict.get('year'):
        query['year'] = filter_dict['year']
    if filter_dict.get('letter'): # For A-Z
        query['title_searchable'] = {'$regex': f"^{filter_dict['letter'].lower()}", '$options': 'i'}

    total_items = await db.animes.count_documents(query)
    results = await db.animes.find(query)\
        .sort(sort_by if sort_by == 'title' else 'title_searchable', sort_order)\
        .skip((page - 1) * per_page)\
        .limit(per_page)\
        .to_list(length=per_page)
    return results, total_items

async def get_newly_added_animes_or_episodes(limit: int = 10, type: str = "episodes"):
    if type == "animes":
        return await db.animes.find().sort('added_at', DESCENDING).limit(limit).to_list(length=limit)
    else: # episodes
        # This needs episodes to have an added_at field and anime_id, anime_title
        # For now, this will be tricky. Let's get newly added episodes with some anime info
        pipeline = [
            {'$sort': {'added_at': DESCENDING}},
            {'$limit': limit},
            { # Join with anime to get anime title
                '$lookup': {
                    'from': 'animes',
                    'localField': 'anime_id',
                    'foreignField': '_id',
                    'as': 'anime_info'
                }
            },
            {'$unwind': '$anime_info'} # Assuming one anime per episode
        ]
        return await db.episodes.aggregate(pipeline).to_list(length=limit)


async def get_popular_animes(limit: int = 10):
    # Based on download_count field in animes collection
    return await db.animes.find({'download_count': {'$gt': 0}})\
        .sort('download_count', DESCENDING)\
        .limit(limit)\
        .to_list(length=limit)

async def increment_anime_download_count(anime_id: ObjectId):
    await db.animes.update_one({'_id': anime_id}, {'$inc': {'download_count': 1}})


# - SEASONS -
async def add_season(anime_id: ObjectId, season_number: int, season_title: str, added_by: int):
    season_doc = {
        'anime_id': anime_id,
        'season_number': season_number, # 0 for specials/movies, 1, 2...
        'title': season_title if season_title else f"Season {season_number}",
        'added_by_user_id': added_by,
        'added_at': datetime.utcnow()
    }
    result = await db.seasons.insert_one(season_doc)
    return result.inserted_id

async def get_seasons_for_anime(anime_id: ObjectId):
    if not isinstance(anime_id, ObjectId):
        try: anime_id = ObjectId(anime_id)
        except: return []
    return await db.seasons.find({'anime_id': anime_id}).sort('season_number', ASCENDING).to_list(length=None) # Get all seasons for an anime

async def get_season_by_id(season_id: str | ObjectId):
    if isinstance(season_id, str):
        try: season_id = ObjectId(season_id)
        except: return None
    return await db.seasons.find_one({'_id': season_id})

async def get_season_by_anime_and_number(anime_id: ObjectId, season_number: int):
    return await db.seasons.find_one({'anime_id': anime_id, 'season_number': season_number})

# - EPISODES -
async def add_episode(anime_id: ObjectId, season_id: ObjectId, season_number: int, # Store season_number for quicker display
                      episode_number: int, episode_title: str,
                      file_id: str, file_unique_id: str, file_size: int, # Telegram file info
                      quality: str, audio_type: str, added_by: int):
    episode_doc = {
        'anime_id': anime_id, # Denormalize for easier querying/display
        'season_id': season_id,
        'season_number': season_number, # Denormalize
        'episode_number': episode_number,
        'episode_title': episode_title if episode_title else f"Episode {episode_number}",
        'file_id': file_id,
        'file_unique_id': file_unique_id, # Useful for detecting re-uploads of same file
        'file_size_bytes': file_size,
        'quality': quality, # e.g. "720p", "1080p"
        'audio_type': audio_type, # e.g. "SUB", "DUB"
        'added_by_user_id': added_by,
        'added_at': datetime.utcnow(),
        'download_count': 0
    }
    result = await db.episodes.insert_one(episode_doc)
    return result.inserted_id

async def get_episodes_for_season(season_id: ObjectId, page: int = 1, per_page: int = config.ITEMS_PER_PAGE):
    if not isinstance(season_id, ObjectId):
        try: season_id = ObjectId(season_id)
        except: return [],0
    
    filter_query = {'season_id': season_id}
    total_items = await db.episodes.count_documents(filter_query)
    
    episodes = await db.episodes.find(filter_query)\
        .sort('episode_number', ASCENDING)\
        .skip((page-1)*per_page)\
        .limit(per_page)\
        .to_list(length=per_page)
    return episodes, total_items

async def get_episode_by_id(episode_id: str | ObjectId):
    if isinstance(episode_id, str):
        try: episode_id = ObjectId(episode_id)
        except: return None
    return await db.episodes.find_one({'_id': episode_id})

async def get_episode_versions(anime_id: ObjectId, season_number: int, episode_number: int):
    # Find all files matching this specific episode (potentially multiple qualities/audio)
    return await db.episodes.find({
        'anime_id': anime_id,
        'season_number': season_number,
        'episode_number': episode_number
    }).sort([('quality', DESCENDING), ('audio_type', ASCENDING)]).to_list(length=None) # Get all versions

async def increment_episode_download_count(episode_id: ObjectId):
    await db.episodes.update_one({'_id': episode_id}, {'$inc': {'download_count': 1}})

async def delete_episode_file(episode_id: ObjectId):
    result = await db.episodes.delete_one({'_id': episode_id})
    return result.deleted_count > 0


# --- Premium User Management ---
async def grant_premium(user_id: int, days: int, granted_by_admin_id: int):
    expiry_date = datetime.utcnow() + timedelta(days=days)
    result = await db.users.update_one(
        {'user_id': user_id},
        {'$set': {'is_premium': True, 'premium_expiry_date': expiry_date}}
    )
    if result.matched_count > 0:
        # Log this action
        await db.user_activity.insert_one({
            'user_id': user_id, 'action': 'premium_granted', 'duration_days': days,
            'granted_by': granted_by_admin_id, 'timestamp': datetime.utcnow(),
            'expires_on': expiry_date
        })
        return True, expiry_date
    return False, None

async def revoke_premium(user_id: int, revoked_by_admin_id: int):
    result = await db.users.update_one(
        {'user_id': user_id, 'is_premium': True},
        {'$set': {'is_premium': False, 'premium_expiry_date': datetime.utcnow()}} # Set expiry to now
    )
    if result.modified_count > 0:
        await db.user_activity.insert_one({
            'user_id': user_id, 'action': 'premium_revoked',
            'revoked_by': revoked_by_admin_id, 'timestamp': datetime.utcnow()
        })
        return True
    return False

async def get_premium_users():
    return await db.users.find({'is_premium': True}).to_list(length=None)

async def check_and_revoke_expired_premiums():
    now = datetime.utcnow()
    # Find users whose premium has expired but is_premium is still True
    expired_users = await db.users.find({
        'is_premium': True,
        'premium_expiry_date': {'$lt': now}
    }).to_list(length=None)

    revoked_count = 0
    for user_doc in expired_users:
        revoked = await revoke_premium(user_doc['user_id'], revoked_by_admin_id=0) # 0 for system revoke
        if revoked:
            revoked_count += 1
            LOGGER.info(f"System automatically revoked expired premium for user {user_doc['user_id']}")
    return revoked_count

# --- Anime Requests ---
async def add_anime_request(user_id: int, anime_title: str, requested_language: str):
    request_doc = {
        'user_id': user_id,
        'anime_title_requested': anime_title,
        'language_requested': requested_language,
        'status': 'pending', # pending, investigating, fulfilled, rejected, unavailable
        'requested_at': datetime.utcnow(),
        'resolved_at': None,
        'resolved_by_admin_id': None,
        'admin_notes': None
    }
    result = await db.anime_requests.insert_one(request_doc)
    return result.inserted_id

async def get_anime_request_by_id(request_id: str | ObjectId):
    if isinstance(request_id, str):
        try: request_id = ObjectId(request_id)
        except: return None
    return await db.anime_requests.find_one({'_id': request_id})

async def get_pending_anime_requests(page: int = 1, per_page: int = config.ITEMS_PER_PAGE):
    query = {'status': 'pending'}
    total_items = await db.anime_requests.count_documents(query)
    requests = await db.anime_requests.find(query)\
        .sort('requested_at', ASCENDING)\
        .skip((page - 1) * per_page)\
        .limit(per_page)\
        .to_list(length=per_page)
    return requests, total_items

async def update_anime_request_status(request_id: ObjectId, new_status: str, admin_id: int, notes: str = None):
    update_payload = {
        'status': new_status,
        'resolved_by_admin_id': admin_id,
        'resolved_at': datetime.utcnow()
    }
    if notes:
        update_payload['admin_notes'] = notes
    
    result = await db.anime_requests.update_one(
        {'_id': request_id},
        {'$set': update_payload}
    )
    return result.modified_count > 0

# --- Bot Settings/Configuration ---
async def get_bot_setting(key: str):
    setting = await db.bot_settings.find_one({'key': key})
    return setting['value'] if setting else None

async def set_bot_setting(key: str, value):
    await db.bot_settings.update_one(
        {'key': key},
        {'$set': {'value': value, 'last_updated': datetime.utcnow()}},
        upsert=True
    )

# --- Overall Statistics for /about and /botstats ---
async def get_total_users_count():
    return await db.users.count_documents({})

async def get_premium_users_count():
     return await db.users.count_documents({'is_premium': True})

async def get_anime_count():
    return await db.animes.count_documents({})

async def get_season_count(): # New
    return await db.seasons.count_documents({})

async def get_episode_count_all_versions(): # Total episode entries (sum of all versions)
    return await db.episodes.count_documents({})

async def get_distinct_file_count(): # Unique file_ids, might be less than total episodes if multiple versions use same file_id (unlikely)
    # More accurately, distinct (anime_id, season_number, episode_number) tuples
    # This one is complex, let's count distinct file_unique_id
    # distinct_files = await db.episodes.distinct('file_unique_id')
    # return len(distinct_files)
    # Simpler for now, count distinct anime episodes if possible or just total records as approx.
    # Or count distinct primary episodes (e.g., first added version)
    # For simplicity, we might return the count of episode docs which usually corresponds to versions
    pipeline = [
        {
            '$group': {
                '_id': {
                    'anime_id': '$anime_id',
                    'season_number': '$season_number',
                    'episode_number': '$episode_number'
                }
            }
        },
        {
            '$count': 'distinct_episodes_primary'
        }
    ]
    result = await db.episodes.aggregate(pipeline).to_list(1)
    return result[0]['distinct_episodes_primary'] if result else 0

async def get_total_downloads_recorded():
    # This requires download logging to be more structured.
    # Let's count from user_activity if we add 'download' type there
    return await db.user_activity.count_documents({'action': 'download'})
