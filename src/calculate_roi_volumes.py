import numpy as np
import nibabel as nib

from data import supabase
from supabase_utilities import get_nifti_file, get_user_meta


def calculate_roi_volumes(nifti_file_id):
    response = supabase.schema("public").rpc("get_file_type_among_children", {"p_nifti_file_id": nifti_file_id,
                                                                             "p_file_type": "nii"}).single().execute()
    user_nifti_file = response.data
    user_nifti_file, _, user_nifti_gz_path = get_nifti_file(user_nifti_file, True)
    user_nifti = nib.load(user_nifti_gz_path)

    response = supabase.schema("public").rpc("get_file_type_among_children", {"p_nifti_file_id": nifti_file_id,
                                                                             "p_file_type": "atlas-sampled.nii"}).single().execute()
    atlas_sampled_nifti_file = response.data
    atlas_sampled_nifti_file, _, atlas_sampled_nifti_gz_path = get_nifti_file(atlas_sampled_nifti_file, True)
    atlas_sampled_nifti = nib.load(atlas_sampled_nifti_gz_path)

    voxel_size = get_user_meta(atlas_sampled_nifti_file['user_id'], 'voxel_size')

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

    return roi_volumes, response.data

# example:
if __name__=="__main__":
    result = calculate_roi_volumes("1a0ffcbb-75e6-4e10-9273-4d7f7ad143ca")
    print(result)