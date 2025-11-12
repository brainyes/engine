# Population Pipeline v2: Summary of Changes

**Date:** 2025-10-23
**Status:** Implementation Complete - Ready for Testing

---

## The Problem

The original population pipeline (v1) was **fundamentally broken**:

- Raw NIFTI scans are in **native acquisition space** (different for each subject)
- MNI atlases are in **standard MNI152 space**
- v1 just **geometrically resampled** the atlas to match scan dimensions
- **No actual registration** was performed
- Result: **Meaningless volume measurements** (no anatomical correspondence)

> "You can't use an atlas directly on already-normalized MNI scans to measure anatomical differences between people." - ChatGPT's key insight

---

## The Solution

Pipeline v2 uses **proper registration-based measurements**:

1. **Start in native space** (where anatomy actually is)
2. **Register native → MNI** using nonlinear transformation (ANTs)
3. **Get inverse warp** (MNI → native)
4. **Bring atlas to native** via inverse warp
5. **Measure in native** space (correct anatomical correspondence)
6. **Normalize with ICV** in statistical models

---

## What Was Changed

### New Files Created (10)

1. **`functions/preprocess_native_scan.py`**
   - N4 bias field correction
   - Skull-stripping (HD-BET, FSL BET, or threshold)
   - Brain mask generation
   - ICV computation

2. **`functions/register_to_template.py`**
   - ANTs nonlinear registration (SyN)
   - Affine-only fallback (ANTs or SimpleITK)
   - Generates forward + inverse warps
   - Stores transforms in Supabase

3. **`utilities/dependency_checker.py`**
   - Checks which tools are installed
   - Reports best available methods
   - Helps troubleshoot missing dependencies

4. **`utilities/registration_utilities.py`**
   - Helper functions for applying transforms
   - Warp field application (ANTs)
   - Affine transform application
   - Jacobian determinant computation

5. **`migrations/002_population_v2_registration.sql`**
   - Database schema updates
   - Adds ICV, registration_method, processing_version fields
   - Adds model_coefficients, residual_std for regression
   - Creates views and indexes

6. **`research/input/templates/MNI152_T1_1mm_brain.nii.gz`**
   - MNI152 template for registration

### Modified Files (5)

1. **`requirements.txt`**
   - Added: antspyx==0.4.2
   - Added: SimpleITK==2.3.1
   - Added: scikit-learn==1.5.2

2. **`functions/resample_atlas_for_user_nifti.py`** (lines 162-274)
   - **CRITICAL FIX**: Now uses registration transforms in population mode
   - Tries ANTs warp first (most accurate)
   - Falls back to affine transform
   - Falls back to geometric (with warnings) if no registration
   - Tracks which method was used in `source` field

3. **`functions/calculate_roi_volumes.py`** (lines 171-203)
   - Checks for registration_method to determine version
   - Stores `processing_version` ('v1_geometric' vs 'v2_registered')
   - Stores `voxel_count` and `voxel_size_mm3`
   - Enables filtering old (wrong) vs new (correct) data

4. **`functions/compute_population_norms.py`** (lines 33-264, 397-494)
   - Added ICV-adjusted regression models
   - Model: `volume ~ age + age² + sex + ICV`
   - Stores `model_coefficients` and `residual_std`
   - Tracks `model_version` ('v1_simple' vs 'v2_icv_adjusted')
   - Falls back to simple stats if sklearn unavailable

5. **`functions/batch_process_population_dataset.py`** (lines 1-23, 212-241)
   - Added preprocessing step
   - Added registration step
   - Updated docstring to reflect v2 pipeline
   - Tracks which scans succeeded/failed at each stage

6. **`CLAUDE.md`** (lines 57-112)
   - Documented v2 workflow
   - Added dependency checker instructions
   - Explained v1 vs v2 differences
   - Added migration instructions

---

## New Workflow

### For Population Datasets

```bash
# 1. Check dependencies
python -m utilities.dependency_checker

# 2. Batch process dataset
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/raw \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv

# This now runs:
#   - Upload
#   - Preprocess (N4 + skull-strip + ICV)
#   - Register (ANTs or affine)
#   - Atlas warp (inverse transform)
#   - Volume calculation

# 3. Compute norms with ICV regression
python -m functions.compute_population_norms --dataset oasis-1

# 4. Compare individual to norms
python -m functions.compare_to_population_norms FILE_ID --age 45 --sex M
```

### Individual Steps (for debugging)

```bash
python -m functions.preprocess_native_scan FILE_ID
python -m functions.register_to_template FILE_ID --method auto
python -m functions.resample_atlas_for_user_nifti FILE_ID --population-mode
python -m functions.calculate_roi_volumes FILE_ID
```

