# Result Merger Function

This Cloud Function merges multiple AI candidate responses from Vertex AI batch predictions and creates deduplication batch jobs.

## Overview

When Vertex AI completes batch processing, it creates multiple candidates per source file. This function:

1. **Subscribes to GCS Events**: Triggered when prediction files are created
2. **Merges Candidates**: Combines articles from all candidates into one dataset
3. **Analyzes with Pandas**: Provides statistics about merged data
4. **Uploads Merged Data**: Stores consolidated results in GCS
5. **Creates Dedup Requests**: Generates new batch jobs for deduplication
6. **Submits to Vertex AI**: Runs final deduplication pass

## Architecture

```
GCS Event (prediction file created)
         ↓
  Result Merger Function
         ↓
    [Merge Logic]
    - Download predictions JSONL
    - Parse candidates
    - Merge articles per source
    - Analyze with pandas
    - Upload merged JSON
         ↓
   [Dedup Request]
    - Load DEDUP_PROMPT.md
    - Create dedup batch JSONL
    - Upload to GCS
    - Submit Vertex AI job
         ↓
  Publish to dedup-job-created
```

## Environment Variables

### Required
- `GOOGLE_CLOUD_PROJECT`: GCP project ID (e.g., "gen-lang-client-0306766464")
- `GCS_BUCKET_NAME`: Main storage bucket (e.g., "aisports-scraping")

### Optional (with defaults)
- `DEDUP_JOB_CREATED_TOPIC`: Pub/Sub topic name (default: "dedup-job-created")
- `NEWS_DATA_ROOT_PREFIX`: Root GCS prefix (default: "news_data/")
- `BATCH_PROCESSING_FOLDER`: Batch folder (default: "batch_processing/")
- `BATCH_RESULTS_RAW_FOLDER`: Raw batch results folder (default: "batch_results_raw/")
- `BATCH_RESULTS_MERGED_FOLDER`: Merged results folder (default: "batch_results_merged/")
- `DEDUP_RESULTS_FOLDER`: Dedup results folder (default: "dedup_results/")
- `VERTEX_AI_LOCATION`: Vertex AI region (default: "us-central1")
- `VERTEX_AI_MODEL`: AI model (default: "gemini-2.5-pro")
- `ENVIRONMENT`: Set to "local" for testing (default: "development")

## GCS Trigger Configuration

The function is triggered by:
- **Event Type**: `google.cloud.storage.object.v1.finalized`
- **Resource Pattern**: `news_data/batch_processing/*/batch_results_raw/*_predictions.jsonl`

When Vertex AI completes a batch job, it writes prediction files to:
```
gs://aisports-scraping/news_data/batch_processing/2025-11/batch_results_raw/20251106_103000_001/
  prediction-model-2025-11-06T10_30_00.123456Z/
    predictions.jsonl
```

This triggers the function automatically.

## Input Format (Prediction JSONL)

Each line in the prediction file:
```json
{
  "request": { /* original batch request */ },
  "response": {
    "candidates": [
      {
        "content": {
          "parts": [{"text": "{...processed_articles JSON...}"}]
        },
        "avgLogprobs": -0.11464,
        "finishReason": "STOP"
      },
      {
        "content": {
          "parts": [{"text": "{...processed_articles JSON...}"}]
        },
        "avgLogprobs": -0.10573,
        "finishReason": "STOP"
      }
    ]
  }
}
```

## Processing Steps

### 1. Download & Parse
```python
predictions = merger.download_prediction_file(gcs_uri)
# Returns list of prediction objects
```

### 2. Merge Candidates
```python
merged_by_source = merger.create_merged_dataset(predictions)
# Combines articles from all candidates per source
# Adds _merge_metadata to each article
```

### 3. Pandas Analysis
```python
dataset = merger.analyze_with_pandas(merged_data)
# Adds statistics:
# - unique_urls
# - content_quality_distribution
# - language_distribution
# - published_date_range
```

### 4. Upload Merged Data
```python
uploaded_files = merger.upload_merged_data(merged_by_source, batch_id)
# Uploads to: gs://bucket/news_data/batch_processing/YYYY-MM/merged_results/batch_ID/merged_SOURCE.json
```

