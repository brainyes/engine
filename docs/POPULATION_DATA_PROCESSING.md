# Population Data Processing Guide

This guide explains how to build normative brain data from population datasets (OASIS, HCP, etc.) for comparison with individual patient scans.

## Overview

The population data processing pipeline consists of four main steps:

1. **Download Dataset** - Automatically download public datasets (OASIS-1, etc.)
2. **Convert Format** - Convert ANALYZE format to NIfTI if needed
3. **Batch Process** - Process all scans with atlas registration and ROI analysis
4. **Compute Norms** - Generate statistical normative data (mean, std, percentiles)
5. **Backfill Metadata** - Update existing records with demographic data

## Prerequisites

- Python environment activated
- Supabase connection configured
- `population_scans` table created (migration provided)
- Sufficient disk space (~20GB for OASIS-1)

## Pipeline Functions

### 1. Download OASIS-1 Dataset

```bash
python -m functions.download_oasis_dataset \
    research/input/datasets/oasis-1 \
    --subjects research/input/datasets/oasis-1/subjects_to_download.txt
```

**What it does:**
- Downloads 12 OASIS-1 disc archives (~18GB total)
- Extracts brain scans automatically
- Organizes by subject ID

**Options:**
- `--subjects` - Text file with subject IDs to download (one per line)
- `--all` - Download all 416 subjects (default if no subject list)

**Time:** ~2-4 hours (depending on connection)

**Output:** Raw ANALYZE format files in disc directories

### 2. Convert ANALYZE to NIfTI (OASIS-1 Only)

```bash
python -m functions.convert_oasis_to_nifti \
    research/input/datasets/oasis-1/raw \
    --output research/input/datasets/oasis-1/nifti
```

**What it does:**
- Finds all ANALYZE format files (.hdr/.img)
- Converts to NIfTI format (.nii.gz)
- Handles 4D to 3D dimension reduction
- Organizes by subject ID

**Options:**
- `--output` - Output directory (default: input_dir/../nifti)
- `--no-compress` - Save as .nii instead of .nii.gz
- `--flat` - Don't organize by subject (put all in one directory)

**Time:** ~5-10 minutes for 437 scans

**Example output:**
```
research/input/datasets/oasis-1/nifti/
├── OAS1_0001_MR1/
│   └── OAS1_0001_MR1_mpr-1_anon_t88_gfc.nii.gz
├── OAS1_0002_MR1/
│   └── OAS1_0002_MR1_mpr-1_anon_t88_gfc.nii.gz
...
```

### 3. Batch Process Population Dataset

```bash
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/nifti \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv
```

**What it does:**
- Finds all NIfTI files in directory
- For each scan:
  1. Uploads to storage
  2. Resamples Harvard-Oxford atlas to scan space
  3. Calculates ROI volumes
  4. Saves population metadata (age, sex, diagnosis)

**Options:**
- `--dataset` - Dataset name (e.g., oasis-1, hcp-young-adult) **[Required]**
- `--metadata` - CSV file with subject metadata (age, sex, diagnosis)
- `--count` - Limit number of scans to process (for testing)
- `--dry-run` - Show what would be processed without actually doing it
- `--overwrite` - Reprocess existing scans (default: skip)

**Metadata CSV Format:**
```csv
ID,Age,M/F,CDR,diagnosis_bl
OAS1_0001_MR1,74,F,0.0,Nondemented
OAS1_0002_MR1,55,F,0.0,Nondemented
OAS1_0003_MR1,73,F,0.5,Demented
```

**Time:** ~2-3 minutes per scan

**Example workflow:**
```bash
# Test with first 5 scans
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/nifti \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv \
    --count 5

# Process all scans
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/nifti \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv
```

### 4. Backfill Population Metadata

If you processed scans **without** the `--metadata` flag, use this to add metadata later:

```bash
python -m functions.backfill_population_metadata \
    research/input/datasets/oasis-1/selected_subjects.csv \
    --dataset oasis-1
```

**What it does:**
- Finds population scans missing age/sex data
- Matches subject IDs with CSV metadata
- Updates database records

**Options:**
- `--dataset` - Filter by specific dataset (optional)
- `--dry-run` - Show what would be updated without making changes

**Time:** < 1 minute for hundreds of records

### 5. Compute Population Norms

```bash
python -m functions.compute_population_norms \
    --dataset oasis-1 \
    --min-samples 30 \
    --age-bin-width 10
```

