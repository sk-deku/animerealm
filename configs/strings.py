# configs/strings.py

# --- Emojis (reuse for consistency) ---
EMOJI_WELCOME = "🎉"
EMOJI_SEARCH = "🔍"
EMOJI_BROWSE = "📚"
EMOJI_POPULAR = "🌟"
EMOJI_LATEST = "🆕"
EMOJI_WATCHLIST = "💖"
EMOJI_PROFILE = "👤"
EMOJI_PREMIUM = "💎"
EMOJI_TOKENS = "🪙"
EMOJI_HELP = "❓"
EMOJI_ERROR = "⚠️"
EMOJI_SUCCESS = "✅"
EMOJI_INFO = "ℹ️"
EMOJI_BACK = "⬅️"
EMOJI_NEXT = "➡️"
EMOJI_CANCEL = "❌"
EMOJI_SETTINGS = "⚙️"
EMOJI_ADMIN = "👑"
EMOJI_DOWNLOAD = "💾"
EMOJI_LOADING = "⏳"
EMOJI_TV = "📺"
EMOJI_MOVIE = "🎬"
EMOJI_OVA = "📼"
EMOJI_SPECIAL = "⭐"
EMOJI_REQUEST = "➕"
EMOJI_NOTIFICATION = "🔔"
EMOJI_SAVE = "💰"
EMOJI_UPLOAD = "📤"
EMOJI_EDIT = "✏️"
EMOJI_DELETE = "🗑️"
EMOJI_LIST = "📋"


# --- General & Core Commands ---
WELCOME_MESSAGE = f"""
{EMOJI_WELCOME} <b>Welcome to Anime Realm Bot, {{user_first_name}}!</b> {EMOJI_WELCOME}

<blockquote>Dive into a world of anime at your fingertips! Search, browse, download, and manage your watchlist with ease.</blockquote>

Use the buttons below or commands to navigate:
/search - Find your favorite anime
/browse - Explore by genre or status
/popular - See what's trending
/latest - Check out newly added episodes
/my_watchlist - View your saved anime
/profile - Check your tokens and premium status
/get_tokens - earn free tokens
/premium - Upgrade for exclusive benefits!
"""

HELP_MESSAGE_GENERAL = f"""
{EMOJI_HELP} <b>Anime Realm Bot Help</b> {EMOJI_HELP}

Here are some commands you can use:
<code>/start</code> - Shows the welcome message & main menu.
<code>/search [anime_name]</code> - Searches for an anime.
<code>/browse</code> - Allows browsing anime by different criteria.
<code>/popular</code> - Shows the most downloaded anime.
<code>/latest</code> - Shows the most recently added episodes.
<code>/my_watchlist</code> - Manages your personal watchlist.
<code>/profile</code> - Shows your current token balance and premium status.
<code>/get_tokens</code> - Earn tokens via shortened links.
<code>/premium</code> - Displays premium membership options.
<code>/cancel</code> - Cancels any ongoing operation (like adding content as an admin).

<blockquote>If you need more specific help during an operation, look for context-sensitive help messages or buttons!</blockquote>
"""

HELP_MESSAGE_ADMIN = f"""
{EMOJI_ADMIN} <b>Admin Help Panel</b> {EMOJI_ADMIN}

Available Admin Commands:
<code>/manage_content</code> - Add, edit, or delete anime and episodes.
<code>/grant_premium [user_id] [days]</code> - Grant premium status to a user.
<code>/revoke_premium [user_id]</code> - Revoke premium status.
<code>/add_tokens [user_id] [amount]</code> - Add tokens to a user.
<code>/remove_tokens [user_id] [amount]</code> - Remove tokens from a user.
<code>/broadcast [message]</code> - Send a message to all bot users.
<code>/user_info [user_id]</code> - Get information about a specific user.
<code>/bot_stats</code> - View bot usage statistics.
<code>/view_requests</code> - (Managed via request channel now)
<code>/delete_all_data_REALLY_SURE [CONFIRMATION_PHRASE]</code> - <b>DANGEROUS!</b> Wipes specific bot data. Use with extreme caution. Separate commands for users/anime preferred.

Use <code>/cancel</code> to stop any ongoing admin operation.
"""

