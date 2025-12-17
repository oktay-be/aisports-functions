# Plan: News API Content Enrichment & Integration Architecture

## 50,000 Feet View: Complete News Pipeline Architecture

### Current State

**News API Fetcher Pipeline:**
```
NewsAPI/GNews/WorldNewsAPI
  ↓ (truncated content "[497 chars]")
articles.json → GCS: news_data/api/{YYYY-MM}/{YYYY-MM-DD}/run_{HH-MM-SS}/
  ↓
Frontend (incomplete articles)
```

**Scraper Pipeline:**
```
Pub/Sub: scraping-requests
  ↓
Scraper Function (Journalist library)
  ↓
GCS: news_data/sources/{collection_id}/{YYYY-MM}/{YYYY-MM-DD}/{source}/session_data_*.json
  ↓ (publishes to session-data-created)
Batch Processing Function
  ↓
AI Processing (predictions, translations, X posts)
  ↓
GCS: news_data/batch_processing/{collection_id}/{YYYY-MM}/{YYYY-MM-DD}/
```

### Problems

1. **Content Truncation**: API articles have truncated content ("[497 chars]")
2. **No AI Processing**: API articles don't go through AI enrichment
3. **Folder Structure Mismatch**: API articles and scraped articles live in separate hierarchies
4. **No Integration**: Two parallel pipelines that don't interact

---

## Proposed Solution: Unified News Pipeline

### New Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     NEWS API FETCHER                          │
│                                                               │
│  NewsAPI/GNews/WorldNewsAPI                                  │
│         ↓                                                     │
│  Classify by Completeness & Region                           │
│         ↓                                                     │
│  ┌──────────────────┬───────────────────┐                   │
│  │  Complete         │  Incomplete        │                   │
│  │  Content          │  Content           │                   │
│  │  (full text)      │  ([497 chars])     │                   │
│  └──────────────────┴───────────────────┘                   │
│         │                      │                              │
│         │                      └─────────┐                    │
│         ↓                                 ↓                    │
│  articles.json                   Trigger Scraper              │
│  (complete)                      via Pub/Sub                  │
│         │                        (by region: tr/eu)           │
│         │                                 │                    │
│         │                                 ↓                    │
│         │                      ┌──────────────────┐          │
│         │                      │ SCRAPER FUNCTION │          │
│         │                      │  (Journalist)     │          │
│         │                      └──────────────────┘          │
│         │                                 │                    │
│         │                      articles_scraped.json          │
│         │                      (scraped full content)         │
│         │                                 │                    │
│         └─────────────┬───────────────────┘                   │
│                       ↓                                        │
│              MERGED ARTICLES                                  │
│         (complete + scraped)                                  │
│                       ↓                                        │
│         AI PROCESSING                                         │
│    (predictions, translations, X posts)                       │
│                       ↓                                        │
│         enriched_articles.json                                │
└─────────────────────────────────────────────────────────────┘
```

### Unified Folder Structure

```
gs://aisports-scraping/
  news_data/
    api/
      {YYYY-MM}/
        {YYYY-MM-DD}/
          run_{HH-MM-SS}/                # Single run folder
            ├── articles.json             # Complete articles from APIs (both TR & EU)
            ├── articles_scraped_tr.json  # Scraped Turkish incomplete articles
            ├── articles_scraped_eu.json  # Scraped EU incomplete articles
            ├── enriched_articles.json    # AI-enriched (predictions, translations)
            ├── metadata.json
            └── responses/                # Raw API responses
                ├── newsapi.json
                ├── worldnewsapi.json
                └── gnews.json
```

**Note**: Two separate scraped files prevent race conditions when TR and EU scrapers run in parallel.

---

## Implementation Plan

### Phase 1: Content Completeness Detection

**File**: `news_aggregator.py`

**Detect Truncated Content**:
```python
def is_content_complete(content: str) -> bool:
    """
    Check if article content is complete or truncated.

    Truncation indicators:
    - Ends with "[+N chars]" or "[N chars]"
    - Content length < 200 chars (suspiciously short)
    - Ends with "..." followed by char count

    Returns:
        True if content appears complete, False if truncated
    """
    if not content:
        return False

    # Check for explicit truncation markers
    import re
    if re.search(r'\[[\+]?\d+\s*chars?\]$', content.strip()):
        return False

    # Check for suspiciously short content
    if len(content.strip()) < 200:
        return False

    return True
