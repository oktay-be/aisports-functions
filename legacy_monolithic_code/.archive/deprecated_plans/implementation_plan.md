# AISports News Collection & Analysis System - Implementation Plan

## Overview

This plan outlines the implementation of a comprehensive news collection and analysis system using MongoDB for data storage, AI for content processing, and a workflow that supports both automated collection and targeted re-scraping based on discovered gaps.

## Use Cases

### UseCase 1: Automated Full Collection
1. **Raw Scraping**: Use journalist to scrape sources (results stored in memory or persisted based on config)
2. **AI Summarization**: Process each source's raw data → generate summarized articles per source
3. **AI Aggregation**: Combine source summaries by region → TR and EU article collections
4. **EU Extension**: Extend EU data with NewsAPI → enhanced EU article collection
5. **AI Diff Analysis**: Compare EU extended vs TR → return missing article objects
6. **Database Storage**: Store all processed article results in MongoDB
7. **Frontend Trigger**: Single button to initiate entire workflow

### UseCase 2: Targeted Re-scraping
1. **Gap Identification**: User identifies missing entities from diff analysis
2. **Targeted Scraping**: Scrape only EU sources with new keywords
3. **AI Processing**: Follow same AI pipeline (summarize → store → display)
4. **Frontend Integration**: Show results organized by source

### UseCase 3: Social Media Post Generation
1. **Article Selection**: User selects article objects for post creation
2. **AI Post Generation**: Create X/Twitter posts based on selected articles
3. **Post Management**: Store and manage prepared posts
4. **Post Publishing**: Publish prepared posts to X/Twitter

## Database Design (MongoDB)

### Collections Schema

```javascript
// Collection: ai_summaries_per_source
{
  "_id": ObjectId,
  "run_id": "run_20250624_153000",
  "source_domain": "www_fanatik_com",
  "source_url": "https://www.fanatik.com.tr",
  "region": "TR" | "EU",
  "summary_data": {
    "processing_summary": {
      "total_input_articles": 14,
      "articles_after_deduplication": 5,
      "articles_after_cleaning": 5,
      "duplicates_removed": 9,
      "empty_articles_removed": 0,
      "processing_date": "2025-06-21T00:00:00Z"
    },
    "processed_articles": [
      {
        "id": "article_1",
        "original_url": "https://www.fanatik.com.tr/basketbol/fenerbahceden-dario-saric-hamlesi-teklif-yapildi-2585851",
        "title": "Fenerbahçe'den Dario Saric hamlesi! Teklif yapıldı",
        "summary": "Fenerbahçe Beko has reportedly made an offer for Croatian NBA star Dario Saric...",
        "key_entities": {
          "teams": ["Fenerbahçe Beko", "Denver Nuggets"],
          "players": ["Dario Saric"],
          "amounts": ["5 million 426 thousand 400 Dolar"],
          "dates": ["2014-2016"]
        },
        "categories": [
          {
            "tag": "transfers_rumors",
            "confidence": 0.9,
            "evidence": "Fenerbahçe Beko'nun NBA'de Denver Nuggets kadrosunda bulunan Hırvat yıldız Dario Saric için teklifini yaptığı belirtildi."
          }
        ],
        "source": "www.fanatik.com.tr",
        "published_date": "2025-06-21T19:45:15+03:00",
        "keywords_matched": ["fenerbahce"],
        "content_quality": "high",
        "language": "turkish"
      }
    ]
  },
  "articles_count": 12,
  "processing_time_seconds": 45,
  "created_at": ISODate
}

// Collection: ai_aggregated_results  
{
  "_id": ObjectId,
  "run_id": "run_20250624_153000",
  "region": "TR" | "EU",
  "aggregation_type": "scraped_only" | "extended_with_newsapi",
  "processed_articles": [
    // Same article schema as above
  ],
  "processing_summary": {
    "total_sources": 5,
    "total_articles": 67,
    "sources_included": ["www_fanatik_com", "www_fotomac_com"],
    "newsapi_articles_added": 23 // Only for extended type
  },
  "created_at": ISODate
}

// Collection: ai_diff_results - SIMPLIFIED
{
  "_id": ObjectId,
  "run_id": "run_20250624_153000",
  "comparison": {
    "eu_file_id": ObjectId,
    "tr_file_id": ObjectId
  },
  "missing_in_tr": [
    // Article objects using same schema - entities found in EU but not TR
    {
      "id": "article_eu_1",
      "original_url": "https://example.com/vlahovic-news",
      "title": "Vlahovic transfer news",
      "summary": "...",
      "key_entities": { "players": ["vlahovic"] },
      "categories": [...],
      "source": "bbc.com",
      "published_date": "2025-06-21T19:45:15+03:00",
      "keywords_matched": ["vlahovic"],
      "content_quality": "high",
      "language": "english"
    }
  ],
  "missing_in_eu": [
    // Article objects using same schema - entities found in TR but not EU
  ],
  "created_at": ISODate
}

// Collection: newsapi_data
{
  "_id": ObjectId,
  "run_id": "run_20250624_153000",
  "fetch_timestamp": ISODate,
  "keywords_used": ["fenerbahce", "mourinho"],
  "raw_articles": [
    {
      "source": {
        "id": null,
        "name": "Just Arsenal News"
      },
      "author": "Michelle",
      "title": "Could Arteta Face the Same Fate? Turkish Board Resigns After Mourinho Leak",
      "description": "Arsenal fans might take interest in recent events in Turkey...",
      "url": "https://www.justarsenal.com/could-arteta-face-the-same-fate-turkish-board-resigns-after-mourinho-leak/395128",
      "urlToImage": "https://icdn.justarsenal.com/wp-content/uploads/2025/06/Mourinho.jpg",
      "publishedAt": "2025-06-23T17:00:00Z",
      "content": "Arsenal fans might take interest in recent events in Turkey..."
    }
  ],
  "transformed_articles": [
    // Converted to our standard article schema
  ],
  "articles_count": 23,
  "api_quota_used": 100
}

// Collection: ai_posts - NEW
{
  "_id": ObjectId,
  "post_id": "post_20250624_001",
  "based_on_articles": [ObjectId], // References to article IDs
  "post_content": {
    "text": "🔥 TRANSFER ALERT: Fenerbahçe reportedly making moves for Dario Saric! The Croatian star has a $5.4M option with Denver Nuggets... Will he return to Turkish basketball? 🏀 #Fenerbahce #TransferNews",
    "hashtags": ["#Fenerbahce", "#TransferNews", "#Basketball"],
    "mentions": ["@Fenerbahce"],
    "character_count": 187
  },
  "post_status": "prepared" | "published" | "failed",
  "created_at": ISODate,
  "published_at": ISODate,
  "x_post_id": "1234567890", // Twitter/X post ID after publishing
  "engagement_stats": {
    "likes": 0,
    "retweets": 0,
    "replies": 0
  }
}
```

