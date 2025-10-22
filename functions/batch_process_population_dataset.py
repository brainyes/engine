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
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

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


def check_if_scan_exists(dataset_source: str, subject_id: str) -> bool:
    """
    Check if a scan already exists in the population_scans table

    Args:
        dataset_source: Source dataset (e.g., 'oasis-1')
        subject_id: Original subject ID from dataset

    Returns:
        True if scan exists, False otherwise
    """
    try:
        response = supabase.table('population_scans')\
            .select('id')\
            .eq('subject_id', subject_id)\
            .eq('dataset_source', dataset_source)\
            .execute()

        return response.data and len(response.data) > 0
    except Exception as e:
        # If check fails, assume doesn't exist to be safe
        return False


def process_single_scan(
    filepath: str,
    dataset_name: str,
    metadata_dict: Optional[Dict] = None,
    skip_existing: bool = True
) -> Dict:
    """
    Process a single scan (used for parallel processing)

    Args:
        filepath: Path to NIFTI file
        dataset_name: Dataset source name
        metadata_dict: Dictionary with metadata for this subject
        skip_existing: Skip if already processed

    Returns:
        Dictionary with processing result
    """
    subject_id = extract_subject_id_from_filename(filepath)

    result = {
        'subject_id': subject_id,
        'filepath': filepath,
        'status': 'unknown',
        'nifti_file_id': None,
        'error': None
    }

    try:
        # Check if already processed
        if skip_existing and check_if_scan_exists(dataset_name, subject_id):
            result['status'] = 'skipped'
            return result

        # Upload NIFTI file
        nifti_file, nifti_file_zipped = upload_nifti(
            filepath,
            user_id=None,
            public_id=f"population-{dataset_name}-{subject_id}"
        )
        nifti_file_id = nifti_file['id']
        result['nifti_file_id'] = nifti_file_id

        # Resample atlas (population mode: skip FreeSurfer, use MNI atlases only)
        atlas_result = resample_atlas_for_user_nifti(nifti_file_id, population_mode=True)

        # Calculate ROI volumes
        roi_volumes = calculate_roi_volumes(nifti_file_id)

        # Get metadata
        age = metadata_dict.get('age') if metadata_dict else None
        sex = metadata_dict.get('sex', 'U') if metadata_dict else 'U'
        diagnosis = metadata_dict.get('diagnosis') if metadata_dict else None

        # Save population metadata
        pop_record = save_population_scan_metadata(
            nifti_file_id=nifti_file_id,
            dataset_source=dataset_name,
            subject_id=subject_id,
            age=age,
            sex=sex,
            diagnosis=diagnosis
        )

        result['status'] = 'success'
        return result

    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        return result


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
    # Use subject_id + dataset_source as unique key to prevent duplicates
    try:
        # Try insert first - will fail if duplicate exists due to unique constraint
        try:
            response = supabase.table('population_scans')\
                .insert(record)\
                .execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            else:
                # Insert succeeded but no data returned (shouldn't happen but handle it)
                return record
        except Exception as insert_error:
            # If insert fails (likely due to duplicate), try update
            error_msg = str(insert_error).lower()
            if 'duplicate' in error_msg or 'unique' in error_msg or 'conflict' in error_msg:
                # Update existing record
                response = supabase.table('population_scans')\
                    .update(record)\
                    .eq('subject_id', subject_id)\
                    .eq('dataset_source', dataset_source)\
                    .execute()

                # Update returns 204 No Content on success, which is actually SUCCESS
                # Just return the record we tried to save
                return record
            else:
                # Some other error, re-raise it
                raise insert_error

    except Exception as e:
        print(f"  ⚠️  Warning: Could not save population metadata: {str(e)}")
        return None


