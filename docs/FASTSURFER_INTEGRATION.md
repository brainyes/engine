# FastSurfer Integration Guide

## Overview

FastSurfer is a fast and accurate deep-learning based neuroimaging pipeline that provides a fully compatible FreeSurfer alternative. It's approximately **10-20x faster** than FreeSurfer:

- **Segmentation only**: ~5 minutes (vs FreeSurfer's 4-8 hours)
- **Full pipeline** (segmentation + surfaces): ~60-90 minutes (vs FreeSurfer's 8-12 hours)

FastSurfer produces FreeSurfer-compatible outputs, so all downstream analysis tools work seamlessly.

## Architecture

### Components

1. **fastsurfer_recon_all.py** - Main processing pipeline
2. **fastsurfer_store_files.py** - Store outputs to object storage
3. **fastsurfer_parse_statistics.py** - Parse and store statistics in database

### FreeSurfer Dependencies

FastSurfer requires **FreeSurfer 7** for surface reconstruction functionality. Our setup supports both:

- **FreeSurfer 8** (default) - For traditional FreeSurfer workflows
- **FreeSurfer 7** - For FastSurfer compatibility

## Installation

### Docker (Recommended)

The Dockerfile automatically installs both FreeSurfer versions:

```dockerfile
# FreeSurfer 8 (default)
ENV FREESURFER_HOME=/usr/local/freesurfer/8.1.0

# FreeSurfer 7 (for FastSurfer)
ENV FREESURFER7_HOME=/usr/local/freesurfer/7.4.1

# FastSurfer
ENV FASTSURFER_HOME=/app/FastSurfer
```

### Local macOS Installation

1. **Install FreeSurfer 7**:
   ```bash
   # Download from https://surfer.nmr.mgh.harvard.edu/fswiki/DownloadAndInstall
   # Install to /Applications/freesurfer/7.4.1 or /usr/local/freesurfer/7.4.1
   ```

2. **Initialize FastSurfer submodule**:
   ```bash
   cd /path/to/brainyes/engine
   git submodule update --init FastSurfer
   ```

3. **Set environment variables** (add to ~/.zshrc or ~/.bash_profile):
   ```bash
   export FREESURFER7_HOME=/Applications/freesurfer/7.4.1
   export FASTSURFER_HOME=/path/to/brainyes/engine/FastSurfer
   ```

## Usage

### 1. Run FastSurfer Processing

#### Segmentation Only (~5 minutes)

Fast mode for volumetric analysis only:

```bash
python -m functions.fastsurfer_recon_all FILE_ID --seg-only
```

**Options**:
- `--seg-only` - Segmentation only mode (~5 min)
- `--device cuda|cpu|auto` - Processing device (default: auto-detect GPU)
- `--parallel-cores N` - Number of CPU cores (default: all available)
- `--field-strength 3T|1.5T` - MRI field strength (default: 3T)
- `--subject-id SUBJECT_ID` - Custom subject identifier
- `--subjects-dir PATH` - Custom output directory

**Example**:
```bash
# Quick segmentation (GPU)
python -m functions.fastsurfer_recon_all d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9 \
    --seg-only \
    --device cuda \
    --parallel-cores 8

# Expected output:
# ✅ FastSurfer processing completed successfully!
# Output directory: /tmp/fastsurfer_xyz/sub-d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9
# Processing time: 312.5 seconds (5.2 minutes)
```

#### Full Pipeline (~60-90 minutes)

Complete analysis including surface reconstruction:

```bash
python -m functions.fastsurfer_recon_all FILE_ID
```

**Example**:
```bash
# Full pipeline
python -m functions.fastsurfer_recon_all d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9 \
    --device cuda \
    --parallel-cores 8 \
    --field-strength 3T

# Expected output:
# ✅ FastSurfer processing completed successfully!
# Processing time: 4520.3 seconds (75.3 minutes)
```

### 2. Store FastSurfer Outputs

Upload processing results to object storage:

```bash
python -m functions.fastsurfer_store_files \
    NIFTI_FILE_ID \
    FASTSURFER_OUTPUT_DIRECTORY \
    --storage-mode complete
```

**Storage Modes**:
- `segmentation_only` (~30MB) - Just segmentation volumes
- `essential` (~50MB) - Key volumes, surfaces, and statistics
- `complete` (~230MB) - All output files (default)

**Example**:
```bash
python -m functions.fastsurfer_store_files \
    d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9 \
    /tmp/fastsurfer_xyz/sub-d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9 \
    --storage-mode essential

# Expected output:
# ✅ FastSurfer files stored successfully
# Files uploaded: 23/23
# Total size: 52.3MB
# Storage path: d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9
```

### 3. Parse and Store Statistics

Extract measurements and store in database:

```bash
python -m functions.fastsurfer_parse_statistics \
    NIFTI_FILE_ID \
    FASTSURFER_OUTPUT_DIRECTORY
```

**Example**:
```bash
python -m functions.fastsurfer_parse_statistics \
    d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9 \
    /tmp/fastsurfer_xyz/sub-d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9

# Expected output:
# ✅ Statistics parsing completed successfully!
# Stored: 15 global measures, 68 regional measures
# Stored: 45 subcortical segments, 2 curvature stats
# Processing method: FastSurfer (deep learning)
```

## Complete Workflow Example

### Local Processing

```bash
# Step 1: Upload NIFTI file
FILE_ID=$(python -m functions.upload_nifti research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz | grep "File ID:" | cut -d' ' -f3)

# Step 2: Run FastSurfer (segmentation only for speed)
python -m functions.fastsurfer_recon_all $FILE_ID \
    --seg-only \
    --subjects-dir ./fastsurfer_output

# Step 3: Store files
python -m functions.fastsurfer_store_files \
    $FILE_ID \
    ./fastsurfer_output/sub-$FILE_ID \
    --storage-mode essential

# Step 4: Parse statistics
python -m functions.fastsurfer_parse_statistics \
    $FILE_ID \
    ./fastsurfer_output/sub-$FILE_ID
```

### Docker Processing

```bash
# Build image with FastSurfer
docker build -t brainyes-engine:fastsurfer .

# Run FastSurfer in container
docker run --gpus all \
    -v /path/to/data:/data \
    -v /path/to/output:/output \
    brainyes-engine:fastsurfer \
    python3.12 -m functions.fastsurfer_recon_all FILE_ID \
        --seg-only \
        --subjects-dir /output
```

## Output Files

FastSurfer produces FreeSurfer-compatible outputs plus some additions:

### Segmentation Outputs

```
{subject_id}/
├── mri/
│   ├── orig.mgz                          # Original volume
│   ├── brain.mgz                         # Skull-stripped brain
│   ├── aseg.mgz                          # Subcortical segmentation
│   ├── aparc+aseg.mgz                    # Combined parcellation
│   └── aparc.DKTatlas+aseg.deep.mgz     # FastSurfer deep learning segmentation ⭐
├── stats/
│   ├── aseg.stats                        # Subcortical statistics
│   ├── lh.aparc.stats                    # Left hemisphere parcellation
│   └── rh.aparc.stats                    # Right hemisphere parcellation
└── scripts/
    └── deep-seg.log                      # FastSurfer processing log
```

### Full Pipeline Outputs

Additional surface files (when not using `--seg-only`):

```
{subject_id}/
├── surf/
│   ├── lh.white                          # Left hemisphere white matter surface
│   ├── rh.white                          # Right hemisphere white matter surface
│   ├── lh.pial                           # Left hemisphere pial surface
│   ├── rh.pial                           # Right hemisphere pial surface
│   ├── lh.inflated                       # Inflated surfaces
│   └── rh.inflated
├── label/
│   ├── lh.aparc.annot                    # Surface parcellation labels
│   └── rh.aparc.annot
└── stats/
    ├── lh.curv.stats                     # Curvature statistics
    └── rh.curv.stats
```

## Database Schema

FastSurfer statistics are stored in the same tables as FreeSurfer, with a `processing_method` field to distinguish:

### Tables

- `freesurfer_global_measures` - Global brain metrics (ICV, total cortical volume, etc.)
- `freesurfer_cortical_regions` - Regional cortical measurements
- `freesurfer_subcortical_segmentations` - Subcortical structure volumes
- `freesurfer_curvature_stats` - Surface curvature statistics
- `freesurfer_summary_stats` - Quick summary metrics

### Processing Method Field

```sql
processing_method VARCHAR DEFAULT 'freesurfer'
-- Values: 'freesurfer' or 'fastsurfer'
```

Query examples:

```sql
-- Get all FastSurfer results
SELECT * FROM freesurfer_global_measures
WHERE processing_method = 'fastsurfer';

-- Compare FreeSurfer vs FastSurfer for same scan
SELECT
    fm.measure_name,
    fm.value as freesurfer_value,
    fs.value as fastsurfer_value,
    ABS(fm.value - fs.value) as difference
FROM freesurfer_global_measures fm
JOIN freesurfer_global_measures fs
    ON fm.nifti_file_id = fs.nifti_file_id
    AND fm.measure_name = fs.measure_name
WHERE fm.processing_method = 'freesurfer'
    AND fs.processing_method = 'fastsurfer'
    AND fm.nifti_file_id = 'FILE_ID';
```

## Storage Buckets

FastSurfer files are stored separately from FreeSurfer:

- **FreeSurfer**: `freesurfer-outputs` bucket
- **FastSurfer**: `fastsurfer-outputs` bucket

Files are organized by NIFTI file ID:

```
fastsurfer-outputs/
└── {nifti_file_id}/
    ├── mri/
    ├── surf/
    ├── stats/
    └── label/
```

## Performance Comparison

| Pipeline | Mode | Time (GPU) | Time (CPU) |
|----------|------|------------|------------|
| FreeSurfer | Full | 8-12 hours | 12-24 hours |
| FastSurfer | Segmentation | ~5 minutes | ~15 minutes |
| FastSurfer | Full | 60-90 minutes | 2-3 hours |

**Speedup**: FastSurfer is approximately **10-20x faster** than FreeSurfer!

## Accuracy

FastSurfer achieves comparable or better accuracy than FreeSurfer:

- **Segmentation**: Dice coefficient > 0.95 for most structures
- **Cortical thickness**: Mean absolute error < 0.1mm
- **Volume measurements**: Highly correlated with FreeSurfer (r > 0.98)

See FastSurfer papers for detailed validation:
- [FastSurfer - NeuroImage 2020](https://doi.org/10.1016/j.neuroimage.2020.117012)
- [FastSurferVINN - NeuroImage 2022](http://dx.doi.org/10.1016/j.neuroimage.2022.118933)

## Troubleshooting

### FreeSurfer 7 Not Found

**Error**: `FreeSurfer 7 not found at /usr/local/freesurfer/7.4.1`

**Solution**:
```bash
# Set environment variable
export FREESURFER7_HOME=/path/to/freesurfer/7.4.1

# Or in Dockerfile
ENV FREESURFER7_HOME=/usr/local/freesurfer/7.4.1
```

### FastSurfer Submodule Not Initialized

**Error**: `FastSurfer not found. Expected at: /app/FastSurfer/run_fastsurfer.sh`

**Solution**:
```bash
cd /path/to/brainyes/engine
git submodule update --init FastSurfer
```

### GPU Not Detected

**Error**: FastSurfer runs on CPU instead of GPU

**Solution**:
```bash
# Check PyTorch GPU availability
python -c "import torch; print(torch.cuda.is_available())"

# Force GPU usage
python -m functions.fastsurfer_recon_all FILE_ID --device cuda

# Or use CPU explicitly (slower)
python -m functions.fastsurfer_recon_all FILE_ID --device cpu
```

### Missing Statistics Files

**Error**: `FastSurfer stats directory not found`

**Solution**: Make sure you ran the full FastSurfer pipeline (not just segmentation):
```bash
# Run full pipeline (generates stats)
python -m functions.fastsurfer_recon_all FILE_ID

# NOT segmentation-only mode
python -m functions.fastsurfer_recon_all FILE_ID --seg-only  # ❌ No stats files
```

## Environment Variables Summary

### Docker
```dockerfile
ENV FREESURFER_HOME=/usr/local/freesurfer/8.1.0
ENV FREESURFER7_HOME=/usr/local/freesurfer/7.4.1
ENV FASTSURFER_HOME=/app/FastSurfer
ENV FS_LICENSE=$FREESURFER_HOME/license.txt
```

### macOS Local
```bash
export FREESURFER_HOME=/Applications/freesurfer/8.1.0
export FREESURFER7_HOME=/Applications/freesurfer/7.4.1
export FASTSURFER_HOME=/Users/username/brainyes/engine/FastSurfer
```

## Next Steps

1. **For quick volumetric analysis**: Use `--seg-only` mode (~5 minutes)
2. **For surface analysis**: Run full pipeline (~60-90 minutes)
3. **For validation**: Compare FastSurfer vs FreeSurfer results in database
4. **For production**: Use Docker with GPU for optimal performance

## References

- [FastSurfer GitHub](https://github.com/Deep-MI/FastSurfer)
- [FastSurfer Documentation](https://github.com/Deep-MI/FastSurfer/tree/stable/doc)
- [FreeSurfer Compatibility](https://surfer.nmr.mgh.harvard.edu/fswiki/FreeSurferMethodsCitation)