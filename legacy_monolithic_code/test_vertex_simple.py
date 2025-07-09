#!/usr/bin/env python3
"""
Simple test of Vertex AI with service account credentials.
"""

import os
import sys
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_vertex_ai_simple():
    """Simple test using the exact pattern you requested."""
    print("🧪 Testing Vertex AI with your exact code pattern...")
    
    try:
        from google import genai

        # ADC automatically finds your credentials from .env
        client = genai.Client(
            vertexai=True,
            project="gen-lang-client-0306766464",  # Your project ID
            location="global"
        )

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=["Write a short summary about football in JSON format with 'title' and 'summary' fields."]
        )
        
        print("✅ Vertex AI connection successful!")
        print(f"Response: {response.text}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("SIMPLE VERTEX AI TEST")
    print("=" * 60)
    
    # Check environment
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    
    print(f"Project ID: {project_id}")
    print(f"Credentials: {creds_path}")
    
    if not project_id or not creds_path:
        print("❌ Environment not configured. Check your .env file.")
        sys.exit(1)
    
    # Test
    success = test_vertex_ai_simple()
    
    if success:
        print("\n🎉 SUCCESS! Your Vertex AI setup is working!")
    else:
        print("\n❌ FAILED! Check the error above.")
