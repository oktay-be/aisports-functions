"""
AI Aggregator for AISports application.
Handles aggregation of source-specific AI summaries and NewsAPI integration.
Uses Google Vertex AI with Application Default Credentials (ADC).
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path
from google import genai

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import our database client
from database.mongodb_client import MongoDBClient

logger = logging.getLogger(__name__)

class AIAggregator:
    """
    AI-powered aggregator for combining source summaries and generating diffs.
    Uses Google Vertex AI with Application Default Credentials (ADC).
    """
    
    def __init__(self, project_id: str = None, location: str = None, model_name: str = "gemini-2.5-pro"):
        """
        Initialize AI Aggregator with Vertex AI using ADC.
        
        Args:
            project_id (str, optional): Google Cloud project ID. If None, gets from GOOGLE_CLOUD_PROJECT env var.
            location (str, optional): Vertex AI location. If None, gets from GOOGLE_CLOUD_LOCATION env var or defaults to "global".
            model_name (str, optional): The name of the Gemini model to use. Defaults to "gemini-2.5-pro".
        """
        self.client = None
        self.model_name = model_name
        self.db_client = None
        
        # Get configuration from environment variables or parameters
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location or os.getenv("GOOGLE_CLOUD_LOCATION", "global")

        if not self.project_id:
            logger.error("Google Cloud project ID is not set. Set GOOGLE_CLOUD_PROJECT environment variable.")
            return

        try:
            # Initialize Vertex AI client with ADC
            # ADC will automatically find credentials from GOOGLE_APPLICATION_CREDENTIALS
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location
            )
            
            logger.info(f"AIAggregator initialized with Vertex AI: project={self.project_id}, location={self.location}, model={model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI client: {e}", exc_info=True)
            self.client = None
    
    async def initialize(self):
        """Initialize database connection."""
        self.db_client = MongoDBClient()
        await self.db_client.connect()
    
    async def aggregate_sources_by_region(self, run_id: str, region: str) -> Dict:
        """
        Aggregate all source summaries for a region using AI.
        
        This method:
        1. Retrieves all source summaries for the region from MongoDB
        2. Combines them using AI to create regional aggregation
        3. Saves the result to MongoDB
        
        Args:
            run_id: Collection run identifier
            region: "TR" or "EU"
        
        Returns:
            Dict: Aggregated result in ai_summarized_{region}.json format
        """
        try:
            if not self.db_client:
                await self.initialize()
            
            logger.info(f"Starting aggregation for region {region}, run {run_id}")
            
            # Get all source summaries for this region
            source_summaries = await self.db_client.get_run_summaries(run_id, region)
            
            if not source_summaries:
                logger.warning(f"No source summaries found for region {region}, run {run_id}")
                return {
                    "error": f"No source summaries found for region {region}",
                    "run_id": run_id,
                    "region": region
                }
            
            logger.info(f"Found {len(source_summaries)} source summaries for {region}")
            
            # Prepare aggregation prompt
            aggregation_prompt = self._create_aggregation_prompt(source_summaries, region)
            
            # Use AI to aggregate
            aggregated_result = await self._run_ai_aggregation(aggregation_prompt, region)
            
            # Prepare data for MongoDB storage
            aggregated_data = {
                "run_id": run_id,
                "region": region,
                "aggregation_type": "scraped_only",
                "aggregated_data": aggregated_result,
                "source_count": len(source_summaries),
                "sources_processed": [summary["source_domain"] for summary in source_summaries]
            }
            
            # Save to MongoDB
            saved_id = await self.db_client.save_aggregated_result(aggregated_data)
            logger.info(f"Saved aggregated result for {region}: {saved_id}")
            
            return aggregated_result
            
        except Exception as e:
            logger.error(f"Error aggregating sources for region {region}: {e}")
            return {
                "error": str(e),
                "run_id": run_id,
                "region": region
            }
    
    async def extend_eu_with_newsapi(self, run_id: str, eu_aggregated: Dict, newsapi_data: Dict) -> Dict:
        """
        Extend EU aggregated data with NewsAPI results.
        
        Args:
            run_id: Collection run identifier
            eu_aggregated: Existing EU aggregated data
            newsapi_data: NewsAPI fetched and transformed data
        
        Returns:
            Dict: Extended result in ai_summarized_eu_extended.json format
        """
        try:
            if not self.db_client:
                await self.initialize()
            
            logger.info(f"Extending EU data with NewsAPI for run {run_id}")
            
            # Prepare extension prompt
            extension_prompt = self._create_extension_prompt(eu_aggregated, newsapi_data)
            
            # Use AI to extend
            extended_result = await self._run_ai_extension(extension_prompt)
            
            # Prepare data for MongoDB storage
            extended_data = {
                "run_id": run_id,
                "region": "EU",
                "aggregation_type": "extended_with_newsapi",
                "aggregated_data": extended_result,
                "newsapi_articles_added": len(newsapi_data.get("transformed_articles", [])),
                "extension_timestamp": datetime.now(timezone.utc)
            }
            
            # Save to MongoDB
            saved_id = await self.db_client.save_aggregated_result(extended_data)
            logger.info(f"Saved extended EU result: {saved_id}")
            
            return extended_result
            
        except Exception as e:
            logger.error(f"Error extending EU data with NewsAPI: {e}")
            return {
                "error": str(e),
                "run_id": run_id,
                "region": "EU_extended"
            }
    
    async def generate_ai_diff(self, run_id: str) -> Dict:
        """
        Generate AI-powered diff between EU extended and TR aggregated data.
        
        Args:
            run_id: Collection run identifier
        
        Returns:
            Dict: Diff analysis with missing entities for targeting
        """
        try:
            if not self.db_client:
                await self.initialize()
            
            logger.info(f"Generating AI diff for run {run_id}")
            
            # Get EU extended result
            eu_extended = await self.db_client.get_aggregated_result(
                run_id, "EU", "extended_with_newsapi"
            )
            
            # Get TR aggregated result
            tr_aggregated = await self.db_client.get_aggregated_result(
                run_id, "TR", "scraped_only"
            )
            
            if not eu_extended or not tr_aggregated:
                missing = []
                if not eu_extended:
                    missing.append("EU extended data")
                if not tr_aggregated:
                    missing.append("TR aggregated data")
                
                error_msg = f"Missing required data for diff: {', '.join(missing)}"
                logger.error(error_msg)
                return {"error": error_msg, "run_id": run_id}
            
            # Prepare diff prompt
            diff_prompt = self._create_diff_prompt(
                eu_extended["aggregated_data"], 
                tr_aggregated["aggregated_data"]
            )
            
            # Use AI to generate diff
            diff_result = await self._run_ai_diff(diff_prompt)
            
            # Prepare data for MongoDB storage
            diff_data = {
                "run_id": run_id,
                "comparison_type": "eu_extended_vs_tr",
                "compared_files": {
                    "eu_file_id": str(eu_extended["_id"]),
                    "tr_file_id": str(tr_aggregated["_id"])
                },
                "diff_analysis": diff_result,
                "missing_entities_for_targeting": diff_result.get("entities_in_eu_only", [])
            }
            
            # Save to MongoDB
            saved_id = await self.db_client.save_diff_result(diff_data)
            logger.info(f"Saved diff result: {saved_id}")
            
            return diff_result
            
        except Exception as e:
            logger.error(f"Error generating AI diff: {e}")
            return {
                "error": str(e),
                "run_id": run_id
            }
    
    def _create_aggregation_prompt(self, source_summaries: List[Dict], region: str) -> str:
        """Create prompt for AI aggregation of source summaries."""
        sources_data = []
        total_articles = 0
        
        for summary in source_summaries:
            source_data = summary["summary_data"]
            sources_data.append({
                "source": summary["source_domain"],
                "url": summary.get("source_url", ""),
                "summary": source_data
            })
            total_articles += len(source_data.get("processed_articles", []))
        
        prompt = f"""
