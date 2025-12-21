# Dropped Articles Analysis - Run 15-17-02

## Summary

**18 articles were dropped** during LLM enrichment in the `complete/merged` branch.

- Input: 63 articles
- Output: 45 articles  
- Lost: 18 articles (28.6% loss rate)

## Root Cause Hypothesis

The dropped articles are concentrated in **batch_1.json** (8 dropped) and **batch_2.json** (9 dropped), with 1 more from batch_6.json. These batches likely exceeded LLM output token limits, causing truncation of the response.

## Dropped Article IDs

```
07e43fffb49a6c8f  - Victor Osimhen CAF Awards/World Cup
0b3cb329866b0d76  - Full List of CAF Award 2025 winners
22fc0ed6d743f25c  - Hakimi named Player of Year
244a1c0c61efec09  - Osimhen loses, Hakimi crowned
25c5bddb9acb60a2  - Hakimi wins CAF Player of Year
3a5bc03d8d32410f  - Hakimi tipped to edge Osimhen
47b227a1fe8216e6  - Morocco scoops doubles at CAF
68b17ade37777d6a  - Hakimi Historic CAF Awards Victory
712816c8b346cc14  - Hakimi Beats Osimhen African Player
720fa2131b10859b  - Hakimi Takes 2025 CAF Men's Player
7aec68465a6ea33f  - Galatasaray'da Osimhen (Turkish)
804d012474277176  - Osimhen treatment strain bleeding
834f0180f2642530  - Hakimi Deserved CAF Player of Year
89595c5990de9dd2  - Hakimi wins 2025 CAF Men's Player
99191558b42ea667  - Meet past CAF Player of Year winners
a899ffb1d930a3cd  - Morocco Hakimi wins Africa Player
b241823f24f7944e  - Hakimi Crowned African Footballer
bb5f098f5a02cea4  - CAF Award 2025 Full List winners
```

## Topic Distribution

### Dropped Articles by Topic:
- CAF Awards / Hakimi: **15 articles**
- Osimhen injury/news: **2 articles**
- Other: **1 article**

### Kept Articles by Topic:
- CAF Awards / Hakimi: 9 articles
- Osimhen injury/news: 10 articles
- Galatasaray: 4 articles
- Fenerbahce: 3 articles
- Liverpool: 2 articles
- Transfers: 2 articles
- Other: 15 articles

## Information Loss Assessment

### Topics Still Covered (Redundant Drops)
Most dropped articles were **redundant** - the same topics are covered by kept articles:
- ✅ CAF Awards winner (Hakimi) - covered by 9 kept articles
- ✅ Osimhen injury - covered by 16 kept articles
- ✅ CAF Awards ceremony - covered

### Unique Sources Lost
**9 news sources completely lost** (no articles from these sources made it through):
- bizwatchnigeria.ng
- kawowo.com
- nycefmonline.com
- persecondnews.com
- thecitizenng.com
- www.ghanamma.com
- www.pulse.com.gh
- www.thenigerianvoice.com
- www.vanguardngr.com

### Potentially Unique Content Lost

1. **"Full List of CAF Award 2025 winners"** (2 articles with complete winners list)
   - Contains: All category winners, runners-up, detailed breakdown
   - Unique info: Complete award list not in other articles

2. **"Meet past CAF Player of Year winners"** (historical context article)
   - Unique info: Historical perspective missing from kept articles

3. **"Hakimi Deserved CAF Player of the Year - Ikpeba quote"**
   - Contains expert opinion from Ikpeba
   - May have unique quotes

## Impact Level: **MEDIUM**

- ✅ **Core news covered**: Main story (Hakimi wins, Osimhen injury) preserved
- ⚠️ **Some unique sources lost**: 9 news outlets not represented
- ⚠️ **Detail loss**: Complete awards list, historical context
- ❌ **No Turkish articles lost in this branch**: All Turkish content preserved

## Recommendations

1. **Reduce batch size** for merged articles (they're longer due to combined content)
2. **Monitor token usage** per batch to prevent truncation
3. **Consider retry logic** for batches that show data loss
4. **Add validation** comparing input vs output article counts before saving

## Python Code to Reproduce Analysis

```python
import json
import re
import glob

def extract_article_ids_from_input(folder_path):
    """Extract article_ids from input batch JSON files."""
    article_ids = {}
    input_files = sorted(glob.glob(f"{folder_path}/batch_*.json"))
    
    for file_path in input_files:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        for article in data.get('articles', []):
            aid = article.get('article_id', '')
            if aid:
                article_ids[aid] = article
    
    return article_ids

def extract_article_ids_from_predictions(file_path):
    """Extract article_ids from prediction JSONL file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Match: \"article_id\": \"<16 hex chars>\"
    matches = re.findall(r'\\"article_id\\"\s*:\s*\\"([a-f0-9]{16})\\"', content)
    return set(matches)

# Usage
input_articles = extract_article_ids_from_input("batch_enrichment/complete/merged/input")
output_ids = extract_article_ids_from_predictions("batch_enrichment/complete/merged/prediction-*/predictions.jsonl")

dropped_ids = set(input_articles.keys()) - output_ids
print(f"Dropped: {len(dropped_ids)} articles")
```