---

## Database Changes

Run migration before processing new data:

```bash
psql -h your-host -U postgres -d postgres -f migrations/002_population_v2_registration.sql
```

**New columns:**
- `population_scans.icv` - Intracranial volume (mm³)
- `population_scans.registration_method` - 'ants_syn', 'ants_affine', 'sitk_affine'
- `population_scans.preprocessing_version` - 'v2_n4_hdbet', etc.
- `roi_volumes.processing_version` - 'v1_geometric' vs 'v2_registered'
- `roi_volumes.voxel_count`, `voxel_size_mm3` - Calculation metadata
- `normative_brain_data.model_version` - 'v1_simple' vs 'v2_icv_adjusted'
- `normative_brain_data.model_coefficients` - Regression coefficients (JSONB)
- `normative_brain_data.residual_std` - Model residual std for z-scores

**New views:**
- `population_scans_v2` - Only properly processed scans
- `population_processing_summary` - Dataset processing statistics

---

## Validation & Testing

### Before Full Deployment

1. **Test dependencies:**
   ```bash
   python -m utilities.dependency_checker
   ```

2. **Test on 2-3 subjects:**
   ```bash
   # Process one scan end-to-end
   python -m functions.preprocess_native_scan TEST_FILE_ID
   python -m functions.register_to_template TEST_FILE_ID
   python -m functions.resample_atlas_for_user_nifti TEST_FILE_ID --population-mode
   python -m functions.calculate_roi_volumes TEST_FILE_ID
   ```

3. **Visual inspection:**
   - Check atlas alignment (overlay on brain)
   - Verify sulci/gyri match
   - Confirm no gross misalignments

4. **Volume sanity checks:**
   - Volumes should differ from v1 (10-50% changes expected)
   - ICV should be realistic (1,200,000 - 1,800,000 mm³ typical)
   - No duplicate volumes across many subjects

---

## Migration Strategy

**For Existing Data:**
- Old data keeps `processing_version='v1_geometric'`
- Old data remains queryable for comparison
- **Do NOT delete old data** until v2 is validated

**For New Data:**
- New scans use `processing_version='v2_registered'`
- New norms use `model_version='v2_icv_adjusted'`
- UI should indicate which version was used

**Optional Reprocessing:**
- Can reprocess specific datasets with v2
- Use batch_process with `--skip-existing=false`
- Compare results before replacing norms

---

## Expected Results

### Volume Measurements
- **Magnitudes may change** significantly (10-50%)
  - v1 measured in wrong space
  - v2 measures actual anatomy

### Statistical Norms
- **Variability should decrease**
  - v1 had noise from misalignment
  - v2 has proper anatomical correspondence

### ICV Correlation
- **Should see strong correlation**
  - Larger ICV → larger regional volumes
  - Regression should explain 20-50% of variance

### Visual Alignment
- **Atlas should match brain anatomy**
  - Sulci align with atlas boundaries
  - No gross misalignments at edges

---

## Troubleshooting

### Dependencies Not Found
```bash
pip install -r requirements.txt
python -m utilities.dependency_checker
```

### Registration Fails
- Check that preprocessing succeeded first
- Try affine-only: `--method sitk_affine`
- Check MNI template exists: `research/input/templates/MNI152_T1_1mm_brain.nii.gz`

### Old Data in Results
```sql
-- Get only v2 data
SELECT * FROM population_scans WHERE registration_method IS NOT NULL;

-- Get only v2 volumes
SELECT * FROM roi_volumes WHERE processing_version = 'v2_registered';
```

### Slow Processing
- ANTs registration takes 5-10 minutes per scan
- Use affine-only for faster testing: `--method sitk_affine`
- Consider parallel processing for batches

---

## Next Steps

1. **Install dependencies:** `pip install -r requirements.txt`
2. **Run migration:** `psql ... -f migrations/002_population_v2_registration.sql`
3. **Test on 2-3 scans:** Validate results
4. **Process small dataset:** Test batch processing
5. **Validate statistically:** Compare v1 vs v2 norms
6. **Deploy to production:** Process full datasets

---

## References

- ChatGPT conversation: Understanding proper neuroimaging registration
- ANTs Documentation: http://stnava.github.io/ANTs/
- MNI ICBM 152 Template: https://www.bic.mni.mcgill.ca/ServicesAtlases/ICBM152NLin2009
- HD-BET Paper: https://doi.org/10.1002/hbm.24750

---

## Contact

For questions about this implementation, refer to:
- `CLAUDE.md` - Development workflow
- `docs/DATABASE_SCHEMA_POPULATION_NORMS.md` - Database details
- Migration script comments: `migrations/002_population_v2_registration.sql`
