"""
Register native-space scan to MNI152 template

Performs nonlinear (or affine) registration and generates:
1. Forward warp (native → MNI)
2. Inverse warp (MNI → native) ← This is what we use for atlas warping
3. Affine transform component

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


# Path to templates
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'research', 'input', 'templates')
MNI152_TEMPLATE_PATH = os.path.join(TEMPLATE_DIR, 'MNI152_T1_1mm_brain.nii.gz')
OASIS_TEMPLATE_PATH = os.path.join(TEMPLATE_DIR, 'OASIS_template', 'T_template0_BrainCerebellum.nii.gz')


def register_to_template(nifti_file_id, method='auto', template_path=None, template_name='mni152'):
    """
    Register native scan to template (MNI152 or OASIS)

    Args:
        nifti_file_id: ID of NIFTI file (must be preprocessed first)
        method: Registration method ('auto', 'ants_syn', 'ants_affine', 'sitk_affine')
        template_path: Path to template (overrides template_name if provided)
        template_name: Template to use ('mni152' or 'oasis', default: 'mni152')

    Returns:
        Dictionary with registration results:
        {
            'forward_warp': storage path (native→MNI),
            'inverse_warp': storage path (MNI→native),
            'affine_transform': storage path,
            'registration_method': method used,
            'quality_metric': registration quality score
        }
    """
    # Select template
    if template_path is None:
        if template_name.lower() == 'oasis':
            template_path = OASIS_TEMPLATE_PATH
            template_display = 'OASIS'
        else:
            template_path = MNI152_TEMPLATE_PATH
            template_display = 'MNI152'
    else:
        template_display = os.path.basename(template_path)

    print(f"=== REGISTERING TO {template_display} TEMPLATE: {nifti_file_id} ===")

    # Check capabilities
    caps = get_capabilities()

    if method == 'auto':
        method = caps['best_registration']['method']
        print(f"Auto-selected method: {method}")

    if method == 'none':
        raise RuntimeError("No registration method available. Install ANTsPy or SimpleITK.")

    # Load preprocessed brain
    print("\n1. Loading preprocessed brain...")
    try:
        brain_data = supabase.storage.from_("freesurfer-outputs").download(
            f"{nifti_file_id}/preprocessing/brain_n4.nii.gz"
        )
        brain_path = save_temp_file(brain_data, 'brain_n4.nii.gz')
        moving_img = nib.load(brain_path)
        print(f"  ✓ Loaded: {moving_img.shape}, {moving_img.header.get_zooms()[:3]} mm")
    except Exception as e:
        raise RuntimeError(
            f"Could not load preprocessed brain. "
            f"Run preprocess_native_scan first. Error: {e}"
        )

    # Load template
    print(f"\n2. Loading {template_display} template...")
    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"Template not found: {template_path}\n"
            f"Ensure templates are downloaded to {TEMPLATE_DIR}/"
        )

    fixed_img = nib.load(template_path)
    print(f"  ✓ Loaded: {fixed_img.shape}, {fixed_img.header.get_zooms()[:3]} mm")

    # Perform registration
    print(f"\n3. Performing registration ({method})...")
    print("  This may take several minutes...")

    if method == 'ants_syn':
        result = register_ants_syn(fixed_img, moving_img, nifti_file_id)
    elif method == 'ants_affine':
        result = register_ants_affine(fixed_img, moving_img, nifti_file_id)
    elif method == 'sitk_affine':
        result = register_sitk_affine(fixed_img, moving_img, nifti_file_id)
    else:
        raise ValueError(f"Unknown registration method: {method}")

    print(f"  ✓ Registration complete!")

    # Upload transforms to Supabase
    print("\n4. Uploading transforms to Supabase...")
    uploaded_paths = upload_transforms(nifti_file_id, result)

    # Update database
    print("\n5. Updating database...")
    try:
        db_result = (supabase.table('population_scans')
         .update({
             'registration_method': result['method']
         })
         .eq('nifti_file_id', nifti_file_id)
         .execute())

        if db_result.data and len(db_result.data) > 0:
            print(f"  ✓ Updated population_scans.registration_method = '{result['method']}'")
        else:
            print(f"  ⚠️  Database update returned no rows - population_scans record may not exist!")
            print(f"     Run batch_process_population_dataset to create the record first.")
    except Exception as e:
        print(f"  ⚠️  Could not update database: {e}")
        import traceback
        traceback.print_exc()

    # Cleanup temp files
    if os.path.exists(brain_path):
        os.remove(brain_path)

    final_result = {
        **uploaded_paths,
        'registration_method': result['method'],
        'quality_metric': result.get('quality_metric', None)
    }

    print("\n=== REGISTRATION COMPLETE ===")
    return final_result


def register_ants_syn(fixed_img, moving_img, file_id):
    """
    Register using ANTs Symmetric Normalization (SyN) - nonlinear

    This is the most accurate method but requires ANTsPy and takes longer.
    """
    try:
        import ants
    except ImportError:
        raise ImportError("ANTsPy required for nonlinear registration. Install: pip install antspyx")

    # Convert to ANTs images
    print("  Converting to ANTs format...")
    fixed_ants = ants.from_nibabel(fixed_img)
    moving_ants = ants.from_nibabel(moving_img)

    # Perform registration
    print("  Running ANTs SyN registration (this takes 5-10 minutes)...")
    registration = ants.registration(
        fixed=fixed_ants,
        moving=moving_ants,
        type_of_transform='SyN',  # Symmetric Normalization (nonlinear)
        verbose=True
    )

    # Save transforms to temp files
    output_dir = tempfile.mkdtemp()
    prefix = os.path.join(output_dir, f"{file_id}_")

    # ANTs saves: {prefix}0GenericAffine.mat, {prefix}1Warp.nii.gz, {prefix}1InverseWarp.nii.gz
    # We need to extract them from the registration object

    # Save forward warp
    forward_warp_path = f"{prefix}1Warp.nii.gz"
    if 'fwdtransforms' in registration and len(registration['fwdtransforms']) > 0:
        # Copy the warp file
        import shutil
        for transform in registration['fwdtransforms']:
            if 'Warp.nii.gz' in transform:
                shutil.copy(transform, forward_warp_path)
                break

    # Save inverse warp (THIS IS WHAT WE NEED FOR ATLAS)
    inverse_warp_path = f"{prefix}1InverseWarp.nii.gz"
    if 'invtransforms' in registration and len(registration['invtransforms']) > 0:
        import shutil
        for transform in registration['invtransforms']:
            if 'InverseWarp.nii.gz' in transform or 'Warp.nii.gz' in transform:
                shutil.copy(transform, inverse_warp_path)
                break

    # Save affine
    affine_path = f"{prefix}0GenericAffine.mat"
    if 'fwdtransforms' in registration:
        import shutil
        for transform in registration['fwdtransforms']:
            if '.mat' in transform:
                shutil.copy(transform, affine_path)
                break

    # Compute quality metric (mutual information or cross-correlation)
    quality_metric = None
    if hasattr(registration, 'metric_value'):
        quality_metric = float(registration['metric_value'])

    return {
        'method': 'ants_syn',
        'forward_warp_path': forward_warp_path if os.path.exists(forward_warp_path) else None,
        'inverse_warp_path': inverse_warp_path if os.path.exists(inverse_warp_path) else None,
        'affine_path': affine_path if os.path.exists(affine_path) else None,
        'quality_metric': quality_metric,
        'output_dir': output_dir
    }


def register_ants_affine(fixed_img, moving_img, file_id):
    """
    Register using ANTs affine-only (faster, linear only)
    """
    try:
        import ants
    except ImportError:
        raise ImportError("ANTsPy required. Install: pip install antspyx")

    # Convert to ANTs
    fixed_ants = ants.from_nibabel(fixed_img)
    moving_ants = ants.from_nibabel(moving_img)

    # Affine registration
    print("  Running ANTs affine registration (1-2 minutes)...")
    registration = ants.registration(
        fixed=fixed_ants,
        moving=moving_ants,
        type_of_transform='Affine',
        verbose=True
    )

    # Save transforms
    output_dir = tempfile.mkdtemp()
    prefix = os.path.join(output_dir, f"{file_id}_")

    affine_path = f"{prefix}0GenericAffine.mat"
    if 'fwdtransforms' in registration and len(registration['fwdtransforms']) > 0:
        import shutil
        shutil.copy(registration['fwdtransforms'][0], affine_path)

    # For affine-only, no separate warp files (affine is both forward and inverse)
    return {
        'method': 'ants_affine',
        'forward_warp_path': None,
        'inverse_warp_path': None,
        'affine_path': affine_path if os.path.exists(affine_path) else None,
        'quality_metric': registration.get('metric_value', None),
        'output_dir': output_dir
    }


def register_sitk_affine(fixed_img, moving_img, file_id):
    """
    Register using SimpleITK affine (fallback, no ANTs required)
    """
    try:
        import SimpleITK as sitk
    except ImportError:
        raise ImportError("SimpleITK required. Install: pip install SimpleITK")

    # Convert to SimpleITK
    print("  Converting to SimpleITK format...")
    fixed_sitk = nibabel_to_sitk(fixed_img)
    moving_sitk = nibabel_to_sitk(moving_img)

    # Set up registration
    print("  Running SimpleITK affine registration (2-3 minutes)...")
    registration = sitk.ImageRegistrationMethod()

    # Similarity metric
    registration.SetMetricAsMattesMutualInformation(numberOfHistogramBins=50)
    registration.SetMetricSamplingStrategy(registration.RANDOM)
    registration.SetMetricSamplingPercentage(0.01)

    # Optimizer
    registration.SetOptimizerAsGradientDescent(
        learningRate=1.0,
        numberOfIterations=100,
        convergenceMinimumValue=1e-6,
        convergenceWindowSize=10
    )
    registration.SetOptimizerScalesFromPhysicalShift()

    # Transform
    initial_transform = sitk.CenteredTransformInitializer(
        fixed_sitk,
        moving_sitk,
        sitk.AffineTransform(3),
        sitk.CenteredTransformInitializerFilter.GEOMETRY
    )
    registration.SetInitialTransform(initial_transform, inPlace=False)

    # Interpolator
    registration.SetInterpolator(sitk.sitkLinear)

    # Multi-resolution
    registration.SetShrinkFactorsPerLevel(shrinkFactors=[4, 2, 1])
    registration.SetSmoothingSigmasPerLevel(smoothingSigmas=[2, 1, 0])
    registration.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()

    # Execute
    final_transform = registration.Execute(fixed_sitk, moving_sitk)

    # Save transform
    output_dir = tempfile.mkdtemp()
    affine_path = os.path.join(output_dir, f"{file_id}_affine.tfm")
    sitk.WriteTransform(final_transform, affine_path)

    # Also save as numpy array for easier loading
    affine_matrix = sitk_transform_to_matrix(final_transform)
    affine_npy_path = os.path.join(output_dir, f"{file_id}_affine.npy")
    np.save(affine_npy_path, affine_matrix)

    # Quality metric
    quality_metric = registration.GetMetricValue()

    return {
        'method': 'sitk_affine',
        'forward_warp_path': None,
        'inverse_warp_path': None,
        'affine_path': affine_npy_path,  # Use numpy format for easier loading
        'quality_metric': float(quality_metric),
        'output_dir': output_dir
    }


def nibabel_to_sitk(img):
    """Convert nibabel image to SimpleITK"""
    import SimpleITK as sitk

    data = img.get_fdata().astype(np.float32)
    sitk_img = sitk.GetImageFromArray(data.transpose(2, 1, 0))

    # Set spacing and origin
    sitk_img.SetSpacing(img.header.get_zooms()[:3])
    sitk_img.SetOrigin(img.affine[:3, 3])

    # Set direction (rotation component of affine)
    spacing = np.array(img.header.get_zooms()[:3])
    rotation = img.affine[:3, :3] / spacing
    sitk_img.SetDirection(rotation.flatten())

    return sitk_img


def sitk_transform_to_matrix(transform):
    """Convert SimpleITK transform to 4x4 matrix"""
    import SimpleITK as sitk

    # Get parameters
    params = transform.GetParameters()
    fixed_params = transform.GetFixedParameters()

    # For AffineTransform, parameters are: [matrix (9), translation (3)]
    # Reconstruct 4x4 matrix
    matrix = np.eye(4)

    if isinstance(transform, sitk.AffineTransform):
        # Affine: 9 elements for 3x3 matrix + 3 for translation
        matrix[:3, :3] = np.array(params[:9]).reshape(3, 3)
        matrix[:3, 3] = params[9:12]

    return matrix


def upload_transforms(nifti_file_id, result):
    """Upload transform files to Supabase storage"""
    uploaded = {}

    output_dir = result.get('output_dir')

    # Upload forward warp
    if result.get('forward_warp_path') and os.path.exists(result['forward_warp_path']):
        with open(result['forward_warp_path'], 'rb') as f:
            storage_path = f"{nifti_file_id}/registration/forward_warp.nii.gz"
            supabase.storage.from_("freesurfer-outputs").upload(
                storage_path, f.read(), {'upsert': 'true'}
            )
            uploaded['forward_warp'] = storage_path
            print(f"  ✓ Uploaded: {storage_path}")

    # Upload inverse warp (MOST IMPORTANT)
    if result.get('inverse_warp_path') and os.path.exists(result['inverse_warp_path']):
        with open(result['inverse_warp_path'], 'rb') as f:
            storage_path = f"{nifti_file_id}/registration/inverse_warp.nii.gz"
            supabase.storage.from_("freesurfer-outputs").upload(
                storage_path, f.read(), {'upsert': 'true'}
            )
            uploaded['inverse_warp'] = storage_path
            print(f"  ✓ Uploaded: {storage_path} (CRITICAL: used for atlas warping)")

    # Upload affine
    if result.get('affine_path') and os.path.exists(result['affine_path']):
        with open(result['affine_path'], 'rb') as f:
            # Determine file extension
            if result['affine_path'].endswith('.mat'):
                ext = '.mat'
            elif result['affine_path'].endswith('.npy'):
                ext = '.npy'
            else:
                ext = '.tfm'

            storage_path = f"{nifti_file_id}/registration/affine{ext}"
            supabase.storage.from_("freesurfer-outputs").upload(
                storage_path, f.read(), {'upsert': 'true'}
            )
            uploaded['affine_transform'] = storage_path
            print(f"  ✓ Uploaded: {storage_path}")

    # Cleanup temp dir
    if output_dir and os.path.exists(output_dir):
        import shutil
        shutil.rmtree(output_dir)

    return uploaded


def save_temp_file(data_bytes, suffix):
    """Save bytes to temp file"""
    temp_path = os.path.join(tempfile.gettempdir(), suffix)
    with open(temp_path, 'wb') as f:
        f.write(data_bytes)
    return temp_path


# CLI
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Register native scan to MNI152 template'
    )
    parser.add_argument('file_id', help='NIFTI file ID (must be preprocessed first)')
    parser.add_argument('--method', default='auto',
                        choices=['auto', 'ants_syn', 'ants_affine', 'sitk_affine'],
                        help='Registration method (default: auto)')
    parser.add_argument('--template', default=None,
                        help='Path to MNI template (default: bundled MNI152)')

    args = parser.parse_args()

    try:
        result = register_to_template(
            args.file_id,
            method=args.method,
            template_path=args.template
        )
        print("\n✓ Registration successful!")
        print(f"  Method: {result['registration_method']}")
        if result.get('inverse_warp'):
            print(f"  Inverse warp: {result['inverse_warp']}")
        if result.get('affine_transform'):
            print(f"  Affine: {result['affine_transform']}")
        if result.get('quality_metric'):
            print(f"  Quality: {result['quality_metric']:.4f}")

    except Exception as e:
        print(f"\n✗ Registration failed: {e}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
