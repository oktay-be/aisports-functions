# European Sports News Processing Prompt for Claude 4

## OBJECTIVE
Process and analyze European sports news data from a journ4list scraping session. Transform the raw data into a clean, deduplicated, summarized, and precisely classified JSON dataset.

## INPUT DATA
You will receive a JSON file containing scraped European sports news articles with the following structure:
- `articles`: Array of news articles with fields like `url`, `title`, `body`, `published_at`, `source`, `keywords_used`
- `session_metadata`: Metadata about the scraping session

## PROCESSING REQUIREMENTS

### 1. LANGUAGE PRESERVATION (CRITICAL)
- **DO NOT TRANSLATE**: The `title` and `summary` MUST be in the **original language** of the source article.
- If the article is in Turkish, the summary must be in Turkish.
- If the article is in Spanish, the summary must be in Spanish.
- If the article is in English, the summary must be in English.
- The `language` field in the output should indicate the detected language (e.g., "turkish", "spanish", "english").

### 2. DEDUPLICATION
- Remove duplicate articles based on:
  - Identical or very similar titles (≥90% similarity)
  - Same URL or same content body
  - Same core story but from different URLs
- Keep the most complete version (with most content) when duplicates are found
- Log how many duplicates were removed

### 3. DATA CLEANING
- Remove articles with missing or empty `title` and `body` fields
- Clean up repeated content within article bodies (remove excessive repetition)
- Normalize special characters and encoding issues
- Remove navigation elements, advertisements, and non-news content from body text

### 4. SUMMARIZATION
- **LANGUAGE:** The summary MUST be written in the **SAME LANGUAGE** as the original article. Do NOT translate.
- Create a comprehensive summary that preserves all important information (no strict sentence limit)
- Include ALL key details: player names, team names, transfer amounts, dates, sources, quotes
- Capture the main news event, supporting details, and context
- Preserve important details like monetary amounts, dates, official statements, and background information
- Maintain factual accuracy while condensing repetitive or redundant content
- Ensure no critical information is lost during the summarization process

### 5. PRECISE CLASSIFICATION
Classify each article with multiple relevant category tags from this taxonomy. **You are NOT restricted to this taxonomy** - feel free to add new categories or subcategories if the content requires more specific classification:

**TRANSFER CATEGORIES:**
- `transfers_confirmed` - Official, completed transfers
- `transfers_rumors` - Unconfirmed transfer speculation
- `transfers_negotiations` - Ongoing transfer talks/meetings
- `transfers_interest` - Club interest or scouting
- `contract_renewals` - Contract extensions
- `contract_disputes` - Contract disagreements
- `departures` - Players leaving clubs

**RIVALRY CATEGORIES:**
- `team_rivalry` - Competition between clubs (local derbies, historic rivalries, etc.)
- `personal_rivalry` - Individual player/coach conflicts
- `fan_rivalry` - Supporter-related tensions

**SCANDAL/CONTROVERSY:**
- `field_incidents` - On-field fights, red cards, referee disputes
- `off_field_scandals` - Personal conduct, legal issues
- `corruption_allegations` - Match fixing, bribery claims
- `disciplinary_actions` - Suspensions, fines, sanctions

**POLITICS IN SPORTS:**
- `elections_management` - Club presidential elections, board changes
- `federation_politics` - National federation matters (FA, FIGC, DFB, etc.)
- `government_sports` - State involvement in sports
- `policy_changes` - Rule changes, regulations
- `uefa_fifa_matters` - European and international governing body decisions

**PERFORMANCE & COMPETITION:**
- `match_results` - Game outcomes and analysis
- `performance_analysis` - Player/team performance evaluation
- `tactical_analysis` - Coach strategies and formations
- `injury_news` - Player injuries and recovery
- `squad_changes` - Lineup modifications

**BUSINESS & FINANCE:**
- `financial_news` - Club finances, debt, revenue
- `sponsorship_deals` - Commercial partnerships
- `stadium_infrastructure` - Facility developments

