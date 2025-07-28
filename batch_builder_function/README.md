# Batch Builder Function

This directory contains the **Batch Builder Function** for the AISports eve7. **Message Publishing**: Publishes batch_job_created message for downstream processing

## Response Schema

The function uses a structured response schema (`VERTEX_AI_RESPONSE_SCHEMA`) defined in `models.py` to ensure consistent AI processing outputs. The schema includes:

- **processing_summary**: Metadata about the processing (total articles, deduplication stats, etc.)
- **processed_articles**: Array of processed articles with:
  - Basic info (id, title, summary, source)
  - Key entities (teams, players, amounts, dates)
  - Categories with confidence scores
  - Content quality and language detection

When `STRUCTURED_OUTPUT=true` (default), Vertex AI will validate responses against this schema.t-driven microservices architecture.

## Overview

The batch builder function is responsible for:
- Receiving batch success messages from the scraper function via Pub/Sub
- Extracting GCS paths from session data messages
- Creating Vertex AI batch processing requests
- Submitting batch jobs to Vertex AI for AI processing
- Publishing batch job creation messages to the next topic in the pipeline

## Files

- `main.py` - Main function code with batch building logic
- `models.py` - Data models and response schemas for Vertex AI
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Configuration

The function uses the following environment variables:

- `GOOGLE_CLOUD_PROJECT` - Google Cloud project ID (default: gen-lang-client-0306766464)
- `GCS_BUCKET_NAME` - GCS bucket for storing data (default: aisports-news-data)
- `BATCH_REQUEST_CREATED_TOPIC` - Pub/Sub topic for publishing batch job results (default: batch-request-created)  
- `NEWS_DATA_ROOT_PREFIX` - Root prefix for GCS storage (default: news_data/)
- `BATCH_PROCESSING_FOLDER` - Subfolder for batch processing (default: batch_processing/)
- `VERTEX_AI_LOCATION` - Vertex AI region (default: us-central1)
- `VERTEX_AI_MODEL` - AI model to use (default: gemini-2.5-pro)
- `STRUCTURED_OUTPUT` - Enable structured output schema (default: true)

## GCS Folder Structure

The function organizes batch processing data in the following GCS structure:
```
news_data/
├── batch_processing/
│   ├── 2025-07/
│   │   ├── batch_YYYYMMDD_HHMMSS_XXX/
│   │   │   ├── request.jsonl        # Input for batch prediction
│   │   │   ├── response.jsonl       # Output from batch prediction (created by Vertex AI)
│   │   │   ├── job_metadata.json    # Metadata about the batch job
│   │   │   └── source_files_manifest.json # List of source files included in batch
```

## Message Flow

### Input Message (from session-data-created topic)
The function expects batch_success messages from the scraper function:
```json
{
  "status": "batch_success",
  "batch_size": 2,
  "success_messages": [
    {
      "status": "success",
      "gcs_path": "gs://aisports-news-data/news_data/sources/fanatik_com_tr/2025-07/articles/session_data_fanatik_com_tr_001.json",
      "source_domain": "fanatik_com_tr",
      "session_id": "001",
      "date_path": "2025-07",
      "articles_count": 15,
      "keywords": ["fenerbahce", "galatasaray"],
      "processed_at": "2025-07-26T12:34:56.789Z"
    }
  ],
  "batch_processed_at": "2025-07-26T12:34:56.789Z",
  "total_articles": 27
}
```

### Output Message (to batch-request-created topic)
```json
{
  "status": "batch_job_created",
  "batch_id": "20250726_123456_002",
  "job_name": "projects/gen-lang-client-0306766464/locations/us-central1/batchJobs/batch_job_id",
  "output_uri": "gs://aisports-news-data/news_data/batch_processing/2025-07/batch_20250726_123456_002/",
  "source_files": ["gs://...", "gs://..."],
  "source_files_count": 2,
  "vertex_ai_model": "gemini-2.5-pro",
  "vertex_ai_location": "us-central1",
  "created_at": "2025-07-26T12:34:56.789Z"
}
```

## Dependencies

- `google-cloud-pubsub` - For Pub/Sub messaging
- `google-cloud-storage` - For GCS file operations  
- `google-genai` - For Vertex AI batch processing
- `python-dotenv` - For environment variable loading

## Batch Processing Logic

1. **Message Reception**: Receives batch_success messages from scraper function
2. **GCS Path Extraction**: Extracts gcs_path from each success_message
3. **Prompt Loading**: Loads AI processing prompt template (PROMPT.md)
4. **JSONL Creation**: Creates batch request JSONL file with prompts and file references
5. **GCS Upload**: Uploads batch request to GCS batch_processing folder
6. **Vertex AI Submission**: Submits batch job to Vertex AI
7. **Metadata Storage**: Saves job metadata and source file manifest to GCS
8. **Message Publishing**: Publishes batch_job_created message for downstream processing

## Testing

For local testing, the function simulates receiving a batch_success message:

```bash
# Set environment for local testing
set ENVIRONMENT=local
python main.py
```

This will create mock GCS paths and simulate the batch creation process without actually submitting to Vertex AI.

## Error Handling

The function includes comprehensive error handling:
- Invalid message format validation
- Missing GCS paths handling
- Vertex AI client initialization errors
- Batch job submission failures
- Metadata storage errors

Error messages are published to the same batch-request-created topic with status "batch_job_error".

## Integration

This function integrates with:
- **Upstream**: Scraper Function (via session-data-created topic)
- **Downstream**: AI Processor Function (via batch-request-created topic)  
- **Services**: Vertex AI, Google Cloud Storage, Pub/Sub
