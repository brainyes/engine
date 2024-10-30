import os
import nibabel as nib
import numpy as np
from nilearn import plotting
from nilearn.image import resample_img
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# Options
silent_run = True
# Get the script's directory
script_dir = os.path.dirname(__file__)
dataset_dir = os.path.join(script_dir, 'input')
output_dir = os.path.join(script_dir, 'output')

# Load the downloaded Harvard-Oxford atlas (keep atlas paths absolute)
atlas_file_path = os.path.join(dataset_dir, 'HarvardOxford-cort-maxprob-thr25-2mm.nii.gz')
atlas_img = nib.load(atlas_file_path)

# Load a sample NIfTI image to check its shape and affine
sample_nifti_path = os.path.join(dataset_dir, 'sub-OASIS10001_ses-M00_T1w.nii.gz')
sample_nifti_img = nib.load(sample_nifti_path)

# Visualize the original and resampled Harvard-Oxford Atlas
plotting.plot_roi(atlas_img, title="Original Harvard-Oxford Atlas")
atlas_resampled = resample_img(
    atlas_img, target_affine=sample_nifti_img.affine, target_shape=sample_nifti_img.shape)
plotting.plot_roi(atlas_resampled, title="Resampled Harvard-Oxford Atlas")
plt.savefig(os.path.join(output_dir, 'Harvard-Oxford-atlas-resampled.png'))
if not silent_run:
    plt.show()

# Get voxel size
voxel_size = np.abs(np.linalg.det(atlas_resampled.affine[:3, :3]))

# Set up paths relative to the script directory
raw_dir = os.path.join(dataset_dir, 'raw')
tsv_file_path = os.path.join(dataset_dir, 'tsv_files', 'lab_1', 'OASIS_BIDS.tsv')

# Dictionary to store patient data
patient_data = {}

# Load neuropsychological data
neuro_data = pd.read_csv(tsv_file_path, sep='\t')


def calculate_roi_volumes(nifti_img, atlas_data, voxel_size):
    data = nifti_img.get_fdata()
    roi_volumes = {}

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

    return roi_volumes


# Get the total number of files for progress tracking
total_files = len([f for f in os.listdir(raw_dir) if f.endswith('.nii.gz')])
print(f"Total NIfTI files to process: {total_files}")

# Process each NIfTI file
for index, file_name in enumerate(os.listdir(raw_dir)):
    if file_name.endswith('.nii.gz'):
        file_path = os.path.join(raw_dir, file_name)
        nifti_img = nib.load(file_path)

        # Resample the atlas to the NIfTI image's space
        resampled_atlas = resample_img(
            atlas_img, target_affine=nifti_img.affine, target_shape=nifti_img.shape)

        # Calculate ROI volumes
        roi_volumes = calculate_roi_volumes(
            nifti_img, resampled_atlas.get_fdata(), voxel_size)

        # Assuming the patient ID is part of the file name
        patient_id = file_name.split('_')[0]

        # Store the result in the patient_data dictionary
        # @oytun THIS IS USER'S VOLUME DATA over atlas. TO BE STORED.
        patient_data[patient_id] = roi_volumes

        # Print progress every 10 files
        if (index + 1) % 10 == 0 or (index + 1) == total_files:
            print(f"Processed {index + 1}/{total_files}: {file_name}")

# Convert patient_data dictionary to a DataFrame
roi_volumes_df = pd.DataFrame.from_dict(patient_data, orient='index').fillna(0)
roi_volumes_df['total_volume'] = roi_volumes_df.sum(axis=1)
roi_volumes_df.index = roi_volumes_df.index.str.replace('sub-', '')

# Remove the 'sub-' prefix from the participant_id in the neuropsychological data to match the NIfTI participant_id format
neuro_data['participant_id'] = neuro_data['participant_id'].str.replace(
    'sub-', '')

# Merge neuropsychological data with the calculated ROI volumes based on the participant_id
combined_data = neuro_data.merge(
    roi_volumes_df, left_on='participant_id', right_index=True, how='inner')


# Save the combined data to a new CSV file using relative path
# @oytun: i believe this is an optional output in this script
combined_data.to_csv(os.path.join(
    output_dir, 'combined_patient_data.csv'), index=False)


roi_volume_columns = roi_volumes_df.columns.tolist()  # Get the ROI volume columns
roi_volumes_to_store = combined_data[["participant_id"] + roi_volume_columns]


# Define the list of attributes for correlation
list1 = ['sex', 'education_level', 'age_bl', 'cdr',
         'diagnosis_bl', 'MMS', 'cdr_global', 'diagnosis']

# Ensure that the combined data contains all attributes in list1
for attribute in list1:
    if attribute not in combined_data.columns:
        print(f"Warning: {attribute} not found in combined_data.")

