# European Sports News Processing Prompt for Claude 4

## OBJECTIVE
Process and analyze European sports news data from a journ4list scraping session. Transform the raw data into a clean, deduplicated, summarized, and precisely classified JSON dataset.

## INPUT DATA
You will receive a JSON file containing scraped European sports news articles with the following structure:
- `articles`: Array of news articles with fields like `url`, `title`, `body`, `published_at`, `source`, `keywords_used`
- `session_metadata`: Metadata about the scraping session

## PROCESSING REQUIREMENTS

### 1. ARTICLE ID PRESERVATION (CRITICAL)
- Each input article contains an `article_id` field - this is a pre-generated unique identifier
- **DO NOT GENERATE NEW IDs**: Copy the `article_id` exactly from the input article to the output
- The `article_id` is used for tracking articles across the entire pipeline

### 2. LANGUAGE PRESERVATION (CRITICAL)
- **DO NOT TRANSLATE**: The `title` and `summary` MUST be in the **original language** of the source article.
- If the article is in Turkish, the summary must be in Turkish.
- If the article is in Spanish, the summary must be in Spanish.
- If the article is in English, the summary must be in English.
- The `language` field in the output should indicate the detected language (e.g., "turkish", "spanish", "english").

### 2. DEDUPLICATION

Remove duplicate articles using a **two-tier approach**: string matching OR entity matching.

#### Tier 1: String-Based Duplicates (High Confidence)

Two articles are duplicates if they meet ANY of these criteria:

1. **Exact URL match** (same `url` field)
2. **Title string similarity ≥90%**
   - Use character-level similarity (Levenshtein/SequenceMatcher)
   - Example: "Liverpool wins 3-1" vs "Liverpool win 3-1" = 95% → DUPLICATE
3. **Near-identical body content** (≥95% text overlap after normalization)

**Action:** Remove one, keep the version with most complete content (longest body).

#### Tier 2: Entity-Based Duplicates (Semantic Matching)

Two articles about the **same event** are duplicates if they meet ALL of these:

**For Match Reports:**
- Same teams (both teams mentioned in title)
- Same score/result (if mentioned)
- Same key player(s) (main subject of the article)
- Same date (within 24 hours)
- Both are match reports (not analysis/reaction/follow-up)

**Example - These ARE duplicates (MERGE):**
```
"Osimhen scores twice as Galatasaray beats Fenerbahce 3-1"
"Galatasaray wins against Fenerbahce as Osimhen shines with 2 goals: 3-1"

Match: Same teams, same score (3-1), same key player (Osimhen), same goals (2)
→ MERGE into one article
```

**For Award/Announcement Articles:**
- Same award/announcement (e.g., "CAF Player of the Year")
- Same nominees/winners mentioned (all key names present)
- Same date
- Both are announcements (not analysis/reaction)

**For Transfer Articles:**
- Same player
- Same club(s) involved
- Same transfer stage (rumor/negotiation/confirmed)
- Within 48 hours

#### What is NOT a Duplicate (Keep Both)

Even if about the same event, these are **different stories**:

❌ **Different article types:**
- Match report ≠ Pre-match preview
- Match report ≠ Post-match reaction/interview
- Match report ≠ Tactical analysis
- Match report ≠ Injury update
- Announcement ≠ Follow-up analysis
- Announcement ≠ Individual player feature

❌ **Different focus:**
- General announcement ≠ Player-specific news
- Match result ≠ Financial impact analysis
- Match result ≠ Fan reactions
- Team news ≠ Individual player news

**Examples - Keep both:**
```
"Galatasaray beats Fenerbahce 3-1" (match report)
"Osimhen injury concern after scoring twice" (injury news)
→ Different story types → Keep both

"CAF Awards: Complete nominee list" (general announcement)
"Osimhen's journey to CAF POTY nomination" (player feature)
→ Different focus → Keep both

"Nigeria loses to DR Congo 4-3" (match result)
"Why Osimhen was substituted during Nigeria match" (tactical analysis)
→ Different story types → Keep both
```

#### Merging Strategy for Entity-Based Duplicates

When you identify entity-based duplicates (Tier 2), **MERGE them** to preserve all unique information:

**Merge Process:**
1. Use the **longest/most descriptive title**
2. **Combine summaries** without repetition (include unique facts from both)
3. **Merge entities**: Union of all teams, players, amounts, dates
4. **Merge categories**: Union of all category tags
5. Keep the **earliest published date**
6. Keep the **highest content quality**
7. Use article_id from the highest quality version

**Example Merge:**
```
Article A: "Osimhen scores twice as Galatasaray beats Fenerbahce 3-1"
  Summary: "Osimhen scored two goals as Galatasaray won 3-1."
  Entities: {teams: [Galatasaray, Fenerbahce], players: [Osimhen]}

Article B: "Galatasaray wins as Osimhen shines with 2 goals: 3-1"
  Summary: "Galatasaray defeated Fenerbahce 3-1. Osimhen's brace. Icardi also scored."
  Entities: {teams: [Galatasaray, Fenerbahce], players: [Osimhen, Icardi]}

MERGED OUTPUT:
  Title: "Galatasaray wins against Fenerbahce as Osimhen shines with 2 goals: 3-1"
  Summary: "Galatasaray defeated Fenerbahce 3-1 in the derby. Osimhen scored a brace (two goals) and Icardi also found the net."
  Entities: {teams: [Galatasaray, Fenerbahce], players: [Osimhen, Icardi]}
```

#### Processing Instructions

