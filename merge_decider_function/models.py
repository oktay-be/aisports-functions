"""
Data models and schemas for the Merge Decider Function.
Following the pattern from result_merger_function/models.py
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
                    "decision": {"type": "string", "enum": ["MERGE", "KEEP_BOTH"]},
                    "reason": {"type": "string"},
                    "primary_article_id": {"type": "string", "nullable": True},
                    "primary_article_url": {"type": "string", "nullable": True},
                    # DEPRECATED: Use merged_from_urls instead
                    "merged_article_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "merged_from_urls": {
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