**What it does:**
- Fetches all population scans with metadata
- Retrieves ROI volumes for all scans
- Creates age bins (e.g., 20-30, 30-40, etc.)
- Computes statistics for each stratum (age_bin × sex × ROI):
  - Mean, standard deviation
  - Percentiles: 10th, 25th, 50th (median), 75th, 90th
  - Sample size
- Saves to `normative_brain_data` table

**Options:**
- `--dataset` - Filter by specific dataset (default: all datasets)
- `--min-samples` - Minimum sample size per stratum (default: 30)
- `--age-bin-width` - Width of age bins in years (default: 10)
- `--no-combined-sex` - Skip computing sex-agnostic norms
- `--dry-run` - Compute but don't save to database

**Time:** ~10-30 seconds for hundreds of scans

**Example:**
```bash
# For testing with small datasets (5 scans)
python -m functions.compute_population_norms \
    --dataset oasis-1 \
    --min-samples 1

# For production with full dataset
python -m functions.compute_population_norms \
    --dataset oasis-1 \
    --min-samples 30

# Custom age bins (5-year intervals)
python -m functions.compute_population_norms \
    --dataset oasis-1 \
    --age-bin-width 5
```

## Complete Workflow Example

### OASIS-1 from Scratch

```bash
# 1. Download dataset
cd /Users/oytuntez/brainyes/engine
python -m functions.download_oasis_dataset \
    research/input/datasets/oasis-1 \
    --subjects research/input/datasets/oasis-1/subjects_to_download.txt

# 2. Convert ANALYZE to NIfTI
python -m functions.convert_oasis_to_nifti \
    research/input/datasets/oasis-1/raw \
    --output research/input/datasets/oasis-1/nifti

# 3. Test with 5 scans first
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/nifti \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv \
    --count 5

# 4. Compute norms (use min-samples 1 for testing)
python -m functions.compute_population_norms \
    --dataset oasis-1 \
    --min-samples 1

# 5. If tests pass, process all scans
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/nifti \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv

# 6. Compute final norms with proper threshold
python -m functions.compute_population_norms \
    --dataset oasis-1 \
    --min-samples 30
```

## Database Schema

### `population_scans` Table

Stores metadata for population dataset scans.

```sql
CREATE TABLE IF NOT EXISTS population_scans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nifti_file_id UUID NOT NULL UNIQUE,
    dataset_source TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    age INTEGER,
    sex TEXT CHECK (sex IN ('M', 'F', 'U')),
    diagnosis TEXT,
    scan_quality FLOAT,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (nifti_file_id) REFERENCES nifti_files(id) ON DELETE CASCADE
);

CREATE INDEX idx_population_scans_dataset ON population_scans(dataset_source);
CREATE INDEX idx_population_scans_age_sex ON population_scans(age, sex);
CREATE INDEX idx_population_scans_nifti_file ON population_scans(nifti_file_id);
```

**Migration file:** `app/supabase/migrations/20251011000000_create_population_scans.sql`

### `normative_brain_data` Table

Stores computed population norms.

```sql
CREATE TABLE IF NOT EXISTS normative_brain_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    structure_name TEXT NOT NULL,
    roi_label INTEGER NOT NULL,
    age_min INTEGER NOT NULL,
    age_max INTEGER NOT NULL,
    sex TEXT CHECK (sex IN ('M', 'F', 'U')),
    mean FLOAT NOT NULL,
    std FLOAT NOT NULL,
    p10 FLOAT NOT NULL,
    p25 FLOAT NOT NULL,
    p50 FLOAT NOT NULL,  -- Median
    p75 FLOAT NOT NULL,
    p90 FLOAT NOT NULL,
    sample_size INTEGER NOT NULL,
    dataset_sources TEXT[] NOT NULL,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    unit TEXT DEFAULT 'mm³',
    source TEXT
);
```

## Subject ID Format

Different datasets use different subject ID formats. The system preserves the exact format:

**OASIS-1:**
- Full ID: `OAS1_0001_MR1` (includes session number)
- Components: `OAS1_` + `0001` + `_MR1` (first scan) or `_MR2` (second scan)
- Database storage: Full ID with session number
- Metadata CSV: Must match exactly (include `_MR1` suffix)

**BIDS format:**
- Example: `sub-OASIS10001_ses-M00_T1w`
- Extraction: `OASIS10001` (removes `sub-` prefix)

## Troubleshooting

### No metadata found for subjects

**Problem:** Backfill or batch processing can't match subject IDs