You are an AI aggregator for European sports news. Your task is to aggregate multiple source-specific summaries into a unified regional summary.

TASK: Aggregate {len(source_summaries)} source summaries for {region} region into a single unified summary.

INPUT DATA:
- Total articles from all sources: {total_articles}
- Sources: {[s["source_domain"] for s in source_summaries]}

SOURCE SUMMARIES:
{json.dumps(sources_data, indent=2, ensure_ascii=False)}

INSTRUCTIONS:
1. Combine all processed_articles from all sources
2. Remove exact duplicates (same URL or very similar content)
3. Merge similar articles about the same topic/event
4. Maintain all entity classifications and categories
5. Create aggregated statistics and summaries
6. Preserve source attribution for each article

OUTPUT FORMAT (JSON):
{{
    "processing_summary": {{
        "total_input_articles": <total from all sources>,
        "articles_after_deduplication": <count after removing duplicates>,
        "articles_after_cleaning": <final count>,
        "duplicates_removed": <count>,
        "sources_aggregated": <list of source domains>,
        "processing_date": "<current ISO timestamp>",
        "region": "{region}"
    }},
    "processed_articles": [
        {{
            "id": "article_X",
            "original_url": "...",
            "title": "...",
            "summary": "...",
            "key_entities": {{...}},
            "categories": [...],
            "source": "...",
            "published_date": "...",
            "keywords_matched": [...],
            "content_quality": "...",
            "language": "..."
        }}
    ],
    "aggregation_metadata": {{
        "entities_summary": {{
            "teams": [...],
            "players": [...],
            "total_entities": <count>
        }},
        "categories_distribution": {{...}},
        "sources_contribution": {{...}}
    }}
}}

