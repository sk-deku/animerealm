from pyrogram import __version__ as pyrogram_version
from platform import python_version
import config

# --- GENERAL ---
def get_start_message(user_mention: str, token_balance: int, is_premium: bool):
    premium_status = "👑 Premium User" if is_premium else f"💰 Tokens: {token_balance}"
    return f"""👋 Hi {user_mention}! ({premium_status})

<b>Welcome to AnimeRealmBot by AnimeFireTamil!</b>

🔥 This bot lets you search, download, anime episodes easily.

Use the buttons below to explore commands, support, updates, and more.

Enjoy your anime journey! 🌟"""

ALL_COMMANDS_TEXT = """<b>Here are all the available commands:</b>

<blockquote><u>User Commands:</u>
/start - Show start message and main menu
/browse - Browse anime library
/search <code><query></code> - Search for an anime
/new - See newly added episodes
/popular - See popular anime (based on downloads)
/watchlist - Manage your watchlist
/get_token or /gen_token - Earn download tokens
/premium - Information about premium access
/request <code><anime_name></code> - Request an anime (Premium Only)
/settings - Adjust your preferences
/help - Show this help message
/mystats - Show your usage statistics</blockquote>

<blockquote><u>Admin Commands (Admins Only):</u>
/addanime - Start adding a new anime series
/addseason - Add a new season to an existing anime
/addepisode - Add a new episode to a season
/editanime <code><anime_id></code> - Edit anime metadata
/deleteanime <code><anime_id></code> - Delete an anime series
/editepisode <code><episode_id></code> - Edit episode details
/deleteepisode <code><episode_id></code> - Delete an episode
/grantpremium <code><user_id_or_username> <days></code> - Grant premium access
/revokepremium <code><user_id_or_username></code> - Revoke premium access
/listpremiumusers - List all premium users
/botstats - View bot statistics
/broadcast <code><message></code> - Send message to all users
/setchannel <code><type> <channel_id></code> - Set log channels (request_log, file_log, bot_log)
/settokenconfig <code><tokens> <expiry_hr> <daily_limit></code> - Configure token system
/managerequests - View and manage anime requests
</blockquote>"""

def get_about_text(anime_count, episode_count, file_count_distinct, db_stats_str, total_users, premium_users):
    return f"""<blockquote>
❍ Bᴏᴛ Nᴀᴍᴇ :- Aɴɪᴍᴇ ʀᴇᴀʟᴍ Bᴏᴛ (AnimeFireTamil)
❍ Cʀᴇᴀᴛᴇʀ :- {config.CREATOR_NAME} (<a href='https://t.me/{config.CREATOR_USERNAME}'>@{config.CREATOR_USERNAME}</a>)
❍ Lᴀɴɢᴜᴀɢᴇ :- Pʏᴛʜᴏɴ ({python_version()})
❍ Lɪʙʀᴀʀʏ :- Pʏʀᴏɢʀᴀᴍ ({pyrogram_version})
❍ Dᴀᴛᴀʙᴀꜱᴇ :- MᴏɴɢᴏDB
❍ Hᴏꜱᴛᴇᴅ Oɴ :- Kᴏʏᴇʙ (Example)

📊 Sᴛᴀᴛs:
Tᴏᴛᴀʟ Aɴɪᴍᴇs Aᴅᴅᴇᴅ :- {anime_count}
Tᴏᴛᴀʟ Eᴘɪsᴏᴅᴇs Aᴅᴅᴇᴅ :- {episode_count} (sum of all versions)
Tᴏᴛᴀʟ Dɪsᴛɪɴᴄᴛ Fɪʟᴇs Rᴇᴄᴏʀᴅᴇᴅ :- {file_count_distinct} (unique Telegram file_ids)
Dᴀᴛᴀʙᴀsᴇ Usᴀɢᴇ :- {db_stats_str}
Tᴏᴛᴀʟ Usᴇʀs :- {total_users}
Pʀᴇᴍɪᴜᴍ Usᴇʀs :- {premium_users}

➻ Cʟɪᴄᴋ ᴏɴ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ɢɪᴠᴇɴ ʙᴇʟᴏᴡ ғᴏʀ ɢᴇᴛᴛɪɴɢ ʙᴀsɪᴄ ʜᴇʟᴩ ᴀɴᴅ ɪɴғᴏ ᴀʙᴏᴜᴛ ᴍᴇ.
</blockquote>"""

