"""
Compute Population Normative Data from Processed Scans

This function computes statistical norms (mean, std, percentiles) from a
population of processed brain scans. The norms are stratified by age group
and sex to enable accurate comparisons with individual scans.

Input: Processed scans in population_scans table with ROI volumes
Output: Normative statistics in normative_brain_data table

Statistical measures computed:
- Mean and standard deviation
- Percentiles: 10th, 25th, 50th (median), 75th, 90th
- Sample size and dataset provenance

Stratification:
- Age bins: 20-30, 30-40, 40-50, 50-60, 60-70, 70-80, 80+
- Sex: M (Male), F (Female), U (Combined/Unknown)
"""

import os
import argparse
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from utilities.data import supabase
from utilities.volume_labels import get_region_name  # For structure_name field

FUNCTION_NAME = "compute_population_norms"

# Try to import scikit-learn for regression models (v2)
try:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️  scikit-learn not available, using simple stratification only (v1)")


def get_population_scans(dataset_name: str = None, min_age: int = None, max_age: int = None) -> pd.DataFrame:
    """
    Get all population scans with metadata from database

    Args:
        dataset_name: Filter by dataset (None = all datasets)
        min_age: Minimum age (inclusive)
        max_age: Maximum age (inclusive)

    Returns:
        DataFrame with columns: nifti_file_id, dataset_source, subject_id, age, sex
    """
    print("📥 Fetching population scans from database...")

    # Fetch all records by paginating (PostgREST default limit is 1000)
    all_data = []
    offset = 0
    batch_size = 1000

    while True:
        query = supabase.table('population_scans').select('*').range(offset, offset + batch_size - 1)

        if dataset_name:
            query = query.eq('dataset_source', dataset_name)

        if min_age is not None:
            query = query.gte('age', min_age)

        if max_age is not None:
            query = query.lte('age', max_age)

        response = query.execute()

        if not response.data:
            break

        all_data.extend(response.data)

        if len(response.data) < batch_size:
            break

        offset += batch_size

    if not all_data:
        print("  ⚠️  No population scans found")
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    print(f"  ✓ Found {len(df)} population scans")

    # Filter out scans without age/sex
    before_count = len(df)
    df = df.dropna(subset=['age', 'sex'])
    after_count = len(df)

    if before_count > after_count:
        print(f"  ℹ️  Filtered out {before_count - after_count} scans without age/sex")

    return df


def get_roi_volumes_for_scans(nifti_file_ids: List[str]) -> pd.DataFrame:
    """
    Get ROI volumes for a list of NIFTI files

    Args:
        nifti_file_ids: List of NIFTI file IDs

    Returns:
        DataFrame with columns: nifti_file_id, label, volume, atlas_name
    """
    print(f"📊 Fetching ROI volumes for {len(nifti_file_ids)} scans...")

    # Fetch in batches - with increased Supabase limit (100K), we can fetch more per batch
    # Each scan has ~426 ROIs, so batch of 200 scans = ~85K rows (under 100K limit)
    batch_size = 200
    all_volumes = []

    for i in range(0, len(nifti_file_ids), batch_size):
        batch = nifti_file_ids[i:i + batch_size]
        print(f"  Fetching batch {i // batch_size + 1}/{(len(nifti_file_ids) + batch_size - 1) // batch_size}... ", end='', flush=True)

        try:
            # With 100K limit, most batches will fit in one query
            response = supabase.table('roi_volumes')\
                .select('nifti_file_id, label, volume, atlas_name')\
                .in_('nifti_file_id', batch)\
                .execute()

            all_volumes.extend(response.data)
            print(f"✓ ({len(response.data)} rows)")

        except Exception as e:
            print(f"✗ Error: {e}")
            print(f"  Retrying with single file...")
            # If batch fails, try one file at a time
            for file_id in batch:
                response = supabase.table('roi_volumes')\
                    .select('nifti_file_id, label, volume, atlas_name')\
                    .eq('nifti_file_id', file_id)\
                    .execute()
                all_volumes.extend(response.data)

    df = pd.DataFrame(all_volumes)
    print(f"  ✓ Retrieved {len(df)} ROI volume measurements")

    # Check if we have atlas_name column
    if 'atlas_name' not in df.columns and len(df) > 0:
        print(f"  ⚠️  Warning: atlas_name column missing from roi_volumes")
        print(f"     Available columns: {list(df.columns)}")

    return df


