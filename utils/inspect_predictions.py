import json
import os
from google.cloud import storage
from urllib.parse import unquote
import sys

def parse_gcs_uri(uri):
    """Parses a GCS URI (gs:// or https://storage.cloud.google.com/) into bucket and blob name."""
    if uri.startswith("https://storage.cloud.google.com/"):
        parts = uri.replace("https://storage.cloud.google.com/", "").split("/", 1)
        return parts[0], parts[1]
    elif uri.startswith("gs://"):
        parts = uri.replace("gs://", "").split("/", 1)
        return parts[0], parts[1]
    return None, None

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
                            if 'processed_articles' in inner_data:
                                articles.extend(inner_data['processed_articles'])
                            elif 'articles' in inner_data:
                                articles.extend(inner_data['articles'])
                            else:
                                articles.append(inner_data)
        except Exception as e:
            print(f"  [Warn] Error parsing nested JSON in Vertex response: {e}")

    # Case 2: Direct prediction object (or other formats)
    elif 'prediction' in data:
        pred = data['prediction']
        if isinstance(pred, list):
            articles.extend(pred)
        else:
            articles.append(pred)
            
    # Case 3: The line itself is the data
    else:
        if isinstance(data, list):
            articles.extend(data)
        elif isinstance(data, dict):
            # Check if it looks like an article or a container
            if 'processed_articles' in data:
                articles.extend(data['processed_articles'])
            else:
                articles.append(data)
                
    return articles

def inspect_predictions(gcs_uris):
    """Downloads and inspects the specified GCS JSONL files."""
    
    # Initialize client (assumes credentials are set in environment)
    try:
        client = storage.Client()
    except Exception as e:
        print(f"Error initializing Storage Client: {e}")
        return

    for uri in gcs_uris:
        print(f"\n{'='*80}")
        print(f"INSPECTING: {uri}")
        print(f"{'='*80}")
        
        bucket_name, blob_name = parse_gcs_uri(uri)
        
        if not bucket_name or not blob_name:
            print(f"❌ Invalid URI format: {uri}")
            continue
            
        # Handle URL encoding (e.g. %3A -> :)
        blob_name = unquote(blob_name)
        
        print(f"Bucket: {bucket_name}")
        print(f"Blob:   {blob_name}")
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        try:
            if not blob.exists():
                print(f"❌ Blob does not exist.")
                continue
                
            content = blob.download_as_text()
            print(f"✅ Downloaded {len(content)} bytes.")
            
        except Exception as e:
            print(f"❌ Error downloading blob: {e}")
            continue
            
        lines = content.splitlines()
        print(f"Found {len(lines)} lines in file.\n")
        
        total_articles_found = 0
        
        for i, line in enumerate(lines):
            if not line.strip():
                continue
                
            try:
                data = json.loads(line)
                articles = extract_articles_from_entry(data)
                
                if not articles:
                    print(f"Line {i+1}: No articles extracted.")
                    continue
                    
                for article in articles:
                    if not isinstance(article, dict):
                        continue
                        
                    total_articles_found += 1
                    
                    # Extract fields
                    url = article.get('original_url') or article.get('url') or article.get('link')
                    
                    # Try to find content in various fields
                    content_text = (
                        article.get('content') or 
                        article.get('full_text') or 
                        article.get('text') or 
                        article.get('body') or
                        article.get('summary') # Fallback
                    )
                    
                    print(f"--- Article {total_articles_found} ---")
                    print(f"URL: {url}")
                    
                    if content_text:
                        # preview = str(content_text)[:200].replace('\n', ' ')
                        # print(f"Content ({len(str(content_text))} chars): {preview}...")
                        print(f"Content ({len(str(content_text))} chars): {content_text}")
                    else:
                        print("Content: [MISSING]")
                        # Print keys to help debug
                        print(f"Available keys: {list(article.keys())}")
                    print("")

            except json.JSONDecodeError:
                print(f"Line {i+1}: ❌ Invalid JSON")
            except Exception as e:
                print(f"Line {i+1}: ❌ Error processing: {e}")

if __name__ == "__main__":
    # URIs provided by user
    target_uris = [
        "https://storage.cloud.google.com/aisports-scraping/news_data/batch_processing/eu/2025-11/2025-11-21/run_23-36-18/stage1_extraction/results/prediction-model-2025-11-21T23%3A36%3A57.561338Z/predictions.jsonl",
        "https://storage.cloud.google.com/aisports-scraping/news_data/batch_processing/tr/2025-11/2025-11-21/run_23-35-53/stage2_deduplication/results/prediction-model-2025-11-21T23%3A42%3A52.622923Z/predictions.jsonl"
    ]
    
    inspect_predictions(target_uris)
