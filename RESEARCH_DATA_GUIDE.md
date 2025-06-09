# Research Data Guide

This guide explains how scientific data is organized and accessed in the Cerebro system.

## 📁 Directory Structure

The `research/input/` directory contains all scientific datasets, atlases, and reference files used by functions and insights.

```
research/input/
├── README.md                                    # Dataset documentation
├── raw/                                         # Raw, unprocessed data
│   ├── sub-OASIS10001_ses-M00_T1w.nii.gz      # Sample brain scans
│   ├── sub-OASIS10003_ses-M00_T1w.nii.gz
│   ├── sub-OASIS10010_ses-M00_T1w.nii.gz
│   ├── lh.custom_regions_de_ki.annot           # FreeSurfer annotations
│   ├── rh.custom_regions_de_ki.annot
│   ├── lh.custom_regions_de_ki.json            # Converted JSON annotations
│   ├── rh.custom_regions_de_ki.json
│   ├── FreeSurferColorLUT.txt                  # Color lookup tables
│   ├── lh.asc                                  # Surface meshes
│   ├── rh.asc
│   └── fsaverage/                              # FreeSurfer average templates
├── preprocessed/                               # Processed/normalized data
├── tsv_files/                                  # Metadata and clinical data
│   ├── lab_1/
│   │   ├── OASIS_BIDS.tsv                     # Clinical/demographic data
│   │   ├── train.tsv                          # Training set splits
│   │   └── validation.tsv                     # Validation set splits
│   └── lab_2/                                 # Additional lab datasets
├── HarvardOxford-cort-maxprob-thr25-2mm.nii.gz # Brain atlas
└── sub-OASIS10001_ses-M00_T1w.nii            # Example NIFTI files
```

## ⚙️ Configuration (utilities/options.py)

The system uses centralized path configuration:

```python
# Base directories
dataset_dir = 'research/input'          # All scientific data
output_dir = 'research/output'          # Processing results

# Specific file paths
atlas_file_path = 'research/input/HarvardOxford-cort-maxprob-thr25-2mm.nii.gz'
oasis_bids_tsv_path = 'research/input/tsv_files/lab_1/OASIS_BIDS.tsv'
```

## 🧠 Data Types

### **1. Brain Images (NIFTI)**
- **Format**: `.nii` or `.nii.gz` (compressed)
- **Location**: `research/input/raw/`
- **Purpose**: Primary brain scan data for analysis
- **Example**: `sub-OASIS10001_ses-M00_T1w.nii.gz`

### **2. Brain Atlases**
- **Format**: `.nii.gz` 
- **Location**: `research/input/`
- **Purpose**: Reference brain regions for ROI analysis
- **Example**: `HarvardOxford-cort-maxprob-thr25-2mm.nii.gz`

### **3. Surface Annotations**
- **Format**: `.annot` (FreeSurfer) or `.json` (converted)
- **Location**: `research/input/raw/`
- **Purpose**: Surface-based brain region definitions
- **Example**: `lh.custom_regions_de_ki.annot`

### **4. Clinical/Metadata**
- **Format**: `.tsv` (tab-separated values)
- **Location**: `research/input/tsv_files/`
- **Purpose**: Demographics, clinical scores, study metadata
- **Example**: `OASIS_BIDS.tsv`

### **5. Surface Meshes**
- **Format**: `.asc` (ASCII format)
- **Location**: `research/input/raw/`
- **Purpose**: 3D brain surface representations
- **Example**: `lh.asc` (left hemisphere)

## 🔧 Accessing Data in Functions

### **Using Configuration Paths**
```python
from utilities.options import dataset_dir, atlas_file_path, oasis_bids_tsv_path

# Load atlas
import nibabel as nib
atlas = nib.load(atlas_file_path)

# Load clinical data
import pandas as pd
clinical_data = pd.read_csv(oasis_bids_tsv_path, sep='\t')

# Build paths to raw data
import os
raw_data_dir = os.path.join(dataset_dir, 'raw')
sample_file = os.path.join(raw_data_dir, 'sub-OASIS10001_ses-M00_T1w.nii.gz')
```

### **Common Patterns**
```python
# Pattern 1: Load example/template data
def my_analysis_function(nifti_file_id):
    from utilities.options import dataset_dir
    
    # Use example data for testing
    example_file = os.path.join(dataset_dir, 'raw', 'sub-OASIS10001_ses-M00_T1w.nii.gz')
    
    # Or load user's uploaded data
    user_nifti = get_nifti_file(nifti_file_id, True)

# Pattern 2: Load reference data
def process_with_atlas(nifti_file_id):
    from utilities.options import atlas_file_path
    
    # Load standard atlas
    atlas = nib.load(atlas_file_path)
    
    # Process user data against atlas
    user_data = get_nifti_file(nifti_file_id, True)

# Pattern 3: Load clinical metadata
def correlate_with_clinical_data(nifti_file_id):
    from utilities.options import oasis_bids_tsv_path
    
    # Load clinical data
    clinical_df = pd.read_csv(oasis_bids_tsv_path, sep='\t')
    
    # Match with imaging data
    volumes = get_roi_volumes(nifti_file_id)
```

