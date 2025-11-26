"""
Preprocessing for native-space brain scans

Performs:
1. N4 bias field correction
2. Skull-stripping (HD-BET, FSL BET, or threshold-based)
3. Brain mask generation
4. Intracranial volume (ICV) computation

Part of Population Pipeline v2 (registration-based measurements)
"""

import os
import argparse
import tempfile
import numpy as np
import nibabel as nib

from utilities.data import supabase
from utilities.supabase_utilities import get_nifti_file
from utilities.dependency_checker import get_capabilities


def preprocess_native_scan(nifti_file_id, method='auto', skip_n4=False):
    """
    Preprocess a native-space brain scan

    Args:
        nifti_file_id: ID of the NIFTI file to preprocess
        method: Skull-stripping method ('auto', 'hdbet', 'fsl_bet', 'threshold')
        skip_n4: If True, skip N4 bias correction (already done upstream)

    Returns:
        Dictionary with preprocessing results:
        {
            'preprocessed_path': storage path to N4-corrected brain,
            'brain_mask_path': storage path to brain mask,
            'icv_mm3': intracranial volume in mm³,
            'method': method used for preprocessing,
            'quality': quality metrics
        }
    """
    print(f"=== PREPROCESSING NATIVE SCAN: {nifti_file_id} ===")

    # Get NIFTI file
    nifti_file, storage_object, nifti_gz_path = get_nifti_file(nifti_file_id, True)
    print(f"✓ Loaded NIFTI file: {nifti_gz_path}")

    # Load image
    img = nib.load(nifti_gz_path)
    print(f"  Image shape: {img.shape}")
    print(f"  Voxel size: {img.header.get_zooms()[:3]} mm")

    # Squeeze 4D images to 3D if needed (some datasets have trailing dimension)
    if len(img.shape) == 4:
        print(f"  ℹ️  Squeezing 4D image {img.shape} to 3D")
        img_data = img.get_fdata()
        if img.shape[3] == 1:
            # Squeeze trailing dimension
            img_data_3d = np.squeeze(img_data, axis=3)
            img = nib.Nifti1Image(img_data_3d, img.affine, img.header)
            print(f"  ✓ Squeezed to: {img.shape}")
        else:
            raise ValueError(f"Cannot handle 4D image with {img.shape[3]} volumes (expected 1)")

    # Step 1: N4 Bias Field Correction (skip if already done)
    if skip_n4:
        print("\n1. N4 Bias Field Correction...")
        print(f"  ⏭️  Skipped (already applied upstream)")
        corrected_img = img
    else:
        print("\n1. N4 Bias Field Correction...")
        corrected_img = apply_n4_correction(img)
        print(f"  ✓ Bias field corrected")

    # Step 2: Skull-Stripping
    print("\n2. Skull-Stripping...")
    brain_img, brain_mask_img, skullstrip_method = skull_strip_brain(
        corrected_img,
        method=method,
        file_id=nifti_file_id  # Pass file ID for unique temp files
    )
    print(f"  ✓ Skull-stripped using: {skullstrip_method}")

    # Step 3: Compute ICV
    print("\n3. Computing Intracranial Volume (ICV)...")
    icv_mm3 = compute_icv(brain_mask_img)
    print(f"  ✓ ICV: {icv_mm3:,.0f} mm³ ({icv_mm3 / 1e6:.2f} liters)")

    # Step 4: Quality Metrics
    print("\n4. Quality Assessment...")
    quality = assess_quality(img, brain_img, brain_mask_img)
    print(f"  Brain volume: {quality['brain_volume_mm3']:,.0f} mm³")
    print(f"  Brain/ICV ratio: {quality['brain_icv_ratio']:.3f}")
    print(f"  Non-zero voxels: {quality['nonzero_voxels']:,}")

    # Step 5: Save to Supabase
    print("\n5. Uploading to Supabase...")

    # Save preprocessed brain
    brain_path = save_temp_nifti(brain_img, 'brain_n4.nii.gz')
    with open(brain_path, 'rb') as f:
        brain_bytes = f.read()

    brain_storage_path = f"{nifti_file_id}/preprocessing/brain_n4.nii.gz"
    supabase.storage.from_("freesurfer-outputs").upload(
        brain_storage_path,
        brain_bytes,
        {'upsert': 'true'}
    )
    print(f"  ✓ Uploaded: {brain_storage_path}")

    # Save brain mask
    mask_path = save_temp_nifti(brain_mask_img, 'brain_mask.nii.gz')
    with open(mask_path, 'rb') as f:
        mask_bytes = f.read()

    mask_storage_path = f"{nifti_file_id}/preprocessing/brain_mask.nii.gz"
    supabase.storage.from_("freesurfer-outputs").upload(
        mask_storage_path,
        mask_bytes,
        {'upsert': 'true'}
    )
    print(f"  ✓ Uploaded: {mask_storage_path}")

    # Update database with ICV
    try:
        # Check if this is a population scan
        pop_scan = (supabase.table('population_scans')
                    .select('id')
                    .eq('nifti_file_id', nifti_file_id)
                    .execute()).data

        if pop_scan:
            # Update population_scans table
            (supabase.table('population_scans')
             .update({
                 'icv': icv_mm3,
                 'preprocessing_version': f'v2_{skullstrip_method}'
             })
             .eq('nifti_file_id', nifti_file_id)
             .execute())
            print(f"  ✓ Updated population_scans with ICV")
        else:
            print(f"  ℹ️  Not a population scan, skipping database update")
    except Exception as e:
        print(f"  ⚠️  Could not update database: {e}")

    # Clean up temp files
    os.remove(brain_path)
    os.remove(mask_path)
    if os.path.exists(nifti_gz_path):
        os.remove(nifti_gz_path)

    result = {
        'preprocessed_path': brain_storage_path,
        'brain_mask_path': mask_storage_path,
        'icv_mm3': icv_mm3,
        'method': skullstrip_method,
        'quality': quality
    }

    print("\n=== PREPROCESSING COMPLETE ===")
    return result


