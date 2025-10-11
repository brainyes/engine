"""
Download OASIS Dataset for Population Normative Data

This function downloads brain MRI scans from the OASIS (Open Access Series of
Imaging Studies) dataset to build population norms.

Supported datasets:
- OASIS-1: Cross-sectional dataset with ~400 subjects (ages 18-96)
- OASIS-3: Longitudinal dataset with ~1000+ subjects

Data sources:
- OASIS-1: https://www.oasis-brains.org/
- OASIS-3: https://www.oasis-brains.org/

The function downloads:
1. T1-weighted structural MRI scans (NIFTI format)
2. Demographic data (age, sex, CDR scores, diagnosis)
3. Scan metadata (scanner parameters, quality metrics)
"""

import os
import argparse
import requests
import pandas as pd
import tarfile
from typing import Dict, List, Optional

from utilities.options import dataset_dir

# Try to import boto3 for S3 support (optional)
try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    print("⚠️  Warning: boto3 not installed. S3 caching will be disabled.")
    print("   Install with: pip install boto3")

FUNCTION_NAME = "download_oasis_dataset"

# OASIS dataset information
OASIS_DATASETS = {
    'oasis-1': {
        'name': 'OASIS-1 Cross-Sectional',
        'description': 'Cross-sectional MRI data from 416 subjects aged 18-96',
        'url_base': 'https://download.nrg.wustl.edu/data',
        'subjects': 416,
        'age_range': '18-96'
    },
    'oasis-3': {
        'name': 'OASIS-3 Longitudinal',
        'description': 'Longitudinal neuroimaging, clinical, and biomarker data from 1000+ subjects',
        'url_base': 'https://download.nrg.wustl.edu/data',
        'subjects': 1000,
        'age_range': '42-95'
    }
}