## 📊 Dataset Information

### **OASIS-1 Dataset**
- **Source**: OASIS Cross-Sectional study
- **Subjects**: Multiple participants with T1-weighted MRI
- **Format**: BIDS-compliant NIFTI files
- **Clinical data**: Demographics, cognitive scores, diagnoses

### **Harvard-Oxford Atlas**
- **Type**: Probabilistic cortical atlas
- **Resolution**: 2mm MNI space
- **Regions**: ~48 cortical regions
- **Use**: Standard brain region definitions

## 🔄 Data Workflow

### **1. Raw Data → Functions**
```bash
# Raw brain scan
research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz
    ↓
# Upload to system
python -m functions.upload_nifti research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz
    ↓
# Process with atlas
research/input/HarvardOxford-cort-maxprob-thr25-2mm.nii.gz
    ↓
# Generate ROI volumes
Database: roi_volumes table
```

### **2. Metadata → Insights**
```bash
# Clinical data
research/input/tsv_files/lab_1/OASIS_BIDS.tsv
    ↓
# Load in insight
pandas.read_csv(oasis_bids_tsv_path, sep='\t')
    ↓
# Correlate with imaging
Combined analysis results
```

## 📝 Adding New Data

### **For Scientists:**

1. **Add new brain scans:**
   ```bash
   # Place in raw directory
   cp your_scan.nii.gz research/input/raw/
   
   # Upload to system
   python -m functions.upload_nifti research/input/raw/your_scan.nii.gz
   ```

2. **Add new clinical data:**
   ```bash
   # Create new lab directory
   mkdir research/input/tsv_files/lab_3/
   
   # Add your TSV files
   cp your_clinical_data.tsv research/input/tsv_files/lab_3/
   
   # Update options.py if needed, or use it directly:
   your_data_path = os.path.join(dataset_dir, 'tsv_files', 'lab_3', 'your_clinical_data.tsv')
   ```

3. **Add new atlases:**
   ```bash
   # Place in main input directory
   cp your_atlas.nii.gz research/input/
   
   # Update options.py
   your_atlas_path = os.path.join(dataset_dir, 'your_atlas.nii.gz')
   ```

4. **Handling user data:**

User-uploaded brain scans and results must **always** use Supabase helper functions - never direct file access.

### **Get User Data**
```python
from utilities.supabase_utilities import get_nifti_file, download_nifti_file

def my_function(nifti_file_id):
    # Get user's brain scan
    nifti_file_path = download_nifti_file(nifti_file_id)
    # Get ROI volumes for the NIFTI file
    roi_volumes = get_roi_volumes(nifti_file_id)
    
    # Load with nibabel
    import nibabel as nib
    user_scan = nib.load(nifti_file_path)
```

### **Save Results to Database**
```python
def my_analysis_function(nifti_file_id):
    # Get ROI volumes for the NIFTI file
    roi_volumes = get_roi_volumes(nifti_file_id)
    # Do your analysis
    result = calculate_something(nifti_file_path)
    
    # Save to database (ask admin to create table first)
    record = {
        "nifti_file_id": nifti_file_id,
        "result_value": result,
        "created_at": datetime.now().isoformat()
    }
    
    response = supabase.table("my_results_table").insert(record).execute()
    return response.data[0]
```

### **Request New Tables**
When you need to save new types of results, send this to admin:
```
Table: my_analysis_results
Columns:
- nifti_file_id (uuid, links to user's scan)
- result_value (float, your analysis result) 
- created_at (timestamp)
```

**Key rules:**
- Use `download_nifti_file(nifti_file_id)` for user data
- Save all results to database tables  
- Request table creation from admin with column specs

## 💡 Best Practices

1. **Keep raw data unchanged** - always work with copies
2. **Use configuration paths** - don't hardcode file paths
3. **Document new datasets** - update README files
4. **Organize by study/lab** - use subdirectories for different projects
5. **Version control metadata** - TSV files should be tracked in git
6. **Large files externally** - consider external storage for very large datasets

## 🔗 Integration with Functions

Functions access this data automatically:
- `upload_nifti()` - can use example files for testing
- `resample_atlas_for_user_nifti()` - uses `atlas_file_path`  
- `paper_1_oasis()` insight - uses `oasis_bids_tsv_path`
- `annot_to_json()` - processes files from `raw/` directory

This centralized approach ensures all functions and insights have consistent access to scientific datasets while maintaining clear organization. 