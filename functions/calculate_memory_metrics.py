"""
Calculate Memory System Metrics

Extracts and calculates memory-related metrics from FreeSurfer output:
- Hippocampal volumes (left, right, total)
- Symmetry scores
- Entorhinal cortex volumes
- Age-adjusted percentiles
- Population context

Stores results in memory_metrics table
"""

import os
from typing import Dict, Optional, Tuple
from utilities.data import supabase
from utilities.supabase_utilities import get_nifti_file
from functions.generate_normative_data import get_normative_range, calculate_percentile


def get_hippocampal_volumes(nifti_file_id: str) -> Dict[str, float]:
    """
    Extract hippocampal volumes from FreeSurfer subcortical segmentations

    Args:
        nifti_file_id: NIFTI file ID

    Returns:
        Dictionary with left, right, and total volumes in mm³
    """
    # Get left hippocampus
    left_result = supabase.schema('public').table('freesurfer_subcortical_segmentations')\
        .select('volume_mm3')\
        .eq('nifti_file_id', nifti_file_id)\
        .eq('structure_name', 'Left-Hippocampus')\
        .execute()

    # Get right hippocampus
    right_result = supabase.schema('public').table('freesurfer_subcortical_segmentations')\
        .select('volume_mm3')\
        .eq('nifti_file_id', nifti_file_id)\
        .eq('structure_name', 'Right-Hippocampus')\
        .execute()

    left_volume = left_result.data[0]['volume_mm3'] if left_result.data else 0
    right_volume = right_result.data[0]['volume_mm3'] if right_result.data else 0
    
    # Fallback to ROI volumes (HCPex or Harvard-Oxford) if FreeSurfer data is missing
    if left_volume == 0 and right_volume == 0:
        print("  ℹ️  FreeSurfer segmentation not found, checking ROI volumes...")
        from functions.calculate_roi_volumes import calculate_roi_volumes
        from utilities.supabase_utilities import get_roi_volumes
        
        # Try HCPex first
        hcpex_volumes = get_roi_volumes(nifti_file_id, 'hcpex')
        if hcpex_volumes:
            # HCPex labels for Hippocampus
            # Left Hippocampus: 80
            # Right Hippocampus: 260
            l_hippo_id = 80
            r_hippo_id = 260
            
            if l_hippo_id in hcpex_volumes:
                left_volume = hcpex_volumes[l_hippo_id]
            if r_hippo_id in hcpex_volumes:
                right_volume = hcpex_volumes[r_hippo_id]
                
            if left_volume > 0:
                print(f"  ✓ Found Hippocampus volumes in HCPex atlas (L: {left_volume:.0f}, R: {right_volume:.0f})")
            
        # If still 0, try Harvard-Oxford
        if left_volume == 0 and right_volume == 0:
            ho_volumes = get_roi_volumes(nifti_file_id, 'harvard-oxford')
            if ho_volumes:
                # Harvard-Oxford Subcortical labels
                # Left Hippocampus: 9
                # Right Hippocampus: 19 (Note: volume_labels.py says 19, not 20!)
                l_hippo_id = 9
                r_hippo_id = 19
                
                if l_hippo_id in ho_volumes:
                    left_volume = ho_volumes[l_hippo_id]
                if r_hippo_id in ho_volumes:
                    right_volume = ho_volumes[r_hippo_id]
                    
                if left_volume > 0:
                    print(f"  ✓ Found Hippocampus volumes in Harvard-Oxford atlas (L: {left_volume:.0f}, R: {right_volume:.0f})")

    total_volume = left_volume + right_volume

    return {
        'left': left_volume,
        'right': right_volume,
        'total': total_volume
    }


def calculate_symmetry_score(left_volume: float, right_volume: float) -> float:
    """
    Calculate hippocampal symmetry score

    Symmetry score = (left / (left + right)) * 100
    Perfect symmetry = 50%
    Range: 0-100%

    Args:
        left_volume: Left hippocampus volume
        right_volume: Right hippocampus volume

    Returns:
        Symmetry score (0-100)
    """
    if left_volume + right_volume == 0:
        return 50.0  # Default to balanced if no data

    symmetry = (left_volume / (left_volume + right_volume)) * 100
    return round(symmetry, 2)


