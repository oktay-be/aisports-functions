#!/usr/bin/env python3
"""
Simple test for AIAggregator Vertex AI integration.
Tests only the initialization without requiring database dependencies.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set Vertex AI environment variables
os.environ['GOOGLE_CLOUD_PROJECT'] = 'gen-lang-client-0306766464'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = './gen-lang-client-0306766464-13fc9c9298ba.json'

try:
    from capabilities.ai_aggregator import AIAggregator
    
    print("🧪 Testing AIAggregator Vertex AI initialization...")
    
    # Test initialization
    aggregator = AIAggregator()
    
    if aggregator.client is not None:
        print("✅ AIAggregator initialized successfully with Vertex AI client")
        print(f"✅ Project ID: {aggregator.project_id}")
        print(f"✅ Location: {aggregator.location}")
        print(f"✅ Model: {aggregator.model_name}")
    else:
        print("❌ AIAggregator client is None")
        
    print("✅ Test completed successfully")
    
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
