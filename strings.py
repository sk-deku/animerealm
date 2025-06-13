# strings.py

# --- General Use Strings ---
# You can use {variable_name} placeholders that will be replaced in the code
WELCOME_MESSAGE = """
🎬🎉 **__Welcome to AnimeRealm!__** 🎉🎬

✨ Your ultimate destination for **easy and fast** anime downloads directly on Telegram. Browse our **massive library**, find your favorites, and start watching in **__HD!__** ✨

➡️ Use the buttons below to explore AnimeRealm:
"""

HELP_MESSAGE = """
❓ **__AnimeRealm Help Guide__** ❓

Navigating the bot is **simple and intuitive**!

🔍 **Search Anime:** Send the name of the anime you're looking for, or use the "Search" button to initiate. We use advanced matching, so even slight typos might work! 😉
📚 **Browse All:** Explore our entire collection by genre, year, or status. Find something new! 💎
👤 **My Profile:** View your token balance, premium status, watchlist, and download history.
🪙 **Earn Tokens:** Get FREE tokens to download anime! Share your unique link and earn tokens when someone new starts the bot through it. It's easy! 👇
🌟 **Premium:** Unlock **unlimited downloads** and exclusive benefits. Check out the available plans!
❓ **Help:** You're here! Read this guide again anytime.

🔄 All button interactions often **__update the message__** to keep your chat tidy!

If you need further assistance, contact administration via their support channels (if available).

Happy downloading! ❤️
"""

ABOUT_BOT_MESSAGE = """
ℹ️ **__About AnimeRealm__** ℹ️

Version: 1.0.0
Developed by: King Deku/@sk_deku_bot
Technology: Python (Pyrogram), MongoDB
Last Updated: [Date]

🙏 Thank you for using AnimeRealm! Your support helps us grow!
"""

ERROR_OCCURRED = "💔 Oops! An unexpected error occurred. We've been notified and will fix it soon. Please try again later."
NO_ANIME_FOUND_SEARCH = "😔 Couldn't find any anime matching `{query}`. Maybe try a different spelling? Or... <blockquote><b>💡 Would you like to request this anime?</b></blockquote>"

# --- Callback Button Labels ---
BUTTON_SEARCH = "🔍 Search Anime"
BUTTON_BROWSE = "📚 Browse Anime"
BUTTON_PROFILE = "👤 My Profile"
BUTTON_EARN_TOKENS = "🪙 Earn Tokens"
BUTTON_PREMIUM = "🌟 Premium"
BUTTON_HELP = "❓ Help"
BUTTON_HOME = "🏠 Main Menu" # For navigation back
BUTTON_BACK = "↩️ Back"
BUTTON_NEXT_PAGE = "➡️ Next ▶️"
BUTTON_PREVIOUS_PAGE = "◀️ Previous ⬅️"

# --- Browse Handlers ---
BROWSE_MAIN_MENU = "📚 __**Browse Options**__ 📚\n\nHow would you like to explore our anime library?"
BROWSE_OPTION_ALL = "📖 View All Anime"
BROWSE_OPTION_GENRE = "🏷️ Browse by Genre"
BROWSE_OPTION_YEAR = "🗓️ Browse by Year"
BROWSE_OPTION_STATUS = "🚦 Browse by Status"

GENRE_SELECTION_TITLE = "👇 **__Select a Genre__** 👇"
YEAR_SELECTION_TITLE = "👇 **__Select a Release Year__** 👇"
STATUS_SELECTION_TITLE = "👇 **__Select Status__** 👇"

BROWSE_LIST_TITLE = "📚 __**Anime Library**__ 📚" # {page_info} can be added: "... ({page} / {total_pages})"

# --- Search Handlers ---
SEARCH_PROMPT = "🔍 **__Search__**\n\nSend me the name of the anime you want to find:"
SEARCH_RESULTS_TITLE = "🔍 __**Search Results for**__ `{query}` 👇"
SEARCH_NO_MATCHES_REQUEST_BUTTON = "✨ Request \"{query}\"" # For the "Request this anime" button on no search results