def get_entorhinal_cortex_volume(nifti_file_id: str) -> float:
    """
    Extract entorhinal cortex volume from FreeSurfer cortical regions

    The entorhinal cortex is part of the parahippocampal gyrus.
    We'll sum both anterior divisions from both hemispheres.

    Args:
        nifti_file_id: NIFTI file ID

    Returns:
        Total entorhinal cortex volume in mm³
    """
    # Get parahippocampal gyrus anterior division (entorhinal cortex proxy)
    result = supabase.schema('public').table('freesurfer_cortical_regions')\
        .select('gray_vol')\
        .eq('nifti_file_id', nifti_file_id)\
        .like('structure_name', 'Parahippocampal Gyrus%anterior%')\
        .execute()

    total_volume = sum(region['gray_vol'] for region in result.data if region['gray_vol'])

    return total_volume


def get_temporal_lobe_volume(nifti_file_id: str) -> float:
    """
    Calculate total temporal lobe volume from cortical regions

    Includes all temporal gyri

    Args:
        nifti_file_id: NIFTI file ID

    Returns:
        Total temporal lobe volume in cm³
    """
    # Get all temporal regions
    result = supabase.schema('public').table('freesurfer_cortical_regions')\
        .select('gray_vol')\
        .eq('nifti_file_id', nifti_file_id)\
        .or_('structure_name.ilike.%Temporal%,structure_name.ilike.%temporal%')\
        .execute()

    total_volume_mm3 = sum(region['gray_vol'] for region in result.data if region['gray_vol'])

    # Convert to cm³
    return total_volume_mm3 / 1000


def get_prefrontal_volume(nifti_file_id: str) -> float:
    """
    Calculate total prefrontal regions volume

    Args:
        nifti_file_id: NIFTI file ID

    Returns:
        Total prefrontal volume in cm³
    """
    # Get frontal regions
    result = supabase.schema('public').table('freesurfer_cortical_regions')\
        .select('gray_vol')\
        .eq('nifti_file_id', nifti_file_id)\
        .or_('structure_name.ilike.%Frontal%,structure_name.ilike.%frontal%')\
        .execute()

    total_volume_mm3 = sum(region['gray_vol'] for region in result.data if region['gray_vol'])

    # Convert to cm³
    return total_volume_mm3 / 1000


