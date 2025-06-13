# strings.py

# --- General Use Strings ---
# You can use {variable_name} placeholders that will be replaced in the code
# Use HTML ParseMode: <b>bold</b>, <i>italics</i>, <code>monospace</code>, <a href="...">link</a>, <blockquote>blockquote</blockquote>

WELCOME_MESSAGE = """
🎬🎉 <b><u>Welcome to AnimeRealm!</u></b> 🎉🎬

✨ Your ultimate destination for <b>easy and fast</b> anime downloads directly on Telegram. Browse our <b>massive library</b>, find your favorites, and start watching in <b><u>HD!</u></b> ✨

➡️ Use the buttons below to explore AnimeRealm:
"""

HELP_MESSAGE = """
❓ <b><u>AnimeRealm Help Guide</u></b> ❓

Navigating the bot is <b>simple and intuitive</b>!

🔍 <b>Search Anime:</b> Send the name of the anime you're looking for, or use the "Search" button to initiate. We use advanced matching, so even slight typos might work! 😉
📚 <b>Browse All:</b> Explore our entire collection by genre, year, or status. Find something new! 💎
👤 <b>My Profile:</b> View your token balance, premium status, watchlist, and download history.
🪙 <b>Earn Tokens:</b> Get FREE tokens to download anime! Generate your link and complete the step to earn tokens for yourself. It's easy! 👇
🌟 <b>Premium:</b> Unlock <b>unlimited downloads</b> and exclusive benefits. Check out the available plans!
❓ <b>Help:</b> You're here! Read this guide again anytime.
⭐ <b>Leaderboard:</b> See who the top downloaders are!

🔄 All button interactions often <b><u>update the message</u></b> to keep your chat tidy!

If you need further assistance, contact administration via their support channels (if available).

Happy downloading! ❤️
"""

ABOUT_BOT_MESSAGE = """
ℹ️ <b><u>About AnimeRealm</u></b> ℹ️

Version: {bot_version}
Developed by: Your Name/Team
Technology: Python (Pyrogram), MongoDB
Last Updated: {last_updated} # Use a placeholder for git commit date or release date

🙏 Thank you for using AnimeRealm! Your support helps us grow!
"""

ERROR_OCCURRED = "💔 Oops! An unexpected error occurred. We've been notified and will fix it soon. Please try again later."
# Error when the bot couldn't perform a required database operation
DB_ERROR = "💔 Database Error: Couldn't complete the requested action. Please try again. If the issue persists, contact admin."
NO_ANIME_FOUND_SEARCH = "😔 Couldn't find any anime matching `{query}`. Maybe try a different spelling? Or... <blockquote><b>💡 Would you like to request this anime?</b></blockquote>"
REQUEST_FROM_SEARCH_ONLY_PREMIUM = "<i>(Requests from search results are only available for Premium users, or if enabled by admin.)</i>" # Optional text for non-premium

# --- Callback Button Labels (User Menus) ---
BUTTON_SEARCH = "🔍 Search Anime"
BUTTON_BROWSE = "📚 Browse All"
BUTTON_PROFILE = "👤 My Profile"
BUTTON_EARN_TOKENS = "🪙 Earn Tokens"
BUTTON_PREMIUM = "🌟 Premium"
BUTTON_HELP = "❓ Help"
BUTTON_LEADERBOARD = "⭐ Leaderboard"
BUTTON_LATEST = "🆕 Latest Added"
BUTTON_POPULAR = "🔥 Popular Anime"

BUTTON_HOME = "🏠 Main Menu" # For navigation back
BUTTON_BACK = "↩️ Back"
BUTTON_NEXT_PAGE = "➡️ Next ▶️"
BUTTON_PREVIOUS_PAGE = "◀️ Previous ⬅️"

# --- Browse Handlers ---
BROWSE_MAIN_MENU = "📚 <b><u>Browse Options</u></b> 📚\n\nHow would you like to explore our anime library?"
BROWSE_OPTION_ALL = "📖 View All Anime"
BROWSE_OPTION_GENRE = "🏷️ Browse by Genre"
BROWSE_OPTION_YEAR = "🗓️ Browse by Year"
BROWSE_OPTION_STATUS = "🚦 Browse by Status"