OPERATION_CANCELLED = f"{EMOJI_CANCEL} Current operation has been cancelled."
OPERATION_COMPLETED = f"{EMOJI_SUCCESS} Operation completed successfully!"
GENERAL_ERROR = f"{EMOJI_ERROR} Oops! Something went wrong. Please try again or contact support if the issue persists."
INVALID_INPUT = f"{EMOJI_ERROR} Invalid input. Please check your command or message and try again."
COMMAND_ONLY_FOR_ADMINS = f"{EMOJI_ERROR} This command is for {EMOJI_ADMIN} Admins only!"
FEATURE_UNDER_CONSTRUCTION = f"{EMOJI_LOADING} This feature is still under construction. Stay tuned!"

# --- Main Menu Buttons ---
BTN_SEARCH = f"{EMOJI_SEARCH} <b>Search Anime</b>"
BTN_BROWSE = f"{EMOJI_BROWSE} <b>Browse Library</b>"
BTN_POPULAR = f"{EMOJI_POPULAR} <b>Popular Now</b>"
BTN_LATEST = f"{EMOJI_LATEST} <b>Latest Episodes</b>"
BTN_MY_WATCHLIST = f"{EMOJI_WATCHLIST} <b>My Watchlist</b>"
BTN_PROFILE = f"{EMOJI_PROFILE} <b>My Profile</b>"
BTN_GET_TOKENS = f"{EMOJI_TOKENS} <b>Get Tokens</b>"
BTN_PREMIUM = f"{EMOJI_PREMIUM} <b>Go Premium!</b>"
BTN_HELP = f"{EMOJI_HELP} <b>Help</b>"
BTN_BACK_TO_MAIN_MENU = f"{EMOJI_BACK} <b>Main Menu</b>"

# --- Profile / Dashboard ---
PROFILE_INFO = f"""
{EMOJI_PROFILE} <b>Your Profile Dashboard</b> {EMOJI_PROFILE}

👤 <b>User:</b> {{user_first_name}} (<code>{{user_id}}</code>)
{EMOJI_TOKENS} <b>Tokens:</b> <code>{{tokens}}</code>

{EMOJI_PREMIUM} <b>Premium Status:</b>
<blockquote>{{premium_status_message}}</blockquote>

{EMOJI_WATCHLIST} <b>Watchlist:</b> You have <code>{{watchlist_count}}</code> anime(s) saved.
<a href="https://t.me/{BOT_USERNAME}?start=view_watchlist">Tap here to view watchlist</a>

<i>Use /get_tokens or /premium to enhance your experience!</i>
""" # Assuming BOT_USERNAME is available here from settings

PREMIUM_ACTIVE_MESSAGE = f"<b>Active</b> {EMOJI_SUCCESS} (Expires on: <i>{{expiry_date}}</i>)"
PREMIUM_INACTIVE_MESSAGE = f"<b>Inactive</b> {EMOJI_ERROR}"


# --- Token System ---
GET_TOKENS_INFO = f"""
{EMOJI_TOKENS} <b>How to Earn Tokens</b> {EMOJI_TOKENS}

You can earn tokens by referring new users to Anime Realm Bot!
<blockquote>1. Use the <code>/gen_token_link</code> command.
2. The bot will give you a unique referral link.
3. Share this link with your friends!
4. When a new user starts the bot using YOUR link, you'll receive <b>{{tokens_per_referral}}</b> tokens! The new user also gets <b>{{tokens_for_new_user_referral}}</b> tokens to start!</blockquote>
<b>Daily Limit:</b> You can earn up to <b>{{daily_token_limit}}</b> tokens per day via referrals.

<i>Tokens allow you to download anime episodes and make requests (if you're not premium).</i>
"""

TOKEN_LINK_GENERATED_MESSAGE = f"""
✨ <b>Your Referral Link is Ready!</b> ✨

Share this link to earn <code>{{tokens_to_award}}</code> {EMOJI_TOKENS} when someone new uses it:
<i>(This referral opportunity is active for the next {{link_active_hours}} hours. The link itself, once shortened, might have its own lifespan from the shortener service.)</i>
""" # Button with shortener link will be attached.