def apply_n4_correction(img):
    """
    Apply N4 bias field correction using SimpleITK

    Args:
        img: nibabel image

    Returns:
        Corrected nibabel image
    """
    try:
        import SimpleITK as sitk
    except ImportError:
        print("  Warning: SimpleITK not available, skipping N4 correction")
        return img

    # Convert to SimpleITK
    img_data = img.get_fdata().astype(np.float32)
    img_sitk = sitk.GetImageFromArray(img_data.transpose(2, 1, 0))

    # Convert numpy types to Python float for SimpleITK
    spacing = [float(x) for x in img.header.get_zooms()[:3]]
    origin = [float(x) for x in img.affine[:3, 3]]

    img_sitk.SetSpacing(spacing)
    img_sitk.SetOrigin(origin)

    # Apply N4
    corrector = sitk.N4BiasFieldCorrectionImageFilter()
    corrected_sitk = corrector.Execute(img_sitk)

    # Convert back to nibabel
    corrected_data = sitk.GetArrayFromImage(corrected_sitk).transpose(2, 1, 0)
    corrected_img = nib.Nifti1Image(corrected_data, img.affine, img.header)

    return corrected_img


def skull_strip_brain(img, method='auto', file_id=None):
    """
    Skull-strip brain image

    Args:
        img: nibabel image (bias-corrected)
        method: 'auto', 'hdbet', 'fsl_bet', or 'threshold'
        file_id: NIFTI file ID for unique temp file naming (optional)

    Returns:
        (brain_img, brain_mask_img, method_used)
    """
    caps = get_capabilities()

    # Auto-select method
    if method == 'auto':
        method = caps['best_skullstrip']['method']
        print(f"  Auto-selected method: {method}")

    # Try requested method with fallbacks
    if method == 'hdbet':
        try:
            return skull_strip_hdbet(img, file_id=file_id)
        except Exception as e:
            print(f"  HD-BET failed: {e}")
            # Try to extract stderr if it's a subprocess error
            if hasattr(e, 'stderr') and e.stderr:
                print(f"  HD-BET stderr: {e.stderr}")
            print(f"  Falling back to threshold method")
            method = 'threshold'

    if method == 'fsl_bet':
        try:
            return skull_strip_fsl_bet(img, file_id=file_id)
        except Exception as e:
            print(f"  FSL BET failed: {e}, falling back to threshold")
            method = 'threshold'

    if method == 'threshold':
        return skull_strip_threshold(img)

    raise ValueError(f"Unknown skull-stripping method: {method}")


