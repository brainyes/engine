import numpy as np
import nibabel as nib
import argparse
import os
from multiprocessing import Pool, cpu_count

from utilities.data import supabase
from utilities.supabase_utilities import get_nifti_file, get_user_meta, download_resampled_atlas


def calculate_roi_volumes(nifti_file_id, atlas_name=None):
    """
    Calculate ROI volumes for a NIFTI scan using brain atlases

    By default, processes ALL available atlases. Pass atlas_name to process just one (for CLI/testing).

    Args:
        nifti_file_id: ID of the NIFTI file to process
        atlas_name: Optional - Name of specific atlas to process (default: None = all atlases)
                   Available: 'harvard-oxford', 'hcpex'

    Returns:
        Dictionary with results for all atlases (or list for single atlas if atlas_name specified)

    Example:
        # Process all atlases (default)
        volumes = calculate_roi_volumes(nifti_id)
        # Returns: {'harvard-oxford': [...], 'hcpex': [...]}

        # Process specific atlas (for CLI/testing)
        volumes = calculate_roi_volumes(nifti_id, 'hcpex')
        # Returns: [{nifti_file_id, label, volume, atlas_name}, ...]
    """

    # If no specific atlas requested, process all
    if atlas_name is None:
        from utilities.atlas_config import list_atlases
        all_atlases = list_atlases()
        results = {}

        print(f"Calculating ROI volumes for all {len(all_atlases)} atlases: {', '.join(all_atlases.keys())}")

        for atlas_key in all_atlases.keys():
            print(f"\n--- Calculating volumes for atlas: {atlas_key} ---")
            try:
                results[atlas_key] = _calculate_volumes_single_atlas(nifti_file_id, atlas_key)
            except Exception as e:
                error_msg = str(e)
                if 'not_found' in error_msg or '404' in error_msg:
                    print(f"⏭️  Skipping {atlas_key} (resampled atlas not found - may not have been processed)")
                    continue
                else:
                    # Re-raise if it's not a missing file error
                    raise

        return results
    else:
        # Process single specific atlas (CLI usage)
        return _calculate_volumes_single_atlas(nifti_file_id, atlas_name)


def _process_roi_batch(args):
    """Process a batch of ROI labels in parallel"""
    labels, atlas_data, data, voxel_size = args
    results = {}
    for roi_label in labels:
        roi_mask = (atlas_data == roi_label)
        roi_voxel_count = np.sum(roi_mask & (data > 0))
        results[roi_label] = roi_voxel_count * voxel_size
    return results


