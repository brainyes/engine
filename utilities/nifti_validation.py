
"""
NIFTI file validation and sanitization utilities

Validates that NIFTI files are proper medical MRI scans and not
RGB/RGBA color images, corrupted files, or other invalid formats.
"""

import numpy as np
import nibabel as nib
from typing import Tuple, Optional


class NiftiValidationError(ValueError):
    """Raised when a NIFTI file fails validation"""
    pass


def validate_and_load_nifti(img: nib.Nifti1Image, strict: bool = True) -> nib.Nifti1Image:
    """
    Validate and load NIFTI image data, ensuring it's suitable for medical image processing.
    
    This function checks for and rejects:
    - RGB/RGBA color images (structured dtypes with R,G,B fields)
    - Corrupted or invalid file formats
    - Non-numeric data types
    
    Args:
        img: Loaded nibabel NIFTI image
        strict: If True (default), reject RGB images. If False, convert RGB to grayscale with warning.
    
    Returns:
        Validated nibabel image with proper numeric dtype (float32)
        
    Raises:
        NiftiValidationError: If the file is not a valid medical MRI scan
    """
    
    print("\n=== NIFTI FILE VALIDATION ===")
    print(f"  Image shape: {img.shape}")
    print(f"  Header dtype: {img.header.get_data_dtype()}")
    print(f"  Dataobj dtype: {img.dataobj.dtype}")
    
    dtype = img.dataobj.dtype
    dtype_str = str(dtype)

    # Check for RGB/RGBA structured dtype (color images, not medical data)
    # dtype.kind == 'V' indicates void/structured types (includes RGB)
    if dtype.kind == 'V' or dtype_str.startswith('V') or 'void' in dtype_str.lower():
        # Check if it's an RGB/RGBA structured array
        if hasattr(img.dataobj.dtype, 'names') and img.dataobj.dtype.names:
            field_names = set(img.dataobj.dtype.names)
            
            if field_names <= {'R', 'G', 'B', 'A'}:
                # This is an RGB/RGBA color image
                error_msg = (
                    "❌ INVALID FILE: This is an RGB/RGBA color image, not a medical MRI scan!\n\n"
                    "This file appears to be a visualization or screenshot, not raw brain imaging data.\n"
                    "RGB images cannot be processed because they:\n"
                    "  • Have lost the original signal intensity information\n"
                    "  • Are pre-rendered visualizations\n"
                    "  • Cannot be used for accurate volumetric measurements\n\n"
                    "Please upload the original MRI scan file:\n"
                    "  ✓ DICOM files (.dcm) from the MRI scanner\n"
                    "  ✓ NIFTI files (.nii, .nii.gz) with grayscale intensity data\n"
                    "  ✓ Files with dtype: int16, float32, or float64\n\n"
                    f"Current file has dtype: {img.dataobj.dtype} (RGB color data)\n"
                    f"RGB fields detected: {field_names}"
                )
                
                if strict:
                    raise NiftiValidationError(error_msg)
                else:
                    # Non-strict mode: convert to grayscale with big warning
                    print(f"  ⚠️  {error_msg}")
                    print(f"  ⚠️  Converting to grayscale (strict=False), but results will NOT be medically accurate!")
                    return _convert_rgb_to_grayscale(img)
            
            # Other structured dtypes that aren't RGB
            error_msg = (
                f"❌ INVALID FILE: Unsupported structured dtype: {img.dataobj.dtype}\n\n"
                f"This file has a complex data structure that cannot be processed.\n"
                f"Field names: {img.dataobj.dtype.names}\n\n"
                "Please upload a standard medical MRI file with numeric intensity values."
            )
            raise NiftiValidationError(error_msg)
        
        # VoidDType but no field names - attempt recovery
        print(f"  ⚠️  WARNING: VoidDType detected without field names")
        print(f"  Attempting to recover data by reinterpreting bytes...")
        
        try:
            return _recover_void_dtype(img)
        except Exception as e:
            error_msg = (
                f"❌ INVALID FILE: Cannot interpret data format\n\n"
                f"The file has a VoidDType that cannot be converted to numeric data.\n"
                f"Error: {str(e)}\n\n"
                "This file may be corrupted or in an unsupported format.\n"
                "Try converting it with: mri_convert input.nii.gz output.nii.gz\n"
                "Or re-export from your DICOM viewer."
            )
            raise NiftiValidationError(error_msg) from e
    
    # Normal numeric dtype - validate and convert
    print(f"  ✓ Valid numeric dtype detected")
    return _normalize_to_float32(img)


