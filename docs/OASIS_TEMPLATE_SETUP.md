# OASIS Template Setup for Population Norms

## Overview

Following Google AI recommendations and medical imaging best practices, we now use **pre-built OASIS templates** from ANTs for population norm processing. This provides:

✅ **Better accuracy** - Age-matched template (OASIS dataset)
✅ **No extra computation** - Template already built by ANTs experts
✅ **Research-grade quality** - Battle-tested in neuroimaging research
✅ **Maximum performance** - Parallel processing with ANTs SyN (still gold standard)

## Why OASIS Template Instead of MNI152?

| Aspect | MNI152 Template | OASIS Template |
|--------|----------------|----------------|
| **Source** | Mixed datasets, multiple ages | OASIS dataset only |
| **Age range** | Generic adult (18-90+) | Better matched to OASIS-1 (18-96) |
| **Quality** | General purpose | Purpose-built for OASIS data |
| **Accuracy** | Good for general use | Optimal for OASIS population norms |

## Downloaded Template

**Location**: `research/input/templates/OASIS_template/`

**Key files**:
- `T_template0_BrainCerebellum.nii.gz` - Brain-extracted template (used for registration)
- `T_template0.nii.gz` - Full head template
- `Priors2/priors*.nii.gz` - Tissue probability maps (6 tissues)

**Template specs**:
- Resolution: 1mm isotropic
- Dimensions: 216 × 256 × 291
- Built from: OASIS dataset using ANTs SyN pipeline

## Automatic Template Selection

The batch processor **automatically selects the correct template**:

```python
# In batch_process_population_dataset.py
template_name = 'oasis' if 'oasis' in dataset_name.lower() else 'mni152'
```

Examples:
- `--dataset oasis-1` → Uses OASIS template
- `--dataset oasis-3` → Uses OASIS template
- `--dataset hcp-young-adult` → Uses MNI152 template

## Manual Template Selection

You can manually specify templates:

```bash
# Use OASIS template
python -m functions.register_to_template FILE_ID --template oasis

# Use MNI152 template
python -m functions.register_to_template FILE_ID --template mni152

# Use custom template
python -m functions.register_to_template FILE_ID --template-path /path/to/template.nii.gz
```

## Performance

### Current Setup (with OASIS template)

**Per scan with ANTs SyN**:
- Sequential: ~10 minutes
- With 7 parallel workers: ~10 minutes ÷ 7 = **~90 seconds wall-clock time**

**Batch of 100 scans**:
- Sequential: 16.7 hours
- With 7 workers: **~2.4 hours** (7x speedup)

### Why Not Use Affine or VoxelMorph?

Per Google AI analysis:
> "Claude's suggestion to use only ANTs affine registration for speed is likely a misstep and could significantly compromise the accuracy of your population norms."

- **Affine-only** captures global scaling/rotation but misses local anatomical details
- **VoxelMorph** has Python 3.12 compatibility issues and unstable API
- **ANTs SyN** is the gold standard - don't compromise on accuracy for population norms

**The real performance win comes from parallel processing, not cutting corners.**

## Setup Instructions

### 1. Download Template (Already Done)

Template is already downloaded to `research/input/templates/OASIS_template/`.

To re-download:
```bash
cd research/input/templates
curl -L -o Oasis.zip "https://ndownloader.figshare.com/files/3133832"
unzip Oasis.zip
mv MICCAI2012-Multi-Atlas-Challenge-Data OASIS_template
rm Oasis.zip
```

### 2. Verify Template

```bash
python3 -c "
import nibabel as nib
import os

template_path = 'research/input/templates/OASIS_template/T_template0_BrainCerebellum.nii.gz'
if os.path.exists(template_path):
    img = nib.load(template_path)
    print(f'✅ OASIS template found')
    print(f'   Shape: {img.shape}')
    print(f'   Voxel size: {img.header.get_zooms()[:3]} mm')
else:
    print(f'❌ Template not found: {template_path}')
"
```

### 3. Run Population Processing

```bash
# Process OASIS-1 dataset (automatically uses OASIS template)
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/raw \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv
```

## Docker Setup

Add to Dockerfile to automatically download template:

```dockerfile
# Download OASIS template
WORKDIR /app/research/input/templates
RUN curl -L -o Oasis.zip "https://ndownloader.figshare.com/files/3133832" && \
    unzip -q Oasis.zip && \
    mv MICCAI2012-Multi-Atlas-Challenge-Data OASIS_template && \
    rm Oasis.zip

WORKDIR /app
```

## Troubleshooting

### "Template not found"

Ensure template is in the correct location:
```bash
ls -lh research/input/templates/OASIS_template/T_template0_BrainCerebellum.nii.gz
```

If missing, re-download using instructions above.

### "Registration failed"

Check that preprocessing was successful:
```bash
# Preprocessing creates brain_n4.nii.gz which registration needs
ls -lh research/input/templates/OASIS_template/
```

### Still slow?

Use parallel processing (auto-detects optimal workers):
```bash
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/raw \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv
    # No --workers flag needed - auto-detects!
```

## References

- **ANTs Templates**: https://figshare.com/articles/dataset/ANTs_ANTsR_Brain_Templates/915436
- **OASIS Dataset**: https://www.oasis-brains.org/
- **ANTs Registration**: https://github.com/ANTsX/ANTs
- **Google AI Recommendation**: Use pre-built templates for population norms to save time while maintaining accuracy

## Summary

**What changed**:
- ✅ Downloaded pre-built OASIS template from ANTs Figshare
- ✅ Auto-select OASIS template for OASIS datasets
- ✅ Keep ANTs SyN as registration method (gold standard)
- ✅ Use parallel processing for speed (7x faster)
- ❌ Removed VoxelMorph (compatibility issues, not needed)

**Result**:
- Maximum accuracy (ANTs SyN + age-matched template)
- Good performance (parallel processing)
- Production-ready (no experimental dependencies)
- Research-grade (using established templates)