```

**Region Classification**:
```python
def classify_region(article: dict, api_source: str) -> str:
    """
    Determine collection_id (tr/eu) based on language.

    Args:
        article: Article dict with language info
        api_source: 'newsapi', 'worldnewsapi', or 'gnews'

    Returns:
        'tr' for Turkish, 'eu' for everything else
    """
    # WorldNewsAPI uses 'language' field
    if api_source == 'worldnewsapi':
        lang = article.get('language', '').lower()
    # GNews uses 'lang' field
    elif api_source == 'gnews':
        lang = article.get('lang', '').lower()
    # NewsAPI - infer from content or use default
    else:
        lang = article.get('language', 'en').lower()

    # Turkish articles go to 'tr' collection
    return 'tr' if lang == 'tr' else 'eu'
```

### Phase 2: Split Articles by Completeness

**File**: `main.py` in `news_api_fetcher_function`

**After fetching articles, before deduplication**:
```python
# Classify articles
complete_articles = []
incomplete_articles_by_region = {'tr': [], 'eu': []}

for article in processed_articles:
    # Determine region first
    region = classify_region(article, article.get('api_source'))
    article['collection_id'] = region

    # Check completeness
    content = article.get('content', '')
    if is_content_complete(content):
        complete_articles.append(article)
    else:
        incomplete_articles_by_region[region].append(article)

logger.info(f"Complete articles: {len(complete_articles)}")
logger.info(f"Incomplete TR articles: {len(incomplete_articles_by_region['tr'])}")
logger.info(f"Incomplete EU articles: {len(incomplete_articles_by_region['eu'])}")
```

### Phase 3: Save Complete Articles Only

**Save `articles.json` with complete articles**:
```python
# After deduplication, save only complete articles
articles_path = f"{base_path}/articles.json"
upload_to_gcs(GCS_BUCKET_NAME, articles_path, {
    'articles': complete_articles,  # Only complete ones
    'count': len(complete_articles),
    'fetched_at': now.isoformat()
})
```

### Phase 4: Trigger Scraper for Incomplete Articles

**New Function: `trigger_scraper_for_incomplete_articles()`**:
```python
async def trigger_scraper_for_incomplete_articles(
    incomplete_by_region: dict,
    base_path: str,
    keywords: list,
    triggered_by: str
):
    """
    Trigger scraper function via Pub/Sub for incomplete articles.

    Args:
        incomplete_by_region: {'tr': [articles], 'eu': [articles]}
        base_path: GCS path for this run
        keywords: Keywords used
        triggered_by: Who triggered this run
    """
    if not publisher:
        logger.warning("Publisher not available, skipping scraper trigger")
        return

    for region, articles in incomplete_by_region.items():
        if not articles:
            continue

        # Extract URLs
        urls = [article.get('url') or article.get('original_url')
                for article in articles if article.get('url') or article.get('original_url')]

        if not urls:
            continue

        # Prepare Pub/Sub message with region-specific filename
        message_data = {
            "urls": urls,
            "keywords": keywords,
            "scrape_depth": 0,  # No link discovery, just scrape given URLs
            "persist": False,   # Memory-only mode
            "collection_id": region,
            "triggered_by": triggered_by,
            "api_run_path": base_path,  # NEW: Tell scraper where to save
            "output_filename": f"articles_scraped_{region}.json"  # NEW: Region-specific filename
        }

        # Publish to scraping-requests topic
        topic_path = publisher.topic_path(PROJECT_ID, 'scraping-requests')
        data = json.dumps(message_data).encode("utf-8")
        future = publisher.publish(topic_path, data)
        message_id = future.result()

        logger.info(f"Triggered scraper for {len(urls)} {region} articles (message_id: {message_id})")
