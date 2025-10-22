import os
import argparse

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import plotting
from nilearn.image import resample_img

from utilities.options import silent_run, output_dir, save_assets
from utilities.data import supabase
from utilities.supabase_utilities import get_nifti_file, upload_resampled_atlas
from utilities.utilities import prefix_file_in_path
from utilities.atlas_config import get_atlas_file_path


def resample_atlas_for_user_nifti(nifti_file_id, atlas_name=None, population_mode=False):
    """
    Resample brain atlases to match the resolution and orientation of a user's NIFTI scan

    By default, processes ALL available atlases. Pass atlas_name to process just one (for CLI/testing).

    Args:
        nifti_file_id: ID of the NIFTI file to process
        atlas_name: Optional - Name of specific atlas to process (default: None = all atlases)
                   Available: 'harvard-oxford', 'hcpex'
        population_mode: If True, skip FreeSurfer atlas (for population datasets without FreeSurfer outputs)

    Returns:
        Dictionary with results for all atlases (or single atlas if atlas_name specified)

    Example:
        # Process all atlases (default)
        result = resample_atlas_for_user_nifti(nifti_id)
        # Returns: {'harvard-oxford': {...}, 'hcpex': {...}}

        # Process specific atlas (for CLI/testing)
        result = resample_atlas_for_user_nifti(nifti_id, 'hcpex')
        # Returns: {storage_path, voxel_size, user_meta, atlas_name}

        # Process population dataset (skip FreeSurfer, use MNI atlases only)
        result = resample_atlas_for_user_nifti(nifti_id, population_mode=True)
        # Returns: {'harvard-oxford': {...}, 'hcpex': {...}}
    """

    # If no specific atlas requested, process all
    if atlas_name is None:
        from utilities.atlas_config import list_atlases
        all_atlases = list_atlases()
        results = {}

        # Filter out FreeSurfer if in population mode
        if population_mode:
            all_atlases = {k: v for k, v in all_atlases.items() if k != 'freesurfer'}
            print(f"🧬 Population mode: Processing {len(all_atlases)} MNI-based atlases (skipping FreeSurfer)")
        else:
            print(f"Processing all {len(all_atlases)} atlases: {', '.join(all_atlases.keys())}")

        for atlas_key in all_atlases.keys():
            print(f"\n--- Processing atlas: {atlas_key} ---")
            results[atlas_key] = _resample_single_atlas(nifti_file_id, atlas_key, population_mode=population_mode)

        return results
    else:
        # Process single specific atlas (CLI usage)
        return _resample_single_atlas(nifti_file_id, atlas_name, population_mode=population_mode)


