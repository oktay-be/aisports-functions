import subprocess
import sys

def get_gsutil_output(path):
    try:
        # Run gsutil ls -r
        result = subprocess.run(['gsutil', 'ls', '-r', path], capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            print(f"Error running gsutil: {result.stderr}")
            return []
        return result.stdout.splitlines()
    except FileNotFoundError:
        print("gsutil not found. Please ensure Google Cloud SDK is installed and in your PATH.")
        return []

def build_tree(paths, root_prefix):
    tree = {}
    for path in paths:
        # Remove the bucket prefix to get relative path
        if path.endswith(':'): continue # Skip directory markers from gsutil
        
        rel_path = path.replace(root_prefix, '').strip('/')
        if not rel_path: continue
        
        parts = rel_path.split('/')
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree

def print_tree(tree, indent=''):
    # Sort keys to put folders first or alphabetical
    items = sorted(tree.keys())
    for i, item in enumerate(items):
        is_last = (i == len(items) - 1)
        prefix = '└── ' if is_last else '├── '
        
        print(f"{indent}{prefix}{item}")
        
        next_indent = indent + ('    ' if is_last else '│   ')
        print_tree(tree[item], next_indent)

def main():
    bucket_path = "gs://aisports-scraping/news_data"
    print(f"Fetching file list from {bucket_path}...")
    
    paths = get_gsutil_output(bucket_path)
    if not paths:
        print("No files found or error occurred.")
        return

    print(f"\nFolder Structure for {bucket_path}:\n")
    # We pass the root prefix including the trailing slash to strip it correctly
    root_tree = build_tree(paths, bucket_path + '/')
    print_tree(root_tree)

if __name__ == "__main__":
    main()
