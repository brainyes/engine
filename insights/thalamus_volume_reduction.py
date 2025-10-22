import pandas as pd

from utilities.supabase_utilities import get_nifti_file, get_roi_volumes_for_niftis, get_user_insight, get_roi_volumes, \
    save_insight_output, save_insight_type

# Fulvia Adriano, Ilaria Spoletini, Carlo Caltagirone, Gianfranco Spalletta,
# Updated meta-analyses reveal thalamus volume reduction in patients with first-episode and chronic schizophrenia,
# Schizophrenia Research,
# Volume 123, Issue 1,
# 2010,
# Pages 1-14,
# ISSN 0920-9964,
# https://doi.org/10.1016/j.schres.2010.07.007.
# (https://www.sciencedirect.com/science/article/pii/S0920996410014222)
# Abstract: Objectives
# Although several structural MRI studies report significant thalamus volume reduction in patients with schizophrenia, many other studies do not. Therefore, the present meta-analyses aimed to clarify whether a reduction in thalamic volume characterizes patients diagnosed with schizophrenia by considering first-episode and chronic phases of the illness and right and left thalamus separately.
# Methods
# Using Pubmed databases, we made a detailed literature search for structural MRI studies on patients with schizophrenia that reported physical volumetric measures of the right and left thalamus. Thirteen structural MRI studies were considered eligible for meta-analysis of the entire sample of patients and of the healthy control subjects. Individual meta-analyses were also performed on 6 studies of first-episode patients only and on 7 studies of chronic patients only. These were followed by additional meta-analyses to investigate the role of the factors “illness phase” and “side” on thalamic volume reduction.
# Results
# Overall, the patient group showed a significant bilateral thalamus volume reduction compared to healthy control subjects. This was found in both first-episode and chronic patients. Furthermore, left thalamus was smaller than right in both patients and healthy control subjects.
# Conclusions
# When only studies that used physical volumetric measures were considered, the present meta-analyses confirmed that thalamic volume reduction characterizes patients with schizophrenia, both at the first-episode and chronic phases of the illness.
# Keywords: Thalamus; Schizophrenia; Structural MRI; Physical measures; Meta-analysis
PARAMETERS = {
    "nifti_id": "27c1ae7e-184e-4fd5-989b-b193003d3de2",  # example
    "user_id": "d480e950-fb57-4ad8-9797-17e5aa8fc1cf",  # example
}
INSIGHT_NAME = "thalamus-volume-reduction-schi"
save_insight_type(INSIGHT_NAME)