GENRE_SELECTION_TITLE = "👇 <b><u>Select Genre(s) to filter</u></b> 👇" # Multi-select filter
YEAR_SELECTION_TITLE = "👇 <b><u>Select a Release Year to filter</u></b> 👇" # Single select filter
STATUS_SELECTION_TITLE = "👇 <b><u>Select a Status to filter</u></b> 👇" # Single select filter

BUTTON_APPLY_FILTER = "✅ Apply Filter" # After selecting multiple options
BUTTON_CLEAR_FILTERS = "🔄 Clear Filters"

BROWSE_LIST_TITLE = "📚 <b><u>Anime Library</u></b> 📚\n\n" # Add {filter_info} placeholder

# --- Search Handlers ---
SEARCH_PROMPT = "🔍 <b><u>Search</u></b>\n\nSend me the name of the anime you want to find:"
SEARCH_RESULTS_TITLE = "🔍 <b><u>Search Results for</u></b> <code>{query}</code> 👇"
SEARCH_NO_MATCHES_REQUEST_BUTTON_FREE = "👇 Request \"{query}\" ({cost} Tokens)" # For the "Request this anime" button on no search results (Free User)
SEARCH_NO_MATCHES_REQUEST_BUTTON_PREMIUM = "👇 Request \"{query}\" (FREE)" # For the "Request this anime" button on no search results (Premium User)


# --- Anime Details, Seasons, Episodes (User View) ---
ANIME_DETAILS_TITLE = "🎬 <b><u>Anime Details</u></b> 🎬"
ANIME_DETAILS_FORMAT = """
✨ <b><u>Title</u></b>: <b>{title}</b>
📚 <b><u>Synopsis</u></b>:
<blockquote>{synopsis}</blockquote>
🏷️ <b><u>Genres</u></b>: {genres}
🗓️ <b><u>Release Year</u></b>: {release_year}
🚦 <b><u>Status</u></b>: {status}
🌟 <b><u>Total Seasons Declared</u></b>: {total_seasons_declared}

<a href="{poster_link}">🖼️ Poster</a>

""" # Season list follows, Add to Watchlist button below
BUTTON_ADD_TO_WATCHLIST = "❤️ Add to Watchlist"
BUTTON_REMOVE_FROM_WATCHLIST = "💔 Remove from Watchlist"

SEASON_LIST_TITLE_USER = "👇 <b><u>Select a Season for</u></b> <b>{anime_title}</b> 👇"
EPISODE_LIST_TITLE_USER = "🎞️ <b><u>Episodes for</u></b> <b>{anime_title}</b> - Season {season_number} 👇"

EPISODE_FORMAT_AVAILABLE_USER = "🎬 EP{episode_number:02d}" # Format like EP01, EP02
EPISODE_FORMAT_RELEASE_DATE_USER = "⏳ EP{episode_number:02d} - Release: {release_date}" # Example format
EPISODE_FORMAT_NOT_ANNOUNCED_USER = "🚫 EP{episode_number:02d} - Release Date Not Announced"

VERSION_LIST_TITLE_USER = "📥 <b><u>Download Options for</u></b> <b>{anime_title}</b> - EP{episode_number:02d} 👇"
VERSION_DETAILS_FORMAT_USER = """
<a href="{file_id_link}">💎 {quality}</a>
🎧 Audio: {audio_langs}
📝 Subtitles: {subtitle_langs}
📦 Size: {file_size}
""" # Note: file_id_link here is conceptual for the Download button's internal data


DOWNLOAD_FILE_DETAILS_PROMPT = "📥 <b><u>Confirm Download</u></b> 📥\n\nYou are about to download this file:"
# Include formatted version details here before the Download button


BUTTON_DOWNLOAD_FILE_USER = "📥 Download This File ({size})" # Use {size} dynamically in the button text
NOT_ENOUGH_TOKENS = "Oops! 😅 You need <b>{required_tokens}</b> token(s) to download this file, but you only have <b>{user_tokens}</b> tokens. \n\n💰 Earn more tokens using the /gen_token command!"
PREMIUM_REQUIRED = "This feature is exclusive to Premium users. ✨ Unlock unlimited downloads by going Premium!" # Example for premium-only features
FILE_BEING_SENT = "Sending your file now... 💪 Please be patient, this may take a few moments."
FILE_SENT_SUCCESS = "✅ File sent successfully! Enjoy! 🎉"
FILE_SEND_ERROR = "😞 Sorry, failed to send the file. Please try again." # Should be handled in download logic

