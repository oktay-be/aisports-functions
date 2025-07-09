import asyncio
import aiohttp
import os
from datetime import datetime, timedelta
import json

# --- Configuration ---
# Replace with your actual NewsAPI key or set it as an environment variable
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "YOUR_NEWSAPI_KEY_HERE") 
KEYWORDS = ["fenerbahce", "Mourinho"]
LANGUAGE = "en" # Keep it simple for testing
DAYS_AGO = 7 # Look back over the last 7 days
MAX_RESULTS = 10

async def test_newsapi_connection():
    """
    Tests connection to NewsAPI with simple keywords and prints the results.
    """
    if NEWSAPI_KEY == "YOUR_NEWSAPI_KEY_HERE":
        print("Please replace 'YOUR_NEWSAPI_KEY_HERE' with your actual NewsAPI key in the script.")
        return

    print(f"Attempting to fetch news from NewsAPI with key: {NEWSAPI_KEY[:5]}... (obfuscated)")

    query = " OR ".join(KEYWORDS)  # Changed from OR to AND
    
    # Calculate date range
    now = datetime.now()
    from_date = (now - timedelta(days=DAYS_AGO)).isoformat()
    to_date = now.isoformat()

    params = {
        "q": query,
        "language": LANGUAGE,
        "from": from_date,
        "to": to_date,
        "apiKey": NEWSAPI_KEY,
        "pageSize": MAX_RESULTS,
        "sortBy": "publishedAt", # Sort by relevance or publishedAt
        "searchIn": "title,description"  # Added to search in title and description
    }

    url = "https://newsapi.org/v2/everything"
    
    print(f"Requesting URL: {url}")
    print(f"With parameters: {json.dumps(params, indent=2)}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                print(f"Response Status: {response.status}")
                response.raise_for_status()  # Raise an exception for HTTP errors
                
                data = await response.json()
                
                print("\n--- Full API Response Data ---")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                
                articles_found = data.get("articles", [])
                
                if articles_found:
                    print(f"\n--- Found {len(articles_found)} Articles ---")
                    for i, article in enumerate(articles_found):
                        print(f"\nArticle {i+1}:")
                        print(f"  Title: {article.get('title')}")
                        print(f"  Source: {article.get('source', {}).get('name')}")
                        print(f"  Published At: {article.get('publishedAt')}")
                        print(f"  URL: {article.get('url')}")
                        print(f"  Description: {article.get('description')}")
                        print(f"  Content: {article.get('content')}") # Added content field
                else:
                    print("\n--- No Articles Found ---")
                
                if data.get("totalResults") == 0:
                    print("NewsAPI reported 0 total results for the query.")
                elif "totalResults" in data:
                     print(f"NewsAPI reported {data.get('totalResults')} total results available.")


    except aiohttp.ClientResponseError as e:
        print(f"HTTP Error: {e.status} - {e.message}")
        if e.status == 401:
            print("Authentication failed. Check your API key.")
        elif e.status == 429:
            print("Rate limit exceeded. Try again later.")
        else:
            # Try to print more details from the response if available
            try:
                error_details = await response.json()
                print(f"Error details from API: {json.dumps(error_details, indent=2)}")
            except Exception:
                print("Could not parse error details from API response.")
    except aiohttp.ClientConnectorError as e:
        print(f"Connection Error: {e}")
        print("Failed to connect to NewsAPI. Check your internet connection or if the API endpoint is correct.")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_newsapi_connection())
