"""
Prepare atlases in OASIS template space (one-time preprocessing)

This script transforms standard MNI-space atlases (Harvard-Oxford, HCPex)
to OASIS template space, so they can be inverse-warped to individual subjects
registered to the OASIS template.

Workflow:
1. Register MNI152 → OASIS template (if not already done)
2. Apply forward warp to transform each atlas from MNI → OASIS space
3. Save OASIS-space atlases for future use

Only needs to be run once. Results are cached in:
  research/input/atlases/oasis-space/
"""

import os
import nibabel as nib
import ants

# Paths
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'research', 'input', 'templates')
ATLAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'research', 'input', 'atlases')

MNI_TEMPLATE = os.path.join(TEMPLATE_DIR, 'MNI152_T1_1mm_brain.nii.gz')
OASIS_TEMPLATE = os.path.join(TEMPLATE_DIR, 'OASIS_template', 'T_template0_BrainCerebellum.nii.gz')

# MNI-space atlases to transform
# OASIS versions will be stored as *-oasis.nii.gz in same directory
MNI_ATLASES = {
    'harvard-oxford': {
        'mni_path': os.path.join(ATLAS_DIR, 'harvard-oxford', 'HarvardOxford-cort-maxprob-thr25-2mm.nii.gz'),
        'oasis_path': os.path.join(ATLAS_DIR, 'harvard-oxford', 'HarvardOxford-cort-maxprob-thr25-2mm-oasis.nii.gz')
    },
    'hcpex': {
        'mni_path': os.path.join(ATLAS_DIR, 'hcpex', 'HCPex.nii.gz'),
        'oasis_path': os.path.join(ATLAS_DIR, 'hcpex', 'HCPex-oasis.nii.gz')
    },
}


def register_mni_to_oasis():
    """
    Register MNI152 template to OASIS template (one-time operation)

    Returns:
        Dictionary with transform file paths
    """
    output_dir = os.path.join(TEMPLATE_DIR, 'mni_to_oasis_registration')
    os.makedirs(output_dir, exist_ok=True)

    forward_warp = os.path.join(output_dir, 'forward_warp.nii.gz')
    inverse_warp = os.path.join(output_dir, 'inverse_warp.nii.gz')
    affine_mat = os.path.join(output_dir, 'affine.mat')

    # Check if already registered
    if os.path.exists(forward_warp) and os.path.exists(affine_mat):
        print(f"✓ MNI→OASIS registration already exists")
        return {
            'forward_warp': forward_warp,
            'inverse_warp': inverse_warp,
            'affine': affine_mat
        }

    print("Registering MNI152 → OASIS template (this takes ~15 minutes)...")
    print(f"  Fixed: OASIS template")
    print(f"  Moving: MNI152 template")

    # Load templates
    oasis_img = ants.image_read(OASIS_TEMPLATE)
    mni_img = ants.image_read(MNI_TEMPLATE)

    # Perform SyN registration
    print("  Running ANTs SyN registration...")
    result = ants.registration(
        fixed=oasis_img,
        moving=mni_img,
        type_of_transform='SyN',
        verbose=True
    )

    # Save transforms
    print("  Saving transforms...")

    # ANTs returns transforms in result['fwdtransforms'] and result['invtransforms']
    # For SyN: [composite.h5] or [warp.nii.gz, affine.mat]
    if len(result['fwdtransforms']) == 1:
        # Composite transform
        import shutil
        shutil.copy(result['fwdtransforms'][0], forward_warp.replace('.nii.gz', '.h5'))
        shutil.copy(result['invtransforms'][0], inverse_warp.replace('.nii.gz', '.h5'))
        print(f"  ✓ Saved: {forward_warp.replace('.nii.gz', '.h5')}")
        print(f"  ✓ Saved: {inverse_warp.replace('.nii.gz', '.h5')}")

        return {
            'forward_warp': forward_warp.replace('.nii.gz', '.h5'),
            'inverse_warp': inverse_warp.replace('.nii.gz', '.h5'),
            'affine': None
        }
    else:
        # Separate warp and affine
        import shutil
        shutil.copy(result['fwdtransforms'][0], forward_warp)  # warp
        shutil.copy(result['fwdtransforms'][1], affine_mat)    # affine
        shutil.copy(result['invtransforms'][1], inverse_warp)  # inverse warp

        print(f"  ✓ Saved: {forward_warp}")
        print(f"  ✓ Saved: {affine_mat}")
        print(f"  ✓ Saved: {inverse_warp}")

        return {
            'forward_warp': forward_warp,
            'inverse_warp': inverse_warp,
            'affine': affine_mat
        }


