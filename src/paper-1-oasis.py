import os

import matplotlib.pyplot as plt
import nibabel as nib
import pandas as pd
import seaborn as sns

from calculate_roi_volumes import calculate_roi_volumes
from options import silent_run, dataset_dir, output_dir
from resample_atlas_for_user import resample_atlas_for_user

file_path = os.path.join(dataset_dir, 'sub-OASIS10001_ses-M00_T1w.nii.gz')

user_nifti = nib.load(file_path)
user_atlas, voxel_size = resample_atlas_for_user(user_nifti)

# Calculate ROI volumes
roi_volumes = calculate_roi_volumes(user_nifti, user_atlas.get_fdata(), voxel_size)

########## PAPER STARTS ##########
patient_id = 'sub-OASIS10001'

tsv_file_path = os.path.join(dataset_dir, 'tsv_files', 'lab_1', 'OASIS_BIDS.tsv')

# Dictionary to store patient data
patient_data = {}
patient_data[patient_id] = roi_volumes

# Load neuropsychological data
neuro_data = pd.read_csv(tsv_file_path, sep='\t')

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
