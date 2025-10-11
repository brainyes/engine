"""
Backfill Population Scan Metadata

This script updates existing population_scans records with metadata from CSV files.
Use this when scans were processed without the --metadata flag.
"""

import os
import argparse
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

from utilities.data import supabase

FUNCTION_NAME = "backfill_population_metadata"


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


def get_population_scans_without_metadata(dataset_source: Optional[str] = None) -> List[Dict]:
    """
    Get population scans that are missing metadata (age/sex)

    Args:
        dataset_source: Filter by dataset source (optional)

    Returns:
        List of population scan records
    """
    query = supabase.table('population_scans').select('*')

    if dataset_source:
        query = query.eq('dataset_source', dataset_source)

    # Filter for records without age or with sex='U'
    query = query.or_('age.is.null,sex.eq.U')

    response = query.execute()
    return response.data if response.data else []


def update_population_scan_metadata(
    scan_id: str,
    age: Optional[int] = None,
    sex: Optional[str] = None,
    diagnosis: Optional[str] = None
) -> Dict:
    """
    Update metadata for a population scan

    Args:
        scan_id: Population scan record ID
        age: Age in years
        sex: Sex ('M', 'F', or 'U')
        diagnosis: Clinical diagnosis

    Returns:
        Updated record
    """
    update_data = {
        'updated_at': datetime.now().isoformat()
    }

    if age is not None:
        update_data['age'] = int(age)

    if sex and sex in ['M', 'F', 'U']:
        update_data['sex'] = sex

    if diagnosis:
        update_data['diagnosis'] = diagnosis

    response = supabase.table('population_scans').update(update_data).eq('id', scan_id).execute()
    return response.data[0] if response.data else None


def backfill_population_metadata(
    metadata_csv: str,
    dataset_source: Optional[str] = None,
    dry_run: bool = False
) -> Dict:
    """
    Backfill metadata for population scans

    Args:
        metadata_csv: Path to CSV with subject metadata
        dataset_source: Filter by dataset source (optional)
        dry_run: If True, only report what would be updated

    Returns:
        Dictionary with update statistics
    """

    print(f"\n{'='*70}")
    print(f"BACKFILL POPULATION METADATA")
    print(f"{'='*70}")
    print(f"Metadata CSV: {metadata_csv}")
    print(f"Dataset filter: {dataset_source or 'all'}")
    print(f"Dry run: {dry_run}")
    print(f"{'='*70}\n")

    # Load metadata from CSV
    print("📋 Loading metadata from CSV...")
    if not os.path.exists(metadata_csv):
        print(f"  ❌ Error: File not found: {metadata_csv}")
        return {'updated': 0, 'failed': 0}

    metadata_df = load_metadata_from_csv(metadata_csv)
    print(f"  ✓ Loaded metadata for {len(metadata_df)} subjects")

    # Show sample of what we have
    print(f"\n  Sample metadata columns: {list(metadata_df.columns)}")
    if 'subject_id' in metadata_df.columns:
        print(f"  Sample subject IDs: {metadata_df['subject_id'].head(3).tolist()}")

    # Get population scans without metadata
    print(f"\n🔍 Finding population scans without metadata...")
    scans = get_population_scans_without_metadata(dataset_source)
    print(f"  ✓ Found {len(scans)} scans missing metadata")

    if len(scans) == 0:
        print(f"\n  ℹ️  No scans need updating. All done!")
        return {'updated': 0, 'failed': 0, 'skipped': 0}

    # Update statistics
    stats = {
        'total_scans': len(scans),
        'updated': 0,
        'skipped': 0,
        'failed': 0
    }

    print(f"\n{'='*70}")
    if dry_run:
        print("DRY RUN MODE - No updates will be made")
    else:
        print("UPDATING SCANS")
    print(f"{'='*70}\n")

    # Process each scan
    for i, scan in enumerate(scans, 1):
        subject_id = scan['subject_id']
        scan_id = scan['id']

        print(f"[{i}/{len(scans)}] Subject: {subject_id}")
        print(f"  Scan ID: {scan_id}")
        print(f"  Current: age={scan.get('age')}, sex={scan.get('sex')}")

        # Find matching metadata
        subject_meta = metadata_df[metadata_df['subject_id'] == subject_id]

        if len(subject_meta) == 0:
            print(f"  ⚠️  No metadata found in CSV for subject {subject_id}")
            stats['skipped'] += 1
            continue

        # Extract metadata
        meta_row = subject_meta.iloc[0]
        age = meta_row.get('age')
        sex = meta_row.get('sex', 'U')
        diagnosis = meta_row.get('diagnosis')

        print(f"  Found metadata: age={age}, sex={sex}, diagnosis={diagnosis}")

        if dry_run:
            print(f"  → Would update with this metadata")
            stats['updated'] += 1
        else:
            try:
                # Update the record
                updated = update_population_scan_metadata(
                    scan_id=scan_id,
                    age=age,
                    sex=sex,
                    diagnosis=diagnosis
                )

                if updated:
                    print(f"  ✓ Updated successfully")
                    stats['updated'] += 1
                else:
                    print(f"  ❌ Update failed (no record returned)")
                    stats['failed'] += 1

            except Exception as e:
                print(f"  ❌ Error: {str(e)}")
                stats['failed'] += 1

        print()

    # Print summary
    print(f"{'='*70}")
    print("BACKFILL COMPLETE")
    print(f"{'='*70}")
    print(f"Total scans: {stats['total_scans']}")
    print(f"Updated: {stats['updated']}")
    print(f"Skipped (no metadata): {stats['skipped']}")
    print(f"Failed: {stats['failed']}")
    print(f"{'='*70}\n")

    if stats['updated'] > 0 and not dry_run:
        print("✅ Metadata backfill complete!")
        print("   You can now run compute_population_norms to generate statistical norms.")

    return stats


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Backfill metadata for population scans',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be updated
  python -m functions.backfill_population_metadata \\
      research/input/datasets/oasis-1/selected_subjects.csv \\
      --dataset oasis-1 \\
      --dry-run

  # Actually update the records
  python -m functions.backfill_population_metadata \\
      research/input/datasets/oasis-1/selected_subjects.csv \\
      --dataset oasis-1

  # Update all datasets (not just oasis-1)
  python -m functions.backfill_population_metadata \\
      metadata/all_subjects.csv
        """
    )

    parser.add_argument(
        'metadata_csv',
        type=str,
        help='CSV file with subject metadata (age, sex, diagnosis)'
    )

    parser.add_argument(
        '--dataset',
        type=str,
        default=None,
        help='Filter by dataset source (e.g., oasis-1)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )

    args = parser.parse_args()

    try:
        result = backfill_population_metadata(
            metadata_csv=args.metadata_csv,
            dataset_source=args.dataset,
            dry_run=args.dry_run
        )

        if result['failed'] > 0:
            print(f"\n⚠️  Warning: {result['failed']} scans failed to update")
            os._exit(1)

        if result['updated'] == 0:
            print("\nℹ️  No scans were updated")
            os._exit(0)

        print("\n✅ Backfill complete!")

    except Exception as e:
        print(f"\n❌ Error during backfill: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)