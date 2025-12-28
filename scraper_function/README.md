# Scraper Function

This directory contains the **Session Data Scraper Function** for the AISports event-driven microservices architecture.

## Overview

The scraper function is responsible for:
- Receiving scraping requests via Pub/Sub messages
- Using the `journalist` library to scrape content from news websites
- Storing scraped session data in Google Cloud Storage
- Publishing success/error messages to the `session-data-created` topic

## Files

- `main.py` - Main function code with scraping logic
- `requirements.txt` - Python dependencies
- `trigger_test.py` - Test script to trigger the function locally
- `README.md` - This file

## Configuration

The function uses the following environment variables:

- `GOOGLE_CLOUD_PROJECT` - Google Cloud project ID (default: gen-lang-client-0306766464)
- `GCS_BUCKET_NAME` - GCS bucket for storing session data (default: aisports-news-data)
- `SESSION_DATA_CREATED_TOPIC` - Pub/Sub topic for publishing results (default: session-data-created)
- `NEWS_DATA_ROOT_PREFIX` - Root prefix for GCS storage (default: news_data/)
- `ARTICLES_SUBFOLDER` - Subfolder for articles (default: articles/)

## GCS Folder Structure

The function stores scraped data in the following GCS structure:
```
news_data/
├── sources/
│   ├── <source_domain>/
│   │   ├── <YYYY-MM>/
│   │   │   ├── articles/
│   │   │   │   ├── session_data_<domain>_<session_id>.json
│   │   │   │   └── ...
```

## Message Format

### Input Message (Pub/Sub)
```json
{
  "urls": [
    "https://www.fanatik.com.tr/",
    "https://www.fotomac.com.tr/"
  ],
  "keywords": [
    "fenerbahce",
    "galatasaray",
    "mourinho"
  ]
}
```

### Output Message (Pub/Sub)
```json
{
  "status": "success",
  "gcs_path": "gs://aisports-news-data/news_data/sources/fanatik_com_tr/2025-01/articles/session_data_fanatik_com_tr_session_20250109_123456.json",
  "source_domain": "fanatik_com_tr",
  "session_id": "session_20250109_123456",
  "date_path": "2025-01",
  "articles_count": 15,
  "keywords": ["fenerbahce", "galatasaray", "mourinho"],
  "processed_at": "2025-01-09T12:34:56.789Z"
}
```

## Dependencies

- `google-cloud-pubsub` - For Pub/Sub messaging
- `google-cloud-storage` - For GCS file operations
- `journ4list` - For web scraping (exports `journalist`)

## Testing

Run the trigger test script to test the function locally:

```bash
python trigger_test.py
```

This will publish test messages to the `scraping-requests` topic and trigger the function.

## Deployment

### Automated Deployment (Recommended)

The function is automatically deployed via GitHub Actions when changes are pushed to `dev` or `feature/*` branches. The workflow file is located at `.github/workflows/deploy-scraper-function.yml`.

**Authentication:** Uses Workload Identity Federation (keyless) - no service account keys required.

The deployment workflow is triggered when:
- Files in `scraper_function/` are modified
- Files in `shared_libs/` are modified

For production deployments to `main`, use `deploy-all.yml` workflow.

### Prerequisites for Manual Deployment

1. Ensure you have the Google Cloud CLI installed and authenticated
2. Set up the required Pub/Sub topics:
   - `scraping-requests` (trigger topic)
   - `session-data-created` (output topic)
3. Create the GCS bucket: `aisports-news-data`
4. Ensure the service account has the necessary permissions

### Manual Deployment (For Testing)

If you need to deploy manually for testing purposes:

```bash
gcloud functions deploy scrape-and-store \
  --gen2 \
  --runtime=python39 \
  --source=. \
  --entry-point=scrape_and_store \
  --trigger-topic=scraping-requests \
  --region=us-central1 \
  --project=gen-lang-client-0306766464 \
  --service-account=svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464,GCS_BUCKET_NAME=aisports-news-data,SESSION_DATA_CREATED_TOPIC=session-data-created,NEWS_DATA_ROOT_PREFIX=news_data/,ARTICLES_SUBFOLDER=articles/" \
  --timeout=540 \
  --memory=512MB \
  --max-instances=10
```

## Monitoring

After deployment, monitor the function using:

1. **Cloud Functions Console** - View function logs and metrics
2. **Cloud Logging** - Search for function logs
3. **Cloud Monitoring** - Set up alerts for function errors

## Error Handling

The function includes comprehensive error handling:
- Publishes error messages to the same topic with `status: "error"`
- Logs detailed error information
- Handles missing journalist library gracefully
- Validates input message format

## Local Development

For local development and testing, you can run the scraper function without Pub/Sub:

### Method 1: Using the Local Runner Script

1. Copy the environment template:
   ```bash
   copy .env.example .env
   ```

2. Edit `.env` file with your settings:
   ```
   ENVIRONMENT=local
   JOURNALIST_LOG_LEVEL=INFO
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the local script:
   ```bash
   python run_local.py
   ```

### Method 2: Running main.py Directly

1. Set the environment variable:
   ```bash
   set ENVIRONMENT=local
   ```

2. Run main.py:
   ```bash
   python main.py
   ```

### Local Execution Behavior

When `ENVIRONMENT=local`:
- **Skips Pub/Sub publishing** - No messages are published to topics
- **Skips GCS upload** - Files are saved locally instead
- **Creates local output structure** - Files are organized in `./local_output/` directory
- **Uses test data** - Uses the same test data from `trigger_test.py`
- **Enhanced logging** - All operations are logged for debugging

### Local Output Structure

Results are saved in:
```
./local_output/
├── sources/
│   ├── <source_domain>/
│   │   ├── <YYYY-MM-DD>/
│   │   │   ├── articles/
│   │   │   │   ├── session_data_<domain>_<session_id>.json
```

## Pipeline Position

The scraper function outputs trigger the downstream processing pipeline:

```
scraper_function → article_processor_function → merge_decider_function → article_enricher_function
      │                      │                          │                         │
      ▼                      ▼                          ▼                         ▼
scraped_*.json        singleton_*.json           decision_*.json          enriched_*.json
                      grouped_*.json
```

## Related Functions

- **news_api_fetcher_function**: Upstream - may trigger scraper for incomplete articles via `to_scrape.json`
- **article_processor_function**: Downstream - processes scraped articles (dedup, group)
- **merge_decider_function**: Downstream - LLM merge decisions on grouped articles
- **article_enricher_function**: Downstream - generates summaries, translations, X posts