"""
GCS API Cloud Function

Unified API middleware between UI and GCS.
Serves: articles, user preferences, config, and triggers for scraper/news-api.

Endpoints:
  GET  /articles              - Fetch enriched articles
  GET  /user                  - Get user info
  GET  /user/preferences      - Get user preferences
  PUT  /user/preferences      - Save user preferences
  GET  /config/news-api       - Get news API config
  GET  /config/allowed-users  - Get allowed users (admin only)
  GET  /config/admin-users    - Get current user's admin status
  POST /trigger/scraper       - Trigger scraper via Pub/Sub
  POST /trigger/news-api      - Trigger news API fetcher via Pub/Sub
"""

import os
import sys
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import functions_framework
from flask import Request, jsonify

from google.cloud import storage, secretmanager, pubsub_v1
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

# Environment Configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
API_KEY_SECRET_ID = os.getenv('API_KEY_SECRET_ID', 'ARTICLE_API_KEY')
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')

# GCS Paths
CONFIG_FOLDER = 'config/'
USER_PREFERENCES_FOLDER = 'config/user_preferences/'

# Pub/Sub Topics
SCRAPING_TOPIC = os.getenv('SCRAPING_REQUEST_TOPIC', 'scraping-requests')
NEWS_API_TOPIC = os.getenv('NEWS_API_REQUEST_TOPIC', 'news-api-requests')

# Fallback allowed emails
FALLBACK_ALLOWED_EMAILS = ['oktay.burak.ertas@gmail.com']

# Initialize Clients
if ENVIRONMENT != 'local':
    storage_client = storage.Client()
    secret_client = secretmanager.SecretManagerServiceClient()
    pubsub_client = pubsub_v1.PublisherClient()
else:
    storage_client = None
    secret_client = None
    pubsub_client = None

# In-memory cache with TTL
CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 10 * 60  # 10 minutes
CONFIG_CACHE_TTL_SECONDS = 5 * 60  # 5 minutes


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def hash_email(email: str) -> str:
    """Generate SHA256 hash of email (first 16 chars)."""
    return hashlib.sha256(email.lower().encode()).hexdigest()[:16]


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


def validate_api_key(request: Request) -> bool:
    """Validate the API key from request headers."""
    api_key = request.headers.get('X-API-Key')
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


def verify_google_token(request: Request) -> Optional[Dict[str, Any]]:
    """Verify Google OAuth token and return user info."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:]  # Remove 'Bearer ' prefix
    
    try:
        # Verify the token
        idinfo = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        return {
            'email': idinfo.get('email'),
            'name': idinfo.get('name'),
            'picture': idinfo.get('picture'),
        }
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return None


def load_allowed_users() -> List[str]:
    """Load allowed users from GCS config."""
    cache_key = 'allowed_users'
    cached = CACHE.get(cache_key)
    
    if cached and (datetime.now().timestamp() - cached['timestamp'] < CONFIG_CACHE_TTL_SECONDS):
        return cached['data']
    
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f'{CONFIG_FOLDER}allowed_users.json')
        
        if not blob.exists():
            return FALLBACK_ALLOWED_EMAILS
        
        content = json.loads(blob.download_as_text())
        users = content.get('allowed_users', FALLBACK_ALLOWED_EMAILS)
        
        CACHE[cache_key] = {'data': users, 'timestamp': datetime.now().timestamp()}
        return users
    except Exception as e:
        logger.error(f"Error loading allowed users: {e}")
        return FALLBACK_ALLOWED_EMAILS


def load_admin_users() -> List[str]:
    """Load admin users from GCS config."""
    cache_key = 'admin_users'
    cached = CACHE.get(cache_key)
    
    if cached and (datetime.now().timestamp() - cached['timestamp'] < CONFIG_CACHE_TTL_SECONDS):
        return cached['data']
    
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f'{CONFIG_FOLDER}admin_users.json')
        
        if not blob.exists():
            return []
        
        content = json.loads(blob.download_as_text())
        admins = content.get('admin_users', [])
        
        CACHE[cache_key] = {'data': admins, 'timestamp': datetime.now().timestamp()}
        return admins
    except Exception as e:
        logger.error(f"Error loading admin users: {e}")
        return []


def is_user_allowed(email: str) -> bool:
    """Check if user email is in allowed list."""
    allowed = load_allowed_users()
    return email in allowed


def is_user_admin(email: str) -> bool:
    """Check if user is an admin."""
    admins = load_admin_users()
    return email in admins


def cors_preflight_response():
    """Return CORS preflight response."""
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-API-Key, Authorization',
        'Access-Control-Max-Age': '3600'
    }
    return ('', 204, headers)


def cors_headers() -> Dict[str, str]:
    """Return CORS headers for responses."""
    return {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
    }


def json_response(data: Any, status: int = 200):
    """Create JSON response with CORS headers."""
    return (json.dumps(data, ensure_ascii=False), status, cors_headers())


def error_response(message: str, status: int = 400):
    """Create error response."""
    return json_response({'error': message}, status)


# =============================================================================
# ARTICLE FUNCTIONS
# =============================================================================

def get_cache_key(date: str) -> str:
    """Generate cache key for date."""
    return f"articles_{date}"


def get_cached_articles(date: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached articles if still valid."""
    cache_key = get_cache_key(date)
    entry = CACHE.get(cache_key)

    if not entry:
        return None

    if datetime.now().timestamp() - entry['timestamp'] >= CACHE_TTL_SECONDS:
        del CACHE[cache_key]
        return None

    return entry['articles']