def batch_process_population_dataset(
    dataset_dir: str,
    dataset_name: str,
    metadata_csv: Optional[str] = None,
    max_scans: Optional[int] = None,
    skip_existing: bool = True,
    dry_run: bool = False,
    offset: int = 0,
    workers: int = 1
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
        offset: Number of scans to skip from the beginning (default: 0)
        workers: Number of parallel workers (default: 1 = sequential)

    Returns:
        Dictionary with processing statistics
    """

    print(f"\n{'='*70}")
    print(f"BATCH POPULATION DATASET PROCESSOR")
    print(f"{'='*70}")
    print(f"Dataset: {dataset_name}")
    print(f"Directory: {dataset_dir}")
    print(f"Dry run: {dry_run}")
    print(f"Skip existing: {skip_existing}")
    if offset > 0:
        print(f"Offset: {offset} (skipping first {offset} scans)")
    print(f"Workers: {workers} ({'parallel' if workers > 1 else 'sequential'})")
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

    # Apply offset to skip already processed scans
    if offset > 0:
        nifti_files = nifti_files[offset:]
        print(f"\n  → Skipping first {offset} scans (offset applied)")

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

    # Prepare metadata lookup dictionary for faster access
    metadata_lookup = {}
    if metadata_df is not None:
        for _, row in metadata_df.iterrows():
            subj_id = row.get('subject_id')
            if subj_id:
                # Clean metadata
                age_raw = row.get('age')
                age = None
                if pd.notna(age_raw):
                    try:
                        age = int(float(age_raw))
                    except (ValueError, TypeError):
                        pass

                sex_raw = row.get('sex', 'U')
                sex = 'U'
                if pd.notna(sex_raw):
                    sex_str = str(sex_raw).strip().upper()
                    sex = sex_str if sex_str in ['M', 'F'] else 'U'

                diagnosis_raw = row.get('diagnosis')
                diagnosis = str(diagnosis_raw) if pd.notna(diagnosis_raw) else None

                metadata_lookup[subj_id] = {
                    'age': age,
                    'sex': sex,
                    'diagnosis': diagnosis
                }

    # Process each NIFTI file
    print(f"\n{'='*70}")
    print("PROCESSING SCANS")
    print(f"{'='*70}\n")

    start_time = time.time()

    if workers > 1:
        # PARALLEL PROCESSING
        print(f"🚀 Processing scans in parallel with {workers} workers...\n")

        with ProcessPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            future_to_filepath = {}
            for filepath in nifti_files:
                subject_id = extract_subject_id_from_filename(filepath)
                metadata_dict = metadata_lookup.get(subject_id)

                future = executor.submit(
                    process_single_scan,
                    filepath,
                    dataset_name,
                    metadata_dict,
                    skip_existing
                )
                future_to_filepath[future] = filepath

            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_filepath):
                filepath = future_to_filepath[future]
                completed += 1

                try:
                    result = future.result()
                    subject_id = result['subject_id']

                    if result['status'] == 'skipped':
                        print(f"[{completed}/{len(nifti_files)}] {subject_id}: ⏭️  Skipped (already processed)")
                        stats['scans_skipped'] += 1
                    elif result['status'] == 'success':
                        print(f"[{completed}/{len(nifti_files)}] {subject_id}: ✅ Success")
                        stats['scans_processed'] += 1
                        if result['nifti_file_id']:
                            stats['nifti_file_ids'].append(result['nifti_file_id'])
                    elif result['status'] == 'failed':
                        print(f"[{completed}/{len(nifti_files)}] {subject_id}: ❌ Failed - {result['error']}")
                        stats['scans_failed'] += 1

                except Exception as e:
                    print(f"[{completed}/{len(nifti_files)}] {os.path.basename(filepath)}: ❌ Failed - {str(e)}")
                    stats['scans_failed'] += 1

    else:
        # SEQUENTIAL PROCESSING (original code)
        for i, filepath in enumerate(nifti_files, 1):
            subject_id = extract_subject_id_from_filename(filepath)

            print(f"[{i}/{len(nifti_files)}] Processing: {subject_id}")
            print(f"  File: {os.path.basename(filepath)}")

            # Check if already processed
            if skip_existing and check_if_scan_exists(dataset_name, subject_id):
                print(f"  ⏭️  Already processed - skipping")
                stats['scans_skipped'] += 1
                continue

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

                # Resample atlas (population mode: skip FreeSurfer, use MNI atlases only)
                print(f"  🗺️  Resampling atlas (population mode)...")
                atlas_result = resample_atlas_for_user_nifti(nifti_file_id, population_mode=True)
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

                        # Clean age (handle NaN, convert to int)
                        age_raw = meta_row.get('age')
                        if pd.notna(age_raw):
                            try:
                                age = int(float(age_raw))
                            except (ValueError, TypeError):
                                age = None

                        # Clean sex (ensure M/F/U)
                        sex_raw = meta_row.get('sex', 'U')
                        if pd.notna(sex_raw):
                            sex_str = str(sex_raw).strip().upper()
                            sex = sex_str if sex_str in ['M', 'F'] else 'U'

                        # Clean diagnosis
                        diagnosis_raw = meta_row.get('diagnosis')
                        if pd.notna(diagnosis_raw):
                            diagnosis = str(diagnosis_raw)

                        print(f"  📋 Metadata found: age={age}, sex={sex}, diagnosis={diagnosis}")
                    else:
                        print(f"  ⚠️  No metadata found for subject_id: {subject_id}")
                        print(f"     CSV has these subject_ids: {metadata_df['subject_id'].head().tolist()}")
                else:
                    print(f"  ℹ️  No metadata CSV provided")

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
    print(f"Skipped (already processed): {stats['scans_skipped']}")
    print(f"Failed: {stats['scans_failed']}")
    print(f"Processing time: {stats['processing_time']:.1f} seconds")
    if stats['scans_processed'] > 0:
        print(f"Average per scan: {stats['processing_time']/stats['scans_processed']:.1f} seconds")
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

  # Process with 8 parallel workers (much faster!)
  python -m functions.batch_process_population_dataset \\
      research/input/datasets/oasis-1/raw \\
      --dataset oasis-1 \\
      --metadata research/input/datasets/oasis-1/selected_subjects.csv \\
      --workers 8

  # Process first 10 scans (testing)
  python -m functions.batch_process_population_dataset \\
      research/input/datasets/oasis-1/raw \\
      --dataset oasis-1 \\
      --count 10

  # Skip first 10 scans and process next 10 (resume from offset)
  python -m functions.batch_process_population_dataset \\
      research/input/datasets/oasis-1/raw \\
      --dataset oasis-1 \\
      --offset 10 \\
      --count 10

  # Dry run to see what would be processed
  python -m functions.batch_process_population_dataset \\
      research/input/datasets/oasis-1/raw \\
      --dataset oasis-1 \\
      --dry-run
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

    parser.add_argument(
        '--offset',
        type=int,
        default=0,
        help='Skip first N scans (useful for resuming interrupted processing)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Number of parallel workers (default: 1 = sequential, use 4-8 for parallel)'
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
            dry_run=args.dry_run,
            offset=args.offset,
            workers=args.workers
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
