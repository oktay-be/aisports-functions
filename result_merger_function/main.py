import os
import json
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from google.cloud import storage, pubsub_v1
from google import genai
from google.genai.types import CreateBatchJobConfig, HttpOptions
import pandas as pd

# Import response schema
try:
    from models import VERTEX_AI_RESPONSE_SCHEMA
    SCHEMA_AVAILABLE = True
except ImportError:
    try:
        from batch_builder_function.models import VERTEX_AI_RESPONSE_SCHEMA
        SCHEMA_AVAILABLE = True
    except ImportError:
        SCHEMA_AVAILABLE = False
        VERTEX_AI_RESPONSE_SCHEMA = None

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("Result Merger Function initialized")

# Initialize Google Cloud clients (only in cloud environment)
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT != 'local':
    publisher = pubsub_v1.PublisherClient()
    storage_client = storage.Client()
else:
    publisher = None
    storage_client = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
DEDUP_JOB_CREATED_TOPIC = os.getenv('DEDUP_JOB_CREATED_TOPIC', 'dedup-job-created')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')
BATCH_PROCESSING_FOLDER = os.getenv('BATCH_PROCESSING_FOLDER', 'batch_processing/')
BATCH_RESULTS_RAW_FOLDER = os.getenv('BATCH_RESULTS_RAW_FOLDER', 'batch_results_raw/')
BATCH_RESULTS_MERGED_FOLDER = os.getenv('BATCH_RESULTS_MERGED_FOLDER', 'batch_results_merged/')
DEDUP_RESULTS_FOLDER = os.getenv('DEDUP_RESULTS_FOLDER', 'dedup_results/')
VERTEX_AI_LOCATION = os.getenv('VERTEX_AI_LOCATION', 'us-central1')
VERTEX_AI_MODEL = os.getenv('VERTEX_AI_MODEL', 'gemini-2.5-pro')


