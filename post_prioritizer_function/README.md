# Post Prioritizer Function

Cloud Function that processes deduplicated prediction results and prioritizes posts based on content categories and sport type.

## Overview

This function is triggered when Vertex AI deduplication jobs complete and write `predictions.jsonl` files to the `dedup_results/` folder in GCS. It downloads the predictions, extracts articles, applies prioritization logic, and outputs the top N posts.

## Prioritization Rules

The function implements the following prioritization logic:

### 1. **Sport Priority**
- **Football**: 1.5x multiplier (highest priority)
- **Basketball**: 1.0x multiplier
- **Other sports**: 0.8x multiplier

### 2. **Category Priorities**

#### Highest Priority (100-90 points)
- **Transfer news** (biggest priority)
  - `transfers_confirmed`: 100 points
  - `transfers_negotiations`: 95 points
  - `transfers_rumors`: 90 points
  - `transfers_interest`: 85 points
  - `departures`: 80 points

#### High Priority (80-70 points)
- **Derbys and rivalries** (great priority)
  - `team_rivalry`: 85 points (+ 20 bonus if "derby" keyword detected)
- **Scandals and fights** (high priority)
  - `off_field_scandals`: 80 points
  - `field_incidents`: 75 points
  - `corruption_allegations`: 75 points
  - `contract_disputes`: 75 points
  - `disciplinary_actions`: 70 points

#### Medium Priority (60-50 points)
- Match results, performance analysis, injuries, etc.

#### Low Priority (<50 points)
- Personal life, social media, lifestyle news

### 3. **Bonus Points**
- **Derby matches**: +20 points (when "derby" keywords detected in title/summary)

## Trigger

The function is triggered by Google Cloud Storage events:

**Event Type**: `google.storage.object.finalize`  
**Filter Pattern**: `dedup_results/**/predictions.jsonl`

Example trigger path:
```
gs://aisports-scraping/news_data/batch_processing/2025-11/dedup_results/dedup_20251107_115120/prediction-model-2025-11-07T11:51:21.908961Z/predictions.jsonl
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID | `gen-lang-client-0306766464` |
| `GCS_BUCKET_NAME` | GCS bucket name | `aisports-scraping` |
| `NEWS_DATA_ROOT_PREFIX` | Root prefix for news data | `news_data/` |
| `BATCH_PROCESSING_FOLDER` | Batch processing folder | `batch_processing/` |
| `DEDUP_RESULTS_FOLDER` | Deduplication results folder | `dedup_results/` |
| `PRIORITIZED_POSTS_FOLDER` | Output folder for prioritized posts | `prioritized_posts/` |
| `NUM_TOP_POSTS` | Number of top posts to select | `10` |
| `ENVIRONMENT` | Environment (local/development) | `development` |

## Input Format

The function expects `predictions.jsonl` files from Vertex AI deduplication jobs with the following structure:

```jsonl
{
  "response": {
    "candidates": [
      {
        "content": {
          "parts": [
            {
              "text": "{\"processed_articles\": [{\"id\": \"...\", \"title\": \"...\", \"categories\": [...], ...}]}"
            }
          ]
        }
      }
    ]
  }
}
```

## Output Format

The function outputs a JSON file to GCS with prioritized posts:

**Output Path**: `news_data/batch_processing/{YYYY-MM}/prioritized_posts/{dedup_id}_prioritized_posts.json`

**Structure**:
```json
{
  "metadata": {
    "created_at": "2025-11-07T11:51:21.908961Z",
    "source_file": "gs://...",
    "dedup_id": "dedup_20251107_115120",
    "num_posts": 10,
    "prioritization_rules": {
      "football_vs_basketball": "Football has 1.5x multiplier",
      "derbys": "+20 bonus points",
      "transfers": "100 (highest) to 85 points",
      "scandals": "70-80 points"
    }
  },
  "prioritized_posts": [
    {
      "id": "article_123",
      "title": "...",
      "summary": "...",
      "categories": [...],
      "priority_score": 150.0,
      "sport": "football",
      "is_derby": true,
      ...
    }
  ]
}
```

## Deployment

### Using GitHub Actions (Automated)

The function is automatically deployed when changes are pushed to the `main` branch via the GitHub Actions workflow.

### Manual Deployment

```bash
gcloud functions deploy post-prioritizer-function \
  --gen2 \
  --runtime=python312 \
  --region=us-central1 \
  --source=. \
  --entry-point=post_prioritizer_function \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=aisports-scraping" \
  --trigger-event-filters-path-pattern="name=news_data/batch_processing/**/dedup_results/**/predictions.jsonl" \
  --memory=512MB \
  --timeout=540s \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464,\
GCS_BUCKET_NAME=aisports-scraping,\
NEWS_DATA_ROOT_PREFIX=news_data/,\
BATCH_PROCESSING_FOLDER=batch_processing/,\
DEDUP_RESULTS_FOLDER=dedup_results/,\
PRIORITIZED_POSTS_FOLDER=prioritized_posts/,\
NUM_TOP_POSTS=10" \
  --service-account=cloud-functions-sa@gen-lang-client-0306766464.iam.gserviceaccount.com
```

## Local Testing

1. Set up environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Authenticate with GCP:
   ```bash
   gcloud auth application-default login
   ```

3. Run local test:
   ```bash
   export ENVIRONMENT=local
   python main.py
   ```

## Data Flow

```
1. Vertex AI Deduplication Job Completes
   ↓
2. Writes predictions.jsonl to dedup_results/
   ↓ triggers GCS event
   
3. Post Prioritizer Function
   ↓ downloads predictions.jsonl
   ↓ extracts processed_articles
   ↓ calculates priority scores
   ↓ sorts by score (descending)
   ↓ selects top N posts
   ↓ saves to prioritized_posts/
   
4. Output: {dedup_id}_prioritized_posts.json
```

## Monitoring

View function logs:
```bash
gcloud functions logs read post-prioritizer-function \
  --region=us-central1 \
  --limit=50
```

Check for errors:
```bash
gcloud functions logs read post-prioritizer-function \
  --region=us-central1 \
  --filter="severity>=ERROR" \
  --limit=20
```

## Example Use Cases

### High-Priority Post Examples

1. **Transfer Confirmed (Football)**
   - Category: `transfers_confirmed` (100 pts)
   - Sport: Football (×1.5)
   - **Final Score**: 150

2. **Derby Match with Transfer Rumors**
   - Category: `transfers_rumors` (90 pts)
   - Sport: Football (×1.5)
   - Derby Bonus: +20
   - **Final Score**: 155

3. **Basketball Scandal**
   - Category: `off_field_scandals` (80 pts)
   - Sport: Basketball (×1.0)
   - **Final Score**: 80

4. **Football Field Incident**
   - Category: `field_incidents` (75 pts)
   - Sport: Football (×1.5)
   - **Final Score**: 112.5

## Architecture Integration

This function is part of the AI Sports Functions pipeline:

```
Scraper Function
  ↓
Batch Builder Function
  ↓
Vertex AI Batch Processing
  ↓
Result Merger Function
  ↓
Vertex AI Deduplication
  ↓
Post Prioritizer Function ← YOU ARE HERE
  ↓
(Future: Social Media Publisher / Database Storage)
```

## Notes

- The function only processes files ending with `predictions.jsonl` in the `dedup_results/` folder
- Priority scores are calculated using weighted category scores, sport multipliers, and derby bonuses
- Articles without categories receive a default priority of 0
- The function uses the highest-scoring category for each article (weighted by confidence)
- Output files use the dedup_id from the source path for traceability
