"""
Configuration management for web scraping.
"""

from typing import Dict, Any


class ScrapingConfig:
    """Configuration class for web scraping operations."""
    
    def __init__(self):
        """Initialize scraping configuration."""
        self.site_specific_selectors = {
            "hurriyet.com.tr": {
                "article_selector": "div.news-item, div.col-md-12.col-sm-12.col-xs-12",
                "title_selector": "h1.rhd-article-title, h1.page-title, .article-title h1",
                "link_selector": "a.news-item__link",
                "date_selector": "span.rhd-time-box-text, .article-date time, .news-item__date",
                "content_selector": "div.rhd-all-article-detail, div.article-content, .news-item__spot",
                "image_selector": "img.rhd-article-spot-img, .article-image img, img.news-item__image",
                "author_selector": "span.rhd-author-name, .article-author, span.news-item__author"
            },
            "fanatik.com.tr": {
                "title_selector": "h1.news-detail__title, h3.title",
                "content_selector": "div.news-detail__body, div.spot",
                "date_selector": "span.news-detail__date, span.date",
                "image_selector": "figure.news-detail__media img, img.lazy",
                "author_selector": ".news-detail__author-name, span.author"
            },
            "sabah.com.tr": {
                "title_selector": "h1.detayH1, h1.pageTitle, h3, h4",
                "content_selector": "div.detayText, div.newsBox, div.spot",
                "date_selector": "span.tarih, .date",
                "image_selector": "figure.newsPicture img, img",
                "author_selector": "a.author, .author"
            },
            "fotomac.com.tr": {
                "title_selector": "h1.news-title, h3.card-title",
                "content_selector": "div.news-text, p.card-text",
                "date_selector": "div.news-date, span.date",
                "image_selector": "div.news-image img, img.card-img-top",
                "author_selector": "div.news-author, span.author"
            },
            "sporx.com": {
                "title_selector": "h1.detail-title, h3.title",
                "content_selector": "div.detail-text, .summary",
                "date_selector": "span.detail-date, .date",
                "image_selector": "div.detail-image img, img",
                "author_selector": "span.author-name, .author-name"
            },
            "mackolik.com": {
                "title_selector": "h1.page-title, h3",
                "content_selector": "div.article-body, .news-summary",
                "date_selector": "div.article-info .date, .news-date",
                "image_selector": "div.article-image img, .news-image img",
                "author_selector": "div.article-info .author, .news-author"
            },
            "ntvspor.net": {
                "title_selector": "h1.news-title, h2, h3",
                "content_selector": "div.news-content, .card-text, .summary",
                "date_selector": "div.meta-data time, .date, time",
                "image_selector": "figure.news-image img, img.card-img-top, .news-image img",
                "author_selector": "div.meta-data .author, .author"
            }
        }
        
        self.generic_selectors = {
            "title_selector": "h1, h2, .article-title, .content-title, .news_title, [itemprop='headline']",
            "content_selector": "article, .article-body, .article-content, .content-text, .news_body, [itemprop='articleBody']",
            "date_selector": ".date, .time, .published, .pubdate, time, [itemprop='datePublished']",
            "image_selector": "img, .image, .thumbnail, [itemprop='image']",
            "author_selector": ".author, .writer, .reporter, [itemprop='author']"
        }
           # HTTP settings
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        self.request_timeout = 25
          # Content quality thresholds
        self.min_body_length = 50
        self.min_title_length = 10
        self.high_quality_body_length = 500
        self.high_quality_title_length = 15
          # Suspicious content patterns to detect low-quality content
        self.suspicious_patterns = [
            'javascript required',
            'enable javascript',
            'cookie policy',
            'privacy policy',
            'terms of service'
        ]
        
        # Additional settings for scraper
        self.http_timeout = 25
        self.max_retries = 3
        self.link_discovery_depth = 1
    
    def get_selectors_for_domain(self, domain: str) -> Dict[str, str]:
        """
        Get selectors for a specific domain.
        
        Args:
            domain: Domain name to get selectors for
            
        Returns:
            Dictionary of selectors for the domain
        """
        for site_domain, selectors in self.site_specific_selectors.items():
            if site_domain in domain.lower():
                return selectors
        return self.generic_selectors
    
    def get_request_headers(self) -> Dict[str, str]:
        """
        Get HTTP request headers.
        
        Returns:
            Dictionary of HTTP headers
        """
        return {
            "User-Agent": self.user_agent
        }