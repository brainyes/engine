# FreeSurfer/FastSurfer Function Consolidation

## Overview

As of 2025-11-15, we've consolidated the duplicate FreeSurfer and FastSurfer functions into universal functions that handle both processing methods automatically.

## Motivation

Previously, we had separate functions for FreeSurfer and FastSurfer:
- `freesurfer_store_files.py` + `fastsurfer_store_files.py`
- `freesurfer_parse_statistics.py` + `fastsurfer_parse_statistics.py`

This created ~50% code duplication since FreeSurfer and FastSurfer outputs are nearly identical, with only minor naming differences (e.g., `lh.aparc.annot` vs `lh.aparc.DKTatlas.mapped.annot`).

## Changes Made

### 1. Updated `freesurfer_store_files.py` (Universal)
**Now handles both FreeSurfer and FastSurfer outputs**

**Key improvements:**
- Includes both FreeSurfer and FastSurfer file patterns in `essential_files`
- Added `segmentation_only` storage mode (~30MB)
- Added FastSurfer-specific files:
  - `mri/aparc.DKTatlas+aseg.deep.mgz` (deep learning segmentation)
  - `label/*.aparc.DKTatlas.mapped.annot` (DKT atlas annotations)
  - `stats/*.aparc.DKTatlas.mapped.stats` (DKT atlas statistics)

**Usage:**
```bash
# Works with FreeSurfer output
python -m functions.freesurfer_store_files FILE_ID FREESURFER_DIR

# Works with FastSurfer output
python -m functions.freesurfer_store_files FILE_ID FASTSURFER_DIR

# Both use the same function!
```

### 2. Updated `freesurfer_parse_statistics.py` (Universal)
**Now handles both FreeSurfer and FastSurfer outputs with auto-detection**

**Key improvements:**
- **Auto-detection**: Automatically determines if output is from FreeSurfer or FastSurfer
- **Processing method tracking**: Stores `processing_method` field in database
  - `"freesurfer"` for traditional FreeSurfer
  - `"fastsurfer"` for deep learning FastSurfer
- **Backward compatible**: Accepts explicit `--processing-method` parameter

**Auto-detection logic:**
Checks for FastSurfer-specific indicators:
1. `stats/lh.aparc.DKTatlas.mapped.stats`
2. `stats/rh.aparc.DKTatlas.mapped.stats`
3. `mri/aparc.DKTatlas+aseg.deep.mgz`

If any exist → FastSurfer, else → FreeSurfer

**Usage:**
```bash
# Auto-detects FreeSurfer vs FastSurfer
python -m functions.freesurfer_parse_statistics FILE_ID OUTPUT_DIR

# Explicit method (optional)
python -m functions.freesurfer_parse_statistics FILE_ID OUTPUT_DIR --processing-method fastsurfer
```

### 3. Deprecated `fastsurfer_*.py` Files
**Converted to thin wrappers for backward compatibility**

Both `fastsurfer_store_files.py` and `fastsurfer_parse_statistics.py` are now thin wrappers that:
1. Show deprecation warning
2. Call the corresponding `freesurfer_*` function
3. Maintain full backward compatibility

**Example deprecation output:**
```
================================================================================
⚠️  DEPRECATION WARNING
================================================================================
This script is deprecated. Please use freesurfer_parse_statistics.py instead.
The freesurfer_parse_statistics() function now handles both FreeSurfer and FastSurfer.
Auto-detection of processing method is enabled.
================================================================================
```

## Database Schema Updates

The `processing_method` column was added to all FreeSurfer tables via migration:
- `freesurfer_global_measures`
- `freesurfer_cortical_regions`
- `freesurfer_subcortical_segmentations`
- `freesurfer_curvature_stats`
- `freesurfer_summary_stats`

**Migration**: `20251115000000_add_processing_method_to_freesurfer_tables.sql`

## File Naming Differences

### FreeSurfer
```
label/lh.aparc.annot
label/rh.aparc.annot
stats/lh.aparc.stats
stats/rh.aparc.stats
mri/aparc+aseg.mgz
```