def set_cached_articles(date: str, articles: List[Dict[str, Any]]) -> None:
    """Cache articles with timestamp."""
    cache_key = get_cache_key(date)
    CACHE[cache_key] = {
        'articles': articles,
        'timestamp': datetime.now().timestamp()
    }


def get_date_range(start_date: str, end_date: str) -> List[str]:
    """Generate list of dates between start and end (inclusive)."""
    dates = []
    current = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    return dates


def normalize_article(article: Dict[str, Any], content_map: Dict[str, str] = None) -> Dict[str, Any]:
    """Normalize article to consistent schema."""
    article_id = article.get('article_id')
    
    content = article.get('body') or article.get('content') or ''
    if content_map and article_id and article_id in content_map:
        content = content_map[article_id]
    
    return {
        'article_id': article_id,
        'original_url': article.get('original_url'),
        'merged_from_urls': article.get('merged_from_urls'),
        'title': article.get('title'),
        'summary': article.get('summary'),
        'content': content,
        'source': article.get('source'),
        'publish_date': article.get('publish_date'),
        'categories': article.get('categories', []),
        'key_entities': article.get('key_entities', {}),
        'content_quality': article.get('content_quality', 'medium'),
        'confidence': article.get('confidence', 0.8),
        'language': article.get('language'),
        'region': article.get('region'),
        'summary_translation': article.get('summary_translation'),
        'x_post': article.get('x_post'),
        'source_type': article.get('source_type', 'scraped'),
        'keywords_used': article.get('keywords_used', [])  # For UI keyword highlighting
    }


def load_content_map(date: str) -> Dict[str, str]:
    """Load article content from batch input files."""
    content_map = {}
    
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        date_prefix = f"ingestion/{date}/"
        all_blobs = list(bucket.list_blobs(prefix=date_prefix))
        
        input_files = [
            b for b in all_blobs
            if '/batch_enrichment/' in b.name
            and '/input/' in b.name
            and b.name.endswith('.json')
        ]
        
        for blob in input_files:
            try:
                data = json.loads(blob.download_as_text())
                articles = data.get('articles', [])
                
                for article in articles:
                    article_id = article.get('article_id')
                    body = article.get('body') or article.get('content') or ''
                    if article_id and body:
                        content_map[article_id] = body
                        
            except Exception as e:
                logger.error(f"Error loading content from {blob.name}: {e}")
                
    except Exception as e:
        logger.error(f"Error loading content map for {date}: {e}")
    
    return content_map


def fetch_articles_for_date(date: str) -> List[Dict[str, Any]]:
    """Fetch enriched articles from GCS for a specific date."""
    articles = []
    prefix = f"ingestion/{date}/"

    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=prefix))
        content_map = load_content_map(date)

        enriched_files = [
            b for b in blobs
            if 'enriched_' in b.name and b.name.endswith('_articles.json')
        ]

        for blob in enriched_files:
            try:
                content = blob.download_as_text()
                data = json.loads(content)

                article_list = []
                if isinstance(data, list):
                    article_list = data
                elif isinstance(data, dict):
                    if 'processed_articles' in data:
                        article_list = data['processed_articles']
                    elif 'articles' in data:
                        article_list = data['articles']

                for article in article_list:
                    articles.append(normalize_article(article, content_map))

            except Exception as e:
                logger.error(f"Error processing {blob.name}: {e}")

    except Exception as e:
        logger.error(f"Error fetching files for {date}: {e}")

    return articles


