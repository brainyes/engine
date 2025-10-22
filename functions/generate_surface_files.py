import os
import argparse
import subprocess
import tempfile
from datetime import datetime

from utilities.data import supabase

FUNCTION_NAME = "generate_surface_files"

def generate_surface_files(nifti_file_id, freesurfer_output_directory=None, subject_id=None, **kwargs):
    """
    Generate ASCII surface files (.asc) from FreeSurfer binary surface files.

    This function can work in two modes:
    1. Local mode: If freesurfer_output_directory is provided and exists, uses local files
    2. Remote mode: Downloads FreeSurfer surface files (.pial) from object storage

    After conversion, uploads .asc files to the visualization directory in storage.

    Storage structure in freesurfer-outputs bucket:
        {nifti_file_id}/surf/           - Binary surface files (.pial)
        {nifti_file_id}/visualization/  - ASCII surface files (.asc, generated here)

    Args:
        nifti_file_id (str): The ID of the NIFTI file whose FreeSurfer surfaces to process
        freesurfer_output_directory (str, optional): Path to local FreeSurfer output directory.
                                                     If provided and exists, uses local files.
                                                     Otherwise downloads from storage.
        subject_id (str, optional): FreeSurfer subject identifier (for consistency with pipeline)
        **kwargs: Additional parameters

    Returns:
        dict: Results with paths to generated surface files
    """

    print(f"Generating surface files for NIFTI file: {nifti_file_id}")

    ########## FUNCTION LOGIC STARTS ##########

    hemispheres = ["lh", "rh"]
    surface_types = ["pial"]  # Can add 'white', 'inflated' if needed later
    surface_files = {}

    # Determine if we're using local files or downloading from storage
    use_local_files = freesurfer_output_directory and os.path.exists(freesurfer_output_directory)

    if use_local_files:
        print(f"Using local FreeSurfer directory: {freesurfer_output_directory}")
        surf_directory = os.path.join(freesurfer_output_directory, "surf")
        if not os.path.exists(surf_directory):
            print(f"⚠️  Local surf directory not found: {surf_directory}")
            print("Falling back to downloading from storage...")
            use_local_files = False

    try:
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()

        if use_local_files:
            # Use local files
            print(f"\n📁 Using local FreeSurfer surface files from {surf_directory}")
        else:
            # Download from storage
            print(f"\n📥 Downloading FreeSurfer surface files from storage...")

        for hemi in hemispheres:
            for surf_type in surface_types:
                binary_filename = f"{hemi}.{surf_type}"

                if use_local_files:
                    # Use local file
                    input_surface = os.path.join(surf_directory, binary_filename)
                    if not os.path.exists(input_surface):
                        print(f"⚠️  Surface file not found: {input_surface}, skipping...")
                        continue
                    print(f"Using local file: {binary_filename}")
                else:
                    # Download binary surface file from storage
                    storage_path = f"{nifti_file_id}/surf/{binary_filename}"

                    try:
                        print(f"Downloading: {storage_path}")
                        response = supabase.storage.from_("freesurfer-outputs").download(storage_path)

                        # Save to temporary file
                        input_surface = os.path.join(temp_dir, binary_filename)
                        with open(input_surface, 'wb') as f:
                            f.write(response)

                        print(f"✅ Downloaded {binary_filename}")

                    except Exception as e:
                        print(f"⚠️  Could not download {binary_filename}: {str(e)}, skipping...")
                        continue

                # Convert to ASCII format
                output_filename = f"{hemi}.asc"
                output_path = os.path.join(temp_dir, output_filename)

                # Run mris_convert command
                print(f"🔄 Converting {binary_filename} to {output_filename}...")
                cmd = ["mris_convert", input_surface, output_path]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 min timeout
                )

                if result.returncode != 0:
                    raise Exception(f"mris_convert failed for {hemi}.{surf_type}: {result.stderr}")

                print(f"✅ Successfully converted {hemi}.{surf_type} to ASCII")

                # Upload to Supabase storage
                vis_storage_path = f"{nifti_file_id}/visualization/{output_filename}"

                with open(output_path, 'rb') as f:
                    file_data = f.read()

                print(f"📤 Uploading {output_filename} to storage...")
                upload_result = supabase.storage.from_("freesurfer-outputs").upload(
                    file=file_data,
                    path=vis_storage_path,
                    file_options={"content-type": "text/plain", "upsert": "true"}
                )

                surface_files[f"{hemi}_{surf_type}"] = vis_storage_path
                print(f"✅ Uploaded: {vis_storage_path}")

        # Cleanup temp directory
        import shutil
        shutil.rmtree(temp_dir)

        result = {
            "nifti_file_id": nifti_file_id,
            "status": "completed",
            "surface_files": surface_files,
            "storage_bucket": "freesurfer-outputs",
            "hemispheres_processed": hemispheres,
            "surface_types_processed": surface_types,
            "message": f"Successfully generated and uploaded {len(surface_files)} surface files",
            "created_at": datetime.now().isoformat()
        }

        ########## FUNCTION LOGIC ENDS ##########

        print(f"\n✅ Surface file generation completed!")
        print(f"📊 Summary:")
        print(f"   - Files generated: {len(surface_files)}")
        print(f"   - Storage bucket: freesurfer-outputs")
        print(f"   - Storage path: {nifti_file_id}/visualization/")

        return result

    except subprocess.TimeoutExpired:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "status": "failed",
            "error": "Surface conversion timed out",
            "message": "mris_convert command timed out after 5 minutes"
        }
        print(f"\n❌ Error: Surface conversion timed out")
        return error_result

    except Exception as e:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "status": "failed",
            "error": str(e),
            "message": f"Surface file generation failed: {str(e)}"
        }
        print(f"\n❌ Error: {str(e)}")
        return error_result


