import os
import argparse
import numpy as np
import nibabel as nib
from datetime import datetime
from scipy.ndimage import zoom

from utilities.data import supabase
from utilities.supabase_utilities import get_nifti_file, download_nifti_file

FUNCTION_NAME = "prepare_visualization_nifti"


def _process_brain(nifti_file_id, user_id, nifti_path, brain_type, supabase_client, original_data=None):
    """
    Process a brain for visualization (crop and optionally downsample)

    Args:
        nifti_file_id: NIFTI file ID
        user_id: User ID
        nifti_path: Path to brain file
        brain_type: 'freesurfer' or 'mni'
        supabase_client: Supabase client
        original_data: Original file data (for size calculation)

    Returns:
        dict with processing results
    """
    import json
    import shutil

    img = nib.load(nifti_path)
    data = img.get_fdata()
    affine = img.affine
    original_shape = data.shape

    # Get original size
    try:
        original_size_mb = os.path.getsize(nifti_path) / (1024 * 1024)
    except:
        original_size_mb = len(original_data) / (1024 * 1024) if original_data else 0

    print(f"   Original shape: {original_shape}")
    print(f"   Original size: {original_size_mb:.2f} MB")

    # Crop to brain bounds
    print("✂️  Cropping to brain bounds...")
    mask = data > 0
    coords = np.argwhere(mask)

    if len(coords) == 0:
        raise ValueError("No non-zero voxels found")

    x_min, y_min, z_min = coords.min(axis=0)
    x_max, y_max, z_max = coords.max(axis=0)

    padding = 5
    x_min = max(0, x_min - padding)
    y_min = max(0, y_min - padding)
    z_min = max(0, z_min - padding)
    x_max = min(data.shape[0], x_max + padding)
    y_max = min(data.shape[1], y_max + padding)
    z_max = min(data.shape[2], z_max + padding)

    cropped_data = data[x_min:x_max, y_min:y_max, z_min:z_max]
    cropped_affine = affine.copy()
    cropped_affine[:3, 3] = affine[:3, :3].dot([x_min, y_min, z_min]) + affine[:3, 3]

    print(f"   Cropped to: {cropped_data.shape}")

    # Save crop params (for FreeSurfer brain only - used by FreeSurfer atlas)
    if brain_type == "freesurfer":
        crop_params = {
            "x_min": int(x_min), "x_max": int(x_max),
            "y_min": int(y_min), "y_max": int(y_max),
            "z_min": int(z_min), "z_max": int(z_max),
            "original_shape": list(original_shape),
            "cropped_shape": list(cropped_data.shape)
        }
        crop_params_json = json.dumps(crop_params).encode('utf-8')
        supabase_client.storage.from_("freesurfer-outputs").upload(
            file=crop_params_json,
            path=f"{nifti_file_id}/visualization/crop_params_{brain_type}.json",
            file_options={"content-type": "application/json", "upsert": "true"}
        )

    final_data = cropped_data
    final_affine = cropped_affine

    # For MNI brain, optionally downsample (FreeSurfer stays at 1mm for atlas precision)
    if brain_type == "mni":
        voxel_dims = np.sqrt(np.sum(cropped_affine[:3, :3] ** 2, axis=0))
        target_resolution = 1.5

        if np.any(voxel_dims < target_resolution * 0.95):
            print(f"⬇️  Downsampling to ~{target_resolution}mm...")
            from scipy.ndimage import zoom
            zoom_factors = np.minimum(voxel_dims / target_resolution, 1.0)

            if np.any(zoom_factors < 0.95):
                downsampled_data = zoom(cropped_data, zoom_factors, order=1)
                downsampled_affine = cropped_affine.copy()
                for i in range(3):
                    downsampled_affine[:3, i] = cropped_affine[:3, i] / zoom_factors[i]

                final_data = downsampled_data
                final_affine = downsampled_affine
                print(f"   Downsampled to: {final_data.shape}")

    # Save optimized brain
    import tempfile
    temp_dir = tempfile.mkdtemp()
    filename = f'brain_optimized_{brain_type}.nii.gz'
    temp_path = os.path.join(temp_dir, filename)

    optimized_img = nib.Nifti1Image(final_data, final_affine)
    nib.save(optimized_img, temp_path)

    optimized_size_mb = os.path.getsize(temp_path) / (1024 * 1024)

    # Upload to storage
    storage_path = f"{nifti_file_id}/visualization/{filename}"
    with open(temp_path, 'rb') as f:
        file_data = f.read()

    supabase_client.storage.from_("freesurfer-outputs").upload(
        file=file_data,
        path=storage_path,
        file_options={"content-type": "application/gzip", "upsert": "true"}
    )

    shutil.rmtree(temp_dir)

    return {
        "brain_type": brain_type,
        "storage_path": storage_path,
        "original_shape": original_shape,
        "optimized_shape": tuple(final_data.shape),
        "original_size_mb": round(original_size_mb, 2),
        "optimized_size_mb": round(optimized_size_mb, 2),
    }


