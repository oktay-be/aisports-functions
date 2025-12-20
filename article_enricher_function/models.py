"""
Data models and schemas for the Article Enricher Function.
Following the pattern from result_merger_function/models.py
"""

# Vertex AI Response Schema - Used for structured output
# This schema ensures consistent JSON responses from the AI model
VERTEX_AI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "enriched_articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "x_post": {"type": "string"},
                    "summary_translation": {"type": "string", "nullable": True},
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tag": {"type": "string"},
                                "confidence": {"type": "number"}
                            },
                            "required": ["tag", "confidence"]
                        }
                    },
                    "key_entities": {
                        "type": "object",
                        "properties": {
                            "teams": {"type": "array", "items": {"type": "string"}},
                            "players": {"type": "array", "items": {"type": "string"}},
                            "amounts": {"type": "array", "items": {"type": "string"}},
                            "dates": {"type": "array", "items": {"type": "string"}},
                            "competitions": {"type": "array", "items": {"type": "string"}},
                            "locations": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    "confidence": {"type": "number"},
                    "content_quality": {"type": "string", "enum": ["high", "medium", "low"]},
                    "language": {"type": "string"},
                    "region": {"type": "string"}
                },
                "required": [
                    "article_id",
                    "summary",
                    "x_post",
                    "categories",
                    "confidence",
                    "content_quality",
                    "language",
                    "region"
                ]
            }
        }
    },
    "required": ["enriched_articles"]
}
