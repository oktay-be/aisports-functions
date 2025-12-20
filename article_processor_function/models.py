"""
Data Models for Article Processor Function

Pydantic models and Vertex AI response schemas for the unified article processing pipeline.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Input Models
# ============================================================================

class RawArticle(BaseModel):
    """Raw article from scraping session data."""
    article_id: str
    url: str
    title: str
    body: str = ""
    source: str = ""
    published_at: Optional[str] = None
    keywords_used: List[str] = Field(default_factory=list)
    language: str = "en"
    region: str = "eu"  # 'tr' or 'eu' - mapped from language


class ArticleGroupInput(BaseModel):
    """Input format for LLM processing - a group of similar articles."""
    group_id: int
    group_size: int
    max_similarity: float
    articles: List[Dict[str, Any]]


# ============================================================================
# Output Models
# ============================================================================

class CategoryAssignment(BaseModel):
    """Category assignment with confidence and evidence."""
    tag: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""


class KeyEntities(BaseModel):
    """Extracted key entities from article."""
    teams: List[str] = Field(default_factory=list)
    players: List[str] = Field(default_factory=list)
    amounts: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    competitions: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)


class GroupingMetadata(BaseModel):
    """Metadata about the grouping that produced this article."""
    group_id: int
    group_size: int
    max_similarity: float
    merge_decision: str  # "MERGED" or "KEPT_SEPARATE"


class ProcessedArticle(BaseModel):
    """Fully processed article output."""
    article_id: str
    original_url: str
    merged_from_urls: List[str] = Field(default_factory=list)
    title: str
    summary: str
    key_entities: KeyEntities = Field(default_factory=KeyEntities)
    categories: List[CategoryAssignment] = Field(default_factory=list)
    source: str
    published_date: str
    content_quality: str = "medium"  # "high", "medium", "low"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)  # Overall article confidence
    language: str = "turkish"
    region: str = "eu"  # 'tr' or 'eu' - preserved from input or decided by LLM during merge
    summary_translation: Optional[str] = None
    x_post: str = ""
    _grouping_metadata: Optional[GroupingMetadata] = None


class GroupProcessingResult(BaseModel):
    """Result of processing a single article group."""
    group_decision: str  # "MERGE" or "KEEP_SEPARATE"
    merge_reason: Optional[str] = None
    output_articles: List[ProcessedArticle]


class ProcessingSummary(BaseModel):
    """Summary statistics for the entire processing run."""
    total_input_articles: int
    total_output_articles: int
    groups_processed: int
    articles_merged: int
    articles_kept_separate: int
    singleton_articles: int
    embedding_model: str = "text-embedding-004"
    similarity_threshold: float = 0.85
    processing_date: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ProcessingOutput(BaseModel):
    """Complete output from article processing pipeline."""
    processing_summary: ProcessingSummary
    processed_articles: List[ProcessedArticle]


# ============================================================================
# Vertex AI Response Schema
# ============================================================================

# Schema for structured output from Vertex AI batch processing
VERTEX_AI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "group_decision": {
            "type": "STRING",
            "description": "Decision: MERGE or KEEP_SEPARATE"
        },
        "merge_reason": {
            "type": "STRING",
            "description": "Explanation for merge decision",
            "nullable": True
        },
        "output_articles": {
            "type": "ARRAY",
            "description": "Processed articles from this group",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "article_id": {
                        "type": "STRING",
                        "description": "Preserved article ID from input"
                    },
                    "original_url": {
                        "type": "STRING",
                        "description": "Primary URL for this article"
                    },
                    "merged_from_urls": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                        "description": "All URLs merged into this article"
                    },
                    "title": {
                        "type": "STRING",
                        "description": "Article title in original language"
                    },
                    "summary": {
                        "type": "STRING",
                        "description": "Comprehensive summary in ORIGINAL language"
                    },
                    "key_entities": {
                        "type": "OBJECT",
                        "properties": {
                            "teams": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            },
                            "players": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            },
                            "amounts": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            },
                            "dates": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            },
                            "competitions": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            },
                            "locations": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            }
                        }
                    },
                    "categories": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "tag": {"type": "STRING"},
                                "confidence": {"type": "NUMBER"},
                                "evidence": {"type": "STRING"}
                            },
                            "required": ["tag", "confidence"]
                        }
                    },
                    "source": {
                        "type": "STRING",
                        "description": "Source domain"
                    },
                    "published_date": {
                        "type": "STRING",
                        "description": "ISO timestamp"
                    },
                    "content_quality": {
                        "type": "STRING",
                        "description": "high, medium, or low"
                    },
                    "confidence": {
                        "type": "NUMBER",
                        "description": "Overall confidence score 0.0-1.0"
                    },
                    "language": {
                        "type": "STRING",
                        "description": "Detected language code"
                    },
                    "region": {
                        "type": "STRING",
                        "description": "Region: 'tr' for Turkish content, 'eu' for all other languages. When merging articles from different regions, preserve the region from the most complete source article."
                    },
                    "summary_translation": {
                        "type": "STRING",
                        "description": "Turkish translation if not Turkish",
                        "nullable": True
                    },
                    "x_post": {
                        "type": "STRING",
                        "description": "Turkish tweet, max 280 chars"
                    }
                },
                "required": [
                    "article_id",
                    "original_url",
                    "title",
                    "summary",
                    "categories",
                    "source",
                    "published_date",
                    "content_quality",
                    "confidence",
                    "language",
                    "region",
                    "x_post"
                ]
            }
        }
    },
    "required": ["group_decision", "output_articles"]
}


# ============================================================================
# Helper Functions
# ============================================================================

def article_to_group_input(articles: List[Dict], group_id: int, max_similarity: float) -> Dict:
    """
    Convert a list of article dicts to LLM input format.

    Args:
        articles: List of raw article dictionaries
        group_id: ID of the article group
        max_similarity: Maximum similarity score within group

    Returns:
        Dictionary formatted for LLM input
    """
    return {
        "group_id": group_id,
        "group_size": len(articles),
        "max_similarity": max_similarity,
        "articles": articles
    }


def parse_llm_response(response_text: str, group_id: int, group_size: int, max_similarity: float) -> GroupProcessingResult:
    """
    Parse LLM response and add grouping metadata.

    Args:
        response_text: JSON string from LLM
        group_id: ID of the processed group
        group_size: Number of articles in group
        max_similarity: Max similarity in group

    Returns:
        GroupProcessingResult with metadata added
    """
    import json

    data = json.loads(response_text)

    # Add grouping metadata to each output article
    for article in data.get("output_articles", []):
        article["_grouping_metadata"] = {
            "group_id": group_id,
            "group_size": group_size,
            "max_similarity": max_similarity,
            "merge_decision": data.get("group_decision", "UNKNOWN")
        }

    return GroupProcessingResult(**data)