## Architecture Components

### 1. Database Layer (`database/`)

#### `mongodb_client.py` (Enhanced)
```python
class MongoDBClient:
    # Connection Management
    async def connect() -> bool
    async def disconnect()
    async def ensure_indexes()
    
    # Collection Runs
    async def create_collection_run(run_data: Dict) -> str
    async def update_run_status(run_id: str, status: str, stats: Dict = None) -> bool
    async def get_run(run_id: str) -> Optional[Dict]
    async def get_latest_run(run_type: str = None) -> Optional[Dict]
    async def list_runs(limit: int = 10) -> List[Dict]
    
    # Source Summaries
    async def save_source_summary(summary_data: Dict) -> str
    async def get_source_summaries(run_id: str, region: str = None) -> List[Dict]
    async def get_source_summary(run_id: str, source_domain: str) -> Optional[Dict]
    
    # Aggregated Results
    async def save_aggregated_result(aggregated_data: Dict) -> str
    async def get_aggregated_result(run_id: str, region: str, type: str) -> Optional[Dict]
    
    # Diff Results
    async def save_diff_result(diff_data: Dict) -> str
    async def get_diff_result(run_id: str) -> Optional[Dict]
    
    # NewsAPI Data
    async def save_newsapi_data(newsapi_data: Dict) -> str
    async def get_newsapi_data(run_id: str) -> Optional[Dict]
    
    # Queries for Frontend
    async def get_articles_by_source(run_id: str, source_domain: str) -> List[Dict]
    async def search_articles(query: str, run_id: str = None) -> List[Dict]
    async def get_missing_entities(run_id: str) -> List[str]
    
    # Post-related queries
    async def save_prepared_post(post_data: Dict) -> str
    async def get_prepared_posts(limit: int = 10, status: str = None) -> List[Dict]
    async def update_post_status(post_id: str, status: str, x_post_id: str = None) -> bool
    async def get_posts_by_articles(article_ids: List[str]) -> List[Dict]
```

### 2. AI Processing Layer (`capabilities/`)

