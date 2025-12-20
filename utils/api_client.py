"""
API Client for AISports UI

Authenticates with Google OAuth and fetches articles from the UI API.

Usage:
    # Using default service account credentials
    python api_client.py

    # Fetch specific region
    python api_client.py --region tr --days 3

Requirements:
    pip install google-auth requests
"""

import argparse
import json
import os
import sys

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

# Cloud Run service URL
UI_SERVICE_URL = "https://aisports-ui-30106847072.us-central1.run.app"


def get_id_token_for_cloud_run(target_audience: str) -> str:
    """
    Get an ID token for authenticating to Cloud Run.

    Uses Application Default Credentials (ADC):
    - Set GOOGLE_APPLICATION_CREDENTIALS env var to service account key path
    - Or use gcloud auth application-default login for user credentials

    Args:
        target_audience: The Cloud Run service URL

    Returns:
        ID token string
    """
    request = Request()
    token = id_token.fetch_id_token(request, target_audience)
    return token


def fetch_articles(region: str = 'eu', last_n_days: int = 1) -> dict:
    """
    Fetch articles from the UI API.

    Args:
        region: Region filter ('eu', 'tr', 'us', or 'all')
        last_n_days: Number of days to fetch (default: 1 = today only)

    Returns:
        List of articles or error dict
    """
    try:
        token = get_id_token_for_cloud_run(UI_SERVICE_URL)
    except Exception as e:
        return {"error": f"Failed to get auth token: {e}"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    params = {
        "region": region,
        "last_n_days": last_n_days
    }

    try:
        response = requests.get(
            f"{UI_SERVICE_URL}/api/news",
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code == 200:
            return response.json()
        else:
            return {
                "error": f"API returned {response.status_code}",
                "message": response.text
            }

    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}


def get_user_info() -> dict:
    """Get current authenticated user info."""
    try:
        token = get_id_token_for_cloud_run(UI_SERVICE_URL)
    except Exception as e:
        return {"error": f"Failed to get auth token: {e}"}

    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(
        f"{UI_SERVICE_URL}/api/user",
        headers=headers,
        timeout=10
    )

    return response.json() if response.ok else {"error": response.text}


def main():
    parser = argparse.ArgumentParser(description="AISports UI API Client")
    parser.add_argument("--region", default="eu", help="Region filter (eu, tr, us, all)")
    parser.add_argument("--days", type=int, default=1, help="Number of days to fetch")
    parser.add_argument("--user", action="store_true", help="Get current user info")
    parser.add_argument("--output", help="Output file path (JSON)")

    args = parser.parse_args()

    if args.user:
        result = get_user_info()
    else:
        result = fetch_articles(region=args.region, last_n_days=args.days)

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Saved to {args.output}")
    else:
        if isinstance(result, list):
            print(f"Fetched {len(result)} articles")
            for i, article in enumerate(result[:5]):
                print(f"\n{i+1}. {article.get('title', 'No title')[:80]}")
                print(f"   URL: {article.get('original_url', 'N/A')[:60]}")
            if len(result) > 5:
                print(f"\n... and {len(result) - 5} more articles")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
