import httpx
import config
import logging

LOGGER = logging.getLogger(__name__)

async def shorten_link(long_url: str) -> str | None:
    if not config.SHORTENER_API_URL or not config.SHORTENER_API_KEY:
        LOGGER.warning("Shortener API URL or Key not configured.")
        return long_url # Fallback to long URL if not configured

    api_url = config.SHORTENER_API_URL
    params = {
        'api': config.SHORTENER_API_KEY,
        'url': long_url
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, params=params, timeout=10)
            response.raise_for_status() # Raise an exception for HTTP errors
            
            data = response.json()
            # linkshortify.com specific response structure (adjust if different)
            if data.get("status") == "success" and data.get("shortenedUrl"):
                short_url = data["shortenedUrl"]
                LOGGER.info(f"Shortened {long_url} to {short_url}")
                return short_url
            else:
                LOGGER.error(f"Failed to shorten link {long_url}. API Response: {data}")
                return None
    except httpx.RequestError as e:
        LOGGER.error(f"HTTP request to shortener failed: {e}")
        return None
    except Exception as e:
        LOGGER.error(f"Error during link shortening: {e}")
        return None
