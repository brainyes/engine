# Quick Reference - Cerebro Backend


```bash
python -m functions.upload_nifti research/input/sub-OASIS10001_ses-M00_T1w.nii.gz 

python -m functions.calculate_roi_volumes d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9
 
python -m functions.population_analysis_todo
```

## Essential Commands (Copy & Paste)

### 1. Activate Environment
```bash
source .venv/bin/activate
```

### 2. Upload Brain Scan
```bash
python -m functions.upload_nifti /path/to/your/file.nii.gz
```
**→ COPY THE COMMANDS FROM THE OUTPUT!**

### 3. Process Atlas (copy command from step 2)
```bash
python -m functions.resample_atlas_for_user_nifti YOUR_FILE_ID
```

### 4. Calculate Volumes (copy command from step 3)
```bash
python -m functions.calculate_roi_volumes YOUR_FILE_ID
```

### 5. Convert Annotation Files (optional)
```bash
python -m functions.annot-to-json /path/to/file.annot
```

## Example with Sample File
```bash
# Upload sample file
python -m functions.upload_nifti research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz

# Then copy-paste the commands from the output
```

## Get Help
```bash
python -m functions.upload_nifti --help
python -m functions.resample_atlas_for_user_nifti --help
python -m functions.calculate_roi_volumes --help
python -m functions.annot-to-json --help
```

## Expected Workflow Time
- Upload: ~30 seconds
- Atlas resampling: ~1-2 minutes  
- Volume calculation: ~30 seconds

## Common File Paths
- Example file: `research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz`
- Your files: `/path/to/your/brain_scans/filename.nii.gz` 