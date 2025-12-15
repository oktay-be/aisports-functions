"""
Test script to fetch news from all 3 APIs and record results.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta

# API Keys from .env
NEWSAPI_KEY = "7d518cdcc9ca4ccba0040eaf1e6334af"
WORLDNEWSAPI_KEY = "552686d97e124e3e856ea305e9c91b20"
GNEWS_API_KEY = "239e1985eb546d6ff7db252e3195c69a"

KEYWORDS = ["fenerbahce", "galatasaray", "tedesco"]


async def fetch_newsapi():
    """Fetch from NewsAPI"""
    query = " OR ".join(KEYWORDS)
    from_date = (datetime.now() - timedelta(days=7)).isoformat()
    
    params = {
        "q": query,
        "language": "en",
        "from": from_date,
        "apiKey": NEWSAPI_KEY,
        "pageSize": 10,
        "sortBy": "publishedAt"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://newsapi.org/v2/everything",
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                print(f"NewsAPI Status: {response.status}")
                data = await response.json()
                return {
                    "api": "NewsAPI",
                    "status": response.status,
                    "total_results": data.get("totalResults", 0),
                    "articles_count": len(data.get("articles", [])),
                    "articles": data.get("articles", []),
                    "error": data.get("message") if data.get("status") == "error" else None
                }
    except Exception as e:
        return {"api": "NewsAPI", "error": str(e), "articles": []}


async def fetch_worldnewsapi():
    """Fetch from WorldNewsAPI"""
    query = " OR ".join(KEYWORDS)
    from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    params = {
        "text": query,
        "language": "en,tr",
        "earliest_publish_date": from_date,
        "api-key": WORLDNEWSAPI_KEY,
        "number": 10,
        "sort": "publish-time",
        "sort_direction": "desc"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.worldnewsapi.com/search-news",
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                print(f"WorldNewsAPI Status: {response.status}")
                data = await response.json()
                return {
                    "api": "WorldNewsAPI",
                    "status": response.status,
                    "total_results": data.get("available", 0),
                    "articles_count": len(data.get("news", [])),
                    "articles": data.get("news", []),
                    "error": data.get("message") if "message" in data else None
                }
    except Exception as e:
        return {"api": "WorldNewsAPI", "error": str(e), "articles": []}


async def fetch_gnews():
    """Fetch from GNews API"""
    query = " OR ".join(KEYWORDS)
    from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    params = {
        "q": query,
        "lang": "en",
        "from": from_date,
        "apikey": GNEWS_API_KEY,
        "max": 10,
        "sortby": "publishedAt"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://gnews.io/api/v4/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                print(f"GNews Status: {response.status}")
                data = await response.json()
                return {
                    "api": "GNews",
                    "status": response.status,
                    "total_results": data.get("totalArticles", 0),
                    "articles_count": len(data.get("articles", [])),
                    "articles": data.get("articles", []),
                    "error": data.get("errors") if "errors" in data else None
                }
    except Exception as e:
        return {"api": "GNews", "error": str(e), "articles": []}


async def main():
    print("="*60)
    print(f"Fetching news at {datetime.now().isoformat()}")
    print(f"Keywords: {KEYWORDS}")
    print("="*60)
    
    results = await asyncio.gather(
        fetch_newsapi(),
        fetch_worldnewsapi(),
        fetch_gnews()
    )
    
    output = {
        "fetched_at": datetime.now().isoformat(),
        "keywords": KEYWORDS,
        "results": results
    }
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    total_articles = 0
    for r in results:
        count = r.get("articles_count", 0)
        total_articles += count
        status = "✅" if count > 0 else "❌"
        error_msg = f" - Error: {r.get('error')}" if r.get('error') else ""
        print(f"{status} {r['api']}: {count} articles{error_msg}")
    
    print(f"\nTotal articles: {total_articles}")
    
    # Save to file
    output_file = "api_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\nResults saved to: {output_file}")
    
    return output


if __name__ == "__main__":
    asyncio.run(main())
