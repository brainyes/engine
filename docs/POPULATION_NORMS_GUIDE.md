# Population Norms System Guide

This guide explains how to use the population norms system to compare individual brain scans against normative data from large datasets (OASIS, HCP, OpenNeuro, etc.).

## 📋 Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Detailed Workflow](#detailed-workflow)
4. [Understanding Results](#understanding-results)
5. [Troubleshooting](#troubleshooting)
6. [Advanced Usage](#advanced-usage)

---

## Overview

### What are Population Norms?

Population norms are statistical baselines computed from large datasets of brain scans from healthy individuals. They include:

- **Mean** and **standard deviation** for each brain region
- **Percentiles** (10th, 25th, 50th, 75th, 90th)
- Stratified by **age groups** and **sex** for accurate comparisons

### Why Use Population Norms?

When analyzing an individual's brain scan, population norms help:

1. **Identify outliers**: Regions that are unusually large or small
2. **Contextualize measurements**: "This person's hippocampus is in the 15th percentile for their age"
3. **Track changes**: Compare follow-up scans to population baselines
4. **Research insights**: Study population trends and variations

### System Components

The system has four main components:

1. **Dataset Download** (`download_oasis_dataset.py`) - Download population datasets
2. **Batch Processing** (`batch_process_population_dataset.py`) - Process datasets through pipeline
3. **Norms Computation** (`compute_population_norms.py`) - Calculate statistical norms
4. **Individual Comparison** (`compare_to_population_norms.py`) - Compare individual scans

---

## Quick Start

### Prerequisites

1. **Database Setup**: Create required tables (see `docs/DATABASE_SCHEMA_POPULATION_NORMS.md`)
   ```sql
   -- Run the migration script from DATABASE_SCHEMA_POPULATION_NORMS.md
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Basic Workflow

```bash
# Step 1: Download dataset metadata
python -m functions.download_oasis_dataset --dataset oasis-1 --count 100

# Step 2: Batch process downloaded scans
python -m functions.batch_process_population_dataset \\
    research/input/datasets/oasis-1/raw \\
    --dataset oasis-1 \\
    --metadata research/input/datasets/oasis-1/selected_subjects.csv

# Step 3: Compute population norms
python -m functions.compute_population_norms --dataset oasis-1

# Step 4: Compare an individual scan
python -m functions.compare_to_population_norms YOUR_FILE_ID --age 45 --sex M
```

---

## Detailed Workflow

### Step 1: Download Population Dataset

**Purpose**: Get metadata and instructions for downloading population MRI scans.

```bash
python -m functions.download_oasis_dataset --dataset oasis-1 --count 200
```

**Options**:
- `--dataset`: Which dataset (`oasis-1`, `oasis-3`)
- `--count`: Max subjects to download (default: all)
- `--output`: Custom output directory

**Output**:
- Subject list with demographics (age, sex, CDR scores)
- Download instructions
- Metadata CSV for batch processing

**Note**: Most datasets require manual download after accepting data use agreements. Follow the printed instructions.

---

### Step 2: Batch Process Population Dataset

**Purpose**: Upload and process all scans through the analysis pipeline.

```bash
python -m functions.batch_process_population_dataset \\
    research/input/datasets/oasis-1/raw \\
    --dataset oasis-1 \\
    --metadata research/input/datasets/oasis-1/selected_subjects.csv \\
    --count 50
```

**What it does**:
1. Scans directory for NIFTI files
2. Uploads each scan to system
3. Resamples atlas to scan space
4. Calculates ROI volumes
5. Stores metadata (age, sex, dataset source)

**Options**:
- First argument: Directory containing NIFTI files
- `--dataset`: Dataset name (used for tracking provenance)
- `--metadata`: CSV with subject demographics (age, sex, etc.)
- `--count`: Limit number of scans (for testing)
- `--dry-run`: Preview what would be processed
- `--overwrite`: Reprocess existing scans

**Expected Processing Time**:
- ~1-2 minutes per scan
- 100 scans ≈ 2-3 hours
- Use ECS for batch processing large datasets

**Metadata CSV Format**:
```csv
ID,Age,M/F,CDR,diagnosis
OAS1_0001,45,M,0,Nondemented
OAS1_0002,52,F,0.5,Very Mild Dementia
```

---

### Step 3: Compute Population Norms

**Purpose**: Calculate statistical norms (mean, std, percentiles) from processed scans.

```bash
python -m functions.compute_population_norms --dataset oasis-1 --min-samples 30
```

**What it does**:
1. Queries all population scans from database
2. Gets ROI volumes for each scan
3. Stratifies by age bins (e.g., 20-30, 30-40, etc.) and sex
4. Computes statistics for each stratum
5. Saves to `normative_brain_data` table

**Options**:
- `--dataset`: Filter by specific dataset (default: all)
- `--min-samples`: Minimum samples needed per stratum (default: 30)
- `--age-bin-width`: Width of age bins in years (default: 10)
- `--no-combined-sex`: Skip sex-agnostic norms
- `--dry-run`: Compute but don't save

**Output**:
- Normative records in `normative_brain_data` table
- Statistics: mean, std, p10, p25, p50, p75, p90
- Stratified by: age bin, sex, ROI label

**Example**: With 100 scans and 48 ROIs:
- Age bins: 20-30, 30-40, ..., 80-90 (7 bins)
- Sex: M, F, U (3 groups)
- ROIs: 48 regions
- **Total norms**: ~7 × 3 × 48 = ~1,000 normative records

---

### Step 4: Compare Individual Scan to Norms

**Purpose**: Compare a user's scan to population norms and identify outliers.

```bash
python -m functions.compare_to_population_norms FILE_ID --age 45 --sex M
```

**What it does**:
1. Gets user's ROI volumes
2. Fetches matching population norms (age/sex-matched)
3. Calculates z-scores and percentiles for each ROI
4. Identifies outliers (|z-score| > 2)
5. Saves comparison to `population_comparisons` table

**Options**:
- First argument: NIFTI file ID to compare
- `--age`: Age in years (enables age-matched comparison)
- `--sex`: M, F, or U (unknown/combined)
- `--threshold`: Z-score threshold for outliers (default: 2.0)
- `--no-save`: Don't save to database

**Output Example**:
```
COMPARISON RESULTS
======================================================================
Total ROIs compared: 48
Outliers found: 3 (6.2%)

⚠️  Outlier ROIs (|z-score| > 2.0):
ROI Name                       Volume       Mean   Z-Score   %ile
----------------------------------------------------------------------
Left_Hippocampus                 6200       7600     -2.03      2%
Right_Temporal_Pole              3800       5200     -2.15      2%
Left_Frontal_Pole                8500       6800     +2.12     98%

Percentile Distribution:
  Very Low (<5%): 2
  Low (5-25%): 8
  Normal (25-75%): 35
  High (75-95%): 2
  Very High (>95%): 1
```

---

## Understanding Results

### Z-Scores

**Definition**: Number of standard deviations from the population mean.

**Interpretation**:
- `z = 0`: Exactly at population average
- `z = +1`: 1 SD above average (larger than ~84% of population)
- `z = -1`: 1 SD below average (smaller than ~84% of population)
- `|z| > 2`: Outside 95% of population (potential outlier)
- `|z| > 3`: Outside 99.7% of population (extreme outlier)

**Examples**:
```
ROI: Left Hippocampus
User volume: 6500 mm³
Population: mean=7600 mm³, std=690 mm³
Z-score: (6500 - 7600) / 690 = -1.59
Interpretation: 1.6 SD below average (smaller than typical)
```

### Percentiles

**Definition**: Where the individual ranks in the population (0-100%).

**Interpretation**:
- `50%`: Exactly average (median)
- `25%`: Below average (smaller than 75% of people)
- `75%`: Above average (larger than 75% of people)
- `<5%` or `>95%`: Potentially clinically significant

**Examples**:
```
Percentile 15%: This person's volume is smaller than 85% of the population
Percentile 85%: This person's volume is larger than 85% of the population
```

### Outliers

**Definition**: ROIs with z-scores beyond a threshold (typically |z| > 2).

**Clinical Relevance**:
- Single outliers can be normal variation
- Multiple outliers in related regions warrant attention
- Consider clinical context and symptoms
- Compare to follow-up scans for trend analysis

**Not Medical Advice**: These are statistical comparisons. Clinical decisions require professional medical evaluation.

---

## Troubleshooting

### Problem: No Population Scans Found

```
Error: No population scans found. Cannot compute norms.
```

**Solution**:
1. Check that scans were processed: `SELECT COUNT(*) FROM population_scans;`
2. Ensure batch processing completed successfully
3. Verify metadata was saved during batch processing

---

### Problem: No Matching Norms

```
Warning: 25 ROIs skipped (no matching norms)
```

**Causes**:
1. Age outside computed range
2. ROI not in normative data
3. Insufficient samples for that stratum

**Solutions**:
- Use sex='U' (combined) instead of M/F
- Compute norms with smaller age bins
- Lower `--min-samples` threshold
- Add more population scans to dataset

---

### Problem: ROI Volumes Not Found

```
Error: No ROI volumes found for this scan
```

**Solution**:
```bash
# Make sure scan was processed through pipeline
python -m functions.calculate_roi_volumes YOUR_FILE_ID
```

---

### Problem: Database Table Missing

```
Error: relation "population_scans" does not exist
```

**Solution**:
Run the SQL migration script from `docs/DATABASE_SCHEMA_POPULATION_NORMS.md`

---

## Advanced Usage

### Using Existing OASIS Data

If you already have OASIS scans in `research/input/raw/`:

```bash
# Process existing scans
python -m functions.batch_process_population_dataset \\
    research/input/raw \\
    --dataset oasis-local \\
    --metadata research/input/tsv_files/lab_1/OASIS_BIDS.tsv

# Compute norms
python -m functions.compute_population_norms --dataset oasis-local
```

---

### Custom Age Bins

For finer age stratification:

```bash
# 5-year age bins instead of 10-year
python -m functions.compute_population_norms --age-bin-width 5
```

**Trade-off**: Smaller bins = more precise matching, but need more samples.

---

### Combining Multiple Datasets

```bash
# Process OASIS
python -m functions.batch_process_population_dataset \\
    datasets/oasis-1/raw --dataset oasis-1 --metadata datasets/oasis-1/meta.csv

# Process HCP
python -m functions.batch_process_population_dataset \\
    datasets/hcp/raw --dataset hcp-young-adult --metadata datasets/hcp/meta.csv

# Compute combined norms
python -m functions.compute_population_norms
# (no --dataset flag = use all datasets)
```

This creates norms from combined population for better coverage.

---

### Querying Results Programmatically

```python
from utilities.data import supabase

# Get all outliers for a user
response = supabase.table('population_comparisons')\\
    .select('*')\\
    .eq('nifti_file_id', 'your-file-id')\\
    .eq('is_outlier', True)\\
    .execute()

outliers = response.data

# Get population scans by age range
response = supabase.table('population_scans')\\
    .select('*')\\
    .gte('age', 40)\\
    .lte('age', 50)\\
    .eq('sex', 'F')\\
    .execute()

scans = response.data
```

---

### Exporting Norms for Analysis

```python
import pandas as pd
from utilities.data import supabase

# Get all norms
response = supabase.table('normative_brain_data').select('*').execute()
norms_df = pd.DataFrame(response.data)

# Save to CSV
norms_df.to_csv('population_norms_export.csv', index=False)

# Analyze coverage
print(norms_df.groupby(['age_min', 'sex']).size())
```

---

## Best Practices

1. **Start Small**: Process 50-100 scans first to validate pipeline
2. **Document Provenance**: Always use `--dataset` flag for tracking
3. **Quality Control**: Review outliers before including in norms
4. **Update Incrementally**: Add new datasets without recomputing all
5. **Age Matching**: Always provide age for most accurate comparisons
6. **Multiple Strata**: Compute both sex-specific and combined norms

---

## Citations and Data Use

### OASIS Dataset

```
Marcus, D.S., et al. (2007). Open Access Series of Imaging Studies (OASIS):
Cross-sectional MRI Data in Young, Middle Aged, Nondemented, and Demented
Older Adults. Journal of Cognitive Neuroscience, 19(9), 1498-1507.
```

**Data Use Agreement**: Required before download. See https://www.oasis-brains.org/

### HCP Dataset

```
Van Essen, D.C., et al. (2013). The WU-Minn Human Connectome Project:
An overview. NeuroImage, 80, 62-79.
```

**Data Use Terms**: Required. See https://www.humanconnectome.org/

### Harvard-Oxford Atlas

```
Harvard Center for Morphometric Analysis
Oxford Centre for Functional MRI of the Brain (FMRIB)
```

**License**: Freely available for research use.

---

## Related Documentation

- **Database Schema**: `docs/DATABASE_SCHEMA_POPULATION_NORMS.md`
- **Function Development**: `docs/FUNCTION_DEVELOPMENT_GUIDE.md`
- **Research Data**: `docs/RESEARCH_DATA_GUIDE.md`
- **Scientist Guide**: `docs/SCIENTIST_GUIDE.md`

---

## Support

For questions or issues:
1. Check this guide and troubleshooting section
2. Review database schema documentation
3. Examine function-specific `--help` output
4. Check function source code comments

---

**Last Updated**: 2025-10-10
**Version**: 1.0
