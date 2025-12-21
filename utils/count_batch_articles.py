#!/usr/bin/env python3
"""
Count articles in batch input and output files.

Usage:
    python count_batch_articles.py <run_folder>
    python count_batch_articles.py /home/neo/aisports/pipeline_runs/15-17-02

This script compares:
- Input files: batch_enrichment/{source_type}/{branch_type}/input/batch_*.json
- Output files: batch_enrichment/{source_type}/{branch_type}/prediction-*/predictions.jsonl
"""

import os
import sys
import glob
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


def count_body_in_json(file_path: str) -> int:
    """Count articles in input JSON file by counting 'body' field occurrences."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count "body": occurrences (the field name)
        # Using regex to match "body": followed by content
        count = len(re.findall(r'"body"\s*:\s*"', content))
        return count
    except Exception as e:
        print(f"  Error reading {file_path}: {e}")
        return 0


def count_article_ids_in_jsonl(file_path: str) -> int:
    """
    Count articles in output JSONL prediction file by counting 'article_id' occurrences.
    
    Each article_id is unique - count all occurrences.
    Matches pattern: \"article_id\": \"<hex_id>\"
    
    Note: The JSONL contains escaped JSON, so article_id appears as \"article_id\"
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Match escaped article_id with hex value: \"article_id\": \"2d2a2657bb70df6f\"
        # Pattern: \"article_id\": \"<16 hex chars>\"
        escaped_count = len(re.findall(r'\\"article_id\\"\s*:\s*\\"[a-f0-9]{16}\\"', content))
        
        return escaped_count
    except Exception as e:
        print(f"  Error reading {file_path}: {e}")
        return 0


def analyze_batch_folder(run_folder: str) -> Dict[str, Dict]:
    """Analyze all batch input/output files in a run folder."""
    
    results = {}
    batch_base = os.path.join(run_folder, "batch_enrichment")
    
    if not os.path.exists(batch_base):
        print(f"No batch_enrichment folder found in {run_folder}")
        return results
    
    # Find all source types (complete, scraped_incomplete)
    source_types = [d for d in os.listdir(batch_base) 
                    if os.path.isdir(os.path.join(batch_base, d))]
    
    for source_type in source_types:
        source_path = os.path.join(batch_base, source_type)
        
        # Find all branch types (merged, singleton)
        branch_types = [d for d in os.listdir(source_path)
                       if os.path.isdir(os.path.join(source_path, d))]
        
        for branch_type in branch_types:
            branch_path = os.path.join(source_path, branch_type)
            key = f"{source_type}/{branch_type}"
            
            results[key] = {
                "input_files": [],
                "output_files": [],
                "input_total": 0,
                "output_total": 0
            }
            
            # Count input files
            input_path = os.path.join(branch_path, "input")
            if os.path.exists(input_path):
                input_files = sorted(glob.glob(os.path.join(input_path, "batch_*.json")))
                
                for f in input_files:
                    count = count_body_in_json(f)
                    results[key]["input_files"].append({
                        "file": os.path.basename(f),
                        "count": count
                    })
                    results[key]["input_total"] += count
            
            # Count output files (prediction folders)
            prediction_folders = glob.glob(os.path.join(branch_path, "prediction-*"))
            
            for pred_folder in prediction_folders:
                jsonl_file = os.path.join(pred_folder, "predictions.jsonl")
                if os.path.exists(jsonl_file):
                    count = count_article_ids_in_jsonl(jsonl_file)
                    results[key]["output_files"].append({
                        "file": os.path.basename(pred_folder),
                        "count": count
                    })
                    results[key]["output_total"] += count
    
    return results


def print_results(results: Dict[str, Dict], run_folder: str):
    """Print analysis results in a formatted table."""
    
    print(f"\n{'='*80}")
    print(f"BATCH ARTICLE COUNT ANALYSIS")
    print(f"Run folder: {run_folder}")
    print(f"{'='*80}\n")
    
    total_input = 0
    total_output = 0
    
    for key, data in sorted(results.items()):
        print(f"\n📁 {key}")
        print(f"   {'─'*60}")
        
        # Input files
        print(f"   INPUT FILES (counting 'body' occurrences):")
        for f in data["input_files"]:
            print(f"      {f['file']}: {f['count']} articles")
        print(f"      ─────────────────────────────")
        print(f"      SUBTOTAL: {data['input_total']} articles")
        
        # Output files
        print(f"\n   OUTPUT FILES (counting 'article_id'):")
        for f in data["output_files"]:
            print(f"      {f['file']}: {f['count']} articles")
        print(f"      ─────────────────────────────")
        print(f"      SUBTOTAL: {data['output_total']} articles")
        
        # Comparison
        diff = data["input_total"] - data["output_total"]
        status = "✅ MATCH" if diff == 0 else f"⚠️  DIFF: {diff}"
        print(f"\n   {status}")
        
        total_input += data["input_total"]
        total_output += data["output_total"]
    
    # Grand total
    print(f"\n{'='*80}")
    print(f"GRAND TOTAL")
    print(f"{'='*80}")
    print(f"   Total Input Articles:  {total_input}")
    print(f"   Total Output Articles: {total_output}")
    diff = total_input - total_output
    status = "✅ ALL MATCH" if diff == 0 else f"⚠️  TOTAL DIFF: {diff}"
    print(f"   {status}")
    print(f"{'='*80}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python count_batch_articles.py <run_folder>")
        print("Example: python count_batch_articles.py /home/neo/aisports/pipeline_runs/15-17-02")
        sys.exit(1)
    
    run_folder = sys.argv[1]
    
    if not os.path.exists(run_folder):
        print(f"Error: Folder not found: {run_folder}")
        sys.exit(1)
    
    results = analyze_batch_folder(run_folder)
    
    if not results:
        print("No batch data found.")
        sys.exit(1)
    
    print_results(results, run_folder)


if __name__ == "__main__":
    main()