Provide the aggregated result as clean JSON.
"""
        return prompt
    
    def _create_extension_prompt(self, eu_aggregated: Dict, newsapi_data: Dict) -> str:
        """Create prompt for extending EU data with NewsAPI."""
        prompt = f"""
You are an AI data extender for European sports news. Your task is to extend existing EU aggregated data with NewsAPI articles.

TASK: Extend the existing EU aggregated data with new articles from NewsAPI, ensuring no duplicates and maintaining data quality.

EXISTING EU DATA:
{json.dumps(eu_aggregated, indent=2, ensure_ascii=False)}

NEWSAPI DATA TO INTEGRATE:
{json.dumps(newsapi_data.get("transformed_articles", []), indent=2, ensure_ascii=False)}

INSTRUCTIONS:
1. Add NewsAPI articles to the existing processed_articles array
2. Remove any duplicates between existing and new articles
3. Ensure all new articles follow the same schema format
4. Update processing_summary with new counts
5. Maintain entity classifications and categories
6. Update aggregation_metadata with new data

OUTPUT FORMAT (JSON):
{{
    "processing_summary": {{
        "total_input_articles": <updated total>,
        "articles_after_deduplication": <updated count>,
        "articles_after_cleaning": <updated count>,
        "duplicates_removed": <updated count>,
        "sources_aggregated": <updated list>,
        "newsapi_articles_added": <count of new articles>,
        "processing_date": "<current ISO timestamp>",
        "region": "EU_extended"
    }},
    "processed_articles": [
        <all articles combined and deduplicated>
    ],
    "aggregation_metadata": {{
        "entities_summary": {{...}},
        "categories_distribution": {{...}},
        "sources_contribution": {{...}},
        "newsapi_contribution": {{...}}
    }}
}}

Provide the extended result as clean JSON.
"""
        return prompt
    
    def _create_diff_prompt(self, eu_extended: Dict, tr_aggregated: Dict) -> str:
        """Create prompt for AI-powered diff analysis."""
        prompt = f"""
You are an AI analyst for European sports news comparison. Your task is to identify differences between EU and Turkish sports news coverage.

TASK: Compare EU extended news coverage with Turkish news coverage and identify key differences, especially missing entities and topics.

EU EXTENDED DATA:
{json.dumps(eu_extended, indent=2, ensure_ascii=False)}

TURKISH DATA:
{json.dumps(tr_aggregated, indent=2, ensure_ascii=False)}

INSTRUCTIONS:
1. Identify entities (players, teams, topics) mentioned in EU but missing in TR
2. Identify entities mentioned in TR but missing in EU
3. Find common entities with different coverage sentiment/focus
4. Analyze transfer rumors, match results, and other sports topics
5. Provide insights for targeted scraping opportunities

OUTPUT FORMAT (JSON):
{{
    "entities_in_eu_only": [
        "Player Name 1",
        "Team Name 1",
        "Topic 1"
    ],
    "entities_in_tr_only": [
        "Turkish Player 1",
        "Turkish Topic 1"
    ],
    "common_entities": [
        {{
            "entity": "Fenerbahçe",
            "eu_mentions": 5,
            "tr_mentions": 12,
            "sentiment_difference": "EU more neutral, TR more positive"
        }}
    ],
    "trending_topics_diff": {{
        "eu_trending": [...],
        "tr_trending": [...],
        "unique_to_eu": [...],
        "unique_to_tr": [...]
    }},
    "transfer_rumors_comparison": {{
        "eu_exclusive_rumors": [...],
        "tr_exclusive_rumors": [...],
        "conflicting_reports": [...]
    }},
    "sentiment_analysis": {{
        "eu_sentiment": "neutral/positive/negative",
        "tr_sentiment": "neutral/positive/negative",
        "sentiment_reasons": "..."
    }},
    "recommendations_for_targeting": [
        {{
            "keyword": "Vlahovic",
            "reason": "Mentioned 8 times in EU sources but not in TR sources",
            "priority": "high"
        }}
    ]
}}