# --- Anime Details, Seasons, Episodes ---
ANIME_DETAILS_TITLE = "🎬 __**Anime Details**__ 🎬"
ANIME_DETAILS_FORMAT = """
✨ **__Title__**: **{title}**
📚 **__Synopsis__**:
<blockquote>{synopsis}</blockquote>
🏷️ **__Genres__**: {genres}
🗓️ **__Release Year__**: {release_year}
🚦 **__Status__**: {status}
🌟 **__Seasons Available__**: {total_seasons}

👇 **__Select a Season__**:
"""
SEASON_LIST_TITLE = "📺 __**Seasons for**__ {anime_title} 👇"
EPISODE_LIST_TITLE = "🎞️ __**Episodes for**__ {anime_title} - Season {season_number} 👇"

EPISODE_FORMAT_AVAILABLE = "🎬 EP{episode_number:02d}" # Format like EP01, EP02
EPISODE_FORMAT_RELEASE_DATE = "⏳ EP{episode_number:02d} - Release On: {release_date}" # Example format
EPISODE_FORMAT_NOT_ANNOUNCED = "🚫 EP{episode_number:02d} - Release Date Not Announced"

VERSION_LIST_TITLE = "📥 __**Download Options for**__ {anime_title} - EP{episode_number:02d} 👇"
VERSION_DETAILS_FORMAT = """
💎 **__Quality__**: {quality}
🎧 **__Audio__**: {audio_langs}
📝 **__Subtitles__**: {subtitle_langs}
📦 **__Size__**: {file_size}
"""

DOWNLOAD_CONFIRM_PROMPT = "Ready to download this version?" # Might use for token check/confirmation
BUTTON_DOWNLOAD = "📥 Download This Version ({size})" # Use {size} dynamically
NOT_ENOUGH_TOKENS = "Oops! 😅 You need **1** token to download this file, but you only have **{user_tokens}** tokens. \n\n💰 Earn more tokens using the /gen_token command! or Buy Premium"
PREMIUM_REQUIRED = "This feature is exclusive to Premium users. ✨ Unlock unlimited downloads by going Premium!" # Example for premium-only features
FILE_BEING_SENT = "Sending your file now... 💪 Please be patient, this may take a few secands."
FILE_SENT_SUCCESS = "✅ File sent successfully! Enjoy! 🎉"
FILE_SEND_ERROR = "😞 Sorry, failed to send the file. Please try again."


# --- Profile & Watchlist Handlers ---
PROFILE_TITLE = "👤 __**Your Profile**__ 👤"
PROFILE_FORMAT = """
👋 **__Hello__**, {user_name}!

💰 **__Download Tokens__**: **{tokens}** 🪙
✨ **__Premium Status__**: {premium_status}
📊 **__Total Files Downloaded__**: {download_count}

🎬 **__Watchlist__**: {watchlist_count} Anime added ({manage_watchlist_button})

Use /gen_token to earn more tokens or /premium to unlock unlimited downloads!
"""
BUTTON_MANAGE_WATCHLIST = "⚙️ Manage Watchlist"

WATCHLIST_TITLE = "🎬 __**Your Watchlist**__ 🎬"
WATCHLIST_EMPTY = "Your watchlist is empty! 😥 Add anime you love by viewing their details and clicking the 'Add to Watchlist' button."
BUTTON_ADD_TO_WATCHLIST = "❤️ Add to Watchlist"
BUTTON_REMOVE_FROM_WATCHLIST = "💔 Remove from Watchlist"
ANIME_ADDED_TO_WATCHLIST = "✅ '{anime_title}' added to your watchlist! We'll notify you about new episodes.🔔"
ANIME_REMOVED_FROM_WATCHLIST = "✅ '{anime_title}' removed from your watchlist. Notifications stopped.🔇"
NOTIFICATION_SETTINGS_TITLE = "🔔 **__Notification Settings__** 🔔"
NOTIFICATION_SETTINGS_PROMPT = "Select the types of notifications you want to receive for your watchlist:"
BUTTON_NOTIFY_NEW_EPISODE = "➕ New Episode" # State will change (✅ On / ❌ Off)
BUTTON_NOTIFY_NEW_VERSION = "✨ New Quality/Version" # State will change
NOTIFICATION_SETTINGS_SAVED = "🔔 Your notification settings have been saved!"

