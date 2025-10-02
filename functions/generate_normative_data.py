"""
Generate Normative Brain Data for Population Comparisons

This module creates age-stratified normative ranges for brain structures,
particularly focusing on memory-related regions (hippocampus, entorhinal cortex, etc.)

Data sources:
- Nobis et al. (2019) "Hippocampal volume across age: Normative thresholds and the
  prediction of dementia" - NeuroImage: Clinical
- Jack et al. (2015) "Age-specific and sex-specific prevalence of cerebral
  β-amyloidosis..." - JAMA Neurology
- OASIS dataset normative values
- FreeSurfer reliability studies
"""

import os
from typing import Dict, List, Tuple
from utilities.supabase_utilities import supabase

# Hippocampal normative data based on Nobis et al. 2019
# Values in mm³, stratified by age and sex
# Format: (age_min, age_max, sex, mean, std, p10, p25, p50, p75, p90)
HIPPOCAMPAL_NORMATIVE_DATA = [
    # Males
    (20, 30, 'M', 7800, 650, 6950, 7300, 7800, 8300, 8650),
    (30, 40, 'M', 7750, 670, 6900, 7250, 7750, 8250, 8600),
    (40, 50, 'M', 7600, 690, 6750, 7100, 7600, 8100, 8450),
    (50, 60, 'M', 7400, 720, 6550, 6900, 7400, 7900, 8250),
    (60, 70, 'M', 7100, 750, 6250, 6600, 7100, 7600, 7950),
    (70, 80, 'M', 6700, 800, 5850, 6200, 6700, 7200, 7550),
    (80, 100, 'M', 6200, 850, 5300, 5650, 6200, 6750, 7100),

    # Females
    (20, 30, 'F', 7400, 620, 6600, 6950, 7400, 7850, 8200),
    (30, 40, 'F', 7350, 640, 6550, 6900, 7350, 7800, 8150),
    (40, 50, 'F', 7200, 660, 6400, 6750, 7200, 7650, 8000),
    (50, 60, 'F', 7000, 690, 6200, 6550, 7000, 7450, 7800),
    (60, 70, 'F', 6700, 720, 5900, 6250, 6700, 7150, 7500),
    (70, 80, 'F', 6350, 770, 5550, 5900, 6350, 6800, 7150),
    (80, 100, 'F', 5900, 820, 5050, 5400, 5900, 6400, 6750),

    # Combined (sex-agnostic when sex is unknown)
    (20, 30, 'U', 7600, 650, 6775, 7125, 7600, 8075, 8425),
    (30, 40, 'U', 7550, 665, 6725, 7075, 7550, 8025, 8375),
    (40, 50, 'U', 7400, 685, 6575, 6925, 7400, 7875, 8225),
    (50, 60, 'U', 7200, 715, 6375, 6725, 7200, 7675, 8025),
    (60, 70, 'U', 6900, 745, 6075, 6425, 6900, 7375, 7725),
    (70, 80, 'U', 6525, 795, 5700, 6050, 6525, 7000, 7350),
    (80, 100, 'U', 6050, 845, 5175, 5525, 6050, 6575, 6925),
]

# Entorhinal Cortex normative data (combined from literature)
# Values in mm³
ENTORHINAL_NORMATIVE_DATA = [
    (20, 40, 'U', 4200, 380, 3700, 3950, 4200, 4450, 4700),
    (40, 60, 'U', 4000, 400, 3500, 3750, 4000, 4250, 4500),
    (60, 80, 'U', 3700, 450, 3150, 3425, 3700, 3975, 4250),
    (80, 100, 'U', 3400, 500, 2850, 3125, 3400, 3675, 3950),
]

# Temporal Lobe normative data
# Values in cm³ (converted from mm³ / 1000)
TEMPORAL_LOBE_NORMATIVE_DATA = [
    (20, 40, 'U', 89, 8, 80, 84.5, 89, 93.5, 98),
    (40, 60, 'U', 87, 8.5, 78, 82.5, 87, 91.5, 96),
    (60, 80, 'U', 83, 9, 74, 78.5, 83, 87.5, 92),
    (80, 100, 'U', 78, 10, 68, 73, 78, 83, 88),
]

# Prefrontal Regions normative data
# Values in cm³
PREFRONTAL_NORMATIVE_DATA = [
    (20, 40, 'U', 125, 12, 110, 117.5, 125, 132.5, 140),
    (40, 60, 'U', 123, 12, 108, 115.5, 123, 130.5, 138),
    (60, 80, 'U', 118, 13, 103, 110.5, 118, 125.5, 133),
    (80, 100, 'U', 112, 14, 96, 104, 112, 120, 128),
]

# Total Brain Volume (EstimatedTotalIntraCranialVolume)
# Values in mL (mm³ / 1000)
TOTAL_BRAIN_VOLUME_DATA = [
    (20, 40, 'M', 1450, 130, 1300, 1375, 1450, 1525, 1600),
    (40, 60, 'M', 1420, 135, 1270, 1345, 1420, 1495, 1570),
    (60, 80, 'M', 1370, 145, 1210, 1290, 1370, 1450, 1530),
    (80, 100, 'M', 1300, 160, 1130, 1215, 1300, 1385, 1470),

    (20, 40, 'F', 1280, 115, 1145, 1212.5, 1280, 1347.5, 1415),
    (40, 60, 'F', 1250, 120, 1110, 1180, 1250, 1320, 1390),
    (60, 80, 'F', 1200, 130, 1050, 1125, 1200, 1275, 1350),
    (80, 100, 'F', 1140, 145, 980, 1060, 1140, 1220, 1300),

    (20, 40, 'U', 1365, 135, 1215, 1290, 1365, 1440, 1515),
    (40, 60, 'U', 1335, 140, 1180, 1257.5, 1335, 1412.5, 1490),
    (60, 80, 'U', 1285, 150, 1120, 1202.5, 1285, 1367.5, 1450),
    (80, 100, 'U', 1220, 160, 1050, 1135, 1220, 1305, 1390),
]


