"""
Compute Population Norms for Global Brain Measures

This function computes statistical norms (mean, std, percentiles) for global brain
measures (total brain volume, cortex, white matter) from population scans.

These norms are stored in the same normative_brain_data table as ROI norms,
using special ROI label values (996-999) to distinguish them.

Input: Processed population scans with FreeSurfer global measures
Output: Normative statistics in normative_brain_data table
"""

import os
import argparse
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from postgrest.exceptions import APIError
from utilities.data import supabase
from utilities.population_utilities import (
    GLOBAL_MEASURE_ROI_LABELS,
    GLOBAL_MEASURE_DISPLAY_NAMES,
    GLOBAL_MEASURE_ATLAS_NAME
)
from functions.compute_population_norms import (
    create_age_bins,
    assign_age_bin,
    compute_statistics
)

FUNCTION_NAME = "compute_population_norms_global"


def get_population_scans_with_global_measures(
    dataset_name: str = None,
    min_age: int = None,
    max_age: int = None
) -> pd.DataFrame:
    """
    Get population scans with their FreeSurfer global measures

    Args:
        dataset_name: Filter by dataset (None = all datasets)
        min_age: Minimum age (inclusive)
        max_age: Maximum age (inclusive)

    Returns:
        DataFrame with columns: nifti_file_id, age, sex, dataset_source, measure_name, value
    """
    print("📥 Fetching population scans with global measures...")

    # Get population scans metadata
    query = supabase.table('population_scans').select('*')

    if dataset_name:
        query = query.eq('dataset_source', dataset_name)

    if min_age is not None:
        query = query.gte('age', min_age)

    if max_age is not None:
        query = query.lte('age', max_age)

    scans_response = query.execute()

    if not scans_response.data:
        print("  ⚠️  No population scans found")
        return pd.DataFrame()

    scans_df = pd.DataFrame(scans_response.data)
    print(f"  ✓ Found {len(scans_df)} population scans")

    # Filter out scans without age/sex
    before_count = len(scans_df)
    scans_df = scans_df.dropna(subset=['age', 'sex'])
    after_count = len(scans_df)

    if before_count > after_count:
        print(f"  ℹ️  Filtered out {before_count - after_count} scans without age/sex")

    # Get global measures for these scans
    nifti_file_ids = scans_df['nifti_file_id'].tolist()

    def fetch_measures_for_ids(ids: List[str]) -> List[Dict]:
        if not ids:
            return []

        try:
            response = supabase.table('freesurfer_global_measures')\
                .select('*')\
                .in_('nifti_file_id', ids)\
                .execute()
            return response.data or []
        except APIError as err:
            if len(ids) == 1:
                raise

            mid = len(ids) // 2
            print(f"  ⚠️  Batch of {len(ids)} IDs caused {err.code or 'API'} error. Splitting and retrying...")
            return fetch_measures_for_ids(ids[:mid]) + fetch_measures_for_ids(ids[mid:])

    # Fetch in smaller batches to avoid URL limits (PostgREST GET)
    batch_size = 150
    all_measures = []

    for i in range(0, len(nifti_file_ids), batch_size):
        batch = nifti_file_ids[i:i + batch_size]
        all_measures.extend(fetch_measures_for_ids(batch))

    if not all_measures:
        print("  ⚠️  No global measures found for population scans")
        return pd.DataFrame()

    measures_df = pd.DataFrame(all_measures)
    print(f"  ✓ Retrieved {len(measures_df)} global measure records")

    # Merge scans with measures
    merged_df = measures_df.merge(
        scans_df[['nifti_file_id', 'age', 'sex', 'dataset_source']],
        on='nifti_file_id'
    )

    print(f"  ✓ Merged data: {len(merged_df)} measure records with demographics")

    return merged_df