MY_STATS_TEXT = """<b>📊 Your Statistics:</b>
<blockquote>
Download Tokens: <b>{tokens}</b>
Premium Status: <b>{is_premium}</b>
{premium_details}
Watchlist Count: <b>{watchlist_count}</b>
Requests Made: <b>{requests_made}</b>
Episodes Downloaded Today: <b>{downloads_today}/{download_limit}</b> (Free users)
Joined: {join_date}
</blockquote>"""

# --- TOKEN SYSTEM ---
GEN_TOKEN_MESSAGE = "🔗 Click the button below to generate a link. Visit the link to earn <b>{tokens_to_earn}</b> Download Tokens.\n\nℹ️ <i>The link will expire in {expiry_hours} hour(s) or after one use. You can earn tokens {daily_limit} times per day.</i>"
TOKEN_LINK_TEXT = "✨ Generate Link & Earn Tokens ✨"
TOKEN_HOW_TO_BUTTON_TEXT = "🤔 How to use?"
TOKEN_HOW_TO_URL = "https://telegra.ph/How-to-Earn-Tokens-01-01" # Create a tutorial page
TOKEN_DAILY_LIMIT_REACHED = "⚠️ You have reached your daily limit for earning tokens. Please try again tomorrow."
TOKEN_SUCCESS_MESSAGE = "✅ Success! You've earned <b>{earned_tokens}</b> Download Tokens.\nYour new balance: <b>{new_balance}</b> tokens."
TOKEN_INVALID_MESSAGE = "⚠️ Sorry, this token is invalid, already used, or has expired. Please try /gen_token again."
TOKEN_NEEDED_FOR_DOWNLOAD = "⚠️ You need <b>{tokens_needed}</b> Download Token(s) to download this.\nYou have <b>{user_tokens}</b>. Earn more with /gen_token or get unlimited access with /premium."
DOWNLOAD_CONFIRMATION = "This will use <b>1</b> Download Token. You have <b>{user_tokens}</b> remaining. Proceed?"
DOWNLOAD_DAILY_LIMIT_REACHED = "⚠️ Free users have a daily download limit of {limit} episodes. You have reached this limit for today. Please try again tomorrow or consider /premium for unlimited downloads."

# --- ANIME DETAILS & DOWNLOAD ---
ANIME_DETAIL_TEXT = """<b>{title}</b> ({year}) - {status}
<i>{original_title}</i>

<b>Genres:</b> {genres}
<b>Synopsis:</b>
<blockquote>{synopsis}</blockquote>

<b>Seasons Available:</b>"""
NO_SEASONS_TEXT = "No seasons (and thus no episodes) have been added for this anime yet."
SEASON_EPISODES_TEXT = "<b>{anime_title} - Season {season_number}</b>\nSelect an episode to download:"
NO_EPISODES_IN_SEASON_TEXT = "No episodes found for this season yet."
EPISODE_VERSIONS_TEXT = "<b>{anime_title} S{s_num}E{e_num}: {ep_title}</b>\nSelect version to download:"
DOWNLOAD_STARTED = "✅ Download initiated for: <b>{file_name}</b>\nIt will be sent to you shortly."
FILE_NOT_FOUND_ON_TELEGRAM = "❌ Critical Error: The file for this episode could not be found on Telegram servers. It might have been deleted. Please report this to an admin."

# --- SEARCH & BROWSE ---
SEARCH_PROMPT = "🔍 Please enter the name of the anime you want to search for:"
SEARCH_NO_RESULTS = "🙁 No anime found matching your query: ` {query} `"
SEARCH_RESULTS_TEXT = "🔍 Search results for ` {query} `:"
BROWSE_MAIN_TEXT = "📚 Browse Anime Library by:"
BROWSE_GENRE_TEXT = "Select a genre to browse:"
BROWSE_AZ_TEXT = "Select a letter to browse anime starting with it:"
BROWSE_STATUS_TEXT = "Select anime status to browse:"
BROWSE_YEAR_TEXT = "Enter a year (e.g., 2023) to browse anime from that year, or select a season:"
BROWSE_NO_ANIME_FOR_FILTER = "🙁 No anime found matching this filter."

