import os
import argparse
import json
import tempfile
from datetime import datetime

from utilities.data import supabase
from utilities.freesurfer_parsers import parse_annot_file

FUNCTION_NAME = "generate_visualization_data"

def generate_visualization_data(nifti_file_id, parcellation="aparc", **kwargs):
    """
    Generate visualization data (JSON files) for frontend from FreeSurfer outputs.

    This function downloads FreeSurfer annotation files from object storage,
    converts them to JSON format, and uploads them back to the same bucket
    under a 'visualization' directory for centralized per-nifti-file storage.

    Storage structure in freesurfer-outputs bucket:
        {nifti_file_id}/label/          - Original .annot files
        {nifti_file_id}/mri/            - Volume files
        {nifti_file_id}/surf/           - Surface files
        {nifti_file_id}/stats/          - Statistics files
        {nifti_file_id}/visualization/  - JSON files for frontend (generated here)

    Args:
        nifti_file_id (str): The ID of the NIFTI file whose FreeSurfer outputs to process
        parcellation (str): Parcellation type (default: "aparc" - Desikan-Killiany atlas).
                           Standard: "aparc", "aparc.DKTatlas", "aparc.a2009s"
                           Custom: "custom_regions_de_ki", "custom_regions", "mpm.vpnl", etc.
        **kwargs: Additional parameters

    Returns:
        dict: Results with paths to generated visualization files
    """

    print(f"Generating visualization data for NIFTI file: {nifti_file_id}")
    print(f"Parcellation: {parcellation}")

    ########## FUNCTION LOGIC STARTS ##########

    # Define annotation files to download for both hemispheres
    hemispheres = ["lh", "rh"]
    annot_files = {}
    visualization_files = {}

    # Storage paths in FreeSurfer outputs bucket
    storage_base_path = f"{nifti_file_id}/label"

    try:
        # Download annotation files from FreeSurfer outputs
        print(f"\n📥 Downloading annotation files from storage...")
        for hemi in hemispheres:
            annot_filename = f"{hemi}.{parcellation}.annot"
            storage_path = f"{nifti_file_id}/label/{annot_filename}"

            try:
                # Download from freesurfer-outputs bucket
                print(f"Downloading: {storage_path}")
                response = supabase.storage.from_("freesurfer-outputs").download(storage_path)

                # Save to temporary file
                temp_dir = tempfile.mkdtemp()
                local_path = os.path.join(temp_dir, annot_filename)
                with open(local_path, 'wb') as f:
                    f.write(response)

                annot_files[hemi] = local_path
                print(f"✅ Downloaded {annot_filename}")

            except Exception as e:
                raise FileNotFoundError(f"Could not download {annot_filename} from storage: {str(e)}")

        # Parse annotation files and convert to JSON
        print(f"\n🔄 Converting annotation files to JSON...")
        regions_data = {}

        for hemi in hemispheres:
            print(f"Processing {hemi} hemisphere...")
            annot_path = annot_files[hemi]

            # Use utility function to parse annotation file
            parsed_data = parse_annot_file(annot_path)

            regions_data[hemi] = parsed_data

            print(f"✅ {hemi}: {parsed_data['num_vertices']} vertices, {parsed_data['num_regions']} regions")

        # Upload JSON files to freesurfer-outputs bucket (centralized storage)
        print(f"\n📤 Uploading visualization JSON files to storage...")
        vis_storage_base = f"{nifti_file_id}/visualization"

        for hemi in hemispheres:
            # Create JSON filename
            json_filename = f"{hemi}.{parcellation}.regions.json"
            json_storage_path = f"{vis_storage_base}/{json_filename}"

            # Convert to JSON
            json_data = json.dumps(regions_data[hemi])

            # Upload to freesurfer-outputs bucket alongside other outputs
            try:
                response = supabase.storage.from_("freesurfer-outputs").upload(
                    file=json_data.encode('utf-8'),
                    path=json_storage_path,
                    file_options={"content-type": "application/json", "upsert": "true"}
                )

                visualization_files[hemi] = json_storage_path
                print(f"✅ Uploaded: {json_storage_path}")

            except Exception as e:
                raise Exception(f"Failed to upload {json_filename}: {str(e)}")

        # Store metadata in database (optional - would need a table)
        # For now, just return the file paths

        result = {
            "nifti_file_id": nifti_file_id,
            "parcellation": parcellation,
            "status": "completed",
            "hemispheres_processed": hemispheres,
            "visualization_files": visualization_files,
            "storage_bucket": "freesurfer-outputs",
            "storage_path": vis_storage_base,
            "regions_summary": {
                "lh_vertices": regions_data["lh"]["num_vertices"],
                "lh_regions": regions_data["lh"]["num_regions"],
                "rh_vertices": regions_data["rh"]["num_vertices"],
                "rh_regions": regions_data["rh"]["num_regions"],
            },
            "created_at": datetime.now().isoformat()
        }

        ########## FUNCTION LOGIC ENDS ##########

        print(f"\n✅ Visualization data generation completed!")
        print(f"📊 Summary:")
        print(f"   - Left hemisphere: {result['regions_summary']['lh_vertices']} vertices, {result['regions_summary']['lh_regions']} regions")
        print(f"   - Right hemisphere: {result['regions_summary']['rh_vertices']} vertices, {result['regions_summary']['rh_regions']} regions")
        print(f"   - Files stored in: freesurfer-outputs/{vis_storage_base}/")

        return result

    except Exception as e:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "parcellation": parcellation,
            "status": "failed",
            "error": str(e),
            "message": f"Visualization data generation failed: {str(e)}"
        }
        print(f"\n❌ Error: {str(e)}")
        return error_result