def download_file(url: str, destination: str, show_progress: bool = True) -> bool:
    """
    Download a file from URL to destination with progress tracking

    Args:
        url: Source URL
        destination: Local file path
        show_progress: Whether to show download progress

    Returns:
        True if successful, False otherwise
    """
    try:
        # Use browser-like headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

        response = requests.get(url, stream=True, headers=headers, timeout=60)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        os.makedirs(os.path.dirname(destination), exist_ok=True)

        with open(destination, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if show_progress:
                            progress = (downloaded / total_size) * 100
                            print(f'\r  Progress: {progress:.1f}%', end='', flush=True)

                if show_progress:
                    print()  # New line after progress

        return True

    except requests.exceptions.RequestException as e:
        print(f"  ❌ Download failed: {str(e)}")
        return False


def download_oasis_1_manifest(output_dir: str) -> str:
    """
    Download OASIS-1 manifest file with subject list

    Downloads the official OASIS cross-sectional Excel file from WUSTL website.

    Returns:
        Path to manifest CSV (converted from Excel), or None if download fails
    """
    # Download as Excel, convert to CSV
    manifest_xlsx_path = os.path.join(output_dir, "oasis_cross-sectional.xlsx")
    manifest_csv_path = os.path.join(output_dir, "oasis-1-manifest.csv")

    print("📥 Downloading OASIS-1 manifest...")

    # Check if already converted to CSV
    if os.path.exists(manifest_csv_path):
        print(f"  ✓ Manifest already exists: {manifest_csv_path}")
        return manifest_csv_path

    # Download Excel file from official OASIS website
    oasis_url = "https://sites.wustl.edu/oasisbrains/files/2024/04/oasis_cross-sectional-5708aa0a98d82080.xlsx"

    print(f"  Downloading from: {oasis_url}")
    if not download_file(oasis_url, manifest_xlsx_path, show_progress=True):
        print(f"  ❌ Could not download manifest")
        print(f"  Please download manually from: https://www.oasis-brains.org/")
        return None

    # Convert Excel to CSV
    print(f"  📄 Converting Excel to CSV...")
    try:
        df = pd.read_excel(manifest_xlsx_path)
        df.to_csv(manifest_csv_path, index=False)
        print(f"  ✓ Manifest downloaded and converted: {manifest_csv_path}")
        return manifest_csv_path
    except Exception as e:
        print(f"  ❌ Error converting Excel to CSV: {str(e)}")
        print(f"  You may need to install: pip install openpyxl")
        return None


def parse_oasis_1_manifest(manifest_path: str, max_subjects: int = None) -> pd.DataFrame:
    """
    Parse OASIS-1 manifest and filter subjects

    Args:
        manifest_path: Path to manifest CSV
        max_subjects: Maximum number of subjects to include (None = all)

    Returns:
        DataFrame with subject information
    """
    df = pd.read_csv(manifest_path)

    # Filter for subjects with complete data
    # Typically we want subjects with:
    # - Age information
    # - Sex information
    # - CDR scores (for cognitive status)
    df = df.dropna(subset=['Age', 'M/F'])

    # Sort by age to get good distribution
    df = df.sort_values('Age')

    if max_subjects:
        # Sample evenly across age range
        step = max(1, len(df) // max_subjects)
        df = df.iloc[::step][:max_subjects]

    return df


# ============================================================================
# S3 Caching Support
# ============================================================================

def get_s3_bucket_name() -> Optional[str]:
    """
    Get S3 bucket name from environment variable

    Returns:
        Bucket name or None if not configured
    """
    return os.environ.get('POPULATION_DATASET_BUCKET')


def check_s3_disc_exists(bucket_name: str, disc_num: int) -> bool:
    """
    Check if a disc archive exists in S3

    Args:
        bucket_name: S3 bucket name
        disc_num: Disc number (1-12)

    Returns:
        True if exists, False otherwise
    """
    if not S3_AVAILABLE:
        return False

    try:
        s3_client = boto3.client('s3')
        s3_key = f"oasis-1/raw/oasis_cross-sectional_disc{disc_num}.tar.gz"

        s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        return True
    except ClientError:
        return False
    except Exception as e:
        print(f"  ⚠️  S3 check error: {str(e)}")
        return False


def download_disc_from_s3(bucket_name: str, disc_num: int, destination: str) -> bool:
    """
    Download a disc archive from S3

    Args:
        bucket_name: S3 bucket name
        disc_num: Disc number (1-12)
        destination: Local file path to save

    Returns:
        True if successful, False otherwise
    """
    if not S3_AVAILABLE:
        return False

    try:
        s3_client = boto3.client('s3')
        s3_key = f"oasis-1/raw/oasis_cross-sectional_disc{disc_num}.tar.gz"

        # Get file size for progress tracking
        response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        total_size = response['ContentLength']

        os.makedirs(os.path.dirname(destination), exist_ok=True)

        # Download with progress
        downloaded = 0
        with open(destination, 'wb') as f:
            def progress_callback(bytes_amount):
                nonlocal downloaded
                downloaded += bytes_amount
                progress = (downloaded / total_size) * 100
                print(f'\r  S3 Progress: {progress:.1f}%', end='', flush=True)

            s3_client.download_fileobj(
                bucket_name,
                s3_key,
                f,
                Callback=progress_callback
            )

        print()  # New line after progress
        return True

    except ClientError as e:
        print(f"  ❌ S3 download failed: {str(e)}")
        return False
    except Exception as e:
        print(f"  ❌ S3 download error: {str(e)}")
        return False


def upload_disc_to_s3(bucket_name: str, disc_num: int, source_file: str) -> bool:
    """
    Upload a disc archive to S3 after downloading from OASIS

    Args:
        bucket_name: S3 bucket name
        disc_num: Disc number (1-12)
        source_file: Local file path to upload

    Returns:
        True if successful, False otherwise
    """
    if not S3_AVAILABLE:
        return False

    try:
        s3_client = boto3.client('s3')
        s3_key = f"oasis-1/raw/oasis_cross-sectional_disc{disc_num}.tar.gz"

        # Get file size for progress tracking
        file_size = os.path.getsize(source_file)

        print(f"  ☁️  Uploading disc {disc_num} to S3 for future use...")

        # Upload with progress
        uploaded = 0
        def progress_callback(bytes_amount):
            nonlocal uploaded
            uploaded += bytes_amount
            progress = (uploaded / file_size) * 100
            print(f'\r  Upload Progress: {progress:.1f}%', end='', flush=True)

        s3_client.upload_file(
            source_file,
            bucket_name,
            s3_key,
            Callback=progress_callback
        )

        print()  # New line after progress
        print(f"  ✓ Uploaded to S3: s3://{bucket_name}/{s3_key}")
        return True

    except ClientError as e:
        print(f"  ⚠️  S3 upload failed: {str(e)}")
        return False
    except Exception as e:
        print(f"  ⚠️  S3 upload error: {str(e)}")
        return False


def download_and_extract_oasis_disc(disc_num: int, output_dir: str, skip_existing: bool = True) -> bool:
    """
    Download and extract a single OASIS disc archive

    Uses S3 caching for faster downloads when available:
    1. Check if already extracted locally
    2. Try downloading from S3 (fast)
    3. If not in S3, download from OASIS source (slow)
    4. Upload to S3 after downloading from source

    Args:
        disc_num: Disc number (1-12)
        output_dir: Directory to save extracted files
        skip_existing: Skip if already extracted

    Returns:
        True if successful, False otherwise
    """
    tar_path = os.path.join(output_dir, f"oasis_cross-sectional_disc{disc_num}.tar.gz")
    extract_dir = os.path.join(output_dir, "raw")
    marker_file = os.path.join(output_dir, f".disc{disc_num}_extracted")

    # Check if already extracted
    if skip_existing and os.path.exists(marker_file):
        print(f"  ⏭️  Disc {disc_num} already extracted, skipping...")
        return True

    # Get S3 bucket name (if configured)
    s3_bucket = get_s3_bucket_name()
    downloaded_from_s3 = False
    downloaded_from_source = False

    print(f"\n📥 Downloading disc {disc_num}/12 (~1.5 GB)...")

    # Try S3 first (faster)
    if s3_bucket and S3_AVAILABLE:
        print(f"  ☁️  Checking S3 bucket: {s3_bucket}")
        if check_s3_disc_exists(s3_bucket, disc_num):
            print(f"  ✓ Found in S3! Downloading from S3 (faster)...")
            if download_disc_from_s3(s3_bucket, disc_num, tar_path):
                downloaded_from_s3 = True
                print(f"  ✓ Downloaded from S3")
            else:
                print(f"  ⚠️  S3 download failed, falling back to source")
        else:
            print(f"  ℹ️  Not found in S3, downloading from source")

    # Fallback to OASIS source if S3 failed or unavailable
    if not downloaded_from_s3:
        disc_url = f"https://download.nrg.wustl.edu/data/oasis_cross-sectional_disc{disc_num}.tar.gz"
        print(f"  🌐 Downloading from OASIS source...")
        print(f"  URL: {disc_url}")

        if not download_file(disc_url, tar_path, show_progress=True):
            print(f"  ❌ Failed to download disc {disc_num}")
            return False

        downloaded_from_source = True
        print(f"  ✓ Downloaded from source")

        # Upload to S3 for future use (if configured)
        if s3_bucket and S3_AVAILABLE:
            upload_disc_to_s3(s3_bucket, disc_num, tar_path)

    # Extract tar.gz
    print(f"  📦 Extracting disc {disc_num}...")
    try:
        with tarfile.open(tar_path, 'r:gz') as tar:
            tar.extractall(path=extract_dir)

        # Create marker file to indicate this disc has been extracted
        open(marker_file, 'w').close()

        # Remove tar.gz to save space
        os.remove(tar_path)
        print(f"  ✅ Disc {disc_num} extracted successfully")
        return True

    except Exception as e:
        print(f"  ❌ Failed to extract disc {disc_num}: {str(e)}")
        return False


def download_oasis_1_raw_data(output_dir: str, required_subjects: List[str] = None, skip_existing: bool = True) -> Dict:
    """
    Download raw OASIS-1 MRI data from disc archives

    Args:
        output_dir: Directory to save files
        required_subjects: List of subject IDs to download (None = all)
        skip_existing: Skip already downloaded files

    Returns:
        Dictionary with download statistics
    """
    results = {
        'discs_downloaded': 0,
        'discs_failed': 0,
        'subjects_found': 0,
        'scans_found': []
    }

    print(f"\n{'='*60}")
    print("DOWNLOADING OASIS-1 RAW DATA")
    print(f"{'='*60}")
    print(f"Total discs: 12 (~18 GB total)")
    print(f"This will take some time...")
    print(f"{'='*60}\n")

    # Download all 12 discs
    for disc_num in range(1, 13):
        if download_and_extract_oasis_disc(disc_num, output_dir, skip_existing):
            results['discs_downloaded'] += 1
        else:
            results['discs_failed'] += 1
            print(f"⚠️  Warning: Failed to download disc {disc_num}, continuing with others...")

    # Count extracted subjects
    raw_dir = os.path.join(output_dir, "raw")
    if os.path.exists(raw_dir):
        # OASIS structure: disc*/OAS1_*_MR*/PROCESSED/MPRAGE/T88_111/
        for root, dirs, files in os.walk(raw_dir):
            for file in files:
                if file.endswith('.hdr') or file.endswith('.img') or file.endswith('.nii') or file.endswith('.nii.gz'):
                    scan_path = os.path.join(root, file)
                    results['scans_found'].append(scan_path)

                    # Extract subject ID from path
                    if 'OAS1_' in scan_path:
                        subject_id = scan_path.split('OAS1_')[1].split('_')[0]
                        subject_id = f"OAS1_{subject_id}_MR1"
                        if subject_id not in [s for s in results.get('subjects', [])]:
                            if 'subjects' not in results:
                                results['subjects'] = []
                            results['subjects'].append(subject_id)

        results['subjects_found'] = len(results.get('subjects', []))

    return results


def download_oasis_dataset(
    dataset_name: str = 'oasis-1',
    max_subjects: int = None,
    output_base_dir: str = None,
    skip_existing: bool = True
) -> Dict:
    """
    Download OASIS dataset with MRI scans and metadata

    Args:
        dataset_name: Which OASIS dataset ('oasis-1', 'oasis-3')
        max_subjects: Maximum subjects to download (None = all available)
        output_base_dir: Where to save files (default: research/input/datasets/)
        skip_existing: Skip already downloaded files

    Returns:
        Dictionary with download statistics and file paths
    """

    if dataset_name not in OASIS_DATASETS:
        raise ValueError(f"Unknown dataset: {dataset_name}. Choose from: {list(OASIS_DATASETS.keys())}")

    dataset_info = OASIS_DATASETS[dataset_name]

    # Set up output directory
    if output_base_dir is None:
        output_base_dir = os.path.join(dataset_dir, 'datasets')

    output_dir = os.path.join(output_base_dir, dataset_name)
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"OASIS DATASET DOWNLOADER")
    print(f"{'='*60}")
    print(f"Dataset: {dataset_info['name']}")
    print(f"Description: {dataset_info['description']}")
    print(f"Age range: {dataset_info['age_range']}")
    print(f"Output directory: {output_dir}")
    print(f"{'='*60}\n")

    results = {
        'dataset_name': dataset_name,
        'output_dir': output_dir,
        'subjects_requested': max_subjects or dataset_info['subjects'],
        'subjects_downloaded': 0,
        'scans_downloaded': 0,
        'scans_skipped': 0,
        'scans_failed': 0,
        'metadata_path': None,
        'scan_paths': []
    }

    # OASIS-1 Download
    if dataset_name == 'oasis-1':

        # Step 1: Download manifest
        manifest_path = download_oasis_1_manifest(output_dir)
        if not manifest_path:
            print("❌ Failed to download manifest. Cannot proceed.")
            return results

        # Step 2: Parse manifest and select subjects
        print(f"\n📋 Parsing manifest...")
        subjects_df = parse_oasis_1_manifest(manifest_path, max_subjects)
        print(f"  ✓ Selected {len(subjects_df)} subjects")

        results['subjects_requested'] = len(subjects_df)
        results['metadata_path'] = manifest_path

        # Step 3: Download raw MRI data
        print(f"\n📊 Selected {len(subjects_df)} subjects for download")

        # Save subject list and manifest
        subject_list_path = os.path.join(output_dir, "subjects_to_download.txt")
        selected_manifest_path = os.path.join(output_dir, "selected_subjects.csv")
        subjects_df.to_csv(selected_manifest_path, index=False)

        with open(subject_list_path, 'w') as f:
            for idx, row in subjects_df.iterrows():
                f.write(f"{row['ID']}\n")

        print(f"✓ Subject list saved to: {subject_list_path}")
        print(f"✓ Metadata saved to: {selected_manifest_path}")
        results['metadata_path'] = selected_manifest_path

        # Download the actual MRI scans
        required_subjects = subjects_df['ID'].tolist()
        download_results = download_oasis_1_raw_data(output_dir, required_subjects, skip_existing)

        # Merge download results
        results['discs_downloaded'] = download_results.get('discs_downloaded', 0)
        results['discs_failed'] = download_results.get('discs_failed', 0)
        results['subjects_downloaded'] = download_results.get('subjects_found', 0)
        results['scan_paths'] = download_results.get('scans_found', [])
        results['scans_downloaded'] = len(results['scan_paths'])


    elif dataset_name == 'oasis-3':
        print("\n⚠️  OASIS-3 download not yet implemented.")
        print("OASIS-3 requires XNAT credentials and uses a different download mechanism.")
        print("This will be added in a future update.")
        print("\nFor now, please use OASIS-1 or download OASIS-3 manually from:")
        print("https://www.oasis-brains.org/oasis-3/")

    # Print summary
    print(f"\n{'='*60}")
    print("DOWNLOAD SUMMARY")
    print(f"{'='*60}")
    print(f"Dataset: {dataset_name}")
    print(f"Subjects requested: {results['subjects_requested']}")
    print(f"Subjects downloaded: {results['subjects_downloaded']}")
    print(f"Scans downloaded: {results['scans_downloaded']}")
    if 'discs_downloaded' in results:
        print(f"Discs downloaded: {results['discs_downloaded']}/12")
        if results['discs_failed'] > 0:
            print(f"⚠️  Discs failed: {results['discs_failed']}")
    print(f"Metadata: {results['metadata_path']}")
    print(f"Output directory: {output_dir}")
    print(f"{'='*60}\n")

    return results


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Download OASIS brain MRI dataset for population normative analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download OASIS-1 with 100 subjects
  python -m functions.download_oasis_dataset --dataset oasis-1 --count 100

  # Download full OASIS-1 dataset (all 416 subjects, ~18GB)
  python -m functions.download_oasis_dataset --dataset oasis-1

  # Download to custom location
  python -m functions.download_oasis_dataset --dataset oasis-1 --output /data/oasis

Available datasets:
  oasis-1: Cross-sectional, 416 subjects, ages 18-96 (~18GB, 12 disc files)
  oasis-3: Longitudinal, 1000+ subjects, ages 42-95 (coming soon)

Note: OASIS-1 will download 12 archive files (~1.5GB each) and extract them automatically.
      The download may take 1-2 hours depending on your internet connection.
        """
    )

    parser.add_argument(
        '--dataset',
        type=str,
        default='oasis-1',
        choices=['oasis-1', 'oasis-3'],
        help='Which OASIS dataset to download (default: oasis-1)'
    )

    parser.add_argument(
        '--count',
        type=int,
        default=None,
        help='Maximum number of subjects to download (default: all available)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output directory (default: research/input/datasets/)'
    )

    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Re-download existing files (default: skip existing)'
    )

    args = parser.parse_args()

    try:
        result = download_oasis_dataset(
            dataset_name=args.dataset,
            max_subjects=args.count,
            output_base_dir=args.output,
            skip_existing=not args.overwrite
        )

        print("\n✅ OASIS dataset download complete!")
        print(f"   Downloaded {result['scans_downloaded']} scans from {result['subjects_downloaded']} subjects")
        print(f"   Data location: {result['output_dir']}/raw")
        print(f"\n📊 Next step: Process the downloaded scans:")
        print(f"   python -m functions.batch_process_population_dataset {result['output_dir']}/raw")

    except Exception as e:
        print(f"\n❌ Error during download: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
