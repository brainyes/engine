import os

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import plotting
from nilearn.image import resample_img

from options import silent_run, output_dir, save_assets, atlas_file_path


def resample_atlas_for_user(nifti_img):
    atlas_img = nib.load(atlas_file_path)
    resampled_atlas = resample_img(atlas_img, target_affine=nifti_img.affine, target_shape=nifti_img.shape)
    voxel_size = np.abs(np.linalg.det(resampled_atlas.affine[:3, :3]))

    if save_assets or not silent_run:
        # Visualize the original and resampled Harvard-Oxford Atlas
        plotting.plot_roi(atlas_img, title="Original Harvard-Oxford Atlas")
        plotting.plot_roi(resampled_atlas, title="Resampled Harvard-Oxford Atlas for User")
        plt.savefig(os.path.join(output_dir, 'resample_atlas_for_user.png'))
        if not silent_run:
            plt.show()

    return resampled_atlas, voxel_size
