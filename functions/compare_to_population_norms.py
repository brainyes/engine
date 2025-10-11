"""
Compare Individual Scan to Population Normative Data

This function compares a user's brain scan ROI volumes to population norms,
computing z-scores and percentiles for each brain region. This helps identify
regions that are unusually large or small compared to a healthy population.

The comparison is age and sex-matched when possible, falling back to combined
norms if specific stratification is not available.

Output:
- Z-scores: How many standard deviations from population mean
- Percentiles: Where the user ranks in the population (0-100)
- Outlier flags: ROIs outside 95% of population (|z| > 2)
- Visualization data: For charts and reports
"""

import os
import argparse
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from scipy import stats

from utilities.data import supabase
from utilities.supabase_utilities import get_roi_volumes
from utilities.volume_labels import volume_labels_dict

FUNCTION_NAME = "compare_to_population_norms"


def get_normative_data(
    roi_label: int,
    age: int,
    sex: str = 'U'
) -> Optional[Dict]:
    """
    Get normative data for a specific ROI, age, and sex

    Args:
        roi_label: Harvard-Oxford atlas label
        age: Age in years
        sex: 'M' (male), 'F' (female), or 'U' (unknown/combined)

    Returns:
        Dictionary with normative statistics, or None if not found
    """

    # Try exact match first (age bin + sex)
    response = supabase.table('normative_brain_data')\
        .select('*')\
        .eq('roi_label', roi_label)\
        .lte('age_min', age)\
        .gte('age_max', age)\
        .eq('sex', sex)\
        .execute()

    if response.data and len(response.data) > 0:
        return response.data[0]

    # Fallback to combined sex if sex-specific not found
    if sex != 'U':
        response = supabase.table('normative_brain_data')\
            .select('*')\
            .eq('roi_label', roi_label)\
            .lte('age_min', age)\
            .gte('age_max', age)\
            .eq('sex', 'U')\
            .execute()

        if response.data and len(response.data) > 0:
            return response.data[0]

    return None


def calculate_z_score(value: float, mean: float, std: float) -> float:
    """
    Calculate z-score (standard deviations from mean)

    Args:
        value: Observed value
        mean: Population mean
        std: Population standard deviation

    Returns:
        Z-score
    """
    if std == 0:
        return 0.0
    return (value - mean) / std


def calculate_percentile_from_z(z_score: float) -> int:
    """
    Calculate percentile rank from z-score using standard normal distribution

    Args:
        z_score: Z-score

    Returns:
        Percentile (0-100)
    """
    percentile = stats.norm.cdf(z_score) * 100
    return int(round(percentile))


def is_outlier(z_score: float, threshold: float = 2.0) -> bool:
    """
    Determine if a value is an outlier based on z-score

    Args:
        z_score: Z-score
        threshold: Z-score threshold (default: 2.0 = outside 95%)

    Returns:
        True if outlier
    """
    return abs(z_score) > threshold


