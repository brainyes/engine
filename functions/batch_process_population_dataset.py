"""
Batch Process Population Dataset for Normative Data

This function batch-processes downloaded brain MRI datasets to build population
normative data. It uploads scans, runs the processing pipeline, and stores
metadata for later statistical analysis.

Processing pipeline for each scan:
1. Upload NIFTI file to system
2. Resample Harvard-Oxford atlas to scan space
3. Calculate ROI volumes
4. Store population metadata (age, sex, dataset source, etc.)

The processed data is used by compute_population_norms.py to generate
statistical norms (mean, std, percentiles) for comparison with individual scans.
"""

import os
import argparse
import pandas as pd
import glob
import time
import traceback
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from functions.upload_nifti import upload_nifti
from functions.resample_atlas_for_user_nifti import resample_atlas_for_user_nifti
from functions.calculate_roi_volumes import calculate_roi_volumes
from utilities.data import supabase

FUNCTION_NAME = "batch_process_population_dataset"


def find_nifti_files(directory: str, recursive: bool = True) -> List[str]:
    """
    Find all NIFTI files in a directory

    Args:
        directory: Directory to search
        recursive: Search subdirectories

    Returns:
        List of NIFTI file paths
    """
    patterns = ['*.nii.gz', '*.nii']
    files = []

    for pattern in patterns:
        if recursive:
            search_pattern = os.path.join(directory, '**', pattern)
            files.extend(glob.glob(search_pattern, recursive=True))
        else:
            search_pattern = os.path.join(directory, pattern)
            files.extend(glob.glob(search_pattern))

    return sorted(list(set(files)))  # Remove duplicates


def extract_subject_id_from_filename(filepath: str) -> str:
    """
    Extract subject ID from NIFTI filename

    Handles common patterns:
    - sub-OASIS10001_ses-M00_T1w.nii.gz -> OASIS10001
r    - OAS1_0001_MR1_mpr-1_anon.nii.gz -> OAS1_0001_MR1
    - subject_123.nii -> subject_123

    Args:
        filepath: Path to NIFTI file

    Returns:
        Subject ID string
    """
    filename = os.path.basename(filepath)

    # Remove extensions
    filename = filename.replace('.nii.gz', '').replace('.nii', '')

    # Handle BIDS format: sub-XXXXX_...
    if filename.startswith('sub-'):
        parts = filename.split('_')
        return parts[0].replace('sub-', '')

    # Handle OASIS-1 format: OAS1_XXXX_MRX_...
    # Preserve the full subject ID including session number (MR1, MR2, etc.)
    if filename.startswith('OAS'):
        parts = filename.split('_')
        # Return first 3 parts: OAS1_0001_MR1
        if len(parts) >= 3:
            return '_'.join(parts[:3])
        elif len(parts) >= 2:
            return '_'.join(parts[:2])
        else:
            return parts[0]

    # Default: use entire filename
    return filename


def load_metadata_from_csv(metadata_path: str) -> pd.DataFrame:
    """
    Load subject metadata from CSV file

    Expected columns:
    - ID or participant_id or subject_id: Subject identifier
    - Age or age: Age in years
    - M/F or Sex or sex: Sex (M/F)
    - CDR or cdr: Clinical Dementia Rating (optional)
    - diagnosis: Diagnosis (optional)

    Args:
        metadata_path: Path to CSV file

    Returns:
        DataFrame with standardized column names
    """
    df = pd.read_csv(metadata_path, sep=None, engine='python')  # Auto-detect separator

    # Standardize column names
    column_mapping = {
        'ID': 'subject_id',
        'participant_id': 'subject_id',
        'Age': 'age',
        'M/F': 'sex',
        'Sex': 'sex',
        'CDR': 'cdr',
        'diagnosis_bl': 'diagnosis'
    }

    for old_col, new_col in column_mapping.items():
        if old_col in df.columns:
            df[new_col] = df[old_col]

    # Clean subject IDs (remove 'sub-' prefix if present)
    if 'subject_id' in df.columns:
        df['subject_id'] = df['subject_id'].astype(str).str.replace('sub-', '')

    return df