def compute_population_norms_global(
    dataset_name: str = None,
    min_samples: int = 30,
    age_bin_width: int = 10,
    compute_combined_sex: bool = True,
    measures_to_compute: List[str] = None,
    dry_run: bool = False
) -> Dict:
    """
    Compute population normative data for global brain measures

    Args:
        dataset_name: Filter by specific dataset (None = all datasets)
        min_samples: Minimum sample size to compute norms for a stratum
        age_bin_width: Width of age bins in years (default: 10)
        compute_combined_sex: Also compute sex-agnostic norms (sex='U')
        measures_to_compute: List of measure names to compute (None = all)
        dry_run: If True, compute but don't save to database

    Returns:
        Dictionary with statistics about computed norms
    """

    print(f"\n{'='*70}")
    print(f"COMPUTE POPULATION NORMS FOR GLOBAL BRAIN MEASURES")
    print(f"{'='*70}")
    print(f"Dataset filter: {dataset_name or 'All datasets'}")
    print(f"Minimum sample size: {min_samples}")
    print(f"Age bin width: {age_bin_width} years")
    print(f"Dry run: {dry_run}")
    print(f"{'='*70}\n")

    # Default to all available global measures
    if measures_to_compute is None:
        measures_to_compute = list(GLOBAL_MEASURE_ROI_LABELS.keys())

    print(f"Computing norms for measures: {', '.join(measures_to_compute)}")

    # Step 1: Get population scans with global measures
    data_df = get_population_scans_with_global_measures(dataset_name)

    if len(data_df) == 0:
        print("❌ No population scan data found. Cannot compute norms.")
        return {'norms_computed': 0}

    # Print dataset summary
    unique_scans = data_df['nifti_file_id'].nunique()
    print(f"\n📊 Population Dataset Summary:")
    print(f"  Total scans: {unique_scans}")
    print(f"  Age range: {data_df['age'].min():.0f} - {data_df['age'].max():.0f} years")
    print(f"  Sex distribution:")
    print(f"    Male: {len(data_df[data_df['sex'] == 'M']['nifti_file_id'].unique())}")
    print(f"    Female: {len(data_df[data_df['sex'] == 'F']['nifti_file_id'].unique())}")

    datasets = data_df['dataset_source'].unique()
    print(f"  Datasets: {', '.join(datasets)}")

    # Filter to only measures we're computing
    data_df = data_df[data_df['measure_name'].isin(measures_to_compute)]
    print(f"\n  Measure records after filtering: {len(data_df)}")
    print(f"  Unique measures: {data_df['measure_name'].nunique()}")
    for measure in data_df['measure_name'].unique():
        count = len(data_df[data_df['measure_name'] == measure])
        print(f"    {measure}: {count} records")

    # Step 2: Create age bins
    age_bins = create_age_bins(
        min_age=int(data_df['age'].min()),
        max_age=int(data_df['age'].max()) + 1,
        bin_width=age_bin_width
    )

    print(f"\n  Age bins: {len(age_bins)}")
    for age_min, age_max in age_bins:
        count = len(data_df[(data_df['age'] >= age_min) & (data_df['age'] < age_max)]['nifti_file_id'].unique())
        print(f"    {age_min}-{age_max}: {count} scans")

    # Step 3: Assign age bins
    data_df['age_bin'] = data_df['age'].apply(lambda age: assign_age_bin(age, age_bins))
    data_df = data_df.dropna(subset=['age_bin'])

    # Step 4: Compute norms for each stratum (age_bin × sex × measure)
    print(f"\n🔢 Computing normative statistics...")

    normative_records = []
    strata_computed = 0
    strata_skipped = 0

    # Get unique measures
    measures = sorted(data_df['measure_name'].unique())

    for measure_name in measures:
        measure_data = data_df[data_df['measure_name'] == measure_name]

        # Get ROI label for this measure
        roi_label = GLOBAL_MEASURE_ROI_LABELS.get(measure_name)
        if roi_label is None:
            print(f"  ⚠️  Unknown measure: {measure_name}, skipping")
            continue

        display_name = GLOBAL_MEASURE_DISPLAY_NAMES.get(measure_name, measure_name)

        for age_min, age_max in age_bins:
            age_data = measure_data[(measure_data['age_bin'] == (age_min, age_max))]

            # Compute for each sex
            for sex in ['M', 'F']:
                sex_data = age_data[age_data['sex'] == sex]
                values = sex_data['value'].values

                if len(values) >= min_samples:
                    stats = compute_statistics(values)

                    if stats:
                        record = {
                            'structure_name': display_name,
                            'roi_label': roi_label,
                            'age_min': age_min,
                            'age_max': age_max,
                            'sex': sex,
                            'atlas_name': GLOBAL_MEASURE_ATLAS_NAME,
                            'mean': stats['mean'],
                            'std': stats['std'],
                            'p10': stats['p10'],
                            'p25': stats['p25'],
                            'p50': stats['p50'],
                            'p75': stats['p75'],
                            'p90': stats['p90'],
                            'sample_size': stats['sample_size'],
                            'dataset_sources': list(datasets),
                            'computed_at': datetime.now().isoformat(),
                            'unit': 'mm³',
                            'source': f'Computed from {unique_scans} scans across {len(datasets)} dataset(s)'
                        }

                        normative_records.append(record)
                        strata_computed += 1
                else:
                    strata_skipped += 1

            # Compute combined sex if requested
            if compute_combined_sex:
                combined_data = age_data[age_data['sex'].isin(['M', 'F', 'U'])]
                values = combined_data['value'].values

                if len(values) >= min_samples:
                    stats = compute_statistics(values)

                    if stats:
                        record = {
                            'structure_name': display_name,
                            'roi_label': roi_label,
                            'age_min': age_min,
                            'age_max': age_max,
                            'sex': 'U',  # Combined
                            'atlas_name': GLOBAL_MEASURE_ATLAS_NAME,
                            'mean': stats['mean'],
                            'std': stats['std'],
                            'p10': stats['p10'],
                            'p25': stats['p25'],
                            'p50': stats['p50'],
                            'p75': stats['p75'],
                            'p90': stats['p90'],
                            'sample_size': stats['sample_size'],
                            'dataset_sources': list(datasets),
                            'computed_at': datetime.now().isoformat(),
                            'unit': 'mm³',
                            'source': f'Computed from {unique_scans} scans across {len(datasets)} dataset(s)'
                        }

                        normative_records.append(record)
                        strata_computed += 1

    print(f"  ✓ Computed norms for {strata_computed} strata")
    print(f"  ℹ️  Skipped {strata_skipped} strata (insufficient samples)")

    # Step 5: Save to database
    if not dry_run and len(normative_records) > 0:
        print(f"\n💾 Saving {len(normative_records)} normative records to database...")

        # Delete existing norms for these global measures (if filtering by dataset)
        if dataset_name:
            print(f"  Clearing existing global measure norms for dataset: {dataset_name}")
            for roi_label in GLOBAL_MEASURE_ROI_LABELS.values():
                try:
                    supabase.table('normative_brain_data')\
                        .delete()\
                        .eq('roi_label', roi_label)\
                        .contains('dataset_sources', [dataset_name])\
                        .execute()
                except Exception as e:
                    print(f"  Warning: Could not clear old norms for ROI {roi_label}: {e}")

        # Insert new norms in batches
        batch_size = 500
        for i in range(0, len(normative_records), batch_size):
            batch = normative_records[i:i + batch_size]
            supabase.table('normative_brain_data').insert(batch).execute()

        print(f"  ✓ Saved {len(normative_records)} records to database")

    # Print summary
    print(f"\n{'='*70}")
    print("COMPUTATION COMPLETE")
    print(f"{'='*70}")
    print(f"Population scans: {unique_scans}")
    print(f"Measures analyzed: {len(measures)}")
    print(f"Age bins: {len(age_bins)}")
    print(f"Normative records computed: {len(normative_records)}")
    print(f"{'='*70}\n")

    if not dry_run and len(normative_records) > 0:
        print("✅ Global measure norms computed and saved!")
        print("\n   Next step: Compare individual scans to norms:")
        print("   python -m functions.compare_to_population_norms NIFTI_FILE_ID --age 45 --sex M")

    return {
        'population_scans': unique_scans,
        'measures': len(measures),
        'age_bins': len(age_bins),
        'norms_computed': len(normative_records),
        'strata_skipped': strata_skipped
    }


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Compute population normative data for global brain measures',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compute norms for all global measures from all datasets
  python -m functions.compute_population_norms_global

  # Compute norms from specific dataset only
  python -m functions.compute_population_norms_global --dataset oasis-1

  # Use stricter sample size requirement
  python -m functions.compute_population_norms_global --min-samples 50

  # Custom age bins (5-year intervals)
  python -m functions.compute_population_norms_global --age-bin-width 5

  # Compute specific measures only
  python -m functions.compute_population_norms_global --measures BrainSeg Cortex

  # Dry run to see what would be computed
  python -m functions.compute_population_norms_global --dry-run