def get_user_age_sex(nifti_file_id: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Get user age and sex from nifti file metadata

    Args:
        nifti_file_id: NIFTI file ID

    Returns:
        Tuple of (age, sex) where sex is 'M', 'F', or 'U'
    """
    nifti_file, _, _ = get_nifti_file(nifti_file_id)

    # Try to get age and sex from user metadata
    # This assumes these fields exist - you may need to adjust based on your schema
    age = nifti_file.get('user_age', None)
    sex = nifti_file.get('user_sex', 'U')

    return age, sex


def calculate_memory_metrics(nifti_file_id: str, age: int = None, sex: str = 'U') -> Dict:
    """
    Calculate comprehensive memory metrics for a user's MRI scan

    Args:
        nifti_file_id: NIFTI file ID
        age: Optional user age (if not in metadata)
        sex: Optional user sex ('M', 'F', 'U')

    Returns:
        Dictionary with all calculated metrics
    """
    print(f"📊 Calculating memory metrics for NIFTI: {nifti_file_id}")

    # Get user metadata if not provided
    if age is None or sex == 'U':
        file_age, file_sex = get_user_age_sex(nifti_file_id)
        age = age or file_age
        sex = sex if sex != 'U' else file_sex

    # Extract hippocampal volumes
    print("  → Extracting hippocampal volumes...")
    hippo_volumes = get_hippocampal_volumes(nifti_file_id)

    # Calculate symmetry
    print("  → Calculating symmetry score...")
    symmetry_score = calculate_symmetry_score(hippo_volumes['left'], hippo_volumes['right'])

    # Get entorhinal cortex
    print("  → Extracting entorhinal cortex volume...")
    entorhinal_volume = get_entorhinal_cortex_volume(nifti_file_id)

    # Get temporal lobe
    print("  → Calculating temporal lobe volume...")
    temporal_volume = get_temporal_lobe_volume(nifti_file_id)

    # Get prefrontal regions
    print("  → Calculating prefrontal volume...")
    prefrontal_volume = get_prefrontal_volume(nifti_file_id)

    # Calculate percentiles if age is available
    hippo_percentile = None
    entorhinal_percentile = None
    temporal_percentile = None
    prefrontal_percentile = None

    if age:
        print(f"  → Calculating percentiles for age {age}, sex {sex}...")

        # Hippocampus percentile
        hippo_norm = get_normative_range('Hippocampus', age, sex)
        if hippo_norm:
            hippo_percentile = calculate_percentile(
                hippo_volumes['total'],
                hippo_norm['mean'],
                hippo_norm['std']
            )

        # Entorhinal percentile
        entorhinal_norm = get_normative_range('Entorhinal_Cortex', age, sex)
        if entorhinal_norm:
            entorhinal_percentile = calculate_percentile(
                entorhinal_volume,
                entorhinal_norm['mean'],
                entorhinal_norm['std']
            )

        # Temporal lobe percentile
        temporal_norm = get_normative_range('Temporal_Lobe', age, sex)
        if temporal_norm:
            temporal_percentile = calculate_percentile(
                temporal_volume,
                temporal_norm['mean'],
                temporal_norm['std']
            )

        # Prefrontal percentile
        prefrontal_norm = get_normative_range('Prefrontal_Regions', age, sex)
        if prefrontal_norm:
            prefrontal_percentile = calculate_percentile(
                prefrontal_volume,
                prefrontal_norm['mean'],
                prefrontal_norm['std']
            )

    # Compile results
    metrics = {
        'nifti_file_id': nifti_file_id,
        'hippocampus_left': hippo_volumes['left'],
        'hippocampus_right': hippo_volumes['right'],
        'hippocampus_total': hippo_volumes['total'],
        'hippocampus_symmetry_score': symmetry_score,
        'hippocampus_percentile': hippo_percentile,
        'entorhinal_cortex_volume': entorhinal_volume,
        'entorhinal_percentile': entorhinal_percentile,
        'temporal_lobe_volume': temporal_volume,
        'temporal_percentile': temporal_percentile,
        'prefrontal_volume': prefrontal_volume,
        'prefrontal_percentile': prefrontal_percentile,
        'user_age': age,
        'user_sex': sex
    }

    # Store in database
    print("  → Storing metrics in database...")
    # Upsert (insert or update)
    result = supabase.schema('public').table('memory_metrics')\
        .upsert(metrics, on_conflict='nifti_file_id')\
        .execute()

    print(f"✅ Memory metrics calculated and stored!")
    print(f"   Hippocampus: {hippo_volumes['total']:.0f} mm³ (symmetry: {symmetry_score:.1f}%)")
    if hippo_percentile:
        print(f"   Percentile: {hippo_percentile}th")

    return metrics


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Calculate memory metrics for MRI scan')
    parser.add_argument('nifti_file_id', help='NIFTI file ID')
    parser.add_argument('--age', type=int, help='User age (optional)')
    parser.add_argument('--sex', choices=['M', 'F', 'U'], default='U', help='User sex (optional)')

    args = parser.parse_args()

    print("=== Memory Metrics Calculator ===\n")
    metrics = calculate_memory_metrics(
        args.nifti_file_id,
        age=args.age,
        sex=args.sex
    )

    print("\n" + "="*50)
    print("Results:")
    for key, value in metrics.items():
        if value is not None:
            print(f"  {key}: {value}")
