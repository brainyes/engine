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
from utilities.supabase_utilities import get_roi_volumes, get_user_profile
from utilities.volume_labels import get_region_name
from utilities.population_utilities import GLOBAL_MEASURE_ROI_LABELS, GLOBAL_MEASURE_DISPLAY_NAMES

FUNCTION_NAME = "compare_to_population_norms"


def get_normative_data(
    roi_label: int,
    age: int,
    sex: str = 'U',
    atlas_name: str = 'hcpex'
) -> Optional[Dict]:
    """
    Get normative data for a specific ROI, age, sex, and atlas

    Args:
        roi_label: Atlas-specific ROI label
        age: Age in years
        sex: 'M' (male), 'F' (female), or 'U' (unknown/combined)
        atlas_name: Name of the atlas (default: 'hcpex')

    Returns:
        Dictionary with normative statistics, or None if not found
    """

    # Try exact match first (age bin + sex + atlas)
    response = supabase.table('normative_brain_data')\
        .select('*')\
        .eq('roi_label', roi_label)\
        .eq('atlas_name', atlas_name)\
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
            .eq('atlas_name', atlas_name)\
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


def get_global_measures(nifti_file_id: str, measures_to_get: List[str] = None) -> Dict[str, float]:
    """
    Get user's global brain measures from FreeSurfer

    Args:
        nifti_file_id: ID of NIFTI file
        measures_to_get: List of measure names to retrieve (None = all)

    Returns:
        Dictionary mapping measure_name to value
    """
    if measures_to_get is None:
        measures_to_get = list(GLOBAL_MEASURE_ROI_LABELS.keys())

    response = supabase.table('freesurfer_global_measures')\
        .select('*')\
        .eq('nifti_file_id', nifti_file_id)\
        .in_('measure_name', measures_to_get)\
        .execute()

    if not response.data:
        return {}

    return {item['measure_name']: item['value'] for item in response.data}