BTN_HOW_TO_EARN_TUTORIAL = f"💡 <b>Full Tutorial</b>" # Links to settings.HOW_TO_EARN_TOKENS_TUTORIAL_LINK
BTN_SHARE_THIS_LINK = f"🔗 <b>Share This Link!</b>"

TOKEN_EARNED_NOTIFICATION_REFERRER = f"{EMOJI_SUCCESS} You earned <b>{{tokens_awarded}}</b> {EMOJI_TOKENS}! User <i>{{new_user_name}}</i> joined using your referral link."
TOKEN_AWARDED_NEW_USER_REFERRAL = f"{EMOJI_WELCOME} Welcome! You've received <b>{{tokens_awarded}}</b> {EMOJI_TOKENS} for joining via a referral!"
TOKEN_AWARDED_NEW_USER_DIRECT = f"{EMOJI_WELCOME} Welcome! You've received <b>{{tokens_awarded}}</b> {EMOJI_TOKENS} to get you started!"
TOKENS_DEDUCTED = f"{EMOJI_INFO} <b>{{tokens_cost}}</b> {EMOJI_TOKENS} have been deducted for this action."
NOT_ENOUGH_TOKENS = f"{EMOJI_ERROR} <b>Not Enough Tokens!</b> You need <code>{{required_tokens}}</code> {EMOJI_TOKENS}, but you only have <code>{{current_tokens}}</code> {EMOJI_TOKENS}."
DAILY_TOKEN_LIMIT_REACHED = f"{EMOJI_ERROR} You've reached your daily token earning limit of <code>{{limit}}</code> {EMOJI_TOKENS} today. Try again tomorrow!"

# --- Premium Membership ---
PREMIUM_INFO_HEADER = f"{EMOJI_PREMIUM} <b>Unlock Anime Realm Premium!</b> {EMOJI_PREMIUM}\n\n"
PREMIUM_BENEFITS = """
Enjoy exclusive benefits with Premium:
✅ <b>Unlimited Downloads:</b> No token costs!
✅ <b>HD/FHD Quality:</b> Access 1080p, BD, and 4K quality when available.
✅ <b>Free Anime Requests:</b> Request any anime without token cost.
✅ <b>Larger Watchlist:</b> Save up to {{max_watchlist_premium}} anime.
✅ <b>Priority Support</b> (if offered)
✅ <b>Ad-Free Experience</b> (if ads are implemented for free users)
"""
PREMIUM_PLAN_ENTRY = """
{plan_icon} <b>{display_name}</b> - ₹{price_inr} for {duration_days} days {savings_text}
""" # Icons can be set dynamically
PREMIUM_CONTACT_INSTRUCTION = f"\n💬 To purchase, please contact our admin: @{{contact_admin_username}}"

# --- Anime Search & Browsing ---
SEARCH_PROMPT = f"{EMOJI_SEARCH} Please enter the <b>English name</b> of the anime you want to search for:"
SEARCH_NO_RESULTS = f'{EMOJI_ERROR} No anime found matching <code>{{query}}</code>. Try a different name or browse our library.'
SEARCH_RESULTS_HEADER = f'{EMOJI_SEARCH} Search Results for <code>{{query}}</code> (Page {{current_page}}/{{total_pages}}):\n\n'
SELECT_ANIME_PROMPT = "👇 Select an anime from the list to view details."

BROWSE_MAIN_PROMPT = f"{EMOJI_BROWSE} How would you like to browse our anime library?"
BTN_BROWSE_BY_GENRE = f"{EMOJI_LIST} <b>By Genre</b>"
BTN_BROWSE_BY_STATUS = f"{EMOJI_TV} <b>By Status (Ongoing/Completed)</b>"
# BTN_BROWSE_BY_YEAR = "📅 By Release Year" (If implemented)

BROWSE_SELECT_GENRE = f"{EMOJI_LIST} Select a genre to explore (Page {{current_page}}/{{total_pages}}):"
BROWSE_SELECT_STATUS = f"{EMOJI_TV} Select an anime status (Page {{current_page}}/{{total_pages}}):"
BROWSE_RESULTS_HEADER = f"{EMOJI_BROWSE} Anime in <i>{{category_name}}</i> (Page {{current_page}}/{{total_pages}}):\n\n" # category_name is Genre/Status

