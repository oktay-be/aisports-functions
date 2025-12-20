# Unified Article Group Processing Prompt

## OBJECTIVE

Process a group of semantically similar sports news articles. These articles have been pre-grouped using vector similarity (cosine >= 0.85). Your task is to make a merge decision and process the output articles.

## INPUT DATA

You will receive a JSON object containing:
- `group_id`: Unique identifier for this article group
- `group_size`: Number of articles in the group
- `max_similarity`: Maximum cosine similarity between articles in the group
- `articles`: Array of article objects

Each article has:
- `article_id`: Pre-generated unique identifier (16-char hex hash) - **PRESERVE THIS**
- `url`: Original article URL
- `title`: Article title (in original language)
- `body`: Full article text
- `source`: Source domain
- `published_at`: Publication timestamp
- `keywords_used`: Keywords that matched this article
- `language`: Language code (e.g., "tr", "en", "es", "it")
- `region`: Region code - "tr" for Turkish content, "eu" for all others

## YOUR TASKS

### Task 1: MERGE DECISION

Analyze all articles in the group and decide:

**MERGE** - Combine into ONE article if they describe the **EXACT same event/news**:
- Same match result (same teams, same score, same key players)
- Same transfer (same player, same clubs, same stage)
- Same announcement (same award, same nominees/winners)
- Same incident (same event, same people involved)

**KEEP_SEPARATE** - Keep as separate articles if they describe **different aspects**:
- Match report vs post-match reaction/interview
- Match report vs tactical analysis
- Match report vs injury update from the match
- General announcement vs player-specific feature
- Transfer rumor vs transfer confirmed
- Different matches/events even if involving same team

### Task 2: MERGE PROCESSING (if MERGE decision)

When merging articles:
1. **article_id**: Use from the highest-quality article
2. **original_url**: Use from the highest-quality article
3. **merged_from_urls**: List ALL original URLs
4. **title**: Use the most descriptive/complete title
5. **summary**: Combine ALL unique information - NO data loss
6. **key_entities**: Union of all teams, players, amounts, dates
7. **categories**: Union of all applicable tags
8. **published_date**: Use the EARLIEST date
9. **content_quality**: Use the HIGHEST quality
10. **region**: Use from the HIGHEST-QUALITY/MOST-COMPLETE article (the one providing original_url)

### Task 3: FOR EACH OUTPUT ARTICLE

Generate the following fields:

#### summary (CRITICAL - PRESERVE LANGUAGE)
- Write in the **ORIGINAL LANGUAGE** of the article
- If article is in Turkish, summary MUST be in Turkish
- If article is in Spanish, summary MUST be in Spanish
- If article is in English, summary MUST be in English
- Comprehensive summary preserving ALL key information
- Include: player names, team names, scores, transfer amounts, dates, quotes

#### categories (STRICT TAXONOMY)
Select from allowed tags with confidence and evidence:

**Sport Tags (for non-football):**
- `basketball` - Use ONLY this for basketball articles
- `volleyball` - Use ONLY this for volleyball articles
- `other-sports` - Use ONLY this for tennis, F1, etc.

**Football Tags:**
- `transfers-confirmed`, `transfers-rumors`, `transfers-negotiations`, `transfers-interest`
- `contract-renewals`, `contract-disputes`, `departures`
- `match-results`, `match-preview`, `match-report`, `match-postponement`
- `tactical-analysis`, `performance-analysis`, `league-standings`
- `super-lig`, `champions-league`, `european-competitions`, `domestic-cups`, `turkish-cup`
- `international-tournaments`, `youth-competitions`, `womens-football`
- `club-news`, `squad-changes`, `injuries`, `stadium-infrastructure`
- `disciplinary-actions`, `field-incidents`, `off-field-scandals`, `corruption-allegations`, `legal-issues`
- `federation-politics`, `elections-management`, `government-sports`, `uefa-fifa-matters`, `policy-changes`
- `fan-activity`, `fan-rivalry`, `fan-protest`
- `team-rivalry`, `personal-rivalry`, `derby`
- `interviews`, `social-media`, `gossip-entertainment`, `player-statement`, `club-statement`