def compare_to_population_norms(
    nifti_file_id: str,
    age: Optional[int] = None,
    sex: Optional[str] = None,
    atlas_name: Optional[str] = None,
    outlier_threshold: float = 2.0,
    save_to_db: bool = True,
    include_global_measures: bool = True
) -> Dict:
    """
    Compare individual scan ROI volumes and global measures to population norms

    By default, compares ALL available atlases. Pass atlas_name to compare just one (for CLI/testing).

    Args:
        nifti_file_id: ID of NIFTI file to compare
        age: Age in years (if None, will fetch from user profile)
        sex: 'M', 'F', or 'U' (if None, will fetch from user profile)
        atlas_name: Optional - Name of specific atlas (default: None = all atlases)
        outlier_threshold: Z-score threshold for outliers (default: 2.0)
        save_to_db: Save comparison results to database
        include_global_measures: Also compare global brain measures (default: True)

    Returns:
        Dictionary with comparison results and statistics
    """

    # If no specific atlas requested, process all
    if atlas_name is None:
        from utilities.atlas_config import list_atlases
        all_atlases = list_atlases()
        results = {}

        print(f"Comparing to population norms for all {len(all_atlases)} atlases: {', '.join(all_atlases.keys())}")

        for atlas_key in all_atlases.keys():
            print(f"\n--- Comparing with atlas: {atlas_key} ---")
            results[atlas_key] = compare_to_population_norms(
                nifti_file_id=nifti_file_id,
                age=age,
                sex=sex,
                atlas_name=atlas_key,  # Recursive call with specific atlas
                outlier_threshold=outlier_threshold,
                save_to_db=save_to_db,
                include_global_measures=include_global_measures
            )

        return results

    # Get user profile if age/sex not explicitly provided
    user_profile = None
    if age is None or sex is None:
        print("👤 Fetching user profile...")
        user_profile = get_user_profile(nifti_file_id)

        if user_profile:
            # Use profile values if not explicitly provided
            if age is None:
                age = user_profile.get('age')
                age_source = user_profile.get('age_source', 'profile')
                if age:
                    print(f"  ✓ Age from user profile: {age} ({age_source})")

            if sex is None:
                sex = user_profile.get('sex', 'U')
                if sex and sex != 'U':
                    print(f"  ✓ Sex from user profile: {sex}")

            health_status = user_profile.get('health_status')
            if health_status:
                print(f"  ℹ️  Health status: {health_status}")
        else:
            print("  ⚠️  Could not fetch user profile")

    # Set defaults if still None
    if sex is None:
        sex = 'U'

    print(f"\n{'='*70}")
    print(f"COMPARE TO POPULATION NORMS")
    print(f"{'='*70}")
    print(f"NIFTI File ID: {nifti_file_id}")
    print(f"Atlas: {atlas_name}")
    print(f"Age: {age or 'Unknown'}")
    print(f"Sex: {sex}")
    print(f"Outlier threshold: {outlier_threshold} SD")
    print(f"{'='*70}\n")

    # Get user's ROI volumes (filtered by atlas)
    print(f"📊 Fetching user's ROI volumes ({atlas_name})...")
    user_volumes = get_roi_volumes(nifti_file_id, atlas_name=atlas_name)

    if not user_volumes:
        print("  ❌ No ROI volumes found for this scan")
        print("     Make sure the scan has been processed through the pipeline:")
        print(f"     python -m functions.calculate_roi_volumes {nifti_file_id}")
        return {'comparisons': [], 'outliers': []}

    print(f"  ✓ Found {len(user_volumes)} ROI volumes")

    # Final fallback: try population_scans table (for population dataset scans)
    if age is None:
        pop_scan = supabase.table('population_scans')\
            .select('age, sex')\
            .eq('nifti_file_id', nifti_file_id)\
            .maybe_single()\
            .execute()

        if pop_scan.data:
            age = pop_scan.data.get('age')
            sex = pop_scan.data.get('sex', sex)
            print(f"  ℹ️  Retrieved from population_scans: age={age}, sex={sex}")

    if age is None:
        print("  ⚠️  Warning: Age not provided in user profile. Using age-agnostic norms may be less accurate.")
        print("  💡 Tip: Update your profile at /dashboard/settings to enable age-matched comparisons")
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
        # Use atlas-aware region name lookup
        roi_name = get_region_name(roi_label_int, atlas_name)

        # Get normative data
        norm_data = get_normative_data(roi_label_int, age, sex, atlas_name)

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
            'atlas_name': atlas_name,
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

    # Compare global measures if requested
    global_measures_found = 0
    global_measures_missing = 0

    if include_global_measures:
        print(f"\n🔍 Comparing global brain measures to population norms...")

        # Get user's global measures
        user_global_measures = get_global_measures(nifti_file_id)

        if user_global_measures:
            print(f"  ✓ Found {len(user_global_measures)} global measures")

            for measure_name, user_value in user_global_measures.items():
                # Get ROI label for this measure
                roi_label = GLOBAL_MEASURE_ROI_LABELS.get(measure_name)
                if roi_label is None:
                    continue

                display_name = GLOBAL_MEASURE_DISPLAY_NAMES.get(measure_name, measure_name)

                # Get normative data for this global measure
                norm_data = get_normative_data(roi_label, age, sex, atlas_name)

                if norm_data is None:
                    global_measures_missing += 1
                    continue

                global_measures_found += 1

                # Calculate comparison statistics
                z = calculate_z_score(user_value, norm_data['mean'], norm_data['std'])
                percentile = calculate_percentile_from_z(z)
                is_outlier_flag = is_outlier(z, outlier_threshold)

                comparison = {
                    'nifti_file_id': nifti_file_id,
                    'roi_label': roi_label,
                    'roi_name': display_name,
                    'atlas_name': atlas_name,
                    'user_volume': float(user_value),
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

            print(f"  ✓ Compared {global_measures_found} global measures")

            if global_measures_missing > 0:
                print(f"  ⚠️  {global_measures_missing} global measures skipped (no matching norms)")
        else:
            print(f"  ℹ️  No global measures found for this scan (FreeSurfer may not have been run)")

    # Save to database if requested
    if save_to_db and len(comparisons) > 0:
        print(f"\n💾 Saving {len(comparisons)} comparisons to database...")

        # Delete existing comparisons for this scan and atlas
        supabase.table('population_comparisons')\
            .delete()\
            .eq('nifti_file_id', nifti_file_id)\
            .eq('atlas_name', atlas_name)\
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

    result = {
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

    # Add global measures info if they were included
    if include_global_measures:
        result['global_measures_compared'] = global_measures_found
        result['global_measures_missing'] = global_measures_missing

    return result


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Compare individual brain scan to population normative data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare scan (age/sex fetched from user profile automatically)
  python -m functions.compare_to_population_norms FILE_ID

  # Override age/sex from command line
  python -m functions.compare_to_population_norms FILE_ID --age 45 --sex M

  # Use stricter outlier threshold (3 SD)
  python -m functions.compare_to_population_norms FILE_ID --threshold 3.0

  # Don't save to database (just display results)
  python -m functions.compare_to_population_norms FILE_ID --no-save

Requirements:
  - Population norms must be computed first (compute_population_norms)
  - User's scan must have ROI volumes calculated
  - normative_brain_data table must have age-stratified norms

User Profile:
  - Age, sex, and health status are automatically fetched from user profile
  - If not in profile, uses --age and --sex CLI arguments
  - If neither provided, uses age-agnostic combined norms
  - Update profile at /dashboard/settings for best accuracy

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
        help='Age in years (optional - fetched from user profile if not provided)'
    )

    parser.add_argument(
        '--sex',
        type=str,
        default=None,
        choices=['M', 'F', 'U'],
        help='Sex: M (male), F (female), U (unknown) - fetched from user profile if not provided'
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

    parser.add_argument(
        '--no-global-measures',
        action='store_true',
        help='Skip comparison of global brain measures (default: include them)'
    )

    args = parser.parse_args()

    try:
        # Always compare against all atlases (atlas_name=None)
        result = compare_to_population_norms(
            nifti_file_id=args.file_id,
            age=args.age,
            sex=args.sex,
            atlas_name=None,  # Process all atlases
            outlier_threshold=args.threshold,
            save_to_db=not args.no_save,
            include_global_measures=not args.no_global_measures
        )

        # Aggregate results from all atlases
        total_rois = sum(r.get('total_rois', 0) for r in result.values())
        total_outliers = sum(r.get('outliers_count', 0) for r in result.values())

        if total_rois == 0:
            print("\n⚠️  No comparisons could be made across any atlas.")
            print("   Check that:")
            print("   1. The scan has ROI volumes calculated")
            print("   2. Population norms exist for this age/sex")
            os._exit(1)

        print("\n✅ Comparison complete across all atlases!")
        print(f"   Total ROIs compared: {total_rois}")

        if total_outliers > 0:
            print(f"\n⚠️  Found {total_outliers} outlier ROIs total - see details above")

    except Exception as e:
        print(f"\n❌ Error during comparison: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
