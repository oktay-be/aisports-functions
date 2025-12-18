Based on your requirements and the shift to a more robust architecture, I have generated a comprehensive strategic plan.

This plan outlines the **"Serverless Vector Search"** approach. It moves the heavy lifting from the LLM (which is error-prone on large lists) to mathematical embeddings (which are precise and cheap), using Gemini only for the final high-intelligence decisions.

Here is the plan file:

```markdown:plan.md
# Strategic Plan: Serverless Vector Deduplication for Sports News

## 1. Executive Summary
The current "Batch Inference" approach fails because LLMs struggle with $N^2$ comparisons in a single context window, leading to "lazy" processing and aggressive deduplication.

We will replace this with a **Hybrid Pipeline** optimized for Google Cloud Run:
1.  **Tier 1 (Code):** Instant string matching for exact duplicates.
2.  **Tier 2 (Vectors):** Use `text-embedding-004` to mathematically find "candidate pairs" (similiarity > 0.85).
3.  **Tier 3 (Agent):** Use Gemini 1.5 Flash *only* to judge these specific candidate pairs.

**Key Benefit:** drastic reduction in cost and hallucination. We stop asking the LLM to "find" duplicates and start asking it to "verify" them.

---

## 2. Architecture (Serverless / In-Memory)

Since the daily volume is likely <10,000 articles, we **do not** need Vertex AI Vector Search (which costs ~$1500/mo min). We can run the vector math **in-memory** inside Cloud Run.

**Data Flow:**
`PubSub` -> `Cloud Run Function` -> `Process` -> `GCS/Next Step`

### The Processing Logic inside Cloud Run:
1.  **Ingest:** Load all scraped articles.
2.  **Filter:** Python-based exact URL/Title deduplication.
3.  **Embed:** Send Titles + Summaries to Vertex AI Embedding API (in batches).
4.  **Compute:** Calculate Cosine Similarity Matrix (NumPy).
5.  **Candidate Selection:** Identify pairs with score > 0.85.
6.  **Agent Verify:** Send *only* candidate pairs to Gemini 1.5 Flash for "Merge/Keep" decision.
7.  **Finalize:** Produce final JSON.

---

## 3. Implementation Steps

### Step 1: Python Pre-filtering (Tier 1)
*Cost: $0.00*
Before calling any AI models, remove exact matches.
- Normalize URLs (strip query params).
- Calculate Levenshtein distance for titles.
- If Similarity > 95% -> **Hard Delete** (Keep longest body).

### Step 2: Vector Embedding Generation
*Model: `text-embedding-004`*
*Cost: ~$0.000025 per 1k characters*

We must chunk requests to avoid hitting API limits (max ~250 items per call).

```python
import numpy as np
from google import genai
from google.genai import types

def generate_embeddings(texts, client):
    # Chunking to avoid batch limits
    BATCH_SIZE = 100 
    embeddings = []
    
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.models.embed_content(
            model="text-embedding-004",
            contents=batch,
            config=types.EmbedContentConfig(
                task_type="SEMANTIC_SIMILARITY"
            )
        )
        # Extract values
        batch_embeddings = [e.values for e in response.embeddings]
        embeddings.extend(batch_embeddings)
        
    return np.array(embeddings)
```

### Step 3: The "Serverless Vector Search" (Math)
*Cost: Free (Compute time)*

Compare every article against every other article using Matrix Multiplication.

```python
def find_candidates(articles, embedding_matrix, threshold=0.85):
    # Dot product of normalized vectors = Cosine Similarity
    # Result is a square matrix of float scores (0.0 to 1.0)
    similarity_matrix = np.dot(embedding_matrix, embedding_matrix.T)
    
    candidates = []
    rows, cols = similarity_matrix.shape
    
    # Iterate upper triangle only (avoid A vs A, and A vs B + B vs A)
    for i in range(rows):
        for j in range(i + 1, cols):
            score = similarity_matrix[i][j]
            if score >= threshold:
                candidates.append({
                    "article_a": articles[i],
                    "article_b": articles[j],
                    "score": float(score)
                })
    return candidates
```

### Step 4: The Agentic Verifier (Tier 2)
*Model: `gemini-1.5-flash`*

We only invoke the LLM for the pairs found in Step 3. This reduces LLM calls from $N$ (processing all text) to just the tricky edge cases.

**Prompt Strategy:**
"You are a sports editor. Compare Article A and Article B.
- If they describe the EXACT same match/event -> Output 'MERGE'
- If they are different angles (Match vs Reaction) -> Output 'KEEP_BOTH'
- If they are different events -> Output 'KEEP_BOTH'
Output JSON: {action: 'MERGE' | 'KEEP_BOTH', reason: '...'}"

---

## 4. Dependencies & Configuration

**`requirements.txt`:**
```text
google-genai==1.22.0
numpy>=1.24.0
scikit-learn>=1.3.0  # Optional, but good for advanced metrics
python-dotenv>=1.0.0
```

**Cloud Run Configuration:**
- **Memory:** 2GB (Safe for holding embeddings of ~5k articles in memory).
- **Timeout:** 300s (Embedding 500 articles takes ~10-20s).
- **Concurrency:** 1 (Keep it simple for batch processing).

## 5. Next Steps
1.  Update `main.py` to include the batching/embedding logic.
2.  Create the specific `verify_duplicates_prompt`.
3.  Deploy to Cloud Run Function.
```