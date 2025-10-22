import os

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from functions.calculate_roi_volumes import calculate_roi_volumes
from utilities.options import silent_run, dataset_dir, output_dir, oasis_bids_tsv_path
from functions.resample_atlas_for_user_nifti import resample_atlas_for_user_nifti
from utilities.supabase_utilities import get_roi_volumes_for_niftis, get_nifti_file, get_user_insight, save_insight_output_file, save_insight_output_pandas
from functions.upload_nifti import upload_nifti
from utilities.utilities import plot_to_image

# todo required data flow. getOrGenerate() / dependencies on other workflows
# todo bulk initial process / migration / reprocess
# todo required initial data specific to this paper, e.g. OASIS_BIDS,tsv
    # todo OASIS is a given dataset, plus we need user's survey here no?
# todo output / generic output for insights?

PARAMETERS = {
    "nifti_id": "27c1ae7e-184e-4fd5-989b-b193003d3de2", # example
    "user_id": "d480e950-fb57-4ad8-9797-17e5aa8fc1cf", # example
}
INSIGHT_NAME = "paper-1-oasis"
UPLOAD_SAMPLE = False

def main():
    if UPLOAD_SAMPLE is True:
        # upload an example MRI nifti file
        workdir_file_path = os.path.join(dataset_dir, 'raw', 'sub-OASIS10001_ses-M00_T1w.nii.gz')
        print(workdir_file_path)
        nifti_file, _ = upload_nifti(workdir_file_path, None, "anonymous-3")
        print(nifti_file)
        atlas_sampled_nifti_file, user_meta = resample_atlas_for_user_nifti(nifti_file['id'])
        print(atlas_sampled_nifti_file)
        print(str(user_meta))
        roi_volumes = calculate_roi_volumes(nifti_file['id'])
        print(roi_volumes)
        exit(0)
    else:

    ########## PAPER STARTS ##########
        print("PARAMETERS: ", PARAMETERS)
        nifti_file, _, _ = get_nifti_file(PARAMETERS["nifti_id"])
        print(nifti_file)
        volumes_for_niftis = get_roi_volumes_for_niftis()

    user_insight = get_user_insight(INSIGHT_NAME, nifti_file['user_id'], nifti_file['id'])
    patient_data = volumes_for_niftis

    # Load neuropsychological data
    neuro_data = pd.read_csv(oasis_bids_tsv_path, sep='\t')

    # todo @DEMO - Replace the participant IDs from survey data with the incoming nifti IDs as patient IDs
    new_ids = list(patient_data.keys())
    for i, new_id in enumerate(new_ids):
        neuro_data['participant_id'] = neuro_data['participant_id'].replace(f'sub-OASIS1000{i+1}', new_id)

    # Convert patient_data dictionary to a DataFrame
    roi_volumes_df = pd.DataFrame.from_dict(patient_data, orient='index').fillna(0)
    roi_volumes_df['total_volume'] = roi_volumes_df.sum(axis=1)
    roi_volumes_df.index = roi_volumes_df.index.str.replace('sub-', '')

    # Match participant_id in the neuropsychological data with the NIfTI participant_id format
    neuro_data['participant_id'] = neuro_data['participant_id'].str.replace('sub-', '')

    # Merge neuropsychological data with the calculated ROI volumes based on the participant_id
    combined_data = neuro_data.merge(
        roi_volumes_df, left_on='participant_id', right_index=True, how='inner')

    roi_volume_columns = roi_volumes_df.columns.tolist()
    roi_volumes_to_store = combined_data[["participant_id"] + roi_volume_columns]

    # Define the list of attributes for correlation
    correlated_attributes = ['sex', 'education_level', 'age_bl', 'cdr',
             'diagnosis_bl', 'MMS', 'cdr_global', 'diagnosis']

    # Ensure that the combined data contains all attributes in correlated_attributes
    for attribute in correlated_attributes:
        if attribute not in combined_data.columns:
            print(f"Warning: {attribute} not found in combined_data.")

    # Select the relevant columns from the combined data, excluding participant_id
    correlation_data = combined_data[roi_volume_columns + correlated_attributes]

    # Convert any non-numeric data to numeric (e.g., encoding categorical variables if necessary)
    correlation_data_encoded = pd.get_dummies(correlation_data, drop_first=True)

    # Calculate the correlation matrix
    correlation_matrix = correlation_data_encoded.corr()

    # Select only the relevant correlation values for the ROI volumes
    correlation_matrix_roi = correlation_matrix.loc[roi_volume_columns,
    correlation_data_encoded.columns.difference(roi_volume_columns)]

    # Print the shape of the correlation matrix
    # todo output
    print(f"Correlation matrix shape: {correlation_matrix_roi.shape}")
    save_insight_output_pandas(user_insight['id'], 'correlation_matrix_roi', correlation_matrix_roi)

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
    # todo output
    plt.savefig(os.path.join(output_dir, 'correlation_matrix.png'))
    save_insight_output_file(user_insight['id'], 'correlation_matrix.png', plot_to_image())
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
    # todo output
    plt.savefig(os.path.join(output_dir, 'Correlation_Between_Total_Volume_and_MMS_Scores.png'))
    save_insight_output_file(user_insight['id'], 'Correlation_Between_Total_Volume_and_MMS_Scores.png', plot_to_image())
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
    # todo output
    plt.savefig(os.path.join(output_dir, 'Distribution of MMS Scores by Total Volume.png'))
    save_insight_output_file(user_insight['id'], 'distribution_of_mms_scores_by_total_volume.png', plot_to_image())
    if not silent_run:
        plt.show()

    # Calculate the correlation of each ROI with the MMS score
    # todo output
    correlation_with_mms = correlation_matrix_roi['MMS'].abs().sort_values(ascending=False)
    save_insight_output_pandas(user_insight['id'], 'correlation_with_mms', correlation_with_mms)

    # Get all correlated ROIs (excluding MMS itself)
    correlated_rois = correlation_with_mms.index[1:]

    # Print correlations
    print("ROIs correlated with MMS:")
    for roi in correlated_rois:
        correlation_value = correlation_with_mms[roi]
        print(f"{roi}: {correlation_value:.2f}")

    # Set up the figure size for the plots
    plt.figure(figsize=(15, 5))

    # Loop through ROIs to create scatter plots
    for i, roi in enumerate(correlated_rois):
        plt.subplot(1, len(correlated_rois), i + 1)  # Create a subplot for each ROI
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
    # todo output
    plt.savefig(os.path.join(output_dir, 'ROIs correlated with MMS.png'))
    save_insight_output_file(user_insight['id'], 'rois_correlated_with_mms.png', plot_to_image())
    if not silent_run:
        plt.show()

# example:
if __name__=="__main__":
    main()
