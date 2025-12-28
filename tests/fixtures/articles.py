"""
Article fixture factories for testing.

Provides functions to create article data with various configurations
for different test scenarios.
"""

import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


def create_article(
    title: str = "Test Article Title",
    body: str = "This is a test article body with some content.",
    url: str = None,
    article_id: str = None,
    source: str = "example.com",
    language: str = "en",
    region: str = "eu",
    publish_date: str = None,
    extraction_method: str = "api:newsapi",
    source_type: str = "api",
    **kwargs
) -> Dict[str, Any]:
    """
    Create a single article with customizable fields.

    Args:
        title: Article title
        body: Article body content
        url: Article URL (auto-generated if not provided)
        article_id: Unique ID (auto-generated from URL if not provided)
        source: News source domain
        language: Article language code
        region: Geographic region (eu, tr)
        publish_date: ISO format publish date
        extraction_method: How article was obtained
        source_type: api or scraped
        **kwargs: Additional fields to include

    Returns:
        Article dictionary
    """
    if url is None:
        url = f"https://{source}/article/{hashlib.md5(title.encode()).hexdigest()[:8]}"

    if article_id is None:
        article_id = hashlib.md5(url.encode()).hexdigest()[:16]

    if publish_date is None:
        publish_date = datetime.now(timezone.utc).isoformat()

    article = {
        "article_id": article_id,
        "url": url,
        "original_url": url,
        "title": title,
        "body": body,
        "source": source,
        "publish_date": publish_date,
        "language": language,
        "region": region,
        "extraction_method": extraction_method,
        "source_type": source_type,
    }
    article.update(kwargs)
    return article


def create_articles_batch(
    count: int = 5,
    region: str = "eu",
    language: str = "en",
    source: str = "example.com"
) -> List[Dict[str, Any]]:
    """
    Create a batch of unique articles.

    Args:
        count: Number of articles to create
        region: Region for all articles
        language: Language for all articles
        source: Source for all articles

    Returns:
        List of article dictionaries
    """
    return [
        create_article(
            title=f"Test Article {i}: {region.upper()} News",
            body=f"This is the body content for article {i}. " * 10,
            region=region,
            language=language,
            source=source
        )
        for i in range(count)
    ]


def create_similar_articles(
    base_title: str = "Breaking News Story",
    num_variants: int = 3,
    region: str = "eu"
) -> List[Dict[str, Any]]:
    """
    Create similar articles for grouping tests.

    Creates articles with similar content that should be grouped together.

    Args:
        base_title: Base title to create variants from
        num_variants: Number of similar articles
        region: Region for all articles

    Returns:
        List of similar article dictionaries
    """
    variants = [
        f"{base_title}",
        f"{base_title}: Latest Update",
        f"Update: {base_title}",
        f"{base_title} - Full Report",
        f"Breaking: {base_title}",
    ]

    base_body = f"Detailed coverage of {base_title.lower()}. This story has been developing over the past few hours. "

    return [
        create_article(
            title=variants[i % len(variants)],
            body=base_body * (10 + i),
            source=f"source{i}.com",
            region=region
        )
        for i in range(num_variants)
    ]


def create_duplicate_articles() -> List[Dict[str, Any]]:
    """
    Create articles with exact duplicates for pre-filter testing.

    Returns:
        List with duplicate URL and duplicate title articles
    """
    return [
        # Original article
        create_article(
            title="Original Article Title",
            body="Original body content. " * 10,
            url="https://example.com/original"
        ),
        # Duplicate URL (should be filtered)
        create_article(
            title="Different Title",
            body="Different body. " * 10,
            url="https://example.com/original"  # Same URL
        ),
        # Duplicate title (should be filtered, keep longer body)
        create_article(
            title="Original Article Title",  # Same title
            body="Short body.",
            url="https://other.com/similar"
        ),
        # Unique article
        create_article(
            title="Completely Different Story",
            body="Unique content here. " * 10,
            url="https://another.com/unique"
        ),
    ]


def create_tr_region_articles(count: int = 3) -> List[Dict[str, Any]]:
    """Create Turkish region articles."""
    return create_articles_batch(count, region="tr", language="tr")


def create_eu_region_articles(count: int = 3) -> List[Dict[str, Any]]:
    """Create European region articles."""
    return create_articles_batch(count, region="eu", language="en")


def create_empty_body_article() -> Dict[str, Any]:
    """Create an article with empty body (edge case)."""
    return create_article(
        title="Article With Empty Body",
        body=""
    )


def create_long_article() -> Dict[str, Any]:
    """Create an article with very long body."""
    return create_article(
        title="Very Long Article",
        body="This is a very long article. " * 500
    )


def create_article_with_missing_fields() -> Dict[str, Any]:
    """Create an article with minimal required fields."""
    return {
        "url": "https://example.com/minimal",
        "title": "Minimal Article"
    }


def create_grouped_articles_payload(groups: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Create a grouped_articles.json payload structure.

    Args:
        groups: List of article groups (each group is a list of articles)

    Returns:
        Grouped articles structure matching pipeline format
    """
    return {
        "groups": [
            {
                "group_id": i + 1,
                "max_similarity": 0.85 + (i * 0.02),
                "articles": group
            }
            for i, group in enumerate(groups)
        ],
        "group_count": len(groups),
        "total_articles": sum(len(g) for g in groups),
        "source_type": "complete",
        "created_at": datetime.now(timezone.utc).isoformat()
    }


def create_singleton_articles_payload(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create a singleton_articles.json payload structure.

    Args:
        articles: List of singleton articles

    Returns:
        Singleton articles structure matching pipeline format
    """
    return {
        "articles": articles,
        "count": len(articles),
        "source_type": "complete",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
