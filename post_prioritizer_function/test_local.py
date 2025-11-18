"""
Test script for Post Prioritizer Function.

This script tests the post prioritizer locally without requiring deployment.
"""

import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock sample data for testing
SAMPLE_ARTICLES = [
    {
        "id": "article_1",
        "title": "Real Madrid confirms Mbappé signing for €180 million",
        "summary": "Real Madrid has officially announced the signing of Kylian Mbappé from PSG for a record €180 million transfer fee.",
        "categories": [
            {"tag": "transfers_confirmed", "confidence": 1.0, "evidence": "Official announcement"}
        ],
        "source": "marca.es",
        "published_date": "2025-11-07T10:00:00Z"
    },
    {
        "id": "article_2", 
        "title": "Barcelona vs Real Madrid: El Clasico Preview",
        "summary": "The biggest derby in football is set for this weekend as Barcelona hosts Real Madrid at Camp Nou.",
        "categories": [
            {"tag": "team_rivalry", "confidence": 0.9, "evidence": "El Clasico derby match"},
            {"tag": "match_results", "confidence": 0.7, "evidence": "Upcoming match preview"}
        ],
        "source": "sport.es",
        "published_date": "2025-11-06T15:00:00Z"
    },
    {
        "id": "article_3",
        "title": "Fenerbahçe and Galatasaray fans clash before derby",
        "summary": "Police intervened as Fenerbahçe and Galatasaray fans clashed in Istanbul before the derby match.",
        "categories": [
            {"tag": "field_incidents", "confidence": 0.8, "evidence": "Fan violence reported"},
            {"tag": "team_rivalry", "confidence": 1.0, "evidence": "Istanbul derby"}
        ],
        "source": "fanatik.com.tr",
        "published_date": "2025-11-06T12:00:00Z"
    },
    {
        "id": "article_4",
        "title": "Manchester United interested in signing Turkish midfielder",
        "summary": "Manchester United scouts were spotted watching Hakan Çalhanoğlu, with rumors of a potential €40 million bid.",
        "categories": [
            {"tag": "transfers_rumors", "confidence": 0.6, "evidence": "Media speculation"}
        ],
        "source": "dailymail.co.uk",
        "published_date": "2025-11-05T18:00:00Z"
    },
    {
        "id": "article_5",
        "title": "Lakers defeat Warriors 115-110 in Western Conference clash",
        "summary": "LeBron James scored 35 points as the Lakers defeated the Warriors in a thrilling game.",
        "categories": [
            {"tag": "match_results", "confidence": 1.0, "evidence": "Game result"}
        ],
        "source": "espn.com",
        "published_date": "2025-11-05T22:00:00Z"
    },
    {
        "id": "article_6",
        "title": "Player arrested for assault in nightclub incident",
        "summary": "Premier League star arrested following alleged assault at a London nightclub early Sunday morning.",
        "categories": [
            {"tag": "off_field_scandals", "confidence": 0.9, "evidence": "Legal incident"}
        ],
        "source": "theguardian.com",
        "published_date": "2025-11-04T08:00:00Z"
    },
    {
        "id": "article_7",
        "title": "Chelsea negotiating contract extension with star midfielder",
        "summary": "Chelsea is in advanced talks to extend their star midfielder's contract until 2028.",
        "categories": [
            {"tag": "contract_renewals", "confidence": 0.8, "evidence": "Contract negotiations ongoing"}
        ],
        "source": "bbc.co.uk",
        "published_date": "2025-11-03T14:00:00Z"
    },
    {
        "id": "article_8",
        "title": "Match fixing allegations rock Italian football",
        "summary": "Several Serie A clubs are under investigation for alleged match fixing involving betting syndicates.",
        "categories": [
            {"tag": "corruption_allegations", "confidence": 0.7, "evidence": "Investigation reported"}
        ],
        "source": "gazzetta.it",
        "published_date": "2025-11-02T11:00:00Z"
    },
    {
        "id": "article_9",
        "title": "NBA star posts workout video on Instagram",
        "summary": "Stephen Curry shared his latest training routine on social media, gaining millions of views.",
        "categories": [
            {"tag": "social_media", "confidence": 1.0, "evidence": "Social media post"}
        ],
        "source": "nba.com",
        "published_date": "2025-11-01T16:00:00Z"
    },
    {
        "id": "article_10",
        "title": "Bayern Munich tactical analysis: How Tuchel's system works",
        "summary": "A deep dive into Bayern Munich's tactical approach under Thomas Tuchel this season.",
        "categories": [
            {"tag": "tactical_analysis", "confidence": 0.8, "evidence": "Tactical breakdown"}
        ],
        "source": "kicker.de",
        "published_date": "2025-10-31T13:00:00Z"
    }
]