Provide the diff analysis as clean JSON.
"""
        return prompt
    
    async def _run_ai_aggregation(self, prompt: str, region: str) -> Dict:
        """Run AI aggregation using Vertex AI client directly."""
        if not self.client:
            logger.error("Vertex AI client is not initialized. Cannot run aggregation.")
            return {
                "error": "AIAggregator client not initialized",
                "processing_summary": {"total_input_articles": 0, "error": "Client not initialized"},
                "processed_articles": []
            }

        try:
            logger.info(f"Running AI aggregation for region {region}")
              # Use Vertex AI to process the aggregation prompt
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 8192,
                    "response_mime_type": "application/json"
                }
            )
            
            # Parse the JSON response
            result_text = response.text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            result = json.loads(result_text)
            
            logger.info(f"AI aggregation completed successfully for {region}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI aggregation response as JSON: {e}")
            return {
                "error": f"JSON parsing error: {str(e)}",
                "processing_summary": {"total_input_articles": 0, "error": "JSON parsing failed"},
                "processed_articles": []
            }
        except Exception as e:
            logger.error(f"Error in AI aggregation: {e}")
            return {
                "error": str(e),
                "processing_summary": {"total_input_articles": 0, "error": str(e)},
                "processed_articles": []            }
    
    async def _run_ai_extension(self, prompt: str) -> Dict:
        """Run AI extension using Vertex AI client directly."""
        if not self.client:
            logger.error("Vertex AI client is not initialized. Cannot run extension.")
            return {
                "error": "AIAggregator client not initialized",
                "processing_summary": {"total_input_articles": 0, "error": "Client not initialized"},
                "processed_articles": []
            }

        try:
            logger.info("Running AI extension")
              # Use Vertex AI to process the extension prompt
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 8192,
                    "response_mime_type": "application/json"
                }
            )
            
            # Parse the JSON response
            result_text = response.text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            result = json.loads(result_text)
            
            logger.info("AI extension completed successfully")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI extension response as JSON: {e}")
            return {
                "error": f"JSON parsing error: {str(e)}",
                "processing_summary": {"total_input_articles": 0, "error": "JSON parsing failed"},
                "processed_articles": []
            }
        except Exception as e:
            logger.error(f"Error in AI extension: {e}")
            return {
                "error": str(e),
                "processing_summary": {"total_input_articles": 0, "error": str(e)},
                "processed_articles": []            }
    
    async def _run_ai_diff(self, prompt: str) -> Dict:
        """Run AI diff analysis using Vertex AI client directly."""
        if not self.client:
            logger.error("Vertex AI client is not initialized. Cannot run diff analysis.")
            return {
                "error": "AIAggregator client not initialized",
                "entities_in_eu_only": [],
                "entities_in_tr_only": [],
                "common_entities": [],
                "trending_topics_diff": {},
                "transfer_rumors_comparison": {},
                "sentiment_analysis": {},
                "recommendations_for_targeting": []
            }

        try:
            logger.info("Running AI diff analysis")
              # Use Vertex AI to process the diff prompt
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 8192,
                    "response_mime_type": "application/json"
                }
            )
            
            # Parse the JSON response
            result_text = response.text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            result = json.loads(result_text)
            
            logger.info("AI diff analysis completed successfully")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI diff response as JSON: {e}")
            return {
                "error": f"JSON parsing error: {str(e)}",
                "entities_in_eu_only": [],
                "entities_in_tr_only": [],
                "common_entities": [],
                "trending_topics_diff": {},
                "transfer_rumors_comparison": {},
                "sentiment_analysis": {},
                "recommendations_for_targeting": []
            }
        except Exception as e:
            logger.error(f"Error in AI diff analysis: {e}")
            return {
                "error": str(e),
                "entities_in_eu_only": [],
                "entities_in_tr_only": [],
                "common_entities": [],
                "trending_topics_diff": {},
                "transfer_rumors_comparison": {},
                "sentiment_analysis": {},
                "recommendations_for_targeting": []
            }


# Example usage and testing
async def test_ai_aggregator():
    """Test AI Aggregator functionality with Vertex AI."""
    print("🧪 Testing AI Aggregator with Vertex AI...")
    
    try:
        # Check Vertex AI environment variables
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        
        if not project_id:
            print("❌ GOOGLE_CLOUD_PROJECT environment variable not set")
            print("   Set it in your .env file: GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464")
            return
            
        if not credentials_path:
            print("❌ GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
            print("   Set it in your .env file: GOOGLE_APPLICATION_CREDENTIALS=./gen-lang-client-0306766464-13fc9c9298ba.json")
            return
        
        print(f"✅ Using Vertex AI with project: {project_id}")
        print(f"✅ Using credentials file: {credentials_path}")
        
        aggregator = AIAggregator()
        await aggregator.initialize()
        
        print("✅ AI Aggregator initialized successfully with Vertex AI")
        
        # Test aggregation (will use placeholder data for now)
        test_run_id = "test_run_123"
        test_region = "TR"
        
        result = await aggregator.aggregate_sources_by_region(test_run_id, test_region)
        print(f"✅ Aggregation test completed: {result.get('processing_summary', {}).get('region', 'N/A')}")
        
        print("✅ AI Aggregator test completed successfully")
        
    except Exception as e:
        print(f"❌ AI Aggregator test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        print("Error: GOOGLE_CLOUD_PROJECT environment variable not set. This test requires it.")
        print("Set your Google Cloud project ID: GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464")
    else:
        asyncio.run(test_ai_aggregator())
