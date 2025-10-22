import os
import argparse
import json
import numpy as np
import nibabel as nib
import tempfile
import warnings
from datetime import datetime
from multiprocessing import Pool, cpu_count
from skimage.measure import marching_cubes
import trimesh

from utilities.data import supabase
from utilities.supabase_utilities import download_resampled_atlas
from utilities.atlas_config import list_atlases

# Suppress numpy warnings from permutation matrix operations
warnings.filterwarnings('ignore', category=RuntimeWarning, module='.*prepare_volume_visualization.*')

FUNCTION_NAME = "prepare_volume_visualization"


def process_region_batch(args):
    """
    Process a batch of regions in parallel.

    Args:
        args: Tuple of (region_labels_batch, atlas_data, affine, nifti_file_id, atlas_name)

    Returns:
        List of successfully processed region data
    """
    region_labels_batch, atlas_data, affine, nifti_file_id, atlas_name = args
    results = []

    # Import supabase in worker (needed for multiprocessing)
    from utilities.data import supabase

    for label in region_labels_batch:
        try:
            region_mask = (atlas_data == label).astype(np.uint8)

            # Skip if region too small
            voxel_count = np.sum(region_mask)
            if voxel_count < 50:
                continue

            # Generate mesh using marching cubes
            # Use the affine matrix to transform voxel coordinates to RAS world coordinates
            verts, faces, normals, values = marching_cubes(
                region_mask,
                level=0.5,
                spacing=(1.0, 1.0, 1.0)  # Unit spacing, will apply real transform via affine
            )

            # Apply full affine transformation to convert voxel coords to RAS coords
            # Create homogeneous coordinates
            verts_homogeneous = np.c_[verts, np.ones(len(verts))]

            # Apply affine transformation
            verts_world = verts_homogeneous @ affine.T
            verts_world = verts_world[:, :3]  # Remove homogeneous coordinate

            # Simplify mesh (reduce polygon count for performance)
            simplified_verts, simplified_faces = simplify_mesh(verts_world, faces, target_reduction=0.5)

            # Prepare mesh data
            mesh_data = {
                "vertices": simplified_verts.flatten().tolist(),
                "faces": simplified_faces.flatten().tolist(),
                "num_vertices": len(simplified_verts),
                "num_faces": len(simplified_faces),
                "label": int(label),
                "atlas": atlas_name,
                "voxel_count": int(voxel_count)
            }

            # Upload to storage
            storage_path = f"{nifti_file_id}/visualization/region_meshes/{atlas_name}/region_{int(label)}.json"
            json_data = json.dumps(mesh_data).encode('utf-8')

            supabase.storage.from_("freesurfer-outputs").upload(
                file=json_data,
                path=storage_path,
                file_options={"content-type": "application/json", "upsert": "true"}
            )

            results.append({"label": int(label), "success": True})

        except Exception as e:
            results.append({"label": int(label), "success": False, "error": str(e)})

    return results


def simplify_mesh(verts, faces, target_reduction=0.5):
    """
    Reduce mesh complexity for web performance using quadric edge collapse decimation.

    Args:
        verts: Vertex array (N x 3)
        faces: Face array (M x 3)
        target_reduction: Fraction of faces to remove (0.5 = reduce by 50%)

    Returns:
        Tuple of (simplified_vertices, simplified_faces)
    """
    # Skip simplification for very small meshes
    if len(faces) < 200:
        return verts, faces

    try:
        mesh = trimesh.Trimesh(vertices=verts, faces=faces)

        # Target face count (at least 100 faces)
        target_faces = max(100, int(len(faces) * (1 - target_reduction)))

        # Ensure target is actually less than current (otherwise simplification fails)
        if target_faces >= len(faces):
            return verts, faces

        # Simplify using quadric edge collapse
        # Use percent parameter instead of target face count (more reliable)
        reduction_percent = min(0.99, max(0.01, target_reduction))  # Clamp to valid range
        simplified = mesh.simplify_quadric_decimation(percent=reduction_percent)

        print(f"      Simplified: {len(faces)} → {len(simplified.faces)} faces ({target_reduction*100:.0f}% reduction)")
        return simplified.vertices, simplified.faces
    except Exception as e:
        # If simplification fails, return original mesh
        # This is OK - trimesh simplification is optional, just means larger files
        if "fast_simplification" not in str(e):
            print(f"      ⚠️  Mesh simplification skipped: {str(e)}")
        return verts, faces