def create_age_bins(min_age: int = 20, max_age: int = 100, bin_width: int = 10) -> List[Tuple[int, int]]:
    """
    Create age bins for stratification

    Args:
        min_age: Minimum age
        max_age: Maximum age
        bin_width: Width of each bin in years

    Returns:
        List of (age_min, age_max) tuples
    """
    bins = []
    for age_start in range(min_age, max_age, bin_width):
        age_end = min(age_start + bin_width, max_age)
        bins.append((age_start, age_end))

    return bins


def assign_age_bin(age: int, age_bins: List[Tuple[int, int]]) -> Tuple[int, int]:
    """
    Assign an age to its bin

    Args:
        age: Age in years
        age_bins: List of age bins

    Returns:
        (age_min, age_max) tuple for the bin, or None if age outside all bins
    """
    for age_min, age_max in age_bins:
        if age_min <= age < age_max:
            return (age_min, age_max)

    return None


def compute_statistics(values: np.ndarray) -> Dict:
    """
    Compute statistical measures from array of values

    Args:
        values: Array of numeric values

    Returns:
        Dictionary with mean, std, percentiles
    """
    if len(values) == 0:
        return None

    # For single sample, std is 0 (no variance)
    if len(values) == 1:
        value = float(values[0])
        return {
            'mean': value,
            'std': 0.0,  # No variance with single sample
            'p10': value,
            'p25': value,
            'p50': value,
            'p75': value,
            'p90': value,
            'sample_size': 1
        }

    return {
        'mean': float(np.mean(values)),
        'std': float(np.std(values, ddof=1)),  # Sample std
        'p10': float(np.percentile(values, 10)),
        'p25': float(np.percentile(values, 25)),
        'p50': float(np.percentile(values, 50)),  # Median
        'p75': float(np.percentile(values, 75)),
        'p90': float(np.percentile(values, 90)),
        'sample_size': len(values)
    }


def fit_icv_regression_model(df: pd.DataFrame) -> Optional[Dict]:
    """
    Fit regression model: volume ~ age + age² + sex + ICV

    This accounts for the fact that larger brains (higher ICV) have
    larger regional volumes. The residuals from this model represent
    anatomical variation independent of overall brain size.

    Args:
        df: DataFrame with columns: volume, age, sex, icv

    Returns:
        Dictionary with:
        - coefficients: Model coefficients
        - residual_std: Standard deviation of residuals
        - r_squared: Proportion of variance explained
        - None if insufficient data or sklearn not available
    """
    if not SKLEARN_AVAILABLE:
        return None

    # Filter out rows without ICV
    df_with_icv = df.dropna(subset=['icv'])

    if len(df_with_icv) < 10:  # Need minimum data for regression
        return None

    # Build design matrix
    X = pd.DataFrame({
        'age': df_with_icv['age'],
        'age_squared': df_with_icv['age'] ** 2,
        'sex_M': (df_with_icv['sex'] == 'M').astype(int),
        'sex_F': (df_with_icv['sex'] == 'F').astype(int),
        'icv': df_with_icv['icv']
    })

    y = df_with_icv['volume'].values

    # Fit model with error handling for numerical issues
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Suppress sklearn warnings
            model = LinearRegression()
            model.fit(X, y)

            # Get predictions and residuals
            y_pred = model.predict(X)
            residuals = y - y_pred
            residual_std = np.std(residuals, ddof=X.shape[1])  # Adjust for DOF

            # R-squared
            r_squared = r2_score(y, y_pred)

            # Check for numerical issues
            if not np.isfinite(r_squared) or not np.isfinite(residual_std):
                return None

    except (ValueError, RuntimeWarning):
        return None

    # Package coefficients
    coefficients = {
        'intercept': float(model.intercept_),
        'age': float(model.coef_[0]),
        'age_squared': float(model.coef_[1]),
        'sex_M': float(model.coef_[2]),
        'sex_F': float(model.coef_[3]),
        'icv': float(model.coef_[4])
    }

    return {
        'coefficients': coefficients,
        'residual_std': float(residual_std),
        'r_squared': float(r_squared),
        'sample_size': len(df_with_icv),
        'icv_mean': float(df_with_icv['icv'].mean()),
        'icv_std': float(df_with_icv['icv'].std())
    }