def _calculate_volumes_single_atlas(nifti_file_id, atlas_name, use_parallel=True):
    """Helper function to calculate volumes for a single atlas"""
    print(f"Calculating ROI volumes using {atlas_name} atlas...")

    # Get the user's original nifti file metadata
    response = supabase.schema("public").rpc("get_file_type_among_children", {"p_nifti_file_id": nifti_file_id,
                                                                             "p_file_type": "nii"}).single().execute()
    user_nifti_file = response.data

    # Try to use FreeSurfer's brain.mgz (preferred - matches atlas resampling)
    # Fall back to user's upload if FreeSurfer hasn't been processed
    user_nifti_path = None
    source = None

    try:
        # Try FreeSurfer brain.mgz (preferred - properly oriented)
        print("📥 Checking for FreeSurfer brain.mgz...")
        brain_mgz_data = supabase.storage.from_("freesurfer-outputs").download(
            f"{nifti_file_id}/mri/brain.mgz"
        )

        # Save to temp file
        import tempfile
        user_nifti_path = os.path.join(tempfile.gettempdir(), f"brain_{nifti_file_id}.mgz")
        with open(user_nifti_path, 'wb') as f:
            f.write(brain_mgz_data)

        source = "freesurfer_brain.mgz"
        print("✅ Using FreeSurfer brain.mgz (matches atlas resampling)")

    except Exception as e:
        print(f"ℹ️  FreeSurfer brain.mgz not available, using original upload")
        # Fall back to user's original upload
        _, _, user_nifti_path = get_nifti_file(user_nifti_file, True)
        source = "user_upload"

    user_nifti = nib.load(user_nifti_path)

    # Download resampled atlas from storage (for the specified atlas)
    atlas_sampled_nifti_gz_path = download_resampled_atlas(user_nifti_file['user_id'], nifti_file_id, atlas_name)
    atlas_sampled_nifti = nib.load(atlas_sampled_nifti_gz_path)

    # Try to get voxel_size from usermeta, or compute from affine matrix
    voxel_size = get_user_meta(user_nifti_file['user_id'], 'voxel_size')
    if voxel_size is None:
        # Compute voxel size directly from NIFTI affine matrix
        voxel_size = np.abs(np.linalg.det(user_nifti.affine[:3, :3]))
        print(f"ℹ️  Voxel size not in usermeta, computed from affine: {voxel_size}")

    data = user_nifti.get_fdata()
    atlas_data = atlas_sampled_nifti.get_fdata()

    # Round atlas data to nearest integer (resampling can create floating point values)
    atlas_data = np.round(atlas_data).astype(int)

    # Get all unique labels (excluding background)
    unique_labels = np.unique(atlas_data)
    unique_labels = unique_labels[unique_labels != 0]  # Remove background
    total_regions = len(unique_labels)

    print(f"Processing {total_regions} brain regions...")

    # Use parallel processing for large atlases (>100 regions)
    if use_parallel and total_regions > 100:
        n_cores = cpu_count()  # Use all available cores
        print(f"🚀 Using {n_cores} CPU cores for parallel processing")

        # Split labels into chunks for each core
        chunk_size = max(1, total_regions // n_cores)
        label_chunks = [unique_labels[i:i + chunk_size] for i in range(0, total_regions, chunk_size)]

        # Create arguments for each worker
        worker_args = [(chunk, atlas_data, data, voxel_size) for chunk in label_chunks]

        # Process in parallel
        with Pool(n_cores) as pool:
            results = pool.map(_process_roi_batch, worker_args)

        # Merge results
        roi_volumes = {}
        for result in results:
            roi_volumes.update(result)

        print(f"✓ Completed processing {total_regions} regions")
    else:
        # Sequential processing for small atlases
        roi_volumes = {}
        for idx, roi_label in enumerate(unique_labels, 1):
            roi_mask = (atlas_data == roi_label)
            roi_voxel_count = np.sum(roi_mask & (data > 0))
            roi_volumes[roi_label] = roi_voxel_count * voxel_size

            # Progress indicator every 10%
            if idx % max(1, total_regions // 10) == 0 or idx == total_regions:
                progress_pct = (idx / total_regions) * 100
                print(f"  Progress: {idx}/{total_regions} regions ({progress_pct:.1f}%)")


    # save roi_volumes for the user's nifti file (with atlas_name)
    roi_volume_records = [
        {
            "nifti_file_id": nifti_file_id,
            "label": int(roi_label),  # Convert numpy int64 to Python int
            "volume": float(roi_volume),
            "atlas_name": atlas_name
        }
        for roi_label, roi_volume in roi_volumes.items()
    ]
    response = (supabase.schema("public").table("roi_volumes")
                .upsert(roi_volume_records, on_conflict="nifti_file_id, label, atlas_name").execute())

    print(f"✅ Saved {len(roi_volume_records)} ROI volumes for {atlas_name} atlas")
    return response.data


# example:
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Calculate brain region volumes from your uploaded NIFTI scan')
    parser.add_argument('file_id', help='File ID from the upload_nifti output')
    parser.add_argument('--atlas', dest='atlas_name', default=None,
                       choices=['harvard-oxford', 'hcpex'],
                       help='Atlas to use (default: all atlases)')

    args = parser.parse_args()

    print("=== ROI VOLUME CALCULATION ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    if args.atlas_name:
        print(f"Atlas: {args.atlas_name}")
    else:
        print(f"Atlas: All available atlases")
    print("This will measure the volume of each brain region...\n")

    try:
        result = calculate_roi_volumes(args.file_id, args.atlas_name)
        print("\n=== VOLUME CALCULATION COMPLETE ===")

        # Handle different return types (single atlas = list, all atlases = dict)
        if isinstance(result, dict):
            # Multiple atlases processed
            total_regions = sum(len(regions) for regions in result.values())
            print(f"✅ Calculated volumes for {total_regions} brain regions across {len(result)} atlases")
            print("📊 Results saved to database.")
            print("\n🧠 Summary by atlas:")
            for atlas_name, regions in result.items():
                print(f"   {atlas_name}: {len(regions)} regions")
        else:
            # Single atlas processed
            print(f"✅ Calculated volumes for {len(result)} brain regions using {args.atlas_name}")
            print("📊 Results saved to database.")
            print("\n🧠 Sample results (first 5 regions):")
            for i, region in enumerate(result[:5]):
                print(f"   Region {region['label']}: {region['volume']:.2f} cubic mm")
            if len(result) > 5:
                print(f"   ... and {len(result) - 5} more regions")

        print(f"\n🎉 Analysis complete! Your brain scan has been fully processed.")

    except Exception as e:
        print(f"❌ Error during volume calculation: {str(e)}")
        print("Please check your file ID and ensure atlas resampling was completed first.")
        os._exit(1)

    # Force exit to prevent hanging
    os._exit(0)