def prepare_volume_visualization(nifti_file_id, **kwargs):
    """
    Generate 3D surface meshes for all atlas regions across all available atlases.

    This function creates volumetric-looking visualizations by generating surface meshes
    for each brain region using the marching cubes algorithm. These meshes can be rendered
    alongside FreeSurfer cortical surfaces in Three.js with semi-transparency to show
    deep brain structures.

    Process:
    1. For each atlas (FreeSurfer, Harvard-Oxford, HCPex)
    2. Load the resampled atlas aligned to the user's brain
    3. Extract each region as a binary mask
    4. Generate surface mesh using marching cubes
    5. Simplify mesh to reduce polygon count for web performance
    6. Save as JSON in same format as FreeSurfer surfaces

    Storage structure in freesurfer-outputs bucket:
        {nifti_file_id}/visualization/region_meshes/
            freesurfer/
                region_1.json
                region_2.json
            harvard-oxford/
                region_1.json
            hcpex/
                region_1.json
                ... (427 files)
            metadata.json

    Args:
        nifti_file_id (str): The ID of the NIFTI file to process
        **kwargs: Additional parameters

    Returns:
        dict: Results with summary of generated meshes
    """

    print(f"🧠 Preparing volume visualization for NIFTI file: {nifti_file_id}")

    ########## FUNCTION LOGIC STARTS ##########

    try:
        # Get user info for accessing resampled atlases
        response = supabase.schema("public").rpc(
            "get_file_type_among_children",
            {"p_nifti_file_id": nifti_file_id, "p_file_type": "nii"}
        ).single().execute()

        user_nifti_file = response.data
        user_id = user_nifti_file['user_id']

        # Get all available atlases
        atlases = list_atlases()
        total_regions = 0
        atlas_summaries = {}

        print(f"\n📋 Processing {len(atlases)} atlases: {', '.join(atlases.keys())}")

        for atlas_name in atlases.keys():
            print(f"\n{'='*60}")
            print(f"🔍 Processing {atlas_name} atlas...")
            print(f"{'='*60}")

            try:
                # Load resampled atlas aligned to user's brain
                atlas_path = download_resampled_atlas(user_id, nifti_file_id, atlas_name)

                # Fix: nibabel needs proper .nii.gz extension
                # The downloaded file might have incorrect extension, rename it
                if not atlas_path.endswith('.nii.gz') and not atlas_path.endswith('.nii'):
                    import shutil
                    correct_path = atlas_path + '.nii.gz' if atlas_path.endswith('.gz') else atlas_path + '.nii.gz'
                    shutil.move(atlas_path, correct_path)
                    atlas_path = correct_path

                atlas_img = nib.load(atlas_path)
                atlas_data = atlas_img.get_fdata()
                affine = atlas_img.affine

                print(f"   Original affine matrix:\n{affine}")

                # Validate affine matrix - check for NaN or Inf
                # Don't check diagonal - permutation matrices have zeros on diagonal
                if not np.all(np.isfinite(affine)):
                    print(f"   ⚠️  Warning: Affine contains NaN or Inf, using identity")
                    affine = np.eye(4)
                else:
                    # Check determinant to ensure it's a valid transformation
                    det = np.linalg.det(affine[:3, :3])
                    if np.abs(det) < 0.001:
                        print(f"   ⚠️  Warning: Affine determinant near zero ({det}), using identity")
                        affine = np.eye(4)
                    else:
                        print(f"   ✓ Valid affine matrix (det={det:.2f})")

                print(f"   Using affine:\n{affine}")

                # Get unique region labels (exclude background 0)
                region_labels = np.unique(atlas_data)
                region_labels = region_labels[region_labels != 0]

                print(f"   Found {len(region_labels)} regions")
                print(f"   Atlas shape: {atlas_data.shape}")

                # Use parallel processing for faster performance
                n_cores = cpu_count()
                print(f"   🚀 Using {n_cores} CPU cores for parallel processing")

                # Split regions into batches for each core
                batch_size = max(1, len(region_labels) // n_cores)
                region_batches = [
                    region_labels[i:i + batch_size]
                    for i in range(0, len(region_labels), batch_size)
                ]

                # Prepare arguments for each worker
                worker_args = [
                    (batch, atlas_data, affine, nifti_file_id, atlas_name)
                    for batch in region_batches
                ]

                # Process regions in parallel
                regions_processed = 0
                regions_skipped = 0

                with Pool(n_cores) as pool:
                    batch_results = pool.map(process_region_batch, worker_args)

                # Aggregate results
                for batch_result in batch_results:
                    for result in batch_result:
                        if result["success"]:
                            regions_processed += 1
                        else:
                            regions_skipped += 1
                            if "error" in result:
                                print(f"   ⚠️  Region {result['label']} failed: {result['error']}")

                print(f"   ✅ Parallel processing complete")

                atlas_summaries[atlas_name] = {
                    "total_regions": len(region_labels),
                    "regions_processed": regions_processed,
                    "regions_skipped": regions_skipped
                }

                total_regions += regions_processed

                print(f"   ✅ Completed {atlas_name}:")
                print(f"      Processed: {regions_processed}")
                print(f"      Skipped: {regions_skipped} (too small or errors)")

            except Exception as e:
                print(f"   ❌ Error processing {atlas_name} atlas: {str(e)}")
                atlas_summaries[atlas_name] = {
                    "error": str(e),
                    "regions_processed": 0
                }
                continue

        # Create master metadata file
        metadata = {
            "nifti_file_id": nifti_file_id,
            "total_regions_processed": total_regions,
            "atlases": atlas_summaries,
            "created_at": datetime.now().isoformat()
        }

        metadata_path = f"{nifti_file_id}/visualization/region_meshes/metadata.json"
        metadata_json = json.dumps(metadata, indent=2).encode('utf-8')

        supabase.storage.from_("freesurfer-outputs").upload(
            file=metadata_json,
            path=metadata_path,
            file_options={"content-type": "application/json", "upsert": "true"}
        )

        result = {
            "nifti_file_id": nifti_file_id,
            "status": "completed",
            "total_regions_processed": total_regions,
            "atlases_processed": list(atlases.keys()),
            "atlas_summaries": atlas_summaries,
            "storage_bucket": "freesurfer-outputs",
            "storage_path": f"{nifti_file_id}/visualization/region_meshes/",
            "created_at": datetime.now().isoformat()
        }

        ########## FUNCTION LOGIC ENDS ##########

        print(f"\n{'='*60}")
        print(f"✅ Volume visualization preparation completed!")
        print(f"{'='*60}")
        print(f"📊 Summary:")
        print(f"   Total regions processed: {total_regions}")
        print(f"   Atlases processed: {len(atlases)}")
        for atlas_name, summary in atlas_summaries.items():
            if 'error' not in summary:
                print(f"   {atlas_name}: {summary['regions_processed']} regions")
        print(f"   Storage path: freesurfer-outputs/{result['storage_path']}")

        return result

    except Exception as e:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "status": "failed",
            "error": str(e),
            "message": f"Volume visualization preparation failed: {str(e)}"
        }
        print(f"\n❌ Error: {str(e)}")
        return error_result


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generate 3D surface meshes for all brain regions across all atlases'
    )
    parser.add_argument('file_id', help='NIFTI file ID to process')

    args = parser.parse_args()

    print(f"=== VOLUME VISUALIZATION MESH GENERATOR ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    print("\nThis will:")
    print("  1. Load resampled atlases for this brain scan")
    print("  2. Extract each region as a 3D binary mask")
    print("  3. Generate surface mesh using marching cubes algorithm")
    print("  4. Simplify mesh for web performance")
    print("  5. Upload meshes to freesurfer-outputs/{file_id}/visualization/region_meshes/")
    print("\nPlease wait...\n")

    try:
        result = prepare_volume_visualization(args.file_id)

        if result['status'] == 'completed':
            print(f"\n=== GENERATION COMPLETE ===")
            print(f"✅ Successfully generated {result['total_regions_processed']} region meshes")
            print(f"\n📊 Atlas Breakdown:")
            for atlas_name, summary in result['atlas_summaries'].items():
                if 'error' not in summary:
                    print(f"   {atlas_name}: {summary['regions_processed']} regions")
            print(f"\n📁 Meshes stored in: {result['storage_path']}")
        else:
            print(f"\n=== GENERATION FAILED ===")
            print(f"❌ Error: {result.get('error', 'Unknown error')}")
            print(f"\nTroubleshooting:")
            print("   - Ensure atlas resampling completed successfully")
            print("   - Verify storage permissions are configured")
            print("   - Check that atlas files exist in storage")

    except Exception as e:
        print(f"\n❌ Error during generation: {str(e)}")
        print("\nPlease check:")
        print("   - File ID is correct")
        print("   - Atlas resampling completed successfully")
        print("   - Storage permissions are configured")
        os._exit(1)

    # Force exit to prevent hanging
    os._exit(0)