#### `ai_aggregator.py` (New)
```python
class AIAggregator:
    def __init__(self, google_api_key: str, mongodb_client: MongoDBClient)
    
    # Main workflows
    async def aggregate_by_region(run_id: str, region: str) -> Dict
    async def extend_eu_with_newsapi(run_id: str, newsapi_data: Dict) -> Dict
    async def generate_diff_analysis(run_id: str) -> Dict
    
    # AI prompt generation
    def _create_aggregation_prompt(source_summaries: List[Dict], region: str) -> str
    def _create_extension_prompt(eu_data: Dict, newsapi_data: Dict) -> str
    def _create_diff_prompt(eu_extended: Dict, tr_data: Dict) -> str
    
    # AI processing
    async def _run_ai_processing(prompt: str, operation_type: str) -> Dict
```

#### `ai_summarizer.py` (Keep existing)
- Maintain current `summarize_and_classify_session_data_object()` method
- Used by orchestrator for processing individual source session files

### 3. Data Integration Layer (`integrations/`)

#### `newsapi_service.py` (New)
```python
class NewsAPIService:
    def __init__(self, api_key: str, cache_dir: str = "./cache")
    
    # Core fetching (copied from news_aggregator.py)
    async def fetch_newsapi_articles(keywords: List[str], max_results: int = 50) -> List[Dict]
    
    # Schema transformation
    def transform_to_standard_schema(newsapi_articles: List[Dict]) -> List[Dict]
    
    # Cache management  
    def _write_to_cache(cache_file: str, data: List[Dict]) -> None
    def _read_from_cache(cache_file: str) -> Optional[List[Dict]]
    
    # Utility
    def validate_quota() -> bool
```

#### `ai_post_maker.py` (New)
```python
class AIPostMaker:
    def __init__(self, google_api_key: str, mongodb_client: MongoDBClient)
    
    # Post generation
    async def create_posts_from_articles(article_ids: List[str]) -> List[Dict]
    async def create_single_post(article: Dict) -> Dict
    
    # Post management
    async def save_prepared_post(post_data: Dict) -> str
    async def get_prepared_posts(limit: int = 10) -> List[Dict]
    async def update_post_status(post_id: str, status: str) -> bool
    
    # X/Twitter integration
    async def publish_post(post_id: str) -> bool
    async def publish_multiple_posts(post_ids: List[str]) -> Dict
    
    # AI prompt generation
    def _create_post_prompt(article: Dict) -> str
    def _validate_post_content(content: str) -> bool
```

#### `collection_orchestrator.py` (Enhanced)
```python
class CollectionOrchestrator:
    def __init__(self, mongodb_client: MongoDBClient, ai_aggregator: AIAggregator, 
                 newsapi_service: NewsAPIService)
    
    # UseCase 1: Full Collection
    async def run_full_collection(keywords: List[str]) -> str:
        """
        1. Create collection run in MongoDB
        2. Trigger parallel scraping (TR + EU sources)
        3. Process each source with AI → save to MongoDB
        4. Aggregate by region → save to MongoDB  
        5. Extend EU with NewsAPI → save to MongoDB
        6. Generate diff analysis → save to MongoDB
        7. Update run status to completed
        """
    
    # UseCase 2: Targeted Scraping
    async def run_targeted_scraping(target_keywords: List[str], region: str = "EU") -> str:
        """
        1. Create targeted run in MongoDB
        2. Scrape only specified region with new keywords
        3. Process with AI → save to MongoDB
        4. Return results for frontend display
        """
      # Helper methods
    async def _scrape_sources(params: Dict, region: str) -> List[Dict]  # Returns article data directly
    async def _process_session_data(session_data: List[Dict], run_id: str) -> List[str]  # Returns summary IDs
    async def _cleanup_temp_data(temp_data: List[Dict]) # Memory cleanup when persist=false
```

### 5. API Layer (`api/endpoints/`)

#### `regional_endpoints.py` (New)
```python
@regional_blueprint.route('/tr', methods=['GET'])
async def get_tr_articles():
    """
    GET /api/tr?days=7&limit=100
    Returns: {
        "articles": [article_objects],
        "pagination": {...},
        "summary": {"total": 145, "sources": 5}
    }
    """

@regional_blueprint.route('/eu', methods=['GET'])
async def get_eu_articles():
    """
    GET /api/eu?days=7&limit=100
    Returns: Same structure as /tr
    """
```

#### `post_endpoints.py` (New)
```python
@post_blueprint.route('/post', methods=['POST'])
async def create_posts():
    """
    POST /api/post
    Body: {
        "article_ids": ["article_1", "article_2"],
        "mode": "make"
    }
    Returns: {"post_ids": ["post_001", "post_002"], "status": "created"}
    """

@post_blueprint.route('/post', methods=['GET'])
async def get_prepared_posts():
    """
    GET /api/post?status=prepared&limit=10
    Returns: {
        "posts": [post_objects],
        "pagination": {...}
    }
    """

@post_blueprint.route('/post/publish', methods=['POST'])
async def publish_posts():
    """
    POST /api/post/publish
    Body: {
        "post_ids": ["post_001", "post_002"]
    }
    Returns: {"published": 2, "failed": 0, "results": [...]}
    """
```

