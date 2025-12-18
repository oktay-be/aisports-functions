"""
Embedding Service for Article Processing

Generates vector embeddings for articles using Google's text-embedding-004 model.
These embeddings are used to compute similarity and group related articles.
"""

import logging
from typing import List, Optional

import numpy as np
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating text embeddings using Vertex AI.

    Uses text-embedding-004 model optimized for semantic similarity tasks.
    """

    BATCH_SIZE = 100  # API limit is ~250, using 100 for safety
    MODEL = "text-embedding-004"
    MAX_TEXT_LENGTH = 2000  # Characters to embed per article

    def __init__(self, client: genai.Client):
        """
        Initialize the embedding service.

        Args:
            client: Initialized genai.Client with Vertex AI credentials
        """
        self.client = client
        logger.info(f"EmbeddingService initialized with model: {self.MODEL}")

    def _prepare_text(self, article: dict) -> str:
        """
        Prepare article text for embedding.

        Concatenates title and body snippet for better semantic representation.

        Args:
            article: Article dictionary with 'title' and 'body' fields

        Returns:
            Combined text string for embedding
        """
        title = article.get('title', '') or ''
        body = article.get('body', '') or ''

        # Combine title (full) + body (truncated)
        combined = f"{title} {body[:self.MAX_TEXT_LENGTH - len(title) - 1]}"
        return combined.strip()

    def generate_embeddings(self, articles: List[dict]) -> np.ndarray:
        """
        Generate embeddings for a list of articles.

        Args:
            articles: List of article dictionaries

        Returns:
            numpy array of shape (n_articles, embedding_dim)

        Raises:
            Exception: If embedding generation fails
        """
        if not articles:
            logger.warning("No articles provided for embedding generation")
            return np.array([])

        # Prepare texts for embedding
        texts = [self._prepare_text(article) for article in articles]

        logger.info(f"Generating embeddings for {len(texts)} articles")

        embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            batch_num = i // self.BATCH_SIZE + 1
            total_batches = (len(texts) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

            logger.info(f"Processing embedding batch {batch_num}/{total_batches} ({len(batch)} articles)")

            try:
                response = self.client.models.embed_content(
                    model=self.MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type="SEMANTIC_SIMILARITY"
                    )
                )

                # Extract embedding values
                batch_embeddings = [e.values for e in response.embeddings]
                embeddings.extend(batch_embeddings)

                logger.debug(f"Batch {batch_num} completed: {len(batch_embeddings)} embeddings")

            except Exception as e:
                logger.error(f"Error generating embeddings for batch {batch_num}: {e}")
                raise

        result = np.array(embeddings)
        logger.info(f"Generated embeddings with shape: {result.shape}")

        return result

    def generate_single_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding for a single text string.

        Args:
            text: Text to embed

        Returns:
            1D numpy array of embedding values, or None on error
        """
        try:
            response = self.client.models.embed_content(
                model=self.MODEL,
                contents=[text],
                config=types.EmbedContentConfig(
                    task_type="SEMANTIC_SIMILARITY"
                )
            )

            return np.array(response.embeddings[0].values)

        except Exception as e:
            logger.error(f"Error generating single embedding: {e}")
            return None
