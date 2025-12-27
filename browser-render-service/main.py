# browser-render-service/main.py
"""
Browser Render Service using Playwright.

This service renders JavaScript-heavy pages (like photo galleries with infinite scroll)
and returns the fully rendered HTML. Secured via X-API-Key header.

Endpoints:
    GET /render?url=<target_url>&scrolls=<num_scrolls>
    GET /health - Health check endpoint (no auth)
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Header, Query
from playwright.async_api import async_playwright
from google.cloud import secretmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Browser Render Service",
    description="Renders JavaScript-heavy pages using Playwright",
    version="1.0.0"
)

# Environment Configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
API_KEY_SECRET_ID = os.getenv('API_KEY_SECRET_ID', 'BROWSER_SERVICE_API_KEY')

# Default configuration
DEFAULT_SCROLL_COUNT = 5
DEFAULT_SCROLL_WAIT_MS = 1500
DEFAULT_TIMEOUT_MS = 60000

# Initialize Secret Manager client
if ENVIRONMENT != 'local':
    secret_client = secretmanager.SecretManagerServiceClient()
else:
    secret_client = None

# In-memory cache with TTL
CACHE: Dict[str, Dict[str, Any]] = {}
CONFIG_CACHE_TTL_SECONDS = 5 * 60  # 5 minutes


def access_secret(secret_id: str, version_id: str = "latest") -> str:
    """Access a secret from Google Cloud Secret Manager."""
    if ENVIRONMENT == 'local':
        return os.getenv(secret_id, '').strip()

    try:
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Error accessing secret {secret_id}: {e}")
        return ''


def validate_api_key(api_key: str) -> bool:
    """Validate the API key from request headers."""
    if not api_key:
        return False

    # Check cache first to avoid Secret Manager calls on every request
    cache_key = 'api_key'
    cached = CACHE.get(cache_key)

    if cached and (datetime.now().timestamp() - cached['timestamp'] < CONFIG_CACHE_TTL_SECONDS):
        expected_key = cached['data']
    else:
        expected_key = access_secret(API_KEY_SECRET_ID)
        if expected_key:
            CACHE[cache_key] = {'data': expected_key, 'timestamp': datetime.now().timestamp()}

    if not expected_key:
        logger.error("Could not retrieve API key from Secret Manager")
        return False

    return api_key == expected_key


@app.get("/")
async def root():
    """Root endpoint - returns 403 Forbidden."""
    raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run (no auth required)."""
    return {"status": "healthy", "service": "browser-render-service"}


@app.get("/render")
async def render(
    url: str = Query(..., description="The URL to render"),
    scrolls: int = Query(DEFAULT_SCROLL_COUNT, description="Number of scroll iterations"),
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """
    Render a URL with JavaScript execution and infinite scroll handling.

    Args:
        url: Target URL to render
        scrolls: Number of times to scroll down (default: 5)
        x_api_key: API key for authentication (REQUIRED)

    Returns:
        JSON with rendered HTML content
    """
    # Authentication check (MANDATORY)
    if not validate_api_key(x_api_key):
        logger.warning("Invalid or missing API key for URL: %s", url)
        raise HTTPException(status_code=403, detail="Forbidden")

    logger.info("Rendering URL: %s (scrolls=%d)", url, scrolls)

    async with async_playwright() as p:
        browser = None
        try:
            # Launch browser with sandbox disabled (required for Docker/Cloud Run)
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])

            # Create context with realistic user agent to avoid bot detection
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()

            # Navigate to URL
            await page.goto(url, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
            logger.info("Page loaded: %s", url)

            # --- INFINITE SCROLL LOGIC ---
            # Scroll down multiple times, waiting between each to trigger AJAX content loading
            for i in range(scrolls):
                await page.mouse.wheel(0, 2000)
                await page.wait_for_timeout(DEFAULT_SCROLL_WAIT_MS)
                logger.debug("Scroll %d/%d completed", i + 1, scrolls)

            # Final wait for any remaining content to load
            await page.wait_for_timeout(1000)

            # Get the fully rendered HTML
            content = await page.content()

            logger.info("Successfully rendered %s (content length: %d)", url, len(content))
            return {"html": content, "url": url, "scrolls": scrolls}

        except Exception as e:
            logger.error("Error rendering %s: %s", url, str(e))
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            if browser:
                await browser.close()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting Browser Render Service on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