def _convert_rgb_to_grayscale(img: nib.Nifti1Image) -> nib.Nifti1Image:
    """
    Convert RGB image to grayscale (for non-strict mode only)
    
    NOT RECOMMENDED - only for backwards compatibility or testing
    """
    raw_data = np.asarray(img.dataobj)
    
    # Extract RGB channels (each is uint8, 0-255)
    r = raw_data['R'].astype(np.float32)
    g = raw_data['G'].astype(np.float32)
    b = raw_data['B'].astype(np.float32)
    
    # Convert RGB to grayscale using standard luminance formula
    # Y = 0.299*R + 0.587*G + 0.114*B (ITU-R BT.601)
    grayscale_data = 0.299 * r + 0.587 * g + 0.114 * b
    
    print(f"  Converted RGB to grayscale: range [{grayscale_data.min():.2f}, {grayscale_data.max():.2f}]")
    
    return nib.Nifti1Image(grayscale_data, img.affine, img.header)


def _recover_void_dtype(img: nib.Nifti1Image) -> nib.Nifti1Image:
    """
    Attempt to recover data from VoidDType by reinterpreting bytes
    """
    raw_data = np.asarray(img.dataobj)
    itemsize = raw_data.dtype.itemsize
    
    print(f"  Item size: {itemsize} bytes")
    
    if itemsize == 4:
        print(f"  Reinterpreting as float32...")
        numeric_data = raw_data.view(np.float32).reshape(img.shape)
    elif itemsize == 2:
        print(f"  Reinterpreting as int16...")
        numeric_data = raw_data.view(np.int16).reshape(img.shape).astype(np.float32)
    elif itemsize == 8:
        print(f"  Reinterpreting as float64...")
        numeric_data = raw_data.view(np.float64).reshape(img.shape).astype(np.float32)
    else:
        raise ValueError(f"Unusual itemsize {itemsize} - cannot determine numeric type")
    
    print(f"  ✓ Recovered data: range [{numeric_data.min():.2f}, {numeric_data.max():.2f}]")
    
    return nib.Nifti1Image(numeric_data, img.affine, img.header)


def _normalize_to_float32(img: nib.Nifti1Image) -> nib.Nifti1Image:
    """
    Normalize image data to float32
    """
    data = img.get_fdata(dtype=np.float32)
    return nib.Nifti1Image(data, img.affine, img.header)


def squeeze_4d_to_3d(img: nib.Nifti1Image) -> nib.Nifti1Image:
    """
    Squeeze 4D images with trailing dimension of size 1 to 3D
    
    Args:
        img: nibabel image (3D or 4D)
        
    Returns:
        3D nibabel image
        
    Raises:
        ValueError: If image is 4D with more than 1 volume in 4th dimension
    """
    if len(img.shape) == 4:
        print(f"  ℹ️  Detected 4D image: {img.shape}")
        
        if img.shape[3] == 1:
            # Squeeze trailing dimension
            data = img.get_fdata()
            data_3d = np.squeeze(data, axis=3)
            img = nib.Nifti1Image(data_3d, img.affine, img.header)
            print(f"  ✓ Squeezed to 3D: {img.shape}")
        else:
            raise ValueError(
                f"Cannot process 4D image with {img.shape[3]} volumes.\n"
                f"Expected a single 3D volume (shape: {img.shape[:3]}, 1)\n"
                f"This may be a time-series or multi-echo acquisition.\n"
                f"Please extract a single volume before uploading."
            )
    
    return img


def validate_mri_dimensions(img: nib.Nifti1Image) -> None:
    """
    Validate that image dimensions are reasonable for brain MRI
    
    Raises:
        NiftiValidationError: If dimensions are unreasonable
    """
    shape = img.shape
    voxel_dims = img.header.get_zooms()[:3]
    
    # Check for obviously wrong dimensions
    if any(s < 10 for s in shape):
        raise NiftiValidationError(
            f"Image dimensions too small: {shape}\n"
            f"Brain MRI scans typically have dimensions > 100 in each axis."
        )
    
    if any(s > 2000 for s in shape):
        raise NiftiValidationError(
            f"Image dimensions too large: {shape}\n"
            f"Brain MRI scans typically have dimensions < 1000 in each axis."
        )
    
    # Check voxel size
    if any(v < 0.1 or v > 10 for v in voxel_dims):
        print(f"  ⚠️  WARNING: Unusual voxel size: {voxel_dims} mm")
        print(f"     Typical brain MRI: 0.5-2.0 mm isotropic")
    
    print(f"  ✓ Dimensions validated: {shape}, voxel size: {voxel_dims} mm")