# --- Profile & Watchlist Handlers ---
PROFILE_TITLE = "👤 <b><u>Your Profile</u></b> 👤"
PROFILE_FORMAT = """
👋 <b><u>Hello</u></b>, {user_mention}!

💰 <b><u>Download Tokens</u></b>: <b>{tokens}</b> 🪙
✨ <b><u>Premium Status</u></b>: {premium_status}
📊 <b><u>Total Files Downloaded</u></b>: {download_count}

🎬 <b><u>Watchlist</u></b>: {watchlist_count} Anime added
""" # Buttons follow: Manage Watchlist, Notification Settings, Back Home

BUTTON_MANAGE_WATCHLIST = "⚙️ Manage Watchlist"
BUTTON_NOTIFICATION_SETTINGS = "🔔 Notification Settings: {status}" # Status will be e.g. '✅ On'

WATCHLIST_TITLE = "🎬 <b><u>Your Watchlist</u></b> 🎬"
WATCHLIST_EMPTY = "Your watchlist is empty! 😥 Add anime you love by viewing their details and clicking the '❤️ Add to Watchlist' button."

NOTIFICATION_SETTINGS_TITLE = "🔔 <b><u>Notification Settings</u></b> 🔔"
NOTIFICATION_SETTINGS_PROMPT = "Select the types of notifications you want to receive for your watchlist:"
BUTTON_NOTIFY_NEW_EPISODE_STATE = "➕ New Episodes: {state}" # State is ✅ On or ❌ Off
BUTTON_NOTIFY_NEW_VERSION_STATE = "✨ New Versions: {state}" # State is ✅ On or ❌ Off
BUTTON_NOTIFY_RELEASE_DATE_STATE = "⏳ Date Changes: {state}" # State is ✅ On or ❌ Off

BUTTON_SAVE_NOTIFICATION_SETTINGS = "💾 Save Settings" # Optional if toggle updates instantly
NOTIFICATION_SETTINGS_SAVED = "🔔 Your notification settings have been saved!"

WATCHLIST_ADDED_NOTIFICATION = """
🔔 <b><u>Watchlist Update!</u></b> 🔔

New episode for <a href="{anime_url}"><b>{anime_title}</b></a> is now available: 🎬 EP{episode_number:02d}

Download it now! 👇
""" # Add a button/link to the episode here

WATCHLIST_NEW_VERSION_NOTIFICATION = """
🔔 <b><u>Watchlist Update!</u></b> 🔔

New version ({quality}, {audio}/{subs}) available for <a href="{anime_url}"><b>{anime_title}</b></a> - S{season_number}E{episode_number:02d}!

Download it now! 👇
"""

# --- Token Handlers ---
GEN_TOKEN_TITLE = "🪙 <b><u>Earn Download Tokens</u></b> 🪙"
GEN_TOKEN_INSTRUCTIONS = """
👇 <b><u>Generate your unique link to earn tokens!</u></b> 👇

Click the button below 👇 titled "<b>✨ Go to Token Link ✨</b>".

It will take you through a quick process via a link shortener. Once completed, you'll be redirected back here, and <b>you will automatically receive {tokens_earned} Download Token(s)</b>!

Press the "🤔 How to earn more?" button for a tutorial.
"""

BUTTON_GO_TO_TOKEN_LINK = "✨ Go to Token Link ✨" # The button with the shortened URL
BUTTON_HOW_TO_EARN_TOKENS = "🤔 How to earn more?" # Button leading to the tutorial