# Table: Global meta-analysis of the right thalamus
global_right_thalamus = {
    "Study or Subgroup": [
        "Bagary, 2002", "Bridle, 2002", "Crespo-Facorro, 2007", "Dasari, 1999",
        "Deicken, 2001", "Ettinger, 2001", "Ettinger, 2007", "Frazier, 2008",
        "Gilbert, 2001", "Lang, 2006", "Preuss, 2005a", "Preuss, 2005b", "Sanderson, 1999",
        "Spoletini, 2009a", "Spoletini, 2009b"
    ],
    "SZ Mean (SD)": [
        "8.84 (0.84)", "7.46 (1.19)", "6.3 (0.77)", "4.13 (0.5)", "7.61 (0.73)",
        "7.11 (0.84)", "7.09 (0.93)", "7.81 (0.77)", "3.41 (1.21)", "4.215 (0.443)",
        "7.34 (1.04)", "7.47 (0.89)", "6.2 (1.1)", "5.944 (0.601)", "6.123 (0.746)"
    ],
    "HC Mean (SD)": [
        "9.6 (1.05)", "8.676 (1.537)", "6.66 (0.73)", "4.49 (0.32)", "7.93 (0.65)",
        "7.49 (0.68)", "7.53 (0.66)", "8.05 (0.69)", "4.09 (0.74)", "4.512 (0.356)",
        "7.55 (1.04)", "7.55 (1.04)", "6.1 (0.6)", "6.308 (0.666)", "6.308 (0.666)"
    ],
    "Std. Mean Difference (95% CI)": [
        "-0.79 [-1.36, -0.21]", "-0.15 [-1.08, 0.79]", "-0.34 [-0.74, 0.06]", "-0.82 [-1.51, -0.13]",
        "-0.46 [-0.90, -0.01]", "-0.48 [-0.98, 0.01]", "-0.52 [-0.90, -0.13]", "-0.33 [-0.90, 0.25]",
        "-0.71 [-1.36, -0.07]", "-0.72 [-1.29, -0.14]", "-0.20 [-0.68, 0.28]", "-0.08 [-0.49, 0.33]",
        "0.11 [-0.42, 0.65]", "-0.54 [-1.57, 0.49]", "-0.26 [-0.68, 0.17]"
    ],
    "Weight (%)": [
        5.2, 2.0, 10.8, 3.7, 8.9, 7.3, 11.8, 5.3, 4.2, 5.3, 7.6, 10.5, 6.1, 1.7, 9.7
    ]
}
# Table: Global meta-analysis of the left thalamus
global_left_thalamus = {
    "Study or Subgroup": [
        "Bagary, 2002", "Bridle, 2002", "Crespo-Facorro, 2007", "Dasari, 1999",
        "Deicken, 2001", "Ettinger, 2001", "Ettinger, 2007", "Frazier, 2008",
        "Gilbert, 2001", "Lang, 2006", "Preuss, 2005a", "Preuss, 2005b", "Sanderson, 1999",
        "Spoletini, 2009a", "Spoletini, 2009b"
    ],
    "SZ Mean (SD)": [
        "9.21 (1.18)", "7.59 (1.27)", "6.18 (0.69)", "4.13 (0.45)", "7.36 (0.81)",
        "7.15 (0.91)", "4.855 (0.98)", "7.79 (0.82)", "3.21 (0.98)", "4.078 (0.411)",
        "6.65 (1.25)", "6.88 (0.87)", "6.3 (1.1)", "5.449 (0.706)", "5.72 (0.71)"
    ],
    "HC Mean (SD)": [
        "9.72 (1.2)", "8.609 (1.521)", "6.42 (0.59)", "4.45 (0.32)", "7.56 (0.76)",
        "7.6 (0.76)", "5.33 (0.57)", "7.93 (0.73)", "4.03 (0.78)", "4.253 (0.325)",
        "7 (0.89)", "7.89 (0.5)", "6.5 (0.6)", "5.979 (0.706)", "5.979 (0.706)"
    ],
    "Std. Mean Difference (95% CI)": [
        "-0.42 [-0.98, 0.14]", "-0.01 [-0.94, 0.92]", "-0.37 [-0.77, 0.04]", "-0.79 [-1.47, -0.10]",
        "-0.25 [-0.69, 0.19]", "-0.52 [-1.02, -0.03]", "-0.59 [-0.98, -0.20]", "-0.21 [-0.78, 0.36]",
        "-0.93 [-1.59, -0.27]", "-0.46 [-1.02, 0.10]", "-0.34 [-0.82, 0.14]", "-0.14 [-0.54, 0.27]",
        "-0.24 [-0.78, 0.29]", "-0.74 [-1.77, 0.30]", "-0.36 [-0.79, 0.06]"
    ],
    "Weight (%)": [
        5.5, 2.0, 10.8, 3.7, 9.0, 7.2, 11.6, 5.3, 4.0, 5.5, 7.5, 10.5, 6.1, 1.6, 9.6
    ]
}
# Table: First-episode meta-analysis of the right thalamus
first_episode_right = {
    "Study or Subgroup": [
        "Bagary, 2002", "Bridle, 2002", "Crespo-Facorro, 2007", "Dasari, 1999",
        "Deicken, 2001", "Ettinger, 2001", "Ettinger, 2007", "Frazier, 2008",
        "Gilbert, 2001", "Lang, 2006", "Preuss, 2005a", "Preuss, 2005b", "Sanderson, 1999",
        "Spoletini, 2009a", "Spoletini, 2009b"
    ],
    "SZ Mean (SD)": [
        "8.84 (0.84)", "7.46 (1.19)", "6.3 (0.77)", "4.13 (0.5)", "7.61 (0.73)",
        "7.11 (0.84)", "7.09 (0.93)", "7.81 (0.77)", "3.41 (1.21)", "4.215 (0.443)",
        "7.34 (1.04)", "7.47 (0.89)", "6.2 (1.1)", "5.944 (0.601)", "6.123 (0.746)"
    ],
    "HC Mean (SD)": [
        "9.6 (1.05)", "8.676 (1.537)", "6.66 (0.73)", "4.49 (0.32)", "7.93 (0.65)",
        "7.49 (0.68)", "7.53 (0.66)", "8.05 (0.69)", "4.09 (0.74)", "4.512 (0.356)",
        "7.55 (1.04)", "7.55 (1.04)", "6.1 (0.6)", "6.308 (0.666)", "6.308 (0.666)"
    ],
    "Std. Mean Difference (95% CI)": [
        "-0.79 [-1.36, -0.21]", "-0.15 [-1.08, 0.79]", "-0.34 [-0.74, 0.06]", "-0.82 [-1.51, -0.13]",
        "-0.46 [-0.90, -0.01]", "-0.48 [-0.98, 0.01]", "-0.52 [-0.90, -0.13]", "-0.33 [-0.90, 0.25]",
        "-0.71 [-1.36, -0.07]", "-0.72 [-1.29, -0.14]", "-0.20 [-0.68, 0.28]", "-0.08 [-0.49, 0.33]",
        "0.11 [-0.42, 0.65]", "-0.54 [-1.57, 0.49]", "-0.26 [-0.68, 0.17]"
    ],
    "Weight (%)": [
        5.2, 2.0, 10.8, 3.7, 8.9, 7.3, 11.8, 5.3, 4.2, 5.3, 7.6, 10.5, 6.1, 1.7, 9.7
    ]
}
# Table: First-episode meta-analysis of the left thalamus
first_episode_left = {
    "Study or Subgroup": [
        "Bagary, 2002", "Bridle, 2002", "Crespo-Facorro, 2007", "Dasari, 1999",
        "Deicken, 2001", "Ettinger, 2001", "Ettinger, 2007", "Frazier, 2008",
        "Gilbert, 2001", "Lang, 2006", "Preuss, 2005a", "Preuss, 2005b", "Sanderson, 1999",
        "Spoletini, 2009a", "Spoletini, 2009b"
    ],
    "SZ Mean (SD)": [
        "9.21 (1.18)", "7.59 (1.27)", "6.18 (0.69)", "4.13 (0.45)", "7.36 (0.81)",
        "7.15 (0.91)", "4.855 (0.98)", "7.79 (0.82)", "3.21 (0.98)", "4.078 (0.411)",
        "6.65 (1.25)", "6.88 (0.87)", "6.3 (1.1)", "5.449 (0.706)", "5.72 (0.71)"
    ],
    "HC Mean (SD)": [
        "9.72 (1.2)", "8.609 (1.521)", "6.42 (0.59)", "4.45 (0.32)", "7.56 (0.76)",
        "7.6 (0.76)", "5.33 (0.57)", "7.93 (0.73)", "4.03 (0.78)", "4.253 (0.325)",
        "7 (0.89)", "7.89 (0.5)", "6.5 (0.6)", "5.979 (0.706)", "5.979 (0.706)"
    ],
    "Std. Mean Difference (95% CI)": [
        "-0.42 [-0.98, 0.14]", "-0.01 [-0.94, 0.92]", "-0.37 [-0.77, 0.04]", "-0.79 [-1.47, -0.10]",
        "-0.25 [-0.69, 0.19]", "-0.52 [-1.02, -0.03]", "-0.59 [-0.98, -0.20]", "-0.21 [-0.78, 0.36]",
        "-0.93 [-1.59, -0.27]", "-0.46 [-1.02, 0.10]", "-0.34 [-0.82, 0.14]", "-0.14 [-0.54, 0.27]",
        "-0.24 [-0.78, 0.29]", "-0.74 [-1.77, 0.30]", "-0.36 [-0.79, 0.06]"
    ],
    "Weight (%)": [
        5.5, 2.0, 10.8, 3.7, 9.0, 7.2, 11.6, 5.3, 4.0, 5.5, 7.5, 10.5, 6.1, 1.6, 9.6
    ]
}