LATEST_UPDATES_HEADER = f"{EMOJI_LATEST} Latest Episode Updates (Page {{current_page}}/{{total_pages}}):\n"
POPULAR_ANIME_HEADER = f"{EMOJI_POPULAR} Most Popular Anime (Page {{current_page}}/{{total_pages}}):\n"

# --- Anime Details & Episodes ---
ANIME_DETAILS_MESSAGE = f"""
🎬 <b>{{title_english}}</b>
🗓️ Year: {{release_year}} | {EMOJI_TV} Status: {{status}}

📚 <b>Genres:</b> <i>{{genres_list}}</i>

📝 <b>Synopsis:</b>
<blockquote>{{synopsis}}</blockquote>

Choose an option:
"""
# Poster will be sent with this message as caption

BTN_VIEW_SEASONS = "Sᴇᴀsᴏɴs & Eᴘɪsᴏᴅᴇs" # Using special fonts to make it stand out
BTN_ADD_TO_WATCHLIST = f"{EMOJI_WATCHLIST} Add to Watchlist"
BTN_REMOVE_FROM_WATCHLIST = f"{EMOJI_CANCEL} Remove from Watchlist"

SEASONS_LIST_PROMPT = f"📺 <b>{{anime_title}}</b> - Select a Season (Page {{current_page}}/{{total_pages}}):"
BTN_SEASON_PREFIX = "S" # e.g., S1, S2

EPISODES_LIST_PROMPT = f"🎞️ <b>{{anime_title}} - Season {{season_num}}</b> - Select an Episode (Page {{current_page}}/{{total_pages}}):"
EPISODE_ENTRY_FORMAT = "EP {{ep_num}}" # Optional: "EP {{ep_num}} - {{ep_title}}" if titles are stored
EPISODE_AIR_DATE_NOTICE = f" (Airs on: <i>{{air_date}}</i> {EMOJI_LOADING})"
EPISODE_NOT_YET_ANNOUNCED = f" (Release date TBA {EMOJI_LOADING})"

VERSIONS_LIST_PROMPT = f"""
💾 <b>{{anime_title}} - S{{season_num}} EP{{episode_num}}</b>

Available versions (tap to download):
<blockquote><b>Note:</b> {{premium_resolution_note}}</blockquote>
"""
VERSION_BUTTON_FORMAT = "{{resolution}} {{audio_lang}} {{sub_lang}} ({{file_size_mb}} MB)" # Resolution, Audio, Sub, Size
PREMIUM_RESOLUTION_NOTE_FREE_USER = f"Users on free tier can only download up to 720p. {EMOJI_PREMIUM} Go Premium for 1080p+!"
PREMIUM_RESOLUTION_NOTE_PREMIUM_USER = f"Enjoy your premium access to all qualities! {EMOJI_PREMIUM}"

FILE_TRANSFER_START = f"{EMOJI_LOADING} Preparing your download for <b>{{anime_title}} S{{s_num}}E{{ep_num}}</b>..."
FILE_TRANSFER_ERROR = f"{EMOJI_ERROR} Could not send the file. It might be too large or an error occurred. Please try again or contact an admin."
FILE_DETAILS_CAPTION = f"""
🎬 <b>{{title_english}}</b>
S{{season_num}} EP{{episode_num}}
⚙️ Resolution: {{resolution}}
🔊 Audio: {{audio_lang}}
字幕 Subtitles: {{sub_lang}}
📦 Size: {{file_size_mb}} MB

<i>Downloaded from @{BOT_USERNAME}</i>
"""