### 5. Create Dedup Request
```python
dedup_prompt = merger.load_dedup_prompt()  # From DEDUP_PROMPT.md
local_jsonl = merger.create_dedup_batch_request(merged_files, dedup_prompt, batch_id)
# Creates JSONL with merged files as input
```

### 6. Submit Dedup Job
```python
job_name, output_uri = merger.submit_dedup_batch_job(dedup_request_uri, batch_id)
# Submits to Vertex AI with candidateCount=1, temperature=0.05
```

### 7. Publish Event
```python
publisher.publish(DEDUP_JOB_CREATED_TOPIC, dedup_message)
# Notifies downstream systems
```

## Output Locations

### Merged Data
```
gs://aisports-scraping/news_data/batch_processing/2025-11/batch_results_merged/
  batch_dedup_20251106_103000/
    merged_session_data_fanatik.com.tr.json
    merged_session_data_sporx.com.json
```

### Dedup Request
```
gs://aisports-scraping/news_data/batch_processing/2025-11/
  dedup_batch_20251106_103000/
    request.jsonl
```

### Dedup Results (from Vertex AI)
```
gs://aisports-scraping/news_data/batch_processing/2025-11/dedup_results/
  dedup_20251106_103000/
    prediction-model-2025-11-06T10_30_01.234567Z/
      predictions.jsonl
```

## Merged Dataset Structure

```json
{
  "source_file": "gs://bucket/path/session_data_example.com.json",
  "source_domain": "example.com",
  "merge_timestamp": "2025-01-15T10:30:00Z",
  "merge_statistics": {
    "total_articles_before_dedup": 77,
    "num_candidates_merged": 2,
    "candidates_avg_logprobs": [-0.11464, -0.10573],
    "pandas_analysis": {
      "unique_urls": 45,
      "unique_sources": ["example.com"],
      "content_quality_distribution": {"high": 50, "medium": 20, "low": 7},
      "language_distribution": {"tr": 77},
      "avg_categories_per_article": 2.3,
      "published_date_range": {
        "earliest": "2025-01-14T08:00:00Z",
        "latest": "2025-01-15T09:30:00Z"
      }
    }
  },
  "articles": [
    {
      "original_url": "https://example.com/article1",
      "title": "...",
      "summary": "...",
      "source": "example.com",
      "published_date": "2025-01-15T08:00:00Z",
      "categories": ["football", "super-lig"],
      "key_entities": {
        "teams": ["Fenerbahçe"],
        "players": ["Dzeko"],
        "competitions": ["Süper Lig"],
        "locations": ["İstanbul"]
      },
      "content_quality": "high",
      "confidence": 0.95,
      "language": "tr",
      "_merge_metadata": {
        "candidate_index": 1,
        "candidate_avg_logprobs": -0.10573,
        "finish_reason": "STOP"
      }
    }
  ]
}
```

## Deduplication Request Format

```json
{
  "request": {
    "contents": [
      {
        "role": "user",
        "parts": [
          {"text": "<contents of DEDUP_PROMPT.md>"},
          {
            "fileData": {
              "fileUri": "gs://bucket/path/merged_example.com.json",
              "mimeType": "application/json"
            }
          }
        ]
      }
    ],
    "generationConfig": {
      "candidateCount": 1,
      "temperature": 0.05,
      "topP": 0.9,
      "maxOutputTokens": 65535,
      "responseMimeType": "application/json",
      "responseSchema": { /* VERTEX_AI_RESPONSE_SCHEMA */ }
    }
  }
}
```

## Published Message Format

Topic: `dedup-job-created`

```json
{
  "status": "dedup_job_created",
  "batch_id": "dedup_20250115_103000",
  "job_name": "projects/.../locations/.../batchPredictionJobs/...",
  "output_uri": "gs://bucket/path/dedup_results/dedup_20250115_103000/",
  "source_prediction_file": "gs://bucket/path/original_predictions.jsonl",
  "merged_files": [
    "gs://bucket/path/merged_example1.json",
    "gs://bucket/path/merged_example2.json"
  ],
  "num_sources": 2,
  "vertex_ai_model": "gemini-2.5-pro",
  "vertex_ai_location": "us-central1",
  "created_at": "2025-01-15T10:30:00.123456Z"
}
```

## Deployment

Deploy with GitHub Actions:

