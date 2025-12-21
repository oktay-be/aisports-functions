"""
Utility functions for generating unique article identifiers.
Article IDs are deterministic hashes based on the article URL, ensuring 
consistency across pipeline stages and reruns.
"""

import hashlib
from typing import Optional


def generate_article_id(url: str, published_date: Optional[str] = None) -> str:
    """
    Generate a deterministic unique ID for an article based on its URL.
    
    The ID is a 16-character hexadecimal hash that remains consistent
    across multiple pipeline runs for the same article.
    
    Args:
        url: The article's URL (primary identifier)
        published_date: Optional published date for additional uniqueness
                       (not currently used to maintain URL-based consistency)
    
    Returns:
        A 16-character hexadecimal string (e.g., "a1b2c3d4e5f6g7h8")
    
    Examples:
        >>> generate_article_id("https://example.com/article-123")
        'e5f6a1b2c3d47890'
        
        >>> # Same URL always produces same ID
        >>> id1 = generate_article_id("https://example.com/article")
        >>> id2 = generate_article_id("https://example.com/article")
        >>> id1 == id2
        True
    """
    if not url:
        raise ValueError("URL is required to generate article ID")
    
    # Normalize URL: strip whitespace and convert to lowercase
    normalized_url = url.strip().lower()
    
    # Generate SHA-256 hash and take first 16 characters for brevity
    # 16 hex chars = 64 bits = ~18 quintillion possible values (collision-resistant)
    hash_bytes = hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()
    
    return hash_bytes[:16]


def add_article_ids(articles: list[dict], source_type: str = 'scraped') -> list[dict]:
    """
    Add article_id and source_type to a list of articles in-place.
    
    Args:
        articles: List of article dictionaries with 'url', 'link', or 'original_url' field
        source_type: The source type for these articles ('api' or 'scraped', default: 'scraped')
    
    Returns:
        The same list with 'article_id' and 'source_type' fields added to each article
    """
    for article in articles:
        # Check various common URL field names
        url = article.get("url") or article.get("link") or article.get("original_url")
        if url:
            article["article_id"] = generate_article_id(url)
        # Add source_type to each article
        article["source_type"] = source_type
    
    return articles