#### x_post (ALWAYS TURKISH)
- Maximum 280 characters
- **ALWAYS in Turkish** regardless of article language
- Must contain ACTUAL information (names, scores, facts)
- Include 1-2 relevant hashtags at the end
- **NO CLICKBAIT**: No "Iste detaylar...", "Bomba iddia!" without content
- **MUST BE INFORMATIVE**: Deliver the actual news, not just tease it

**BAD x_post** (DO NOT DO):
```
"Fenerbahce'den flas transfer hamlesi! Iste detaylar... #Fenerbahce"
```

**GOOD x_post**:
```
"Fenerbahce, Juventus'tan Dusan Vlahovic'i 45 milyon Euro'ya kadrosuna katti. Sirbistanli golcu 4 yillik sozlesme imzaladi. #Fenerbahce #Transfer"
```

#### summary_translation (CONDITIONAL)
- If article language is NOT Turkish: Provide Turkish translation of the summary
- If article language IS Turkish: Set to null or empty string

#### confidence (REQUIRED)
- Overall confidence score for the article (0.0 to 1.0)
- Based on: source reliability, information completeness, corroboration across merged articles
- 0.9-1.0: High confidence - verified facts, official sources
- 0.7-0.9: Medium confidence - reliable sources, clear information
- 0.5-0.7: Lower confidence - rumors, unverified claims
- Calculate as average of category confidences if uncertain

## OUTPUT FORMAT

Return JSON:

```json
{
  "group_decision": "MERGE" | "KEEP_SEPARATE",
  "merge_reason": "Same match report: Galatasaray vs Fenerbahce 3-1",
  "output_articles": [
    {
      "article_id": "a1b2c3d4e5f67890",
      "original_url": "https://example.com/article",
      "merged_from_urls": ["url1", "url2"],
      "title": "Article title in original language",
      "summary": "Comprehensive summary in ORIGINAL language with all key details...",
      "key_entities": {
        "teams": ["Galatasaray", "Fenerbahce"],
        "players": ["Osimhen", "Icardi"],
        "amounts": ["30 million euro"],
        "dates": ["2025-01-15"]
      },
      "categories": [
        {
          "tag": "match-results",
          "confidence": 0.95,
          "evidence": "Article reports final score 3-1"
        },
        {
          "tag": "super-lig",
          "confidence": 0.9,
          "evidence": "Turkish Super Lig derby match"
        }
      ],
      "source": "example.com",
      "published_date": "2025-01-15T18:00:00Z",
      "content_quality": "high",
      "confidence": 0.92,
      "language": "turkish",
      "region": "tr",
      "summary_translation": null,
      "x_post": "Derbi Galatasaray'in! Osimhen'in 2 goluyle sari-kirmizililar Fenerbahce'yi 3-1 yendi. Icardi penalti kacirdi. #Galatasaray #Derbi"
    }
  ]
}
```

## PROCESSING EXAMPLES

### Example 1: MERGE (Same Match Report)

**Input Group:**
```
Article A: "Osimhen scores twice as Galatasaray beats Fenerbahce 3-1"
Article B: "Galatasaray wins against Fenerbahce, Osimhen shines with 2 goals"
```

**Decision:** MERGE - Same match, same result, same key player

**Output:** ONE article with combined information

### Example 2: KEEP_SEPARATE (Different Story Types)

**Input Group:**
```
Article A: "Galatasaray beats Fenerbahce 3-1" (match report)
Article B: "Osimhen injury concern after derby goals" (injury news)
```

**Decision:** KEEP_SEPARATE - Different article types (match report vs injury news)

**Output:** TWO separate articles

### Example 3: SINGLETON (Single Article)

**Input Group:** 1 article only

**Decision:** KEEP_SEPARATE (nothing to merge)

**Output:** ONE processed article

## CRITICAL REMINDERS

1. **PRESERVE article_id**: Copy exactly from input - never generate new IDs
2. **PRESERVE LANGUAGE**: Summary in original language, x_post always Turkish
3. **PRESERVE REGION**: When merging mixed-region groups, use region from the most complete article
4. **NO DATA LOSS**: When merging, include ALL unique facts from ALL articles
5. **NO CLICKBAIT**: x_post must contain actual information
6. **CONSERVATIVE MERGING**: When uncertain, KEEP_SEPARATE is safer

Process the provided article group according to these specifications and return the structured JSON result.
