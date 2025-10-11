"""
Convert OASIS-1 ANALYZE format (.hdr/.img) to NIfTI format (.nii.gz)

OASIS-1 dataset uses the older ANALYZE format. This script converts all
brain scans to modern NIfTI format for processing.
"""

import os
import argparse
import nibabel as nib
from pathlib import Path
from typing import List, Dict


def find_oasis_analyze_files(root_dir: str) -> List[str]:
    """
    Find all ANALYZE .hdr files in OASIS directory structure

    OASIS structure: disc*/OAS1_*_MR*/PROCESSED/MPRAGE/T88_111/*.hdr

    Args:
        root_dir: Root directory containing OASIS data

    Returns:
        List of paths to .hdr files
    """
    hdr_files = []
    root_path = Path(root_dir)

    # Find all .hdr files in T88_111 directories (atlas-aligned scans)
    for hdr_file in root_path.rglob("PROCESSED/MPRAGE/T88_111/*_t88_gfc.hdr"):
        hdr_files.append(str(hdr_file))

    return sorted(hdr_files)


def convert_analyze_to_nifti(hdr_path: str, output_dir: str = None, compress: bool = True) -> str:
    """
    Convert ANALYZE format to NIfTI format

    Args:
        hdr_path: Path to .hdr file
        output_dir: Output directory (default: same as input)
        compress: Save as .nii.gz instead of .nii

    Returns:
        Path to converted NIfTI file
    """
    # Load ANALYZE format
    img = nib.load(hdr_path)

    # Handle 4D images with trailing singleton dimension
    # ANALYZE files sometimes have shape (x, y, z, 1) instead of (x, y, z)
    if len(img.shape) == 4 and img.shape[3] == 1:
        print(f"  ℹ️  Squeezing 4D image {img.shape} to 3D")
        data = img.get_fdata().squeeze()
        img = nib.Nifti1Image(data, img.affine, img.header)

    # Determine output path
    if output_dir is None:
        output_dir = os.path.dirname(hdr_path)
    else:
        os.makedirs(output_dir, exist_ok=True)

    # Generate output filename
    base_name = os.path.basename(hdr_path).replace('.hdr', '')
    extension = '.nii.gz' if compress else '.nii'
    output_path = os.path.join(output_dir, base_name + extension)

    # Save as NIfTI
    nib.save(img, output_path)

    return output_path


def convert_oasis_dataset(
    input_dir: str,
    output_dir: str = None,
    compress: bool = True,
    organize_by_subject: bool = True
) -> Dict:
    """
    Convert entire OASIS-1 dataset from ANALYZE to NIfTI

    Args:
        input_dir: Root directory with OASIS raw data
        output_dir: Output directory for NIfTI files (default: input_dir/nifti)
        compress: Save as .nii.gz instead of .nii
        organize_by_subject: Organize output by subject ID

    Returns:
        Dictionary with conversion statistics
    """

    if output_dir is None:
        output_dir = os.path.join(input_dir, '../nifti')

    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print("OASIS-1 ANALYZE → NIfTI CONVERTER")
    print(f"{'='*60}")
    print(f"Input directory: {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Compression: {'.nii.gz' if compress else '.nii'}")
    print(f"{'='*60}\n")

    # Find all ANALYZE files
    print("🔍 Scanning for ANALYZE files...")
    hdr_files = find_oasis_analyze_files(input_dir)
    print(f"✓ Found {len(hdr_files)} brain scans to convert\n")

    results = {
        'total_files': len(hdr_files),
        'converted': 0,
        'failed': 0,
        'output_files': []
    }

    # Convert each file
    for i, hdr_path in enumerate(hdr_files, 1):
        try:
            # Extract subject ID from path
            subject_id = None
            if 'OAS1_' in hdr_path:
                parts = hdr_path.split('OAS1_')[1].split('_')
                subject_id = f"OAS1_{parts[0]}_MR1"

            # Determine output location
            if organize_by_subject and subject_id:
                subject_output_dir = os.path.join(output_dir, subject_id)
            else:
                subject_output_dir = output_dir

            print(f"[{i}/{len(hdr_files)}] Converting {subject_id or 'unknown'}...")

            # Convert
            output_path = convert_analyze_to_nifti(
                hdr_path,
                output_dir=subject_output_dir,
                compress=compress
            )

            results['converted'] += 1
            results['output_files'].append(output_path)
            print(f"  ✓ Saved to: {output_path}")

        except Exception as e:
            print(f"  ❌ Failed: {str(e)}")
            results['failed'] += 1

    # Print summary
    print(f"\n{'='*60}")
    print("CONVERSION SUMMARY")
    print(f"{'='*60}")
    print(f"Total files: {results['total_files']}")
    print(f"Converted: {results['converted']}")
    print(f"Failed: {results['failed']}")
    print(f"Output directory: {output_dir}")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Convert OASIS-1 ANALYZE format to NIfTI format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert all OASIS-1 scans
  python -m functions.convert_oasis_to_nifti research/input/datasets/oasis-1/raw

  # Convert to specific output directory
  python -m functions.convert_oasis_to_nifti research/input/datasets/oasis-1/raw \\
      --output /data/oasis-nifti

  # Convert without compression (save as .nii instead of .nii.gz)
  python -m functions.convert_oasis_to_nifti research/input/datasets/oasis-1/raw \\
      --no-compress
        """
    )

    parser.add_argument(
        'input_dir',
        type=str,
        help='Input directory containing OASIS raw data'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output directory for NIfTI files (default: input_dir/../nifti)'
    )

    parser.add_argument(
        '--no-compress',
        action='store_true',
        help='Save as .nii instead of .nii.gz'
    )

    parser.add_argument(
        '--flat',
        action='store_true',
        help='Save all files in one directory (don\'t organize by subject)'
    )

    args = parser.parse_args()

    try:
        result = convert_oasis_dataset(
            input_dir=args.input_dir,
            output_dir=args.output,
            compress=not args.no_compress,
            organize_by_subject=not args.flat
        )

        print("\n✅ Conversion complete!")
        print(f"   Converted {result['converted']} scans")
        print(f"   NIfTI files ready for processing")

    except Exception as e:
        print(f"\n❌ Error during conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)