**LEAGUE & COMPETITION:**
- `league_standings` - Table positions, points, relegation battles
- `european_competitions` - Champions League, Europa League, Conference League
- `domestic_cups` - National cup competitions
- `international_tournaments` - World Cup, Euros, Nations League
- `youth_competitions` - U21, academy tournaments

**GOSSIP & ENTERTAINMENT:**
- `personal_life` - Player personal matters (non-scandalous)
- `social_media` - Player social media activities
- `lifestyle_news` - Player lifestyle coverage

**ADDITIONAL CATEGORIES:**
- Add new categories as needed based on the specific content
- Use descriptive names following the same naming convention (lowercase_with_underscores)
- Provide clear descriptions for any new categories you create

### 6. CONFIDENCE SCORING
For each category assignment, provide a confidence score (0.0-1.0):
- 1.0: Explicitly stated facts with evidence
- 0.8: Strong indications with supporting details
- 0.6: Moderate indications based on context
- 0.4: Weak indications, mostly speculation
- 0.2: Minimal indication, mostly assumed

## OUTPUT FORMAT

Return a JSON object with this exact structure:

```json
{  "processing_summary": {
    "total_input_articles": 0,
    "articles_after_deduplication": 0,
    "articles_after_cleaning": 0,
    "duplicates_removed": 0,
    "empty_articles_removed": 0,
    "processing_date": "2025-06-21T00:00:00Z",
    "custom_categories_added": ["new_category1", "new_category2"]
  },
  "processed_articles": [
    {
      "id": "unique_identifier",
      "original_url": "source_url",
      "title": "cleaned_title (in original language)",
      "summary": "Comprehensive summary in ORIGINAL LANGUAGE preserving all key information, quotes, amounts, dates, and context",
      "key_entities": {
        "teams": ["team1", "team2"],
        "players": ["player1", "player2"],
        "amounts": ["30 million euro"],
        "dates": ["June 21, 2025"]
      },
      "categories": [
        {
          "tag": "transfers_rumors",
          "confidence": 0.8,
          "evidence": "Article mentions unconfirmed interest from Italian clubs"
        },
        {
          "tag": "contract_disputes", 
          "confidence": 0.6,
          "evidence": "Player reportedly unhappy with contract terms"
        }
      ],      
      "source": "www.marca.es",
      "published_date": "2025-06-21T09:20:50+03:00",
      "keywords_matched": ["real madrid", "transfer"],
      "content_quality": "high|medium|low",
      "language": "spanish"
    }
  ]
}
```

## CLASSIFICATION GUIDELINES

**Be precise and evidence-based:**
- Only assign categories that are clearly supported by the article content
- Multiple categories are encouraged when appropriate
- Provide specific evidence quotes for each category assignment
- Use higher confidence scores for concrete facts, lower for speculation
- Feel free to create new categories if existing ones don't adequately describe the content

**European Football Context:**
- Understand major European leagues: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, etc.
- Recognize football terminology and cultural context across different countries
- Consider the reliability and editorial style of various European sports media
- Account for different languages and regional football cultures

**Transfer News Precision:**
- Distinguish between confirmed deals and rumors
- Note the source of information (official club statements vs. media speculation)
- Identify the stage of transfer process (interest, negotiations, completion)

## QUALITY REQUIREMENTS
- **LANGUAGE:** Summaries MUST be in the original language.
- Every article must have at least one category with confidence ≥ 0.6
- Summaries must be comprehensive and factual, preserving all important information without data loss
- All monetary amounts and dates must be preserved accurately
- Player names and team names must be preserved with correct spelling
- If you create new categories, provide a brief explanation in the output
- Prioritize information preservation over brevity in summaries

## PROCESSING INSTRUCTIONS
1. First, analyze the data structure and identify all articles
2. Remove duplicates and empty articles
3. Clean and normalize the text content
4. Extract entities and create summaries
5. Apply classification with evidence-based reasoning
6. Generate the final JSON output

Process the attached European sports news data according to these specifications and return the structured JSON result.