# --- Watchlist ---
WATCHLIST_EMPTY = f"{EMOJI_WATCHLIST} Your watchlist is currently empty. Start by searching or browsing anime!"
WATCHLIST_HEADER = f"{EMOJI_WATCHLIST} <b>Your Watchlist</b> (Page {{current_page}}/{{total_pages}}):\n\n"
ADDED_TO_WATCHLIST = f"{EMOJI_SUCCESS} <b>{{anime_title}}</b> has been added to your watchlist!"
REMOVED_FROM_WATCHLIST = f"{EMOJI_CANCEL} <b>{{anime_title}}</b> has been removed from your watchlist."
WATCHLIST_FULL_FREE = f"{EMOJI_ERROR} Your watchlist is full (Max: {{limit}} items for free users). {EMOJI_PREMIUM} Upgrade to Premium for more space!"
WATCHLIST_FULL_PREMIUM = f"{EMOJI_ERROR} Your watchlist is full (Max: {{limit}} items for premium users)."
ALREADY_IN_WATCHLIST = f"{EMOJI_INFO} <b>{{anime_title}}</b> is already in your watchlist."
NOT_IN_WATCHLIST = f"{EMOJI_ERROR} <b>{{anime_title}}</b> was not found in your watchlist."
NOTIFICATION_NEW_EPISODE_WATCHLIST = f"""
{EMOJI_NOTIFICATION} <b>New Episode Alert!</b> {EMOJI_NOTIFICATION}
A new episode is available for <b>{{anime_title}}</b> (S{{season_num}} EP{{episode_num}}), which is on your watchlist!

Tap here to view: /view_{{anime_id}}_s{{season_num}}_e{{episode_num}}
""" # This would be a deep link command if implemented

# --- Anime Requests ---
REQUEST_PROMPT_PREMIUM = f"{EMOJI_REQUEST} Premium User: What anime (English title) would you like to request?"
REQUEST_PROMPT_FREE_CONFIRM = f"Requesting '<code>{{anime_title}}</code>' will cost <b>{{token_cost}}</b> {EMOJI_TOKENS}. Do you want to proceed?"
BTN_CONFIRM_REQUEST = f"{EMOJI_SUCCESS} Yes, Request it!"
BTN_CANCEL_REQUEST = f"{EMOJI_CANCEL} No, Cancel"

REQUEST_SENT_SUCCESS = f"{EMOJI_SUCCESS} Your request for '<b>{{anime_title}}</b>' has been submitted to the admins!"
REQUEST_SENT_TO_ADMIN_CHANNEL = f"""
🆕 <b>Anime Request Received</b> 🆕

🎬 <b>Title:</b> <code>{{anime_title}}</code>
👤 <b>Requested by:</b> <a href="tg://user?id={{user_id}}">{{user_first_name}}</a> (<code>{{user_id}}</code>)
{EMOJI_PREMIUM} <b>Premium User:</b> {{is_premium_status}}

👇 <b>Admin Actions:</b>
""" # Inline keyboard with admin reply options will be attached by the bot

REQUEST_ADMIN_REPLY_FULFILLED = f"{EMOJI_SUCCESS} Request fulfilled by {{admin_name}}."
REQUEST_ADMIN_REPLY_UNAVAILABLE = f"{EMOJI_ERROR} Marked as 'Unavailable' by {{admin_name}}."
REQUEST_ADMIN_REPLY_NOT_RELEASED = f"{EMOJI_LOADING} Marked as 'Not Yet Released' by {{admin_name}}."
REQUEST_ADMIN_REPLY_IGNORED = f"🗑️ Request ignored by {{admin_name}}."

# User Notifications from Admin Request Actions
USER_NOTIF_REQUEST_FULFILLED = f"{EMOJI_SUCCESS} Good news! Your request for '<b>{{anime_title}}</b>' has been fulfilled and is now available. Use /search!"
USER_NOTIF_REQUEST_UNAVAILABLE = f"{EMOJI_ERROR} We're sorry, but your request for '<b>{{anime_title}}</b>' cannot be fulfilled at this time."
USER_NOTIF_REQUEST_NOT_RELEASED = f"{EMOJI_LOADING} Your request for '<b>{{anime_title}}</b>' is for an anime not yet released. We'll keep an eye out!"

# --- Admin Content Management ---
ADMIN_CONTENT_MAIN_MENU = f"{EMOJI_ADMIN} <b>Content Management Panel</b> {EMOJI_ADMIN}\nChoose an action:"
BTN_CM_ADD_ANIME = f"{EMOJI_UPLOAD} <b>Add New Anime</b>"
BTN_CM_MODIFY_ANIME = f"{EMOJI_EDIT} <b>Modify Existing Anime</b>"
BTN_CM_DELETE_ANIME = f"{EMOJI_DELETE} <b>Delete Anime (Dangerous)</b>"