class ResultMerger:
    """
    Handles merging of Vertex AI batch prediction results and creation of
    deduplication batch jobs.
    """
    
    def __init__(self):
        """Initialize the result merger with necessary clients."""
        self.genai_client = None
        self.storage_client = storage_client
        
        if ENVIRONMENT != 'local':
            try:
                # Initialize Vertex AI client
                regional_endpoint = f"https://{VERTEX_AI_LOCATION}-aiplatform.googleapis.com/"
                
                http_options = HttpOptions(
                    api_version="v1",
                    base_url=regional_endpoint
                )
                
                self.genai_client = genai.Client(
                    vertexai=True,
                    project=PROJECT_ID,
                    location=VERTEX_AI_LOCATION,
                    http_options=http_options
                )
                logger.info(f"Vertex AI client initialized: project={PROJECT_ID}, location={VERTEX_AI_LOCATION}")
            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI client: {e}")
                self.genai_client = None

    def download_prediction_file(self, gcs_uri: str) -> List[dict]:
        """
        Download and parse prediction JSONL file from GCS.
        
        Args:
            gcs_uri: GCS URI of the prediction file (gs://bucket/path/file.jsonl)
            
        Returns:
            List of parsed prediction objects
        """
        try:
            # Parse GCS URI
            if not gcs_uri.startswith('gs://'):
                raise ValueError(f"Invalid GCS URI: {gcs_uri}")
            
            parts = gcs_uri.replace('gs://', '').split('/', 1)
            bucket_name = parts[0]
            blob_name = parts[1] if len(parts) > 1 else ''
            
            logger.info(f"Downloading prediction file from: {gcs_uri}")
            
            # Download file
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            content = blob.download_as_text()
            
            # Parse JSONL
            predictions = []
            for line in content.strip().split('\n'):
                if line.strip():
                    predictions.append(json.loads(line))
            
            logger.info(f"Downloaded and parsed {len(predictions)} prediction entries")
            return predictions
            
        except Exception as e:
            logger.error(f"Error downloading prediction file: {e}")
            raise

    def merge_candidates(self, candidates: List[dict]) -> List[dict]:
        """
        Merge multiple candidates' processed_articles into one list.
        
        Args:
            candidates: List of candidate responses from Vertex AI
            
        Returns:
            Combined list of all articles from all candidates
        """
        all_articles = []
        
        for idx, candidate in enumerate(candidates):
            try:
                # Parse the JSON text from candidate
                response_text = candidate['content']['parts'][0]['text']
                response_data = json.loads(response_text)
                
                # Extract processed_articles
                articles = response_data.get('processed_articles', [])
                
                # Add metadata to track which candidate produced each article
                for article in articles:
                    article['_merge_metadata'] = {
                        'candidate_index': idx,
                        'candidate_avg_logprobs': candidate.get('avgLogprobs', 0),
                        'finish_reason': candidate.get('finishReason', 'UNKNOWN')
                    }
                
                all_articles.extend(articles)
                logger.info(f"Merged {len(articles)} articles from candidate {idx}")
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Error parsing candidate {idx}: {e}")
                continue
        
        logger.info(f"Total merged articles: {len(all_articles)}")
        return all_articles

    def create_merged_dataset(self, predictions: List[dict]) -> Dict[str, Any]:
        """
        Process all predictions and create merged datasets per source.
        
        Args:
            predictions: List of prediction objects from JSONL file
            
        Returns:
            Dictionary with merged data per source file
        """
        merged_by_source = {}
        
        for pred_idx, prediction in enumerate(predictions):
            try:
                # Extract source file URI from request
                request = prediction.get('request', {})
                contents = request.get('contents', [{}])[0]
                parts = contents.get('parts', [])
                
                # Find the fileData part
                source_uri = None
                for part in parts:
                    if 'fileData' in part and part['fileData']:
                        source_uri = part['fileData'].get('fileUri')
                        break
                
                if not source_uri:
                    logger.warning(f"No source URI found in prediction {pred_idx}")
                    continue
                
                # Extract source domain from URI
                source_filename = Path(source_uri).stem
                
                # Merge candidates
                candidates = prediction.get('response', {}).get('candidates', [])
                if not candidates:
                    logger.warning(f"No candidates found for {source_filename}")
                    continue
                
                merged_articles = self.merge_candidates(candidates)
                
                # Create merged dataset with statistics
                dataset = {
                    'source_file': source_uri,
                    'source_domain': source_filename.replace('session_data_', '').replace('_', '.'),
                    'merge_timestamp': datetime.now(timezone.utc).isoformat(),
                    'merge_statistics': {
                        'total_articles_before_dedup': len(merged_articles),
                        'num_candidates_merged': len(candidates),
                        'candidates_avg_logprobs': [c.get('avgLogprobs', 0) for c in candidates]
                    },
                    'articles': merged_articles
                }
                
                merged_by_source[source_filename] = dataset
                logger.info(f"Created merged dataset for {source_filename}: {len(merged_articles)} articles")
                
            except Exception as e:
                logger.error(f"Error processing prediction {pred_idx}: {e}")
                continue
        
        return merged_by_source

    def analyze_with_pandas(self, merged_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use pandas to analyze merged dataset and provide statistics.
        
        Args:
            merged_data: Merged dataset dictionary
            
        Returns:
            Enhanced dataset with pandas-based statistics
        """
        try:
            articles = merged_data['articles']
            if not articles:
                return merged_data
            
            # Create DataFrame
            df = pd.DataFrame(articles)
            
            # Calculate statistics
            stats = {
                'unique_urls': int(df['original_url'].nunique()) if 'original_url' in df.columns else 0,
                'unique_sources': df['source'].unique().tolist() if 'source' in df.columns else [],
                'content_quality_distribution': df['content_quality'].value_counts().to_dict() if 'content_quality' in df.columns else {},
                'language_distribution': df['language'].value_counts().to_dict() if 'language' in df.columns else {},
                'avg_categories_per_article': float(df['categories'].apply(len).mean()) if 'categories' in df.columns else 0,
                'published_date_range': {
                    'earliest': str(df['published_date'].min()) if 'published_date' in df.columns else None,
                    'latest': str(df['published_date'].max()) if 'published_date' in df.columns else None
                }
            }
            
            # Add pandas statistics to merge_statistics
            merged_data['merge_statistics']['pandas_analysis'] = stats
            
            logger.info(f"Pandas analysis complete: {stats['unique_urls']} unique URLs found")
            return merged_data
            
        except Exception as e:
            logger.error(f"Error in pandas analysis: {e}")
            return merged_data

    def upload_merged_data(self, merged_by_source: Dict[str, Any], batch_id: str) -> Dict[str, str]:
        """
        Upload merged datasets to GCS.
        
        Args:
            merged_by_source: Dictionary of merged datasets per source
            batch_id: Unique batch identifier
            
        Returns:
            Dictionary mapping source to GCS URI
        """
        uploaded_files = {}
        
        try:
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m")
            
            for source_name, dataset in merged_by_source.items():
                # Analyze with pandas first
                dataset = self.analyze_with_pandas(dataset)
                
                # Create GCS path - store in batch_results_merged folder
                gcs_blob_name = f"{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/{BATCH_RESULTS_MERGED_FOLDER}batch_{batch_id}/merged_{source_name}.json"
                
                bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
                blob = bucket.blob(gcs_blob_name)
                
                # Upload
                blob.upload_from_string(
                    json.dumps(dataset, indent=2, ensure_ascii=False),
                    content_type='application/json'
                )
                
                gcs_uri = f"gs://{GCS_BUCKET_NAME}/{gcs_blob_name}"
                uploaded_files[source_name] = gcs_uri
                
                logger.info(f"Uploaded merged data for {source_name} to {gcs_uri}")
            
            return uploaded_files
            
        except Exception as e:
            logger.error(f"Error uploading merged data: {e}")
            raise

    def load_dedup_prompt(self) -> str:
        """
        Load the deduplication prompt template.
        
        Returns:
            str: The deduplication prompt content
        """
        try:
            # Look for DEDUP_PROMPT.md
            prompt_paths = [
                Path(__file__).parent / "DEDUP_PROMPT.md",
                Path(__file__).parent.parent / "batch_builder_function" / "DEDUP_PROMPT.md"
            ]
            
            for prompt_path in prompt_paths:
                if prompt_path.exists():
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        prompt_content = f.read()
                    
                    logger.info(f"Loaded dedup prompt from {prompt_path}")
                    return prompt_content
            
            # Use a basic default prompt
            logger.warning("DEDUP_PROMPT.md not found, using basic prompt")
            return self._get_default_dedup_prompt()
            
        except Exception as e:
            logger.error(f"Error loading dedup prompt: {e}")
            return self._get_default_dedup_prompt()

    def _get_default_dedup_prompt(self) -> str:
        """Get a basic deduplication prompt."""
        return """# Article Deduplication Task

You are given a merged dataset of sports news articles that may contain duplicates.

## Your Task:
1. Identify and remove exact duplicates (same URL or nearly identical content)
2. Consolidate near-duplicates (same story from different angles) while preserving ALL information
3. Keep all unique articles

## Rules:
- Same URL = duplicate (keep the better one)
- Title similarity ≥90% = likely duplicate
- Preserve ALL key information (dates, amounts, names, quotes)
- Maintain the same output schema

Return the deduplicated articles in the standard format without losing any unique information."""

    def create_dedup_batch_request(self, merged_files: Dict[str, str], prompt_template: str, batch_id: str) -> str:
        """
        Create a batch request JSONL for deduplication.
        
        Args:
            merged_files: Dictionary mapping source to GCS URI
            prompt_template: The deduplication prompt
            batch_id: Unique batch identifier
            
        Returns:
            Local path to the created JSONL file
        """
        try:
            # Create batch requests directory
            batch_dir = Path("/tmp/dedup_requests")
            batch_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            jsonl_filename = f"dedup_request_{timestamp}.jsonl"
            jsonl_path = batch_dir / jsonl_filename
            
            # Create dedup requests
            batch_requests = []
            for source_name, gcs_uri in merged_files.items():
                request = {
                    "request": {
                        "contents": [
                            {
                                "role": "user",
                                "parts": [
                                    {"text": prompt_template},
                                    {
                                        "fileData": {
                                            "fileUri": gcs_uri,
                                            "mimeType": "application/json"
                                        }
                                    }
                                ]
                            }
                        ],
                        "generationConfig": {
                            "candidateCount": 1,  # Only 1 candidate for dedup
                            "temperature": 0.05,   # Lower temperature for consistency
                            "topP": 0.9,
                            "maxOutputTokens": 65535,
                            "responseMimeType": "application/json"
                        }
                    }
                }
                
                # Add structured output schema if available
                if SCHEMA_AVAILABLE:
                    request["request"]["generationConfig"]["responseSchema"] = VERTEX_AI_RESPONSE_SCHEMA
                    logger.info(f"Using structured output schema for {source_name}")
                
                batch_requests.append(request)
                logger.info(f"Created dedup request for {source_name}")
            
            # Write JSONL file
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                for request in batch_requests:
                    f.write(json.dumps(request, ensure_ascii=False) + '\n')
            
            logger.info(f"Dedup batch request JSONL created: {jsonl_path}")
            logger.info(f"Total dedup requests: {len(batch_requests)}")
            
            return str(jsonl_path)
            
        except Exception as e:
            logger.error(f"Error creating dedup batch request: {e}")
            return None

    def upload_dedup_request(self, local_jsonl_path: str, batch_id: str) -> str:
        """
        Upload the dedup request JSONL file to GCS.
        
        Args:
            local_jsonl_path: Local path to the JSONL file
            batch_id: Unique batch identifier
            
        Returns:
            GCS URI of the uploaded file
        """
        try:
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m")
            gcs_blob_name = f"{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/dedup_batch_{batch_id}/request.jsonl"
            
            bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(gcs_blob_name)
            
            blob.upload_from_filename(
                local_jsonl_path,
                content_type='application/x-ndjson'
            )
            
            gcs_uri = f"gs://{GCS_BUCKET_NAME}/{gcs_blob_name}"
            logger.info(f"Dedup request uploaded to GCS: {gcs_uri}")
            
            return gcs_uri
            
        except Exception as e:
            logger.error(f"Error uploading dedup request: {e}")
            return None

    def submit_dedup_batch_job(self, batch_request_gcs_uri: str, batch_id: str) -> tuple:
        """
        Submit a deduplication batch job to Vertex AI.
        
        Args:
            batch_request_gcs_uri: GCS URI of the batch request file
            batch_id: Unique batch identifier
            
        Returns:
            Tuple of (job_name, output_uri) if successful, (None, None) otherwise
        """
        try:
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m")
            output_uri = f"gs://{GCS_BUCKET_NAME}/{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/{DEDUP_RESULTS_FOLDER}{batch_id}/"
            
            # Create batch job configuration
            batch_config = CreateBatchJobConfig(dest=output_uri)
            
            logger.info(f"Submitting dedup batch job...")
            logger.info(f"  Model: {VERTEX_AI_MODEL}")
            logger.info(f"  Source: {batch_request_gcs_uri}")
            logger.info(f"  Output: {output_uri}")
            
            # Submit the batch job
            job = self.genai_client.batches.create(
                model=VERTEX_AI_MODEL,
                src=batch_request_gcs_uri,
                config=batch_config
            )
            
            logger.info(f"Dedup batch job submitted successfully!")
            logger.info(f"  Job name: {job.name}")
            logger.info(f"  Job state: {job.state}")
            logger.info(f"  Output location: {output_uri}")
            
            return job.name, output_uri
            
        except Exception as e:
            logger.error(f"Error submitting dedup batch job: {e}")
            return None, None


async def _process_merge_request(file_data: dict):
    """
    Process a merge request triggered by GCS object creation.
    
    Args:
        file_data (dict): Dictionary containing GCS file information
    """
    logger.info(f"Received merge request for file: {file_data}")
    
    # Construct GCS URI from file data
    bucket = file_data.get('bucket')
    name = file_data.get('name')
    
    if not bucket or not name:
        logger.error("Missing bucket or name in file data")
        return
    
    gcs_uri = f"gs://{bucket}/{name}"
    logger.info(f"Processing prediction file: {gcs_uri}")
    
    # Only process prediction files from batch_results_raw folder with correct structure
    # Expected pattern: news_data/batch_processing/*/batch_results_raw/*/predictions.jsonl
    if not name.endswith('/predictions.jsonl'):
        logger.info(f"Skipping file - doesn't end with '/predictions.jsonl': {name}")
        return
    
    if 'batch_results_raw' not in name:
        logger.info(f"Skipping non-raw batch results file: {name}")
        return
    
    # Verify the file is in a subdirectory under batch_results_raw (not directly in it)
    # Split path and check structure
    path_parts = name.split('/')
    try:
        raw_idx = path_parts.index('batch_results_raw')
        # Should have at least 2 more levels: batch_id/prediction-dir/predictions.jsonl
        if len(path_parts) - raw_idx < 3:
            logger.info(f"Skipping file - not in expected subdirectory structure: {name}")
            return
    except (ValueError, IndexError):
        logger.info(f"Skipping file - unexpected path structure: {name}")
        return
    
    try:
        # Initialize result merger
        merger = ResultMerger()
        
        if not merger.genai_client and ENVIRONMENT != 'local':
            logger.error("Vertex AI client not available")
            return
        
        # Generate unique batch ID
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        batch_id = f"dedup_{timestamp}"
        
        logger.info(f"Processing merge batch {batch_id}")
        
        # Step 1: Download and parse prediction file
        logger.info("Step 1: Downloading prediction file...")
        predictions = merger.download_prediction_file(gcs_uri)
        if not predictions:
            logger.error("No predictions found in file")
            return
        
        # Step 2: Merge candidates for each source
        logger.info("Step 2: Merging candidates...")
        merged_by_source = merger.create_merged_dataset(predictions)
        if not merged_by_source:
            logger.error("No merged data created")
            return
        
        # Step 3: Upload merged data to GCS
        logger.info("Step 3: Uploading merged data...")
        merged_files = merger.upload_merged_data(merged_by_source, batch_id)
        if not merged_files:
            logger.error("Failed to upload merged data")
            return
        
        # Step 4: Load dedup prompt
        logger.info("Step 4: Loading dedup prompt...")
        dedup_prompt = merger.load_dedup_prompt()
        
        # Step 5: Create dedup batch request
        logger.info("Step 5: Creating dedup batch request...")
        local_jsonl_path = merger.create_dedup_batch_request(
            merged_files,
            dedup_prompt,
            batch_id
        )
        if not local_jsonl_path:
            logger.error("Failed to create dedup batch request")
            return
        
        # Step 6: Upload dedup request to GCS
        logger.info("Step 6: Uploading dedup request...")
        dedup_request_uri = merger.upload_dedup_request(local_jsonl_path, batch_id)
        if not dedup_request_uri:
            logger.error("Failed to upload dedup request")
            return
        
        # Step 7: Submit dedup batch job
        logger.info("Step 7: Submitting dedup batch job...")
        job_name, output_uri = merger.submit_dedup_batch_job(dedup_request_uri, batch_id)
        if not job_name:
            logger.error("Failed to submit dedup batch job")
            return
        
        # Step 8: Publish dedup job created message
        logger.info("Step 8: Publishing dedup job created message...")
        dedup_message = {
            "status": "dedup_job_created",
            "batch_id": batch_id,
            "job_name": job_name,
            "output_uri": output_uri,
            "source_prediction_file": gcs_uri,
            "merged_files": list(merged_files.values()),
            "num_sources": len(merged_files),
            "vertex_ai_model": VERTEX_AI_MODEL,
            "vertex_ai_location": VERTEX_AI_LOCATION,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if ENVIRONMENT != 'local':
            topic_path = publisher.topic_path(PROJECT_ID, DEDUP_JOB_CREATED_TOPIC)
            future = publisher.publish(topic_path, json.dumps(dedup_message).encode("utf-8"))
            future.result()
            logger.info(f"Dedup job message published to {DEDUP_JOB_CREATED_TOPIC}")
        else:
            logger.info(f"Local mode: Would publish to {DEDUP_JOB_CREATED_TOPIC}")
            logger.info(f"Message: {json.dumps(dedup_message, indent=2)}")
        
        logger.info(f"Successfully processed merge and created dedup job: {job_name}")
        
    except Exception as e:
        logger.error(f"Error processing merge request: {e}", exc_info=True)


def merge_results(event, context):
    """
    Background Cloud Function to be triggered by GCS object creation.
    Triggered when Vertex AI batch prediction results are written to GCS.
    
    Args:
        event (dict): The Cloud Storage event data.
        context (google.cloud.functions.Context): The Cloud Functions event metadata.
    """
    logger.info(f"=== RESULT MERGER FUNCTION TRIGGERED ===")
    logger.info(f"Event: {event}")
    logger.info(f"Context: {context}")
    
    try:
        # Extract file information from event
        file_data = {
            'bucket': event.get('bucket'),
            'name': event.get('name'),
            'content_type': event.get('contentType'),
            'size': event.get('size'),
            'time_created': event.get('timeCreated')
        }
        
        logger.info(f"File data: {file_data}")
        asyncio.run(_process_merge_request(file_data))
        
    except Exception as e:
        logger.error(f"Error processing GCS event: {e}", exc_info=True)
    
    logger.info(f"=== RESULT MERGER FUNCTION EXECUTION COMPLETED ===")


if __name__ == "__main__":
    # For local testing
    logger.info("Running in local mode")
    test_file_data = {
        'bucket': 'aisports-scraping',
        'name': 'news_data/batch_processing/2025-10/batch_results_raw/20251025_095557_003/prediction-model-2025-10-25T09_55_58.376824Z_predictions.jsonl'
    }
    asyncio.run(_process_merge_request(test_file_data))