def compare_to_population_norms(
    nifti_file_id: str,
    age: Optional[int] = None,
    sex: str = 'U',
    outlier_threshold: float = 2.0,
    save_to_db: bool = True
) -> Dict:
    """
    Compare individual scan ROI volumes to population norms

    Args:
        nifti_file_id: ID of NIFTI file to compare
        age: Age in years (if None, will try to get from metadata)
        sex: 'M', 'F', or 'U' (unknown/combined)
        outlier_threshold: Z-score threshold for outliers (default: 2.0)
        save_to_db: Save comparison results to database

    Returns:
        Dictionary with comparison results and statistics
    """

    print(f"\n{'='*70}")
    print(f"COMPARE TO POPULATION NORMS")
    print(f"{'='*70}")
    print(f"NIFTI File ID: {nifti_file_id}")
    print(f"Age: {age or 'Unknown'}")
    print(f"Sex: {sex}")
    print(f"Outlier threshold: {outlier_threshold} SD")
    print(f"{'='*70}\n")

    # Get user's ROI volumes
    print("📊 Fetching user's ROI volumes...")
    user_volumes = get_roi_volumes(nifti_file_id)

    if not user_volumes:
        print("  ❌ No ROI volumes found for this scan")
        print("     Make sure the scan has been processed through the pipeline:")
        print(f"     python -m functions.calculate_roi_volumes {nifti_file_id}")
        return {'comparisons': [], 'outliers': []}

    print(f"  ✓ Found {len(user_volumes)} ROI volumes")

    # Get age from metadata if not provided
    if age is None:
        # Try to get from population_scans table
        pop_scan = supabase.table('population_scans')\
            .select('age, sex')\
            .eq('nifti_file_id', nifti_file_id)\
            .maybe_single()\
            .execute()

        if pop_scan.data:
            age = pop_scan.data.get('age')
            sex = pop_scan.data.get('sex', sex)
            print(f"  ℹ️  Retrieved metadata: age={age}, sex={sex}")

    if age is None:
        print("  ⚠️  Warning: Age not provided. Using age-agnostic norms may be less accurate.")
        age = 50  # Default fallback

    # Compare each ROI to norms
    print(f"\n🔍 Comparing ROIs to population norms...")

    comparisons = []
    outliers = []
    norms_found = 0
    norms_missing = 0

    for roi_label, user_volume in user_volumes.items():
        # Convert roi_label to int (handle string floats like '1.0')
        roi_label_int = int(float(roi_label))
        roi_name = volume_labels_dict.get(roi_label_int, f"ROI_{roi_label_int}")

        # Get normative data
        norm_data = get_normative_data(roi_label_int, age, sex)

        if norm_data is None:
            norms_missing += 1
            continue

        norms_found += 1

        # Calculate comparison statistics
        z = calculate_z_score(user_volume, norm_data['mean'], norm_data['std'])
        percentile = calculate_percentile_from_z(z)
        is_outlier_flag = is_outlier(z, outlier_threshold)

        comparison = {
            'nifti_file_id': nifti_file_id,
            'roi_label': roi_label_int,
            'roi_name': roi_name,
            'user_volume': float(user_volume),
            'norm_mean': float(norm_data['mean']),
            'norm_std': float(norm_data['std']),
            'norm_p10': float(norm_data.get('p10', 0)),
            'norm_p25': float(norm_data.get('p25', 0)),
            'norm_p50': float(norm_data.get('p50', 0)),
            'norm_p75': float(norm_data.get('p75', 0)),
            'norm_p90': float(norm_data.get('p90', 0)),
            'z_score': float(z),
            'percentile': int(percentile),
            'is_outlier': is_outlier_flag,
            'age_bin': f"{norm_data['age_min']}-{norm_data['age_max']}",
            'sex_used': norm_data['sex'],
            'sample_size': norm_data.get('sample_size', 0)
        }

        comparisons.append(comparison)

        if is_outlier_flag:
            outliers.append(comparison)

    print(f"  ✓ Compared {norms_found} ROIs")

    if norms_missing > 0:
        print(f"  ⚠️  {norms_missing} ROIs skipped (no matching norms)")

    # Save to database if requested
    if save_to_db and len(comparisons) > 0:
        print(f"\n💾 Saving {len(comparisons)} comparisons to database...")

        # Delete existing comparisons for this scan
        supabase.table('population_comparisons')\
            .delete()\
            .eq('nifti_file_id', nifti_file_id)\
            .execute()

        # Insert new comparisons in batches
        batch_size = 500
        for i in range(0, len(comparisons), batch_size):
            batch = comparisons[i:i + batch_size]
            supabase.table('population_comparisons').insert(batch).execute()

        print(f"  ✓ Saved to database")

    # Print summary
    print(f"\n{'='*70}")
    print("COMPARISON RESULTS")
    print(f"{'='*70}")
    print(f"Total ROIs compared: {len(comparisons)}")
    print(f"Outliers found: {len(outliers)} ({len(outliers)/max(len(comparisons),1)*100:.1f}%)")

    if len(outliers) > 0:
        print(f"\n⚠️  Outlier ROIs (|z-score| > {outlier_threshold}):")
        print(f"{'ROI Name':<30} {'Volume':>10} {'Mean':>10} {'Z-Score':>10} {'%ile':>6}")
        print("-" * 70)

        # Sort by absolute z-score
        outliers_sorted = sorted(outliers, key=lambda x: abs(x['z_score']), reverse=True)

        for comp in outliers_sorted[:10]:  # Show top 10
            print(f"{comp['roi_name']:<30} "
                  f"{comp['user_volume']:>10.1f} "
                  f"{comp['norm_mean']:>10.1f} "
                  f"{comp['z_score']:>+10.2f} "
                  f"{comp['percentile']:>6}%")

        if len(outliers) > 10:
            print(f"... and {len(outliers) - 10} more outliers")

    # Categorize results
    very_low = len([c for c in comparisons if c['percentile'] < 5])
    low = len([c for c in comparisons if 5 <= c['percentile'] < 25])
    normal = len([c for c in comparisons if 25 <= c['percentile'] <= 75])
    high = len([c for c in comparisons if 75 < c['percentile'] <= 95])
    very_high = len([c for c in comparisons if c['percentile'] > 95])

    print(f"\nPercentile Distribution:")
    print(f"  Very Low (<5%): {very_low}")
    print(f"  Low (5-25%): {low}")
    print(f"  Normal (25-75%): {normal}")
    print(f"  High (75-95%): {high}")
    print(f"  Very High (>95%): {very_high}")

    print(f"\n{'='*70}\n")

    return {
        'nifti_file_id': nifti_file_id,
        'age': age,
        'sex': sex,
        'total_rois': len(comparisons),
        'outliers_count': len(outliers),
        'comparisons': comparisons,
        'outliers': outliers,
        'distribution': {
            'very_low': very_low,
            'low': low,
            'normal': normal,
            'high': high,
            'very_high': very_high
        }
    }


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Compare individual brain scan to population normative data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare scan for 45-year-old male
  python -m functions.compare_to_population_norms FILE_ID --age 45 --sex M

  # Compare without age/sex (uses combined norms)
  python -m functions.compare_to_population_norms FILE_ID

  # Use stricter outlier threshold (3 SD)
  python -m functions.compare_to_population_norms FILE_ID --age 60 --sex F --threshold 3.0

  # Don't save to database (just display results)
  python -m functions.compare_to_population_norms FILE_ID --age 50 --no-save