#### `collection_endpoints.py` (Existing)
```python
@collection_blueprint.route('/run', methods=['POST'])
async def start_full_collection():
    """
    POST /api/collection/run
    Body: {
        "keywords": ["fenerbahce", "mourinho"]
    }
    Returns: {"run_id": "run_20250624_153000", "status": "started"}
    """

@collection_blueprint.route('/targeted', methods=['POST'])
async def start_targeted_scraping():
    """
    POST /api/collection/targeted  
    Body: {
        "target_keywords": ["vlahovic"],
        "region": "EU",
        "base_keywords": ["fenerbahce"] # Optional
    }
    Returns: {"run_id": "run_20250624_153001", "status": "started"}
    """

@collection_blueprint.route('/status/<run_id>', methods=['GET'])
async def get_collection_status(run_id: str):
    """Get real-time status of collection run"""

@collection_blueprint.route('/runs', methods=['GET'])
async def list_collection_runs():
    """List recent collection runs with summary"""
```

#### `results_endpoints.py` (New)
```python
@results_blueprint.route('/latest', methods=['GET'])
async def get_latest_results():
    """Get latest collection results summary"""

@results_blueprint.route('/run/<run_id>', methods=['GET'])
async def get_run_results(run_id: str):
    """Get complete results for specific run"""

@results_blueprint.route('/diff/<run_id>', methods=['GET'])  
async def get_diff_analysis(run_id: str):
    """Get diff analysis results"""

@results_blueprint.route('/sources/<run_id>', methods=['GET'])
async def get_source_breakdown(run_id: str):
    """Get results broken down by source"""

@results_blueprint.route('/articles/search', methods=['POST'])
async def search_articles():
    """Search articles across runs"""

@results_blueprint.route('/missing-entities/<run_id>', methods=['GET'])
async def get_missing_entities(run_id: str):
    """Get entities for targeted scraping (UseCase2)"""
```

### 6. Configuration (`helpers/config/`)

#### Update `main.py`
```python
# Add MongoDB configuration
app.config['MONGODB_URI'] = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
app.config['MONGODB_DATABASE'] = os.getenv('MONGODB_DATABASE', 'aisports')

# Add NewsAPI configuration  
app.config['NEWSAPI_KEY'] = os.getenv('NEWSAPI_KEY')
app.config['NEWSAPI_SOURCES'] = ['bbc-sport', 'espn', 'four-four-two']

# Add collection settings
app.config['MAX_CONCURRENT_SCRAPING'] = int(os.getenv('MAX_CONCURRENT_SCRAPING', '5'))
app.config['CLEANUP_TEMP_FILES'] = os.getenv('CLEANUP_TEMP_FILES', 'true').lower() == 'true'
```

## Data Flow

### Full Collection Workflow
```
Frontend Button Click
    ↓
POST /api/collection/run
    ↓
CollectionOrchestrator.run_full_collection()
    ↓
1. Create run record in MongoDB
2. Parallel scraping (TR + EU sources) 
3. For each session file:
   - AI summarization → save to ai_summaries_per_source
4. AI aggregation by region → save to ai_aggregated_results  
5. Extend EU with NewsAPI → save to ai_aggregated_results
6. AI diff analysis → save to ai_diff_results
7. Update run status → completed
    ↓
Frontend polls /api/collection/status/{run_id}
    ↓
Frontend displays results via /api/results/run/{run_id}
```

### Targeted Scraping Workflow
```
User clicks missing entity from diff
    ↓
POST /api/collection/targeted
    ↓
CollectionOrchestrator.run_targeted_scraping()
    ↓
1. Create targeted run record
2. Scrape EU sources with new keywords
3. AI summarization per source → save to MongoDB
4. Return results for immediate display
    ↓
Frontend shows source-by-source results
```

### TR/EU Endpoint Workflow
```
GET /api/tr?days=7&limit=100
    ↓
Query ai_aggregated_results collection
    ↓
Filter by region=TR, created_at >= (now - 7 days)
    ↓
Return processed_articles array with pagination
    ↓
Frontend displays article objects per day/source
```

### Social Media Post Generation