def find_hdbet_executable():
    """Find hd-bet executable path"""
    import shutil

    # First check if hd-bet is in PATH
    hd_bet_path = shutil.which('hd-bet')
    if hd_bet_path:
        return hd_bet_path

    # Check venv bin directory (same as Python executable)
    import sys
    venv_bin = os.path.dirname(sys.executable)
    possible_path = os.path.join(venv_bin, 'hd-bet')
    if os.path.exists(possible_path):
        return possible_path

    # Check common locations
    common_paths = [
        '/opt/venv/bin/hd-bet',
        '/usr/local/bin/hd-bet',
        os.path.expanduser('~/.local/bin/hd-bet'),
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path

    return None


def skull_strip_hdbet(img, file_id=None):
    """Skull-strip using HD-BET (deep learning)"""
    import subprocess

    # Find hd-bet executable
    hd_bet_path = find_hdbet_executable()
    if not hd_bet_path:
        raise FileNotFoundError("hd-bet executable not found. Install with: pip install hd-bet")
    print(f"  Using HD-BET at: {hd_bet_path}")

    # Check if GPU is available
    device = 'cpu'
    try:
        import torch
        if torch.cuda.is_available():
            device = 'cuda'
            print(f"  Using CUDA GPU for HD-BET")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            # Apple Silicon (M1/M2/M3/M4) - use MPS
            device = 'mps'
            print(f"  Using Apple Silicon GPU (MPS) for HD-BET")
        else:
            print(f"  Using CPU for HD-BET (no GPU detected)")
    except ImportError:
        print(f"  Using CPU for HD-BET (PyTorch not installed)")

    # Use file ID for unique temp files (better than UUID for debugging)
    suffix = file_id[:8] if file_id else 'temp'
    input_path = save_temp_nifti(img, f'hdbet_input_{suffix}.nii.gz')
    output_dir = tempfile.mkdtemp(prefix=f'hdbet_{suffix}_')

    try:
        # Run HD-BET with TTA enabled for best accuracy
        cmd = [
            hd_bet_path,
            '-i', input_path,
            '-o', os.path.join(output_dir, 'brain.nii.gz'),
            '-device', device,
            '--save_bet_mask',  # Save the brain mask
            '--verbose'  # Show progress
        ]

        print(f"  Running HD-BET (this may take 1-3 minutes with TTA)...")
        proc_result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,  # Let output stream to console so we can see progress
            timeout=600,
            text=True
        )

        # Load results
        # HD-BET creates brain_bet.nii.gz (the skull-stripped brain)
        brain_path = os.path.join(output_dir, 'brain_bet.nii.gz')

        if not os.path.exists(brain_path):
            raise FileNotFoundError(f"HD-BET did not create brain_bet.nii.gz at {brain_path}")

        brain_img_temp = nib.load(brain_path)

        # Force load data into memory before cleaning up temp files
        brain_data = brain_img_temp.get_fdata()

        # Create new image with data in memory (not lazy-loaded from file)
        brain_img = nib.Nifti1Image(brain_data, brain_img_temp.affine, brain_img_temp.header)

        # Create mask from the brain image (mask is non-zero voxels)
        mask_data = (brain_data > 0).astype(np.uint8)
        mask_img = nib.Nifti1Image(mask_data, brain_img.affine, brain_img.header)

        return brain_img, mask_img, 'hdbet'

    except subprocess.CalledProcessError as e:
        # Capture and re-raise with stderr
        error_msg = f"HD-BET failed with return code {e.returncode}"
        if e.stderr:
            error_msg += f"\nStderr: {e.stderr}"
        if e.stdout:
            error_msg += f"\nStdout: {e.stdout}"
        raise RuntimeError(error_msg) from e

    finally:
        # Cleanup
        import shutil
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)


def skull_strip_fsl_bet(img, file_id=None):
    """Skull-strip using FSL BET"""
    import subprocess

    # Use file ID for unique temp files
    suffix = file_id[:8] if file_id else 'temp'
    input_path = save_temp_nifti(img, f'fsl_input_{suffix}.nii.gz')
    output_path = save_temp_nifti(img, f'fsl_output_{suffix}.nii.gz')
    mask_path = output_path.replace('.nii.gz', '_mask.nii.gz')

    try:
        # Run BET
        subprocess.run([
            'bet',
            input_path,
            output_path,
            '-R',  # Robust brain center estimation
            '-f', '0.3',  # Fractional intensity threshold
            '-g', '0',  # Vertical gradient
            '-m'  # Generate mask
        ], check=True, capture_output=True, timeout=120)

        # Load results
        brain_img = nib.load(output_path)
        mask_img = nib.load(mask_path)

        return brain_img, mask_img, 'fsl_bet'

    finally:
        for path in [input_path, output_path, mask_path]:
            if os.path.exists(path):
                os.remove(path)