**Step 1: Extract entities**
For each article, identify:
- Teams mentioned (especially in title)
- Players mentioned (especially in title)
- Scores/results
- Award names
- Transfer details

**Step 2: Check Tier 1 (String-based)**
- Calculate title similarity for all pairs
- If ≥90% similarity OR same URL → Mark as duplicate, keep best version
- Remove duplicates

**Step 3: Check Tier 2 (Entity-based)**
For remaining articles:
- Group by event type (match, award, transfer)
- Within each group, check entity overlap:
  - Match reports: Same teams + same score + same key player → MERGE
  - Award articles: Same award + same nominees → MERGE
  - Transfer articles: Same player + same clubs → MERGE
- If different article types → Keep both (not duplicates)

**Step 4: Conservative approach**
- If unsure whether two articles are duplicates → **KEEP BOTH**
- Better to over-retain than over-remove
- Focus on removing OBVIOUS duplicates only

**Step 5: Log results**
In processing_summary:
```json
{
  "duplicates_removed": X,
  "articles_merged": Y,
  "merge_details": [
    "Merged 2 match reports: Galatasaray vs Fenerbahce",
    "Merged 3 CAF Award announcements"
  ]
}
```

### 3. DATA CLEANING
- Remove articles with missing or empty `title` and `body` fields
- Clean up repeated content within article bodies (remove excessive repetition)
- Normalize special characters and encoding issues
- Remove navigation elements, advertisements, and non-news content from body text

### 5. SUMMARIZATION
- **LANGUAGE:** The summary MUST be written in the **SAME LANGUAGE** as the original article. Do NOT translate.
- Create a comprehensive summary that preserves all important information (no strict sentence limit)
- Include ALL key details: player names, team names, transfer amounts, dates, sources, quotes
- Capture the main news event, supporting details, and context
- Preserve important details like monetary amounts, dates, official statements, and background information
- Maintain factual accuracy while condensing repetitive or redundant content
- Ensure no critical information is lost during the summarization process

### 6. PRECISE CLASSIFICATION
Classify each article using tags from the **ALLOWED TAGS** list provided at the end of this prompt. 

**CRITICAL RULES:**
- For **basketball** articles: Use ONLY the tag `basketball`
- For **volleyball** articles: Use ONLY the tag `volleyball`  
- For **other non-football sports**: Use ONLY the tag `other-sports`
- For **football** articles: Select appropriate tags from the allowed list (multiple tags encouraged)

**If no existing tag fits:**
- You may propose a NEW tag using the `suggested_new_tags` field
- New tags must use hyphenated format: `new-category-name`
- Provide justification for why no existing tag fits

### 7. CONFIDENCE SCORING
For each category assignment, provide a confidence score (0.0-1.0):
- 1.0: Explicitly stated facts with evidence
- 0.8: Strong indications with supporting details
- 0.6: Moderate indications based on context
- 0.4: Weak indications, mostly speculation
- 0.2: Minimal indication, mostly assumed

### 8. TRANSLATION & SOCIAL MEDIA
- **Summary Translation**:
  - If the article is NOT in Turkish, provide a Turkish translation of the summary in `summary_translation`.
  - If the article IS in Turkish, leave `summary_translation` as null or empty string.
- **X Post**:
  - Generate a short, engaging tweet (max 280 chars) in `x_post`.
  - **Language**: ALWAYS Turkish.
  - Include relevant hashtags.

## OUTPUT FORMAT

Return a JSON object with this exact structure:

```json
{  "processing_summary": {
    "total_input_articles": 0,
    "articles_after_deduplication": 0,
    "articles_after_cleaning": 0,
    "duplicates_removed": 0,
    "articles_merged": 0,
    "empty_articles_removed": 0,
    "processing_date": "2025-06-21T00:00:00Z",
    "merge_details": [
      "Description of merges performed, e.g., 'Merged 2 match reports: Galatasaray vs Fenerbahce'"
    ],
    "suggested_new_tags": [
      {
        "tag": "new-tag-name",
        "justification": "Reason why no existing tag fits this content"
      }
    ]
  },
  "processed_articles": [
    {
      "article_id": "preserve_from_input",
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
          "tag": "transfers-rumors",
          "confidence": 0.8,
          "evidence": "Article mentions unconfirmed interest from Italian clubs"
        },
        {
          "tag": "contract-disputes", 
          "confidence": 0.6,
          "evidence": "Player reportedly unhappy with contract terms"
        }
      ],      
      "source": "www.marca.es",
      "published_date": "2025-06-21T09:20:50+03:00",
      "keywords_matched": ["real madrid", "transfer"],
      "content_quality": "high|medium|low",
      "language": "spanish",
      "summary_translation": "Real Madrid transferi hakkında Türkçe özet...",
      "x_post": "Real Madrid'den flaş transfer hamlesi! 🚨 İspanyol devi genç yıldız için harekete geçti. #RealMadrid #Transfer"
    }
  ]
}
```

## CLASSIFICATION GUIDELINES

**Be precise and evidence-based:**
- Only assign categories that are clearly supported by the article content
- Multiple categories are encouraged for football articles
- Provide specific evidence quotes for each category assignment
- Use higher confidence scores for concrete facts, lower for speculation
- Only propose new tags via `suggested_new_tags` if NO existing tag fits

**Sport-Specific Rules:**
- **Basketball**: Use ONLY the `basketball` tag
- **Volleyball**: Use ONLY the `volleyball` tag
- **Other sports** (tennis, F1, etc.): Use ONLY the `other-sports` tag
- **Football**: Use multiple tags from the allowed list as appropriate

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
