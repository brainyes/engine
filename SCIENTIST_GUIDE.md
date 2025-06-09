# Cerebro Backend Guide for Scientists

This guide will help you use the Cerebro system to analyze NIFTI brain images. You don't need to be a programmer to use these tools - just follow the examples below.

## Prerequisites

1. **Python Environment**: Make sure you have Python installed and the virtual environment activated:
   ```bash
   source .venv/bin/activate  # On Mac/Linux
   # or
   .venv\Scripts\activate     # On Windows
   ```

2. **Working Directory**: Always run commands from the main project directory (where this guide is located), not from inside the `functions/` folder.

3. **Sample Data**: We've provided example NIFTI files in the `research/input/` directory that you can use to test the system. See `RESEARCH_DATA_GUIDE.md` for detailed information about available datasets and how to access them.

## Quick Start - Common Tasks

### 1. Upload a NIFTI File

This uploads your brain scan to the system and prepares it for analysis.

**Example:**
```bash
python -m functions.upload_nifti research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz
```

**With your own file:**
```bash
python -m functions.upload_nifti /path/to/your/brain_scan.nii.gz
```

**What it does:**
- Uploads both compressed (.nii.gz) and uncompressed (.nii) versions
- Creates a user account for your analysis session
- Returns file IDs that you'll use for further analysis

**Expected output:**
```
=== CEREBRO NIFTI UPLOAD ===
Uploading NIFTI file: your_file.nii.gz
...
📋 Main file ID: 97d321f3-405f-4a27-a96a-2b53e0f1c899
👤 User ID: b984c11c-11a9-4ed9-b82e-83c52fd5d0eb
```

**Important:** The script will show you the exact commands to run next with your file ID already filled in!

### 2. Resample Atlas for Your Brain Scan

This aligns the brain atlas with your specific brain scan so regions can be properly identified.

**Example:**
```bash
python -m functions.resample_atlas_for_user_nifti 97d321f3-405f-4a27-a96a-2b53e0f1c899
```

**What it does:**
- Takes the Harvard-Oxford brain atlas and reshapes it to match your brain scan
- Saves the resampled atlas for your scan
- Calculates voxel size information

**Note:** Use the file ID from step 1. The upload script will show you the exact command to copy and paste.

### 3. Calculate Brain Region Volumes

This calculates the volume of different brain regions in your scan.

**Example:**
```bash
python -m functions.calculate_roi_volumes 97d321f3-405f-4a27-a96a-2b53e0f1c899
```

**What it does:**
- Measures the volume of each brain region (ROI - Region of Interest)
- Stores the results in the database
- Returns volume measurements for each brain region

**Note:** Use the same file ID from step 1. The previous scripts will show you the exact command to run.

### 4. Convert Annotation Files

This converts FreeSurfer annotation files (.annot) to JSON format for visualization and analysis.

**Example:**
```bash
python -m functions.annot-to-json research/input/raw/lh.custom_regions_de_ki.annot
```

**With custom output:**
```bash
python -m functions.annot-to-json /path/to/your/file.annot --output /path/to/output.json
```

**What it does:**
- Converts FreeSurfer brain region annotations to JSON format
- Extracts vertex labels and region information
- Creates structured data for visualization tools
- Provides detailed processing statistics

**Note:** This is for surface-based analysis and works with FreeSurfer annotation files.

## Detailed Workflow

### Step-by-Step Analysis Process

1. **Upload your NIFTI file**
   ```bash
   python -m functions.upload_nifti /path/to/your/brain_scan.nii.gz
   ```
   → Copy the commands shown in the output for steps 2 and 3

2. **Resample the atlas** (use the command from step 1 output)
   ```bash
   python -m functions.resample_atlas_for_user_nifti YOUR_FILE_ID
   ```

3. **Calculate volumes** (use the command from step 2 output)
   ```bash
   python -m functions.calculate_roi_volumes YOUR_FILE_ID
   ```

### Command Line Help

Each script has built-in help. You can see usage instructions by adding `--help`:

```bash
python -m functions.upload_nifti --help
python -m functions.resample_atlas_for_user_nifti --help  
python -m functions.calculate_roi_volumes --help
```

## Understanding the Output

### Upload Results
- `id`: The unique identifier for your uploaded file (SAVE THIS!)
- `file_type`: Either 'nii' or 'nii.gz'
- `user_id`: Your temporary user ID in the system

### Volume Calculation Results
- Returns a list of brain regions with their calculated volumes
- Each region has a `label` (numerical ID) and `volume` (in cubic millimeters)

### Brain Region Labels
The system uses the Harvard-Oxford Cortical Structural Atlas. Common regions include:
- Label 1: Frontal Pole
- Label 2: Insular Cortex
- Label 3: Superior Frontal Gyrus
- (And many more...)

## Troubleshooting

### Common Issues

1. **Script doesn't exit**: This is normal - the script will finish and exit automatically.

2. **File not found**: Make sure your NIFTI file path is correct and the file exists.

3. **Permission errors**: Ensure you have read access to your NIFTI files.

4. **Missing dependencies**: Make sure you've activated the virtual environment.

### Getting Help

If you encounter errors:
1. Check that your NIFTI file is valid (can be opened with standard neuroimaging software)
2. Ensure file paths are correct
3. Make sure you're using the file IDs from previous steps correctly

## Example Files

The system includes example files in `research/input/`:
- `sub-OASIS10001_ses-M00_T1w.nii.gz`: Example brain scan
- `HarvardOxford-cort-maxprob-thr25-2mm.nii.gz`: Brain atlas

You can use these to test the system before analyzing your own data.

## Tips for Scientists

1. **Keep track of file IDs**: Write down or copy the file IDs from each step
2. **One scan at a time**: Process one brain scan completely before starting another
3. **Check file formats**: Ensure your NIFTI files are properly formatted (.nii or .nii.gz)
4. **Backup your data**: The system stores results in a database, but keep your original files safe

## Next Steps

After running these analyses, you'll have:
- Your brain scan uploaded and processed
- A customized brain atlas aligned to your scan
- Volume measurements for all brain regions

You can then use this data for your research, statistical analysis, or clinical applications. 