"""
Test file for processing session data directly from Google Cloud Storage using Vertex AI.
Tests the AISummarizer functionality with multiple GCS-hosted session data files.

Processes files sequentially with 1-minute delays between each file to avoid rate limits.
Uses the same structure and patterns as the main ai_summarizer.py file.

Required environment variables:
- GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464
- GOOGLE_APPLICATION_CREDENTIALS=./gen-lang-client-0306766464-13fc9c9298ba.json
- GOOGLE_CLOUD_LOCATION=global

GCS Files Processed:
- gs://multi-modal-ai-bucket/session_data_fanatik_com_tr.json
- gs://multi-modal-ai-bucket/session_data_fotomac_com_tr.json
- gs://multi-modal-ai-bucket/session_data_milliyet_com_tr.json
- gs://multi-modal-ai-bucket/session_data_sabah_com_tr.json
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig, HttpOptions
from langchain_core.utils.json import parse_json_markdown

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()],
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

class AISummarizerGCS:
    """
    Tests AI Summarizer using session data stored in Google Cloud Storage.
    Uses the same structure and patterns as the main AISummarizer class.
    """
    
    def __init__(self, project_id: str = None, location: str = None, model_name: str = "gemini-2.5-pro"):
        """
        Initialize AISummarizer with GCS support using the same pattern as main ai_summarizer.py.
        """
        self.client = None
        self.model_name = model_name
        
        # Get configuration from environment variables or parameters
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        
        if not self.project_id:
            logger.error("Google Cloud project ID is not set. Set GOOGLE_CLOUD_PROJECT environment variable.")
            return

        try:
            # Initialize Vertex AI client with ADC and proper HTTP options
            # Use same pattern as main ai_summarizer.py
            http_options = HttpOptions(
                timeout=int(os.getenv("VERTEX_AI_TIMEOUT", "600000"))  # 10 minutes default (in milliseconds)
            )
            
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
                http_options=http_options
            )
            
            logger.info(f"AISummarizerGCS initialized with Vertex AI: project={self.project_id}, location={self.location}, model={model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI client: {e}", exc_info=True)
            self.client = None

    async def process_gcs_session_data(self, gcs_uri: str) -> Dict[str, Any]:
        """
        Process session data directly from Google Cloud Storage using Vertex AI.
        Uses the same structure and error handling as the main summarize_and_classify_session_data_object method.
        
        Args:
            gcs_uri (str): GCS URI in format gs://bucket-name/file-name.json
            
        Returns:
            Dict[str, Any]: Processed result from Gemini
        """
        if not self.client:
            logger.error("Vertex AI client is not initialized. Cannot process GCS data.")
            return {
                "error": "Summarizer not initialized",
                "processing_summary": {"total_input_articles": 0, "error": "Client not initialized"},
                "processed_articles": []
            }
        
        try:
            # Load PROMPT.md file - same pattern as main ai_summarizer.py
            prompt_md_path = Path(__file__).parent / "PROMPT.md"
            if not prompt_md_path.exists():
                logger.error(f"PROMPT.md file not found: {prompt_md_path}")
                return {
                    "error": f"PROMPT.md file not found: {prompt_md_path}",
                    "processing_summary": {"total_input_articles": 0, "error": "PROMPT.md not found"},
                    "processed_articles": []
                }

            with open(prompt_md_path, 'r', encoding='utf-8') as f:
                prompt_content = f.read()

            # Construct the complete prompt with JSON output request - same pattern
            combined_prompt = f"""{prompt_content}

## SESSION DATA TO PROCESS

Please process the session data from the provided JSON file according to the specifications above.

