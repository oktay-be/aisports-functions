#!/usr/bin/env python3
"""
Analyze the result_merger_function to understand its purpose and benefit.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

def load_jsonl(filepath: str) -> List[dict]:
    """Load JSONL file and return list of predictions."""
    predictions = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                predictions.append(json.loads(line))
    return predictions

def extract_source_from_uri(uri: str) -> str:
    """Extract source domain from file URI."""
    parts = Path(uri).stem.replace('session_data_', '').split('_')
    # Remove timestamp parts (last 3 parts are typically date and time)
    if len(parts) > 3:
        return '_'.join(parts[:-3])
    return '_'.join(parts)

def analyze_stage1_predictions(predictions: List[dict]) -> Dict[str, Any]:
    """Analyze stage1 extraction predictions (with multiple candidates)."""
    analysis = {
        'total_predictions': len(predictions),
        'sources': {},
        'candidate_comparison': {},
        'overall_stats': {
            'total_candidates': 0,
            'total_articles_all_candidates': 0,
            'avg_candidates_per_source': 0,
            'avg_articles_per_candidate': 0
        }
    }

    for pred_idx, prediction in enumerate(predictions):
        try:
            # Extract source
            request = prediction.get('request', {})
            contents = request.get('contents', [{}])[0]
            parts = contents.get('parts', [])

            source_uri = None
            for part in parts:
                if 'fileData' in part and part['fileData']:
                    source_uri = part['fileData'].get('fileUri')
                    break

            if not source_uri:
                continue

            source_name = extract_source_from_uri(source_uri)

            # Get candidates
            candidates = prediction.get('response', {}).get('candidates', [])

            if not candidates:
                continue

            # Initialize source analysis
            if source_name not in analysis['sources']:
                analysis['sources'][source_name] = {
                    'source_uri': source_uri,
                    'num_candidates': len(candidates),
                    'candidates': []
                }

            # Analyze each candidate
            candidate_articles = []
            for idx, candidate in enumerate(candidates):
                try:
                    response_text = candidate['content']['parts'][0]['text']
                    response_data = json.loads(response_text)

                    articles = response_data.get('processed_articles', [])
                    processing_summary = response_data.get('processing_summary', {})

                    candidate_info = {
                        'index': idx,
                        'num_articles': len(articles),
                        'avg_logprobs': candidate.get('avgLogprobs', 0),
                        'finish_reason': candidate.get('finishReason', 'UNKNOWN'),
                        'article_ids': [a.get('article_id', '') for a in articles],
                        'article_titles': [a.get('title', '')[:60] for a in articles],
                        'article_urls': [a.get('original_url', '') for a in articles],
                        'processing_summary': processing_summary,
                        'articles': articles
                    }

                    candidate_articles.append(candidate_info)
                    analysis['overall_stats']['total_candidates'] += 1
                    analysis['overall_stats']['total_articles_all_candidates'] += len(articles)

                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Error parsing candidate {idx} for {source_name}: {e}")
                    continue

            analysis['sources'][source_name]['candidates'] = candidate_articles

            # Compare candidates for this source
            if len(candidate_articles) > 1:
                comparison = compare_candidates(candidate_articles, source_name)
                analysis['candidate_comparison'][source_name] = comparison

        except Exception as e:
            print(f"Error processing prediction {pred_idx}: {e}")
            continue

    # Calculate averages
    if analysis['sources']:
        analysis['overall_stats']['avg_candidates_per_source'] = (
            analysis['overall_stats']['total_candidates'] / len(analysis['sources'])
        )

    if analysis['overall_stats']['total_candidates'] > 0:
        analysis['overall_stats']['avg_articles_per_candidate'] = (
            analysis['overall_stats']['total_articles_all_candidates'] /
            analysis['overall_stats']['total_candidates']
        )

    return analysis

def compare_candidates(candidates: List[dict], source_name: str) -> Dict[str, Any]:
    """Compare multiple candidates to find differences."""
    comparison = {
        'source': source_name,
        'num_candidates': len(candidates),
        'article_counts': [c['num_articles'] for c in candidates],
        'common_articles': set(),
        'unique_to_candidates': {},
        'differences': []
    }

    # Find common articles (by URL)
    all_url_sets = []
    for idx, candidate in enumerate(candidates):
        url_set = set(candidate['article_urls'])
        all_url_sets.append((idx, url_set))

    if len(all_url_sets) >= 2:
        # Find intersection
        common_urls = all_url_sets[0][1]
        for idx, url_set in all_url_sets[1:]:
            common_urls = common_urls & url_set

        comparison['common_articles'] = list(common_urls)  # Convert set to list
        comparison['num_common_articles'] = len(common_urls)

        # Find unique articles per candidate
        for idx, url_set in all_url_sets:
            unique_urls = url_set - common_urls
            comparison['unique_to_candidates'][f'candidate_{idx}'] = {
                'count': len(unique_urls),
                'urls': list(unique_urls),
                'titles': []
            }

            # Find titles for unique URLs
            candidate = candidates[idx]
            for i, url in enumerate(candidate['article_urls']):
                if url in unique_urls:
                    comparison['unique_to_candidates'][f'candidate_{idx}']['titles'].append(
                        candidate['article_titles'][i]
                    )

    # Calculate difference metrics
    max_articles = max(comparison['article_counts'])
    min_articles = min(comparison['article_counts'])
    comparison['article_count_range'] = max_articles - min_articles
    comparison['article_count_variance_pct'] = (
        (max_articles - min_articles) / max_articles * 100 if max_articles > 0 else 0
    )

    return comparison

def analyze_stage2_predictions(predictions: List[dict]) -> Dict[str, Any]:
    """Analyze stage2 deduplication predictions (single candidate after merge)."""
    analysis = {
        'total_predictions': len(predictions),
        'sources': {},
        'overall_stats': {
            'total_deduplicated_articles': 0,
            'avg_articles_per_source': 0
        }
    }

    for pred_idx, prediction in enumerate(predictions):
        try:
            # Extract source
            request = prediction.get('request', {})
            contents = request.get('contents', [{}])[0]
            parts = contents.get('parts', [])

            source_uri = None
            for part in parts:
                if 'fileData' in part and part['fileData']:
                    source_uri = part['fileData'].get('fileUri')
                    break

            if not source_uri:
                continue

            # Extract source from merged filename
            source_name = Path(source_uri).stem.replace('merged_session_data_', '').replace('_', '.')

            # Get single candidate (after merge)
            candidates = prediction.get('response', {}).get('candidates', [])

            if not candidates:
                continue

            candidate = candidates[0]  # Should only be 1 candidate

            try:
                response_text = candidate['content']['parts'][0]['text']
                response_data = json.loads(response_text)

                articles = response_data.get('processed_articles', [])
                processing_summary = response_data.get('processing_summary', {})

                analysis['sources'][source_name] = {
                    'source_uri': source_uri,
                    'num_articles_after_dedup': len(articles),
                    'processing_summary': processing_summary,
                    'article_ids': [a.get('article_id', '') for a in articles],
                    'article_urls': [a.get('original_url', '') for a in articles]
                }

                analysis['overall_stats']['total_deduplicated_articles'] += len(articles)

            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing candidate for {source_name}: {e}")
                continue

        except Exception as e:
            print(f"Error processing prediction {pred_idx}: {e}")
            continue

    # Calculate average
    if analysis['sources']:
        analysis['overall_stats']['avg_articles_per_source'] = (
            analysis['overall_stats']['total_deduplicated_articles'] / len(analysis['sources'])
        )

    return analysis

def compare_stages(stage1_analysis: Dict, stage2_analysis: Dict) -> Dict[str, Any]:
    """Compare stage1 (before merge) and stage2 (after merge) to see impact."""
    comparison = {
        'sources_compared': {},
        'summary': {}
    }

    # Debug: print source names
    print("\nDEBUG - Stage1 sources:")
    for name in stage1_analysis['sources'].keys():
        print(f"  - {name}")
    print("\nDEBUG - Stage2 sources:")
    for name in stage2_analysis['sources'].keys():
        print(f"  - {name}")
    print()

    for source_name, stage1_data in stage1_analysis['sources'].items():
        # Find matching source in stage2
        # Stage1 source names have underscores, stage2 have dots
        stage1_normalized = source_name.replace('_', '.')

        stage2_source = None
        for s2_name, s2_data in stage2_analysis['sources'].items():
            # Try exact match first
            if stage1_normalized == s2_name:
                stage2_source = s2_data
                break
            # Try partial match (source domain might be slightly different)
            if stage1_normalized in s2_name or s2_name in stage1_normalized:
                stage2_source = s2_data
                break

        if not stage2_source:
            continue

        # Compare article counts
        stage1_candidates = stage1_data['candidates']
        total_before_merge = sum(c['num_articles'] for c in stage1_candidates)
        after_dedup = stage2_source['num_articles_after_dedup']

        comparison['sources_compared'][source_name] = {
            'stage1_candidates': len(stage1_candidates),
            'stage1_total_articles': total_before_merge,
            'stage1_articles_per_candidate': [c['num_articles'] for c in stage1_candidates],
            'stage2_articles_after_merge_and_dedup': after_dedup,
            'articles_reduced': total_before_merge - after_dedup,
            'reduction_pct': ((total_before_merge - after_dedup) / total_before_merge * 100)
                            if total_before_merge > 0 else 0
        }

    # Calculate overall summary
    total_stage1 = sum(d['stage1_total_articles'] for d in comparison['sources_compared'].values())
    total_stage2 = sum(d['stage2_articles_after_merge_and_dedup'] for d in comparison['sources_compared'].values())

    comparison['summary'] = {
        'total_sources_compared': len(comparison['sources_compared']),
        'total_articles_before_merge': total_stage1,
        'total_articles_after_merge_and_dedup': total_stage2,
        'total_reduction': total_stage1 - total_stage2,
        'overall_reduction_pct': ((total_stage1 - total_stage2) / total_stage1 * 100) if total_stage1 > 0 else 0
    }

    return comparison

def main():
    stage1_file = '/tmp/stage1_predictions.jsonl'
    stage2_file = '/tmp/stage2_predictions.jsonl'

    print("=" * 80)
    print("RESULT MERGER FUNCTION INVESTIGATION")
    print("=" * 80)
    print()

    # Load predictions
    print("Loading prediction files...")
    stage1_predictions = load_jsonl(stage1_file)
    stage2_predictions = load_jsonl(stage2_file)
    print(f"  Stage1 (extraction): {len(stage1_predictions)} predictions")
    print(f"  Stage2 (deduplication): {len(stage2_predictions)} predictions")
    print()

    # Analyze stage1
    print("Analyzing Stage 1 (Extraction with multiple candidates)...")
    stage1_analysis = analyze_stage1_predictions(stage1_predictions)
    print(f"  Sources: {len(stage1_analysis['sources'])}")
    print(f"  Total candidates: {stage1_analysis['overall_stats']['total_candidates']}")
    print(f"  Total articles (all candidates): {stage1_analysis['overall_stats']['total_articles_all_candidates']}")
    print(f"  Avg candidates per source: {stage1_analysis['overall_stats']['avg_candidates_per_source']:.1f}")
    print(f"  Avg articles per candidate: {stage1_analysis['overall_stats']['avg_articles_per_candidate']:.1f}")
    print()

    # Analyze stage2
    print("Analyzing Stage 2 (Deduplication after merge)...")
    stage2_analysis = analyze_stage2_predictions(stage2_predictions)
    print(f"  Sources: {len(stage2_analysis['sources'])}")
    print(f"  Total deduplicated articles: {stage2_analysis['overall_stats']['total_deduplicated_articles']}")
    print(f"  Avg articles per source: {stage2_analysis['overall_stats']['avg_articles_per_source']:.1f}")
    print()

    # Compare stages
    print("Comparing Stage 1 vs Stage 2...")
    stage_comparison = compare_stages(stage1_analysis, stage2_analysis)
    print(f"  Sources compared: {stage_comparison['summary']['total_sources_compared']}")
    print(f"  Before merge: {stage_comparison['summary']['total_articles_before_merge']} articles")
    print(f"  After merge+dedup: {stage_comparison['summary']['total_articles_after_merge_and_dedup']} articles")
    print(f"  Reduction: {stage_comparison['summary']['total_reduction']} articles ({stage_comparison['summary']['overall_reduction_pct']:.1f}%)")
    print()

    # Save full analysis
    output_file = '/home/neo/aisports/aisports-functions/result_merger_function_investigation/analysis_results.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'stage1_analysis': stage1_analysis,
            'stage2_analysis': stage2_analysis,
            'stage_comparison': stage_comparison
        }, f, indent=2, ensure_ascii=False)

    print(f"Full analysis saved to: {output_file}")
    print()

    # Generate detailed report
    generate_report(stage1_analysis, stage2_analysis, stage_comparison)

def generate_report(stage1_analysis, stage2_analysis, stage_comparison):
    """Generate detailed markdown report."""
    report_file = '/home/neo/aisports/aisports-functions/result_merger_function_investigation/INVESTIGATION_REPORT.md'

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# Result Merger Function Investigation Report\n\n")
        f.write("## Executive Summary\n\n")

        # Purpose
        f.write("### What is result_merger_function?\n\n")
        f.write("The `result_merger_function` is a critical component in the batch processing pipeline that:\n\n")
        f.write("1. **Merges Multiple Candidates**: Takes predictions from Stage 1 (extraction) where each source has 2 candidates (different AI responses)\n")
        f.write("2. **Combines Articles**: Merges all articles from both candidates into a single dataset per source\n")
        f.write("3. **Triggers Deduplication**: Creates and submits a Stage 2 batch job to deduplicate the merged articles\n")
        f.write("4. **Tracks Metadata**: Adds merge metadata to each article to track which candidate it came from\n\n")

        # Benefits
        f.write("### Benefits\n\n")

        summary = stage_comparison['summary']
        reduction_pct = summary['overall_reduction_pct']

        f.write(f"**Quality Improvement through Diversity**:\n")
        f.write(f"- Stage 1 uses 2 candidates per source (different AI responses for quality)\n")
        f.write(f"- Each candidate might extract different articles or miss some\n")
        f.write(f"- Merging ensures we capture the maximum number of articles from both attempts\n\n")

        f.write(f"**Data Consolidation**:\n")
        f.write(f"- Before merge: {summary['total_articles_before_merge']} articles across {summary['total_sources_compared']} sources\n")
        f.write(f"- After merge+dedup: {summary['total_articles_after_merge_and_dedup']} articles\n")
        f.write(f"- Reduction: {summary['total_reduction']} articles ({reduction_pct:.1f}%) removed as duplicates\n\n")

        # Per-source analysis
        f.write("## Per-Source Analysis\n\n")
        f.write("| Source | Candidates | Before Merge | After Merge+Dedup | Reduction | Reduction % |\n")
        f.write("|--------|-----------|--------------|-------------------|-----------|-------------|\n")

        for source_name, data in sorted(stage_comparison['sources_compared'].items()):
            f.write(f"| {source_name} | {data['stage1_candidates']} | ")
            f.write(f"{data['stage1_total_articles']} | ")
            f.write(f"{data['stage2_articles_after_merge_and_dedup']} | ")
            f.write(f"{data['articles_reduced']} | ")
            f.write(f"{data['reduction_pct']:.1f}% |\n")

        f.write("\n")

        # Candidate comparison
        f.write("## Candidate Comparison (Stage 1)\n\n")
        f.write("Comparison of articles extracted by different candidates for the same source:\n\n")

        for source_name, comparison in stage1_analysis['candidate_comparison'].items():
            f.write(f"### {source_name}\n\n")
            f.write(f"- **Number of candidates**: {comparison['num_candidates']}\n")
            f.write(f"- **Article counts**: {comparison['article_counts']}\n")
            f.write(f"- **Common articles**: {comparison['num_common_articles']}\n")
            f.write(f"- **Variance**: {comparison['article_count_range']} articles ({comparison['article_count_variance_pct']:.1f}%)\n\n")

            if comparison['unique_to_candidates']:
                f.write("**Unique articles per candidate**:\n\n")
                for cand_name, unique_data in comparison['unique_to_candidates'].items():
                    f.write(f"- **{cand_name}**: {unique_data['count']} unique articles\n")
                    if unique_data['titles']:
                        f.write("  - Examples:\n")
                        for title in unique_data['titles'][:3]:
                            f.write(f"    - {title}...\n")
                f.write("\n")

        # Necessity Analysis
        f.write("## Necessity Analysis\n\n")
        f.write("### Is result_merger_function necessary?\n\n")

        # Calculate how many sources have candidate differences
        sources_with_differences = sum(
            1 for comp in stage1_analysis['candidate_comparison'].values()
            if comp.get('article_count_range', 0) > 0
        )

        f.write(f"**YES** - The merger function is necessary for:\n\n")
        f.write(f"1. **Maximizing Article Coverage**: {sources_with_differences}/{len(stage1_analysis['candidate_comparison'])} sources ")
        f.write(f"had different article counts between candidates\n")
        f.write(f"2. **Quality Improvement**: Using 2 candidates catches articles that one might miss\n")
        f.write(f"3. **Deduplication**: The {reduction_pct:.1f}% reduction shows significant duplicate removal\n")
        f.write(f"4. **Pipeline Automation**: Automatically triggers Stage 2 deduplication\n\n")

        f.write("### Alternative Approach\n\n")
        f.write("**Could we use only 1 candidate in Stage 1?**\n\n")
        f.write("Pros:\n")
        f.write("- Simpler pipeline (no merge needed)\n")
        f.write("- Lower cost (half the API calls)\n")
        f.write("- Faster processing\n\n")

        f.write("Cons:\n")
        f.write("- Might miss articles that only one candidate extracts\n")
        f.write("- Lower quality due to lack of redundancy\n")
        f.write("- Single point of failure (if one candidate fails, lose all data)\n\n")

        f.write("**Recommendation**: Keep result_merger_function for quality, but could consider:\n")
        f.write("- Reducing to 1 candidate if cost is a concern\n")
        f.write("- Using 3 candidates for even higher quality (but more expensive)\n\n")

    print(f"Detailed report saved to: {report_file}")

if __name__ == '__main__':
    main()
