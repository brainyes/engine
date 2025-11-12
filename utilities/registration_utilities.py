"""
Utilities for image registration and transformation

Helper functions for applying registration transforms to atlas images
and computing Jacobian determinants for volume modulation.
"""

import nibabel as nib
import numpy as np
import tempfile
import os
from pathlib import Path


def save_temp_file(data_bytes, suffix='.nii.gz'):
    """
    Save bytes to temporary file

    Args:
        data_bytes: File bytes
        suffix: File extension

    Returns:
        Path to temporary file
    """
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(data_bytes)
    temp_file.close()
    return temp_file.name


def apply_ants_warp_to_atlas(atlas_img, inverse_warp_path, reference_img, affine_path=None):
    """
    Apply ANTs warp field to atlas labels

    Args:
        atlas_img: nibabel image of atlas in MNI space
        inverse_warp_path: Path to inverse warp (MNI → native)
        reference_img: nibabel image of native space reference
        affine_path: Optional path to affine transform (applied first)

    Returns:
        nibabel image of atlas in native space
    """
    try:
        import ants
    except ImportError:
        raise ImportError("ANTsPy is required for this function. Install with: pip install antspyx")

    # Convert nibabel → ANTs
    atlas_ants = ants.from_nibabel(atlas_img)
    reference_ants = ants.from_nibabel(reference_img)

    # Build transform list (applied in reverse order)
    transformlist = []

    if affine_path and os.path.exists(affine_path):
        transformlist.append(affine_path)

    transformlist.append(inverse_warp_path)

    # Apply transform
    print(f"   Applying ANTs transforms: {transformlist}")
    warped_atlas = ants.apply_transforms(
        fixed=reference_ants,
        moving=atlas_ants,
        transformlist=transformlist,
        interpolator='nearestNeighbor',  # CRITICAL for preserving integer labels
        verbose=False
    )

    # Convert back to nibabel
    return warped_atlas.to_nibabel()


def apply_affine_to_atlas(atlas_img, affine_transform, reference_img):
    """
    Apply affine transformation to atlas using nilearn

    Args:
        atlas_img: nibabel image of atlas in MNI space
        affine_transform: 4x4 numpy array or path to transform file
        reference_img: nibabel image of native space reference

    Returns:
        nibabel image of atlas in native space
    """
    from nilearn.image import resample_img

    # If transform is a path, try to load it
    if isinstance(affine_transform, (str, Path)):
        if str(affine_transform).endswith('.mat'):
            # Try to load ANTs .mat file
            affine_matrix = load_ants_affine(affine_transform)
        elif str(affine_transform).endswith('.npy'):
            affine_matrix = np.load(affine_transform)
        else:
            raise ValueError(f"Unknown affine format: {affine_transform}")
    else:
        affine_matrix = affine_transform

    # Compute inverse (we want MNI → native)
    try:
        inv_affine = np.linalg.inv(affine_matrix)
    except np.linalg.LinAlgError:
        print("Warning: Affine matrix is singular, using pseudo-inverse")
        inv_affine = np.linalg.pinv(affine_matrix)

    # Apply transform to atlas affine
    transformed_affine = inv_affine @ atlas_img.affine

    # Create transformed atlas
    atlas_transformed = nib.Nifti1Image(
        atlas_img.get_fdata(),
        transformed_affine,
        atlas_img.header
    )

    # Resample to reference grid
    print(f"   Resampling atlas to reference space...")
    resampled = resample_img(
        atlas_transformed,
        target_affine=reference_img.affine,
        target_shape=reference_img.shape[:3],  # Handle 3D/4D
        interpolation='nearest',  # Preserve labels
        force_resample=True
    )

    return resampled


def load_ants_affine(mat_file_path):
    """
    Load ANTs .mat affine transform file

    ANTs .mat files are text files with specific format.

    Args:
        mat_file_path: Path to .mat file

    Returns:
        4x4 numpy array
    """
    try:
        import ants
        # ANTs can read its own format
        transform = ants.read_transform(mat_file_path)
        # Extract the matrix (this is implementation-dependent)
        # For now, return identity and warn
        print("Warning: ANTs .mat file loading not fully implemented, using identity")
        return np.eye(4)
    except Exception as e:
        print(f"Warning: Could not load ANTs .mat file: {e}")
        print("Using identity matrix as fallback")
        return np.eye(4)