def deduplicate_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate articles by URL."""
    seen_urls = set()
    unique = []

    for article in articles:
        url = article.get('original_url') or article.get('article_id')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(article)

    return unique


# =============================================================================
# ROUTE HANDLERS
# =============================================================================

def handle_get_articles(request: Request):
    """GET /articles - Fetch enriched articles."""
    # Validate API key
    if not validate_api_key(request):
        return error_response('Invalid or missing API key', 401)

    region = request.args.get('region', 'all')

    # Route diff region to dedicated handler
    if region == 'diff':
        return handle_get_diff(request)
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    last_n_days = request.args.get('last_n_days', type=int)
    search = request.args.get('search', '')
    no_cache = request.args.get('no_cache', 'false').lower() == 'true'

    # Determine dates
    if start_date and end_date:
        dates_to_fetch = get_date_range(start_date, end_date)
    elif last_n_days and last_n_days > 0:
        end = datetime.now()
        start = end - timedelta(days=last_n_days - 1)
        dates_to_fetch = get_date_range(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
    else:
        dates_to_fetch = [datetime.now().strftime('%Y-%m-%d')]

    all_articles = []
    for date in dates_to_fetch:
        cached = get_cached_articles(date)
        if cached is not None and not no_cache:
            all_articles.extend(cached)
        else:
            date_articles = fetch_articles_for_date(date)
            set_cached_articles(date, date_articles)
            all_articles.extend(date_articles)

    unique_articles = deduplicate_articles(all_articles)

    if region and region != 'all':
        unique_articles = [a for a in unique_articles if a.get('region') == region]

    if search:
        search_lower = search.lower()
        unique_articles = [
            a for a in unique_articles
            if search_lower in (a.get('title', '') or '').lower()
            or search_lower in (a.get('summary', '') or '').lower()
        ]

    return json_response(unique_articles)


def handle_get_diff(request: Request):
    """GET /articles?region=diff - Fetch region diff analysis files."""
    # Validate API key
    if not validate_api_key(request):
        return error_response('Invalid or missing API key', 401)

    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    last_n_days = request.args.get('last_n_days', type=int)

    # Determine dates
    if start_date and end_date:
        dates_to_fetch = get_date_range(start_date, end_date)
    elif last_n_days and last_n_days > 0:
        end = datetime.now()
        start = end - timedelta(days=last_n_days - 1)
        dates_to_fetch = get_date_range(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
    else:
        dates_to_fetch = [datetime.now().strftime('%Y-%m-%d')]

    logger.info(f"[DIFF] Fetching diff files for dates: {dates_to_fetch}")

    # Aggregate results
    all_diff_results = {
        'metadata': {
            'region1': 'eu',
            'region2': 'tr',
            'dates': dates_to_fetch,
            'generated_at': datetime.now().isoformat()
        },
        'summary': {
            'total_region1_articles': 0,
            'total_region2_articles': 0,
            'unique_to_region1': 0
        },
        'unique_articles': []
    }

    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)

        for date in dates_to_fetch:
            diff_prefix = f"ingestion/{date}/"
            logger.info(f"[DIFF] Searching for diff files: {diff_prefix}")

            blobs = list(bucket.list_blobs(prefix=diff_prefix))

            # Find region_diff files in analysis folders
            diff_files = [
                b for b in blobs
                if '/analysis/region_diff_' in b.name and b.name.endswith('.json')
            ]

            logger.info(f"[DIFF] Found {len(diff_files)} diff files for {date}")

            for blob in diff_files:
                try:
                    content = blob.download_as_text()
                    diff_data = json.loads(content)

                    # Aggregate summaries
                    if diff_data.get('summary'):
                        all_diff_results['summary']['total_region1_articles'] += diff_data['summary'].get('total_region1_articles', 0)
                        all_diff_results['summary']['total_region2_articles'] += diff_data['summary'].get('total_region2_articles', 0)
                        all_diff_results['summary']['unique_to_region1'] += diff_data['summary'].get('unique_to_region1', 0)

                    # Collect unique articles
                    if diff_data.get('unique_articles'):
                        all_diff_results['unique_articles'].extend(diff_data['unique_articles'])

                    logger.info(f"[DIFF] Loaded {len(diff_data.get('unique_articles', []))} articles from {blob.name}")

                except Exception as e:
                    logger.error(f"[DIFF] Error processing {blob.name}: {e}")

        # Deduplicate by article_id
        seen_ids = set()
        unique_articles = []
        for article in all_diff_results['unique_articles']:
            article_id = article.get('article_id')
            if article_id and article_id not in seen_ids:
                seen_ids.add(article_id)
                unique_articles.append(article)

        all_diff_results['unique_articles'] = unique_articles

        logger.info(f"[DIFF] Total unique articles: {len(unique_articles)}")

        # Transform to NewsEntry-compatible format for UI
        news_entries = []
        for article in unique_articles:
            closest_match_info = ''
            if article.get('closest_match'):
                closest_title = article['closest_match'].get('title', '')[:50]
                closest_match_info = f' Closest TR: "{closest_title}..."'

            entry = {
                'article_id': article.get('article_id', ''),
                'original_url': article.get('original_url', ''),
                'title': article.get('title', ''),
                'summary': f"[EU-only, similarity: {int(article.get('max_similarity', 0) * 100)}%]{closest_match_info}",
                'source': article.get('source', ''),
                'publish_date': article.get('publish_date', ''),
                'categories': [],
                'key_entities': {'teams': [], 'players': [], 'amounts': [], 'dates': [], 'competitions': [], 'locations': []},
                'content_quality': 'medium',
                'confidence': 1 - article.get('max_similarity', 0),
                'language': article.get('language', 'en'),  # Preserve original language
                'region': 'diff',  # Keep for routing
                'source_type': article.get('source_type', 'scraped'),  # Preserve original source_type
                '_diff_metadata': {
                    'max_similarity': article.get('max_similarity', 0),
                    'closest_match': article.get('closest_match'),
                    'closest_match_url': article.get('closest_match_url', ''),
                    'original_region': article.get('original_region', 'eu')
                }
            }
            news_entries.append(entry)

        return json_response(news_entries)

    except Exception as e:
        logger.error(f"[DIFF] Error: {e}")
        return error_response(f'Failed to fetch diff data: {str(e)}', 500)


def handle_get_user(request: Request):
    """GET /user - Get user info."""
    user = verify_google_token(request)
    if not user:
        return error_response('Invalid or missing token', 401)
    
    if not is_user_allowed(user['email']):
        return error_response('User not allowed', 403)
    
    user['isAdmin'] = is_user_admin(user['email'])
    return json_response(user)


def handle_get_preferences(request: Request):
    """GET /user/preferences - Get user preferences."""
    user = verify_google_token(request)
    if not user:
        return error_response('Invalid or missing token', 401)
    
    email_hash = hash_email(user['email'])
    
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f'{USER_PREFERENCES_FOLDER}{email_hash}/preferences.json')
        
        if not blob.exists():
            return json_response({
                'email': user['email'],
                'scraperConfig': None,
                'feedSettings': {'defaultRegion': 'tr', 'autoRefresh': False},
                'createdAt': None,
                'lastUpdated': None
            })
        
        content = json.loads(blob.download_as_text())
        return json_response(content)
    except Exception as e:
        logger.error(f"Error loading preferences: {e}")
        return error_response(str(e), 500)


def handle_put_preferences(request: Request):
    """PUT /user/preferences - Save user preferences."""
    user = verify_google_token(request)
    if not user:
        return error_response('Invalid or missing token', 401)
    
    email_hash = hash_email(user['email'])
    
    try:
        data = request.get_json() or {}
        
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f'{USER_PREFERENCES_FOLDER}{email_hash}/preferences.json')
        
        # Load existing if available
        existing = {'version': 0}
        if blob.exists():
            existing = json.loads(blob.download_as_text())
        
        preferences = {
            'email': user['email'],
            'scraperConfig': data.get('scraperConfig', existing.get('scraperConfig')),
            'feedSettings': data.get('feedSettings', existing.get('feedSettings')),
            'createdAt': existing.get('createdAt') or datetime.now().isoformat(),
            'lastUpdated': datetime.now().isoformat(),
            'version': existing.get('version', 0) + 1
        }
        
        blob.upload_from_string(
            json.dumps(preferences, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        
        return json_response(preferences)
    except Exception as e:
        logger.error(f"Error saving preferences: {e}")
        return error_response(str(e), 500)


def handle_get_news_api_config(request: Request):
    """GET /config/news-api - Get news API config."""
    user = verify_google_token(request)
    if not user:
        return error_response('Invalid or missing token', 401)
    
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f'{CONFIG_FOLDER}news_api_config.json')
        
        if not blob.exists():
            return json_response({
                'default_keywords': ['fenerbahce', 'galatasaray', 'tedesco'],
                'default_time_range': 'last_24_hours',
                'default_max_results': 100,
                'available_time_ranges': ['last_24_hours', 'last_7_days', 'last_30_days']
            })
        
        content = json.loads(blob.download_as_text())
        return json_response(content)
    except Exception as e:
        logger.error(f"Error loading news API config: {e}")
        return error_response(str(e), 500)


def handle_get_allowed_users(request: Request):
    """GET /config/allowed-users - Get list of allowed users (admin only)."""
    user = verify_google_token(request)
    if not user:
        return error_response('Invalid or missing token', 401)

    if not is_user_admin(user['email']):
        return error_response('Admin access required', 403)

    allowed_users = load_allowed_users()
    return json_response({'allowed_users': allowed_users})


def handle_get_admin_status(request: Request):
    """GET /config/admin-users - Get current user's admin status."""
    user = verify_google_token(request)
    if not user:
        return error_response('Invalid or missing token', 401)

    return json_response({
        'email': user['email'],
        'isAdmin': is_user_admin(user['email'])
    })