```yaml
- name: Deploy Result Merger Function
  run: |
    gcloud functions deploy result-merger-function \
      --gen2 \
      --runtime=python312 \
      --region=us-central1 \
      --source=./result_merger_function \
      --entry-point=merge_results \
      --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
      --trigger-event-filters="bucket=aisports-scraping" \
      --trigger-event-filters-path-pattern="object=news_data/batch_processing/*/batch_results_raw/*_predictions.jsonl" \
      --memory=1Gi \
      --timeout=540s \
      --set-env-vars="GOOGLE_CLOUD_PROJECT=${{ env.PROJECT_ID }},GCS_BUCKET_NAME=aisports-scraping,DEDUP_JOB_CREATED_TOPIC=dedup-job-created,BATCH_RESULTS_RAW_FOLDER=batch_results_raw/,BATCH_RESULTS_MERGED_FOLDER=batch_results_merged/,DEDUP_RESULTS_FOLDER=dedup_results/"
```

## Local Testing

```bash
# Set environment
export ENVIRONMENT=local
export GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464
export GCS_BUCKET_NAME=aisports-scraping

# Run with test data
python main.py
```

The `main.py` includes a `__main__` block with test file data.

## Monitoring

### Logs
```bash
gcloud functions logs read result-merger-function --region=us-central1 --limit=50
```

### Key Log Messages
- "Result Merger Function initialized"
- "Processing prediction file: gs://..."
- "Downloaded and parsed N prediction entries"
- "Merged X articles from candidate Y"
- "Total merged articles: Z"
- "Pandas analysis complete: W unique URLs found"
- "Uploaded merged data for source to gs://..."
- "Dedup batch job submitted successfully!"
- "Dedup job message published to dedup-job-created"

### Metrics to Monitor
- Number of predictions processed
- Number of candidates merged per source
- Total articles before deduplication
- Number of unique URLs (from pandas)
- Dedup job submission success rate
- Processing time per prediction file

## Error Handling

The function handles:
- Missing or malformed prediction files
- JSON parsing errors in candidates
- Missing source URIs in requests
- GCS upload failures
- Vertex AI submission failures
- Pub/Sub publishing errors

All errors are logged with full stack traces.

## Dependencies

See `requirements.txt`:
- `google-cloud-storage`: GCS operations
- `google-cloud-pubsub`: Message publishing
- `google-genai`: Vertex AI batch jobs
- `pandas`: Data analysis
- `functions-framework`: Cloud Functions runtime

## Related Functions

1. **scraper_function**: Scrapes news articles → publishes to `scraping-requests`
2. **batch_builder_function**: Creates batch jobs → produces prediction files
3. **result_merger_function** (this): Merges candidates → creates dedup jobs
4. **(Future) final_processor_function**: Processes deduped results → stores final data

## Pipeline Flow

```
Scraper → Session Data → Batch Builder → Predictions → Result Merger → Dedup Job → Final Results
```

Each stage is event-driven and asynchronous.

## Best Practices

1. **Idempotency**: Check if merged files already exist before processing
2. **Batch IDs**: Use timestamps for unique identification
3. **Error Recovery**: Log all failures for manual intervention
4. **Resource Limits**: Set appropriate memory and timeout for large files
5. **Monitoring**: Track pandas statistics to understand data quality

## Troubleshooting

### Function not triggered
- Check GCS event filter pattern
- Verify bucket name matches
- Check Eventarc trigger configuration
- Look for service account permissions

### Merge failures
- Check prediction file format
- Verify candidates have required structure
- Look for JSON parsing errors in logs

### Vertex AI submission failures
- Verify API is enabled
- Check service account permissions
- Verify model name and location
- Check request format matches API requirements

### Pub/Sub publishing failures
- Verify topic exists
- Check service account has `pubsub.publisher` role
- Verify topic name matches environment variable

## Future Enhancements

- [ ] Add duplicate detection before processing (skip already-merged files)
- [ ] Support incremental merging (append to existing merged data)
- [ ] Add confidence-based candidate weighting
- [ ] Implement advanced pandas analysis (outlier detection, quality trends)
- [ ] Add BigQuery export for merged statistics
- [ ] Support custom dedup strategies per source domain
- [ ] Add retry logic for failed Vertex AI submissions
- [ ] Implement dead-letter queue for failed events