# --- Token Handlers ---
GEN_TOKEN_TITLE = "🪙 __**Earn Download Tokens**__ 🪙"
GEN_TOKEN_INSTRUCTIONS = """
Want **FREE** downloads? Follow these steps! 👇

1️⃣ Share the link below with your friends or on social media.
2️⃣ When someone **new** starts the bot using *your* unique link, they'll go through a quick step.
3️⃣ Once they're done, **you automatically get 1 Download Token**! ✨

🏆 Each token = 1 file download! The more you share, the more you can download!

<a href="{redeem_link}">🔗 **Your Unique Token Link (Tap to copy!)** 🔗</a>

❗ **This link is unique to you and will expire after {expiry_hours} hour(s) or one successful use.**
""" # Link is provided via HTML for clickable text

BUTTON_HOW_TO_EARN_TOKENS = "🤔 Tutorial?" # Button leading to a tutorial message
EARN_TOKENS_TUTORIAL_MESSAGE = """
📄 **__How to Earn Tokens Tutorial__** 📄

Step-by-step guide:

1.  Use the `/gen_token` command or button.
2.  You will get a unique Telegram link (`t.me/...`).
3.  Share **that link**! (You can share the message the bot sends, which includes the link).
4.  When a *new user* clicks your link, they are directed to start the bot.
5.  They might need to click 'Start' or a button if a shortener is involved.
6.  After they complete the step and successfully land back in chat with AnimeRealm (often they just need to hit 'Start'), our bot recognizes your token.
7.  **Boom! 💥 You automatically receive 1 Download Token!**

Share widely and enjoy your free anime! 🥰
"""
TOKEN_REDEEMED_SUCCESS = "🎉 Congratulations! Your token link was successfully redeemed, and you've earned **{tokens_earned}** token(s)! \n\n📊 You now have **{user_tokens}** tokens."
TOKEN_REDEEMED_OWN = "Oops! You clicked your own token link. 😉 Share it with others to earn tokens!"
TOKEN_ALREADY_REDEEMED = "😟 This token link has already been used."
TOKEN_EXPIRED = "⏳ This token link has expired."
TOKEN_INVALID = "🚫 Invalid token link."


# --- Premium Handlers ---
PREMIUM_INFO_TITLE = "✨ __**Unlock Premium Benefits**__ ✨"
PREMIUM_INFO_HEADER = """
💎 **Go Premium** and experience AnimeRealm without limits! 💎

Become a Premium member and enjoy:
""" # Features are listed after this
PREMIUM_PLAN_FORMAT = """
**__🌟 {plan_name}__**
💸 **__Price__**: {price}
⏳ **__Duration__**: {duration} days
🎉 **__Benefits__**:
{features}

➡️ {description}
""" # Format for each plan in the list

PREMIUM_PURCHASE_INSTRUCTIONS = """
Interested in a plan? 👇

{payment_info}

For manual activation or questions, contact an admin!
"""

# --- Request Handlers ---
REQUEST_PROMPT = "🙏 **__Anime Request__** 🙏\n\nPlease send me the **exact name** of the anime you'd like to request:"
REQUEST_RECEIVED_USER_CONFIRM = "✅ Your request for '**{anime_name}**' has been sent to the admins! We'll review it shortly."
REQUEST_NOTIFICATION_ADMIN = "📥 **__NEW ANIME REQUEST__**\n\nRequester: [{user_name}](tg://user?id={user_id})\nAnime: **{anime_name}**"
ADMIN_REQUEST_OPTIONS_TITLE = "Reply with one of the options below:"
BUTTON_REQ_UNAVAILABLE = "❌ Unavailable"
BUTTON_REQ_ALREADY_ADDED = "✅ Already Added"
BUTTON_REQ_NOT_RELEASED = "⏳ Not Yet Released"
BUTTON_REQ_WILL_ADD_SOON = "✨ Will Add Soon" # Optional
REQUEST_ADMIN_REPLY_SENT = "➡️ Your response ('{response}') has been sent to [{user_name}](tg://user?id={user_id})."
USER_REQUEST_RESPONSE = "📣 Update on your request for '**{anime_name}**':\n<blockquote>{admin_response}</blockquote>"
REQUEST_ONLY_PREMIUM = "The `/request` command is only available to **Premium users**. ✨ However, if you search for an anime and we don't find it, you'll see an option to request it then!"

