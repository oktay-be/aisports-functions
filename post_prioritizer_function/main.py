import os
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple
from google.cloud import storage
import re

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

logger = logging.getLogger(__name__)
logger.info("Post Prioritizer Function initialized")

# Initialize Google Cloud clients (only in cloud environment)
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

if ENVIRONMENT != 'local':
    storage_client = storage.Client()
else:
    storage_client = None
    logger.info("Running in local environment - skipping Google Cloud client initialization")

# Configuration from environment variables
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
NEWS_DATA_ROOT_PREFIX = os.getenv('NEWS_DATA_ROOT_PREFIX', 'news_data/')
BATCH_PROCESSING_FOLDER = os.getenv('BATCH_PROCESSING_FOLDER', 'batch_processing/')
DEDUP_RESULTS_FOLDER = os.getenv('DEDUP_RESULTS_FOLDER', 'dedup_results/')
PRIORITIZED_POSTS_FOLDER = os.getenv('PRIORITIZED_POSTS_FOLDER', 'prioritized_posts/')
NUM_TOP_POSTS = int(os.getenv('NUM_TOP_POSTS', '10'))


class PostPrioritizer:
    """
    Handles prioritization of posts from deduplicated predictions.
    
    Prioritization Rules:
    1. Football articles have higher priority than basketball
    2. Derby matches have great priority
    3. Transfer news has the biggest priority
    4. Fights and scandals have high priority
    """
    
    # Priority weights for different categories
    CATEGORY_PRIORITIES = {
        # Transfers (highest priority)
        'transfers_confirmed': 100,
        'transfers_negotiations': 95,
        'transfers_rumors': 90,
        'transfers_interest': 85,
        
        # Scandals and controversies (high priority)
        'off_field_scandals': 80,
        'field_incidents': 75,
        'corruption_allegations': 75,
        'disciplinary_actions': 70,
        
        # Derbys and rivalries (great priority)
        'team_rivalry': 85,
        'personal_rivalry': 70,
        'fan_rivalry': 65,
        
        # Contract issues (related to transfers)
        'contract_disputes': 75,
        'contract_renewals': 70,
        'departures': 80,
        
        # Other categories (lower priority)
        'match_results': 50,
        'performance_analysis': 45,
        'tactical_analysis': 40,
        'injury_news': 55,
        'squad_changes': 50,
        'financial_news': 45,
        'elections_management': 60,
        'federation_politics': 50,
        'league_standings': 45,
        'european_competitions': 55,
        'domestic_cups': 50,
        'personal_life': 20,
        'social_media': 15,
        'lifestyle_news': 10,
    }
    
    # Sport priority multipliers
    SPORT_PRIORITY = {
        'football': 1.5,
        'basketball': 1.0,
        'other': 0.8,
    }
    
    def __init__(self):
        """Initialize the post prioritizer."""
        self.storage_client = storage_client
    
    def download_prediction_file(self, gcs_uri: str) -> List[dict]:
        """
        Download and parse prediction JSONL file from GCS.
        
        Args:
            gcs_uri: GCS URI of the prediction file (gs://bucket/path/file.jsonl)
            
        Returns:
            List of parsed prediction objects
        """
        try:
            # Parse GCS URI
            if not gcs_uri.startswith('gs://'):
                raise ValueError(f"Invalid GCS URI: {gcs_uri}")
            
            parts = gcs_uri.replace('gs://', '').split('/', 1)
            bucket_name = parts[0]
            blob_name = parts[1] if len(parts) > 1 else ''
            
            logger.info(f"Downloading prediction file from: {gcs_uri}")
            
            # Download file
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            content = blob.download_as_text()
            
            # Parse JSONL
            predictions = []
            for line in content.strip().split('\n'):
                if line.strip():
                    predictions.append(json.loads(line))
            
            logger.info(f"Downloaded and parsed {len(predictions)} prediction entries")
            return predictions
            
        except Exception as e:
            logger.error(f"Error downloading prediction file: {e}")
            raise
    
    def extract_articles_from_predictions(self, predictions: List[dict]) -> List[dict]:
        """
        Extract processed articles from prediction results.
        
        Args:
            predictions: List of prediction objects
            
        Returns:
            List of article dictionaries
        """
        articles = []
        
        for prediction in predictions:
            try:
                # Extract response content
                response = prediction.get('response', {})
                candidates = response.get('candidates', [])
                
                if not candidates:
                    logger.warning("No candidates found in prediction")
                    continue
                
                # Get the first candidate's content
                candidate = candidates[0]
                content = candidate.get('content', {})
                parts = content.get('parts', [])
                
                if not parts:
                    logger.warning("No parts found in candidate content")
                    continue
                
                # Parse JSON response
                text = parts[0].get('text', '')
                data = json.loads(text)
                
                # Extract processed articles
                processed_articles = data.get('processed_articles', [])
                articles.extend(processed_articles)
                
            except Exception as e:
                logger.error(f"Error extracting articles from prediction: {e}")
                continue
        
        logger.info(f"Extracted {len(articles)} articles from predictions")
        return articles
    
    def detect_sport(self, article: dict) -> str:
        """
        Detect the sport type from article categories and content.
        
        Args:
            article: Article dictionary
            
        Returns:
            Sport type: 'football', 'basketball', or 'other'
        """
        categories = article.get('categories', [])
        
        # Check for basketball-specific categories
        basketball_tags = ['basketball_news', 'basketball_transfers', 'basketball_league_champions',
                          'basketball_match_results', 'basketball_performance_analysis']
        
        for category in categories:
            tag = category.get('tag', '')
            if tag in basketball_tags:
                return 'basketball'
        
        # Check title and summary for basketball keywords
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        text = f"{title} {summary}"
        
        basketball_keywords = ['basketball', 'basket', 'basketbol', 'euroleague', 'nba']
        if any(keyword in text for keyword in basketball_keywords):
            return 'basketball'
        
        # Default to football
        return 'football'
    
    def is_derby(self, article: dict) -> bool:
        """
        Detect if the article is about a derby match.
        
        Args:
            article: Article dictionary
            
        Returns:
            True if derby-related, False otherwise
        """
        # Check for team_rivalry category
        categories = article.get('categories', [])
        for category in categories:
            if category.get('tag') == 'team_rivalry':
                return True
        
        # Check for derby keywords in title and summary
        title = article.get('title', '').lower()
        summary = article.get('summary', '').lower()
        text = f"{title} {summary}"
        
        derby_keywords = ['derby', 'derbi', 'rivalry', 'rekabet', 'klasico', 'el clasico']
        return any(keyword in text for keyword in derby_keywords)
    
    def calculate_priority_score(self, article: dict) -> float:
        """
        Calculate priority score for an article based on categories and sport.
        
        Args:
            article: Article dictionary
            
        Returns:
            Priority score (higher = more important)
        """
        categories = article.get('categories', [])
        
        if not categories:
            return 0.0
        
        # Calculate weighted category score
        category_scores = []
        for category in categories:
            tag = category.get('tag', '')
            confidence = category.get('confidence', 0.0)
            base_priority = self.CATEGORY_PRIORITIES.get(tag, 30)  # Default priority: 30
            
            # Weight by confidence
            weighted_score = base_priority * confidence
            category_scores.append(weighted_score)
        
        # Use the maximum category score
        max_category_score = max(category_scores) if category_scores else 0
        
        # Apply sport multiplier
        sport = self.detect_sport(article)
        sport_multiplier = self.SPORT_PRIORITY.get(sport, 1.0)
        
        # Apply derby bonus
        derby_bonus = 20 if self.is_derby(article) else 0
        
        # Calculate final score
        final_score = (max_category_score * sport_multiplier) + derby_bonus
        
        return final_score
    
    def prioritize_articles(self, articles: List[dict], top_n: int = 10) -> List[dict]:
        """
        Prioritize articles and return top N.
        
        Args:
            articles: List of article dictionaries
            top_n: Number of top articles to return
            
        Returns:
            List of top N prioritized articles with scores
        """
        # Calculate scores for all articles
        scored_articles = []
        for article in articles:
            score = self.calculate_priority_score(article)
            article_with_score = article.copy()
            article_with_score['priority_score'] = score
            article_with_score['sport'] = self.detect_sport(article)
            article_with_score['is_derby'] = self.is_derby(article)
            scored_articles.append(article_with_score)
        
        # Sort by score (descending)
        scored_articles.sort(key=lambda x: x['priority_score'], reverse=True)
        
        # Return top N
        top_articles = scored_articles[:top_n]
        
        logger.info(f"Prioritized {len(articles)} articles, returning top {len(top_articles)}")
        for i, article in enumerate(top_articles[:5], 1):
            logger.info(f"  #{i}: {article.get('title', 'Unknown')[:60]}... "
                       f"(score: {article['priority_score']:.2f}, sport: {article['sport']})")
        
        return top_articles
    
    def save_prioritized_posts(self, articles: List[dict], source_gcs_path: str) -> str:
        """
        Save prioritized posts to GCS.
        
        Args:
            articles: List of prioritized articles
            source_gcs_path: Original GCS path that triggered this function
            
        Returns:
            GCS URI of saved file
        """
        try:
            # Extract dedup ID from source path
            # Example: gs://bucket/news_data/batch_processing/2025-11/dedup_results/dedup_20251107_115120/...
            match = re.search(r'/dedup_results/([^/]+)/', source_gcs_path)
            if match:
                dedup_id = match.group(1)
            else:
                dedup_id = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            
            # Extract date path
            match = re.search(r'/batch_processing/([^/]+)/', source_gcs_path)
            if match:
                date_path = match.group(1)
            else:
                date_path = datetime.now(timezone.utc).strftime('%Y-%m')
            
            # Construct output path
            output_blob_name = (
                f"{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{date_path}/"
                f"{PRIORITIZED_POSTS_FOLDER}{dedup_id}_prioritized_posts.json"
            )
            
            # Prepare output data
            output_data = {
                'metadata': {
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'source_file': source_gcs_path,
                    'dedup_id': dedup_id,
                    'num_posts': len(articles),
                    'prioritization_rules': {
                        'football_vs_basketball': 'Football has 1.5x multiplier',
                        'derbys': '+20 bonus points',
                        'transfers': '100 (highest) to 85 points',
                        'scandals': '70-80 points',
                    }
                },
                'prioritized_posts': articles
            }
            
            # Upload to GCS
            bucket = self.storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(output_blob_name)
            blob.upload_from_string(
                json.dumps(output_data, indent=2, ensure_ascii=False),
                content_type='application/json'
            )
            
            output_uri = f"gs://{GCS_BUCKET_NAME}/{output_blob_name}"
            logger.info(f"Saved prioritized posts to: {output_uri}")
            
            return output_uri
            
        except Exception as e:
            logger.error(f"Error saving prioritized posts: {e}")
            raise
    
    def process_predictions(self, gcs_uri: str, top_n: int = None) -> str:
        """
        Main processing function: download, extract, prioritize, and save.
        
        Args:
            gcs_uri: GCS URI of predictions.jsonl file
            top_n: Number of top posts to select (default: from env var)
            
        Returns:
            GCS URI of saved prioritized posts
        """
        if top_n is None:
            top_n = NUM_TOP_POSTS
        
        logger.info(f"Processing predictions from: {gcs_uri}")
        logger.info(f"Will select top {top_n} posts")
        
        # Download and parse predictions
        predictions = self.download_prediction_file(gcs_uri)
        
        # Extract articles
        articles = self.extract_articles_from_predictions(predictions)
        
        if not articles:
            logger.warning("No articles found in predictions")
            return None
        
        # Prioritize articles
        prioritized = self.prioritize_articles(articles, top_n)
        
        # Save results
        output_uri = self.save_prioritized_posts(prioritized, gcs_uri)
        
        logger.info(f"Post prioritization complete. Output: {output_uri}")
        return output_uri