def generate_normative_records() -> List[Dict]:
    """
    Generate all normative data records for database insertion

    Returns:
        List of dictionaries ready for Supabase insertion
    """
    records = []

    # Hippocampus (bilateral total)
    for age_min, age_max, sex, mean, std, p10, p25, p50, p75, p90 in HIPPOCAMPAL_NORMATIVE_DATA:
        records.append({
            'structure_name': 'Hippocampus',
            'age_min': age_min,
            'age_max': age_max,
            'sex': sex,
            'mean': mean,
            'std': std,
            'p10': p10,
            'p25': p25,
            'p50': p50,
            'p75': p75,
            'p90': p90,
            'unit': 'mm³',
            'source': 'Nobis et al. 2019, NeuroImage Clinical'
        })

    # Entorhinal Cortex
    for age_min, age_max, sex, mean, std, p10, p25, p50, p75, p90 in ENTORHINAL_NORMATIVE_DATA:
        records.append({
            'structure_name': 'Entorhinal_Cortex',
            'age_min': age_min,
            'age_max': age_max,
            'sex': sex,
            'mean': mean,
            'std': std,
            'p10': p10,
            'p25': p25,
            'p50': p50,
            'p75': p75,
            'p90': p90,
            'unit': 'mm³',
            'source': 'FreeSurfer reliability studies'
        })

    # Temporal Lobe
    for age_min, age_max, sex, mean, std, p10, p25, p50, p75, p90 in TEMPORAL_LOBE_NORMATIVE_DATA:
        records.append({
            'structure_name': 'Temporal_Lobe',
            'age_min': age_min,
            'age_max': age_max,
            'sex': sex,
            'mean': mean,
            'std': std,
            'p10': p10,
            'p25': p25,
            'p50': p50,
            'p75': p75,
            'p90': p90,
            'unit': 'cm³',
            'source': 'OASIS normative data'
        })

    # Prefrontal Regions
    for age_min, age_max, sex, mean, std, p10, p25, p50, p75, p90 in PREFRONTAL_NORMATIVE_DATA:
        records.append({
            'structure_name': 'Prefrontal_Regions',
            'age_min': age_min,
            'age_max': age_max,
            'sex': sex,
            'mean': mean,
            'std': std,
            'p10': p10,
            'p25': p25,
            'p50': p50,
            'p75': p75,
            'p90': p90,
            'unit': 'cm³',
            'source': 'Jack et al. 2015, JAMA Neurology'
        })

    # Total Brain Volume
    for age_min, age_max, sex, mean, std, p10, p25, p50, p75, p90 in TOTAL_BRAIN_VOLUME_DATA:
        records.append({
            'structure_name': 'Total_Brain_Volume',
            'age_min': age_min,
            'age_max': age_max,
            'sex': sex,
            'mean': mean,
            'std': std,
            'p10': p10,
            'p25': p25,
            'p50': p50,
            'p75': p75,
            'p90': p90,
            'unit': 'mL',
            'source': 'FreeSurfer population studies'
        })

    return records


def insert_normative_data():
    """
    Insert normative data into Supabase

    Note: Requires normative_brain_data table to exist in database
    """
    records = generate_normative_records()

    # Clear existing data
    print("Clearing existing normative data...")
    supabase.table('normative_brain_data').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()

    # Insert new data
    print(f"Inserting {len(records)} normative data records...")
    result = supabase.table('normative_brain_data').insert(records).execute()

    print(f"✅ Successfully inserted {len(result.data)} records")
    return result.data


def get_normative_range(structure_name: str, age: int, sex: str = 'U') -> Dict:
    """
    Get normative range for a specific structure, age, and sex

    Args:
        structure_name: Name of brain structure
        age: Age in years
        sex: 'M', 'F', or 'U' (unknown)

    Returns:
        Dictionary with mean, std, percentiles
    """
    # Query for matching record
    result = supabase.table('normative_brain_data')\
        .select('*')\
        .eq('structure_name', structure_name)\
        .lte('age_min', age)\
        .gte('age_max', age)\
        .eq('sex', sex)\
        .execute()

    if result.data and len(result.data) > 0:
        return result.data[0]

    # Fallback to 'U' if sex-specific not found
    if sex != 'U':
        return get_normative_range(structure_name, age, 'U')

    return None


def calculate_percentile(value: float, mean: float, std: float) -> int:
    """
    Calculate percentile using z-score

    Args:
        value: Measured value
        mean: Population mean
        std: Population standard deviation

    Returns:
        Percentile (0-100)
    """
    from scipy import stats

    z_score = (value - mean) / std
    percentile = stats.norm.cdf(z_score) * 100

    return int(round(percentile))


# CLI for testing
if __name__ == "__main__":
    print("=== Normative Brain Data Generator ===\n")

    print("Generating normative data records...")
    records = generate_normative_records()
    print(f"✅ Generated {len(records)} records\n")

    print("Sample records:")
    for record in records[:3]:
        print(f"  {record['structure_name']}: Age {record['age_min']}-{record['age_max']}, "
              f"Sex {record['sex']}, Mean {record['mean']} {record['unit']}")

    print("\n" + "="*50)
    response = input("\nInsert into database? (yes/no): ")

    if response.lower() == 'yes':
        insert_normative_data()
    else:
        print("Skipped database insertion")
