"""
Data models and schemas for the AISports event-driven microservices architecture.
Contains response schemas for Vertex AI processing and other data structures.
"""

# JSON schema for Vertex AI Gemini response (using Google Cloud format)
VERTEX_AI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "processing_summary": {
            "type": "OBJECT",
            "properties": {
                "total_input_articles": {"type": "INTEGER"},
                "articles_after_deduplication": {"type": "INTEGER"},
                "articles_after_cleaning": {"type": "INTEGER"},
                "duplicates_removed": {"type": "INTEGER"},
                "empty_articles_removed": {"type": "INTEGER"},
                "processing_date": {"type": "STRING"},
                "custom_categories_added": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"}
                }
            },
            "required": ["total_input_articles", "processing_date"]
        },
        "processed_articles": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "article_id": {"type": "STRING"},
                    "original_url": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "key_entities": {
                        "type": "OBJECT",
                        "properties": {
                            "teams": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "players": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "amounts": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "dates": {"type": "ARRAY", "items": {"type": "STRING"}}
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
                            }
                        }
                    },
                    "source": {"type": "STRING"},
                    "published_date": {"type": "STRING", "nullable": True},
                    "keywords_matched": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "content_quality": {"type": "STRING"},
                    "language": {"type": "STRING"},
                    "summary_translation": {"type": "STRING"},
                    "x_post": {"type": "STRING"}
                },
                "required": ["article_id", "title", "summary", "categories", "source", "x_post"]
            }
        }
    },
    "required": ["processing_summary", "processed_articles"]
}