# Command line interface for scientists
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generate ASCII surface files (.asc) from FreeSurfer binary surface files'
    )
    parser.add_argument('nifti_file_id', help='NIFTI file ID whose FreeSurfer surfaces to process')
    parser.add_argument('--freesurfer-dir', help='Path to local FreeSurfer output directory (optional). If not provided, downloads from storage.')

    args = parser.parse_args()

    print(f"=== SURFACE FILE GENERATOR ===")
    print(f"Processing NIFTI file ID: {args.nifti_file_id}")
    if args.freesurfer_dir:
        print(f"Local FreeSurfer directory: {args.freesurfer_dir}")
    print("\nThis will:")
    if args.freesurfer_dir:
        print("  1. Use local FreeSurfer binary surface files (.pial)")
    else:
        print("  1. Download FreeSurfer binary surface files (.pial) from freesurfer-outputs bucket")
    print("  2. Convert them to ASCII format (.asc) using mris_convert")
    print("  3. Upload .asc files to freesurfer-outputs/{nifti_file_id}/visualization/")
    print("\nPlease wait...\n")

    try:
        result = generate_surface_files(
            args.nifti_file_id,
            freesurfer_output_directory=args.freesurfer_dir
        )

        if result['status'] == 'completed':
            print(f"\n=== GENERATION COMPLETE ===")
            print("✅ Surface files generated successfully")
            print(f"\n📁 Files created:")
            for key, path in result['surface_files'].items():
                print(f"   - {key}: {path}")

        else:
            print(f"\n=== GENERATION FAILED ===")
            print(f"❌ Error: {result.get('error', 'Unknown error')}")
            print(f"\nTroubleshooting:")
            print("   - Ensure FreeSurfer is installed and mris_convert is in PATH")
            print("   - Verify FreeSurfer output directory exists")
            print("   - Check that surf/ directory contains .pial files")

    except Exception as e:
        print(f"\n❌ Error during generation: {str(e)}")
        print("\nPlease check:")
        print("   - FreeSurfer installation")
        print("   - File paths are correct")
        print("   - Storage permissions are configured")
        os._exit(1)

    # Force exit to prevent hanging
    os._exit(0)
