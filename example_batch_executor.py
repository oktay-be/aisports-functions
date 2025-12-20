"""
Test file for Vertex AI Batch Processing using existing GCS session data files.
This test validates the batch processing approach before implementing the full pipeline.

Creates a batch request file from existing session data and processes it using Vertex AI's
native batch processing capabilities.

Required environment variables:
- GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464
- GOOGLE_APPLICATION_CREDENTIALS=./gen-lang-client-0306766464-13fc9c9298ba.json
- GOOGLE_CLOUD_LOCATION=us-central1

GCS Files to Process in Batch:
- gs://multi-modal-ai-bucket/session_data_fanatik_com_tr.json
- gs://multi-modal-ai-bucket/session_data_fotomac_com_tr.json
- gs://multi-modal-ai-bucket/session_data_milliyet_com_tr.json
- gs://multi-modal-ai-bucket/session_data_sabah_com_tr.json

Output Location:
- gs://multi-modal-ai-bucket/batch_results/test_batch_YYYYMMDD_HHMMSS/
"""

import json
import logging
import os
import time
import sys
import codecs
import locale
import io
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from google import genai
from google.genai.types import CreateBatchJobConfig, JobState
from google.cloud import storage

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import the response schema
try:
    from capabilities.models import VERTEX_AI_RESPONSE_SCHEMA
    SCHEMA_AVAILABLE = True
except ImportError:
    SCHEMA_AVAILABLE = False
    VERTEX_AI_RESPONSE_SCHEMA = None

# Configure logging with proper encoding for Windows
import locale
import io

# Set up proper console encoding
if sys.platform == "win32":
    # Force UTF-8 encoding for Windows console
    import codecs
    
    # Create a proper UTF-8 stream handler
    class UTF8StreamHandler(logging.StreamHandler):
        def __init__(self, stream=None):
            if stream is None:
                stream = sys.stderr
            # Wrap the stream to ensure UTF-8 encoding
            if hasattr(stream, 'buffer'):
                stream = io.TextIOWrapper(stream.buffer, encoding='utf-8', newline='', line_buffering=True)
            super().__init__(stream)
    
    handler = UTF8StreamHandler()
else:
    handler = logging.StreamHandler(sys.stderr)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[handler]
)

logger = logging.getLogger(__name__)