# If HOW_TO_EARN_TUTORIAL_LINK in config.py is None, use this text:
EARN_TOKENS_TUTORIAL_MESSAGE_TEXT = """
📄 <b><u>How to Earn Tokens Tutorial</u></b> 📄

Follow these steps:

1.  Use the <code>/gen_token</code> command or button.
2.  You will get a message with a "<b>✨ Go to Token Link ✨</b>" button.
3.  Tap this button. You'll be taken to a website (a link shortener).
4.  On that website, you'll complete a short step (like viewing an ad or completing a captcha). Follow the instructions on the website carefully.
5.  After completing their step, the website will provide a final link that redirects you back to Telegram, opening <b><u>AnimeRealm</u></b> again.
6.  When you're redirected back here via that link, our bot automatically verifies the token embedded in it.
7.  <b>Boom! 💥 You automatically receive {tokens_earned} Download Token(s)!</b>

Generate and redeem links anytime you need more tokens for downloads!
""" # Use {tokens_earned} dynamically

# If HOW_TO_EARN_TUTORIAL_LINK is set in config.py, use this message and the button will open the link:
EARN_TOKENS_TUTORIAL_MESSAGE_LINK_INTRO = """
📄 <b><u>How to Earn Tokens Tutorial</u></b> 📄

Watch this quick guide to understand the process of earning tokens:
""" # The button to open the link will be added programmatically


TOKEN_REDEEMED_SUCCESS = "🎉 Congratulations! Your token link was successfully redeemed, and you've earned <b>{tokens_earned}</b> token(s)! \n\n📊 Your new balance is <b>{user_tokens}</b> tokens. Happy downloading! 😊"
TOKEN_REDEEMED_OWN = "🤔 You can only redeem <b>your own</b> generated links. That's how it works! Share the /gen_token command itself, not your personal link." # Adjusted message
TOKEN_ALREADY_REDEEMED = "😟 This token link has already been used or has expired." # Adjusted message
TOKEN_EXPIRED = "⏳ This token link has expired and cannot be used."
TOKEN_INVALID = "🚫 Invalid token link provided."


# --- Premium Handlers ---
PREMIUM_INFO_TITLE = "✨ <b><u>Unlock Premium Benefits</u></b> ✨"
PREMIUM_INFO_HEADER = """
💎 <b>Go Premium</b> and experience AnimeRealm without limits! 💎

Become a Premium member and enjoy:
""" # Features are listed after this
PREMIUM_PLAN_FORMAT = """
<b><u>🌟 {plan_name}</u></b>
💸 <b><u>Price</u></b>: {price}
⏳ <b><u>Duration</u></b>: {duration} days
🎉 <b><u>Benefits</u></b>:
{features_list}

➡️ {description}
""" # Format for each plan in the list (features_list should be bullet points)
# For bullet points in HTML: <blockquote>• Benefit 1<br>• Benefit 2</blockquote>


PREMIUM_PURCHASE_INSTRUCTIONS = """
Interested in a plan? 👇

{payment_info}

For manual activation or questions, contact an admin!
"""

# --- Request Handlers (User-Facing) ---
REQUEST_PROMPT_FREE = """
🙏 <b><u>Anime Request</u></b> 🙏\n\nPlease send me the <b>exact name</b> of the anime you'd like to request:

⚠️ Note for Free Users: Making a request will cost you <b>{request_token_cost} download token(s)</b>. You currently have <b>{user_tokens}</b> tokens.

Continue by sending the anime name, or type `❌ Cancel` to abort.
"""

REQUEST_PROMPT_PREMIUM = """
🙏 <b><u>Anime Request</u></b> 🙏\n\nPlease send me the <b>exact name</b> of the anime you'd like to request:

✨ <b><u>Premium Perk:</u></b> You can request anime for <b>FREE</b> as a Premium user!

Continue by sending the anime name, or type `❌ Cancel` to abort.
"""

REQUEST_NOT_ENOUGH_TOKENS = "😟 Sorry, you need <b>{request_token_cost}</b> token(s) to make a request, but you only have <b>{user_tokens}</b>. \n\nEarn more tokens using the /gen_token command before making a request."

REQUEST_RECEIVED_USER_CONFIRM_FREE = "✅ Your request for '<b>{anime_name}</b>' has been sent to the admins! \n\n💰 <b>{request_token_cost} token(s)</b> have been deducted from your balance. You now have <b>{user_tokens}</b> tokens."

REQUEST_RECEIVED_USER_CONFIRM_PREMIUM = "✅ Your request for '<b>{anime_name}</b>' has been sent to the admins! \n\n✨ Thanks to your Premium status, this request was <b>FREE</b>!"