def save_population_scan_metadata(
    nifti_file_id: str,
    dataset_source: str,
    subject_id: str,
    age: Optional[int] = None,
    sex: Optional[str] = None,
    diagnosis: Optional[str] = None,
    scan_quality: Optional[float] = None
) -> Dict:
    """
    Save population scan metadata to database

    This creates a record linking the uploaded scan to population metadata.

    Args:
        nifti_file_id: ID of uploaded NIFTI file
        dataset_source: Source dataset (e.g., 'oasis-1', 'hcp-young-adult')
        subject_id: Original subject ID from dataset
        age: Age in years (optional)
        sex: Sex ('M', 'F', or 'U' for unknown)
        diagnosis: Clinical diagnosis (optional)
        scan_quality: Quality metric 0-1 (optional)

    Returns:
        Database record
    """

    record = {
        'nifti_file_id': nifti_file_id,
        'dataset_source': dataset_source,
        'subject_id': subject_id,
        'age': int(age) if age is not None else None,
        'sex': sex if sex in ['M', 'F', 'U'] else 'U',
        'diagnosis': diagnosis,
        'scan_quality': float(scan_quality) if scan_quality is not None else None,
        'processed_at': datetime.now().isoformat()
    }

    # Upsert to population_scans table
    # Note: This table needs to be created in Supabase first
    try:
        response = supabase.table('population_scans').upsert(
            record,
            on_conflict='nifti_file_id'
        ).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"  ⚠️  Warning: Could not save population metadata: {str(e)}")
        print(f"     Make sure 'population_scans' table exists in Supabase.")
        return None


def batch_process_population_dataset(
    dataset_dir: str,
    dataset_name: str,
    metadata_csv: Optional[str] = None,
    max_scans: Optional[int] = None,
    skip_existing: bool = True,
    dry_run: bool = False
) -> Dict:
    """
    Batch process a population dataset

    Args:
        dataset_dir: Directory containing NIFTI files
        dataset_name: Name of dataset source (e.g., 'oasis-1')
        metadata_csv: Optional CSV with subject metadata (age, sex, etc.)
        max_scans: Maximum scans to process (None = all)
        skip_existing: Skip scans already in database
        dry_run: If True, only scan and report, don't process

    Returns:
        Dictionary with processing statistics
    """

    print(f"\n{'='*70}")
    print(f"BATCH POPULATION DATASET PROCESSOR")
    print(f"{'='*70}")
    print(f"Dataset: {dataset_name}")
    print(f"Directory: {dataset_dir}")
    print(f"Dry run: {dry_run}")
    print(f"{'='*70}\n")

    # Find all NIFTI files
    print("🔍 Scanning for NIFTI files...")
    nifti_files = find_nifti_files(dataset_dir)
    print(f"  ✓ Found {len(nifti_files)} NIFTI files")

    if len(nifti_files) == 0:
        print("  ❌ No NIFTI files found. Check directory path.")
        return {'scans_processed': 0, 'scans_failed': 0}

    # Load metadata if provided
    metadata_df = None
    if metadata_csv and os.path.exists(metadata_csv):
        print(f"\n📋 Loading metadata from {metadata_csv}...")
        metadata_df = load_metadata_from_csv(metadata_csv)
        print(f"  ✓ Loaded metadata for {len(metadata_df)} subjects")

    # Limit number of scans
    if max_scans:
        nifti_files = nifti_files[:max_scans]
        print(f"\n  → Processing limited to {len(nifti_files)} scans")

    # Processing statistics
    stats = {
        'dataset_name': dataset_name,
        'total_scans': len(nifti_files),
        'scans_processed': 0,
        'scans_skipped': 0,
        'scans_failed': 0,
        'processing_time': 0,
        'nifti_file_ids': []
    }

    if dry_run:
        print(f"\n{'='*70}")
        print("DRY RUN MODE - No processing will occur")
        print(f"{'='*70}")
        for i, filepath in enumerate(nifti_files[:10], 1):
            subject_id = extract_subject_id_from_filename(filepath)
            print(f"  {i}. Subject: {subject_id}")
            print(f"     File: {os.path.basename(filepath)}")

        if len(nifti_files) > 10:
            print(f"  ... and {len(nifti_files) - 10} more files")

        print(f"\nTo process, run without --dry-run flag")
        return stats

    # Process each NIFTI file
    print(f"\n{'='*70}")
    print("PROCESSING SCANS")
    print(f"{'='*70}\n")

    start_time = time.time()

    for i, filepath in enumerate(nifti_files, 1):
        subject_id = extract_subject_id_from_filename(filepath)

        print(f"[{i}/{len(nifti_files)}] Processing: {subject_id}")
        print(f"  File: {os.path.basename(filepath)}")

        try:
            # Upload NIFTI file
            print(f"  ↗️  Uploading...")
            nifti_file, nifti_file_zipped = upload_nifti(
                filepath,
                user_id=None,
                public_id=f"population-{dataset_name}-{subject_id}"
            )
            nifti_file_id = nifti_file['id']
            stats['nifti_file_ids'].append(nifti_file_id)

            print(f"  ✓ Uploaded: {nifti_file_id}")

            # Resample atlas
            print(f"  🗺️  Resampling atlas...")
            atlas_result = resample_atlas_for_user_nifti(nifti_file_id)
            print(f"  ✓ Atlas resampled")

            # Calculate ROI volumes
            print(f"  📊 Calculating ROI volumes...")
            roi_volumes = calculate_roi_volumes(nifti_file_id)
            print(f"  ✓ Calculated {len(roi_volumes)} ROI volumes")

            # Get metadata for this subject
            age = None
            sex = 'U'
            diagnosis = None

            if metadata_df is not None:
                subject_meta = metadata_df[metadata_df['subject_id'] == subject_id]
                if len(subject_meta) > 0:
                    meta_row = subject_meta.iloc[0]
                    age = meta_row.get('age')
                    sex = meta_row.get('sex', 'U')
                    diagnosis = meta_row.get('diagnosis')

            # Save population metadata
            print(f"  💾 Saving population metadata...")
            pop_record = save_population_scan_metadata(
                nifti_file_id=nifti_file_id,
                dataset_source=dataset_name,
                subject_id=subject_id,
                age=age,
                sex=sex,
                diagnosis=diagnosis
            )

            if pop_record:
                print(f"  ✓ Population metadata saved")
            else:
                print(f"  ⚠️  Warning: Could not save population metadata")

            stats['scans_processed'] += 1
            print(f"  ✅ Complete! ({stats['scans_processed']}/{len(nifti_files)})\n")

            # Brief pause to avoid overwhelming the system
            time.sleep(0.5)

        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            print(f"\n  Stack trace:")
            traceback.print_exc()
            stats['scans_failed'] += 1
            print(f"\n  Continuing to next scan...\n")
            continue

    stats['processing_time'] = time.time() - start_time

    # Print summary
    print(f"\n{'='*70}")
    print("PROCESSING COMPLETE")
    print(f"{'='*70}")
    print(f"Total scans found: {stats['total_scans']}")
    print(f"Successfully processed: {stats['scans_processed']}")
    print(f"Failed: {stats['scans_failed']}")
    print(f"Processing time: {stats['processing_time']:.1f} seconds")
    print(f"Average per scan: {stats['processing_time']/max(stats['scans_processed'], 1):.1f} seconds")
    print(f"{'='*70}\n")

    if stats['scans_processed'] > 0:
        print("✅ Next step: Compute population norms from processed data:")
        print(f"   python -m functions.compute_population_norms --dataset {dataset_name}")

    return stats


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Batch process brain MRI dataset to build population norms',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process OASIS-1 dataset with metadata
  python -m functions.batch_process_population_dataset \\
      research/input/datasets/oasis-1/raw \\
      --dataset oasis-1 \\
      --metadata research/input/datasets/oasis-1/selected_subjects.csv

  # Process first 10 scans (testing)
  python -m functions.batch_process_population_dataset \\
      research/input/datasets/oasis-1/raw \\
      --dataset oasis-1 \\
      --count 10

  # Dry run to see what would be processed
  python -m functions.batch_process_population_dataset \\
      research/input/datasets/oasis-1/raw \\
      --dataset oasis-1 \\
      --dry-run