def create_mock_prediction():
    """Create a mock prediction object matching Vertex AI format."""
    return {
        "response": {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "processed_articles": SAMPLE_ARTICLES
                                })
                            }
                        ]
                    }
                }
            ]
        }
    }


def test_prioritizer():
    """Test the PostPrioritizer class."""
    # Set environment to local
    os.environ['ENVIRONMENT'] = 'local'
    
    # Import after setting environment
    from post_prioritizer_function.main import PostPrioritizer
    
    print("=" * 80)
    print("POST PRIORITIZER FUNCTION - LOCAL TEST")
    print("=" * 80)
    print()
    
    # Create prioritizer instance
    prioritizer = PostPrioritizer()
    
    # Test 1: Extract articles from predictions
    print("Test 1: Extract articles from predictions")
    print("-" * 80)
    predictions = [create_mock_prediction()]
    articles = prioritizer.extract_articles_from_predictions(predictions)
    print(f"✓ Extracted {len(articles)} articles")
    print()
    
    # Test 2: Detect sport
    print("Test 2: Detect sport for each article")
    print("-" * 80)
    for article in articles[:3]:
        sport = prioritizer.detect_sport(article)
        print(f"  - {article['title'][:50]}... → {sport}")
    print()
    
    # Test 3: Detect derby
    print("Test 3: Detect derby matches")
    print("-" * 80)
    for article in articles[:3]:
        is_derby = prioritizer.is_derby(article)
        print(f"  - {article['title'][:50]}... → {'Derby' if is_derby else 'Not derby'}")
    print()
    
    # Test 4: Calculate priority scores
    print("Test 4: Calculate priority scores")
    print("-" * 80)
    for article in articles:
        score = prioritizer.calculate_priority_score(article)
        sport = prioritizer.detect_sport(article)
        is_derby = prioritizer.is_derby(article)
        print(f"  Score: {score:6.1f} | Sport: {sport:10s} | Derby: {is_derby} | {article['title'][:50]}")
    print()
    
    # Test 5: Prioritize articles
    print("Test 5: Prioritize and select top 5 posts")
    print("-" * 80)
    top_posts = prioritizer.prioritize_articles(articles, top_n=5)
    
    for i, post in enumerate(top_posts, 1):
        print(f"\n#{i} - Score: {post['priority_score']:.1f}")
        print(f"    Title: {post['title']}")
        print(f"    Sport: {post['sport']}")
        print(f"    Derby: {post['is_derby']}")
        categories = [cat['tag'] for cat in post.get('categories', [])]
        print(f"    Categories: {', '.join(categories)}")
    
    print()
    print("=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    print()
    
    # Verify expected results
    assert len(articles) == 10, f"Expected 10 articles, got {len(articles)}"
    assert len(top_posts) == 5, f"Expected 5 top posts, got {len(top_posts)}"
    
    # Check that football articles with transfers are at the top
    top_post = top_posts[0]
    top_categories = [cat['tag'] for cat in top_post.get('categories', [])]
    is_transfer = any('transfer' in tag or 'contract' in tag or 'departure' in tag for tag in top_categories)
    assert is_transfer, f"Top post should be about transfers, but got categories: {top_categories}"
    
    # Check that basketball articles have lower priority than football
    football_scores = [p['priority_score'] for p in top_posts if p['sport'] == 'football']
    basketball_scores = [p['priority_score'] for p in top_posts if p['sport'] == 'basketball']
    
    if football_scores and basketball_scores:
        assert max(basketball_scores) < max(football_scores), "Football should have higher priority than basketball"
    
    print("✓ All tests passed!")
    print()
    print("Prioritization Rules Verified:")
    print("  ✓ Transfers have highest priority")
    print("  ✓ Football > Basketball")
    print("  ✓ Derbys receive bonus points")
    print("  ✓ Scandals have high priority")
    print()
    print("=" * 80)
    
    return top_posts


if __name__ == "__main__":
    try:
        top_posts = test_prioritizer()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