**Solution:** Ensure subject IDs match exactly between filenames and CSV:
- OASIS-1 files: `OAS1_0001_MR1_*.nii.gz`
- CSV column: `ID` or `subject_id` = `OAS1_0001_MR1`

### No norms computed (all strata skipped)

**Problem:** Not enough samples per age/sex/ROI stratum

**Solutions:**
1. Lower `--min-samples` threshold: `--min-samples 10`
2. Process more scans from the dataset
3. Use wider age bins: `--age-bin-width 20`
4. Compute sex-agnostic norms: `--no-combined-sex` (remove this flag)

### 4D image dimension errors

**Problem:** `ValueError: The shape specified should be the shape of the 3D grid`

**Solution:** This is handled automatically by:
- `convert_oasis_to_nifti.py` - squeezes 4D images during conversion
- `resample_atlas_for_user_nifti.py` - defensively checks and squeezes

If you still see this error, the scan may have an unusual format. Check with:
```python
import nibabel as nib
img = nib.load('path/to/scan.nii.gz')
print(img.shape)  # Should be (x, y, z) not (x, y, z, 1)
```

### Storage RLS policy violations

**Problem:** `new row violates row-level security policy`

**Solution:** Storage paths must start with `user_id/`:
- Correct: `{user_id}/{nifti_file_id}/atlas-resampled.nii`
- Wrong: `{nifti_file_id}/atlas-resampled.nii`

This is handled automatically for anonymous users in batch processing.

## File Paths Reference

### OASIS-1 Directory Structure

```
research/input/datasets/oasis-1/
├── subjects_to_download.txt           # List of subject IDs to download
├── selected_subjects.csv              # Metadata (age, sex, diagnosis)
├── raw/                               # Downloaded ANALYZE files
│   ├── disc1/
│   │   └── OAS1_0001_MR1/
│   │       └── PROCESSED/MPRAGE/T88_111/
│   │           ├── *.hdr              # ANALYZE header
│   │           └── *.img              # ANALYZE image
│   ├── disc2/
│   └── ...
└── nifti/                             # Converted NIfTI files
    ├── OAS1_0001_MR1/
    │   └── *.nii.gz
    ├── OAS1_0002_MR1/
    └── ...
```

## Next Steps

After computing population norms, you can:

1. **Compare individual scans:**
   ```bash
   python -m functions.compare_to_population_norms \
       NIFTI_FILE_ID \
       --age 45 \
       --sex M
   ```

2. **View in dashboard:**
   - Normative comparisons shown in patient reports
   - Z-scores and percentiles displayed
   - Outlier regions highlighted

3. **Add more datasets:**
   - Process HCP, UK Biobank, or other public datasets
   - Norms will be combined across datasets with proper attribution

## Best Practices

1. **Always include metadata CSV** when batch processing
2. **Test with --count 5 first** before processing full dataset
3. **Use --dry-run** to preview before making changes
4. **Keep min-samples ≥ 30** for statistically meaningful norms
5. **Backup database** before re-computing norms for existing datasets
6. **Monitor processing** - scans take 2-3 minutes each
7. **Verify subject IDs** match exactly between files and CSV

## Performance Tips

- **Batch processing:** Processes scans sequentially (2-3 min each)
- **Disk space:** Allow ~50MB per scan for storage
- **Memory:** Peak usage ~2-4GB during atlas resampling
- **Parallelization:** Not currently supported (sequential processing)

## API Integration

These functions are designed for **command-line use only**. They are **not** exposed via API endpoints because:

- Long-running operations (hours for full datasets)
- Large file downloads and processing
- Administrative/research workflows

For programmatic access, use the Python functions directly:

```python
from functions.batch_process_population_dataset import batch_process_population_dataset
from functions.compute_population_norms import compute_population_norms

# Process dataset
stats = batch_process_population_dataset(
    dataset_dir='research/input/datasets/oasis-1/nifti',
    dataset_name='oasis-1',
    metadata_csv='research/input/datasets/oasis-1/selected_subjects.csv',
    max_scans=10
)

# Compute norms
norms = compute_population_norms(
    dataset_name='oasis-1',
    min_samples=30
)
```

## Related Documentation

- [RESEARCH_DATA_GUIDE.md](RESEARCH_DATA_GUIDE.md) - General data organization
- [FUNCTION_DEVELOPMENT_GUIDE.md](FUNCTION_DEVELOPMENT_GUIDE.md) - Creating new functions
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Basic commands for individual scans