#!/usr/bin/env python3
"""
Test script for Turkish sports news extraction
Testing with Fenerbahçe and Galatasaray keywords on Turkish sports sites
"""

import asyncio
import sys
import os
import logging

# Add the src directory to Python path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from journalist import Journalist

# Single source of truth for log level
LOG_LEVEL = "INFO"

# Configure logging to see messages
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)


async def main():
    """Main test function for Turkish sports news extraction"""
    print("🚀 Starting Turkish Sports News Extraction Test")
    print("=" * 60)
    
    # Create journalist instance with persistence and depth 1
    journalist = Journalist(persist=True, scrape_depth=1)
    
    # Define test parameters
    urls = [
        "https://www.fanatik.com.tr",
        "https://www.ntvspor.net"    ]
    
    keywords = ["fenerbahce", "mourinho", "galatasaray"]
    
    print(f"📰 Target URLs: {urls}")
    print(f"🔍 Keywords: {keywords}")
    print("-" * 60)
    
    try:
        # Extract content from Turkish sports news sites
        print("⏳ Starting content extraction...")
        result = await journalist.read(
            urls=urls,
            keywords=keywords,
            log_level=LOG_LEVEL
        )
        
        print("✅ Content extraction completed!")
        print("=" * 60)
        
        # Extract articles from source-specific session data
        all_articles = []
        if isinstance(result, list):
            # New format: list of source-specific session data
            for source_data in result:
                source_articles = source_data.get('articles', [])
                all_articles.extend(source_articles)
        else:
            # Fallback for old format (shouldn't happen with new code)
            all_articles = result.get('articles', [])
        
        print(f"📄 Found {len(all_articles)} articles:")
        print("-" * 60)
        
        for i, article in enumerate(all_articles, 1):
            print(f"\n🏆 Article {i}:")
            print(f"   Title: {article.get('title', 'N/A')}")
            print(f"   URL: {article.get('url', 'N/A')}")
            print(f"   Published: {article.get('published_date', 'N/A')}")
            print(f"   Content Preview: {article.get('content', '')[:200]}...")
            if article.get('matched_keywords'):
                print(f"   Matched Keywords: {article.get('matched_keywords')}")
            print("-" * 40)
        
        # Display extraction summary
        total_articles = len(all_articles)
        total_sources = len(result) if isinstance(result, list) else 0
        print(f"\n📊 Extraction Summary:")
        print(f"   URLs Processed: {len(urls)}")
        print(f"   Articles Extracted: {total_articles}")
        print(f"   Sources Processed: {total_sources}")
        
        # Display source-specific information
        if isinstance(result, list) and result:
            print(f"\n🌐 Source-Specific Results:")
            print("-" * 60)
            for i, source_data in enumerate(result, 1):
                domain = source_data.get('source_domain', 'Unknown')
                source_url = source_data.get('source_url', 'N/A')
                source_articles = source_data.get('articles', [])
                
                print(f"\n📍 Source {i}: {domain}")
                print(f"   Original URL: {source_url}")
                print(f"   Articles Found: {len(source_articles)}")
                
                # Show first few articles from this source
                for j, article in enumerate(source_articles[:3], 1):
                    print(f"   📄 Article {j}:")
                    print(f"      Title: {article.get('title', 'N/A')[:60]}...")
                    print(f"      URL: {article.get('url', 'N/A')}")
                
                if len(source_articles) > 3:
                    print(f"   ... and {len(source_articles) - 3} more articles")
                print("-" * 40)
          # Check for any errors in source data (if the format supports it)
        errors = []
        if isinstance(result, list):
            for source_data in result:
                source_errors = source_data.get('errors', [])
                errors.extend(source_errors)
        else:
            # Fallback for old format
            errors = result.get('errors', [])
            
        if errors:
            print(f"\n⚠️  Errors encountered:")
            for error in errors:
                print(f"   - {error}")
        
        print("\n🎉 Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during extraction: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
    


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())