REQUEST_ONLY_PREMIUM = "The <code>/request</code> command is only available to <b>Premium users</b>. ✨ However, if you search for an anime and we don't find it, you'll see an option to request it then!"


# --- Admin Content Management Handlers ---
MANAGE_CONTENT_TITLE = "🛠️ <b><u>Admin Content Management</u></b> 🛠️"
MANAGE_CONTENT_OPTIONS = """
👋 <b><u>Welcome Admin!</u></b>\n\nWhat would you like to manage today?
"""
BUTTON_ADD_NEW_ANIME = "✨ Add New Anime"
BUTTON_EDIT_ANIME = "✏️ Edit Existing Anime" # Leads to searching/selecting existing
BUTTON_VIEW_ALL_ANIME = "📚 View All Anime (Admin)" # Admin-only full list for management
BUTTON_HOME_ADMIN_MENU = "🏠 CM Main Menu" # Button back to content management menu


ADD_ANIME_NAME_PROMPT = "👇 Send the <b><u>Name</u></b> of the new anime:"
ADD_ANIME_NAME_SEARCH_RESULTS = "🔍 Found existing entries matching '<code>{name}</code>'. Select one to edit or 'Add as New':" # Presented after name search in add flow
BUTTON_ADD_AS_NEW_ANIME = "🆕 Add \"{name}\" as New"

ADD_ANIME_POSTER_PROMPT = "🖼️ Send the <b><u>Poster Image</u></b> for '{anime_name}':"
ADD_ANIME_SYNOPSIS_PROMPT = "📝 Send the <b><u>Synopsis</u></b> for '{anime_name}':"
ADD_ANIME_SEASONS_PROMPT = "📺 How many <b><u>Total Seasons</u></b> does '{anime_name}' have? (Send a number):" # For Add New flow

ADD_ANIME_GENRES_PROMPT = "🏷️ Select the <b><u>Genres</u></b> for '{anime_name}' (Use buttons. Click Done when finished):"
BUTTON_METADATA_DONE_SELECTING = "✅ Done Selecting {metadata_type}" # Placeholder for type (Genres, Audio, Subs)

ADD_ANIME_YEAR_PROMPT = "🗓️ Send the <b><u>Release Year</u></b> for '{anime_name}':"
ADD_ANIME_STATUS_PROMPT = "🚦 Select the <b><u>Status</u></b> for '{anime_name}':"

ANIME_ADDED_SUCCESS = "🎉 Anime <b><u>{anime_name}</u></b> added successfully! 🎉\nYou can now add seasons and episodes. 👇"
ANIME_EDITED_SUCCESS = "✅ Anime details updated for <b><u>{anime_name}</u></b>!"

# Specific buttons for managing an ANIME
BUTTON_MANAGE_SEASONS_EPISODES = "📺 Manage Seasons/Episodes"
BUTTON_EDIT_NAME = "✏️ Edit Name"
BUTTON_EDIT_SYNOPSIS = "📝 Edit Synopsis"
BUTTON_EDIT_POSTER = "🖼️ Edit Poster"
BUTTON_EDIT_GENRES = "🏷️ Edit Genres"
BUTTON_EDIT_YEAR = "🗓️ Edit Release Year"
BUTTON_EDIT_STATUS = "🚦 Edit Status"
BUTTON_EDIT_TOTAL_SEASONS = "🔢 Re-prompt Total Seasons" # Option to change total seasons count

MANAGE_SEASONS_TITLE = "📺 <b><u>Manage Seasons for</u></b> <b>{anime_name}</b> 🛠️"
SEASON_MANAGEMENT_OPTIONS = """
🔧 <b><u>Managing Season {season_number}</u></b> for {anime_name}:
"""
BUTTON_ADD_NEW_SEASON = "➕ Add New Season"
BUTTON_REMOVE_SEASON = "🗑️ Remove Season {season_number}" # Used in remove selection list
BUTTON_MANAGE_EPISODES = "🎬 Manage Episodes for Season {season_number}"
BUTTON_BACK_TO_ANIME_LIST_ADMIN = "↩️ Back to Anime Menu" # From season/episode management to anime details/management view