def transform_atlas_to_oasis(atlas_name, atlas_info, transforms):
    """
    Transform atlas from MNI space to OASIS space

    Args:
        atlas_name: Name of atlas (e.g., 'harvard-oxford')
        atlas_info: Dictionary with 'mni_path' and 'oasis_path'
        transforms: Dictionary with forward transform paths

    Returns:
        Path to OASIS-space atlas
    """
    mni_path = atlas_info['mni_path']
    output_path = atlas_info['oasis_path']

    # Check if already transformed
    if os.path.exists(output_path):
        print(f"  ✓ {atlas_name} already in OASIS space")
        return output_path

    print(f"  Transforming {atlas_name} atlas to OASIS space...")

    # Load atlas and template
    atlas_img = ants.image_read(mni_path)
    oasis_img = ants.image_read(OASIS_TEMPLATE)

    # Apply forward transform (MNI → OASIS)
    # Use nearest neighbor interpolation for label maps
    if transforms['affine']:
        # Separate warp and affine
        transformed = ants.apply_transforms(
            fixed=oasis_img,
            moving=atlas_img,
            transformlist=[transforms['forward_warp'], transforms['affine']],
            interpolator='nearestNeighbor'  # Critical for label preservation
        )
    else:
        # Composite transform
        transformed = ants.apply_transforms(
            fixed=oasis_img,
            moving=atlas_img,
            transformlist=[transforms['forward_warp']],
            interpolator='nearestNeighbor'
        )

    # Save transformed atlas
    ants.image_write(transformed, output_path)
    print(f"  ✓ Saved: {output_path}")

    # Verify labels were preserved
    original_labels = len(set(atlas_img.numpy().flatten().astype(int)))
    transformed_labels = len(set(transformed.numpy().flatten().astype(int)))
    print(f"    Original labels: {original_labels}, Transformed labels: {transformed_labels}")

    return output_path


def prepare_all_atlases():
    """
    Prepare all atlases in OASIS space (main entry point)
    """
    print("=" * 80)
    print("PREPARING ATLASES FOR OASIS TEMPLATE SPACE")
    print("=" * 80)
    print()

    # Check templates exist
    if not os.path.exists(MNI_TEMPLATE):
        raise FileNotFoundError(f"MNI template not found: {MNI_TEMPLATE}")
    if not os.path.exists(OASIS_TEMPLATE):
        raise FileNotFoundError(f"OASIS template not found: {OASIS_TEMPLATE}")

    print("Step 1: Register MNI152 → OASIS template")
    print("-" * 80)
    transforms = register_mni_to_oasis()
    print()

    print("Step 2: Transform atlases to OASIS space")
    print("-" * 80)
    oasis_atlases = {}

    for atlas_name, atlas_info in MNI_ATLASES.items():
        if not os.path.exists(atlas_info['mni_path']):
            print(f"  ⚠️  {atlas_name} not found: {atlas_info['mni_path']}")
            continue

        oasis_path = transform_atlas_to_oasis(atlas_name, atlas_info, transforms)
        oasis_atlases[atlas_name] = oasis_path

    print()
    print("=" * 80)
    print("SETUP COMPLETE")
    print("=" * 80)
    print("OASIS-space atlases saved alongside their MNI versions:")
    for atlas_name, oasis_path in oasis_atlases.items():
        print(f"  - {atlas_name}: {oasis_path}")
    print()
    print("These will be automatically used when processing OASIS datasets.")
    print()

    return oasis_atlases


if __name__ == '__main__':
    import sys

    try:
        prepare_all_atlases()
        print("✅ All atlases prepared successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
