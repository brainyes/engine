# OASIS-Assignment
This repository provides an efficient workflow for analyzing neuroimaging data, combining neuropsychological assessments with volume calculations, and visualizing correlations between features through comprehensive scatter plots and heatmaps.

Overview
This project aims to streamline the process of analyzing neuroimaging data by efficiently loading, preprocessing, and visualizing critical information. The structure and functionality are designed to facilitate the extraction of insights from both atlas and neuroimaging data, making it valuable for research in neuroscience and related fields.

Key Features
Data Loading and Preprocessing: Efficiently loads atlas and neuroimaging data, resampling the atlas to match NIfTI images and calculating ROI volumes. The extraction of patient IDs is implemented accurately, ensuring data integrity.

Combining Neuropsychological and ROI Data: Merges neuropsychological data with calculated ROI volumes after aligning participant IDs, while removing missing values to ensure a smooth integration of datasets.

Correlation and Visualization: Generates scatter plots and heatmaps to visualize correlations between neuropsychological features and the highest-variance ROIs. Standard deviation calculations and the selection of the top three variables allow for a focused analysis of significant relationships.

Output Generation: Exports the combined data to a CSV file (combined_patient_data.csv).

This project serves as a robust framework for understanding the relationship between neuroimaging and neuropsychological data, offering valuable tools for researchers and practitioners alike.
