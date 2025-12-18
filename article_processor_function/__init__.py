"""
Article Processor Function

A unified article processing pipeline that uses vector embeddings for grouping
similar articles and a single LLM call per group for processing.

Replaces the two-stage batch_builder + result_merger architecture.
"""

from .embedding_service import EmbeddingService
from .grouping_service import GroupingService
from .llm_processor import LLMProcessor

__all__ = [
    "EmbeddingService",
    "GroupingService",
    "LLMProcessor",
]
