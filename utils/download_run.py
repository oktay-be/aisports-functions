import os
import sys
import argparse
import subprocess
from pathlib import Path

def download_run(gcs_path, local_base_path, skip_existing=False):
    """
    Downloads a GCS folder to a local directory using gcloud storage (faster than gsutil).
    
    Args:
        gcs_path: Full GCS path (e.g., aisports-scraping/ingestion/2025-12-20/15-24-07)
                  or gs:// URI
        local_base_path: Local directory to download to
        skip_existing: Skip files that already exist locally
    """
    
    # Parse GCS path
    if not gcs_path.startswith('gs://'):
        gcs_path = f"gs://{gcs_path}"
    
    # Remove trailing slash if present
    gcs_path = gcs_path.rstrip('/')
    
    # Extract run ID for local folder name
    # Assuming format .../YYYY-MM-DD/HH-MM-SS
    run_id = gcs_path.split('/')[-1]
    
    local_run_dir = os.path.join(local_base_path, run_id)
    os.makedirs(local_run_dir, exist_ok=True)
    
    print(f"Downloading from {gcs_path}")
    print(f"To local: {local_run_dir}")
    
    # Use gcloud storage cp (faster than gsutil)
    # -r for recursive
    # --no-clobber to skip existing files (optional)
    command = [
        "gcloud", "storage", "cp",
        "-r",
        f"{gcs_path}/*",
        local_run_dir
    ]
    
    if skip_existing:
        command.insert(4, "--no-clobber")
        print("Skipping existing files...")
    
    try:
        subprocess.check_call(command)
        print(f"Download completed successfully to {local_run_dir}")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading files: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download GCS run folder.')
    parser.add_argument('gcs_path', help='GCS path (e.g., aisports-scraping/ingestion/2025-12-20/15-24-07)')
    parser.add_argument('--local_dir', default='/home/neo/aisports/pipeline_runs', help='Local base directory')
    parser.add_argument('--skip-existing', '-s', action='store_true', help='Skip files that already exist')
    
    args = parser.parse_args()
    
    download_run(args.gcs_path, args.local_dir, args.skip_existing)