def _resample_single_atlas(nifti_file_id, atlas_name, population_mode=False):
    """
    Helper function to resample a single atlas

    Args:
        nifti_file_id: ID of the NIFTI file
        atlas_name: Name of the atlas to resample
        population_mode: If True, use raw NIFTI instead of FreeSurfer outputs
    """
    nifti_file, storage_object, nifti_gz_path = get_nifti_file(nifti_file_id, True)

    # For FreeSurfer-based atlases, use aparc+aseg.mgz (already in FreeSurfer space)
    # For MNI-based atlases (harvard-oxford, hcpex), use visualization brain
    # In population mode, use the raw NIFTI file directly
    user_nifti = None
    atlas_img = None
    atlas_img_original = None
    source = None
    brain_temp_path = None
    import tempfile

    # Check if this is a FreeSurfer atlas
    if atlas_name == 'freesurfer':
        # FreeSurfer aparc+aseg.mgz is already in the same space as brain.mgz
        # We just need to apply the same crop that was applied to brain_optimized_freesurfer
        print(f"📥 Loading FreeSurfer aparc+aseg.mgz...")
        seg_data = supabase.storage.from_("freesurfer-outputs").download(
            f"{nifti_file_id}/mri/aparc+aseg.mgz"
        )
        seg_path = os.path.join(tempfile.gettempdir(), f"aparc_aseg_{nifti_file_id}.mgz")
        with open(seg_path, 'wb') as f:
            f.write(seg_data)
        seg_img = nib.load(seg_path)

        # Load crop params for FreeSurfer brain
        import json
        crop_params_data = supabase.storage.from_("freesurfer-outputs").download(
            f"{nifti_file_id}/visualization/crop_params_freesurfer.json"
        )
        crop_params = json.loads(crop_params_data)

        print(f"📐 Applying crop to match FreeSurfer visualization brain...")
        print(f"   Crop: [{crop_params['x_min']}:{crop_params['x_max']}, "
              f"{crop_params['y_min']}:{crop_params['y_max']}, "
              f"{crop_params['z_min']}:{crop_params['z_max']}]")

        # Apply crop
        seg_array = seg_img.get_fdata()
        cropped_seg = seg_array[
            crop_params['x_min']:crop_params['x_max'],
            crop_params['y_min']:crop_params['y_max'],
            crop_params['z_min']:crop_params['z_max']
        ]

        # Update affine for cropping
        cropped_affine = seg_img.affine.copy()
        offset = np.array([crop_params['x_min'], crop_params['y_min'], crop_params['z_min']])
        cropped_affine[:3, 3] = seg_img.affine[:3, :3].dot(offset) + seg_img.affine[:3, 3]

        # Create cropped atlas (this replaces the "resampled" atlas for FreeSurfer)
        resampled_atlas = nib.Nifti1Image(cropped_seg, cropped_affine)
        source = "freesurfer_native"
        print(f"✅ Cropped FreeSurfer segmentation to {cropped_seg.shape}")

        # CRITICAL: Mask atlas to only include voxels where brain tissue exists
        # Load the corresponding FreeSurfer brain to create mask
        brain_data = supabase.storage.from_("freesurfer-outputs").download(
            f"{nifti_file_id}/visualization/brain_optimized_freesurfer.nii.gz"
        )
        brain_temp_path = os.path.join(tempfile.gettempdir(), f"brain_fs_{nifti_file_id}.nii.gz")
        with open(brain_temp_path, 'wb') as f:
            f.write(brain_data)
        brain_img = nib.load(brain_temp_path)
        brain_mask = brain_img.get_fdata() > 0

        # Mask the segmentation
        masked_seg = cropped_seg * brain_mask
        resampled_atlas = nib.Nifti1Image(masked_seg, cropped_affine)

        labels_before = np.count_nonzero(cropped_seg)
        labels_after = np.count_nonzero(masked_seg)
        removed_pct = ((labels_before - labels_after) / labels_before * 100) if labels_before > 0 else 0
        print(f"🎯 Masked atlas to brain boundary (removed {removed_pct:.1f}% of labels outside brain)")

        os.remove(brain_temp_path)
        os.remove(seg_path)

        # Skip the standard resampling logic - jump straight to compression
        user_nifti = None  # Not needed for FreeSurfer
        atlas_img = None  # Already processed

    else:
        # MNI-based atlases (Harvard-Oxford, HCPex)
        if population_mode:
            # Population mode: Use raw NIFTI directly (no FreeSurfer processing)
            print(f"📥 Loading raw NIFTI file (population mode)...")
            user_nifti = nib.load(nifti_gz_path)
            brain_temp_path = nifti_gz_path
            source = "raw_nifti_mni"
            print(f"✅ Loaded raw NIFTI: {user_nifti.shape}")
            print(f"   Using raw scan for MNI atlas alignment (no FreeSurfer transform)")

            # Load MNI atlas directly - no transform needed
            atlas_file_path = get_atlas_file_path(atlas_name)
            atlas_img_mni = nib.load(atlas_file_path)
            print(f"✅ Loaded MNI atlas: {atlas_name}")
            print(f"   Will resample atlas directly to match raw NIFTI dimensions")

            # Use atlas as-is (both should be in MNI space approximately)
            atlas_img = atlas_img_mni
            atlas_img_original = atlas_img_mni

        else:
            # User mode: Transform atlas FROM MNI space back to the user's native FreeSurfer space
            print(f"📥 Loading FreeSurfer visualization brain (native space for overlays)...")

            # Load the cropped FreeSurfer visualization brain (native space)
            freesurfer_brain_data = supabase.storage.from_("freesurfer-outputs").download(
                f"{nifti_file_id}/visualization/brain_optimized_freesurfer.nii.gz"
            )
            brain_path = os.path.join(tempfile.gettempdir(), f"brain_native_{nifti_file_id}.nii.gz")
            with open(brain_path, 'wb') as f:
                f.write(freesurfer_brain_data)

            user_nifti = nib.load(brain_path)
            brain_temp_path = brain_path
            source = "freesurfer_native_with_mni_transform"
            print(f"✅ Loaded FreeSurfer visualization brain: {user_nifti.shape}")
            print(f"   This brain is cropped FreeSurfer native space used for visualization overlays")

            # Load talairach transform (native → MNI) and compute inverse (MNI → native)
            xfm_data = supabase.storage.from_("freesurfer-outputs").download(
                f"{nifti_file_id}/mri/transforms/talairach.xfm"
            )
            xfm_text = xfm_data.decode('utf-8')
            lines = [l.strip() for l in xfm_text.split('\n') if l.strip() and not l.strip().startswith('%')]

            matrix_lines = []
            in_matrix = False
            for line in lines:
                if 'Linear_Transform' in line:
                    in_matrix = True
                    continue
                if in_matrix and line.endswith(';'):
                    matrix_lines.append(line.rstrip(';'))
                    break
                elif in_matrix:
                    matrix_lines.append(line)

            native_to_mni = np.eye(4)
            for i, line in enumerate(matrix_lines):
                values = [float(x) for x in line.split()]
                native_to_mni[i, :] = values

            mni_to_native = np.linalg.inv(native_to_mni)
            print("✅ Loaded talairach transform and computed MNI→native matrix")

            # Load the MNI atlas and convert its affine into the user's native space
            atlas_file_path = get_atlas_file_path(atlas_name)
            atlas_img_mni = nib.load(atlas_file_path)
            print(f"✅ Loaded MNI atlas: {atlas_name}")
            print(f"   Transforming atlas to native FreeSurfer space for alignment...")

            atlas_native_affine = mni_to_native @ atlas_img_mni.affine
            atlas_img = nib.Nifti1Image(atlas_img_mni.get_fdata(), atlas_native_affine, atlas_img_mni.header)
            atlas_img_original = atlas_img_mni

    # Only resample if we haven't already processed the atlas (FreeSurfer path skips this)
    if atlas_img is not None:
        # Handle 4D images with trailing singleton dimension (defensive check)
        # Some NIfTI files may have shape (x, y, z, 1) instead of (x, y, z)
        target_shape = user_nifti.shape
        if len(target_shape) == 4 and target_shape[3] == 1:
            print(f"  ℹ️  Squeezing 4D image {target_shape} to 3D")
            user_nifti_data = user_nifti.get_fdata().squeeze()
            user_nifti = nib.Nifti1Image(user_nifti_data, user_nifti.affine, user_nifti.header)
            target_shape = user_nifti.shape

        # Both brain and atlas now share the user's native FreeSurfer space.
        # Resample atlas to match the cropped visualization brain dimensions.
        print(f"📐 Resampling atlas to match user's brain dimensions...")

        resampled_atlas = resample_img(
            atlas_img,
            target_affine=user_nifti.affine,
            target_shape=target_shape,
            interpolation='nearest',  # Preserve integer labels
            force_resample=True,
            copy_header=True
        )

        print(f"✅ Resampled atlas in native space: {resampled_atlas.shape}")

        # Apply brain mask for precision (only show atlas where there's brain tissue)
        brain_mask = user_nifti.get_fdata() > 0
        atlas_data = resampled_atlas.get_fdata()
        masked_atlas_data = atlas_data * brain_mask
        resampled_atlas = nib.Nifti1Image(masked_atlas_data, resampled_atlas.affine)

        labels_before = np.count_nonzero(atlas_data)
        labels_after = np.count_nonzero(masked_atlas_data)
        removed_pct = ((labels_before - labels_after) / labels_before * 100) if labels_before > 0 else 0
        print(f"🎯 Masked to brain boundary (removed {removed_pct:.1f}% outside labels)")

        # Clean up temp files
        if brain_temp_path and os.path.exists(brain_temp_path):
            os.remove(brain_temp_path)

    # else: resampled_atlas already set by FreeSurfer path

    voxel_size = np.abs(np.linalg.det(resampled_atlas.affine[:3, :3]))

    if (save_assets or not silent_run) and (atlas_img_original is not None or atlas_img is not None):
        # Visualize the original and resampled Atlas
        plotting.plot_roi(atlas_img_original or atlas_img, title=f"Original {atlas_name} Atlas")
        plotting.plot_roi(resampled_atlas, title=f"Resampled {atlas_name} Atlas for User")
        plt.savefig(os.path.join(output_dir, f'resample_atlas_for_user_{atlas_name}.png'))
        if not silent_run:
            plt.show()

    # Convert to int16 and compress for efficient storage
    # Label atlases should be integers, not float64
    atlas_data_int = np.round(resampled_atlas.get_fdata()).astype(np.int16)
    compressed_atlas = nib.Nifti1Image(atlas_data_int, resampled_atlas.affine)

    # Save to compressed .nii.gz format
    import tempfile
    temp_path = os.path.join(tempfile.gettempdir(), f'{atlas_name}_temp.nii.gz')
    nib.save(compressed_atlas, temp_path)

    with open(temp_path, 'rb') as f:
        compressed_bytes = f.read()

    os.remove(temp_path)

    print(f"   Compressed size: {len(compressed_bytes) / (1024*1024):.2f} MB")

    # Upload resampled atlas to storage (with atlas name in path)
    storage_path = upload_resampled_atlas(nifti_file['user_id'], nifti_file_id, compressed_bytes, atlas_name)
    print(f"✅ Uploaded resampled {atlas_name} atlas to: {storage_path}")

    # save voxel_size (optional - may fail for anonymous/population users)
    user_meta = None
    try:
        user_meta = (supabase.schema("public")
                     .rpc("set_user_meta", {"p_user_id": nifti_file['user_id'], "p_meta_key": "voxel_size", "p_meta_value": voxel_size})
                     .single().execute()).data
        print("Saved voxel size: ", user_meta)
    except Exception as e:
        print(f"⚠️  Warning: Could not save voxel_size to usermeta (likely anonymous user): {str(e)}")
        print(f"   Voxel size: {voxel_size} (not persisted)")

    return {
        "storage_path": storage_path,
        "voxel_size": voxel_size,
        "user_meta": user_meta,
        "atlas_name": atlas_name,
        "source": source  # Track whether we used FreeSurfer or user upload
    }


# example:
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Resample brain atlas to match your uploaded NIFTI scan')
    parser.add_argument('file_id', help='File ID from the upload_nifti output')
    parser.add_argument('--atlas', dest='atlas_name', default=None,
                       choices=['freesurfer', 'harvard-oxford', 'hcpex'],
                       help='Atlas to use (default: all atlases, freesurfer recommended for guaranteed alignment)')

    args = parser.parse_args()

    print(f"=== ATLAS RESAMPLING ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    if args.atlas_name:
        print(f"Atlas: {args.atlas_name}")
    else:
        print(f"Atlas: All available atlases")
    print("This will align the brain atlas to match your scan...")
    print("Please wait, this may take 1-2 minutes...\n")

    try:
        result = resample_atlas_for_user_nifti(args.file_id, args.atlas_name)
        print("\n=== ATLAS RESAMPLING COMPLETE ===")
        print("Result:", result)

    except Exception as e:
        print(f"❌ Error during atlas resampling: {str(e)}")
        print("Please check your file ID and try again.")
        os._exit(1)

    # Force exit to prevent hanging
    os._exit(0)