# --- Admin Content Management Handlers ---
MANAGE_CONTENT_TITLE = "🛠️ __**Admin Content Management**__ 🛠️"
MANAGE_CONTENT_OPTIONS = """
👋 **__Welcome Admin!__**\n\nWhat would you like to manage today?
"""
BUTTON_ADD_NEW_ANIME = "✨ Add New Anime"
BUTTON_EDIT_ANIME = "✏️ Edit Existing Anime"
BUTTON_VIEW_ALL_ANIME = "📚 View All Anime (Admin)" # Admin-only full list

ADD_ANIME_NAME_PROMPT = "👇 Send the **__Name__** of the new anime:"
ADD_ANIME_NAME_SEARCH_RESULTS = "Found existing entries matching '{name}'. Select to edit or 'Add as New':"
BUTTON_ADD_AS_NEW_ANIME = "🆕 Add \"{name}\" as New"
ADD_ANIME_POSTER_PROMPT = "🖼️ Send the **__Poster Image__** for '{anime_name}':"
ADD_ANIME_SYNOPSIS_PROMPT = "📝 Send the **__Synopsis__** for '{anime_name}':"
ADD_ANIME_SEASONS_PROMPT = "📺 How many **__Seasons__** does '{anime_name}' have? (Send a number):"
ADD_ANIME_GENRES_PROMPT = "🏷️ Select the **__Genres__** for '{anime_name}' (Use buttons. Click Done when finished):"
BUTTON_ADD_GENRE_DONE = "✅ Done Selecting Genres"
ADD_ANIME_YEAR_PROMPT = "🗓️ Send the **__Release Year__** for '{anime_name}':"
ADD_ANIME_STATUS_PROMPT = "🚦 Select the **__Status__** for '{anime_name}':"

ANIME_ADDED_SUCCESS = "✅ Anime '{anime_name}' added successfully! You can now manage its seasons and episodes."
ANIME_EDITED_SUCCESS = "✅ Anime '{anime_name}' details updated!"

MANAGE_SEASONS_TITLE = "📺 __**Manage Seasons for**__ {anime_name} 🛠️"
SEASON_MANAGEMENT_OPTIONS = """
🔧 **__Managing Season {season_number}__** for {anime_name}:
"""
BUTTON_ADD_NEW_SEASON = "➕ Add New Season"
BUTTON_REMOVE_SEASON = "🗑️ Remove Season {season_number}"
BUTTON_MANAGE_EPISODES = "🎬 Manage Episodes for Season {season_number}"
BUTTON_BACK_TO_ANIME_LIST = "↩️ Back to Anime List" # Admin list

ADD_SEASON_EPISODES_PROMPT = "🔢 How many **__Episodes__** does Season {season_number} of '{anime_name}' have? (Send a number):"
EPISODES_CREATED_SUCCESS = "✅ {episode_count} episode slots created for Season {season_number}."

MANAGE_EPISODES_TITLE = "🎞️ __**Manage Episodes for**__ {anime_name} - Season {season_number} 🛠️"
EPISODE_OPTIONS_NO_FILES = "🔧 **__Managing EP{episode_number:02d}__** for {anime_name} - Season {season_number}.\n\nCurrently no files or release date."
EPISODE_OPTIONS_WITH_RELEASE_DATE = "🔧 **__Managing EP{episode_number:02d}__** for {anime_name} - Season {season_number}.\n\n🗓️ **Release Date**: {release_date}"
EPISODE_OPTIONS_WITH_FILES = "🔧 **__Managing EP{episode_number:02d}__** for {anime_name} - Season {season_number}.\n\n📥 **__Available Versions__**:" # List versions below
BUTTON_ADD_EPISODE_FILE = "➕ Add Episode File(s)"
BUTTON_ADD_RELEASE_DATE = "🗓️ Set Release Date"
BUTTON_REMOVE_EPISODE = "🗑️ Remove Episode {episode_number}"
PROMPT_RELEASE_DATE = "📅 Send the **__Release Date__** for EP{episode_number:02d} ({anime_name}) in DD/MM/YYYY format:"
RELEASE_DATE_SET_SUCCESS = "✅ Release date for EP{episode_number:02d} set to {release_date}."
INVALID_DATE_FORMAT = "🚫 Invalid date format. Please send in DD/MM/YYYY."