# Command line interface for scientists
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generate visualization data (JSON) from FreeSurfer outputs for frontend rendering'
    )
    parser.add_argument('file_id', help='NIFTI file ID whose FreeSurfer outputs to process')
    parser.add_argument(
        '--parcellation',
        default='aparc',
        help='FreeSurfer parcellation type. Standard: aparc, aparc.DKTatlas, aparc.a2009s. '
             'Custom: custom_regions_de_ki, custom_regions, mpm.vpnl, etc. (default: aparc)'
    )

    args = parser.parse_args()

    print(f"=== VISUALIZATION DATA GENERATOR ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    print(f"Parcellation: {args.parcellation}")
    print("\nThis will:")
    print("  1. Download FreeSurfer annotation files from freesurfer-outputs bucket")
    print("  2. Convert them to JSON format for frontend")
    print("  3. Upload JSON files to freesurfer-outputs/{file_id}/visualization/")
    print("\nPlease wait...\n")

    try:
        result = generate_visualization_data(args.file_id, parcellation=args.parcellation)

        if result['status'] == 'completed':
            print(f"\n=== GENERATION COMPLETE ===")
            print("✅ Visualization data generated successfully")
            print(f"\n📁 Files created:")
            for hemi, path in result['visualization_files'].items():
                print(f"   - {hemi}: {path}")

            print(f"\n📊 Region Statistics:")
            summary = result['regions_summary']
            print(f"   - Left hemisphere: {summary['lh_vertices']:,} vertices, {summary['lh_regions']} regions")
            print(f"   - Right hemisphere: {summary['rh_vertices']:,} vertices, {summary['rh_regions']} regions")
            print(f"   - Path: {result['storage_path']}/")

        else:
            print(f"\n=== GENERATION FAILED ===")
            print(f"❌ Error: {result.get('error', 'Unknown error')}")
            print(f"\nTroubleshooting:")
            print("   - Ensure FreeSurfer outputs exist for this file ID")
            print("   - Verify annotation files are in freesurfer-outputs bucket")
            print("   - Check storage permissions are configured")

    except Exception as e:
        print(f"\n❌ Error during generation: {str(e)}")
        print("\nPlease check:")
        print("   - File ID is correct")
        print("   - FreeSurfer processing completed successfully")
        print("   - Storage permissions are configured")
        os._exit(1)

    # Force exit to prevent hanging
    os._exit(0)