def handle_trigger_scraper(request: Request):
    """POST /trigger/scraper - Trigger scraper via Pub/Sub."""
    user = verify_google_token(request)
    if not user:
        return error_response('Invalid or missing token', 401)

    try:
        data = request.get_json() or {}

        # Validate required fields (scraper requires urls, keywords, and region)
        if not data.get('urls'):
            return error_response('Missing urls', 400)
        if not data.get('keywords'):
            return error_response('Missing keywords', 400)
        if not data.get('region'):
            return error_response('Missing region', 400)

        payload = {
            'urls': data['urls'],
            'keywords': data['keywords'],
            'region': data['region'],
            'scrape_depth': data.get('scrape_depth', 1),
            'persist': data.get('persist', True),
            'triggered_by': user['email']
        }
        
        topic_path = pubsub_client.topic_path(PROJECT_ID, SCRAPING_TOPIC)
        message = json.dumps(payload).encode('utf-8')
        future = pubsub_client.publish(topic_path, message)
        message_id = future.result()
        
        logger.info(f"Scraper triggered by {user['email']}: {message_id}")
        
        return json_response({
            'success': True,
            'messageId': message_id,
            'region': payload['region'],
            'sourcesCount': len(payload['urls']),
            'triggeredBy': user['email']
        })
    except Exception as e:
        logger.error(f"Error triggering scraper: {e}")
        return error_response(str(e), 500)


