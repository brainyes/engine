import inngest
import os
import argparse

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import plotting
from nilearn.image import resample_img

from utilities.options import silent_run, output_dir, save_assets, atlas_file_path
from utilities.data import supabase
from utilities.supabase_utilities import get_nifti_file, upload_resampled_atlas
from utilities.utilities import prefix_file_in_path
from utilities.inngest import client as inngest_client


def resample_atlas_for_user_nifti(nifti_file_id):
    nifti_file, storage_object, nifti_gz_path = get_nifti_file(nifti_file_id, True)

    user_nifti = nib.load(nifti_gz_path)
    atlas_img = nib.load(atlas_file_path)

    # Handle 4D images with trailing singleton dimension (defensive check)
    # Some NIfTI files may have shape (x, y, z, 1) instead of (x, y, z)
    target_shape = user_nifti.shape
    if len(target_shape) == 4 and target_shape[3] == 1:
        print(f"  ℹ️  Squeezing 4D image {target_shape} to 3D")
        user_nifti_data = user_nifti.get_fdata().squeeze()
        user_nifti = nib.Nifti1Image(user_nifti_data, user_nifti.affine, user_nifti.header)
        target_shape = user_nifti.shape

    resampled_atlas = resample_img(atlas_img, target_affine=user_nifti.affine, target_shape=target_shape)
    voxel_size = np.abs(np.linalg.det(resampled_atlas.affine[:3, :3]))

    if save_assets or not silent_run:
        # Visualize the original and resampled Harvard-Oxford Atlas
        plotting.plot_roi(atlas_img, title="Original Harvard-Oxford Atlas")
        plotting.plot_roi(resampled_atlas, title="Resampled Harvard-Oxford Atlas for User")
        plt.savefig(os.path.join(output_dir, 'resample_atlas_for_user.png'))
        if not silent_run:
            plt.show()

    # Upload resampled atlas to storage
    storage_path = upload_resampled_atlas(nifti_file['user_id'], nifti_file_id, resampled_atlas.to_bytes())
    print(f"✅ Uploaded resampled atlas to: {storage_path}")

    # save voxel_size (optional - may fail for anonymous/population users)
    user_meta = None
    try:
        user_meta = (supabase.schema("public")
                     .rpc("set_user_meta", {"p_user_id": nifti_file['user_id'], "p_meta_key": "voxel_size", "p_meta_value": voxel_size})
                     .single().execute()).data
        print("Saved voxel size: ", user_meta)
    except Exception as e:
        print(f"⚠️  Warning: Could not save voxel_size to usermeta (likely anonymous user): {str(e)}")
        print(f"   Voxel size: {voxel_size} (not persisted)")

    return {"storage_path": storage_path, "voxel_size": voxel_size, "user_meta": user_meta}

@inngest_client.create_function(
    fn_id="resample_atlas_for_user_nifti",
    trigger=inngest.TriggerEvent(event="uploaded_nifti"),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    res = resample_atlas_for_user_nifti(**parameters)
    print("fn res: ", res)
    return res

# example:
if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Resample brain atlas to match your uploaded NIFTI scan')
    parser.add_argument('file_id', help='File ID from the upload_nifti output')
    
    args = parser.parse_args()
    
    print(f"=== ATLAS RESAMPLING ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    print("This will align the brain atlas to match your scan...")
    print("Please wait, this may take 1-2 minutes...\n")
    
    try:
        result = resample_atlas_for_user_nifti(args.file_id)
        print("\n=== ATLAS RESAMPLING COMPLETE ===")
        print("Result:", result)
        
    except Exception as e:
        print(f"❌ Error during atlas resampling: {str(e)}")
        print("Please check your file ID and try again.")
        os._exit(1)
    
    # Force exit to prevent hanging
    os._exit(0)