def prepare_visualization_nifti(nifti_file_id, **kwargs):
    """
    Prepare optimized NIfTI file for web visualization.

    This function takes a user's brain scan and optimizes it for web delivery:
    1. Crops to brain bounds (removes empty space)
    2. Downsamples to 2mm resolution if higher resolution
    3. Compresses to .nii.gz format
    4. Uploads to {nifti_file_id}/visualization/brain_optimized.nii.gz

    Typical size reduction: 50MB raw → 2-5MB optimized

    Args:
        nifti_file_id (str): The ID of the NIFTI file to optimize
        **kwargs: Additional parameters

    Returns:
        dict: Results with path to optimized file and size info
    """

    print(f"Preparing visualization NIfTI for: {nifti_file_id}")

    ########## FUNCTION LOGIC STARTS ##########

    try:
        # Get the user's original NIFTI file
        response = supabase.schema("public").rpc(
            "get_file_type_among_children",
            {"p_nifti_file_id": nifti_file_id, "p_file_type": "nii"}
        ).single().execute()

        user_nifti_file = response.data
        user_id = user_nifti_file['user_id']

        # Create TWO visualization brains for multi-atlas support:
        # 1. brain_optimized_freesurfer.nii.gz - From FreeSurfer brain.mgz (for FreeSurfer atlas)
        # 2. brain_optimized_mni.nii.gz - From user upload (for Harvard-Oxford, HCPex atlases)

        import tempfile
        results = []

        # BRAIN 1: FreeSurfer-based (if available)
        try:
            print("\n=== CREATING FREESURFER-BASED VISUALIZATION ===")
            print("📥 Loading FreeSurfer brain.mgz...")
            brain_mgz_data = supabase.storage.from_("freesurfer-outputs").download(
                f"{nifti_file_id}/mri/brain.mgz"
            )

            fs_path = os.path.join(tempfile.gettempdir(), f"brain_{nifti_file_id}.mgz")
            with open(fs_path, 'wb') as f:
                f.write(brain_mgz_data)

            # Process FreeSurfer brain (crop only, no downsample)
            fs_result = _process_brain(nifti_file_id, user_id, fs_path, "freesurfer",
                                       supabase, brain_mgz_data)
            results.append(fs_result)
            print(f"✅ Created FreeSurfer visualization: {fs_result['storage_path']}")

        except Exception as e:
            print(f"ℹ️  FreeSurfer brain.mgz not available: {e}")

        # BRAIN 2: MNI-space brain (for MNI atlases: Harvard-Oxford, HCPex)
        try:
            print("\n=== CREATING MNI-SPACE VISUALIZATION ===")
            print("📥 Loading FreeSurfer brain and talairach transform...")

            # Load FreeSurfer brain
            brain_mgz_data = supabase.storage.from_("freesurfer-outputs").download(
                f"{nifti_file_id}/mri/brain.mgz"
            )
            brain_path = os.path.join(tempfile.gettempdir(), f"brain_mni_{nifti_file_id}.mgz")
            with open(brain_path, 'wb') as f:
                f.write(brain_mgz_data)

            # Load native brain
            brain_img = nib.load(brain_path)

            # Load talairach transform
            xfm_data = supabase.storage.from_("freesurfer-outputs").download(
                f"{nifti_file_id}/mri/transforms/talairach.xfm"
            )

            # Parse transform matrix
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

            # Build 4x4 affine matrix (native → MNI)
            native_to_mni = np.eye(4)
            for i, line in enumerate(matrix_lines):
                values = [float(x) for x in line.split()]
                native_to_mni[i, :] = values

            print(f"✅ Loaded talairach transform")

            # Apply transform to create MNI-space brain
            mni_affine = native_to_mni @ brain_img.affine
            mni_brain = nib.Nifti1Image(brain_img.get_fdata(), mni_affine)

            # Save MNI brain to temp file for processing
            mni_temp_path = os.path.join(tempfile.gettempdir(), f"mni_brain_{nifti_file_id}.nii.gz")
            nib.save(mni_brain, mni_temp_path)

            print(f"🧮 Transformed brain to MNI space")

            # Process MNI brain (crop + downsample)
            mni_result = _process_brain(nifti_file_id, user_id, mni_temp_path, "mni",
                                        supabase, brain_mgz_data)
            results.append(mni_result)
            print(f"✅ Created MNI visualization: {mni_result['storage_path']}")

            # Cleanup
            os.remove(brain_path)
            os.remove(mni_temp_path)

        except Exception as e:
            print(f"❌ Error creating MNI visualization: {e}")

        if not results:
            raise Exception("Failed to create any visualization brains")

        # Return combined results
        return {
            "nifti_file_id": nifti_file_id,
            "status": "completed",
            "brains": results,
            "message": f"Created {len(results)} visualization brain(s)",
            "created_at": datetime.now().isoformat()
        }

    except Exception as e:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "status": "failed",
            "error": str(e),
            "message": f"Failed to optimize NIfTI: {str(e)}"
        }
        print(f"\n❌ Error: {str(e)}")
        return error_result


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Prepare optimized NIfTI file for web visualization'
    )
    parser.add_argument('file_id', help='NIFTI file ID to optimize')

    args = parser.parse_args()

    print(f"=== VISUALIZATION NIFTI OPTIMIZER ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    print("\nThis will:")
    print("  1. Crop to brain bounds (remove empty space)")
    print("  2. Downsample to 2mm resolution if needed")
    print("  3. Compress to .nii.gz format")
    print("  4. Upload to freesurfer-outputs/{file_id}/visualization/")
    print("\nPlease wait...\n")

    try:
        result = prepare_visualization_nifti(args.file_id)

        if result['status'] == 'completed':
            print(f"\n=== OPTIMIZATION COMPLETE ===")
            print(f"✅ {result['message']}")
            print(f"\n📁 Created visualization brains:")
            for brain in result['brains']:
                print(f"\n   {brain['brain_type'].upper()}:")
                print(f"   - Path: {brain['storage_path']}")
                print(f"   - Shape: {brain['original_shape']} → {brain['optimized_shape']}")
                print(f"   - Size: {brain['original_size_mb']}MB → {brain['optimized_size_mb']}MB")
        else:
            print(f"\n=== OPTIMIZATION FAILED ===")
            print(f"❌ Error: {result.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"\n❌ Error during optimization: {str(e)}")
        os._exit(1)

    # Force exit
    os._exit(0)