```

### Phase 5: Modify Scraper Function Output Path

**File**: `scraper_function/main.py`

**New behavior based on `api_run_path` parameter**:
```python
async def _process_scraping_request(message_data: dict):
    # ... existing code ...

    # NEW: Check if triggered from News API fetcher
    api_run_path = message_data.get("api_run_path")
    output_filename = message_data.get("output_filename", "articles_scraped.json")

    if api_run_path:
        # Save to API run folder instead of sources folder
        gcs_object_path = f"{api_run_path}/{output_filename}"
        logger.info(f"API integration mode: saving to {gcs_object_path}")

        # Merge all sessions into single file
        all_articles = []
        for session in source_sessions:
            all_articles.extend(session.get("articles", []))

        # Upload merged articles
        upload_data = {
            'articles': all_articles,
            'count': len(all_articles),
            'scraped_at': datetime.now(timezone.utc).isoformat(),
            'scrape_method': 'journalist',
            'collection_id': collection_id
        }

        blob = bucket.blob(gcs_object_path)
        blob.upload_from_string(
            json.dumps(upload_data, indent=2, ensure_ascii=False),
            content_type='application/json'
        )

        # Do NOT publish to session-data-created (no batch processing yet)
        logger.info(f"Saved scraped articles to {gcs_object_path}")
        return

    # Otherwise, use existing logic (sources folder + batch processing)
    # ... existing code ...
```

### Phase 6: AI Processing Integration

**New Function: `trigger_ai_processing()`** (Future enhancement):
```python
async def trigger_ai_processing(base_path: str, collection_id: str):
    """
    Trigger AI processing for both complete and scraped articles.

    Reads:
        - articles.json (complete articles)
        - articles_scraped.json (scraped articles)

    Processes:
        - Generate predictions
        - Translate non-Turkish articles
        - Generate X post suggestions

    Writes:
        - enriched_articles.json
    """
    # To be implemented in future phase
    pass
```

---

## Data Flow Examples

### Example 1: All Complete Articles

```
News API Fetch (60 articles, all complete)
  ↓
Classify by region: 40 TR, 20 EU
  ↓
Deduplicate
  ↓
Save to articles.json (60 articles)
  ↓
No scraper trigger needed
  ↓
Done
```

### Example 2: Mixed Complete/Incomplete

```
News API Fetch (60 articles)
  ├─ 30 complete
  └─ 30 incomplete (20 TR, 10 EU)
  ↓
Save complete → articles.json (30 articles)
  ↓
Trigger scraper (2 Pub/Sub messages in parallel):
  ├─ TR scraper (20 URLs) → articles_scraped_tr.json
  └─ EU scraper (10 URLs) → articles_scraped_eu.json
  ↓
Result:
  - articles.json (30 complete, both TR & EU)
  - articles_scraped_tr.json (20 scraped TR)
  - articles_scraped_eu.json (10 scraped EU)
  - Total: 60 articles with full content
```

### Example 3: With AI Processing (Future)

```
Merge 3 files:
  - articles.json (30 complete)
  - articles_scraped_tr.json (20 TR)
  - articles_scraped_eu.json (10 EU)
  ↓
Process through AI (by region)
  ↓
enriched_articles.json (60 articles with):
  - Full content
  - Predictions (region-specific models)
  - Translations (EU → TR if needed)
  - X post suggestions
