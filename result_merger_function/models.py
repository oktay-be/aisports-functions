"""
Data models and schemas for the Result Merger Function.
Reuses the VERTEX_AI_RESPONSE_SCHEMA from batch_builder_function.
"""

# Vertex AI Response Schema - Used for structured output
# This schema ensures consistent JSON responses from the AI model
VERTEX_AI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "processing_summary": {
            "type": "object",
            "properties": {
                "total_articles_processed": {"type": "integer"},
                "articles_deduplicated": {"type": "integer"},
                "articles_removed_low_quality": {"type": "integer"},
                "articles_kept": {"type": "integer"},
                "processing_notes": {"type": "string"}
            },
            "required": [
                "total_articles_processed",
                "articles_deduplicated",
                "articles_removed_low_quality",
                "articles_kept"
            ]
        },
        "processed_articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "string"},
                    "original_url": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "source": {"type": "string"},
                    "published_date": {"type": "string"},
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "key_entities": {
                        "type": "object",
                        "properties": {
                            "teams": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "players": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "competitions": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "locations": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        }
                    },
                    "content_quality": {
                        "type": "string",
                        "enum": ["high", "medium", "low"]
                    },
                    "confidence": {"type": "number"},
                    "language": {"type": "string"},
                    "summary_translation": {"type": "string"},
                    "x_post": {"type": "string"}
                },
                "required": [
                    "article_id",
                    "original_url",
                    "title",
                    "summary",
                    "source",
                    "published_date",
                    "categories",
                    "key_entities",
                    "content_quality",
                    "confidence",
                    "language",
                    "x_post"
                ]
            }
        }
    },
    "required": ["processing_summary", "processed_articles"]
}
