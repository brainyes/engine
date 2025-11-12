"""
Batch Process Population Dataset for Normative Data (Pipeline v2)

This function batch-processes downloaded brain MRI datasets to build population
normative data. It uploads scans, runs the processing pipeline, and stores
metadata for later statistical analysis.

Processing pipeline v2 for each scan:
1. Upload NIFTI file to system
2. **NEW** Preprocess: N4 bias correction + skull-stripping + ICV computation
3. **NEW** Register: Nonlinear registration to MNI152 template (ANTs or affine fallback)
4. Resample atlas: Use inverse warp to bring atlas from MNI → native space
5. Calculate ROI volumes: Measure in native space (where anatomy is)
6. Store population metadata (age, sex, ICV, dataset source, etc.)

Changes from v1:
- v1 used geometric atlas resampling (WRONG - no anatomical correspondence)
- v2 uses proper registration + inverse warp (CORRECT - anatomically aligned)

The processed data is used by compute_population_norms.py to generate
statistical norms (mean, std, percentiles, ICV-adjusted models) for comparison
with individual scans.
"""

import glob
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Optional

import argparse
import pandas as pd
import traceback

from functions.calculate_roi_volumes import calculate_roi_volumes
from functions.resample_atlas_for_user_nifti import resample_atlas_for_user_nifti
from functions.upload_nifti import upload_nifti
from utilities.data import supabase

FUNCTION_NAME = "batch_process_population_dataset"


def find_nifti_files(directory: str, recursive: bool = True) -> List[str]:
    """
    Find all NIFTI files in a directory

    Args:
        directory: Directory to search
        recursive: Search subdirectories

    Returns:
        List of NIFTI file paths (including converted ANALYZE files)
    """
    patterns = ['*.nii.gz', '*.nii', '*.hdr']  # Add ANALYZE format
    files = []

    for pattern in patterns:
        if recursive:
            search_pattern = os.path.join(directory, '**', pattern)
            files.extend(glob.glob(search_pattern, recursive=True))
        else:
            search_pattern = os.path.join(directory, pattern)
            files.extend(glob.glob(search_pattern))

    return sorted(list(set(files)))  # Remove duplicates


def is_normalized_scan(filepath: str) -> bool:
    """
    Detect if scan is already normalized to atlas space OR is a segmentation/mask

    Checks filename patterns for:
    - Normalization: t88, tal (Talairach), mni (MNI space)
    - Segmentations: fseg, seg, mask, label
    - Post-processing: gfc (gradient field corrected), masked

    NOTE: N4-corrected scans are ACCEPTED (will skip N4 step but continue with registration)

    Args:
        filepath: Path to scan file

    Returns:
        True if scan should be skipped (normalized or segmentation)
    """
    filename = os.path.basename(filepath).lower()

    # Check for normalization indicators FIRST (highest priority)
    # Even if file has _sbj, if it has t88/mni/tal it's normalized
    normalized_patterns = ['t88', 'tal', 'mni', 'normalized']
    for pattern in normalized_patterns:
        if pattern in filename:
            return True  # Normalized = skip

    # Check for segmentation/mask files (not raw scans)
    segmentation_patterns = ['fseg', '_seg', 'mask', 'label', 'parcellation', 'gfc']
    for pattern in segmentation_patterns:
        if pattern in filename:
            return True  # Segmentation = skip

    # Check for native space indicators (these are good - explicit check for usability)
    native_patterns = ['_sbj', '_native', '_subj', '_mpr']
    for pattern in native_patterns:
        if pattern in filename:
            # Double-check no normalization markers (defensive)
            for norm_pattern in normalized_patterns:
                if norm_pattern in filename:
                    return True  # Normalized wins over native marker
            return False  # Native space = usable

    return False


def is_n4_corrected(filepath: str) -> bool:
    """
    Detect if scan has already been N4 bias-corrected

    Args:
        filepath: Path to scan file

    Returns:
        True if N4 correction already applied
    """
    filename = os.path.basename(filepath).lower()
    return '_n4_' in filename or 'mpr_n4' in filename


def convert_analyze_to_nifti(hdr_path: str) -> str:
    """
    Convert ANALYZE format (.hdr/.img) to NIFTI (.nii.gz)

    Args:
        hdr_path: Path to .hdr file

    Returns:
        Path to converted NIFTI file
    """
    import tempfile
    import nibabel as nib

    # Load ANALYZE image
    img = nib.load(hdr_path)

    # Create temp NIFTI path
    temp_dir = tempfile.gettempdir()
    basename = os.path.basename(hdr_path).replace('.hdr', '')
    nifti_path = os.path.join(temp_dir, f"{basename}.nii.gz")

    # Save as NIFTI
    nib.save(img, nifti_path)

    return nifti_path


