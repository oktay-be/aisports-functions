"""
AI Post Maker for AISports application.
Handles creation and management of social media posts from articles.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import uuid
import re

# Import database client
from database.mongodb_client import MongoDBClient
from capabilities.ai_summarizer import AISummarizer

logger = logging.getLogger(__name__)

class AIPostMaker:
    """
    AI-powered post generation and management for social media.
    Supports X/Twitter post creation from article objects.
    """
    
    def __init__(self, google_api_key: str):
        """
        Initialize AI Post Maker.
        
        Args:
            google_api_key: Google API key for AI operations
        """
        self.ai_summarizer = AISummarizer(google_api_key=google_api_key)
        self.db_client = None
        
        # X/Twitter configuration
        self.max_post_length = 280
        self.hashtag_limit = 5
        
    async def initialize(self):
        """Initialize database connection."""
        self.db_client = MongoDBClient()
        await self.db_client.connect()
    
    async def create_posts_from_articles(self, article_ids: List[str]) -> List[Dict]:
        """
        Create social media posts from multiple articles.
        
        Args:
            article_ids: List of article IDs to create posts from
            
        Returns:
            List of post objects with post_ids
        """
        if not self.db_client:
            await self.initialize()
        
        posts = []
        
        for article_id in article_ids:
            try:
                # Find the article in the database
                article = await self._find_article_by_id(article_id)
                if not article:
                    logger.warning(f"Article not found: {article_id}")
                    continue
                
                # Generate post for this article
                post = await self.create_single_post(article)
                if post:
                    # Save the prepared post
                    post_id = await self.save_prepared_post(post)
                    post['post_id'] = post_id
                    posts.append(post)
                    
            except Exception as e:
                logger.error(f"Error creating post for article {article_id}: {e}")
                continue
        
        logger.info(f"Created {len(posts)} posts from {len(article_ids)} articles")
        return posts
    
    async def create_single_post(self, article: Dict) -> Dict:
        """
        Create a single social media post from an article.
        
        Args:
            article: Article object in standard schema
            
        Returns:
            Post object ready for saving
        """
        try:
            # Generate post content using AI
            post_text = await self._generate_post_content(article)
            
            # Extract hashtags and mentions
            hashtags = self._extract_hashtags(post_text)
            mentions = self._extract_mentions(post_text)
            
            # Validate post length
            if len(post_text) > self.max_post_length:
                logger.warning(f"Post too long ({len(post_text)} chars), truncating")
                post_text = post_text[:self.max_post_length-3] + "..."
            
            # Create post object
            post = {
                "post_id": f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
                "based_on_articles": [article.get('id', '')],
                "post_content": {
                    "text": post_text,
                    "hashtags": hashtags,
                    "mentions": mentions,
                    "character_count": len(post_text)
                },
                "post_status": "prepared",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "published_at": None,
                "x_post_id": None,
                "engagement_stats": {
                    "likes": 0,
                    "retweets": 0,
                    "replies": 0
                },
                "source_article": {
                    "title": article.get('title', ''),
                    "source": article.get('source', ''),
                    "url": article.get('original_url', '')
                }
            }
            
            return post
            
        except Exception as e:
            logger.error(f"Error creating post from article: {e}")
            return None
    
    async def _generate_post_content(self, article: Dict) -> str:
        """
        Generate post content using AI.
        
        Args:
            article: Article object
            
        Returns:
            Generated post text
        """
        # Create prompt for post generation
        prompt = self._create_post_prompt(article)
        
        try:
            # Use AI summarizer to generate post content
            response = await self.ai_summarizer._call_google_gemini_api(
                prompt=prompt,
                temperature=0.7
            )
            
            # Extract post text from response
            post_text = self._extract_post_from_response(response)
            
            # Validate and clean post
            post_text = self._validate_post_content(post_text)
            
            return post_text
            
        except Exception as e:
            logger.error(f"Error generating post content: {e}")
            # Fallback to simple template
            return self._create_fallback_post(article)
    
    def _create_post_prompt(self, article: Dict) -> str:
        """
        Create AI prompt for post generation.
        
        Args:
            article: Article object
            
        Returns:
            AI prompt string
        """
        # Extract key information
        title = article.get('title', '')
        summary = article.get('summary', '')
        entities = article.get('key_entities', {})
        source = article.get('source', '')
        
        # Extract teams and players for hashtags
        teams = entities.get('teams', [])
        players = entities.get('players', [])
        
        prompt = f'''
Create an engaging X/Twitter post based on this sports article:

Title: {title}
Summary: {summary}
Source: {source}
Teams mentioned: {', '.join(teams) if teams else 'None'}
Players mentioned: {', '.join(players) if players else 'None'}

Requirements:
1. Maximum 280 characters
2. Include relevant emojis (🔥, ⚽, 🏀, 🚨, etc.)
3. Add 2-3 relevant hashtags
4. Make it engaging and newsworthy
5. Include key entities (teams/players) naturally
6. Use Turkish if source is Turkish, English otherwise
7. Return ONLY the post text, no explanations

Example formats:
- 🔥 TRANSFER ALERT: [Team] reportedly interested in [Player]! #TransferNews #Football
- ⚽ MATCH UPDATE: [Team] vs [Team] - [Score] at half-time! #Football #MatchDay
- 🚨 BREAKING: [Player] signs new contract with [Team]! #Football #ContractNews

Generate the post:
'''
        
        return prompt
    
    def _extract_post_from_response(self, response: str) -> str:
        """
        Extract clean post text from AI response.
        
        Args:
            response: Raw AI response
            
        Returns:
            Clean post text
        """
        # Remove any markdown formatting
        response = re.sub(r'```.*?```', '', response, flags=re.DOTALL)
        response = re.sub(r'`([^`]+)`', r'\1', response)
        
        # Remove common AI response prefixes
        prefixes_to_remove = [
            'Here\'s the post:',
            'Post:',
            'Tweet:',
            'X post:',
            'Generated post:',
            'Social media post:'
        ]
        
        for prefix in prefixes_to_remove:
            if response.strip().lower().startswith(prefix.lower()):
                response = response[len(prefix):].strip()
        
        # Clean up extra whitespace and newlines
        response = ' '.join(response.split())
        
        return response.strip()
    
    def _validate_post_content(self, content: str) -> str:
        """
        Validate and clean post content.
        
        Args:
            content: Raw post content
            
        Returns:
            Validated and cleaned content
        """
        # Remove extra whitespace
        content = ' '.join(content.split())
        
        # Ensure it's not empty
        if not content:
            return "🔥 Sports news update! Check out the latest developments."
        
        # Truncate if too long
        if len(content) > self.max_post_length:
            content = content[:self.max_post_length-3] + "..."
        
        return content
    
    def _create_fallback_post(self, article: Dict) -> str:
        """
        Create fallback post when AI generation fails.
        
        Args:
            article: Article object
            
        Returns:
            Simple fallback post
        """
        title = article.get('title', 'Sports news update')[:100]
        teams = article.get('key_entities', {}).get('teams', [])
        
        if teams:
            team_hashtags = ' '.join([f"#{team.replace(' ', '')}" for team in teams[:2]])
            return f"🔥 {title}... {team_hashtags} #SportsNews"
        else:
            return f"🔥 {title}... #SportsNews"
    
    def _extract_hashtags(self, text: str) -> List[str]:
        """Extract hashtags from post text."""
        hashtags = re.findall(r'#(\w+)', text)
        return ['#' + tag for tag in hashtags[:self.hashtag_limit]]
    
    def _extract_mentions(self, text: str) -> List[str]:
        """Extract mentions from post text."""
        mentions = re.findall(r'@(\w+)', text)
        return ['@' + mention for mention in mentions]
    
    async def _find_article_by_id(self, article_id: str) -> Optional[Dict]:
        """
        Find article by ID across all collections.
        
        Args:
            article_id: Article ID to search for
            
        Returns:
            Article object or None
        """
        # Search in aggregated results first
        collections = ['ai_aggregated_results', 'ai_summaries_per_source']
        
        for collection_name in collections:
            try:
                # Search for article in processed_articles array
                cursor = self.db_client.db[collection_name].find(
                    {"processed_articles.id": article_id}
                )
                
                async for doc in cursor:
                    for article in doc.get('processed_articles', []):
                        if article.get('id') == article_id:
                            return article
                            
            except Exception as e:
                logger.error(f"Error searching in {collection_name}: {e}")
        
        return None
    
    async def save_prepared_post(self, post_data: Dict) -> str:
        """
        Save prepared post to database.
        
        Args:
            post_data: Post object to save
            
        Returns:
            Post ID
        """
        if not self.db_client:
            await self.initialize()
        
        try:
            result = await self.db_client.db['ai_posts'].insert_one(post_data)
            post_id = post_data['post_id']
            logger.info(f"Saved prepared post: {post_id}")
            return post_id
            
        except Exception as e:
            logger.error(f"Error saving prepared post: {e}")
            raise
    
    async def get_prepared_posts(self, limit: int = 10, status: str = None) -> List[Dict]:
        """
        Get prepared posts from database.
        
        Args:
            limit: Maximum number of posts to return
            status: Filter by post status
            
        Returns:
            List of post objects
        """
        if not self.db_client:
            await self.initialize()
        
        try:
            query = {}
            if status:
                query['post_status'] = status
            
            cursor = self.db_client.db['ai_posts'].find(query).sort('created_at', -1).limit(limit)
            posts = []
            
            async for post in cursor:
                # Convert ObjectId to string for JSON serialization
                post['_id'] = str(post['_id'])
                posts.append(post)
            
            return posts
            
        except Exception as e:
            logger.error(f"Error getting prepared posts: {e}")
            return []
    
    async def update_post_status(self, post_id: str, status: str, x_post_id: str = None) -> bool:
        """
        Update post status in database.
        
        Args:
            post_id: Post ID to update
            status: New status
            x_post_id: X/Twitter post ID if published
            
        Returns:
            True if updated successfully
        """
        if not self.db_client:
            await self.initialize()
        
        try:
            update_data = {
                'post_status': status,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            if status == 'published':
                update_data['published_at'] = datetime.now(timezone.utc).isoformat()
                if x_post_id:
                    update_data['x_post_id'] = x_post_id
            
            result = await self.db_client.db['ai_posts'].update_one(
                {'post_id': post_id},
                {'$set': update_data}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating post status: {e}")
            return False
    
    async def get_posts_by_articles(self, article_ids: List[str]) -> List[Dict]:
        """
        Get posts based on specific articles.
        
        Args:
            article_ids: List of article IDs
            
        Returns:
            List of post objects
        """
        if not self.db_client:
            await self.initialize()
        
        try:
            cursor = self.db_client.db['ai_posts'].find(
                {'based_on_articles': {'$in': article_ids}}
            ).sort('created_at', -1)
            
            posts = []
            async for post in cursor:
                post['_id'] = str(post['_id'])
                posts.append(post)
            
            return posts
            
        except Exception as e:
            logger.error(f"Error getting posts by articles: {e}")
            return []
    
    # X/Twitter integration methods (placeholder for future implementation)
    async def publish_post(self, post_id: str) -> bool:
        """
        Publish post to X/Twitter.
        
        Args:
            post_id: Post ID to publish
            
        Returns:
            True if published successfully
        """
        # TODO: Implement X/Twitter API integration
        logger.warning("X/Twitter publishing not yet implemented")
        
        # For now, just update status to "published" for testing
        return await self.update_post_status(post_id, "published", f"mock_x_id_{post_id}")
    
    async def publish_multiple_posts(self, post_ids: List[str]) -> Dict:
        """
        Publish multiple posts to X/Twitter.
        
        Args:
            post_ids: List of post IDs to publish
            
        Returns:
            Publishing results summary
        """
        results = {
            'published': 0,
            'failed': 0,
            'results': []
        }
        
        for post_id in post_ids:
            try:
                success = await self.publish_post(post_id)
                if success:
                    results['published'] += 1
                    results['results'].append({'post_id': post_id, 'status': 'published'})
                else:
                    results['failed'] += 1
                    results['results'].append({'post_id': post_id, 'status': 'failed'})
                    
            except Exception as e:
                logger.error(f"Error publishing post {post_id}: {e}")
                results['failed'] += 1
                results['results'].append({'post_id': post_id, 'status': 'failed', 'error': str(e)})
        
        return results