CM_PROMPT_ANIME_TITLE_ENG = f"{EMOJI_EDIT} Enter the <b>English Title</b> for the anime:"
CM_PROMPT_POSTER = f"{EMOJI_UPLOAD} Send the <b>Poster Image</b> for the anime (or type 'skip' or send URL):"
CM_PROMPT_SYNOPSIS = f"{EMOJI_EDIT} Enter the <b>Synopsis</b> for the anime (or 'skip'):"
CM_PROMPT_SELECT_GENRES = f"{EMOJI_LIST} Select <b>Genres</b> for '{{anime_title}}' (tap to toggle, then 'Done'):"
CM_PROMPT_SELECT_STATUS = f"{EMOJI_TV} Select the <b>Status</b> for '{{anime_title}}':"
CM_PROMPT_RELEASE_YEAR = f"{EMOJI_EDIT} Enter the <b>Release Year</b> (YYYY) for '{{anime_title}}':"
CM_PROMPT_NUM_SEASONS = f"{EMOJI_EDIT} How many <b>Seasons</b> does this anime entry have?"

CM_ANIME_ADDED_SUCCESS = f"{EMOJI_SUCCESS} Base info for '<b>{{anime_title}}</b>' added successfully!"
CM_ANIME_UPDATED_SUCCESS = f"{EMOJI_SUCCESS} '<b>{{anime_title}}</b>' details updated!"
CM_NOW_MANAGE_SEASONS_EPISODES = "Now, let's manage seasons and episodes for '<b>{{anime_title}}</b>'."
BTN_CM_MANAGE_SEASONS_EPISODES = "🎬 Manage Seasons/Episodes"

CM_SELECT_ANIME_TO_MODIFY = f"{EMOJI_SEARCH} Enter the English title of the anime you want to modify:"
CM_NO_ANIME_FOUND_FOR_MODIFY = f"{EMOJI_ERROR} No anime found matching '<code>{{query}}</code>' to modify."
CM_SELECT_ACTION_FOR_ANIME = "Selected: <b>{{anime_title}}</b>. What do you want to modify?"
BTN_CM_EDIT_DETAILS = "ℹ️ Edit Core Details (Title, Poster, Synopsis etc.)"
BTN_CM_MANAGE_EXISTING_SEASONS = "🎞️ Manage Seasons & Episodes"
# BTN_CM_ADD_NEW_SEASON = "➕ Add a New Season" (Could be part of Manage Existing Seasons flow)

CM_SEASON_PROMPT = f"Managing <b>Season {{season_num}}</b> of '{{anime_title}}'."
CM_EPISODE_PROMPT_NUM = f"{EMOJI_EDIT} Enter the <b>Episode Number</b> for S{{season_num}} (e.g., 1, 2, ...):"
# CM_EPISODE_PROMPT_TITLE = "{EMOJI_EDIT} Enter the <b>Episode Title</b> for S{{s_num}}E{{ep_num}} (optional, or 'skip'):" # Removed per plan
CM_EPISODE_FILE_OR_DATE = f"For <b>S{{season_num}}EP{{episode_num}}</b> of '{{anime_title}}', do you want to:"
BTN_CM_ADD_EPISODE_FILES = f"{EMOJI_UPLOAD} <b>Add Files</b>"
BTN_CM_SET_RELEASE_DATE = f"🗓️ <b>Set Release Date</b>"

CM_PROMPT_SEND_FILE = f"{EMOJI_UPLOAD} Send the <b>video or document file</b> for <b>S{{s_num}}EP{{ep_num}}</b> of '{{anime_title}}':"
CM_PROMPT_RESOLUTION = f"{EMOJI_SETTINGS} Select <b>Resolution</b> for this file:"
CM_PROMPT_AUDIO_LANG = f"{EMOJI_SETTINGS} Select <b>Audio Language</b>:"
CM_PROMPT_SUB_LANG = f"{EMOJI_SETTINGS} Select <b>Subtitle Language</b>:"
CM_FILE_VERSION_ADDED = f"{EMOJI_SUCCESS} File version added for S{{s_num}}EP{{ep_num}}."
CM_OPTIONS_AFTER_VERSION_ADD = "What's next?"
BTN_CM_ADD_ANOTHER_VERSION = f"{EMOJI_UPLOAD} Add Another Version (Quality/Lang)"
BTN_CM_NEXT_EPISODE = f"{EMOJI_NEXT} Add Next Episode for this Season"
BTN_CM_FINISH_SEASON_EPISODES = f"{EMOJI_SUCCESS} Done with this Season's Episodes"
BTN_CM_MANAGE_ANOTHER_SEASON = "🎬 Manage Another Season"