Requirements:
  - Population norms must be computed first (compute_population_norms)
  - User's scan must have ROI volumes calculated
  - normative_brain_data table must have age-stratified norms

Interpretation:
  - Z-score: How many standard deviations from mean
    - Positive: Larger than average
    - Negative: Smaller than average
    - |z| > 2: Outside 95% of population (potential outlier)

  - Percentile: Where you rank (0-100)
    - 50%: Exactly average
    - <25%: Below average
    - >75%: Above average
        """
    )

    parser.add_argument(
        'file_id',
        type=str,
        help='NIFTI file ID to compare'
    )

    parser.add_argument(
        '--age',
        type=int,
        default=None,
        help='Age in years (for age-matched comparison)'
    )

    parser.add_argument(
        '--sex',
        type=str,
        default='U',
        choices=['M', 'F', 'U'],
        help='Sex: M (male), F (female), U (unknown/combined)'
    )

    parser.add_argument(
        '--threshold',
        type=float,
        default=2.0,
        help='Z-score threshold for outliers (default: 2.0 = 95%%)'
    )

    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Do not save results to database'
    )

    args = parser.parse_args()

    try:
        result = compare_to_population_norms(
            nifti_file_id=args.file_id,
            age=args.age,
            sex=args.sex,
            outlier_threshold=args.threshold,
            save_to_db=not args.no_save
        )

        if result['total_rois'] == 0:
            print("\n⚠️  No comparisons could be made.")
            print("   Check that:")
            print("   1. The scan has ROI volumes calculated")
            print("   2. Population norms exist for this age/sex")
            os._exit(1)

        print("\n✅ Comparison complete!")

        if result['outliers_count'] > 0:
            print(f"\n⚠️  Found {result['outliers_count']} outlier ROIs - see details above")

    except Exception as e:
        print(f"\n❌ Error during comparison: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
