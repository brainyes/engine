"""
Population Norms Utilities

Helper functions for working with population normative data, including
status indicators, interpretation text, and dashboard formatting.
"""

# Global measure ROI label mappings (for storing in population_comparisons table)
GLOBAL_MEASURE_ROI_LABELS = {
    "BrainSeg": 999,  # Total Brain Volume
    "Cortex": 998,    # Total Cortex Volume
    "CerebralWhiteMatter": 997,  # Total White Matter
    "EstimatedTotalIntraCranialVol": 996,  # eTIV
}

# Reverse mapping
ROI_LABEL_TO_GLOBAL_MEASURE = {v: k for k, v in GLOBAL_MEASURE_ROI_LABELS.items()}

# Display names for global measures
GLOBAL_MEASURE_DISPLAY_NAMES = {
    "BrainSeg": "Total Brain Volume",
    "Cortex": "Total Cortical Volume",
    "CerebralWhiteMatter": "Total White Matter Volume",
    "EstimatedTotalIntraCranialVol": "Estimated Total Intracranial Volume",
}