CM_PROMPT_RELEASE_DATE = f"🗓️ Enter <b>Release Date</b> for S{{s_num}}EP{{ep_num}} (YYYY-MM-DD), or 'TBA':"
CM_RELEASE_DATE_SET = f"{EMOJI_SUCCESS} Release date for S{{s_num}}EP{{ep_num}} set to {{date}}."

CM_CONFIRM_DELETE_ANIME = f"{EMOJI_DELETE}{EMOJI_ERROR} <b>DANGER ZONE!</b> Are you absolutely sure you want to delete the anime '<b>{{anime_title}}</b>' and all its seasons, episodes, and files? This cannot be undone."
CM_CONFIRM_DELETE_SEASON = f"{EMOJI_DELETE} Confirm delete Season {{season_num}} of '<b>{{anime_title}}</b>' and all its episodes?"
CM_CONFIRM_DELETE_EPISODE = f"{EMOJI_DELETE} Confirm delete S{{season_num}}EP{{episode_num}} of '<b>{{anime_title}}</b>' and all its file versions?"
CM_CONFIRM_DELETE_FILE_VERSION = f"{EMOJI_DELETE} Confirm delete this file version ({{resolution}}, {{audio}}, {{sub}}) for S{{s_num}}EP{{ep_num}}?"
BTN_CONFIRM_DELETE_YES = f"{EMOJI_DELETE} Yes, Delete It!"
BTN_CONFIRM_DELETE_NO = f"{EMOJI_SUCCESS} No, Keep It"
ITEM_DELETED_SUCCESS = f"{EMOJI_SUCCESS} Successfully deleted!"

# --- Admin User Management & Bot Control ---
ADMIN_USER_INFO_HEADER = f"{EMOJI_ADMIN} <b>User Information for ID:</b> <code>{{user_id}}</code> {EMOJI_ADMIN}"
ADMIN_USER_INFO_DETAILS = """
<b>Name:</b> {{first_name}} {{last_name_optional}} (@{{username_optional}})
<b>ID:</b> <code>{{user_id}}</code>
{EMOJI_TOKENS} <b>Tokens:</b> <code>{{tokens}}</code>
{EMOJI_PREMIUM} <b>Premium:</b> {{is_premium}} (Expires: {{premium_expiry_date_str}})
<b>Joined:</b> {{join_date_str}}
<b>Last Active:</b> {{last_active_date_str}}
<b>Watchlist Count:</b> {{watchlist_count}}
"""
USER_NOT_FOUND_FOR_ADMIN_ACTION = f"{EMOJI_ERROR} User with ID/Username '<code>{{identifier}}</code>' not found."

PREMIUM_GRANTED_ADMIN = f"{EMOJI_SUCCESS} Granted <b>{{days}}</b> days of Premium to user <code>{{user_id}}</code>. Expires: {{expiry_date}}."
PREMIUM_GRANTED_USER = f"💎 Congratulations, {EMOJI_WELCOME} You are now a Premium member for <b>{{days}}</b> days! Enjoy the perks!"
PREMIUM_REVOKED_ADMIN = f"{EMOJI_SUCCESS} Revoked Premium status from user <code>{{user_id}}</code>."
PREMIUM_REVOKED_USER = f"⚠️ Your Premium membership has been revoked by an administrator."
TOKENS_ADJUSTED_ADMIN = f"{EMOJI_SUCCESS} Adjusted tokens for user <code>{{user_id}}</code>. New balance: <code>{{new_balance}}</code>."
TOKENS_ADJUSTED_USER = f"{EMOJI_TOKENS} Your token balance has been adjusted by an administrator. New balance: <code>{{new_balance}}</code>."