ADD_FILE_PROMPT = "📥 Send the **__Episode File__** (video or compressed) for EP{episode_number:02d} ({anime_name} - Season {season_number}):"
ADD_FILE_METADATA_PROMPT = "💾 File received! Now send the details:\n\n📺 **Quality/Resolution** (e.g., 1080p, 720p):\n🎧 **Audio Languages** (comma-separated, e.g., Japanese, English):\n📝 **Subtitle Languages** (comma-separated, e.g., English, Spanish, None):" # Prompt for metadata after file

BUTTON_ADD_OTHER_VERSION = "➕ Add Another Version for EP{episode_number:02d}"
BUTTON_NEXT_EPISODE = "➡️ Go to Next Episode ({next_episode_number:02d})"
BUTTON_DELETE_FILE_VERSION = "🗑️ Delete This File Version"
FILE_ADDED_SUCCESS = "✅ File version added for EP{episode_number:02d} ({quality} - {audio}/{subs})!"
FILE_DELETED_SUCCESS = "🗑️ File version deleted successfully."


# --- Admin Utility Handlers ---
BROADCAST_PROMPT = "📢 Send the **__message__** you want to broadcast to all users:"
BROADCAST_CONFIRM = "✅ Your message has been added to the broadcast queue and will be sent shortly."
DATA_DELETION_PROMPT = "💀 **__DANGER: PERMANENT DATA LOSS__** 💀\n\nAre you absolutely sure you want to delete ALL bot data (users, anime, requests, tokens)?\n\n**THIS CANNOT BE UNDONE.**\n\nType `YES I AM SURE DELETE EVERYTHING` to confirm."
DATA_DELETION_CONFIRMED = "💥 ALL BOT DATA IS BEING PERMANENTLY DELETED. This may take some time. The bot may restart."
DATA_DELETION_CANCELLED = "😌 Data deletion cancelled."
DATA_DELETION_WRONG_CONFIRMATION = "❌ Incorrect confirmation phrase. Data deletion cancelled."

ADMIN_ADD_TOKENS_PROMPT = "➕ Send the Telegram **__User ID__** of the user to add tokens to:"
ADMIN_ADD_TOKENS_AMOUNT_PROMPT = "🔢 How many **__tokens__** do you want to add to user ID {user_id}? (Send a number):"
ADMIN_TOKENS_ADDED_SUCCESS = "✅ Successfully added **{amount}** tokens to user ID {user_id}. New balance: {new_balance}."
ADMIN_REMOVE_TOKENS_PROMPT = "➖ Send the Telegram **__User ID__** of the user to remove tokens from:"
ADMIN_REMOVE_TOKENS_AMOUNT_PROMPT = "🔢 How many **__tokens__** do you want to remove from user ID {user_id}? (Send a number):"
ADMIN_TOKENS_REMOVED_SUCCESS = "✅ Successfully removed **{amount}** tokens from user ID {user_id}. New balance: {new_balance}."
ADMIN_TOKENS_ERROR = "💔 Error updating tokens for user ID {user_id}."

# --- Leaderboard ---
LEADERBOARD_TITLE = "🏆 __**Top Downloaders**__ 🏆"
LEADERBOARD_EMPTY = "The leaderboard is currently empty. Start downloading to see your name here! 😉"
LEADERBOARD_ENTRY_FORMAT = "#{rank}. [{user_name}](tg://user?id={user_id}) - {download_count} Downloads" # Use markdown for link

# --- Latest/Popular ---
LATEST_TITLE = "🆕 __**Latest Episodes Added**__ 👇"
POPULAR_TITLE = "🔥 __**Most Popular Anime**__ 👇"
NO_CONTENT_YET = "😞 No content added yet! Check back later or use the search."

# --- Inline Mode ---
# If implementing inline search
INLINE_SEARCH_PLACEHOLDER = "Type anime name to search..."
# Message for empty inline results
INLINE_NO_RESULTS = "😔 No anime found matching your query."


# --- Utility Texts ---
LOADING_ANIMATION = "🔄 Processing..."
CANCEL_ACTION = "❌ Cancel"
ACTION_CANCELLED = "❌ Action cancelled."
INPUT_TIMEOUT = "⏳ Input timed out. Please try again."

# --- Placeholder/Under Construction ---
FEATURE_UNDER_CONSTRUCTION = "👷 This feature is currently under construction and not available yet. Please check back later!"

# --- Data Formatting ---
FILE_SIZE_FORMAT_MB = "{size:.2f} MB"
FILE_SIZE_FORMAT_GB = "{size:.2f} GB"