### FastSurfer
```
label/lh.aparc.DKTatlas.mapped.annot  (with symlink lh.aparc.DKTatlas.annot)
label/rh.aparc.DKTatlas.mapped.annot
stats/lh.aparc.DKTatlas.mapped.stats
stats/rh.aparc.DKTatlas.mapped.stats
mri/aparc+aseg.mgz
mri/aparc.DKTatlas+aseg.deep.mgz  (FastSurfer-specific deep learning output)
```

## Migration Guide

### For Existing Code Using `fastsurfer_*` Functions

**No immediate action required!** The `fastsurfer_*` functions still work via thin wrappers.

**Recommended migration:**
```python
# OLD (deprecated, but still works)
from functions.fastsurfer_parse_statistics import fastsurfer_parse_statistics
result = fastsurfer_parse_statistics(file_id, output_dir)

# NEW (recommended)
from functions.freesurfer_parse_statistics import freesurfer_parse_statistics
result = freesurfer_parse_statistics(file_id, output_dir)  # Auto-detects FastSurfer!
```

### For CLI Scripts

**OLD:**
```bash
python -m functions.fastsurfer_parse_statistics FILE_ID OUTPUT_DIR
```

**NEW:**
```bash
python -m functions.freesurfer_parse_statistics FILE_ID OUTPUT_DIR
```

Both commands work, but the new one is preferred.

## Benefits of Consolidation

✅ **50% less code** to maintain
✅ **Single source of truth** for file handling
✅ **Easier to add features** (one place to update)
✅ **Backward compatible** (old code still works)
✅ **Auto-detection** (users don't need to think about it)
✅ **Better tracking** (processing_method in database)

## Testing

To verify the consolidation works:

```bash
# Test with FastSurfer output
FILE_ID=d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9
FASTSURFER_DIR=/path/to/___fastsurfer_output_full/sub-$FILE_ID

# Store files (universal function)
python -m functions.freesurfer_store_files $FILE_ID $FASTSURFER_DIR --storage-mode essential

# Parse statistics (auto-detects FastSurfer)
python -m functions.freesurfer_parse_statistics $FILE_ID $FASTSURFER_DIR

# Should output: "🔍 Auto-detected: FastSurfer output"
# Should output: "Processing method: fastsurfer"
```

## Files Modified

### Universal Functions (Main)
- **`functions/freesurfer_store_files.py`** - Now handles both FreeSurfer and FastSurfer
- **`functions/freesurfer_parse_statistics.py`** - Now handles both with auto-detection

### Deprecated Wrappers (Backward Compatibility)
- **`functions/fastsurfer_store_files.py`** - Thin wrapper, shows deprecation warning
- **`functions/fastsurfer_parse_statistics.py`** - Thin wrapper, shows deprecation warning

### Related Files
- **`functions/generate_visualization_data.py`** - Already handles both (fallback patterns)
- **`docs/FASTSURFER_ANNOT_COMPATIBILITY.md`** - Documentation on file naming differences

## Future Deprecation Timeline

1. **Now (2025-11-15)**: `fastsurfer_*` functions show deprecation warnings but work
2. **Future (TBD)**: Remove `fastsurfer_*` wrapper files entirely
3. **Users should migrate**: Update code to use `freesurfer_*` functions directly

## FAQ

**Q: Will my existing FastSurfer code break?**
A: No! The `fastsurfer_*` functions still work via thin wrappers. You'll just see a deprecation warning.

**Q: Do I need to specify --processing-method?**
A: No! The function auto-detects based on files present. But you can override if needed.

**Q: What if I have both FreeSurfer and FastSurfer outputs?**
A: Use the `freesurfer_*` functions for both. They handle either automatically.

**Q: Will this affect my database records?**
A: Records now include a `processing_method` field to distinguish FreeSurfer vs FastSurfer results.

**Q: Can I still use the old fastsurfer_* functions?**
A: Yes, but they're deprecated. Please migrate to `freesurfer_*` functions when convenient.

## Summary

The consolidation provides a cleaner, more maintainable codebase while preserving full backward compatibility. All existing code continues to work, with gentle deprecation warnings to guide migration to the unified functions.

Use `freesurfer_*` functions for all new code. They work seamlessly with both FreeSurfer and FastSurfer outputs.
