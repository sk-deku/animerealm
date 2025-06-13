# AnimeRealm

AnimeRealm is an advanced Telegram bot designed for browsing, searching, and downloading anime. It features a sophisticated admin content management system, a token-based download model for users, premium membership benefits, and a highly interactive user interface.

## Features

*   Browsing and searching a vast anime library
*   Intelligent search using fuzzy matching
*   Token-based download system
*   Premium memberships for unlimited downloads and requests
*   Personalized user profiles and watchlists
*   Notifications for new episodes on the watchlist
*   Comprehensive admin panel for content and user management
*   Configurable through environment variables

## Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/anime-realm-bot.git
    cd anime-realm-bot
    ```

2.  **Set up Environment Variables:**
    Create a `.env` file in the project root based on the `.env.example`.
    ```env
    BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
    MONGO_URI=YOUR_MONGODB_CONNECTION_STRING
    ADMIN_IDS=COMMA,SEPARATED,ADMIN,USER,IDS
    OWNER_ID=YOUR_TELEGRAM_USER_ID
    LOG_CHANNEL_ID=YOUR_TELEGRAM_LOG_CHANNEL_ID
    FILE_STORAGE_CHANNEL_ID=YOUR_TELEGRAM_FILE_STORAGE_CHANNEL_ID

    # Optional: If using a shortener API
    # SHORTENER_API_KEY=YOUR_SHORTENER_API_KEY
    # SHORTENER_SITE_URL=YOUR_SHORTENER_SITE_URL # e.g., api.example.com (without https://)
    # TOKENS_PER_REDEEM=1
    # TOKEN_LINK_EXPIRY_HOURS=1

    # Optional: If you need to specify the listening port explicitly
    # PORT=8080
    ```
    **Replace placeholder values with your actual credentials and settings.**

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up MongoDB:**
    Ensure your MongoDB database is running and accessible via the `MONGO_URI`.

5.  **Running the bot:**
    ```bash
    python main.py
    ```
    *(Note: For production deployment with Docker/Koyeb, refer to their documentation and the provided `Dockerfile` and `Procfile`)*

## Deployment on Koyeb

*   Connect your GitHub repository to Koyeb.
*   Configure deployment settings to use the `Dockerfile` and `Procfile`.
*   Ensure you configure the required environment variables within the Koyeb dashboard.
*   The basic health check is set up on port 8080 by serving the `healthz` file using the `release` process in the Procfile.

## Admin & User Commands

*(To be filled as commands are implemented)*

## Contributing

*(Placeholder - details on how to contribute)*

## License

This project is licensed under the MIT License - see the LICENSE file for details.
