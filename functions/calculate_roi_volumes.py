import inngest
import numpy as np
import nibabel as nib
import argparse
import os

from utilities.inngest import client as inngest_client
from utilities.data import supabase
from utilities.supabase_utilities import get_nifti_file, get_user_meta, download_resampled_atlas


def calculate_roi_volumes(nifti_file_id):
    # Get the user's original nifti file
    response = supabase.schema("public").rpc("get_file_type_among_children", {"p_nifti_file_id": nifti_file_id,
                                                                             "p_file_type": "nii"}).single().execute()
    user_nifti_file = response.data
    user_nifti_file, _, user_nifti_gz_path = get_nifti_file(user_nifti_file, True)
    user_nifti = nib.load(user_nifti_gz_path)

    # Download resampled atlas from storage
    atlas_sampled_nifti_gz_path = download_resampled_atlas(user_nifti_file['user_id'], nifti_file_id)
    atlas_sampled_nifti = nib.load(atlas_sampled_nifti_gz_path)

    # Try to get voxel_size from usermeta, or compute from affine matrix
    voxel_size = get_user_meta(user_nifti_file['user_id'], 'voxel_size')
    if voxel_size is None:
        # Compute voxel size directly from NIFTI affine matrix
        voxel_size = np.abs(np.linalg.det(user_nifti.affine[:3, :3]))
        print(f"ℹ️  Voxel size not in usermeta, computed from affine: {voxel_size}")

    data = user_nifti.get_fdata()
    roi_volumes = {}

    atlas_data = atlas_sampled_nifti.get_fdata()

    # Iterate through unique ROI labels in the atlas
    for roi_label in np.unique(atlas_data):
        if roi_label == 0:  # Skip the background label
            continue

        # Create a mask for the current ROI
        roi_mask = (atlas_data == roi_label)

        # Count the voxels in the ROI
        roi_voxel_count = np.sum(roi_mask & (data > 0))
        roi_volume = roi_voxel_count * voxel_size  # Convert voxel count to volume

        roi_volumes[roi_label] = roi_volume


    # save roi_volumes for the user's nifti file
    roi_volume_records = [
        {"nifti_file_id": nifti_file_id, "label": roi_label, "volume": float(roi_volume)}
        for roi_label, roi_volume in roi_volumes.items()
    ]
    response = (supabase.schema("public").table("roi_volumes")
                .upsert(roi_volume_records, on_conflict="nifti_file_id, label").execute())

    return response.data

@inngest_client.create_function(
    fn_id="calculate_roi_volumes",
    trigger=inngest.TriggerEvent(event="resampled_atlas_for_user_nifti"),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    res = calculate_roi_volumes(**parameters)
    await inngest_client.send(
        inngest.Event(name="calculated_roi_volumes")
    )
    return res

# example:
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Calculate brain region volumes from your uploaded NIFTI scan')
    parser.add_argument('file_id', help='File ID from the upload_nifti output')
    
    args = parser.parse_args()
    
    print("=== ROI VOLUME CALCULATION ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    print("This will measure the volume of each brain region...")
    print("Please wait, this may take 30-60 seconds...\n")
    
    try:
        result = calculate_roi_volumes(args.file_id)
        print("\n=== VOLUME CALCULATION COMPLETE ===")
        print(f"✅ Calculated volumes for {len(result)} brain regions")
        print("📊 Results saved to database.")
        print("\n🧠 Sample results (first 5 regions):")
        for i, region in enumerate(result[:5]):
            print(f"   Region {region['label']}: {region['volume']:.2f} cubic mm")
        if len(result) > 5:
            print(f"   ... and {len(result) - 5} more regions")
        
        print(f"\n🎉 Analysis complete! Your brain scan has been fully processed.")
        
    except Exception as e:
        print(f"❌ Error during volume calculation: {str(e)}")
        print("Please check your file ID and ensure atlas resampling was completed first.")
        os._exit(1)
    
    # Force exit to prevent hanging
    import os
    os._exit(0)
