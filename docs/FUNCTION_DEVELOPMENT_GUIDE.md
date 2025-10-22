# Function Development Guide

This guide helps you create new processing functions for the neuroimaging pipeline.

## Quick Start

1. **Copy the template**:
   ```bash
   cp functions/template.py functions/your_function_name.py
   ```

2. **Follow the TODO checklist below**

3. **Test your function**:
   ```bash
   python -m functions.your_function_name FILE_ID
   ```

## TODO Checklist for New Functions

### ✅ **Step 1: Basic Setup**
- [ ] Replace `FUNCTION_NAME = "my_new_function"` with your function name
- [ ] Replace `def my_new_function(...)` with your function name
- [ ] Update the docstring with your function's purpose

### ✅ **Step 2: Function Logic**
Replace the section between `########## YOUR FUNCTION LOGIC STARTS ##########`:

**Common Patterns:**
```python
# Load NIFTI data
import nibabel as nib
nifti_img = nib.load(nifti_gz_path)
data = nifti_img.get_fdata()

# Your processing
result = your_algorithm(data)

# Save to database
record = {"nifti_file_id": nifti_file_id, "result": result}
response = supabase.table("your_table").insert(record).execute()
```

### ✅ **Step 3: Command Line Interface**
- [ ] Update `parser.add_argument` description
- [ ] Add any function-specific arguments you need
- [ ] Update the progress messages

### ✅ **Step 4: Test and Document**
- [ ] Test with a real file ID
- [ ] Add your function to the main pipeline if needed
- [ ] Document what your function does in the team wiki

## Function Types

### **Type 1: Data Processing**
Transforms NIFTI data into new NIFTI data
- Input: NIFTI file
- Output: New NIFTI file + database record
- Example: `smooth_nifti`, `normalize_intensity`

### **Type 2: Feature Extraction** 
Extracts numerical features from NIFTI data
- Input: NIFTI file  
- Output: Numbers/arrays + database record
- Example: `calculate_roi_volumes`, `extract_texture_features`

### **Type 3: Quality Assessment**
Analyzes data quality and generates reports
- Input: NIFTI file
- Output: Quality metrics + database record  
- Example: `motion_assessment`, `artifact_detection`

## Pipeline Integration

Your function can be called from other functions or via the web API for automated workflows. Functions can be orchestrated by calling them directly from other Python code or triggered via web API endpoints.

## Example Function Names

Good function names are clear and action-oriented:
- `calculate_cortical_thickness`
- `detect_brain_lesions` 
- `normalize_intensity_values`
- `extract_connectivity_features`
- `assess_image_quality`

## Common Imports

```python
import nibabel as nib          # NIFTI file handling
import numpy as np             # Numerical processing
import pandas as pd            # Data manipulation
import matplotlib.pyplot as plt # Visualization
from scipy import ndimage      # Image processing
from sklearn import metrics   # Machine learning metrics
```

## Testing Your Function

```bash
# Test with example file
python -m functions.your_function_name 97d321f3-405f-4a27-a96a-2b53e0f1c899

# Test with additional arguments
python -m functions.your_function_name 97d321f3-405f-4a27-a96a-2b53e0f1c899 --threshold 0.8

# Get help
python -m functions.your_function_name --help
```

## Tips

1. **Keep functions focused** - one function, one job
2. **Use clear variable names** - `cortical_thickness` not `ct`
3. **Add progress messages** - scientists like to see what's happening
4. **Handle errors gracefully** - wrap risky operations in try/catch
5. **Save intermediate results** - helps with debugging and pipeline recovery 