def get_base_subject_id(subject_id: str) -> str:
    """
    Get base subject ID for metadata matching (removes scan-specific suffixes)

    Examples:
    - OAS1_0102_MR1_mpr-1 -> OAS1_0102_MR1
    - OAS1_0102_MR1_sbj -> OAS1_0102_MR1
    - OAS1_0102_MR1 -> OAS1_0102_MR1

    Args:
        subject_id: Full subject ID (potentially with scan suffix)

    Returns:
        Base subject ID (for metadata matching)
    """
    # Remove scan-specific suffixes
    if '_mpr-' in subject_id:
        # OAS1_0102_MR1_mpr-1 -> OAS1_0102_MR1
        return subject_id.rsplit('_mpr-', 1)[0]
    elif subject_id.endswith('_sbj'):
        # OAS1_0102_MR1_sbj -> OAS1_0102_MR1
        return subject_id.rsplit('_sbj', 1)[0]
    elif subject_id.endswith('_n4'):
        # OAS1_0102_MR1_n4 -> OAS1_0102_MR1
        return subject_id.rsplit('_n4', 1)[0]

    # Already a base ID
    return subject_id


def extract_subject_id_from_filename(filepath: str) -> str:
    """
    Extract subject ID from NIFTI filename

    Handles common patterns:
    - sub-OASIS10001_ses-M00_T1w.nii.gz -> OASIS10001
    - OAS1_0001_MR1_mpr-1_anon.nii.gz -> OAS1_0001_MR1_mpr-1 (includes scan number)
    - OAS1_0001_MR1_mpr_n4_anon_sbj_111.hdr -> OAS1_0001_MR1_sbj (processed version)
    - subject_123.nii -> subject_123

    Args:
        filepath: Path to NIFTI file

    Returns:
        Subject ID string (unique per scan, not per subject)
    """
    filename = os.path.basename(filepath)

    # Remove extensions
    filename = filename.replace('.nii.gz', '').replace('.nii', '').replace('.hdr', '')

    # Handle BIDS format: sub-XXXXX_...
    if filename.startswith('sub-'):
        parts = filename.split('_')
        return parts[0].replace('sub-', '')

    # Handle OASIS-1 format: OAS1_XXXX_MRX_...
    # Need to differentiate between multiple scans of same subject
    if filename.startswith('OAS'):
        parts = filename.split('_')

        # Base ID: OAS1_0001_MR1
        if len(parts) >= 3:
            base_id = '_'.join(parts[:3])
        elif len(parts) >= 2:
            base_id = '_'.join(parts[:2])
        else:
            base_id = parts[0]

        # Add scan-specific suffix to differentiate multiple scans
        # Examples:
        # - OAS1_0001_MR1_mpr-1_anon -> "OAS1_0001_MR1_mpr-1"
        # - OAS1_0001_MR1_mpr-2_anon -> "OAS1_0001_MR1_mpr-2"
        # - OAS1_0001_MR1_mpr_n4_anon_sbj_111 -> "OAS1_0001_MR1_sbj" (processed/averaged)

        # Check the entire filename for patterns (not just parts[3])
        if len(parts) >= 4:
            # Look for raw scan pattern: mpr-1, mpr-2, mpr-3, mpr-4
            # These use hyphen, not underscore
            for part in parts:
                if part.startswith('mpr-'):
                    # Raw scan: mpr-1, mpr-2, etc
                    return f"{base_id}_{part}"

            # Look for processed scan indicator (sbj = subject-averaged)
            if 'sbj' in parts:
                # Processed/averaged scan: mpr_n4_anon_sbj_111
                return f"{base_id}_sbj"

        # If no specific scan identifier found, return base ID
        return base_id

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


def check_if_scan_exists(dataset_source: str, subject_id: str) -> tuple:
    """
    Check if a scan already exists in the population_scans table and get its version

    Args:
        dataset_source: Source dataset (e.g., 'oasis-1')
        subject_id: Original subject ID from dataset

    Returns:
        Tuple of (exists: bool, preprocessing_version: str or None)
    """
    try:
        response = supabase.table('population_scans')\
            .select('id, preprocessing_version')\
            .eq('subject_id', subject_id)\
            .eq('dataset_source', dataset_source)\
            .execute()

        if response.data and len(response.data) > 0:
            version = response.data[0].get('preprocessing_version', 'v1_none')
            return True, version
        return False, None
    except Exception as e:
        # If check fails, assume doesn't exist to be safe
        return False, None


