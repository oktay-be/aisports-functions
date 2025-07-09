"""
Simple test to verify the scraper function imports and structure.
"""

import os
import sys
import json
from pathlib import Path

# Add the current directory to the path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all necessary imports work."""
    print("Testing imports...")
    
    try:
        from google.cloud import pubsub_v1, storage
        print("✅ Google Cloud imports successful")
    except ImportError as e:
        print(f"❌ Google Cloud imports failed: {e}")
        return False
    
    # Test journalist import (might not be available in dev environment)
    try:
        from journalist import Journalist
        print("✅ Journalist import successful")
    except ImportError as e:
        print(f"⚠️ Journalist import failed (expected in dev): {e}")
    
    return True

def test_function_structure():
    """Test that the main function structure is correct."""
    print("\nTesting function structure...")
    
    try:
        # Import the main module
        import main
        
        # Check if the main function exists
        if hasattr(main, 'scrape_and_store'):
            print("✅ scrape_and_store function exists")
        else:
            print("❌ scrape_and_store function not found")
            return False
            
        # Check if the async helper function exists
        if hasattr(main, '_process_scraping_request'):
            print("✅ _process_scraping_request function exists")
        else:
            print("❌ _process_scraping_request function not found")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Function structure test failed: {e}")
        return False

def test_configuration():
    """Test that configuration variables are set correctly."""
    print("\nTesting configuration...")
    
    try:
        import main
        
        # Check if configuration variables are defined
        config_vars = [
            'PROJECT_ID', 'SESSION_DATA_CREATED_TOPIC', 'GCS_BUCKET_NAME',
            'NEWS_DATA_ROOT_PREFIX', 'ARTICLES_SUBFOLDER'
        ]
        
        for var in config_vars:
            if hasattr(main, var):
                value = getattr(main, var)
                print(f"✅ {var} = {value}")
            else:
                print(f"❌ {var} not found")
                return False
                
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def test_message_format():
    """Test that message format handling works correctly."""
    print("\nTesting message format...")
    
    # Test message format
    test_message = {
        "urls": [
            "https://www.fanatik.com.tr/",
            "https://www.fotomac.com.tr/"
        ],
        "keywords": [
            "fenerbahce",
            "galatasaray"
        ]
    }
    
    try:
        # Test JSON serialization
        message_json = json.dumps(test_message)
        print(f"✅ Message JSON: {message_json}")
        
        # Test base64 encoding (as used in Pub/Sub)
        import base64
        encoded = base64.b64encode(message_json.encode('utf-8')).decode('utf-8')
        print(f"✅ Base64 encoded: {encoded[:50]}...")
        
        # Test decoding
        decoded = json.loads(base64.b64decode(encoded).decode('utf-8'))
        print(f"✅ Decoded message: {decoded}")
        
        return True
        
    except Exception as e:
        print(f"❌ Message format test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=== Scraper Function Tests ===")
    
    tests = [
        test_imports,
        test_function_structure, 
        test_configuration,
        test_message_format
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n=== Results ===")
    print(f"Passed: {passed}/{len(tests)}")
    
    if passed == len(tests):
        print("✅ All tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
