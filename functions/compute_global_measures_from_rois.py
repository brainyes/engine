"""
Derive global brain measures (BrainSeg, Cortex, White Matter, eTIV) from ROI volumes.

This is used to populate freesurfer_global_measures for scans that did not run
through the expensive FreeSurfer pipeline (e.g., population datasets processed
with the v2 atlas workflow). It estimates:

- Total brain volume (BrainSeg) from the sum of all HCPex ROI volumes.
- Total cortical volume from Harvard-Oxford ROI volumes (fallbacks to HCPex).
- Total white matter volume as the residual between total brain and cortex.
- Estimated total intracranial volume (eTIV) from population_scans.icv, if present.

All derived values are inserted into freesurfer_global_measures so downstream
systems (norm computation, dashboard comparisons) can treat them the same way
as FreeSurfer outputs.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from utilities.data import supabase
from utilities.supabase_utilities import get_roi_volumes
from utilities.population_utilities import GLOBAL_MEASURE_DISPLAY_NAMES
from utilities.volume_labels import ATLAS_LABELS

HCPEX_ATLAS = 'hcpex'
HARVARD_OXFORD_ATLAS = 'harvard-oxford'

NON_CORTICAL_KEYWORDS = [
    'Hippocampus',
    'Amygdala',
    'Thalamus',
    'Putamen',
    'Pallidum',
    'Accumbens',
    'Cerebell',
    'Brain-Stem',
    'Brain_Stem',
    'BrainStem',
    'Ventricle',
    'White',
    'Mammillary',
    'Septal',
    'Nucleus',
    'Substantia',
    'Tegmenta',
    'Hypothalamus',
    'Claustrum',
    'Striatum',
    'Basal',
    'Dentate',
    'Pineal',
    'Cerebellar',
    'PeriCallosal'
]

MEASURE_METADATA = {
    'BrainSeg': {'field': 'BrainSegVol', 'display': 'Total Brain Volume'},
    'Cortex': {'field': 'CortexVol', 'display': 'Total Cortical Volume'},
    'CerebralWhiteMatter': {'field': 'CerebralWhiteMatterVol', 'display': 'Total White Matter Volume'},
    'EstimatedTotalIntraCranialVol': {'field': 'eTIV', 'display': 'Estimated Total Intracranial Volume'}
}


def _sum_volume_dict(volume_dict: Dict[Iterable, float]) -> float:
    """Sum helper that tolerates None/str values."""
    total = 0.0

    for value in volume_dict.values():
        if value is None:
            continue
        total += float(value)

    return total


def _estimate_cortical_volume_from_hcpex(hcpex_volumes: Dict[int, float]) -> float:
    """Fallback: approximate cortical volume by filtering HCPex labels."""
    atlas_labels = ATLAS_LABELS.get(HCPEX_ATLAS, {})
    cortical_volume = 0.0

    for raw_label, value in hcpex_volumes.items():
        label = int(raw_label)
        name = atlas_labels.get(label, '')

        if not name:
            continue

        if any(keyword in name for keyword in NON_CORTICAL_KEYWORDS):
            continue

        cortical_volume += float(value)

    return cortical_volume


def _get_population_icv(nifti_file_id: str) -> Optional[float]:
    """Fetch ICV stored in population_scans (if available)."""
    response = supabase.table('population_scans')\
        .select('icv')\
        .eq('nifti_file_id', nifti_file_id)\
        .maybe_single()\
        .execute()

    if response and response.data and response.data.get('icv'):
        return float(response.data['icv'])

    return None


def _get_existing_measure_names(nifti_file_id: str) -> List[str]:
    """Return list of global measure names already stored for this scan."""
    response = supabase.table('freesurfer_global_measures')\
        .select('measure_name')\
        .eq('nifti_file_id', nifti_file_id)\
        .execute()

    if not response.data:
        return []

    return [record['measure_name'] for record in response.data]


def compute_global_measure_values(nifti_file_id: str, verbose: bool = True) -> Optional[Dict[str, float]]:
    """
    Derive global brain measures from ROI volumes.

    Returns dict mapping measure_name -> value, or None if data missing.
    """
    hcpex_volumes = get_roi_volumes(nifti_file_id, HCPEX_ATLAS)
    if not hcpex_volumes:
        if verbose:
            print(f"  ⚠️  No {HCPEX_ATLAS} ROI volumes found. Cannot derive global measures.")
        return None

    total_brain_volume = _sum_volume_dict(hcpex_volumes)

    ho_volumes = get_roi_volumes(nifti_file_id, HARVARD_OXFORD_ATLAS)
    cortical_volume = _sum_volume_dict(ho_volumes)

    if cortical_volume == 0:
        cortical_volume = _estimate_cortical_volume_from_hcpex(hcpex_volumes)
        if verbose:
            print(f"  ℹ️  Harvard-Oxford volumes missing. Estimated cortex from {HCPEX_ATLAS} atlas: {cortical_volume:,.0f} mm³")

    white_matter_volume = max(total_brain_volume - cortical_volume, 0.0)

    icv = _get_population_icv(nifti_file_id)
    if icv is None:
        icv = total_brain_volume
        if verbose:
            print("  ℹ️  ICV not stored for this scan. Using total brain volume as fallback.")

    return {
        'BrainSeg': total_brain_volume,
        'Cortex': cortical_volume,
        'CerebralWhiteMatter': white_matter_volume,
        'EstimatedTotalIntraCranialVol': icv
    }


def compute_global_measures_from_rois(
    nifti_file_id: str,
    overwrite: bool = False,
    verbose: bool = True
) -> Dict[str, int]:
    """
    Compute and persist global measures for a scan.

    Args:
        nifti_file_id: Scan identifier.
        overwrite: If True, replace existing measures. Otherwise skip those already present.
        verbose: Print progress logs.

    Returns summary dict.
    """
    if verbose:
        print(f"\n🧮 Deriving global measures from ROI volumes for {nifti_file_id}...")

    derived_values = compute_global_measure_values(nifti_file_id, verbose=verbose)
    if not derived_values:
        return {'inserted': 0, 'skipped': len(MEASURE_METADATA), 'nifti_file_id': nifti_file_id}

    existing_names = set(_get_existing_measure_names(nifti_file_id))
    records_to_upsert = []
    skipped = 0

    for measure_name, value in derived_values.items():
        if not overwrite and measure_name in existing_names:
            skipped += 1
            continue

        metadata = MEASURE_METADATA[measure_name]
        records_to_upsert.append({
            'nifti_file_id': nifti_file_id,
            'measure_name': measure_name,
            'measure_field': metadata['field'],
            'value': float(value),
            'unit': 'mm³',
            'source_file': 'roi_volumes',
            'created_at': datetime.now().isoformat()
        })

    if records_to_upsert:
        supabase.table('freesurfer_global_measures')\
            .upsert(records_to_upsert, on_conflict='nifti_file_id,measure_name')\
            .execute()
        if verbose:
            print(f"  ✓ Stored {len(records_to_upsert)} global measures")
    else:
        if verbose:
            print("  ℹ️  All global measures already exist. Nothing to insert.")

    return {
        'inserted': len(records_to_upsert),
        'skipped': skipped,
        'nifti_file_id': nifti_file_id
    }


def _fetch_population_scan_ids(dataset: Optional[str] = None) -> List[str]:
    """Return list of nifti_file_ids from population_scans (optionally filtered by dataset)."""
    ids: List[str] = []
    page = 0
    page_size = 500

    while True:
        query = supabase.table('population_scans')\
            .select('nifti_file_id')\
            .order('nifti_file_id')\
            .range(page * page_size, page * page_size + page_size - 1)

        if dataset:
            query = query.eq('dataset_source', dataset)

        response = query.execute()
        rows = response.data or []

        if not rows:
            break

        ids.extend(row['nifti_file_id'] for row in rows if row.get('nifti_file_id'))

        if len(rows) < page_size:
            break
        page += 1

    return ids


def run_cli():
    parser = argparse.ArgumentParser(
        description='Derive global brain measures from ROI volumes and store them in freesurfer_global_measures.'
    )
    parser.add_argument('--file-id', dest='file_id', help='Specific NIFTI file ID to process')
    parser.add_argument('--dataset', dest='dataset', help='Process all population scans from this dataset')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing global measures')

    args = parser.parse_args()

    if args.file_id:
        result = compute_global_measures_from_rois(args.file_id, overwrite=args.overwrite)
        print(result)
        return

    dataset_name = args.dataset
    nifti_ids = _fetch_population_scan_ids(dataset_name)

    if not nifti_ids:
        scope = dataset_name or 'all datasets'
        print(f"⚠️  No population scans found for {scope}.")
        return

    print(f"Processing {len(nifti_ids)} population scans{' for ' + dataset_name if dataset_name else ''}...")
    inserted_total = 0
    skipped_total = 0

    for idx, nifti_id in enumerate(nifti_ids, start=1):
        print(f"\n[{idx}/{len(nifti_ids)}] {nifti_id}")
        result = compute_global_measures_from_rois(
            nifti_id,
            overwrite=args.overwrite,
            verbose=True
        )
        inserted_total += result['inserted']
        skipped_total += result['skipped']

    print("\n✅ Global measure derivation complete!")
    print(f"  Records inserted: {inserted_total}")
    print(f"  Measures skipped: {skipped_total}")


if __name__ == '__main__':
    run_cli()
