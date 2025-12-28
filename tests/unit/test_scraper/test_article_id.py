"""
Unit tests for scraper_function/article_id.py

Tests the article ID generation utility functions.
"""

import pytest
from scraper_function.article_id import generate_article_id, add_article_ids


class TestGenerateArticleId:
    """Tests for generate_article_id function."""

    def test_generates_16_character_hex_string(self):
        """Article ID should be exactly 16 hex characters."""
        article_id = generate_article_id("https://example.com/article")
        assert len(article_id) == 16
        assert all(c in '0123456789abcdef' for c in article_id)

    def test_deterministic_same_url(self):
        """Same URL should always generate the same ID."""
        url = "https://example.com/sports/article-123"
        id1 = generate_article_id(url)
        id2 = generate_article_id(url)
        assert id1 == id2

    def test_different_urls_different_ids(self):
        """Different URLs should generate different IDs."""
        id1 = generate_article_id("https://example.com/article-1")
        id2 = generate_article_id("https://example.com/article-2")
        assert id1 != id2

    def test_normalizes_whitespace(self):
        """URLs with leading/trailing whitespace should be normalized."""
        id1 = generate_article_id("https://example.com/article")
        id2 = generate_article_id("  https://example.com/article  ")
        assert id1 == id2

    def test_normalizes_case(self):
        """URLs with different case should be normalized."""
        id1 = generate_article_id("https://example.com/article")
        id2 = generate_article_id("HTTPS://EXAMPLE.COM/ARTICLE")
        assert id1 == id2

    def test_empty_url_raises_error(self):
        """Empty URL should raise ValueError."""
        with pytest.raises(ValueError, match="URL is required"):
            generate_article_id("")

    def test_none_url_raises_error(self):
        """None URL should raise ValueError (not empty check)."""
        with pytest.raises(ValueError, match="URL is required"):
            generate_article_id(None)

    def test_special_characters_in_url(self):
        """URLs with special characters should work."""
        article_id = generate_article_id("https://example.com/article?q=test&lang=tr")
        assert len(article_id) == 16

    def test_unicode_url(self):
        """URLs with unicode characters should work."""
        article_id = generate_article_id("https://example.com/türkçe-makale")
        assert len(article_id) == 16


class TestAddArticleIds:
    """Tests for add_article_ids function."""

    def test_adds_id_with_url_field(self):
        """Should add article_id when article has 'url' field."""
        articles = [{"url": "https://example.com/article-1", "title": "Test"}]
        result = add_article_ids(articles)
        
        assert len(result) == 1
        assert "article_id" in result[0]
        assert len(result[0]["article_id"]) == 16

    def test_adds_id_with_link_field(self):
        """Should add article_id when article has 'link' field."""
        articles = [{"link": "https://example.com/article-1", "title": "Test"}]
        result = add_article_ids(articles)
        
        assert "article_id" in result[0]

    def test_adds_id_with_original_url_field(self):
        """Should add article_id when article has 'original_url' field."""
        articles = [{"original_url": "https://example.com/article-1", "title": "Test"}]
        result = add_article_ids(articles)
        
        assert "article_id" in result[0]

    def test_adds_source_type(self):
        """Should add source_type to each article."""
        articles = [{"url": "https://example.com/article-1"}]
        result = add_article_ids(articles, source_type="api")
        
        assert result[0]["source_type"] == "api"

    def test_default_source_type_is_scraped(self):
        """Default source_type should be 'scraped'."""
        articles = [{"url": "https://example.com/article-1"}]
        result = add_article_ids(articles)
        
        assert result[0]["source_type"] == "scraped"

    def test_modifies_list_in_place(self):
        """Should modify the original list (returns same reference)."""
        articles = [{"url": "https://example.com/article-1"}]
        result = add_article_ids(articles)
        
        assert result is articles

    def test_handles_multiple_articles(self):
        """Should handle multiple articles."""
        articles = [
            {"url": "https://example.com/article-1"},
            {"url": "https://example.com/article-2"},
            {"url": "https://example.com/article-3"},
        ]
        result = add_article_ids(articles)
        
        assert len(result) == 3
        assert all("article_id" in a for a in result)
        # IDs should be unique
        ids = [a["article_id"] for a in result]
        assert len(set(ids)) == 3

    def test_handles_empty_list(self):
        """Should handle empty list."""
        articles = []
        result = add_article_ids(articles)
        
        assert result == []

    def test_skips_articles_without_url(self):
        """Should skip articles without any URL field."""
        articles = [{"title": "No URL article"}]
        result = add_article_ids(articles)
        
        assert "article_id" not in result[0]
        assert result[0]["source_type"] == "scraped"
