"""
LLM Processor for Article Processing

Handles Vertex AI batch job submission and response parsing for article group processing.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from google.cloud import storage
from google import genai
from google.genai.types import CreateBatchJobConfig, HttpOptions

from .grouping_service import ArticleGroup
from .models import (
    VERTEX_AI_RESPONSE_SCHEMA,
    article_to_group_input,
    parse_llm_response,
    GroupProcessingResult,
    ProcessedArticle,
)

logger = logging.getLogger(__name__)


class LLMProcessor:
    """
    Handles LLM batch processing for article groups.

    Creates batch requests, submits to Vertex AI, and processes responses.
    """

    def __init__(
        self,
        genai_client: genai.Client,
        storage_client: storage.Client,
        bucket_name: str,
        model: str = "gemini-3-pro-preview",
        thinking_level: str = "LOW",
    ):
        """
        Initialize the LLM processor.

        Args:
            genai_client: Initialized genai.Client for Vertex AI
            storage_client: GCS storage client
            bucket_name: GCS bucket for batch files
            model: Vertex AI model to use
            thinking_level: Thinking level for model (LOW, MEDIUM, HIGH)
        """
        self.genai_client = genai_client
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.model = model
        self.thinking_level = thinking_level

        logger.info(f"LLMProcessor initialized: model={model}, thinking={thinking_level}")

    def load_prompt_template(self) -> str:
        """
        Load the unified prompt template.

        Returns:
            Prompt template string
        """
        prompt_paths = [
            Path(__file__).parent / "UNIFIED_PROMPT.md",
        ]

        for prompt_path in prompt_paths:
            if prompt_path.exists():
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                logger.info(f"Loaded prompt template from {prompt_path}")
                return content

        raise FileNotFoundError("UNIFIED_PROMPT.md not found")

    def create_batch_request(
        self,
        groups: List[ArticleGroup],
        articles: List[Dict[str, Any]],
        prompt_template: str,
    ) -> List[Dict]:
        """
        Create batch request entries for each article group.

        Args:
            groups: List of ArticleGroup objects
            articles: Full list of raw articles
            prompt_template: The prompt template to use

        Returns:
            List of batch request dictionaries
        """
        batch_requests = []

        for group in groups:
            # Extract articles for this group
            group_articles = [articles[idx] for idx in group.article_indices]

            # Format as LLM input
            group_input = article_to_group_input(
                articles=group_articles,
                group_id=group.group_id,
                max_similarity=group.max_similarity,
            )

            # Create request with prompt + data
            request = {
                "request": {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt_template},
                                {"text": f"\n\n## ARTICLE GROUP DATA\n\n```json\n{json.dumps(group_input, ensure_ascii=False, indent=2)}\n```"}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "candidateCount": 1,
                        "temperature": 0.1,
                        "topP": 0.95,
                        "maxOutputTokens": 65535,
                        "responseMimeType": "application/json",
                        "responseSchema": VERTEX_AI_RESPONSE_SCHEMA,
                        "thinkingConfig": {
                            "thinkingLevel": self.thinking_level
                        }
                    }
                }
            }

            batch_requests.append(request)

        logger.info(f"Created {len(batch_requests)} batch requests for {len(groups)} groups")
        return batch_requests

    def create_batch_request_for_singletons(
        self,
        singleton_groups: List[ArticleGroup],
        articles: List[Dict[str, Any]],
        prompt_template: str,
        batch_size: int = 10,
    ) -> List[Dict]:
        """
        Create optimized batch requests for singleton articles.

        Groups multiple singletons into single requests for efficiency.

        Args:
            singleton_groups: List of singleton ArticleGroup objects
            articles: Full list of raw articles
            prompt_template: The prompt template to use
            batch_size: Number of singletons per request

        Returns:
            List of batch request dictionaries
        """
        batch_requests = []

        # Process singletons in batches
        for i in range(0, len(singleton_groups), batch_size):
            batch_groups = singleton_groups[i:i + batch_size]

            # Create combined input for multiple singletons
            combined_input = {
                "batch_processing": True,
                "groups": []
            }

            for group in batch_groups:
                group_articles = [articles[idx] for idx in group.article_indices]
                group_input = article_to_group_input(
                    articles=group_articles,
                    group_id=group.group_id,
                    max_similarity=group.max_similarity,
                )
                combined_input["groups"].append(group_input)

            request = {
                "request": {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt_template},
                                {"text": f"\n\n## BATCH OF SINGLETON ARTICLES\n\nProcess each group independently.\n\n```json\n{json.dumps(combined_input, ensure_ascii=False, indent=2)}\n```"}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "candidateCount": 1,
                        "temperature": 0.1,
                        "topP": 0.95,
                        "maxOutputTokens": 65535,
                        "responseMimeType": "application/json",
                        "thinkingConfig": {
                            "thinkingLevel": self.thinking_level
                        }
                    }
                }
            }

            batch_requests.append(request)

        logger.info(f"Created {len(batch_requests)} batch requests for {len(singleton_groups)} singletons")
        return batch_requests

    def write_batch_jsonl(
        self,
        batch_requests: List[Dict],
        output_path: str,
    ) -> str:
        """
        Write batch requests to a JSONL file in GCS.

        Args:
            batch_requests: List of request dictionaries
            output_path: GCS blob path for the JSONL file

        Returns:
            GCS URI of the uploaded file
        """
        # Write to local temp file first
        local_path = Path("/tmp") / f"batch_request_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl"

        with open(local_path, 'w', encoding='utf-8') as f:
            for request in batch_requests:
                f.write(json.dumps(request, ensure_ascii=False) + '\n')

        # Upload to GCS
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(output_path)
        blob.upload_from_filename(str(local_path), content_type='application/x-ndjson')

        gcs_uri = f"gs://{self.bucket_name}/{output_path}"
        logger.info(f"Uploaded batch request to {gcs_uri}")

        # Clean up local file
        local_path.unlink()

        return gcs_uri

    def submit_batch_job(
        self,
        batch_request_uri: str,
        output_path: str,
        display_name: str,
    ) -> Tuple[str, str]:
        """
        Submit a batch job to Vertex AI.

        Args:
            batch_request_uri: GCS URI of the batch request JSONL
            output_path: GCS path for results
            display_name: Display name for the job

        Returns:
            Tuple of (job_name, output_uri)
        """
        output_uri = f"gs://{self.bucket_name}/{output_path}"

        batch_config = CreateBatchJobConfig(
            dest=output_uri,
            display_name=display_name,
        )

        logger.info(f"Submitting batch job: {display_name}")
        logger.info(f"  Source: {batch_request_uri}")
        logger.info(f"  Output: {output_uri}")

        job = self.genai_client.batches.create(
            model=self.model,
            src=batch_request_uri,
            config=batch_config,
        )

        logger.info(f"Batch job submitted: {job.name}, state: {job.state}")

        return job.name, output_uri

    def parse_batch_results(
        self,
        results_uri: str,
        groups: List[ArticleGroup],
    ) -> List[ProcessedArticle]:
        """
        Parse batch job results from GCS.

        Args:
            results_uri: GCS URI of the results JSONL
            groups: Original ArticleGroup list for metadata

        Returns:
            List of ProcessedArticle objects
        """
        # Download results
        if results_uri.startswith('gs://'):
            parts = results_uri.replace('gs://', '').split('/', 1)
            bucket_name = parts[0]
            blob_path = parts[1] if len(parts) > 1 else ''
        else:
            raise ValueError(f"Invalid GCS URI: {results_uri}")

        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        content = blob.download_as_text()

        # Parse JSONL results
        all_articles = []
        group_map = {g.group_id: g for g in groups}

        for line_num, line in enumerate(content.strip().split('\n')):
            if not line.strip():
                continue

            try:
                prediction = json.loads(line)

                # Extract response text
                candidates = prediction.get('response', {}).get('candidates', [])
                if not candidates:
                    logger.warning(f"No candidates in result line {line_num}")
                    continue

                response_text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                if not response_text:
                    logger.warning(f"Empty response in result line {line_num}")
                    continue

                # Parse the response
                response_data = json.loads(response_text)

                # Extract articles and add metadata
                for article in response_data.get('output_articles', []):
                    # Add grouping metadata if we can identify the group
                    grouping_meta = article.get('_grouping_metadata', {})
                    group_id = grouping_meta.get('group_id')

                    if group_id is not None and group_id in group_map:
                        group = group_map[group_id]
                        article['_grouping_metadata'] = {
                            'group_id': group.group_id,
                            'group_size': group.size,
                            'max_similarity': group.max_similarity,
                            'merge_decision': response_data.get('group_decision', 'UNKNOWN')
                        }

                    all_articles.append(article)

            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.error(f"Error parsing result line {line_num}: {e}")
                continue

        logger.info(f"Parsed {len(all_articles)} articles from batch results")
        return all_articles


def create_llm_processor(
    project_id: str,
    bucket_name: str,
    model: str = "gemini-3-pro-preview",
    thinking_level: str = "LOW",
) -> LLMProcessor:
    """
    Factory function to create an LLMProcessor with initialized clients.

    Args:
        project_id: GCP project ID
        bucket_name: GCS bucket name
        model: Vertex AI model
        thinking_level: Model thinking level

    Returns:
        Configured LLMProcessor instance
    """
    # Determine location based on model
    if "gemini-3" in model.lower():
        location = "global"
    else:
        location = os.getenv('VERTEX_AI_LOCATION', 'us-central1')

    http_options = HttpOptions(api_version="v1")

    genai_client = genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
        http_options=http_options,
    )

    storage_client = storage.Client()

    return LLMProcessor(
        genai_client=genai_client,
        storage_client=storage_client,
        bucket_name=bucket_name,
        model=model,
        thinking_level=thinking_level,
    )