#### Post Creation Workflow
```
User selects article objects → clicks "Prepare Posts"
    ↓
POST /api/post with article_ids and mode="make"
    ↓
AIPostMaker.create_posts_from_articles()
    ↓
For each article: Generate X/Twitter post content
    ↓
Save prepared posts to ai_posts collection
    ↓
Return post_ids to frontend
```

#### Post Publishing Workflow
```
User reviews prepared posts → clicks "Publish Selected"
    ↓
POST /api/post/publish with post_ids
    ↓
AIPostMaker.publish_multiple_posts()
    ↓
For each post: Publish to X/Twitter via API
    ↓
Update post status and store X post IDs
    ↓
Return publishing results
```

### Article Object Schema (Consistent Across All Endpoints)
```json
{
  "id": "article_1",
  "original_url": "https://www.fanatik.com.tr/...",
  "title": "Fenerbahçe'den Dario Saric hamlesi!",
  "summary": "AI-generated summary...",
  "key_entities": {
    "teams": ["Fenerbahçe Beko"],
    "players": ["Dario Saric"],
    "amounts": ["5.4M USD"],
    "dates": ["2014-2016"]
  },
  "categories": [
    {
      "tag": "transfers_rumors",
      "confidence": 0.9,
      "evidence": "Supporting text..."
    }
  ],
  "source": "www.fanatik.com.tr",
  "published_date": "2025-06-21T19:45:15+03:00",
  "keywords_matched": ["fenerbahce"],
  "content_quality": "high",
  "language": "turkish"
}
```

### Post Object Schema
```json
{
  "post_id": "post_20250624_001",
  "based_on_articles": ["article_1", "article_2"],
  "post_content": {
    "text": "🔥 TRANSFER ALERT: Fenerbahçe reportedly making moves for Dario Saric! #Fenerbahce #TransferNews",
    "hashtags": ["#Fenerbahce", "#TransferNews"],
    "mentions": ["@Fenerbahce"],
    "character_count": 95
  },
  "post_status": "prepared" | "published" | "failed",
  "created_at": "2025-06-24T15:30:00Z",
  "published_at": "2025-06-24T15:45:00Z",
  "x_post_id": "1234567890",
  "engagement_stats": {
    "likes": 12,
    "retweets": 3,
    "replies": 1
  }
}
```

## Implementation Phases

### Phase 1: Database Foundation
1. Enhance `mongodb_client.py` with all required methods
2. Create database indexes for performance
3. Add connection management and error handling
4. Create test scripts for database operations

### Phase 2: AI Processing Components  
1. Create `ai_aggregator.py` with AI prompt generation
2. Create `newsapi_service.py` for data integration
3. Test AI aggregation with sample data
4. Validate schema transformations

### Phase 3: Orchestration Layer
1. Create `collection_orchestrator.py` 
2. Implement full collection workflow
3. Implement targeted scraping workflow
4. Add comprehensive error handling and logging

### Phase 4: API Endpoints
1. Create collection endpoints
2. Create results endpoints
3. Create regional endpoints (/tr, /eu)
4. Create post endpoints (/post)
5. Add input validation and error responses
6. Create API documentation

### Phase 5: Social Media Integration
1. Create ai_post_maker.py capability
2. Implement X/Twitter integration
3. Add post management functionality
4. Test post generation and publishing

### Phase 6: Integration & Testing
1. End-to-end testing of both use cases
2. Performance optimization
3. Error scenarios testing
4. Frontend integration points

## Dependencies

### New Python Packages
```
pymongo>=4.6.0
motor>=3.3.0  # Async MongoDB driver
tweepy>=4.14.0  # X/Twitter API integration
```

### Environment Variables
```
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=aisports
NEWSAPI_KEY=your_newsapi_key
MAX_CONCURRENT_SCRAPING=5
PERSIST_RAW_DATA=true  # true for file persistence, false for memory only

# X/Twitter API Configuration
X_API_KEY=your_x_api_key
X_API_SECRET=your_x_api_secret
X_ACCESS_TOKEN=your_x_access_token
X_ACCESS_TOKEN_SECRET=your_x_access_token_secret
```

## Notes

- **Flexible Storage**: Supports both persistent (files) and memory-only modes via PERSIST_RAW_DATA config
- **Article-Focused**: Core schemas focus on article objects with consistent structure across all sources
- **Social Media Ready**: Built-in X/Twitter post generation and publishing capabilities
- **AI-First**: All processing steps use AI for intelligent content handling
- **Scalable**: Designed to handle multiple concurrent collection runs
- **Frontend Ready**: API structure supports real-time status updates and flexible data access
- **Journalist Integration**: Uses journalist package for web scraping (formerly journ4list)
