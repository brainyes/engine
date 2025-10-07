# BrainYes Engine Tests

Simple test suite for verifying function integrity after code changes.

## Quick Start

```bash
# Run quick tests (recommended for development)
python tests/test_functions.py

# Run all tests including slow ones
python tests/test_functions.py --full

# Test a specific function
python tests/test_functions.py --function calculate_roi_volumes

# Show detailed error messages
python tests/test_functions.py --verbose
```

## Test Data

The test suite uses pre-existing data in the Supabase database:

- **NIFTI File ID**: `d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9`
- **DICOM Series ID**: `cb5ff621-12f7-4b80-9d31-4ff96df99fa6`

These IDs are already created and available for testing.

## Test Modes

### Quick Mode (Default)

Runs fast tests that complete in seconds to minutes:
- ✅ `dicom_to_nifti_converter` - Convert DICOM to NIfTI
- ✅ `resample_atlas_for_user_nifti` - Atlas resampling
- ✅ `calculate_roi_volumes` - Brain region volume calculations
- ✅ `calculate_memory_metrics` - Memory-related metrics

### Full Mode (`--full`)

Includes slow tests that may take hours:
- ⏱️ `freesurfer_recon_all` - Full FreeSurfer processing (hours)

### Skipped Tests

Some tests are skipped because they require additional setup:
- ⏭️ `freesurfer_parse_statistics` - Requires FreeSurfer output directory
- ⏭️ `freesurfer_store_files` - Requires FreeSurfer output directory
- ⏭️ `generate_surface_files` - Requires FreeSurfer output
- ⏭️ `generate_visualization_data` - Requires FreeSurfer output

## Adding New Tests

Edit `tests/test_functions.py` and add a new `FunctionTest` to the `FUNCTION_TESTS` list:

```python
FunctionTest(
    name="my_new_function",
    module_path="functions.my_new_function",
    function_name="my_new_function",
    args=[TEST_NIFTI_ID],  # Use TEST_DICOM_SERIES_ID for DICOM functions
    kwargs={},  # Optional keyword arguments
    slow=False,  # Set True if function takes >5 minutes
    skip=False,  # Set True to skip by default
    skip_reason=""  # Reason for skipping
),
```

## CI/CD Integration

To integrate with CI/CD pipelines:

```bash
# Exit with non-zero code if any test fails
python tests/test_functions.py || exit 1
```

## Examples

```bash
# Before deploying changes
python tests/test_functions.py

# Testing specific functionality after changes to ROI volume code
python tests/test_functions.py --function calculate_roi_volumes -v

# Full validation before major release
python tests/test_functions.py --full
```

## Expected Output

```
======================================================================
BRAINYES-ENGINE FUNCTION TESTS
======================================================================
Mode: QUICK
Test data: NIFTI ID=d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9, DICOM ID=cb5ff621-12f7-4b80-9d31-4ff96df99fa6
Tests to run: 4
Tests to skip: 6
======================================================================

[1/10] 🧪 Testing dicom_to_nifti_converter... ✅ PASS
[2/10] 🧪 Testing resample_atlas_for_user_nifti... ✅ PASS
[3/10] 🧪 Testing calculate_roi_volumes... ✅ PASS
[4/10] 🧪 Testing calculate_memory_metrics... ✅ PASS
[5/10] ⏭️  Skipping freesurfer_recon_all...
...

======================================================================
TEST RESULTS
======================================================================

✅ PASSED (4):
   • dicom_to_nifti_converter
   • resample_atlas_for_user_nifti
   • calculate_roi_volumes
   • calculate_memory_metrics

⏭️  SKIPPED (6):
   • freesurfer_recon_all - Slow test - use --full to run
   ...

======================================================================
Total: 10 | Passed: 4 | Failed: 0 | Skipped: 6
======================================================================
```