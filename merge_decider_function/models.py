"""
Data models and schemas for the Merge Decider Function.
Following the pattern from result_merger_function/models.py

Decision types:
- MERGE: All articles merged into one (primary)
- PARTIAL_MERGE: Most articles merged, 1-2 unique ones kept separate
- KEEP_ALL: All articles kept separate (replaces KEEP_BOTH)
"""

# Vertex AI Response Schema - Used for structured output
# This schema ensures consistent JSON responses from the AI model
VERTEX_AI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer"},
                    "decision": {"type": "string", "enum": ["MERGE", "PARTIAL_MERGE", "KEEP_ALL"]},
                    "reason": {"type": "string"},
                    "primary_article_id": {"type": "string", "nullable": True},
                    "primary_article_url": {"type": "string", "nullable": True},
                    "merged_article_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "merged_from_urls": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "kept_separate_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "kept_separate_urls": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["group_id", "decision", "reason"]
            }
        }
    },
    "required": ["decisions"]
}
