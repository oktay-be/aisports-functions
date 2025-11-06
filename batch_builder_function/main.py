import os
import json
import base64
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from google.cloud import pubsub_v1, storage
from google import genai
from google.genai.types import CreateBatchJobConfig, JobState, HttpOptions

# Import response schema
try:
    from models import VERTEX_AI_RESPONSE_SCHEMA
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

# Application logger
logger = logging.getLogger(__name__)
logger.info("Batch Builder Function initialized")

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
SESSION_DATA_CREATED_TOPIC = os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')  # Input topic (trigger)
BATCH_REQUEST_CREATED_TOPIC = os.getenv('BATCH_REQUEST_CREATED_TOPIC', 'batch-request-created')  # Output topic
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-news-data')
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')
BATCH_PROCESSING_FOLDER = os.getenv('BATCH_PROCESSING_FOLDER', 'batch_processing/')
VERTEX_AI_LOCATION = os.getenv('VERTEX_AI_LOCATION', 'us-central1')
VERTEX_AI_MODEL = os.getenv('VERTEX_AI_MODEL', 'gemini-2.5-pro')


class BatchBuilder:
    """
    Handles creation and submission of Vertex AI batch processing jobs
    from scraped session data.
    """
    
    def __init__(self):
        """Initialize the batch builder with Vertex AI client."""
        self.genai_client = None
        self.storage_client = storage_client
        
        if ENVIRONMENT != 'local':
            try:
                # Initialize Vertex AI client for batch processing
                regional_endpoint = f"https://{VERTEX_AI_LOCATION}-aiplatform.googleapis.com/"
                
                http_options = HttpOptions(
                    api_version="v1",
                    base_url=regional_endpoint                )
                
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

    def load_prompt_template(self) -> str:
        """
        Load the PROMPT.md template for processing session data.
        
        Returns:
            str: The prompt template content
        """
        try:
            # Look for PROMPT.md in the legacy directory first, then in current directory
            prompt_paths = [
                Path(__file__).parent.parent / "legacy_monolithic_code" / "PROMPT.md",
                Path(__file__).parent / "PROMPT.md"
            ]
            
            for prompt_path in prompt_paths:
                if prompt_path.exists():
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        prompt_content = f.read()
                    
                    # Construct the complete prompt
                    combined_prompt = f"""{prompt_content}

## SESSION DATA TO PROCESS

Please process the session data from the provided JSON file according to the specifications above.

The data contains sports news articles that need to be processed according to the OUTPUT FORMAT specified in the prompt above. Return the structured JSON result."""                    
                    logger.info(f"Loaded prompt template from {prompt_path}")
                    return combined_prompt
            
            # PROMPT.md should always be available
            raise FileNotFoundError("PROMPT.md not found in expected locations")
            
        except Exception as e:
            logger.error(f"Error loading prompt template: {e}")
            raise
    
    def create_batch_request_jsonl(self, gcs_files: List[str], prompt_template: str) -> str:
        """
        Create a JSONL file with batch requests for each GCS file.
        
        Args:
            gcs_files: List of GCS URIs to process
            prompt_template: The prompt template to use
            
        Returns:
            Local path to the created JSONL file
        """
        try:
            # Create batch requests directory in /tmp for cloud functions
            batch_dir = Path("/tmp/batch_requests")
            batch_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            jsonl_filename = f"batch_request_{timestamp}.jsonl"
            jsonl_path = batch_dir / jsonl_filename
              # Create batch requests
            batch_requests = []
            for i, gcs_uri in enumerate(gcs_files):
                # Extract source domain for logging
                filename = Path(gcs_uri).stem
                source_domain = filename.replace('session_data_', '').replace('_', '.')
                
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
                                            "mimeType": "text/plain"
                                        }
                                    }
                                ]
                            }
                        ],
                        "generationConfig": {
                            "candidateCount": 2,
                            "temperature": 0.1,
                            "topP": 0.95,
                            "maxOutputTokens": 65535,
                            "responseMimeType": "application/json"
                        }
                    }
                }
                  # Add structured output schema if available
                if os.getenv("STRUCTURED_OUTPUT", "true").lower() == "true" and SCHEMA_AVAILABLE:
                    request["request"]["generationConfig"]["responseSchema"] = VERTEX_AI_RESPONSE_SCHEMA
                    logger.info(f"Using structured output schema for request {i+1}")
                else:
                    logger.info(f"Using unstructured JSON output for request {i+1}")
                
                batch_requests.append(request)
                logger.info(f"Created batch request {i+1}/{len(gcs_files)} for {source_domain}")
            
            # Write JSONL file
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                for request in batch_requests:
                    f.write(json.dumps(request, ensure_ascii=False) + '\n')
            
            logger.info(f"Batch request JSONL created: {jsonl_path}")
            logger.info(f"Total requests: {len(batch_requests)}")
            
            return str(jsonl_path)
            
        except Exception as e:
            logger.error(f"Error creating batch request JSONL: {e}")
            return None

    def upload_batch_request_to_gcs(self, local_jsonl_path: str, batch_id: str) -> str:
        """
        Upload the batch request JSONL file to GCS.
        
        Args:
            local_jsonl_path: Local path to the JSONL file
            batch_id: Unique batch identifier
            
        Returns:
            GCS URI of the uploaded file
        """
        try:
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m")
            gcs_blob_name = f"{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/batch_{batch_id}/request.jsonl"
            
            bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(gcs_blob_name)
            
            # Upload with proper content type
            blob.upload_from_filename(
                local_jsonl_path,
                content_type='application/x-ndjson'
            )
            
            gcs_uri = f"gs://{GCS_BUCKET_NAME}/{gcs_blob_name}"
            logger.info(f"Batch request uploaded to GCS: {gcs_uri}")
            
            return gcs_uri
            
        except Exception as e:
            logger.error(f"Error uploading batch request to GCS: {e}")
            return None

    def submit_batch_job(self, batch_request_gcs_uri: str, batch_id: str) -> tuple:
        """
        Submit a batch job to Vertex AI.
        
        Args:
            batch_request_gcs_uri: GCS URI of the batch request file
            batch_id: Unique batch identifier
            
        Returns:
            Tuple of (job_name, output_uri) if successful, (None, None) otherwise
        """
        try:
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m")
            output_uri = f"gs://{GCS_BUCKET_NAME}/{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/batch_results_raw/{batch_id}/"
            
            # output_uri = f"gs://multi-modal-ai-bucket/batch_results_raw/{current_date_path}/{batch_id}/"
            
            # Create batch job configuration
            batch_config = CreateBatchJobConfig(dest=output_uri)
            
            logger.info(f"Submitting batch job...")
            logger.info(f"  Model: {VERTEX_AI_MODEL}")
            logger.info(f"  Source: {batch_request_gcs_uri}")
            logger.info(f"  Output: {output_uri}")
            
            # Submit the batch job
            job = self.genai_client.batches.create(
                model=VERTEX_AI_MODEL,
                src=batch_request_gcs_uri,
                config=batch_config
            )
            
            logger.info(f"Batch job submitted successfully!")
            logger.info(f"  Job name: {job.name}")
            logger.info(f"  Job state: {job.state}")
            logger.info(f"  Output location: {output_uri}")
            
            return job.name, output_uri
            
        except Exception as e:
            logger.error(f"Error submitting batch job: {e}")
            return None, None

    def save_batch_metadata(self, batch_id: str, job_name: str, output_uri: str, 
                           source_files: List[str], batch_message: Dict[str, Any]) -> None:
        """
        Save batch job metadata to GCS.
        
        Args:
            batch_id: Unique batch identifier
            job_name: Vertex AI batch job name
            output_uri: GCS output URI
            source_files: List of source GCS files
            batch_message: Original batch message from scraper
        """
        try:
            current_date_path = datetime.now(timezone.utc).strftime("%Y-%m")
            metadata_path = f"{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/batch_{batch_id}/job_metadata.json"
            
            metadata = {
                "batch_id": batch_id,
                "job_name": job_name,
                "output_uri": output_uri,
                "source_files": source_files,
                "source_files_count": len(source_files),
                "vertex_ai_model": VERTEX_AI_MODEL,
                "vertex_ai_location": VERTEX_AI_LOCATION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "submitted",
                "original_batch_message": batch_message
            }
            
            # Also save source files manifest
            manifest = {
                "batch_id": batch_id,
                "source_files": source_files,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            
            # Save job metadata
            metadata_blob = bucket.blob(metadata_path)
            metadata_blob.upload_from_string(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                content_type='application/json'
            )
            
            # Save source files manifest
            manifest_path = f"{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/batch_{batch_id}/source_files_manifest.json"
            manifest_blob = bucket.blob(manifest_path)
            manifest_blob.upload_from_string(
                json.dumps(manifest, indent=2, ensure_ascii=False),
                content_type='application/json'
            )
            
            logger.info(f"Batch metadata saved to GCS: {metadata_path}")
            logger.info(f"Source files manifest saved to GCS: {manifest_path}")
            
        except Exception as e:
            logger.error(f"Error saving batch metadata: {e}")


async def _process_batch_request(message_data: dict):
    """
    Process a batch request from the session-data-created topic.
    
    Args:
        message_data (dict): Dictionary containing batch_success message with success_messages
    """
    logger.info(f"Received batch request: {message_data}")
    
    # Validate message format
    if message_data.get("status") != "batch_success":
        logger.error(f"Invalid message status: {message_data.get('status')}")
        return
    
    success_messages = message_data.get("success_messages", [])
    if not success_messages:
        logger.error("No success messages found in batch request")
        return
    
    # Extract GCS paths from success messages (commented out for troubleshooting)
    gcs_files = []
    for msg in success_messages:
        gcs_path = msg.get("gcs_path")
        if gcs_path and gcs_path.startswith("gs://"):
            gcs_files.append(gcs_path)
            logger.info(f"Added GCS file for batch processing: {gcs_path}")
        else:
            logger.warning(f"Invalid or missing gcs_path in message: {msg}")
    
    if not gcs_files:
        logger.error("No valid GCS files found in success messages")
        return
    
    logger.info(f"Total GCS files extracted from success messages: {len(gcs_files)}")
    
    # HARDCODED GCS FILES FOR TROUBLESHOOTING
    # gcs_files = [
    #     "gs://multi-modal-ai-bucket/session_data_fanatik_com_tr.json",
    #     "gs://multi-modal-ai-bucket/session_data_fotomac_com_tr.json", 
    #     "gs://multi-modal-ai-bucket/session_data_milliyet_com_tr.json",
    #     "gs://multi-modal-ai-bucket/session_data_sabah_com_tr.json"
    # ]
    
    logger.info(f"Found {len(gcs_files)} GCS files to process:")
    for i, gcs_file in enumerate(gcs_files, 1):
        logger.info(f"  {i}. {gcs_file}")
    
    try:
        # Initialize batch builder
        batch_builder = BatchBuilder()
        
        if not batch_builder.genai_client and ENVIRONMENT != 'local':
            logger.error("Vertex AI client not available")
            return
        
        # Generate unique batch ID
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        batch_id = f"{timestamp}_{len(gcs_files):03d}"
        
        logger.info(f"Processing batch {batch_id} with {len(gcs_files)} files")
        
        if ENVIRONMENT == 'local':
            # Local testing - just log what would be done
            logger.info("=== LOCAL MODE: BATCH PROCESSING SIMULATION ===")
            logger.info(f"Batch ID: {batch_id}")
            logger.info(f"Files to process: {len(gcs_files)}")
            for i, gcs_file in enumerate(gcs_files, 1):
                logger.info(f"  {i}. {gcs_file}")
            
            # Create success message for local testing
            batch_job_message = {
                "status": "batch_job_created",
                "batch_id": batch_id,
                "job_name": f"local_test_job_{batch_id}",
                "output_uri": f"gs://{GCS_BUCKET_NAME}/{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}batch_{batch_id}/",
                "source_files": gcs_files,
                "source_files_count": len(gcs_files),
                "vertex_ai_model": VERTEX_AI_MODEL,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "original_batch_message": message_data
            }
            
            logger.info(f"Local batch job message: {json.dumps(batch_job_message, indent=2)}")
            return
        
        # Step 1: Load prompt template
        logger.info("Step 1: Loading prompt template...")
        prompt_template = batch_builder.load_prompt_template()
        if not prompt_template:
            logger.error("Failed to load prompt template")
            return
        
        # Step 2: Create batch request JSONL
        logger.info("Step 2: Creating batch request JSONL...")
        local_jsonl_path = batch_builder.create_batch_request_jsonl(gcs_files, prompt_template)
        if not local_jsonl_path:
            logger.error("Failed to create batch request JSONL")
            return
        
        # Step 3: Upload to GCS
        logger.info("Step 3: Uploading batch request to GCS...")
        batch_request_gcs_uri = batch_builder.upload_batch_request_to_gcs(local_jsonl_path, batch_id)
        if not batch_request_gcs_uri:
            logger.error("Failed to upload batch request to GCS")
            return
        
        # Step 4: Submit batch job
        logger.info("Step 4: Submitting batch job to Vertex AI...")
        job_name, output_uri = batch_builder.submit_batch_job(batch_request_gcs_uri, batch_id)
        if not job_name:
            logger.error("Failed to submit batch job")
            return
        
        # Step 5: Save batch metadata
        logger.info("Step 5: Saving batch metadata...")
        batch_builder.save_batch_metadata(batch_id, job_name, output_uri, gcs_files, message_data)
        
        # Step 6: Publish batch job created message
        logger.info("Step 6: Publishing batch job created message...")
        batch_job_message = {
            "status": "batch_job_created",
            "batch_id": batch_id,
            "job_name": job_name,
            "output_uri": output_uri,
            "source_files": gcs_files,
            "source_files_count": len(gcs_files),
            "vertex_ai_model": VERTEX_AI_MODEL,
            "vertex_ai_location": VERTEX_AI_LOCATION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "original_batch_message": message_data
        }
        
        # Publish to batch-request-created topic
        topic_path = publisher.topic_path(PROJECT_ID, BATCH_REQUEST_CREATED_TOPIC)
        future = publisher.publish(topic_path, json.dumps(batch_job_message).encode("utf-8"))
        future.result()  # Wait for publish to complete
        
        logger.info(f"Successfully created and submitted batch job: {job_name}")
        logger.info(f"Batch job message published to {BATCH_REQUEST_CREATED_TOPIC}")
        
    except Exception as e:
        logger.error(f"Error processing batch request: {e}", exc_info=True)
        
        # Publish error message
        error_message = {
            "status": "batch_job_error",
            "error": str(e),
            "gcs_files": gcs_files,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "original_batch_message": message_data
        }
        
        if ENVIRONMENT == 'local':
            logger.error(f"Local batch processing error: {json.dumps(error_message, indent=2)}")
        else:
            try:
                topic_path = publisher.topic_path(PROJECT_ID, BATCH_REQUEST_CREATED_TOPIC)
                future = publisher.publish(topic_path, json.dumps(error_message).encode("utf-8"))
                future.result()
                logger.info("Error message published successfully")
            except Exception as pub_error:
                logger.error(f"Failed to publish error message: {pub_error}")


def build_batch(event, context):
    """
    Background Cloud Function to be triggered by Pub/Sub.
    Triggered by messages from the SESSION_DATA_CREATED_TOPIC (configured in deployment).
    
    Args:
        event (dict): The Pub/Sub message data.
        context (google.cloud.functions.Context): The Cloud Functions event metadata.
    """
    logger.info(f"=== BATCH BUILDER FUNCTION TRIGGERED ===")
    logger.info(f"Function triggered via {SESSION_DATA_CREATED_TOPIC} topic")
    logger.info(f"Event: {event}")
    logger.info(f"Context: {context}")
    
    if isinstance(event, dict) and "data" in event:
        try:
            message_data = json.loads(base64.b64decode(event["data"]).decode("utf-8"))
            logger.info(f"Decoded message data: {message_data}")
            asyncio.run(_process_batch_request(message_data))
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
    else:
        logger.error("Invalid Pub/Sub message format")
    
    logger.info(f"=== BATCH BUILDER FUNCTION EXECUTION COMPLETED ===")


def get_test_data():
    """
    Load test parameters from search_parameters.json for local execution.
    Simulates a batch_success message from the scraper function.
    """
    try:
        # Create a mock batch_success message similar to what scraper function publishes
        test_data = {
            "status": "batch_success",
            "batch_size": 2,
            "success_messages": [
                {
                    "status": "success",
                    "gcs_path": f"gs://{GCS_BUCKET_NAME}/news_data/sources/fanatik_com_tr/2025-07/articles/session_data_fanatik_com_tr_20250726_001.json",
                    "source_domain": "fanatik_com_tr",
                    "session_id": "20250726_001",
                    "date_path": "2025-07",
                    "articles_count": 15,
                    "keywords": ["fenerbahce", "galatasaray", "mourinho"],
                    "scrape_depth": 1,
                    "persist": True,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                },
                {
                    "status": "success",
                    "gcs_path": f"gs://{GCS_BUCKET_NAME}/news_data/sources/fotomac_com_tr/2025-07/articles/session_data_fotomac_com_tr_20250726_002.json",
                    "source_domain": "fotomac_com_tr",
                    "session_id": "20250726_002",
                    "date_path": "2025-07",
                    "articles_count": 12,
                    "keywords": ["fenerbahce", "galatasaray", "mourinho"],
                    "scrape_depth": 1,
                    "persist": True,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }
            ],
            "batch_processed_at": datetime.now(timezone.utc).isoformat(),
            "total_articles": 27
        }
        
        logger.info("Using mock batch_success test data for local execution")
        return test_data
        
    except Exception as e:
        logger.error(f"Failed to create test data: {e}")
        raise RuntimeError(f"Cannot create test data: {e}")


async def main_local():
    """
    Main function for local execution.
    Simulates receiving a batch_success message from the scraper function.
    """
    logger.info("=== STARTING LOCAL BATCH BUILDER EXECUTION ===")
    logger.info(f"Environment: {ENVIRONMENT}")
    
    # Get test data
    test_data = get_test_data()
    logger.info(f"Using test data: {json.dumps(test_data, indent=2)}")
    
    # Process the batch request
    await _process_batch_request(test_data)
    
    logger.info("=== LOCAL BATCH BUILDER EXECUTION COMPLETED ===")


if __name__ == "__main__":
    if ENVIRONMENT == 'local':
        logger.info("Running in local mode")
        asyncio.run(main_local())
    else:
        logger.info("Running in cloud mode - use Pub/Sub trigger")
