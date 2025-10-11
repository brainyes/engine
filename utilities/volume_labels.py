import numpy as np

# Dictionary of Harvard-Oxford cortical regions
ho_cortical = {
    1: "Frontal Pole",
    2: "Insular Cortex",
    3: "Superior Frontal Gyrus",
    4: "Middle Frontal Gyrus",
    5: "Inferior Frontal Gyrus, pars triangularis",
    6: "Inferior Frontal Gyrus, pars opercularis",
    7: "Precentral Gyrus",
    8: "Temporal Pole",
    9: "Superior Temporal Gyrus, anterior division",
    10: "Superior Temporal Gyrus, posterior division",
    11: "Middle Temporal Gyrus, anterior division",
    12: "Middle Temporal Gyrus, posterior division",
    13: "Middle Temporal Gyrus, temporooccipital part",
    14: "Inferior Temporal Gyrus, anterior division",
    15: "Inferior Temporal Gyrus, posterior division",
    16: "Inferior Temporal Gyrus, temporooccipital part",
    17: "Postcentral Gyrus",
    18: "Superior Parietal Lobule",
    19: "Supramarginal Gyrus, anterior division",
    20: "Supramarginal Gyrus, posterior division",
    21: "Angular Gyrus",
    22: "Lateral Occipital Cortex, superior division",
    23: "Lateral Occipital Cortex, inferior division",
    24: "Intracalcarine Cortex",
    25: "Frontal Medial Cortex",
    26: "Juxtapositional Lobule Cortex",
    27: "Subcallosal Cortex",
    28: "Paracingulate Gyrus",
    29: "Cingulate Gyrus, anterior division",
    30: "Cingulate Gyrus, posterior division",
    31: "Precuneous Cortex",
    32: "Cuneal Cortex",
    33: "Frontal Orbital Cortex",
    34: "Parahippocampal Gyrus, anterior division",
    35: "Parahippocampal Gyrus, posterior division",
    36: "Lingual Gyrus",
    37: "Temporal Fusiform Cortex, anterior division",
    38: "Temporal Fusiform Cortex, posterior division",
    39: "Temporal Occipital Fusiform Cortex",
    40: "Occipital Fusiform Gyrus",
    41: "Frontal Operculum Cortex",
    42: "Central Opercular Cortex",
    43: "Parietal Operculum Cortex",
    44: "Planum Polare",
    45: "Heschl's Gyrus",
    46: "Planum Temporale",
    47: "Supracalcarine Cortex",
    48: "Occipital Pole"
}

# Dictionary of Harvard-Oxford subcortical regions
ho_subcortical = {
    1: "Left Cerebral White Matter",
    2: "Left Cerebral Cortex",
    3: "Left Lateral Ventricle",
    4: "Left Thalamus",
    5: "Left Caudate",
    6: "Left Putamen",
    7: "Left Pallidum",
    8: "Brain-Stem",
    9: "Left Hippocampus",
    10: "Left Amygdala",
    11: "Left Accumbens",
    12: "Right Cerebral White Matter",
    13: "Right Cerebral Cortex",
    14: "Right Lateral Ventricle",
    15: "Right Thalamus",
    16: "Right Caudate",
    17: "Right Putamen",
    18: "Right Pallidum",
    19: "Right Hippocampus",
    20: "Right Amygdala",
    21: "Right Accumbens"
}

# Combine cortical and subcortical dictionaries into one
volume_labels_dict = {**ho_cortical, **ho_subcortical}

# Helper function to get region name
def get_region_name(roi_label: int) -> str:
    """
    Get the human-readable name for a ROI label

    Args:
        roi_label: Integer label from Harvard-Oxford atlas

    Returns:
        Region name string
    """
    if roi_label in ho_cortical:
        return ho_cortical[roi_label]
    elif roi_label in ho_subcortical:
        return ho_subcortical[roi_label]
    else:
        return f"Unknown Region {roi_label}"