BROADCAST_CONFIRM = f"📣 Are you sure you want to broadcast the following message to ALL users?\n\n<pre>{{message}}</pre>"
BTN_BROADCAST_SEND = f"{EMOJI_SUCCESS} Yes, Send Broadcast"
BTN_BROADCAST_CANCEL = f"{EMOJI_CANCEL} No, Cancel Broadcast"
BROADCAST_STARTED = f"{EMOJI_LOADING} Broadcast started... This may take some time."
BROADCAST_COMPLETE = f"{EMOJI_SUCCESS} Broadcast complete! Sent to {{success_count}} users. Failed for {{failure_count}} users."

# --- User Log Messages (Sent to USER_LOGS_CHANNEL_ID) ---
LOG_NEW_USER_DIRECT = f"{EMOJI_WELCOME} <b>New User (Direct Start)</b>\n👤 Name: <a href='tg://user?id={{user_id}}'>{{user_first_name}}</a>\n🆔 ID: <code>{{user_id}}</code>\n🪙 Initial Tokens: {{tokens_awarded}}"
LOG_NEW_USER_REFERRAL = f"{EMOJI_WELCOME} <b>New User (Referral)</b>\n👤 Name: <a href='tg://user?id={{user_id}}'>{{user_first_name}}</a>\n🆔 ID: <code>{{user_id}}</code>\n🪙 Initial Tokens: {{tokens_awarded}}\n🗣️ Referred by: <a href='tg://user?id={{referrer_id}}'>{{referrer_name}}</a> (<code>{{referrer_id}}</code>)"
LOG_TOKEN_LINK_GENERATED = f"🔗 <b>Referral Link Generated</b>\n👤 By: <a href='tg://user?id={{user_id}}'>{{user_first_name}}</a> (<code>{{user_id}}</code>)\n🏷️ Code: <code>{{referral_code}}</code>\n⏰ Expires: {{expiry_time_str}}"
LOG_TOKEN_AWARDED_REFERRER = f"{EMOJI_TOKENS} <b>Referral Reward</b>\n👤 Referrer: <a href='tg://user?id={{referrer_id}}'>{{referrer_name}}</a> (<code>{{referrer_id}}</code>)\n🪙 Tokens Earned: +{{tokens_awarded}}\n🤝 From New User: <a href='tg://user?id={{new_user_id}}'>{{new_user_name}}</a>"
LOG_PREMIUM_GRANTED = f"{EMOJI_PREMIUM} <b>Premium Granted</b>\n👤 User: <a href='tg://user?id={{user_id}}'>{{user_first_name}}</a> (<code>{{user_id}}</code>)\n⏳ Duration: {{days}} days\n👑 By Admin: <a href='tg://user?id={{admin_id}}'>{{admin_name}}</a>"
LOG_PREMIUM_REVOKED = f"{EMOJI_CANCEL} <b>Premium Revoked</b>\n👤 User: <a href='tg://user?id={{user_id}}'>{{user_first_name}}</a> (<code>{{user_id}}</code>)\n👑 By Admin: <a href='tg://user?id={{admin_id}}'>{{admin_name}}</a>"
LOG_DOWNLOAD_COMPLETED = f"{EMOJI_DOWNLOAD} <b>Download Initiated</b>\n👤 User: <a href='tg://user?id={{user_id}}'>{{user_first_name}}</a> (<code>{{user_id}}</code>)\n🎬 Anime: {{anime_title}}\n🎞️ S{{season_num}}E{{episode_num}}\n⚙️ Version: {{version_details}}"

# --- Pagination Buttons ---
BTN_PREVIOUS_PAGE = f"{EMOJI_BACK} Prev"
BTN_NEXT_PAGE = f"Next {EMOJI_NEXT}"
BTN_CLOSE_PAGINATION = f"{EMOJI_CANCEL} Close" # Or could be part of main menu / back button

# --- Generic Buttons ---
BTN_YES = f"{EMOJI_SUCCESS} Yes"
BTN_NO = f"{EMOJI_CANCEL} No"
BTN_SKIP = "Skip ➡️"
BTN_DONE = f"{EMOJI_SUCCESS} Done"
BTN_CANCEL_OPERATION = f"{EMOJI_CANCEL} Cancel Operation"


# Placeholder for BOT_USERNAME in some strings, to be replaced at runtime
# This is mainly for links if settings.BOT_USERNAME is needed but not directly accessible
# Example: If a function in strings needs the bot username, it would be passed in.
# For now, it's assumed BOT_USERNAME from settings will be used by the calling functions.