def compute_jacobian_determinant(warp_field_path):
    """
    Compute Jacobian determinant from ANTs warp field

    The Jacobian determinant at each voxel indicates local volume change:
    - det(J) > 1: Local expansion
    - det(J) < 1: Local compression
    - det(J) = 1: No volume change

    Args:
        warp_field_path: Path to ANTs warp field (.nii.gz)

    Returns:
        numpy array of Jacobian determinants (same shape as warp field)
    """
    try:
        import ants
    except ImportError:
        raise ImportError("ANTsPy is required. Install with: pip install antspyx")

    # Load warp field
    warp = ants.image_read(str(warp_field_path))

    # Compute Jacobian
    jacobian = ants.create_jacobian_determinant_image(
        warp,
        do_log=False,  # Return determinant, not log(determinant)
        geom=False  # Use deformation field, not velocity field
    )

    return jacobian.numpy()


def compute_modulated_volume(roi_mask, jacobian_det, voxel_size_mm3):
    """
    Compute Jacobian-modulated volume for an ROI

    Args:
        roi_mask: Boolean array indicating ROI voxels
        jacobian_det: Array of Jacobian determinants (same shape as roi_mask)
        voxel_size_mm3: Voxel size in mm³

    Returns:
        Modulated volume in mm³
    """
    # For each voxel in ROI, multiply by local Jacobian
    # This accounts for local compression/expansion during registration
    modulated_volume = np.sum(roi_mask * jacobian_det) * voxel_size_mm3

    return modulated_volume


def apply_sitk_transform_to_atlas(atlas_img, transform, reference_img):
    """
    Apply SimpleITK transform to atlas

    Args:
        atlas_img: nibabel image of atlas in MNI space
        transform: SimpleITK transform object
        reference_img: nibabel image of native space reference

    Returns:
        nibabel image of atlas in native space
    """
    try:
        import SimpleITK as sitk
    except ImportError:
        raise ImportError("SimpleITK is required. Install with: pip install SimpleITK")

    # Convert nibabel → SimpleITK
    atlas_sitk = sitk.GetImageFromArray(
        atlas_img.get_fdata().transpose(2, 1, 0),  # nibabel uses different axis order
        isVector=False
    )
    atlas_sitk.SetOrigin(atlas_img.affine[:3, 3])
    atlas_sitk.SetSpacing(np.abs(np.diag(atlas_img.affine[:3, :3])))

    reference_sitk = sitk.GetImageFromArray(
        reference_img.get_fdata().transpose(2, 1, 0),
        isVector=False
    )
    reference_sitk.SetOrigin(reference_img.affine[:3, 3])
    reference_sitk.SetSpacing(np.abs(np.diag(reference_img.affine[:3, :3])))

    # Get inverse transform (MNI → native)
    try:
        inv_transform = transform.GetInverse()
    except:
        print("Warning: Could not invert transform, using original")
        inv_transform = transform

    # Resample atlas to reference space
    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(reference_sitk)
    resampler.SetInterpolator(sitk.sitkNearestNeighbor)  # Preserve labels
    resampler.SetTransform(inv_transform)

    warped_atlas_sitk = resampler.Execute(atlas_sitk)

    # Convert back to nibabel
    warped_array = sitk.GetArrayFromImage(warped_atlas_sitk).transpose(2, 1, 0)
    warped_atlas = nib.Nifti1Image(warped_array, reference_img.affine, reference_img.header)

    return warped_atlas


def validate_atlas_alignment(atlas_img, brain_img, slice_indices=None):
    """
    Visual validation of atlas alignment to brain

    Args:
        atlas_img: Registered atlas (nibabel image)
        brain_img: Native brain (nibabel image)
        slice_indices: List of slice indices to check (default: middle slices)

    Returns:
        Dictionary with alignment metrics
    """
    atlas_data = atlas_img.get_fdata()
    brain_data = brain_img.get_fdata()

    # Get brain mask
    brain_mask = brain_data > 0

    # Count atlas labels inside vs outside brain
    labels_inside = np.sum((atlas_data > 0) & brain_mask)
    labels_outside = np.sum((atlas_data > 0) & ~brain_mask)

    total_labels = labels_inside + labels_outside
    pct_inside = (labels_inside / total_labels * 100) if total_labels > 0 else 0

    # Check overlap of atlas with brain boundary
    from scipy.ndimage import binary_erosion
    brain_edge = brain_mask & ~binary_erosion(brain_mask, iterations=3)
    atlas_mask = atlas_data > 0

    edge_overlap = np.sum(atlas_mask & brain_edge) / np.sum(brain_edge) * 100

    metrics = {
        'labels_inside_brain_pct': pct_inside,
        'labels_outside_brain_pct': 100 - pct_inside,
        'edge_overlap_pct': edge_overlap,
        'total_labels': int(total_labels),
        'unique_label_count': len(np.unique(atlas_data)) - 1  # Exclude 0
    }

    # Quality assessment
    if pct_inside > 95 and edge_overlap > 50:
        metrics['quality'] = 'good'
    elif pct_inside > 85 and edge_overlap > 30:
        metrics['quality'] = 'acceptable'
    else:
        metrics['quality'] = 'poor'

    return metrics