# Select the relevant columns from the combined data, excluding participant_id
correlation_data = combined_data[roi_volume_columns + list1]

# Convert any non-numeric data to numeric (e.g., encoding categorical variables if necessary)
correlation_data_encoded = pd.get_dummies(correlation_data, drop_first=True)

# Calculate the correlation matrix
correlation_matrix = correlation_data_encoded.corr()

# Select only the relevant correlation values for the ROI volumes
correlation_matrix_roi = correlation_matrix.loc[roi_volume_columns,
                                                correlation_data_encoded.columns.difference(roi_volume_columns)]

# Print the shape of the correlation matrix
print(f"Correlation matrix shape: {correlation_matrix_roi.shape}")

# Visualize the correlation matrix using seaborn
plt.figure(figsize=(12, 8))
sns.heatmap(
    correlation_matrix_roi,
    annot=False,  # Disable annotations
    cmap='coolwarm',
    square=True,
    linewidths=0.5,  # Add linewidth between cells
    linecolor='white'  # Color of the lines between cells
)
plt.title('Correlation Matrix ROI Volumes - Attributes', fontsize=16)
plt.tight_layout()  # Adjust layout to make room for the title
plt.savefig(os.path.join(output_dir, 'correlation_matrix.png'))
if not silent_run:
    plt.show()

# Set the figure size for the plots
# Adjust height based on the number of ROIs
plt.figure(figsize=(15, len(roi_volume_columns) * 5))

# Loop through each ROI column to create scatter plots
for i, roi in enumerate(roi_volume_columns):
    # Create a subplot for each ROI
    plt.subplot(len(roi_volume_columns), 1, i + 1)
    plt.scatter(combined_data[roi], combined_data['MMS'], alpha=0.6)

    # Fit a regression line (optional)
    sns.regplot(x=combined_data[roi], y=combined_data['MMS'],
                scatter=False, color='red', ax=plt.gca())

    plt.title(f'Correlation between {roi} Volume and MMS Score')
    plt.xlabel(f'{roi} Volume (in mm³)')
    plt.ylabel('MMS Score')
    plt.grid(True)

plt.tight_layout()  # Adjust layout to avoid overlap
# Save the figure as a PDF
plt.tight_layout()
plt.savefig(os.path.join(
    output_dir, 'Correlation_Between_Total_Volume_and_MMS_Scores.pdf'), format='pdf')
plt.savefig(os.path.join(output_dir, 'Correlation_Between_Total_Volume_and_MMS_Scores.png'))
if not silent_run:
    plt.show()

# Set the figure size for the plot
plt.figure(figsize=(10, 6))

# Create a scatter plot with colors based on sex
sns.scatterplot(data=combined_data, x='total_volume',
                y='MMS', hue='sex', style='sex', alpha=0.7)

# Add labels and title
plt.title('Distribution of MMS Scores by Total Volume')
plt.xlabel('Total Volume (in mm³)')
plt.ylabel('MMS Score')
plt.grid(True)

# Display the legend
plt.legend(title='Sex')

# Show the plot
plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'Distribution of MMS Scores by Total Volume.png'))
if not silent_run:
    plt.show()

# Calculate the correlation of each ROI with the MMS score
correlation_with_mms = correlation_matrix_roi['MMS'].abs(
).sort_values(ascending=False)

# Get the top 3 most correlated ROIs
top_3_rois = correlation_with_mms.index[1:4]  # Exclude the MMS itself

# Print the top 3 correlations
print("Top 3 ROIs correlated with MMS:")
for roi in top_3_rois:
    correlation_value = correlation_with_mms[roi]
    print(f"{roi}: {correlation_value:.2f}")

# Set up the figure size for the plots
plt.figure(figsize=(15, 5))

# Loop through each of the top 3 ROIs to create scatter plots
for i, roi in enumerate(top_3_rois):
    plt.subplot(1, 3, i + 1)  # Create a subplot for each ROI
    plt.scatter(combined_data[roi], combined_data['MMS'], alpha=0.7)

    # Fit a regression line (optional)
    sns.regplot(x=combined_data[roi], y=combined_data['MMS'],
                scatter=False, color='red', ax=plt.gca())

    # Add labels and title
    plt.title(f'Correlation: #ROI {roi} Volume - MMS Score')
    plt.xlabel(f'#ROI {roi} Volume (in mm³)')
    plt.ylabel('MMS Score')
    plt.grid(True)

plt.tight_layout()  # Adjust layout to avoid overlap
plt.savefig(os.path.join(output_dir, 'Top 3 ROIs correlated with MMS.png'))
if not silent_run:
    plt.show()
