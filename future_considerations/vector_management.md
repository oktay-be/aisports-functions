# Architecture Decision Record: Embedding Storage & Vector Search

**Date:** December 18, 2025  
**Status:** Accepted  
**Context:** Article De-duplication Pipeline

## 1. Current Strategy: GCS-Based In-Memory Search

For the initial implementation of the Article Processing Pipeline, we have decided to rely solely on **Google Cloud Storage (GCS)** and **In-Memory (NumPy)** calculation for vector similarity and deduplication.

### The Rationale (The Math)
We operate under a specific constraint: **Deduplication is scoped to the current day.**
- **Volume:** Estimated max ~100 articles per run × 24 runs/day = 2,400 articles.
- **Size:** 2,400 vectors (768-dim) ≈ 7 MB of data.
- **Latency:** Downloading 24 small JSON files from GCS takes < 2 seconds. Computing cosine similarity on 7MB of data in memory takes < 0.1 seconds.
- **Cost:** GCS storage and Class B operations are negligible compared to managed database costs.

### Decision
We will **not** implement a dedicated Vector Database (Vector DB) for the MVP. The overhead of managing an index and the cost of idle instances does not justify the performance gain at this scale.

---

## 2. Future Migration Paths (GCP Ecosystem)

As the system scales, we may hit specific limitations (e.g., deduplicating against a 7-day window instead of 24 hours, or processing >20,000 articles/day). When "in-memory" processing becomes too slow or memory-intensive, we will migrate to a managed service.

The following options were evaluated as equivalents to **Azure AI Search**:

### Option A: Firestore with Vector Search (Recommended Next Step)
*   **Description:** Store article metadata and embeddings directly in Firestore documents. Use the native `FindNearest` query.
*   **Why:** It is **Serverless**. It scales to zero, requires no instance management, and integrates natively with Cloud Functions.
*   **Trigger for Migration:** When GCS download times exceed 5-10 seconds, or we need atomic updates.

### Option B: Cloud SQL (PostgreSQL) + pgvector
*   **Description:** Standard Postgres instance with the `pgvector` extension.
*   **Why:** Good if we need complex relational queries alongside vector search (e.g., *"Find similar articles published by Source X between 2 PM and 4 PM"*).
*   **Trade-off:** Requires managing SQL instances and connection pooling.

### Option C: Vertex AI Vector Search (formerly Matching Engine)
*   **Description:** Google's high-scale, low-latency enterprise vector DB.
*   **Why:** Capable of handling millions/billions of vectors with millisecond latency.
*   **Verdict:** **Overkill.** This service often incurs high minimum monthly costs (for index endpoints) and is designed for scales far beyond this project's scope.

---

## 3. Scaling Triggers

We will trigger a review of this architecture if:
1.  **Volume:** Daily article volume exceeds **15,000**.
2.  **Scope:** Business requirements change to require deduplication against the **past 7+ days** (increasing the search space significantly).
3.  **Performance:** The `cross_run_dedup` step consistently takes longer than **20 seconds**.