def handle_trigger_news_api(request: Request):
    """POST /trigger/news-api - Trigger news API fetcher via Pub/Sub."""
    user = verify_google_token(request)
    if not user:
        return error_response('Invalid or missing token', 401)
    
    try:
        data = request.get_json() or {}
        
        payload = {
            'keywords': data.get('keywords', ['fenerbahce', 'galatasaray', 'tedesco']),
            'time_range': data.get('time_range', 'last_24_hours'),
            'max_results': data.get('max_results', 50),
            'triggered_by': user['email']
        }
        
        topic_path = pubsub_client.topic_path(PROJECT_ID, NEWS_API_TOPIC)
        message = json.dumps(payload).encode('utf-8')
        future = pubsub_client.publish(topic_path, message)
        message_id = future.result()
        
        logger.info(f"News API triggered by {user['email']}: {message_id}")
        
        return json_response({
            'success': True,
            'messageId': message_id,
            'keywords': payload['keywords'],
            'triggeredBy': user['email']
        })
    except Exception as e:
        logger.error(f"Error triggering news API: {e}")
        return error_response(str(e), 500)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

@functions_framework.http
def main(request: Request):
    """HTTP Cloud Function entry point - routes requests to handlers."""

    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return cors_preflight_response()

    # Get path from request
    path = request.path.rstrip('/')
    method = request.method

    logger.info(f"{method} {path}")

    # Route to appropriate handler
    if path == '/articles' or path == '' or path == '/':
        if method == 'GET':
            return handle_get_articles(request)
    
    elif path == '/user':
        if method == 'GET':
            return handle_get_user(request)
    
    elif path == '/user/preferences':
        if method == 'GET':
            return handle_get_preferences(request)
        elif method == 'PUT':
            return handle_put_preferences(request)
    
    elif path == '/config/news-api':
        if method == 'GET':
            return handle_get_news_api_config(request)

    elif path == '/config/allowed-users':
        if method == 'GET':
            return handle_get_allowed_users(request)

    elif path == '/config/admin-users':
        if method == 'GET':
            return handle_get_admin_status(request)

    elif path == '/trigger/scraper':
        if method == 'POST':
            return handle_trigger_scraper(request)
    
    elif path == '/trigger/news-api':
        if method == 'POST':
            return handle_trigger_news_api(request)

    return error_response(f'Not found: {method} {path}', 404)


# =============================================================================
# LOCAL TESTING
# =============================================================================

if __name__ == "__main__":
    ENVIRONMENT = 'local'
    print("Local testing mode - use functions-framework for proper testing")