class VertexAIBatchTester:
    """
    Test class for Vertex AI Batch Processing functionality.
    Creates batch requests from existing GCS files and processes them using native batch API.
    """
    def __init__(self, project_id: str = None, location: str = None, model_name: str = "gemini-2.5-pro"):
        """
        Initialize Vertex AI Batch Tester.
        """
        self.client = None
        self.storage_client = None
        self.model_name = model_name
        
        # Get configuration from environment variables or parameters
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.bucket_name = "multi-modal-ai-bucket"
        
        if not self.project_id:
            logger.error("Google Cloud project ID is not set. Set GOOGLE_CLOUD_PROJECT environment variable.")
            return

        try:
            # Initialize Vertex AI client for batch processing with regional endpoint
            # Batch processing requires regional endpoints, not global
            if self.location == "global":
                logger.warning(f"Batch processing not supported on global endpoint. Using us-central1 instead.")
                self.location = "us-central1"
            
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location
            )
            
            # Initialize GCS client for file operations
            self.storage_client = storage.Client(project=self.project_id)
            
            logger.info(f"VertexAIBatchTester initialized: project={self.project_id}, location={self.location}, model={model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize clients: {e}", exc_info=True)
            self.client = None
            self.storage_client = None

    def load_prompt_template(self) -> str:
        """
        Load the PROMPT.md template for processing session data.
        """
        try:
            prompt_md_path = Path(__file__).parent / "PROMPT.md"
            if not prompt_md_path.exists():
                logger.error(f"PROMPT.md file not found: {prompt_md_path}")
                return None

            with open(prompt_md_path, 'r', encoding='utf-8') as f:
                prompt_content = f.read()

            # Construct the complete prompt
            combined_prompt = f"""{prompt_content}

## SESSION DATA TO PROCESS

Please process the session data from the provided JSON file according to the specifications above.

The data contains sports news articles that need to be processed according to the OUTPUT FORMAT specified in the prompt above. Return the structured JSON result."""

            return combined_prompt
        except Exception as e:
            logger.error(f"Error loading prompt template: {e}")
            return None

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
            # Create batch requests directory
            batch_dir = Path(__file__).parent / ".workspace" / "batch_requests"
            batch_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
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
                            "candidateCount": 3,
                            "temperature": 0.1,
                            "topP": 0.95,
                            "maxOutputTokens": 65535
                        }
                    }
                }
                
                # Add structured output if enabled - same pattern
                if os.getenv("STRUCTURED_OUTPUT", "true").lower() == "true" and SCHEMA_AVAILABLE:
                    request["request"]["generationConfig"]["responseMimeType"] = "application/json"
                    request["request"]["generationConfig"]["responseSchema"] = VERTEX_AI_RESPONSE_SCHEMA
                else:
                    # For unstructured output, still request JSON format but without schema validation
                    request["request"]["generationConfig"]["responseMimeType"] = "application/json"
                
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

    def upload_batch_request_to_gcs(self, local_jsonl_path: str) -> str:
        """
        Upload the batch request JSONL file to GCS.
        
        Args:
            local_jsonl_path: Local path to the JSONL file
            
        Returns:
            GCS URI of the uploaded file
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            gcs_blob_name = f"batch_requests/test_batch_request_{timestamp}.jsonl"
            
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_blob_name)
            
            # Upload with proper content type
            blob.upload_from_filename(
                local_jsonl_path,
                content_type='application/x-ndjson'
            )
            
            gcs_uri = f"gs://{self.bucket_name}/{gcs_blob_name}"
            logger.info(f"Batch request uploaded to GCS: {gcs_uri}")
            
            return gcs_uri
            
        except Exception as e:
            logger.error(f"Error uploading batch request to GCS: {e}")
            return None

    def submit_batch_job(self, batch_request_gcs_uri: str) -> str:
        """
        Submit a batch job to Vertex AI.
        
        Args:
            batch_request_gcs_uri: GCS URI of the batch request file
            
        Returns:
            Job name if successful, None otherwise
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_uri = f"gs://{self.bucket_name}/batch_results/test_batch_{timestamp}/"
            
            # Create batch job configuration
            batch_config = CreateBatchJobConfig(dest=output_uri)
            
            logger.info(f"Submitting batch job...")
            logger.info(f"  Model: {self.model_name}")
            logger.info(f"  Source: {batch_request_gcs_uri}")
            logger.info(f"  Output: {output_uri}")
            
            # Submit the batch job - following Google's pattern
            job = self.client.batches.create(
                model=self.model_name,
                src=batch_request_gcs_uri,
                config=batch_config
            )
            
            logger.info(f"[SUCCESS] Batch job submitted successfully!")
            logger.info(f"  Job name: {job.name}")
            logger.info(f"  Job state: {job.state}")
            logger.info(f"  Output location: {output_uri}")
            
            return job.name, output_uri
            
        except Exception as e:
            logger.error(f"Error submitting batch job: {e}")
            return None, None

    def monitor_batch_job(self, job_name: str, polling_interval: int = 30) -> Dict[str, Any]:
        """
        Monitor a batch job until completion.
        
        Args:
            job_name: The name of the batch job
            polling_interval: How often to check job status (seconds)
            
        Returns:
            Final job status information
        """
        try:
            completed_states = {
                JobState.JOB_STATE_SUCCEEDED,
                JobState.JOB_STATE_FAILED,
                JobState.JOB_STATE_CANCELLED,
                JobState.JOB_STATE_PAUSED,
            }
            
            start_time = time.time()
            logger.info(f"[MONITOR] Monitoring batch job: {job_name}")
            logger.info(f"  Checking every {polling_interval} seconds...")
            
            # Get initial job status
            job = self.client.batches.get(name=job_name)
            
            # Follow Google's pattern for monitoring
            while job.state not in completed_states:
                elapsed = time.time() - start_time
                logger.info(f"  Job state: {job.state} (elapsed: {elapsed:.1f}s)")
                
                time.sleep(polling_interval)
                job = self.client.batches.get(name=job_name)
            
            # Final status
            elapsed = time.time() - start_time
            logger.info(f"[SUCCESS] Job completed with state: {job.state}")
            
            # Return comprehensive job information
            return {
                "job_name": job_name,
                "state": job.state,
                "elapsed_time": elapsed,
                "success": job.state == JobState.JOB_STATE_SUCCEEDED,
                "job_object": job
            }
                
        except Exception as e:
            logger.error(f"Error monitoring batch job: {e}")
            return {
                "job_name": job_name,
                "state": "ERROR",
                "error": str(e),
                "success": False
            }

    def download_batch_results(self, output_uri: str) -> List[Dict[str, Any]]:
        """
        Download and parse batch processing results.
        
        Args:
            output_uri: GCS URI where results are stored
            
        Returns:
            List of processed results
        """
        try:
            # Parse the output URI to get bucket and prefix
            if not output_uri.startswith("gs://"):
                raise ValueError(f"Invalid GCS URI: {output_uri}")
                
            uri_parts = output_uri[5:].split("/", 1)
            bucket_name = uri_parts[0]
            prefix = uri_parts[1] if len(uri_parts) > 1 else ""
            
            logger.info(f"[DOWNLOAD] Downloading batch results from: {output_uri}")
            
            bucket = self.storage_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix=prefix))
            
            results = []
            for blob in blobs:
                if blob.name.endswith('.jsonl'):
                    logger.info(f"  Processing result file: {blob.name}")
                    
                    # Download and parse JSONL content
                    content = blob.download_as_text(encoding='utf-8')
                    
                    for line_num, line in enumerate(content.strip().split('\n'), 1):
                        if line.strip():
                            try:
                                result = json.loads(line)
                                results.append({
                                    "file": blob.name,
                                    "line": line_num,
                                    "result": result
                                })
                            except json.JSONDecodeError as e:
                                logger.warning(f"  Failed to parse line {line_num} in {blob.name}: {e}")
            
            logger.info(f"[SUCCESS] Downloaded {len(results)} batch results")
            return results
            
        except Exception as e:
            logger.error(f"Error downloading batch results: {e}")
            return []

    def save_results_to_workspace(self, results: List[Dict[str, Any]], output_uri: str) -> None:
        """
        Save batch processing results to local workspace for analysis.
        
        Args:
            results: List of batch processing results
            output_uri: Original output URI
        """
        try:
            workspace_dir = Path(__file__).parent / ".workspace" / "batch_results"
            workspace_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Save combined results
            combined_file = workspace_dir / f"batch_results_{timestamp}.json"
            with open(combined_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "batch_metadata": {
                        "processed_at": datetime.now().isoformat(),
                        "output_uri": output_uri,
                        "total_results": len(results)
                    },
                    "results": results
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[SAVE] Batch results saved to: {combined_file}")
            
            # Save individual results for easier analysis
            for i, result_item in enumerate(results):
                if "result" in result_item and "response" in result_item["result"]:
                    individual_file = workspace_dir / f"individual_result_{i+1:03d}_{timestamp}.json"
                    with open(individual_file, 'w', encoding='utf-8') as f:
                        json.dump(result_item["result"]["response"], f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Error saving results to workspace: {e}")


def test_vertex_ai_batch_processing():
    """
    Main test function for Vertex AI batch processing.
    """
    logger.info("[START] Starting Vertex AI Batch Processing Test")
    
    # Initialize batch tester
    batch_tester = VertexAIBatchTester()
    
    if not batch_tester.client:
        logger.error("[ERROR] Failed to initialize VertexAIBatchTester")
        return False
    
    # GCS files to process in batch
    gcs_files = [
        "gs://multi-modal-ai-bucket/session_data_fanatik_com_tr.json",
        "gs://multi-modal-ai-bucket/session_data_fotomac_com_tr.json", 
        "gs://multi-modal-ai-bucket/session_data_milliyet_com_tr.json",
        "gs://multi-modal-ai-bucket/session_data_sabah_com_tr.json"
    ]
    
    try:
        # Step 1: Load prompt template
        logger.info("[STEP1] Step 1: Loading prompt template...")
        prompt_template = batch_tester.load_prompt_template()
        if not prompt_template:
            logger.error("[ERROR] Failed to load prompt template")
            return False
        logger.info("[SUCCESS] Prompt template loaded successfully")
        
        # Step 2: Create batch request JSONL
        logger.info("[STEP2] Step 2: Creating batch request JSONL...")
        local_jsonl_path = batch_tester.create_batch_request_jsonl(gcs_files, prompt_template)
        if not local_jsonl_path:
            logger.error("[ERROR] Failed to create batch request JSONL")
            return False
        logger.info("[SUCCESS] Batch request JSONL created successfully")
        
        # Step 3: Upload to GCS
        logger.info("[STEP3] Step 3: Uploading batch request to GCS...")
        batch_request_gcs_uri = batch_tester.upload_batch_request_to_gcs(local_jsonl_path)
        if not batch_request_gcs_uri:
            logger.error("[ERROR] Failed to upload batch request to GCS")
            return False
        logger.info("[SUCCESS] Batch request uploaded to GCS successfully")
        
        # Step 4: Submit batch job
        logger.info("[STEP4] Step 4: Submitting batch job to Vertex AI...")
        job_name, output_uri = batch_tester.submit_batch_job(batch_request_gcs_uri)
        if not job_name:
            logger.error("[ERROR] Failed to submit batch job")
            return False
        logger.info("[SUCCESS] Batch job submitted successfully")
        
        # Step 5: Monitor batch job
        logger.info("[STEP5] Step 5: Monitoring batch job progress...")
        job_result = batch_tester.monitor_batch_job(job_name, polling_interval=30)
        
        if not job_result["success"]:
            logger.error(f"[ERROR] Batch job failed: {job_result}")
            return False
        
        logger.info(f"[SUCCESS] Batch job completed successfully in {job_result['elapsed_time']:.1f}s")
        
        # Step 6: Download and analyze results
        logger.info("[STEP6] Step 6: Downloading batch results...")
        results = batch_tester.download_batch_results(output_uri)
        
        if not results:
            logger.error("[ERROR] No results downloaded")
            return False
        
        logger.info(f"[SUCCESS] Downloaded {len(results)} batch results")
        
        # Step 7: Save results to workspace
        logger.info("[STEP7] Step 7: Saving results to workspace...")
        batch_tester.save_results_to_workspace(results, output_uri)
        logger.info("[SUCCESS] Results saved to workspace")
        
        # Summary
        logger.info("[COMPLETE] BATCH PROCESSING TEST COMPLETED SUCCESSFULLY!")
        logger.info(f"  [STATS] Files processed: {len(gcs_files)}")
        logger.info(f"  [STATS] Results generated: {len(results)}")
        logger.info(f"  [STATS] Processing time: {job_result['elapsed_time']:.1f}s")
        logger.info(f"  [STATS] Output location: {output_uri}")
        
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Error during batch processing test: {e}", exc_info=True)
        return False


def main():
    """Main test function."""
    logger.info("=" * 80)
    logger.info("[TEST] Vertex AI Batch Processing Test")
    logger.info("=" * 80)
    
    # Check environment variables
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        logger.error("[ERROR] GOOGLE_CLOUD_PROJECT environment variable not set")
        return
    
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.warning("[WARNING] GOOGLE_APPLICATION_CREDENTIALS not set - using default credentials")
    
    # Run the test
    success = test_vertex_ai_batch_processing()
    
    if success:
        logger.info("[SUCCESS] Vertex AI batch processing test completed successfully!")
    else:
        logger.error("[ERROR] Vertex AI batch processing test failed!")
    
    logger.info("=" * 80)
    logger.info("[FINISH] Test completed!")


if __name__ == "__main__":
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("Error: GOOGLE_CLOUD_PROJECT environment variable not set. This test requires it.")
        print("Set your Google Cloud project ID: export GOOGLE_CLOUD_PROJECT=your-project-id")
    else:
        main()