# --- WATCHLIST ---
WATCHLIST_EMPTY = "📌 Your watchlist is empty. Browse or search for anime to add them!"
WATCHLIST_TEXT = "📌 Your Watchlist:"
ADDED_TO_WATCHLIST = "✅ <b>{anime_title}</b> added to your watchlist!"
REMOVED_FROM_WATCHLIST = "🗑️ <b>{anime_title}</b> removed from your watchlist."
ALREADY_IN_WATCHLIST = "ℹ️ <b>{anime_title}</b> is already in your watchlist."
NOT_IN_WATCHLIST = "ℹ️ <b>{anime_title}</b> was not found in your watchlist."
NEW_EPISODE_NOTIFICATION = """🔔 New Episode Alert!
<b>{anime_title}</b> - Season {season_number}, Episode {episode_number}: {episode_title} is now available!
/viewanime_{anime_id}"""


# --- PREMIUM & REQUESTS ---
PREMIUM_INFO_TEXT = """👑 **Unlock Premium Access!**

Enjoy the ultimate anime experience with these benefits:
✅ Access to ALL anime, including exclusives.
✅ HD/FHD quality downloads (1080p+ where available).
✅ No daily download limits.
✅ No download tokens needed.
✅ Ad-free experience.
✅ Request unavailable anime directly.
✅ Priority support.

**Subscription Plans:**
- Monthly: $X.XX
- Quarterly: $Y.YY (Save Z%)
- Annually: $A.AA (Save B%)

Click the button below to learn how to subscribe!
(Payments are currently handled manually or via an external link. Bot will guide you.)""" # Update with actual price/link
REQUEST_PROMPT_TITLE = "🙏 What is the <b>exact title</b> of the anime you want to request?"
REQUEST_PROMPT_LANGUAGE = "🗣️ Preferred language for <b>{anime_title}</b>? (e.g., SUB English, DUB Hindi, Any)"
REQUEST_SUBMITTED = "✅ Your request for <b>{anime_title}</b> ({language}) has been submitted. We'll notify you of updates. Request ID: `{request_id}`"
REQUEST_PREMIUM_ONLY = "⚠️ Sorry, the anime request feature is available for Premium users only. Check /premium for more info."
REQUEST_NOTIFICATION_ADDED = """🎉 Good News!
Your requested anime <b>{anime_title}</b> ({language}) has been added!
You can find it by searching or browsing.
Admin notes: {notes}"""
REQUEST_NOTIFICATION_REJECTED = """🙁 Update on your request for <b>{anime_title}</b> ({language}):
Unfortunately, we couldn't fulfill your request at this time.
Reason: {reason}
Admin notes: {notes}"""
REQUEST_MANAGEMENT_TEXT = "Anime Requests Management (Pending First):"


# --- SETTINGS ---
SETTINGS_TEXT = "⚙️ Your Settings:"
SETTING_UPDATED = "✅ Setting updated!"
PREF_QUALITY_TEXT = "Preferred Download Quality (Bot will try to offer this first if available):"
PREF_AUDIO_TEXT = "Preferred Audio Type (SUB/DUB):"
NOTIFICATIONS_TEXT = "Watchlist Notifications for New Episodes:"


