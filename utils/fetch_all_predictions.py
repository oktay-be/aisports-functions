import json
import os
from google.cloud import storage
import sys

# Reuse logic from inspect_predictions.py if possible, or reimplement simplified version
def extract_articles_from_entry(data):
    """Extracts a list of article objects from a single JSONL entry."""
    articles = []
    
    # Case 1: Vertex AI Batch Response (nested JSON in candidates)
    if 'response' in data and 'candidates' in data['response']:
        try:
            candidates = data['response']['candidates']
            if candidates and len(candidates) > 0:
                content_parts = candidates[0].get('content', {}).get('parts', [])
                if content_parts:
                    text_content = content_parts[0].get('text', '')
                    # Clean markdown code blocks if present
                    text_content = text_content.replace('```json', '').replace('```', '').strip()
                    
                    if text_content:
                        inner_data = json.loads(text_content)
                        
                        if isinstance(inner_data, list):
                            articles.extend(inner_data)
                        elif isinstance(inner_data, dict):
                            # Check for common keys
                            if 'consolidated_articles' in inner_data:
                                articles.extend(inner_data['consolidated_articles'])
                            elif 'processed_articles' in inner_data:
                                articles.extend(inner_data['processed_articles'])
                            elif 'articles' in inner_data:
                                articles.extend(inner_data['articles'])
                            else:
                                # Maybe the dict itself is an article? Or it's a wrapper we don't know.
                                # For now, assume if it has 'title' and 'summary', it's an article
                                if 'title' in inner_data and 'summary' in inner_data:
                                    articles.append(inner_data)
        except Exception as e:
            print(f"  [Warn] Error parsing nested JSON in Vertex response: {e}")

    # Case 2: Direct prediction object (or other formats)
    elif 'prediction' in data:
        pred = data['prediction']
        if isinstance(pred, list):
             articles.extend(pred)
        elif isinstance(pred, dict):
             articles.append(pred)
    
    # Case 3: The line itself is the list of articles or an article
    elif isinstance(data, list):
        articles.extend(data)
    elif isinstance(data, dict):
        if 'consolidated_articles' in data:
             articles.extend(data['consolidated_articles'])
        elif 'processed_articles' in data:
             articles.extend(data['processed_articles'])
        elif 'title' in data: # Simple heuristic
             articles.append(data)

    return articles

def main():
    bucket_name = "aisports-scraping"
    prefix = "news_data/batch_processing/"
    output_file = "all_aggregated_predictions.jsonl"
    
    print(f"Connecting to bucket: {bucket_name}")
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
    except Exception as e:
        print(f"Error connecting to GCS: {e}")
        return

    print(f"Listing blobs with prefix: {prefix}")
    blobs = bucket.list_blobs(prefix=prefix)
    
    target_files = []
    for blob in blobs:
        if blob.name.endswith("predictions.jsonl") and "stage2_deduplication" in blob.name:
            target_files.append(blob)
    
    print(f"Found {len(target_files)} prediction files.")
    
    all_articles = []
    
    for blob in target_files:
        print(f"Processing: {blob.name}")
        try:
            content = blob.download_as_text()
            lines = content.strip().split('\n')
            for line in lines:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    articles = extract_articles_from_entry(data)
                    all_articles.extend(articles)
                except json.JSONDecodeError:
                    print(f"  [Error] Invalid JSON in {blob.name}")
        except Exception as e:
            print(f"  [Error] Failed to download or process {blob.name}: {e}")

    print(f"Total extracted articles: {len(all_articles)}")
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        for article in all_articles:
            f.write(json.dumps(article, ensure_ascii=False) + '\n')
            
    print(f"Written to {output_file}")

if __name__ == "__main__":
    main()
