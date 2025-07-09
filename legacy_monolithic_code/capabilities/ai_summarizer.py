import asyncio
import logging
import os
import json
from typing import Dict, Any
from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions
from pathlib import Path
from .models import VERTEX_AI_RESPONSE_SCHEMA
from langchain_core.utils.json import parse_json_markdown

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import FileManager from journalist for file operations
try:
    from journalist.core.file_manager import FileManager
    FILEMANAGER_AVAILABLE = True
except ImportError:
    FILEMANAGER_AVAILABLE = False
    FileManager = None
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

class AISummarizer:
    """
    Uses Google's Vertex AI (Gemini 2.5 Pro) to process European sports news session data.
    Provides a single focused method for summarizing and classifying journalist session data.
    Uses Application Default Credentials for authentication.
    """    
    def __init__(self, project_id: str = None, location: str = None, model_name: str = "gemini-2.5-pro"):
        """
        Initializes the AISummarizer with Google Vertex AI using ADC.

        Args:
            project_id (str, optional): Google Cloud project ID. If None, gets from GOOGLE_CLOUD_PROJECT env var.
            location (str, optional): Vertex AI location. If None, gets from GOOGLE_CLOUD_LOCATION env var or defaults to "global".
            model_name (str, optional): The name of the Gemini model to use. Defaults to "gemini-2.5-pro".
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
            # ADC will automatically find credentials from GOOGLE_APPLICATION_CREDENTIALS            # Configure HTTP options with timeout for better reliability
            http_options = HttpOptions(
                # api_version="v1",
                timeout=int(os.getenv("VERTEX_AI_TIMEOUT", "600000"))  # 10 minutes default (in milliseconds)
            )
            
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
                http_options=http_options
            )
            
            logger.info(f"AISummarizer initialized with Vertex AI: project={self.project_id}, location={self.location}, model={model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI client: {e}", exc_info=True)
            self.client = None

    async def summarize_and_classify_session_data_object(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes journalist session data using the PROMPT.md instructions.
        
        Takes session data directly (e.g., tr_sessions[0] or eu_sessions[0]) and sends to Gemini 2.5 Pro
        for comprehensive processing including deduplication, cleaning, summarization, and 
        classification according to European sports news taxonomy.

        Args:
            session_data (Dict[str, Any]): Session data object containing articles and metadata
                                          (e.g., tr_sessions[0] with articles accessible via session_data["articles"])        Returns:
            Dict[str, Any]: Structured JSON result containing processed articles with summaries,
                           classifications, and processing metadata according to PROMPT.md specifications.
                           Returns error structure if processing fails.
        """
        if not self.client:
            logger.error("Vertex AI client is not initialized. Cannot process session data.")
            return {
                "error": "Summarizer not initialized",
                "processing_summary": {"total_input_articles": 0, "error": "Client not initialized"},
                "processed_articles": []
            }

        try:
            # Load PROMPT.md file
            prompt_md_path = Path(__file__).parent.parent / "PROMPT.md"
            if not prompt_md_path.exists():
                logger.error(f"PROMPT.md file not found: {prompt_md_path}")
                return {
                    "error": f"PROMPT.md file not found: {prompt_md_path}",
                    "processing_summary": {"total_input_articles": 0, "error": "PROMPT.md not found"},
                    "processed_articles": []
                }

            with open(prompt_md_path, 'r', encoding='utf-8') as f:                prompt_content = f.read()
              # Construct the complete prompt with JSON output request
            combined_prompt = f"""{prompt_content}

## SESSION DATA TO PROCESS

Please process the following European sports news session data according to the specifications above:

{json.dumps(session_data, indent=2, ensure_ascii=False)}

Process this data according to the OUTPUT FORMAT specified in the prompt above and return the structured JSON result."""

            articles_count = len(session_data.get('articles', []))
            source_domain = session_data.get('source_domain', 'unknown domain')
            logger.info(f"Processing session data with {articles_count} articles from {source_domain}")            # Send to Vertex AI for processing with retry logic for quota errors
            max_retries = 3
            base_delay = 10  # seconds
            
            for attempt in range(max_retries + 1):
                try:
                    # Use synchronous Vertex AI client call in thread pool
                    config_params = {
                        "max_output_tokens": 65535
                    }
                      # Add structured output if enabled
                    if os.getenv("STRUCTURED_OUTPUT", "true").lower() == "true":
                        config_params["response_mime_type"] = "application/json"
                        config_params["response_schema"] = VERTEX_AI_RESPONSE_SCHEMA
                    
                    # Measure AI operation time
                    ai_start_time = asyncio.get_event_loop().time()
                    response = await asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=[combined_prompt],
                        config=GenerateContentConfig(**config_params))
                    ai_end_time = asyncio.get_event_loop().time()
                    ai_duration = ai_end_time - ai_start_time
                    
                    print(f"Attempt {attempt + 1}: Received response from Gemini for {source_domain}")
                    logger.info(f"AI operation completed in {ai_duration:.2f}s for {source_domain} (attempt {attempt + 1})")
                    
                    # Clean the response content using langchain-core for reliable JSON parsing
                    try:
                        if os.getenv("STRUCTURED_OUTPUT", "true").lower() == "true":
                            # For structured output, use response.parsed if available
                            if hasattr(response, 'parsed') and response.parsed:
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
                            "processing_summary": {"total_input_articles": len(session_data.get('articles', [])), "error": "Response parsing failed"},
                            "processed_articles": []
                        }
                      # Record response usage_metadata
                    try:
                        workspace_debug = Path(__file__).parent.parent / ".workspace" / "debug"
                        workspace_debug.mkdir(parents=True, exist_ok=True)
                        
                        if hasattr(response, 'usage_metadata') and response.usage_metadata:
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            debug_file = workspace_debug / f"usage_metadata_{timestamp}.json"
                            
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                json.dump(response.usage_metadata, f, indent=2, ensure_ascii=False, default=str)
                            
                            logger.info(f"Usage metadata saved to: {debug_file}")
                        else:
                            logger.warning("No usage_metadata found in response")
                            
                    except Exception as debug_error:
                        logger.warning(f"Failed to save usage metadata: {debug_error}")
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e).lower() or "resource_exhausted" in str(e).lower():
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(f"Quota exceeded for {source_domain}. Retrying in {delay}s (attempt {attempt + 1}/{max_retries + 1})")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(f"Max retries exceeded for {source_domain}. Check Vertex AI quotas and billing.")
                            raise
                    else:
                        # Non-quota error, don't retry
                        raise

            # Validate the response structure matches our expected schema
            if "processing_summary" in result and "processed_articles" in result:
                logger.info(f"Successfully processed session data: {len(result.get('processed_articles', []))} articles processed")
                
                # Save the AI summary to workspace
                await self._save_ai_summary_to_workspace(session_data, result)
                
                return result
            else:
                logger.error(f"Response structure validation failed. Keys: {list(result.keys())}")
                return {
                    "error": "Invalid response structure from Gemini",
                    "processing_summary": {"total_input_articles": len(session_data.get('articles', [])), "error": "Invalid response structure"},
                    "processed_articles": []
                }

        except FileNotFoundError as e:
            logger.error(f"File not found error: {e}")
            return {
                "error": f"File not found: {str(e)}",
                "processing_summary": {"total_input_articles": 0, "error": "File not found"},
                "processed_articles": []
            }
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing session data JSON: {e}")
            return {
                "error": f"Session data JSON error: {str(e)}",
                "processing_summary": {"total_input_articles": 0, "error": "Session data JSON error"},
                "processed_articles": []
            }
        except Exception as e:
            logger.error(f"Error during session data processing: {e}", exc_info=True)
            return {
                "error": f"Processing error: {str(e)}",
                "processing_summary": {"total_input_articles": 0, "error": "Processing error"},
                "processed_articles": []
            }
    
    async def _save_ai_summary_to_workspace(self, session_data: Dict[str, Any], result: Dict[str, Any]) -> None:
        """
        Save AI summary result to workspace directory structure using journalist's FileManager.
        
        Creates: .workspace/<session_id>/ai_summarized_session_data_<source>.json
        
        Args:
            session_data: Original session data containing metadata
            result: AI processing result to save
        """
        try:
            # Extract session_id from session_data
            session_metadata = session_data.get('session_metadata', {})
            session_id = session_metadata.get('session_id')
            
            if not session_id:
                logger.warning("No session_id found in session_data, cannot save to workspace")
                return
            
            # Extract source domain for filename
            source_domain = session_data.get('source_domain', 'unknown_source')
            
            # Create workspace directory structure
            workspace_root = Path(__file__).parent.parent / ".workspace"
            session_workspace = workspace_root / session_id
            session_workspace.mkdir(parents=True, exist_ok=True)
            
            # Use journalist's FileManager for consistent file operations
            if FILEMANAGER_AVAILABLE:
                # Initialize FileManager for this workspace directory
                file_manager = FileManager(str(session_workspace))
                
                # Use FileManager's sanitization for the domain
                clean_source = file_manager._sanitize_filename(
                    source_domain.replace('www.', '').replace('.', '_').replace('-', '_')
                )
                
                # Create filename following the convention
                filename = f"ai_summarized_session_data_{clean_source}.json"
                
                # Add metadata to the result
                enhanced_result = {
                    **result,
                    "workspace_metadata": {
                        "session_id": session_id,
                        "source_domain": source_domain,
                        "original_articles_count": len(session_data.get('articles', [])),
                        "processed_at": datetime.now().isoformat(),
                        "saved_to": str(session_workspace / filename)
                    }
                }
                
                # Use FileManager's save_json_data method
                file_path = str(session_workspace / filename)
                success = file_manager.save_json_data(
                    file_path, 
                    enhanced_result, 
                    data_type=f"AI summary for {source_domain}"
                )
                
                if success:
                    logger.info(f"AI summary saved using FileManager to: {file_path}")
                else:
                    logger.error(f"FileManager failed to save AI summary to: {file_path}")
                    
            else:
                # Fallback to original method if FileManager not available
                logger.warning("FileManager not available, using fallback file operations")
                clean_source = source_domain.replace('www.', '').replace('.', '_')
                filename = f"ai_summarized_session_data_{clean_source}.json"
                output_path = session_workspace / filename
                
                enhanced_result = {
                    **result,
                    "workspace_metadata": {
                        "session_id": session_id,
                        "source_domain": source_domain,
                        "original_articles_count": len(session_data.get('articles', [])),
                        "processed_at": datetime.now().isoformat(),
                        "saved_to": str(output_path)
                    }
                }
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(enhanced_result, f, indent=2, ensure_ascii=False)
                
                logger.info(f"AI summary saved (fallback) to: {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to save AI summary to workspace: {e}", exc_info=True)


