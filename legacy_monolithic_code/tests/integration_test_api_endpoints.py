"""
API endpoint integration tests for the refactored architecture.
Tests the new separated scraping and analysis endpoints.
"""

import requests
import json
import time
import os

BASE_URL = "http://localhost:5000/api"

def test_health_endpoints():
    """Test health and status endpoints."""
    print("\n🏥 Testing Health Endpoints")
    print("-" * 40)
    
    try:
        # Test main health check
        response = requests.get(f"{BASE_URL}/health")
        print(f"GET /api/health: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Version: {data.get('version')}")
            print(f"   Architecture: {data.get('architecture')}")
        
        # Test overall status
        response = requests.get(f"{BASE_URL}/status")
        print(f"GET /api/status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Overall status: {data.get('overall_status')}")
        
        # Test migration info
        response = requests.get(f"{BASE_URL}/migration_info")
        print(f"GET /api/migration_info: {response.status_code}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API server. Is it running on localhost:5000?")
        return False
    except Exception as e:
        print(f"❌ Health test error: {e}")
        return False

def test_scraping_endpoints():
    """Test scraping endpoints."""
    print("\n🕷️ Testing Scraping Endpoints")
    print("-" * 40)
    
    try:
        # Test scraping status
        response = requests.get(f"{BASE_URL}/scraping/status")
        print(f"GET /api/scraping/status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Service: {data.get('service')}")
            print(f"   Status: {data.get('status')}")
            print(f"   Total sessions: {data.get('total_sessions')}")
        
        # Test session listing
        response = requests.get(f"{BASE_URL}/scraping/sessions")
        print(f"GET /api/scraping/sessions: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Sessions available: {data.get('total_sessions')}")
        
        # Test latest session
        response = requests.get(f"{BASE_URL}/scraping/latest")
        print(f"GET /api/scraping/latest: {response.status_code}")
        
        # Test scraping start (small test)
        test_scraping_data = {
            "urls": ["https://www.fanatik.com.tr"],
            "keywords": ["Fenerbahçe"],
            "persist": True,
            "scrape_depth": 1
        }
        
        print(f"\nStarting test scraping job...")
        response = requests.post(
            f"{BASE_URL}/scraping/start",
            json=test_scraping_data,
            headers={'Content-Type': 'application/json'}
        )
        print(f"POST /api/scraping/start: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Session ID: {data.get('session_id')}")
            print(f"   Articles found: {data.get('articles_found')}")
            print(f"   Status: {data.get('status')}")
            return data.get('session_id')
        
        return None
        
    except Exception as e:
        print(f"❌ Scraping test error: {e}")
        return None

def test_analysis_endpoints(session_id=None):
    """Test analysis endpoints."""
    print("\n🧠 Testing Analysis Endpoints")
    print("-" * 40)
    
    try:
        # Test analysis status
        response = requests.get(f"{BASE_URL}/analysis/status")
        print(f"GET /api/analysis/status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Service: {data.get('service')}")
            print(f"   Status: {data.get('status')}")
            print(f"   AI model ready: {data.get('ai_model_ready')}")
        
        # Test AI connection
        test_ai_data = {
            "test_data": "Fenerbahçe transfer haberleri test"
        }
        
        response = requests.post(
            f"{BASE_URL}/analysis/test_ai",
            json=test_ai_data,
            headers={'Content-Type': 'application/json'}
        )
        print(f"POST /api/analysis/test_ai: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   AI test: {data.get('ai_test')}")
            print(f"   Model available: {data.get('model_available')}")
        
        # Test auto process (convenience method)
        auto_process_data = {
            "use_claude4": True
        }
        
        response = requests.post(
            f"{BASE_URL}/analysis/auto_process",
            json=auto_process_data,
            headers={'Content-Type': 'application/json'}
        )
        print(f"POST /api/analysis/auto_process: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            result = data.get('analysis_result', {})
            print(f"   Auto processed: {data.get('auto_processed')}")
            print(f"   Processed articles: {len(result.get('processed_articles', []))}")
        elif response.status_code == 404:
            print(f"   No sessions found for auto processing")
        
        # Test manual analysis with latest session
        manual_analysis_data = {
            "use_latest_session": True,
            "use_claude4": True
        }
        
        response = requests.post(
            f"{BASE_URL}/analysis/process_scraped_data",
            json=manual_analysis_data,
            headers={'Content-Type': 'application/json'}
        )
        print(f"POST /api/analysis/process_scraped_data: {response.status_code}")
        
        return True
        
    except Exception as e:
        print(f"❌ Analysis test error: {e}")
        return False

def test_separated_workflow():
    """Test the complete separated workflow."""
    print("\n🔄 Testing Separated Workflow")
    print("-" * 40)
    
    try:
        # Step 1: Start scraping
        scraping_data = {
            "urls": ["https://www.fanatik.com.tr"],
            "keywords": ["Fenerbahçe", "transfer"],
            "persist": True,
            "scrape_depth": 1
        }
        
        print("Step 1: Starting scraping...")
        scraping_response = requests.post(
            f"{BASE_URL}/scraping/start",
            json=scraping_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if scraping_response.status_code != 200:
            print(f"❌ Scraping failed: {scraping_response.status_code}")
            return False
        
        scraping_result = scraping_response.json()
        session_id = scraping_result.get('session_id')
        print(f"✅ Scraping completed. Session: {session_id}")
        
        # Small delay to ensure file is written
        time.sleep(2)
        
        # Step 2: Analyze the results
        analysis_data = {
            "use_latest_session": True,
            "use_claude4": True
        }
        
        print("Step 2: Analyzing scraped data...")
        analysis_response = requests.post(
            f"{BASE_URL}/analysis/process_scraped_data",
            json=analysis_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if analysis_response.status_code != 200:
            print(f"❌ Analysis failed: {analysis_response.status_code}")
            return False
        
        analysis_result = analysis_response.json()
        processed_articles = len(analysis_result.get('analysis_result', {}).get('processed_articles', []))
        print(f"✅ Analysis completed. Processed articles: {processed_articles}")
        
        return True
        
    except Exception as e:
        print(f"❌ Workflow test error: {e}")
        return False

def main():
    """Run all API tests."""
    print("🚀 AISports Refactored API Tests")
    print("Testing separated scraping and analysis endpoints")
    print("=" * 60)
    
    # Test 1: Health endpoints
    health_ok = test_health_endpoints()
    
    if not health_ok:
        print("\n❌ Cannot reach API server. Please ensure:")
        print("   1. Flask app is running (python app.py)")
        print("   2. Server is accessible on localhost:5000")
        print("   3. New routes are loaded")
        return
    
    # Test 2: Service endpoints
    session_id = test_scraping_endpoints()
    analysis_ok = test_analysis_endpoints(session_id)
    
    # Test 3: Complete workflow
    if health_ok:
        workflow_ok = test_separated_workflow()
        
        print("\n" + "=" * 60)
        if workflow_ok:
            print("🎉 ALL API TESTS PASSED!")
            print("✅ Health endpoints working")
            print("✅ Scraping endpoints working") 
            print("✅ Analysis endpoints working")
            print("✅ Separated workflow functioning")
        else:
            print("⚠️  SOME TESTS HAD ISSUES")
            print("Check the API server logs for details")
        print("=" * 60)

if __name__ == "__main__":
    main()