def skull_strip_threshold(img):
    """Simple threshold-based skull-stripping (fallback)"""
    data = img.get_fdata()

    # Otsu thresholding
    from scipy.ndimage import binary_fill_holes, binary_erosion, binary_dilation

    # Compute threshold
    hist, bin_edges = np.histogram(data[data > 0], bins=256)
    threshold = otsu_threshold(hist)

    # Create mask
    mask = data > threshold

    # Morphological operations to clean up
    mask = binary_fill_holes(mask)
    mask = binary_erosion(mask, iterations=2)
    mask = binary_dilation(mask, iterations=2)

    # Apply mask
    brain_data = data * mask

    brain_img = nib.Nifti1Image(brain_data, img.affine, img.header)
    mask_img = nib.Nifti1Image(mask.astype(np.uint8), img.affine, img.header)

    return brain_img, mask_img, 'threshold'


    idx = np.argmax(variance)
    return idx


def compute_icv(brain_mask_img):
    """
    Compute intracranial volume from brain mask

    ICV = sum(mask) * voxel_volume

    Args:
        brain_mask_img: nibabel image of brain mask

    Returns:
        ICV in mm³
    """
    mask = brain_mask_img.get_fdata() > 0

    # Compute voxel volume
    voxel_dims = brain_mask_img.header.get_zooms()[:3]
    voxel_volume = np.prod(voxel_dims)

    # Count voxels
    icv_mm3 = np.sum(mask) * voxel_volume

    return float(icv_mm3)


def assess_quality(original_img, brain_img, mask_img):
    """Compute quality metrics"""
    mask = mask_img.get_fdata() > 0
    voxel_volume = np.prod(original_img.header.get_zooms()[:3])

    brain_volume = np.sum(mask) * voxel_volume
    nonzero_voxels = np.sum(brain_img.get_fdata() > 0)

    # Compute brain/ICV ratio (should be around 0.7-0.85 for healthy adults)
    icv = compute_icv(mask_img)
    brain_icv_ratio = brain_volume / icv if icv > 0 else 0
    
    # Sanity check
    if brain_icv_ratio > 0.95:
        print(f"  ⚠️  WARNING: Brain/ICV ratio is {brain_icv_ratio:.3f} (suspiciously high).")
        print(f"      This suggests skull-stripping failed and included the skull/background.")
        print(f"      Check if HD-BET is installed correctly. Current method: {brain_img.header.get('descrip', b'').decode('utf-8')}")

    return {
        'brain_volume_mm3': float(brain_volume),
        'brain_icv_ratio': float(brain_icv_ratio),
        'nonzero_voxels': int(nonzero_voxels),
        'voxel_volume_mm3': float(voxel_volume)
    }


def save_temp_nifti(img, suffix='temp.nii.gz'):
    """Save nibabel image to temporary file"""
    temp_path = os.path.join(tempfile.gettempdir(), suffix)
    nib.save(img, temp_path)
    return temp_path


# CLI
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Preprocess native-space brain scan (N4 + skull-strip + ICV)'
    )
    parser.add_argument('file_id', help='NIFTI file ID from upload_nifti')
    parser.add_argument('--method', default='auto',
                        choices=['auto', 'hdbet', 'fsl_bet', 'threshold'],
                        help='Skull-stripping method (default: auto)')

    args = parser.parse_args()

    try:
        result = preprocess_native_scan(args.file_id, method=args.method)
        print("\n✓ Preprocessing successful!")
        print(f"  ICV: {result['icv_mm3']:,.0f} mm³")
        print(f"  Method: {result['method']}")
        print(f"  Brain: {result['preprocessed_path']}")
        print(f"  Mask: {result['brain_mask_path']}")

    except Exception as e:
        print(f"\n✗ Preprocessing failed: {e}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