# Example Usage (for testing this module directly)
async def main_test_summarizer():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Initialize with Vertex AI (requires GOOGLE_CLOUD_PROJECT environment variable)
    summarizer = AISummarizer() 

    if not summarizer.client:
        print("AISummarizer (Vertex AI) could not be initialized. Exiting test.")
        print("Ensure GOOGLE_CLOUD_PROJECT environment variable is set and Vertex AI is enabled.")
        return
          # Test with available session data files
    journalist_workspace = Path(".journalist_workspace")
    
    if journalist_workspace.exists():
        # Find available session directories
        session_dirs = [d for d in journalist_workspace.iterdir() if d.is_dir()]
        
        if session_dirs:
            # Use the most recent session directory
            latest_session = max(session_dirs, key=lambda x: x.name)
            session_files = list(latest_session.glob("session_data_*.json"))
            
            if session_files:
                print(f"\\n--- Testing Session Data Processing ---")
                print(f"Found {len(session_files)} session data files in: {latest_session}")
                
                # Test with the first session data file
                session_file = session_files[0]
                print(f"Loading session data from: {session_file}")
                
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                result = await summarizer.summarize_and_classify_session_data_object(session_data)
                
                print("\\nProcessing Result:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"No session data files found in: {latest_session}")
        else:
            print("No session directories found in .journalist_workspace")
    else:
        print("No .journalist_workspace directory found.")
        print("Run the journalist tool first to generate session data for testing.")


if __name__ == "__main__":
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("Error: GOOGLE_CLOUD_PROJECT environment variable not set. This test requires it.")
        print("Set your Google Cloud project ID: export GOOGLE_CLOUD_PROJECT=your-project-id")
    else:
        asyncio.run(main_test_summarizer())