```

---

## Benefits of New Architecture

### 1. **Unified Storage**
- All data for a single run in one folder
- Easy to track what was fetched vs scraped
- Simplified downstream processing

### 2. **No Duplicate Scraping**
- Scraper only processes incomplete articles
- Complete articles bypass scraping entirely
- Faster, more efficient

### 3. **Proper Region Classification**
- Articles classified before storage
- Enables region-specific AI processing
- Maintains existing scraper's region logic

### 4. **Extensible for AI**
- Clear separation of fetch → scrape → enrich
- Can add AI processing as next phase
- Follows existing batch processing pattern

### 5. **Backwards Compatible**
- Scraper still works independently (sources folder)
- API fetcher works independently (articles.json only)
- New integration is additive, not breaking

---

## Implementation Phases

### Phase 1: Detection & Classification (1-2 hours)
- Add `is_content_complete()` to news_aggregator.py
- Add `classify_region()` to news_aggregator.py
- Test with existing GCS data

### Phase 2: Split & Save (1 hour)
- Modify main.py to split articles
- Save only complete to articles.json
- Add metadata about incomplete count

### Phase 3: Scraper Integration (2-3 hours)
- Add Pub/Sub trigger logic
- Modify scraper to accept `api_run_path`
- Modify scraper to save to custom location
- Test end-to-end with sample incomplete articles

### Phase 4: Testing & Validation (1-2 hours)
- Test with real API responses
- Verify correct region classification
- Verify scraper saves to correct location
- Validate merged output

### Phase 5: AI Integration (Future)
- Design AI processing function
- Integrate with existing batch processing
- Add predictions, translations, X posts

---

## Critical Files to Modify

### News API Fetcher
1. `/home/neo/aisports/aisports-functions/news_api_fetcher_function/news_aggregator.py`
   - Add `is_content_complete()`
   - Add `classify_region()`
   - Modify article processing to include completeness check

2. `/home/neo/aisports/aisports-functions/news_api_fetcher_function/main.py`
   - Add `trigger_scraper_for_incomplete_articles()`
   - Modify `fetch_and_store_news()` to split complete/incomplete
   - Add Pub/Sub publisher initialization

### Scraper Function
3. `/home/neo/aisports/aisports-functions/scraper_function/main.py`
   - Modify `_process_scraping_request()` to check for `api_run_path`
   - Add alternative save path logic
   - Skip batch processing publish when in API integration mode

---

## Open Questions

1. **Retry Logic**: What if scraper fails? Should we retry incomplete articles?
   - **Recommendation**: Let Cloud Functions handle retries (max 3 attempts)

2. **Timeout**: What if scraping 30 URLs takes too long?
   - **Recommendation**: Use scrape_depth=0 (no discovery) for speed
   - **Recommendation**: Set reasonable timeout (5 min for Cloud Function)

3. **Partial Success**: What if some URLs scrape successfully but others fail?
   - **Recommendation**: Save partial results, log failures
   - **Recommendation**: Don't block on failures

4. **AI Processing Trigger**: How to know when both articles.json and articles_scraped.json are ready?
   - **Recommendation**: Use Cloud Storage triggers on articles_scraped.json creation
   - **Recommendation**: Or wait for Phase 5 design

---

## Expected Outcomes

### Before Implementation
```
news_data/api/2025-12/2025-12-17/run_10-00-14/
  ├── articles.json (60 articles, many with truncated content)
  └── responses/ (raw API data)

news_data/sources/tr/2025-12/2025-12-17/hurriyet_com/
  └── session_data_*.json (separate scraping run)
```

### After Implementation
```
news_data/api/2025-12/2025-12-17/run_10-00-14/
  ├── articles.json (30 complete articles)
  ├── articles_scraped_tr.json (20 scraped TR)
  ├── articles_scraped_eu.json (10 scraped EU)
  ├── metadata.json (includes incomplete_count: 30)
  └── responses/ (raw API data)

# Scraper sources folder still works independently for non-API scraping
news_data/sources/tr/2025-12/2025-12-17/hurriyet_com/
  └── session_data_*.json (independent scraping runs)
```

---

## Performance Considerations

- **API Fetch**: ~5-10 seconds (unchanged)
- **Deduplication**: ~1 second (unchanged)
- **Pub/Sub Trigger**: ~1-2 seconds (new, async)
- **Scraper**: ~30-60 seconds for 30 URLs (new, parallel)
- **Total**: ~40-70 seconds (vs 5-10 seconds before, but with full content!)

**Cloud Function Timeout**: Set to 300 seconds (5 min) to accommodate scraping

---

## Rollback Plan

If implementation causes issues:

1. **Remove Pub/Sub trigger** - Goes back to complete articles only
2. **Keep folder structure** - Still compatible with existing setup
3. **Scraper unchanged** - Can still work independently

**Risk: Low** - Changes are additive, not destructive