# --- ADMIN ---
ADMIN_PANEL_TEXT = "🛠️ Admin Panel 🛠️"
# Add Anime
ADD_ANIME_TITLE_PROMPT = "Enter the <b>Main Title</b> of the anime (e.g., Attack on Titan):"
ADD_ANIME_ORIGINAL_TITLE_PROMPT = "Enter the <b>Original/Japanese Title</b> (optional, press /skip if none/same):"
ADD_ANIME_SYNOPSIS_PROMPT = "Enter a brief <b>Synopsis</b> for {title}:"
ADD_ANIME_YEAR_PROMPT = "Enter the <b>Release Year</b> for {title} (e.g., 2013):"
ADD_ANIME_STATUS_PROMPT = "Select the <b>Status</b> for {title}:" # Uses keyboard
ADD_ANIME_GENRES_PROMPT = "Select <b>Genres</b> for {title} (multi-select, click 'Done Selecting' when finished):" # Uses keyboard
ADD_ANIME_POSTER_PROMPT = "Send the <b>Poster Image URL</b> for {title} (or upload an image, or /skip for no poster):"
ADD_ANIME_ALIASES_PROMPT = "Enter any <b>Aliases</b> (alternative names, comma-separated) for {title} (optional, /skip):"
ADD_ANIME_CONFIRM = "<b>Review Anime Details:</b>\n\nTitle: {title}\nOriginal Title: {original_title}\nSynopsis: {synopsis}\nYear: {year}\nStatus: {status}\nGenres: {genres}\nPoster: {poster_info}\nAliases: {aliases}\n\nConfirm to add to database?"
ADD_ANIME_SUCCESS = "✅ Anime '<b>{title}</b>' added successfully with ID: `{anime_id}`. You can now /addseason for it."
ADD_ANIME_CANCELLED = "❌ Anime addition cancelled."
# Add Season
ADD_SEASON_PROMPT_ANIME = "Enter the <b>Anime ID</b> or <b>Anime Title</b> to add a season to:"
ADD_SEASON_PROMPT_NUMBER = "Enter the <b>Season Number</b> for {anime_title} (e.g., 1, 2, 0 for Specials/OVAs):"
ADD_SEASON_PROMPT_TITLE = "Enter an optional <b>Season Title</b> (e.g., The Final Season Part 2, or /skip):"
ADD_SEASON_CONFIRM = "<b>Review Season Details:</b>\n\nAnime: {anime_title} ({anime_id})\nSeason Number: {season_number}\nSeason Title: {season_title}\n\nConfirm to add this season?"
ADD_SEASON_SUCCESS = "✅ Season {season_number} ('{season_title}') added successfully for {anime_title}. You can now /addepisode."
# Add Episode
ADD_EPISODE_PROMPT_ANIME = "Enter the <b>Anime ID</b> or <b>Anime Title</b> for the episode:"
ADD_EPISODE_PROMPT_SEASON = "Enter the <b>Season Number</b> for {anime_title}:"
ADD_EPISODE_PROMPT_EPISODE_NUM = "Enter the <b>Episode Number</b> for Season {season_num} of {anime_title}:"
ADD_EPISODE_PROMPT_EPISODE_TITLE = "Enter the <b>Episode Title</b> for S{s_num}E{ep_num} (or /skip):"
ADD_EPISODE_PROMPT_FILE = "Now, send the <b>video file</b> for S{s_num}E{ep_num} - {ep_title} of {anime_title}.\n<i>Or forward a message containing the video.</i>"
ADD_EPISODE_PROMPT_QUALITY = "Enter the <b>Quality</b> of this file (e.g., 720p, 1080p, FHD, 480p):"
ADD_EPISODE_PROMPT_AUDIO_TYPE = "Select the <b>Audio Type</b> for this file:" # Uses keyboard
ADD_EPISODE_CONFIRM = "<b>Review Episode Details:</b>\nAnime: {anime_title} (S{s_num})\nEpisode: {ep_num} - {ep_title}\nFile ID: {file_id} (Size: {file_size_mb:.2f} MB)\nQuality: {quality}\nAudio: {audio_type}\n\nConfirm to add this episode?"
ADD_EPISODE_SUCCESS = "✅ Episode S{s_num}E{ep_num} ('{ep_title}') added successfully for {anime_title}!"
ADD_EPISODE_ANOTHER = "Do you want to add another version (e.g. different quality/audio) for THIS SAME episode, or add the NEXT episode, or finish?"

# Generic Admin
OPERATION_SUCCESSFUL = "✅ Operation successful."
OPERATION_FAILED = "❌ Operation failed. Check logs or input."
ITEM_NOT_FOUND = "❌ Item not found with ID/Name: {identifier}"
INVALID_INPUT = "❌ Invalid input: {reason}"
CONFIRMATION_PROMPT = "Are you sure you want to proceed with this action?"
PREMIUM_GRANTED = "👑 Premium access granted to {user_mention} for {days} days. Expires: {expiry_date}."
PREMIUM_REVOKED = "🗑️ Premium access revoked for {user_mention}."
USER_NOT_FOUND = "❌ User {identifier} not found in the bot's database."
CONFIG_UPDATED = "⚙️ Configuration updated successfully."
BROADCAST_STARTED = "📣 Broadcast started... It may take some time to complete."
BROADCAST_SUMMARY = "📣 Broadcast finished. Sent to {sent_count} users. Failed for {failed_count} users."

# --- ERRORS & PLACEHOLDERS ---
FEATURE_NOT_IMPLEMENTED = "🚧 This feature ({feature_name}) is still under construction. Coming soon!"
SOMETHING_WENT_WRONG = "🤖 Oops! Something went wrong on my end. Please try again later. If the problem persists, contact support."
