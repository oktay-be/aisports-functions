"""
Main configuration for the Turkish Sports News API.
"""

import os
from quart import Quart
from dotenv import load_dotenv
import json

def configure_app(name, config_name=None):
    """
    Configure and return Quart application
    
    Args:
        name: The name of the Quart application
        config_name: Configuration name ('development', 'production', 'testing')
    
    Returns:
        Configured Quart application
    """
    # Load environment variables from .env file
    load_dotenv()
      # Create Quart app
    app = Quart(name)
      # Configure based on environment
    if config_name == 'testing':
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['NEWSAPI_KEY'] = 'test-newsapi-key'
        app.config['WORLDNEWSAPI_KEY'] = 'test-worldnewsapi-key'
        app.config['GNEWS_API_KEY'] = 'test-gnews-api-key'
        app.config['TWITTER_API_KEY'] = 'test-twitter-api-key'
        app.config['TWITTER_API_SECRET'] = 'test-twitter-api-secret'
        app.config['TWITTER_ACCESS_TOKEN'] = 'test-twitter-access-token'
        app.config['TWITTER_ACCESS_SECRET'] = 'test-twitter-access-secret'
        app.config['CACHE_EXPIRATION'] = 0  # Disable caching for tests
    else:
        # Configure secret key
        app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev-secret-key")
          # API keys
        app.config['NEWSAPI_KEY'] = os.getenv("NEWSAPI_KEY")
        app.config['WORLDNEWSAPI_KEY'] = os.getenv("WORLDNEWSAPI_KEY")
        app.config['GNEWS_API_KEY'] = os.getenv("GNEWS_API_KEY")
        app.config['TWITTER_API_KEY'] = os.getenv("TWITTER_API_KEY")
        app.config['TWITTER_API_SECRET'] = os.getenv("TWITTER_API_SECRET")
        app.config['TWITTER_ACCESS_TOKEN'] = os.getenv("TWITTER_ACCESS_TOKEN")
        app.config['TWITTER_ACCESS_SECRET'] = os.getenv("TWITTER_ACCESS_SECRET")
        
        # Cache settings
        app.config['CACHE_EXPIRATION'] = int(os.getenv("CACHE_EXPIRATION_HOURS", "1"))
    
    # Common settings
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    app.config['JSON_AS_ASCII'] = False  # Ensures proper handling of Turkish characters
    
    # Cache directory
    app.config['CACHE_DIR'] = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'cache')
    
    # Workspace directory for session data, summaries, etc.
    app.config['WORKSPACE_DIR'] = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'workspace')
    os.makedirs(app.config['WORKSPACE_DIR'], exist_ok=True)

    # LLM Configuration for AISummarizer (passed to AnalysisOrchestrator)
    # These should be set in your .env file or environment variables
    app.config['LLM_CONFIG'] = {
        "config_list": [
            {
                "base_url": os.getenv("AZURE_OPENAI_ENDPOINT"),
                "model": os.getenv("MODEL_NAME"), # Your Azure OpenAI deployment name
                "api_key": os.getenv("AZURE_OPENAI_KEY"),
                "api_type": "azure",
                "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
            }
        ],
        "temperature": float(os.getenv("LLM_TEMPERATURE", 0.2)),
        "timeout": int(os.getenv("LLM_TIMEOUT", 120)),
        "cache_seed": None # Or an integer for reproducible caching, None to disable caching based on seed
    }    # News aggregator configuration
    app.config['NEWS_SOURCES'] = json.loads(os.getenv('NEWS_SOURCES', '["newsapi", "gnews"]'))
    app.config['NEWS_LANGUAGES'] = json.loads(os.getenv('NEWS_LANGUAGES', '["en", "tr"]'))
    app.config['TEAM_IDS'] = json.loads(os.getenv('TEAM_IDS', '[8650]'))  # Fenerbahçe default
    app.config['NEWS_DOMAINS'] = json.loads(os.getenv('NEWS_DOMAINS', '[]'))

    # Create cache directory
    os.makedirs(app.config['CACHE_DIR'], exist_ok=True)
    
    return app