ADD_SEASON_EPISODES_PROMPT = "🔢 How many <b><u>Episodes</u></b> does Season <b>__{season_number}__</b> of '{anime_name}' have? (Send a number):" # For adding episode placeholders
EPISODES_CREATED_SUCCESS = "✅ Added <b>{episode_count}</b> episode slot(s) for Season <b>__{season_number}__</b>!\nYou can now add files or release dates."


MANAGE_EPISODES_TITLE = "🎞️ <b><u>Manage Episodes for</u></b> <b>{anime_name}</b> - Season {season_number} 🛠️"

EPISODE_OPTIONS_WITH_RELEASE_DATE_ADMIN = "🗓️ <b>Release Date</b>: {release_date}" # Admin view
EPISODE_OPTIONS_WITH_FILES_ADMIN = "📥 <b><u>Available Versions</u></b>:" # Admin view

# Used in episodes list and single episode view when no files/date
EPISODE_STATUS_NO_CONTENT = "❓ No Files/Date"
EPISODE_STATUS_HAS_FILES = "✅ Files Available"
EPISODE_STATUS_HAS_DATE = "⏳ {date}"

BUTTON_ADD_EPISODE_FILE = "➕ Add Episode File(s)"
BUTTON_ADD_RELEASE_DATE = "🗓️ Set Release Date"
BUTTON_REMOVE_EPISODE = "🗑️ Remove Episode {episode_number}"

PROMPT_RELEASE_DATE = "📅 Send the <b><u>Release Date</u></b> for EP<b>__{episode_number:02d}__</b> (<code>{anime_name}</code>) in <b>DD/MM/YYYY</b> format:"
RELEASE_DATE_SET_SUCCESS = "✅ Release date for EP<b>__{episode_number:02d}__</b> set to <b>__{release_date}__</b>."
INVALID_DATE_FORMAT = "🚫 Invalid date format. Please send in <b>DD/MM/YYYY</b> format (e.g., 25/12/2023)."


ADD_FILE_PROMPT = "📥 Send the <b><u>Episode File</u></b> (video or compressed archive) for S<b>__{season_number}__</b>E<b>__{episode_number:02d}__</b> (<code>{anime_name}</code>):"
ADD_FILE_METADATA_PROMPT_BUTTONS = "💾 File received! Please select the details using the buttons below or type manually if needed:"

PROMPT_AUDIO_LANGUAGES_BUTTONS = "🎧 <b><u>Select Audio Language(s)</u></b>: (Click to toggle, Done when finished)"
PROMPT_SUBTITLE_LANGUAGES_BUTTONS = "📝 <b><u>Select Subtitle Language(s)</u></b>: (Click to toggle, Done when finished)"

BUTTON_ADD_OTHER_VERSION = "➕ Add Another Version for EP<b>__{episode_number:02d}__</b>"
BUTTON_NEXT_EPISODE = "➡️ Go to Next Episode (EP<b>__{next_episode_number:02d}__</b>)" # Display next number

FILE_ADDED_SUCCESS = "✅ File version added for EP<b>__{episode_number:02d}__</b> ({quality}, {audio} / {subs})!"
FILE_DELETED_SUCCESS = "🗑️ File version deleted successfully."
BUTTON_DELETE_FILE_VERSION_SELECT = "🗑️ Delete a File Version" # Button in episode menu


# --- Admin Utility Handlers ---
ADMIN_ADD_TOKENS_PROMPT = "➕ Send the Telegram <b><u>User ID</u></b> of the user you want to add tokens to:"
ADMIN_ADD_TOKENS_AMOUNT_PROMPT = "🔢 How many <b><u>tokens</u></b> do you want to add to user ID <code>{user_id}</code>? (Send a number):"
ADMIN_TOKENS_ADDED_SUCCESS = "✅ Successfully added <b>{amount}</b> tokens to user ID <code>{user_id}</code>. New balance: <b>{new_balance}</b>."

ADMIN_REMOVE_TOKENS_PROMPT = "➖ Send the Telegram <b><u>User ID</u></b> of the user you want to remove tokens from:"
ADMIN_REMOVE_TOKENS_AMOUNT_PROMPT = "🔢 How many <b><u>tokens</u></b> do you want to remove from user ID <code>{user_id}</code>? (Send a number):"
ADMIN_TOKENS_REMOVED_SUCCESS = "✅ Successfully removed <b>{amount}</b> tokens from user ID <code>{user_id}</code>. New balance: <b>{new_balance}</b>."
ADMIN_TOKENS_ERROR = "💔 Error updating tokens for user ID <code>{user_id}</code>."