def compute_population_norms(
    dataset_name: str = None,
    min_samples: int = 30,
    age_bin_width: int = 10,
    compute_combined_sex: bool = True,
    use_icv_regression: bool = True,
    dry_run: bool = False
) -> Dict:
    """
    Compute population normative data from processed scans

    Computes both v1 (simple stratification) and v2 (ICV-adjusted regression) models.

    Args:
        dataset_name: Filter by specific dataset (None = all datasets)
        min_samples: Minimum sample size to compute norms for a stratum
        age_bin_width: Width of age bins in years (default: 10)
        compute_combined_sex: Also compute sex-agnostic norms (sex='U')
        use_icv_regression: Attempt ICV-adjusted regression models (v2) if data available
        dry_run: If True, compute but don't save to database

    Returns:
        Dictionary with statistics about computed norms
    """

    print(f"\n{'='*70}")
    print(f"COMPUTE POPULATION NORMATIVE DATA")
    print(f"{'='*70}")
    print(f"Dataset filter: {dataset_name or 'All datasets'}")
    print(f"Minimum sample size: {min_samples}")
    print(f"Age bin width: {age_bin_width} years")
    print(f"Dry run: {dry_run}")
    print(f"{'='*70}\n")

    # Step 1: Get population scans
    scans_df = get_population_scans(dataset_name)

    if len(scans_df) == 0:
        print("❌ No population scans found. Cannot compute norms.")
        return {'norms_computed': 0}

    # Print dataset summary
    print(f"\n📊 Population Dataset Summary:")
    print(f"  Total scans: {len(scans_df)}")
    print(f"  Age range: {scans_df['age'].min():.0f} - {scans_df['age'].max():.0f} years")
    print(f"  Sex distribution:")
    print(f"    Male: {len(scans_df[scans_df['sex'] == 'M'])}")
    print(f"    Female: {len(scans_df[scans_df['sex'] == 'F'])}")
    print(f"    Unknown: {len(scans_df[scans_df['sex'] == 'U'])}")

    datasets = scans_df['dataset_source'].unique()
    print(f"  Datasets: {', '.join(datasets)}")

    # Step 2: Get ROI volumes for all scans
    nifti_file_ids = scans_df['nifti_file_id'].tolist()
    volumes_df = get_roi_volumes_for_scans(nifti_file_ids)

    if len(volumes_df) == 0:
        print("❌ No ROI volumes found. Make sure scans have been processed.")
        return {'norms_computed': 0}

    # Drop atlas_name from scans_df if it exists (it shouldn't be there)
    print(f"\n🔍 DEBUG - Before merge:")
    print(f"  volumes_df columns: {list(volumes_df.columns)}")
    print(f"  scans_df columns: {list(scans_df.columns)}")

    if 'atlas_name' in scans_df.columns:
        print(f"  ⚠️  WARNING: atlas_name column found in scans_df! Dropping it...")
        scans_df = scans_df.drop(columns=['atlas_name'])
        print(f"  scans_df columns after drop: {list(scans_df.columns)}")

    # Merge scans with volumes
    data_df = volumes_df.merge(scans_df, on='nifti_file_id')

    print(f"\n🔍 DEBUG - After merge:")
    print(f"  data_df columns: {list(data_df.columns)}")
    print(f"  data_df shape: {data_df.shape}")
    if 'atlas_name' in data_df.columns:
        print(f"  Unique atlas_name values: {sorted(data_df['atlas_name'].unique())}")
    else:
        print(f"  ⚠️  atlas_name column missing after merge!")

    print(f"\n  Total ROI measurements: {len(data_df)}")
    print(f"  Unique ROIs: {data_df['label'].nunique()}")

    # Check if atlas_name column exists after merge
    if 'atlas_name' not in data_df.columns:
        print(f"\n  ❌ Error: atlas_name column missing after merge!")
        print(f"     volumes_df columns: {list(volumes_df.columns)}")
        print(f"     scans_df columns: {list(scans_df.columns)}")
        print(f"     data_df columns: {list(data_df.columns)}")
        return {'norms_computed': 0}

    # Step 3: Create age bins
    age_bins = create_age_bins(
        min_age=int(scans_df['age'].min()),
        max_age=int(scans_df['age'].max()) + 1,
        bin_width=age_bin_width
    )

    print(f"\n  Age bins: {len(age_bins)}")
    for age_min, age_max in age_bins:
        count = len(scans_df[(scans_df['age'] >= age_min) & (scans_df['age'] < age_max)])
        print(f"    {age_min}-{age_max}: {count} scans")

    # Step 4: Assign age bins to each measurement
    data_df['age_bin'] = data_df['age'].apply(lambda age: assign_age_bin(age, age_bins))
    data_df = data_df.dropna(subset=['age_bin'])

    # Step 5: Compute norms for each stratum (age_bin × sex × roi_label)
    print(f"\n🔢 Computing normative statistics...")

    normative_records = []
    strata_computed = 0
    strata_skipped = 0

    # Get unique ROI labels and atlases
    roi_labels = sorted(data_df['label'].unique())
    atlases = sorted(data_df['atlas_name'].unique())

    print(f"  Atlases: {', '.join(atlases)}")

    # Compute norms for each atlas separately
    for atlas_name in atlases:
        atlas_data = data_df[data_df['atlas_name'] == atlas_name]
        atlas_roi_labels = sorted(atlas_data['label'].unique())

        # DEBUG: Log atlas data size
        print(f"\n  📊 Processing atlas: {atlas_name}")
        print(f"     Total rows in atlas_data: {len(atlas_data)}")
        print(f"     Unique labels in atlas: {len(atlas_roi_labels)}")

        for roi_label in atlas_roi_labels:
            roi_data = atlas_data[atlas_data['label'] == roi_label]

            # Convert label to integer
            roi_label_int = int(float(roi_label))
            # Note: structure_name is redundant (can be derived from roi_label + atlas_name)
            # but kept for database compatibility. To remove, make column nullable in DB first.
            structure_name = get_region_name(roi_label_int, atlas_name)

            # DEBUG: Log label 7 specifically for both atlases
            if roi_label_int == 7:
                print(f"\n  🔍 DEBUG - Label 7 for {atlas_name}:")
                print(f"     Rows for label 7: {len(roi_data)}")
                print(f"     Volume range: {roi_data['volume'].min():.2f} - {roi_data['volume'].max():.2f} mm³")
                print(f"     Volume mean: {roi_data['volume'].mean():.2f} mm³")
                print(f"     Atlas name values in roi_data: {roi_data['atlas_name'].unique()}")

                # If we see large volumes, investigate further
                if roi_data['volume'].max() > 10000:
                    print(f"     ⚠️  ANOMALY: Large volumes detected!")
                    print(f"     Sample nifti_file_ids: {roi_data['nifti_file_id'].head(3).tolist()}")
                    print(f"     Sample volumes: {roi_data['volume'].head(10).tolist()}")
                    print(f"     Label values: {roi_data['label'].unique()}")
                    print(f"     Label dtypes: {roi_data['label'].dtype}")

            for age_min, age_max in age_bins:
                age_data = roi_data[(roi_data['age_bin'] == (age_min, age_max))]

                # Compute for each sex
                for sex in ['M', 'F']:
                    sex_data = age_data[age_data['sex'] == sex]
                    volumes = sex_data['volume'].values

                    # DEBUG: Log label 7 computation details
                    if roi_label_int == 7 and len(volumes) > 0:
                        print(f"     Age {age_min}-{age_max}, Sex {sex}: {len(volumes)} samples, mean={volumes.mean():.2f}")

                    if len(volumes) >= min_samples:
                        stats = compute_statistics(volumes)

                        if stats:
                            # Try ICV-adjusted regression if requested
                            model_version = 'v1_simple'
                            model_coefficients = None
                            residual_std = None

                            if use_icv_regression and SKLEARN_AVAILABLE:
                                # Build dataframe for regression
                                regression_df = sex_data[['volume', 'age', 'sex', 'icv']].copy()
                                regression_model = fit_icv_regression_model(regression_df)

                                if regression_model and regression_model['r_squared'] > 0.1:
                                    # Use regression model if it explains >10% variance
                                    model_version = 'v2_icv_adjusted'
                                    model_coefficients = regression_model['coefficients']
                                    residual_std = regression_model['residual_std']

                            record = {
                                'structure_name': structure_name,  # Redundant but required by DB
                                'roi_label': roi_label_int,
                                'age_min': age_min,
                                'age_max': age_max,
                                'sex': sex,
                                'atlas_name': atlas_name,
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
                                'source': f'Computed from {len(scans_df)} scans across {len(datasets)} dataset(s)',
                                'model_version': model_version,
                                'model_coefficients': model_coefficients,
                                'residual_std': residual_std
                            }

                            normative_records.append(record)
                            strata_computed += 1
                    else:
                        strata_skipped += 1

                # Compute combined sex if requested
                if compute_combined_sex:
                    combined_data = age_data[age_data['sex'].isin(['M', 'F', 'U'])]
                    volumes = combined_data['volume'].values

                    if len(volumes) >= min_samples:
                        stats = compute_statistics(volumes)

                        if stats:
                            # Try ICV-adjusted regression if requested
                            model_version = 'v1_simple'
                            model_coefficients = None
                            residual_std = None

                            if use_icv_regression and SKLEARN_AVAILABLE:
                                regression_df = combined_data[['volume', 'age', 'sex', 'icv']].copy()
                                regression_model = fit_icv_regression_model(regression_df)

                                if regression_model and regression_model['r_squared'] > 0.1:
                                    model_version = 'v2_icv_adjusted'
                                    model_coefficients = regression_model['coefficients']
                                    residual_std = regression_model['residual_std']

                            record = {
                                'structure_name': structure_name,  # Redundant but required by DB
                                'roi_label': roi_label_int,
                                'age_min': age_min,
                                'age_max': age_max,
                                'sex': 'U',  # Combined
                                'atlas_name': atlas_name,
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
                                'source': f'Computed from {len(scans_df)} scans across {len(datasets)} dataset(s)',
                                'model_version': model_version,
                                'model_coefficients': model_coefficients,
                                'residual_std': residual_std
                            }

                            normative_records.append(record)
                            strata_computed += 1

    print(f"  ✓ Computed norms for {strata_computed} strata")
    print(f"  ℹ️  Skipped {strata_skipped} strata (insufficient samples)")

    # Step 6: Save to database
    if not dry_run and len(normative_records) > 0:
        print(f"\n💾 Saving {len(normative_records)} normative records to database...")

        # Delete existing norms for these datasets (if filtering by dataset)
        if dataset_name:
            print(f"  Clearing existing norms for dataset: {dataset_name}")
            try:
                # Note: This requires dataset_sources column to be array type
                supabase.table('normative_brain_data').delete().contains('dataset_sources', [dataset_name]).execute()
                print(f"  ✓ Cleared existing records")
            except Exception as e:
                print(f"  ⚠️  Could not clear existing records: {str(e)}")
                print(f"  Will use upsert instead...")

        # Deduplicate records by unique key (roi_label, age_min, age_max, sex, atlas_name)
        # Keep the last occurrence if there are duplicates
        seen_keys = set()
        deduplicated_records = []

        for record in reversed(normative_records):
            key = (record['roi_label'], record['age_min'], record['age_max'], record['sex'], record['atlas_name'])
            if key not in seen_keys:
                seen_keys.add(key)
                deduplicated_records.append(record)

        deduplicated_records.reverse()  # Restore original order

        if len(deduplicated_records) < len(normative_records):
            print(f"  ℹ️  Deduplicated {len(normative_records) - len(deduplicated_records)} duplicate records")

        # Use upsert to insert or update records
        # The unique constraint is: (roi_label, age_min, age_max, sex, atlas_name)
        batch_size = 500
        for i in range(0, len(deduplicated_records), batch_size):
            batch = deduplicated_records[i:i + batch_size]
            print(f"  Upserting batch {i//batch_size + 1}/{(len(deduplicated_records)-1)//batch_size + 1}...")

            # Use upsert with on_conflict parameter
            # This will update existing records instead of failing
            supabase.table('normative_brain_data').upsert(
                batch,
                on_conflict='roi_label,age_min,age_max,sex,atlas_name'
            ).execute()

        print(f"  ✓ Saved {len(deduplicated_records)} records to database")

    # Print summary
    print(f"\n{'='*70}")
    print("COMPUTATION COMPLETE")
    print(f"{'='*70}")
    print(f"Population scans: {len(scans_df)}")
    print(f"ROIs analyzed: {len(roi_labels)}")
    print(f"Age bins: {len(age_bins)}")
    print(f"Normative records computed: {len(normative_records)}")
    print(f"{'='*70}\n")

    if not dry_run and len(normative_records) > 0:
        print("✅ Population norms computed and saved!")
        print("\n   Next step: Compare individual scans to norms:")
        print("   python -m functions.compare_to_population_norms NIFTI_FILE_ID --age 45 --sex M")

    return {
        'population_scans': len(scans_df),
        'roi_labels': len(roi_labels),
        'age_bins': len(age_bins),
        'norms_computed': len(normative_records),
        'strata_skipped': strata_skipped
    }


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Compute population normative data from processed brain scans',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compute norms from all datasets
  python -m functions.compute_population_norms

  # Compute norms from specific dataset only
  python -m functions.compute_population_norms --dataset oasis-1

  # Use stricter sample size requirement
  python -m functions.compute_population_norms --min-samples 50

  # Custom age bins (5-year intervals)
  python -m functions.compute_population_norms --age-bin-width 5

  # Dry run to see what would be computed
  python -m functions.compute_population_norms --dry-run

Requirements:
  - Population scans must be processed first (batch_process_population_dataset)
  - Database must have population_scans table with metadata
  - ROI volumes must be calculated for all scans
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
        '--dry-run',
        action='store_true',
        help='Compute but do not save to database'
    )

    args = parser.parse_args()

    try:
        result = compute_population_norms(
            dataset_name=args.dataset,
            min_samples=args.min_samples,
            age_bin_width=args.age_bin_width,
            compute_combined_sex=not args.no_combined_sex,
            dry_run=args.dry_run
        )

        if result['norms_computed'] == 0:
            print("\n⚠️  No norms computed. Check that population scans exist and have been processed.")
            os._exit(1)

        print("\n✅ Population norms computation complete!")

    except Exception as e:
        print(f"\n❌ Error during computation: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