Database Setup Required:
  Before running, create the 'population_scans' table in Supabase:

  CREATE TABLE population_scans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nifti_file_id UUID NOT NULL UNIQUE,
    dataset_source TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    age INTEGER,
    sex TEXT CHECK (sex IN ('M', 'F', 'U')),
    diagnosis TEXT,
    scan_quality FLOAT,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (nifti_file_id) REFERENCES nifti_files(id) ON DELETE CASCADE
  );

  CREATE INDEX idx_population_scans_dataset ON population_scans(dataset_source);
  CREATE INDEX idx_population_scans_age_sex ON population_scans(age, sex);
        """
    )

    parser.add_argument(
        'directory',
        type=str,
        help='Directory containing NIFTI files to process'
    )

    parser.add_argument(
        '--dataset',
        type=str,
        required=True,
        help='Dataset name (e.g., oasis-1, hcp-young-adult)'
    )

    parser.add_argument(
        '--metadata',
        type=str,
        default=None,
        help='CSV file with subject metadata (age, sex, diagnosis)'
    )

    parser.add_argument(
        '--count',
        type=int,
        default=None,
        help='Maximum number of scans to process (default: all)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Scan and report only, do not process'
    )

    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Reprocess existing scans (default: skip)'
    )

    args = parser.parse_args()

    # Validate directory exists
    if not os.path.exists(args.directory):
        print(f"❌ Error: Directory not found: {args.directory}")
        os._exit(1)

    try:
        result = batch_process_population_dataset(
            dataset_dir=args.directory,
            dataset_name=args.dataset,
            metadata_csv=args.metadata,
            max_scans=args.count,
            skip_existing=not args.overwrite,
            dry_run=args.dry_run
        )

        if result['scans_failed'] > 0:
            print(f"\n⚠️  Warning: {result['scans_failed']} scans failed to process")
            os._exit(1)

        print("\n✅ Batch processing complete!")

    except Exception as e:
        print(f"\n❌ Error during batch processing: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