Global Measures:
  - BrainSeg: Total Brain Volume
  - Cortex: Total Cortical Volume
  - CerebralWhiteMatter: Total White Matter Volume
  - EstimatedTotalIntraCranialVol: Estimated Total Intracranial Volume

Requirements:
  - Population scans must be processed through FreeSurfer pipeline
  - Database must have population_scans and freesurfer_global_measures tables
  - FreeSurfer statistics must be parsed for all scans
        """
    )

    parser.add_argument(
        '--dataset',
        type=str,
        default=None,
        help='Filter by specific dataset (e.g., oasis-1, hcp)'
    )

    parser.add_argument(
        '--min-samples',
        type=int,
        default=30,
        help='Minimum sample size per stratum (default: 30)'
    )

    parser.add_argument(
        '--age-bin-width',
        type=int,
        default=10,
        help='Width of age bins in years (default: 10)'
    )

    parser.add_argument(
        '--no-combined-sex',
        action='store_true',
        help='Skip computing sex-agnostic norms (default: compute them)'
    )

    parser.add_argument(
        '--measures',
        nargs='+',
        default=None,
        help='Specific measures to compute (default: all available)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Compute but do not save to database'
    )

    args = parser.parse_args()

    try:
        result = compute_population_norms_global(
            dataset_name=args.dataset,
            min_samples=args.min_samples,
            age_bin_width=args.age_bin_width,
            compute_combined_sex=not args.no_combined_sex,
            measures_to_compute=args.measures,
            dry_run=args.dry_run
        )

        if result['norms_computed'] == 0:
            print("\n⚠️  No norms computed. Check that population scans exist and have FreeSurfer measures.")
            os._exit(1)

        print("\n✅ Global measure population norms computation complete!")

    except Exception as e:
        print(f"\n❌ Error during computation: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
