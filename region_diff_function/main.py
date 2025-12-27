"""
Region Diff Function - Cross-Regional News Coverage Analysis

Analyzes news coverage differences between regions.
Finds articles that appear in one region but not in another.

Flow:
1. Triggered by GCS file creation/update (enriched_*.json)
2. Loads embeddings and articles for the run
3. Compares EU articles against TR articles
4. Outputs unique articles to analysis/ folder
"""

import os
import json
import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any

CET = ZoneInfo("Europe/Berlin")

from google.cloud import storage

from region_diff import RegionDiffAnalyzer

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("Region Diff Function initialized")

# Environment configuration
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT != 'local':
    storage_client = storage.Client()
else:
    storage_client = None
    logger.info("Running in local environment")

# Configuration
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')

# Diff configuration
REGION_DIFF_THRESHOLD = float(os.getenv('REGION_DIFF_THRESHOLD', '0.75'))
REGION1 = os.getenv('REGION1', 'eu')
REGION2 = os.getenv('REGION2', 'tr')
HISTORICAL_DIFF_DEPTH = int(os.getenv('HISTORICAL_DIFF_DEPTH', '3'))  # Days of TR history to compare against

# File patterns that trigger this function
TRIGGER_PATTERNS = [
    'enriched_complete_articles.json',
    'enriched_scraped_incomplete_articles.json',
    'enriched_scraped_articles.json',
]


def region_diff_handler(event, context):
    """
    Cloud Function entry point.
    Triggered by GCS Eventarc on enriched_*.json creation/update.
    """
    logger.info("=== REGION DIFF FUNCTION TRIGGERED ===")

    if isinstance(event, dict):
        bucket = event.get('bucket', GCS_BUCKET_NAME)
        name = event.get('name', '')
        metageneration = event.get('metageneration', '1')
    else:
        logger.error(f"Unknown event format: {type(event)}")
        return

    logger.info(f"Triggered by: gs://{bucket}/{name}")
    logger.info(f"Metageneration: {metageneration} ({'new file' if metageneration == '1' else 'overwrite'})")

    # Check if file matches trigger pattern
    filename = name.split('/')[-1] if name else ''
    if filename not in TRIGGER_PATTERNS:
        logger.info(f"Ignoring file: {filename}")
        return

    try:
        # Extract run folder from path
        # Path format: ingestion/2025-12-22/08-37-29/enriched_scraped_articles.json
        parts = name.split('/')
        if len(parts) < 4:
            logger.error(f"Invalid path format: {name}")
            return

        run_folder = '/'.join(parts[:-1])  # ingestion/2025-12-22/08-37-29
        logger.info(f"Run folder: {run_folder}")

        # Initialize analyzer
        analyzer = RegionDiffAnalyzer(
            storage_client=storage_client,
            bucket_name=bucket,
            diff_threshold=REGION_DIFF_THRESHOLD,
            historical_diff_depth=HISTORICAL_DIFF_DEPTH
        )

        # Compute diff
        result = analyzer.get_diff(
            region1=REGION1,
            region2=REGION2,
            run_folder=run_folder
        )

        logger.info(f"Historical diff depth: {HISTORICAL_DIFF_DEPTH} days")

        # Save result to analysis folder
        output_path = f"{run_folder}/analysis/region_diff_{REGION1}_vs_{REGION2}.json"
        gcs_uri = analyzer.save_result_to_gcs(result, output_path)

        logger.info(f"Diff result saved to: {gcs_uri}")
        logger.info(
            f"Summary: {result['summary']['unique_to_region1']} {REGION1} articles "
            f"not covered in {REGION2} (out of {result['summary']['total_region1_articles']})"
        )

    except Exception as e:
        logger.error(f"Error computing region diff: {e}", exc_info=True)

    logger.info("=== REGION DIFF FUNCTION COMPLETED ===")


def main(request):
    """HTTP entry point for testing."""
    logger.info("=== REGION DIFF HTTP TRIGGERED ===")

    try:
        data = request.get_json() if request.is_json else {}
        run_folder = data.get('run_folder', '')
        region1 = data.get('region1', REGION1)
        region2 = data.get('region2', REGION2)
        diff_threshold = float(data.get('diff_threshold', REGION_DIFF_THRESHOLD))
        historical_diff_depth = int(data.get('historical_diff_depth', HISTORICAL_DIFF_DEPTH))

        if not run_folder:
            return {"error": "run_folder required"}, 400

        analyzer = RegionDiffAnalyzer(
            storage_client=storage_client,
            bucket_name=GCS_BUCKET_NAME,
            diff_threshold=diff_threshold,
            historical_diff_depth=historical_diff_depth
        )

        result = analyzer.get_diff(
            region1=region1,
            region2=region2,
            run_folder=run_folder
        )

        # Save result
        output_path = f"{run_folder}/analysis/region_diff_{region1}_vs_{region2}.json"
        gcs_uri = analyzer.save_result_to_gcs(result, output_path)

        return {
            "status": "success",
            "output_path": gcs_uri,
            "summary": result['summary']
        }, 200

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"error": str(e)}, 500


if __name__ == "__main__":
    # Local testing
    logger.info("Running in local mode")

    # Simulate GCS event
    test_event = {
        'bucket': 'aisports-scraping',
        'name': 'ingestion/2025-12-22/22-00-29/enriched_scraped_articles.json',
        'metageneration': '1'
    }

    region_diff_handler(test_event, None)