def should_reprocess_scan(preprocessing_version: str) -> bool:
    """
    Determine if a scan should be reprocessed based on its version

    v1 scans (v1_none) should be reprocessed with v2 pipeline
    v2 scans (v2_*) should be skipped

    Args:
        preprocessing_version: Version string from database

    Returns:
        True if scan should be reprocessed
    """
    if not preprocessing_version:
        return True  # No version = needs processing

    if preprocessing_version.startswith('v1'):
        return True  # v1 scans need upgrading to v2

    if preprocessing_version.startswith('v2'):
        return False  # v2 scans are already processed correctly

    return True  # Unknown version = reprocess to be safe


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
        # Check if scan is already normalized (skip if so)
        if is_normalized_scan(filepath):
            result['status'] = 'skipped'
            result['error'] = 'Scan appears to be already normalized (t88/mni) - need native space scan'
            print(f"  ⚠️  Skipping {subject_id}: Already normalized to atlas space")
            return result

        # Convert ANALYZE to NIFTI if needed
        working_filepath = filepath
        if filepath.endswith('.hdr'):
            print(f"  🔄 Converting ANALYZE to NIFTI: {subject_id}")
            working_filepath = convert_analyze_to_nifti(filepath)
            result['converted'] = True

        # Check if already processed and get version
        if skip_existing:
            exists, version = check_if_scan_exists(dataset_name, subject_id)
            if exists:
                # Check if we should reprocess (v1 -> v2 upgrade)
                if should_reprocess_scan(version):
                    print(f"  ♻️  Reprocessing {subject_id}: Upgrading from {version} to v2")
                    # Continue processing (don't return)
                else:
                    print(f"  ⏭️  Skipping {subject_id}: Already processed with {version}")
                    result['status'] = 'skipped'
                    return result

        # Upload NIFTI file (using converted path if ANALYZE was converted)
        # Retry upload on timeout (large files can timeout on slow connections)
        max_retries = 3
        retry_count = 0
        upload_success = False

        while retry_count < max_retries and not upload_success:
            try:
                if retry_count > 0:
                    print(f"  Retry {retry_count}/{max_retries}...")

                nifti_file, nifti_file_zipped = upload_nifti(
                    working_filepath,
                    user_id=None,
                    public_id=f"population-{dataset_name}-{subject_id}"
                )
                nifti_file_id = nifti_file['id']
                result['nifti_file_id'] = nifti_file_id
                upload_success = True
            except Exception as upload_error:
                retry_count += 1
                error_msg = str(upload_error).lower()
                if 'timeout' in error_msg or 'timed out' in error_msg:
                    if retry_count < max_retries:
                        print(f"  ⚠️  Upload timeout, retrying ({retry_count}/{max_retries})...")
                        import time
                        time.sleep(2 * retry_count)  # Exponential backoff
                    else:
                        raise Exception(f"Upload failed after {max_retries} retries: {upload_error}")
                else:
                    # Not a timeout error, re-raise immediately
                    raise

        # Get metadata for this subject (use base subject ID)
        base_subject_id = get_base_subject_id(subject_id)
        age = metadata_dict.get('age') if metadata_dict else None
        sex = metadata_dict.get('sex', 'U') if metadata_dict else 'U'
        diagnosis = metadata_dict.get('diagnosis') if metadata_dict else None

        # Create population_scans record FIRST (before preprocessing)
        # This allows preprocessing and registration steps to update it
        print(f"  💾 Creating population scan record...")
        pop_record = save_population_scan_metadata(
            nifti_file_id=nifti_file_id,
            dataset_source=dataset_name,
            subject_id=subject_id,
            age=age,
            sex=sex,
            diagnosis=diagnosis
        )
        if pop_record:
            print(f"  ✓ Population record created")
        else:
            print(f"  ⚠️  Warning: Could not create population record")

        # Check if N4 correction already applied (based on filename)
        n4_already_done = is_n4_corrected(filepath)
        if n4_already_done:
            print(f"  ℹ️  N4 correction already applied (detected from filename)")

        # NEW: Preprocess scan (N4 + skull-strip + ICV)
        try:
            from functions.preprocess_native_scan import preprocess_native_scan
            print(f"  Preprocessing scan...")
            preprocess_result = preprocess_native_scan(
                nifti_file_id,
                skip_n4=n4_already_done  # Skip N4 if already done
            )
            result['icv'] = preprocess_result['icv_mm3']
            result['preprocessing_method'] = preprocess_result['method']
            print(f"  ✓ Preprocessing complete (ICV: {preprocess_result['icv_mm3']:,.0f} mm³)")
        except Exception as e:
            print(f"  ⚠️  Preprocessing failed: {e}")
            print(f"     Continuing without preprocessing (will use geometric resampling)")
            result['preprocessing_method'] = 'failed'

        # NEW: Register to template (use MNI152 - industry standard for all datasets)
        try:
            from functions.register_to_template import register_to_template

            # Use MNI152 template for all datasets (industry standard)
            # This ensures consistency between population norms and user scans
            template_name = 'mni152'

            print(f"  Registering to MNI152 template...")
            registration_result = register_to_template(nifti_file_id, method='auto', template_name=template_name)
            result['registration_method'] = registration_result['registration_method']
            result['template_used'] = template_name
            print(f"  ✓ Registration complete ({registration_result['registration_method']})")
        except Exception as e:
            print(f"  ⚠️  Registration failed: {e}")
            print(f"     Continuing without registration (will use geometric resampling)")
            result['registration_method'] = 'failed'

        # Resample atlas (population mode v2: uses registration transforms if available)
        # Pass template parameter so it uses the correct atlas version (MNI or OASIS space)
        atlas_result = resample_atlas_for_user_nifti(nifti_file_id, population_mode=True, template=template_name)

        # Calculate ROI volumes
        roi_volumes = calculate_roi_volumes(nifti_file_id)

        # Population metadata already saved earlier (before preprocessing)
        # Preprocessing and registration steps have updated it with ICV and registration info

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
    workers: Optional[int] = None
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
        workers: Number of parallel workers (None = auto-detect, 1 = sequential)

    Returns:
        Dictionary with processing statistics
    """

    # Auto-detect optimal number of workers if not specified
    if workers is None:
        import psutil
        cpu_count = os.cpu_count() or 1
        # Estimate memory needed per worker (4GB for registration)
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        max_workers_by_memory = max(1, int(available_memory_gb / 4))
        # Use all CPUs but respect memory constraints, reserve 1 core for system
        workers = min(max(1, cpu_count - 1), max_workers_by_memory)
        print(f"🔧 Auto-detected {workers} workers (CPUs: {cpu_count}, Available RAM: {available_memory_gb:.1f}GB)")

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

        # Filter files to only include subjects in metadata
        # Use base subject ID for matching (without scan-specific suffixes)
        if metadata_df is not None and len(metadata_df) > 0:
            metadata_subject_ids = set(metadata_df['subject_id'].tolist())
            original_count = len(nifti_files)
            nifti_files = [
                f for f in nifti_files
                if get_base_subject_id(extract_subject_id_from_filename(f)) in metadata_subject_ids
            ]
            filtered_count = original_count - len(nifti_files)
            if filtered_count > 0:
                print(f"  → Filtered out {filtered_count} files not in metadata (kept {len(nifti_files)})")

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
                # Use base subject ID for metadata lookup (removes scan-specific suffix)
                base_subject_id = get_base_subject_id(subject_id)
                metadata_dict = metadata_lookup.get(base_subject_id)

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
        # SEQUENTIAL PROCESSING - use same process_single_scan function
        for i, filepath in enumerate(nifti_files, 1):
            subject_id = extract_subject_id_from_filename(filepath)
            # Use base subject ID for metadata lookup (removes scan-specific suffix)
            base_subject_id = get_base_subject_id(subject_id)
            metadata_dict = metadata_lookup.get(base_subject_id)

            print(f"[{i}/{len(nifti_files)}] Processing: {subject_id}")
            print(f"  File: {os.path.basename(filepath)}")

            try:
                # Use centralized processing function
                result = process_single_scan(
                    filepath,
                    dataset_name,
                    metadata_dict,
                    skip_existing
                )

                # Update stats based on result
                if result['status'] == 'skipped':
                    print(f"  ⏭️  Skipped")
                    stats['scans_skipped'] += 1
                elif result['status'] == 'success':
                    print(f"  ✅ Complete! ({i}/{len(nifti_files)})\n")
                    stats['scans_processed'] += 1
                    if result['nifti_file_id']:
                        stats['nifti_file_ids'].append(result['nifti_file_id'])
                elif result['status'] == 'failed':
                    print(f"  ❌ Failed: {result['error']}\n")
                    stats['scans_failed'] += 1

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
        default=None,
        help='Number of parallel workers (default: auto-detect based on CPU/RAM)'
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