The data contains European sports news articles that need to be processed according to the OUTPUT FORMAT specified in the prompt above. Return the structured JSON result."""

            logger.info(f"Processing session data from GCS: {gcs_uri}")
            
            # Send to Vertex AI for processing with retry logic for quota errors - same pattern
            max_retries = 3
            base_delay = 10  # seconds
            
            for attempt in range(max_retries + 1):
                try:
                    # Use synchronous Vertex AI client call in thread pool - same pattern
                    config_params = {
                        "max_output_tokens": 65535
                    }
                    
                    # Add structured output if enabled - same pattern
                    if os.getenv("STRUCTURED_OUTPUT", "true").lower() == "true" and SCHEMA_AVAILABLE:
                        config_params["response_mime_type"] = "application/json"
                        config_params["response_schema"] = VERTEX_AI_RESPONSE_SCHEMA
                    
                    # Measure AI operation time - same pattern
                    ai_start_time = asyncio.get_event_loop().time()
                    response = await asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=[
                            combined_prompt,
                            types.Part.from_uri(
                                file_uri=gcs_uri,
                                mime_type="text/plain"
                            )
                        ],
                        config=GenerateContentConfig(**config_params))
                    ai_end_time = asyncio.get_event_loop().time()
                    ai_duration = ai_end_time - ai_start_time
                    
                    print(f"Attempt {attempt + 1}: Received response from Gemini for GCS file")
                    logger.info(f"AI operation completed in {ai_duration:.2f}s for GCS file: {gcs_uri} (attempt {attempt + 1})")
                    
                    # Clean the response content using langchain-core for reliable JSON parsing - same pattern
                    try:
                        if os.getenv("STRUCTURED_OUTPUT", "true").lower() == "true":
                            # For structured output, use response.parsed if available
                            if hasattr(response, 'parsed') and response.parsed:
                                logger.info("Parsing structured response")
                                result = response.parsed
                            else:
                                # Fallback: try to parse from response.text with langchain-core
                                logger.warning("No parsed response available, falling back to text parsing")
                                clean_json = parse_json_markdown(response.text)
                                result = clean_json
                        else:
                            # For unstructured output, always use langchain-core to clean the response
                            logger.info("Parsing unstructured response using langchain-core")
                            clean_json = parse_json_markdown(response.text)
                            result = clean_json
                            
                    except Exception as parse_error:
                        logger.error(f"Failed to parse response content: {parse_error}")
                        logger.debug(f"Raw response text: {response.text[:500]}...")
                        return {
                            "error": f"Failed to parse response: {str(parse_error)}",
                            "processing_summary": {"total_input_articles": 0, "error": "Response parsing failed"},
                            "processed_articles": []
                        }

                    # Record response usage_metadata - same pattern
                    try:
                        workspace_debug = Path(__file__).parent / ".workspace" / "debug"
                        workspace_debug.mkdir(parents=True, exist_ok=True)
                        
                        if hasattr(response, 'usage_metadata') and response.usage_metadata:
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            debug_file = workspace_debug / f"gcs_usage_metadata_{timestamp}.json"
                            
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                json.dump(response.usage_metadata, f, indent=2, ensure_ascii=False, default=str)
                            
                            logger.info(f"GCS usage metadata saved to: {debug_file}")
                        else:
                            logger.warning("No usage_metadata found in response")
                            
                    except Exception as debug_error:
                        logger.warning(f"Failed to save usage metadata: {debug_error}")
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e).lower() or "resource_exhausted" in str(e).lower():
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(f"Quota exceeded for GCS file. Retrying in {delay}s (attempt {attempt + 1}/{max_retries + 1})")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(f"Max retries exceeded for GCS file. Check Vertex AI quotas and billing.")
                            raise
                    else:
                        # Non-quota error, don't retry
                        raise

            # Validate the response structure matches our expected schema - same pattern
            if "processing_summary" in result and "processed_articles" in result:
                logger.info(f"Successfully processed GCS session data: {len(result.get('processed_articles', []))} articles processed")
                
                # Save the GCS result to workspace
                await self._save_gcs_result_to_workspace(gcs_uri, result)
                
                return result
            else:
                logger.error(f"Response structure validation failed. Keys: {list(result.keys())}")
                return {
                    "error": "Invalid response structure from Gemini",
                    "processing_summary": {"total_input_articles": 0, "error": "Invalid response structure"},
                    "processed_articles": []
                }

        except FileNotFoundError as e:
            logger.error(f"File not found error: {e}")
            return {
                "error": f"File not found: {str(e)}",
                "processing_summary": {"total_input_articles": 0, "error": "File not found"},
                "processed_articles": []
            }
        except Exception as e:
            logger.error(f"Error during GCS session data processing: {e}", exc_info=True)
            return {
                "error": f"GCS processing error: {str(e)}",
                "processing_summary": {"total_input_articles": 0, "error": "GCS processing error"},
                "processed_articles": []
            }

    async def _save_gcs_result_to_workspace(self, gcs_uri: str, result: Dict[str, Any]) -> None:
        """
        Save GCS processing result to workspace - similar pattern to main ai_summarizer.py.
        """
        try:
            workspace_debug = Path(__file__).parent / ".workspace" / "debug"
            workspace_debug.mkdir(parents=True, exist_ok=True)
            
            # Extract filename from GCS URI for result filename
            gcs_filename = Path(gcs_uri).stem  # Gets filename without extension
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            result_filename = f"gcs_result_{gcs_filename}_{timestamp}.json"
            
            enhanced_result = {
                **result,
                "gcs_metadata": {
                    "source_gcs_uri": gcs_uri,
                    "processed_at": datetime.now().isoformat(),
                    "model_used": self.model_name,
                    "project_id": self.project_id
                }
            }
            
            result_path = workspace_debug / result_filename
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(enhanced_result, f, indent=2, ensure_ascii=False)
            
            logger.info(f"GCS processing result saved to: {result_path}")
            
        except Exception as e:
            logger.error(f"Failed to save GCS result to workspace: {e}", exc_info=True)


async def test_gcs_session_data():
    """
    Test processing session data from Google Cloud Storage.
    Processes multiple GCS files sequentially with 1-minute delays between files.
    Uses the same pattern as test_ai_summarizer_with_session_data.py.
    """
    logger.info("🚀 Starting GCS Session Data Test")
    
    # Initialize GCS-enabled AI Summarizer
    summarizer = AISummarizerGCS()
    
    if not summarizer.client:
        logger.error("❌ Failed to initialize AISummarizerGCS")
        return False
    
    # GCS file locations to process sequentially
    gcs_files = [
        "gs://multi-modal-ai-bucket/session_data_fanatik_com_tr.json",
        "gs://multi-modal-ai-bucket/session_data_fotomac_com_tr.json", 
        "gs://multi-modal-ai-bucket/session_data_milliyet_com_tr.json",
        "gs://multi-modal-ai-bucket/session_data_sabah_com_tr.json"
    ]
    
    # Process files sequentially to avoid rate limits - same pattern as test_ai_summarizer_with_session_data.py
    logger.info(f"� Starting sequential processing of {len(gcs_files)} GCS files...")
    logger.info("Note: Using sequential processing to avoid Vertex AI rate limits")
    start_time = asyncio.get_event_loop().time()
    
    processed_results = []
    
    for i, gcs_uri in enumerate(gcs_files):
        # Extract source domain from filename for logging
        filename = Path(gcs_uri).stem  # e.g., session_data_fanatik_com_tr
        source_domain = filename.replace('session_data_', '').replace('_', '.')
        
        # Log session start
        logger.info(f"📝 Processing file {i+1}/{len(gcs_files)}: {source_domain} from {gcs_uri}")
        session_start_time = asyncio.get_event_loop().time()
        
        try:
            # Process GCS file without timeout wrapper (let Vertex AI handle its own timeouts)
            result = await summarizer.process_gcs_session_data(gcs_uri)
            
            session_end_time = asyncio.get_event_loop().time()
            session_duration = session_end_time - session_start_time
            
            if result.get("error"):
                logger.error(f"AI processing failed for {source_domain} after {session_duration:.1f}s: {result['error']}")
            else:
                processed_articles = len(result.get('processed_articles', []))
                logger.info(f"✅ Successfully processed {source_domain} after {session_duration:.1f}s: {processed_articles} articles processed")
                processed_results.append({
                    'source_domain': source_domain,
                    'gcs_uri': gcs_uri,
                    'result': result,
                    'file_index': i
                })
                
        except Exception as e:
            session_end_time = asyncio.get_event_loop().time()
            session_duration = session_end_time - session_start_time
            logger.error(f"❌ Exception processing {source_domain} after {session_duration:.1f}s: {str(e)}", exc_info=True)
            continue
        
        # Add 1-minute delay between files to avoid rate limiting (except for the last file)
        if i < len(gcs_files) - 1:
            logger.info(f"⏳ Waiting 60 seconds before processing next file ({i+2}/{len(gcs_files)})...")
            await asyncio.sleep(60)
    
    end_time = asyncio.get_event_loop().time()
    total_duration = end_time - start_time
    
    # Log final results
    logger.info(f"Sequential processing completed after {total_duration:.1f}s total")
    logger.info(f"Successfully processed {len(processed_results)} out of {len(gcs_files)} GCS files")
    
    for processed in processed_results:
        source_domain = processed['source_domain']
        result = processed['result']
        processing_summary = result.get('processing_summary', {})
        articles_processed = processing_summary.get('articles_after_cleaning', 0)
        logger.info(f"  - File {processed['file_index']+1}: {source_domain} -> {articles_processed} articles processed")
    
    return len(processed_results) > 0


async def main():
    """Main test function - same pattern as main ai_summarizer.py."""
    logger.info("=" * 80)
    logger.info("🧪 GCS Session Data Processing Test")
    logger.info("=" * 80)
    
    # Check environment variables - same pattern
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        logger.error("❌ GOOGLE_CLOUD_PROJECT environment variable not set")
        return
    
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.warning("⚠️  GOOGLE_APPLICATION_CREDENTIALS not set - using default credentials")
      # Run the test
    success = await test_gcs_session_data()
    
    if success:
        logger.info("✅ GCS session data test completed successfully!")
    else:
        logger.error("❌ GCS session data test failed!")
    
    logger.info("=" * 80)
    logger.info("🏁 Test completed!")


if __name__ == "__main__":
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("Error: GOOGLE_CLOUD_PROJECT environment variable not set. This test requires it.")
        print("Set your Google Cloud project ID: export GOOGLE_CLOUD_PROJECT=your-project-id")
    else:
        asyncio.run(main())