df_global_right = pd.DataFrame(global_right_thalamus)
df_global_left = pd.DataFrame(global_left_thalamus)
df_first_episode_right = pd.DataFrame(first_episode_right)
df_first_episode_left = pd.DataFrame(first_episode_left)

def main(**parameters):
    ########## PAPER STARTS ##########
    if not parameters:
        parameters = PARAMETERS

    nifti_file, _, _ = get_nifti_file(parameters["nifti_id"])
    user_insight = get_user_insight(INSIGHT_NAME, nifti_file['user_id'], nifti_file['id'])
    volumes_for_nifti = get_roi_volumes(nifti_file['id'])

    left_volume_mm3 = volumes_for_nifti["Left-Thalamus"].values[0]
    right_volume_mm3 = volumes_for_nifti["Right-Thalamus"].values[0]

    # Convert to cm³
    left_volume_cm3 = left_volume_mm3 / 1000
    right_volume_cm3 = right_volume_mm3 / 1000

    # Extract population statistics for left and right thalamus
    left_mean = df_global_left["SZ Mean (SD)"].str.extract(r"(\d+\.\d+)").astype(float).mean().values[0]
    left_std = df_global_left["SZ Mean (SD)"].str.extract(r"\((\d+\.\d+)\)").astype(float).mean().values[0]

    right_mean = df_global_right["SZ Mean (SD)"].str.extract(r"(\d+\.\d+)").astype(float).mean().values[0]
    right_std = df_global_right["SZ Mean (SD)"].str.extract(r"\((\d+\.\d+)\)").astype(float).mean().values[0]

    # Calculate Z-scores
    left_z = (left_volume_cm3 - left_mean) / left_std
    right_z = (right_volume_cm3 - right_mean) / right_std

    # Generate insights
    insight = f"For Nifti - {nifti_file['id']} Insights:\n"
    insight += f"Left Thalamus Volume: {left_volume_cm3:.2f} cm³ (Z-score: {left_z:.2f})\n"
    insight += f"Right Thalamus Volume: {right_volume_cm3:.2f} cm³ (Z-score: {right_z:.2f})\n"

    if abs(left_z) > 1:
        insight += "The left thalamus volume is significantly different from the population norm.\nThis could indicate a susceptibility to schizophrenia according to Adriano 2010"
    if abs(right_z) > 1:
        insight += "The right thalamus volume is significantly different from the population norm.\nThis could indicate a susceptibility to schizophrenia according to Adriano 2010"
    if abs(left_z) < 1:
        insight += "The left thalamus volume is within the population norm.\n"
    if abs(right_z) < 1:
        insight += "The right thalamus volume is within the population norm.\n"

    print(insight)

    save_insight_output(user_insight['id'], 'correlation_matrix.png', plot_to_image())

    ########## PAPER ENDS ##########
    return insight

# example:
if __name__ == "__main__":
    main()
