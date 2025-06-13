# AnimeRealm

AnimeRealm is an advanced Telegram bot meticulously designed for browsing, searching, and downloading anime content. It empowers administrators with a comprehensive content management system and provides users with a feature-rich experience including a token-based download model, premium memberships, watchlists, and a dynamic interface.

## ✨ Features

*   🎬 **Vast Anime Library:** Seamlessly browse and search a large collection of anime.
*   🔍 **Intelligent Search:** Find anime easily even with slight typos using fuzzy matching.
*   📚 **Categorized Browsing:** Explore anime by genres, release year, status (Ongoing, Completed, Movie, OVA).
*   📥 **Token-Based Downloads:** Earn free download tokens by interacting with token generation links.
*   💎 **Premium Membership:** Unlock unlimited downloads and exclusive features.
*   👤 **Personal Profile:** Monitor token balance, premium status, download history, and manage your watchlist.
*   ❤️ **Watchlist & Notifications:** Add your favorite anime to a watchlist and get notified of new episodes/versions.
*   📝 **Anime Request System:** Request anime titles directly (premium users have dedicated access).
*   📊 **Discovery:** See Leaderboard of top downloaders and browse Latest additions and Popular anime.
*   🛠️ **Robust Admin Panel:**
    *   Add and manage anime details (Name, Poster, Synopsis, Genres, Year, Status).
    *   Organize content into Seasons and Episodes.
    *   Add multiple file versions (Qualities, Audio, Subtitles) to episodes.
    *   Set episode release dates.
    *   Manage user tokens manually.
    *   Broadcast messages to all users.
*   🗄️ **Database:** Efficiently stores all data using MongoDB.
*   🚀 **Deployment Ready:** Includes `Dockerfile` and `Procfile` for easy deployment (e.g., on Koyeb).
*   ✅ **Interactive Interface:** Uses inline keyboards, auto-editing messages, and rich formatting.

## ⚙️ Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/anime-realm-bot.git
    cd anime-realm-bot
    ```

2.  **Set up Environment Variables:**
    Create a `.env` file in the project root based on the `.env.example`. **Crucially, get your API ID and API Hash from https://my.telegram.org/ for Pyrogram.**

    ```env
    BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
    API_ID=YOUR_TELEGRAM_API_ID # Get from https://my.telegram.org/
    API_HASH=YOUR_TELEGRAM_API_HASH # Get from https://my.telegram.org/
    MONGO_URI=YOUR_MONGODB_CONNECTION_STRING

    # Admin user IDs (comma separated string of integers)
    ADMIN_IDS=123456,789012,345678
    # Bot owner ID (single integer ID for super-sensitive commands like /delete_all_data)
    OWNER_ID=123456

    # Telegram Channel IDs where bot must be an admin (integers)
    # LOG_CHANNEL_ID: Channel for admin logs and notifications
    # FILE_STORAGE_CHANNEL_ID: Private channel where the bot forwards and stores episode files to get file_ids
    LOG_CHANNEL_ID=-1001234567890
    FILE_STORAGE_CHANNEL_ID=-1009876543210

    # Optional: URL Shortener Configuration (Required for Token Earning)
    # Example uses a hypothetical API structure. Replace with your chosen service details.
    # REQUIRES you to adapt the `shorten_url` function in `handlers/tokens_handler.py`
    SHORTENER_API_KEY=YOUR_SHORTENER_API_KEY
    SHORTENER_SITE_URL=YOUR_SHORTENER_API_BASE_URL # e.g., "api.example.com"
    # Example: For cutco.de, SHORTENER_ENDPOINT might be "https://{shortener_site_url}/api?api={api_key}&url={long_url}"
    SHORTENER_ENDPOINT="https://{shortener_site_url}/api?key={api_key}&url={long_url}" # **UPDATE THIS FORMAT FOR YOUR API**
    TOKENS_PER_REDEEM=1 # Tokens earned by the generator for a single link completion
    TOKEN_LINK_EXPIRY_HOURS=1 # Link validity period

    # Optional: How to Earn Tutorial Link (If not using text tutorial)
    # HOW_TO_EARN_TUTORIAL_LINK="https://telegra.ph/your_tutorial_video_or_article"

    # Optional: Configure specific thresholds/limits
    # FUZZYWUZZY_THRESHOLD=70 # Search similarity score (0-100)
    # PAGE_SIZE=15 # Items per page in lists
    # LATEST_COUNT=15 # Items in Latest list
    # POPULAR_COUNT=10 # Items in Popular list
    # LEADERBOARD_COUNT=10 # Items in Leaderboard
    # REQUEST_TOKEN_COST=5 # Tokens a free user spends on a request

    # Optional: Preset values (can modify in config.py or load from DB/file if more dynamic needed)
    # See config.py for examples: QUALITY_PRESETS, AUDIO_LANGUAGES_PRESETS, SUBTITLE_LANGUAGES_PRESETS, INITIAL_GENRES, ANIME_STATUSES
    # MAX_BUTTONS_PER_ROW=4
    ```
    **Replace placeholder values (`YOUR_...`) with your actual credentials and settings.**

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up MongoDB:**
    Ensure your MongoDB database is running and accessible via the `MONGO_URI`. The bot will automatically create necessary collections and indices on startup.

5.  **Running the bot locally:**
    ```bash
    python main.py
    ```

6.  **Deployment on Koyeb (or similar platforms):**
    *   Connect your GitHub repository to Koyeb.
    *   Configure the service to use the `Dockerfile`.
    *   Set the Build Command (often unnecessary if using Dockerfile).
    *   Set the Run Command as `python main.py` or rely on the `worker: python main.py` in `Procfile`.
    *   Crucially, configure the required environment variables within the Koyeb dashboard matching your `.env`.
    *   Ensure the health check is configured on port 8080, pointing to `/healthz` endpoint (as configured in `Procfile`).

## Commands

### 🌐 User Commands

*   `/start` - Start the bot and see the main menu.
*   `/help` - Get information about using the bot.
*   `/profile` - View your profile (tokens, premium, watchlist, downloads).
*   `/gen_token` - Generate a link to earn download tokens by completing a short step.
*   `/premium` - View premium membership options.
*   `/request <anime_name>` (Premium Only) - Directly request an anime to be added.
*   `/settings` (Not implemented fully) - Access user settings (like notification preferences).
*   Sending a plain text message - Attempts to search for anime (when not in a multi-step state).

### 🛠️ Admin Commands (Requires User ID in `ADMIN_IDS`)

*   `/manage_content` - Access the administrative menu for managing anime content.
*   `/add_tokens <user_id> <amount>` - Manually add download tokens to a user's account.
*   `/remove_tokens <user_id> <amount>` - Manually remove download tokens from a user's account.
*   `/broadcast <message>` - Send a message to all bot users.
*   `/delete_all_data` (Owner Only, Use with Extreme Caution) - **PERMANENTLY DELETES ALL BOT DATA.**

## 📚 Documentation

*(Placeholder - more detailed docs could go here)*

## Contributing

Contributions are welcome! Please follow these steps:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix.
3.  Make your changes.
4.  Test thoroughly.
5.  Commit your changes with clear messages.
6.  Push your branch and open a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

*(Optional - thank contributors, libraries, etc.)*
