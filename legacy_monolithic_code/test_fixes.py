#!/usr/bin/env python3
"""
Simple test script to verify our fixes
"""
import subprocess
import sys
import os

# Change to the project directory
os.chdir(r"c:\Users\oktay\Documents\archive\aisports")

def run_test(test_path, desc):
    """Run a specific test and return results"""
    print(f"\n{'='*60}")
    print(f"Testing: {desc}")
    print(f"Command: pytest {test_path}")
    print('='*60)
    
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', test_path, '-v', '--tb=short'],
        capture_output=True,
        text=True,
        cwd='.'
    )
    
    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("\nSTDERR:")
        print(result.stderr)
    print(f"\nReturn code: {result.returncode}")
    return result.returncode == 0

# Test our fixes
tests_to_run = [
    ("tests/test_capabilities.py::TestWebScraper::test_scrape_article_details_successful_extraction", 
     "Capabilities test - title expectation fix"),
    ("tests/test_journalist_integration.py::test_journalist_library_integration", 
     "Journalist integration test - return type fix"),
    ("tests/unit/scraping/test_link_discoverer.py::test_link_discoverer_initialization", 
     "LinkDiscoverer initialization test - constructor fix"),
    ("tests/test_mongodb_client.py::TestMongoDBClient::test_get_prepared_posts", 
     "MongoDB client test - mock signature fix"),
]

passed = 0
total = len(tests_to_run)

for test_path, desc in tests_to_run:
    if run_test(test_path, desc):
        passed += 1
        print("✅ PASSED")
    else:
        print("❌ FAILED")

print(f"\n{'='*60}")
print(f"SUMMARY: {passed}/{total} tests passed")
print('='*60)
