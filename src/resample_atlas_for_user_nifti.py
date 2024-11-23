import os
import tempfile

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import plotting
from nilearn.image import resample_img

from options import silent_run, output_dir, save_assets, atlas_file_path
from data import supabase
from supabase_utilities import get_nifti_file
from utilities import prefix_file_in_path


def resample_atlas_for_user_nifti(nifti_file_id):
    nifti_file, storage_object, nifti_gz_path = get_nifti_file(nifti_file_id, True)

    user_nifti = nib.load(nifti_gz_path)
    atlas_img = nib.load(atlas_file_path)

    resampled_atlas = resample_img(atlas_img, target_affine=user_nifti.affine, target_shape=user_nifti.shape)
    # temp_file = tempfile.NamedTemporaryFile(prefix="resampled_atlas_",
    #                                         suffix="nii.gz",
    #                                         delete=False)
    # resampled_atlas.to_filename(temp_file.name)
    voxel_size = np.abs(np.linalg.det(resampled_atlas.affine[:3, :3]))

    if save_assets or not silent_run:
        # Visualize the original and resampled Harvard-Oxford Atlas
        plotting.plot_roi(atlas_img, title="Original Harvard-Oxford Atlas")
        plotting.plot_roi(resampled_atlas, title="Resampled Harvard-Oxford Atlas for User")
        plt.savefig(os.path.join(output_dir, 'resample_atlas_for_user.png'))
        if not silent_run:
            plt.show()

    upload_res = supabase.storage.from_("nifti_gz_files").upload(
        file=resampled_atlas.to_bytes(), path=prefix_file_in_path("atlas-resampled", storage_object['name']),
        file_options={"content-type": "application/octet-stream; charset=binary", "upsert": "true"})
    upload_obj = upload_res.json()

    atlas_sampled_nifti_file = supabase.schema("public").table("nifti_files").upsert({
        "id": upload_obj['Id'],
        "parent_nifti_file_id": nifti_file['id'],
        "user_id": nifti_file['user_id'],
        "file_type": "atlas-sampled.nii"
    }).execute().data

    # save voxel_size
    user_meta = (supabase.schema("public")
                 .rpc("set_user_meta", {"p_user_id": nifti_file['user_id'], "p_meta_key": "voxel_size", "p_meta_value": voxel_size})
                 .single().execute()).data

    return atlas_sampled_nifti_file, user_meta

# example:
if __name__=="__main__":
    result = resample_atlas_for_user_nifti("1a0ffcbb-75e6-4e10-9273-4d7f7ad143ca")
    print(result)
