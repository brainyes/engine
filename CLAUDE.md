# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start the FastAPI server with Inngest orchestration
INNGEST_DEV=1 uvicorn server:app --reload

# Start the Inngest orchestrator (in separate terminal)
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest --no-discovery
```

### Python Environment
```bash
# Install dependencies
pip install -r requirements.txt

# Run individual functions directly
python -m functions.function_name FILE_ID

# Example function calls
python -m functions.upload_nifti path/to/file.nii.gz
python -m functions.calculate_roi_volumes FILE_ID
python -m functions.resample_atlas_for_user_nifti FILE_ID
```

### Testing Functions
```bash
# Test with example data
python -m functions.upload_nifti research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz
python -m functions.annot-to-json research/input/raw/lh.custom_regions_de_ki.annot

# Get help for any function
python -m functions.function_name --help
```

## Architecture Overview

### Core Components

**1. Function-Based Processing Pipeline**
- `functions/` - Individual neuroimaging processing functions
- Each function follows template pattern (`functions/template.py`)
- Functions can run standalone via CLI or through Inngest orchestration
- All functions use standardized utilities for database and file operations


**3. Data Management**
- `utilities/data.py` - Supabase database connection
- `utilities/supabase_utilities.py` - File upload/download helpers
- `research/input/` - Reference datasets and atlases
- Database stores processing results and metadata

**4. Neuroimaging Analysis**
- `insights/` - Research analysis and scientific insights
- `utilities/freesurfer_parsers.py` - FreeSurfer output parsing
- `utilities/volume_labels.py` - Brain region label mappings
- Harvard-Oxford atlas integration for ROI analysis

### Function Development Pattern

All processing functions follow this structure:
1. **Input validation** - Check file IDs and parameters
2. **Data loading** - Use `get_nifti_file()` and `download_nifti_file()`
3. **Processing logic** - Core neuroimaging analysis
4. **Database storage** - Save results to Supabase
5. **CLI interface** - Argparse for scientist-friendly command line
6. **Inngest integration** - Async wrapper for workflow automation

### Key Dependencies
- **FastAPI** - Web framework for API endpoints
- **Inngest** - Workflow orchestration and event handling
- **Supabase** - Database and file storage
- **nibabel** - NIFTI file handling
- **numpy/scipy** - Numerical processing for brain imaging
- **matplotlib/seaborn** - Visualization and plotting

### Data Flow
1. Scientists upload NIFTI files via `upload_nifti` function
2. Atlas resampling aligns reference brain regions to user data
3. ROI volume calculation extracts quantitative measurements
4. Results stored in database with file ID relationships
5. Insights and analysis functions process results for research

### File Organization
- `functions/` - Processing pipeline components
- `utilities/` - Shared database, file, and parsing utilities  
- `insights/` - Research analysis and scientific studies
- `research/` - Input datasets, processed data, and outputs
- `docs/` - User guides for scientists and developers

### Integration Points
- All functions use shared Supabase utilities for consistency
- Inngest events enable automated multi-step processing
- Template-based development ensures standardized function structure
- CLI interfaces allow scientists to run individual steps manually