def post_prioritizer_function(event, context):
    """
    Cloud Function entry point triggered by GCS object creation.
    
    Args:
        event: GCS event data
        context: Cloud Function context
    """
    try:
        # Extract file information from event
        bucket_name = event['bucket']
        file_name = event['name']
        gcs_uri = f"gs://{bucket_name}/{file_name}"
        
        logger.info(f"=== Post Prioritizer Function Triggered ===")
        logger.info(f"Bucket: {bucket_name}")
        logger.info(f"File: {file_name}")
        logger.info(f"Event ID: {context.event_id}")
        logger.info(f"Event Type: {context.event_type}")
        
        # Filter: Only process predictions.jsonl files from dedup_results
        if not file_name.endswith('predictions.jsonl'):
            logger.info(f"Skipping non-predictions file: {file_name}")
            return
        
        if f'{DEDUP_RESULTS_FOLDER}' not in file_name:
            logger.info(f"Skipping file not in {DEDUP_RESULTS_FOLDER}: {file_name}")
            return
        
        # Initialize prioritizer
        prioritizer = PostPrioritizer()
        
        # Process predictions
        output_uri = prioritizer.process_predictions(gcs_uri)
        
        if output_uri:
            logger.info(f"✅ Successfully created prioritized posts: {output_uri}")
        else:
            logger.warning("⚠️  No prioritized posts created (no articles found)")
        
        return {'status': 'success', 'output': output_uri}
        
    except Exception as e:
        logger.error(f"❌ Error in post prioritizer function: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # For local testing
    if ENVIRONMENT == 'local':
        # Example test URI
        test_uri = "gs://aisports-scraping/news_data/batch_processing/2025-11/dedup_results/dedup_20251107_115120/prediction-model-2025-11-07T11:51:21.908961Z/predictions.jsonl"
        
        logger.info("Running in local test mode")
        prioritizer = PostPrioritizer()
        
        # Mock storage client for local testing
        prioritizer.storage_client = storage.Client()
        
        output = prioritizer.process_predictions(test_uri, top_n=10)
        logger.info(f"Test complete. Output: {output}")
