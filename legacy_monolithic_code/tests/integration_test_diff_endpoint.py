#!/usr/bin/env python3
"""
Test script for the new /diff endpoint
Tests the simultaneous scraping of EU and TR sports sources
"""

import asyncio
import json
import requests
import sys
import time

def test_diff_endpoint():
    """
    Test the /diff endpoint that runs journalist.read simultaneously
    for European and Turkish sports sources.
    """
    print("🧪 Testing /diff endpoint...")
    print("=" * 60)
    
    # API endpoint URL (adjust as needed for your setup)
    api_url = "http://localhost:5000/api/diff"
    
    print(f"📡 Making POST request to: {api_url}")
    
    try:
        start_time = time.time()
        
        # Make the request (no body needed for this endpoint)
        response = requests.post(api_url, json={}, timeout=120)  # 2 minute timeout
        
        end_time = time.time()
        request_time = round(end_time - start_time, 2)
        
        print(f"⏱️  Request completed in {request_time} seconds")
        print(f"📊 Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            print("✅ Diff scraping completed successfully!")
            print("=" * 60)
            
            # Display summary
            summary = result.get('summary', {})
            print(f"📈 Summary:")
            print(f"   Total articles: {summary.get('total_articles', 0)}")
            print(f"   EU articles: {summary.get('eu_articles', 0)}")
            print(f"   TR articles: {summary.get('tr_articles', 0)}")
            print(f"   Execution time: {result.get('execution_time_seconds', 0)} seconds")
            
            # Display EU results
            eu_results = result.get('results', {}).get('eu_sources', {})
            print(f"\n🇪🇺 European Sources:")
            print(f"   Session ID: {eu_results.get('session_id', 'N/A')}")
            print(f"   Articles found: {eu_results.get('articles_count', 0)}")
            print(f"   URLs scraped: {eu_results.get('urls_scraped', 0)}")
            print(f"   Keywords: {eu_results.get('keywords_used', [])}")
            if eu_results.get('error'):
                print(f"   ❌ Error: {eu_results.get('error')}")
            else:
                print(f"   ✅ Completed successfully")
            
            # Display TR results  
            tr_results = result.get('results', {}).get('tr_sources', {})
            print(f"\n🇹🇷 Turkish Sources:")
            print(f"   Session ID: {tr_results.get('session_id', 'N/A')}")
            print(f"   Articles found: {tr_results.get('articles_count', 0)}")
            print(f"   URLs scraped: {tr_results.get('urls_scraped', 0)}")
            print(f"   Keywords: {tr_results.get('keywords_used', [])}")
            if tr_results.get('error'):
                print(f"   ❌ Error: {tr_results.get('error')}")
            else:
                print(f"   ✅ Completed successfully")
            
            # Show sample articles
            print(f"\n📰 Sample Articles:")
            print("-" * 40)
            
            eu_articles = eu_results.get('articles', [])
            if eu_articles:
                print(f"🇪🇺 EU Article Example:")
                sample_eu = eu_articles[0]
                print(f"   Title: {sample_eu.get('title', 'N/A')[:80]}...")
                print(f"   URL: {sample_eu.get('url', 'N/A')}")
                print(f"   Source: {sample_eu.get('source', 'N/A')}")
            
            tr_articles = tr_results.get('articles', [])
            if tr_articles:
                print(f"\n🇹🇷 TR Article Example:")
                sample_tr = tr_articles[0]
                print(f"   Title: {sample_tr.get('title', 'N/A')[:80]}...")
                print(f"   URL: {sample_tr.get('url', 'N/A')}")
                print(f"   Source: {sample_tr.get('source', 'N/A')}")
            
            print(f"\n🎉 Test completed successfully!")
            
        else:
            print(f"❌ Request failed with status {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Error response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out (>2 minutes)")
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - make sure the API server is running")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")

def test_search_parameters_files():
    """
    Test that the search parameter files exist and are valid.
    """
    print("\n🔍 Checking search parameter files...")
    
    files_to_check = [
        "search_parameters_eu.json",
        "search_parameters_tr.json"
    ]
    
    for filename in files_to_check:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"✅ {filename}:")
            print(f"   Keywords: {data.get('keywords', [])}")
            print(f"   URLs: {len(data.get('urls', []))} URLs")
            print(f"   Persist: {data.get('persist', False)}")
            
        except FileNotFoundError:
            print(f"❌ {filename} not found")
        except Exception as e:
            print(f"❌ Error reading {filename}: {e}")

if __name__ == "__main__":
    print("🚀 Starting /diff endpoint test")
    print("=" * 60)
    
    # First check the parameter files
    test_search_parameters_files()
    
    # Then test the endpoint
    test_diff_endpoint()
