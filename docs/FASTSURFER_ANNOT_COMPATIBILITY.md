# FastSurfer Annotation File Compatibility

## Problem
The `generate_visualization_data.py` function was hardcoded to look for FreeSurfer-style annotation files (e.g., `lh.aparc.annot`), but FastSurfer uses different naming conventions for its output files.

## FastSurfer vs FreeSurfer Annotation Naming

### FreeSurfer Naming Convention
```
lh.aparc.annot
rh.aparc.annot
lh.aparc.a2009s.annot
rh.aparc.a2009s.annot
```

### FastSurfer Naming Convention
FastSurfer uses `.mapped.annot` and `.mapped.stats` suffixes with DKTatlas naming:

**Annotation files:**
```
lh.aparc.DKTatlas.mapped.annot  (instead of lh.aparc.annot)
rh.aparc.DKTatlas.mapped.annot  (instead of rh.aparc.annot)

# FastSurfer also creates symlinks:
lh.aparc.DKTatlas.annot -> lh.aparc.DKTatlas.mapped.annot
rh.aparc.DKTatlas.annot -> rh.aparc.DKTatlas.mapped.annot
```

**Statistics files:**
```
lh.aparc.DKTatlas.mapped.stats  (instead of lh.aparc.stats)
rh.aparc.DKTatlas.mapped.stats  (instead of rh.aparc.stats)
```

### FastSurfer Full Output (from full pipeline run)
```
# Standard parcellations
lh.aparc.DKTatlas.mapped.annot
rh.aparc.DKTatlas.mapped.annot

# Additional parcellations
lh.BA_exvivo.annot              (Brodmann areas)
rh.BA_exvivo.annot
lh.mpm.vpnl.annot               (Visual cortex parcellation)
rh.mpm.vpnl.annot

# Thresholded versions
lh.BA_exvivo.thresh.annot
rh.BA_exvivo.thresh.annot
```

## Solution Implemented

Updated `generate_visualization_data.py` to **try multiple filename patterns** when downloading annotation files:

### For `parcellation="aparc"`:
1. Try `lh.aparc.annot` (FreeSurfer standard)
2. Try `lh.aparc.DKTatlas.mapped.annot` (FastSurfer)
3. Try `lh.aparc.DKTatlas.annot` (FastSurfer symlink)

### For other parcellations:
1. Try `lh.{parcellation}.annot` (standard)
2. Try `lh.{parcellation}.mapped.annot` (FastSurfer variant)

### Fallback Logic
The function tries each pattern in order and uses the first one that exists. If none are found, it reports all attempted filenames in the error message.

## Code Changes

### Before (FreeSurfer-only):
```python
annot_filename = f"{hemi}.{parcellation}.annot"
storage_path = f"{nifti_file_id}/label/{annot_filename}"
response = supabase.storage.from_("freesurfer-outputs").download(storage_path)
```

### After (FreeSurfer + FastSurfer compatible):
```python
possible_filenames = []

if parcellation == "aparc":
    possible_filenames = [
        f"{hemi}.{parcellation}.annot",  # FreeSurfer
        f"{hemi}.aparc.DKTatlas.mapped.annot",  # FastSurfer
        f"{hemi}.aparc.DKTatlas.annot",  # FastSurfer symlink
    ]
else:
    possible_filenames = [
        f"{hemi}.{parcellation}.annot",  # Standard
        f"{hemi}.{parcellation}.mapped.annot",  # FastSurfer variant
    ]

for annot_filename in possible_filenames:
    try:
        storage_path = f"{nifti_file_id}/label/{annot_filename}"
        response = supabase.storage.from_("freesurfer-outputs").download(storage_path)
        # Success! Use this file
        break
    except:
        continue  # Try next pattern
```

## Usage Examples

### Generate visualization for FreeSurfer output:
```bash
python -m functions.generate_visualization_data FILE_ID --parcellation aparc
# Will find: lh.aparc.annot, rh.aparc.annot
```

### Generate visualization for FastSurfer output:
```bash
python -m functions.generate_visualization_data FILE_ID --parcellation aparc
# Will find: lh.aparc.DKTatlas.mapped.annot, rh.aparc.DKTatlas.mapped.annot
```

### Generate visualization for FastSurfer DKT parcellation:
```bash
python -m functions.generate_visualization_data FILE_ID --parcellation aparc.DKTatlas
# Will find: lh.aparc.DKTatlas.annot or lh.aparc.DKTatlas.mapped.annot
```

### Generate visualization for FastSurfer Brodmann areas:
```bash
python -m functions.generate_visualization_data FILE_ID --parcellation BA_exvivo
# Will find: lh.BA_exvivo.annot, rh.BA_exvivo.annot
```

### Generate visualization for visual cortex parcellation:
```bash
python -m functions.generate_visualization_data FILE_ID --parcellation mpm.vpnl
# Will find: lh.mpm.vpnl.annot, rh.mpm.vpnl.annot
```

## Available FastSurfer Parcellations

Based on the full FastSurfer output, these parcellations are available:

1. **aparc.DKTatlas** (default, Desikan-Killiany-Tourville atlas)
   - Use: `--parcellation aparc` (automatically tries DKTatlas variant)
   - Files: `lh.aparc.DKTatlas.mapped.annot`, `rh.aparc.DKTatlas.mapped.annot`

2. **BA_exvivo** (Brodmann areas)
   - Use: `--parcellation BA_exvivo`
   - Files: `lh.BA_exvivo.annot`, `rh.BA_exvivo.annot`

3. **mpm.vpnl** (Visual cortex parcellation)
   - Use: `--parcellation mpm.vpnl`
   - Files: `lh.mpm.vpnl.annot`, `rh.mpm.vpnl.annot`

## Backward Compatibility

The changes are **fully backward compatible**:
- FreeSurfer outputs continue to work (tries standard naming first)
- FastSurfer outputs now work (tries FastSurfer naming as fallback)
- Error messages improved to show all attempted filenames

## Testing

Test with FastSurfer output:
```bash
# After running FastSurfer and storing files
python -m functions.fastsurfer_store_files FILE_ID FASTSURFER_OUTPUT_DIR

# Generate visualization
python -m functions.generate_visualization_data FILE_ID --parcellation aparc
```

Expected output:
```
📥 Downloading annotation files from storage...
Trying to download: FILE_ID/label/lh.aparc.annot
Trying to download: FILE_ID/label/lh.aparc.DKTatlas.mapped.annot
✅ Downloaded lh.aparc.DKTatlas.mapped.annot
...
```

## Related Files

- **Modified:** `/Users/oytuntez/brainyes/engine/functions/generate_visualization_data.py`
  - Added fallback logic to try multiple annotation filename patterns
  - Now supports both FreeSurfer and FastSurfer naming conventions

- **Modified:** `/Users/oytuntez/brainyes/engine/functions/fastsurfer_store_files.py`
  - Added FastSurfer annotation files to essential_files list
  - Added FastSurfer stats files to essential_files list
  - Files now include both FreeSurfer and FastSurfer variants

- **Related:** `/Users/oytuntez/brainyes/engine/utilities/freesurfer_parsers.py`

## Notes

- FastSurfer's DKT atlas is slightly different from FreeSurfer's aparc atlas but largely compatible
- The `.mapped.annot` suffix indicates FastSurfer's deep learning-based segmentation
- Symlinks are created for compatibility but the actual files have `.mapped.annot` extension
- The annotation file format itself is identical (FreeSurfer-compatible), only naming differs