BROADCAST_PROMPT = "📢 Send the <b><u>message</u></b> you want to broadcast to all users:"
BROADCAST_CONFIRMATION = "Are you sure you want to send this message to all {user_count} users?\n\n<b>Message Preview:</b>\n\n<blockquote>{message_preview}</blockquote>"
BUTTON_CONFIRM_BROADCAST = "✅ Send Broadcast Now"
BUTTON_CANCEL_BROADCAST = "❌ Cancel Broadcast"
BROADCAST_STARTED = "✅ Broadcast started. It may take some time."
BROADCAST_CANCELLED = "❌ Broadcast cancelled."
BROADCAST_MESSAGE_SENT = "📢 **Broadcast Message**\n\n{message_text}" # Format of the broadcast message itself

DATA_DELETION_PROMPT = "💀 <b><u>DANGER: PERMANENT DATA LOSS</u></b> 💀\n\nAre you absolutely sure you want to delete <b>ALL</b> bot data (users, anime, requests, tokens, states)?\n\n<b>THIS CANNOT BE UNDONE.</b>\n\nType `YES I AM SURE DELETE EVERYTHING` to confirm."
DATA_DELETION_CONFIRMATION_PHRASE = "YES I AM SURE DELETE EVERYTHING" # Phrase the admin must type
DATA_DELETION_CONFIRMED = "💥 ALL BOT DATA IS BEING PERMANENTLY DELETED. This may take some time. The bot will attempt to log completion but may restart."
DATA_DELETION_CANCELLED = "😌 Data deletion cancelled."
DATA_DELETION_WRONG_CONFIRMATION = "❌ Incorrect confirmation phrase. Data deletion cancelled."


# --- Leaderboard ---
LEADERBOARD_TITLE = "🏆 <b><u>Top Downloaders</u></b> 🏆"
LEADERBOARD_EMPTY = "The leaderboard is currently empty. Start downloading to see your name here! 😉"
LEADERBOARD_ENTRY_FORMAT = "<b>#{rank}.</b> {user_mention} - <b>{download_count}</b> Downloads" # Use user_mention helper from common


# --- Latest/Popular ---
LATEST_TITLE = "🆕 <b><u>Latest Episodes Added</u></b> 👇"
POPULAR_TITLE = "🔥 <b><u>Most Popular Anime</u></b> 👇"
NO_CONTENT_YET = "😞 No content added yet! Check back later or use the search."
LATEST_ENTRY_FORMAT = "🎬 <b><u>{anime_title}</u></b> - S{season_number}E{episode_number:02d}"
POPULAR_ENTRY_FORMAT = "<b><u>{anime_title}</u></b> ({download_count} Downloads)"


# --- Inline Mode ---
# If implementing inline search
INLINE_SEARCH_PLACEHOLDER = "Type anime name to search..."
# Message for empty inline results
INLINE_NO_RESULTS = "😔 No anime found matching your query."


# --- Utility Texts ---
LOADING_ANIMATION = "🔄 Processing..." # Use where applicable with answer or message edits
CANCEL_ACTION = "❌ Cancel" # Text that triggers cancellation
ACTION_CANCELLED = "✅ Action cancelled."
INPUT_TIMEOUT = "⏳ Input timed out. Please try again."
USER_NOT_FOUND_DB = "⚠️ User not found in database. Please try again. If the issue persists, contact admin." # For admin lookups

# --- Data Formatting ---
FILE_SIZE_FORMAT_MB = "{size:.2f} MB"
FILE_SIZE_FORMAT_GB = "{size:.2f} GB"
# Use a helper to format bytes
FILE_SIZE_UNKNOWN = "Unknown Size"

# --- Admin Content Management Helper Texts/Buttons ---
BUTTON_DONE = "✅ Done" # Generic Done button text
BUTTON_SELECT = "Select" # Generic Select button text (for multi-select button states)
BUTTON_UNSELECT = "✅ Selected" # Generic Unselect button state (for multi-select button states)
