"""
Source Discoverer Cloud Function

Discovers new news sources from API-fetched articles and tracks them
for potential addition to the scraper configuration.

Triggered by: Pub/Sub topic 'source-discovery'
Input: run_path reference to complete_articles.json and to_scrape.json
Output: Appends new FQDNs to config/discovered_sources.json
"""

import os
import sys
import json
import base64
import logging
from datetime import datetime, timezone
from typing import Set, List, Dict, Any, Optional
from urllib.parse import urlparse

from google.cloud import storage

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

# GCS Paths
USER_PREFERENCES_PREFIX = 'config/user_preferences/'
DISCOVERED_SOURCES_PATH = 'config/discovered_sources.json'

# Initialize clients
if ENVIRONMENT != 'local':
    storage_client = storage.Client()
else:
    storage_client = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")


def extract_fqdn(url: str) -> Optional[str]:
    """
    Extract FQDN from URL, removing path and www prefix.

    Examples:
        "https://www.sport1.de/channel/transfermarkt" → "sport1.de"
        "https://allnigeriasoccer.com/article" → "allnigeriasoccer.com"
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        fqdn = parsed.netloc.lower()

        # Remove www. prefix
        if fqdn.startswith('www.'):
            fqdn = fqdn[4:]

        # Skip empty or invalid FQDNs
        if not fqdn or '.' not in fqdn:
            return None

        return fqdn
    except Exception as e:
        logger.warning(f"Failed to parse URL '{url}': {e}")
        return None


def extract_unique_fqdns(urls: List[str]) -> Set[str]:
    """Extract unique FQDNs from a list of URLs."""
    fqdns = set()
    for url in urls:
        fqdn = extract_fqdn(url)
        if fqdn:
            fqdns.add(fqdn)
    return fqdns


def read_gcs_json(path: str) -> Dict[str, Any]:
    """Read JSON file from GCS."""
    if not storage_client:
        logger.warning(f"No storage client - cannot read {path}")
        return {}

    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(path)

        if not blob.exists():
            logger.info(f"File does not exist: {path}")
            return {}

        content = blob.download_as_text()
        return json.loads(content)
    except Exception as e:
        logger.error(f"Error reading {path}: {e}")
        return {}


def load_known_fqdns_from_preferences() -> Set[str]:
    """
    Load known FQDNs from ALL user preferences files.
    Iterates through config/user_preferences/*/preferences.json
    """
    known = set()

    if not storage_client:
        logger.warning("No storage client - cannot load preferences")
        return known

    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blobs = bucket.list_blobs(prefix=USER_PREFERENCES_PREFIX)

        for blob in blobs:
            if blob.name.endswith('/preferences.json'):
                try:
                    content = blob.download_as_text()
                    prefs = json.loads(content)

                    scraper_config = prefs.get('scraperConfig', {})
                    for region in ['eu', 'tr']:
                        region_config = scraper_config.get(region, {})
                        sources = region_config.get('sources', [])

                        for source in sources:
                            url = source.get('url', '')
                            fqdn = extract_fqdn(url)
                            if fqdn:
                                known.add(fqdn)

                except Exception as e:
                    logger.warning(f"Error reading preferences from {blob.name}: {e}")

        logger.info(f"Loaded {len(known)} known FQDNs from user preferences")
        return known

    except Exception as e:
        logger.error(f"Error loading user preferences: {e}")
        return known


def load_discovered_fqdns() -> Set[str]:
    """Load already-discovered FQDNs from discovered_sources.json."""
    discovered = set()

    data = read_gcs_json(DISCOVERED_SOURCES_PATH)
    if data:
        for entry in data.get('discovered', []):
            fqdn = entry.get('fqdn')
            if fqdn:
                discovered.add(fqdn)

    logger.info(f"Loaded {len(discovered)} already-discovered FQDNs")
    return discovered


def append_discovered_sources(new_fqdns: Set[str]) -> bool:
    """
    Append new FQDNs to discovered_sources.json.
    Creates the file if it doesn't exist.
    """
    if not storage_client or not new_fqdns:
        return False

    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(DISCOVERED_SOURCES_PATH)

        # Load existing data or create new structure
        if blob.exists():
            existing = json.loads(blob.download_as_text())
        else:
            existing = {'discovered': [], 'last_updated': None}

        # Get current timestamp
        now = datetime.now(timezone.utc).isoformat()

        # Append new FQDNs
        for fqdn in sorted(new_fqdns):
            existing['discovered'].append({
                'fqdn': fqdn,
                'first_seen': now
            })

        existing['last_updated'] = now

        # Save back to GCS
        blob.upload_from_string(
            json.dumps(existing, indent=2, ensure_ascii=False),
            content_type='application/json'
        )

        logger.info(f"Appended {len(new_fqdns)} new FQDNs to {DISCOVERED_SOURCES_PATH}")
        return True

    except Exception as e:
        logger.error(f"Error appending to discovered_sources.json: {e}")
        return False


def _process_discovery_request(message_data: Dict[str, Any]) -> None:
    """
    Process a source discovery request.

    Args:
        message_data: Dict containing 'run_path' and optional metadata
    """
    run_path = message_data.get('run_path')
    triggered_by = message_data.get('triggered_by', 'system')

    if not run_path:
        logger.error("No run_path provided in message")
        return

    logger.info(f"Processing source discovery for run_path: {run_path}")
    logger.info(f"Triggered by: {triggered_by}")

    # Read article files
    complete_articles_path = f"{run_path}/complete_articles.json"
    to_scrape_path = f"{run_path}/to_scrape.json"

    complete_data = read_gcs_json(complete_articles_path)
    to_scrape_data = read_gcs_json(to_scrape_path)

    # Extract URLs from articles
    all_urls = []

    for article in complete_data.get('articles', []):
        url = article.get('url') or article.get('original_url')
        if url:
            all_urls.append(url)

    for article in to_scrape_data.get('articles', []):
        url = article.get('url') or article.get('original_url')
        if url:
            all_urls.append(url)

    logger.info(f"Found {len(all_urls)} total URLs from article files")

    # Extract unique FQDNs
    fqdns = extract_unique_fqdns(all_urls)
    logger.info(f"Extracted {len(fqdns)} unique FQDNs: {sorted(fqdns)[:10]}...")

    # Load known sources from user preferences
    known_fqdns = load_known_fqdns_from_preferences()

    # Load already-discovered FQDNs
    already_discovered = load_discovered_fqdns()

    # Filter to only truly new FQDNs
    new_fqdns = fqdns - known_fqdns - already_discovered

    if new_fqdns:
        logger.info(f"Discovered {len(new_fqdns)} NEW sources: {sorted(new_fqdns)}")
        append_discovered_sources(new_fqdns)
    else:
        logger.info("No new sources discovered in this run")

    logger.info("Source discovery completed")


def source_discoverer(event, context):
    """
    Cloud Function entry point - triggered by Pub/Sub.

    Args:
        event: Pub/Sub message data
        context: Cloud Functions context
    """
    logger.info("=== SOURCE DISCOVERER TRIGGERED ===")
    logger.info(f"Event: {event}")

    if isinstance(event, dict) and "data" in event:
        try:
            message_data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
            logger.info(f"Decoded message: {message_data}")
            _process_discovery_request(message_data)
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
    else:
        logger.error("Invalid Pub/Sub message format")

    logger.info("=== SOURCE DISCOVERER COMPLETED ===")


# Local testing
if __name__ == "__main__":
    # Test with sample data
    test_message = {
        'run_path': 'ingestion/2025-12-21/15-17-02',
        'triggered_by': 'local_test'
    }

    logger.info("Running local test...")
    _process_discovery_request(test_message)
