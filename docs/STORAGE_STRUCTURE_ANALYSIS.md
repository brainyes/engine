# Storage Structure Analysis: nifti_gz_files Bucket

## 🚨 Current Situation (MESSY)

The `nifti_gz_files` bucket currently has **3 different directory patterns**:

### Pattern 1: User ID Directories (Raw Uploads)
```
{user_id}/{timestamp}.nii
{user_id}/{timestamp}.nii.gz
{user_id}/{timestamp}_from_dicom.nii
```

**Source**:
- `brainyes-app/app/api/v1/mri/route.ts:294` - User uploaded NIfTI
- `brainyes-engine/functions/upload_nifti.py:36` - User uploaded NIfTI
- `brainyes-engine/functions/dicom_to_nifti_converter.py:200` - DICOM converted to NIfTI

**Example**: `13c794ba-ad74-4dd6-af93-2a5496b71f0d/1749438481.717726.nii`

### Pattern 2: User ID + DICOM Subdirectories (DICOM Storage)
```
{user_id}/dicom/{series_id}/{filename}.dcm
```

**Source**:
- `brainyes-app/app/api/v1/mri/route.ts:192` - DICOM series upload

**Example**: `13c794ba.../dicom/cb5ff621-12f7-4b80-9d31-4ff96df99fa6/file001.dcm`

**⚠️ PROBLEM**: DICOM files are **NOT** NIfTI files - they shouldn't be in `nifti_gz_files` bucket!

### Pattern 3: NIfTI File ID Directories (Processed Files)
```
{nifti_file_id}/atlas-resampled.nii
{nifti_file_id}/surf/{freesurfer_files}
{nifti_file_id}/mri/{freesurfer_files}
{nifti_file_id}/stats/{freesurfer_files}
{nifti_file_id}/label/{freesurfer_files}
{nifti_file_id}/visualization/{viz_files}
```

**Source**:
- `brainyes-engine/utilities/supabase_utilities.py:71` - Resampled atlas
- `brainyes-engine/functions/freesurfer_store_files.py:119` - FreeSurfer outputs
- `brainyes-engine/functions/generate_surface_files.py:119` - Visualization files

**Example**: `44ae2d38-f83c-4893-9459-6c309c9838d0/atlas-resampled.nii`

---

## 📊 Storage Object Mapping

### Supabase Storage Objects Table
The `storage.objects` table tracks uploaded files with these fields:
- `id` (UUID) - Unique identifier for the file
- `bucket_id` - Which bucket (e.g., "nifti_gz_files")
- `name` - The path within the bucket
- `owner` - User who uploaded it

### nifti_files Database Table
```sql
CREATE TABLE nifti_files (
  id UUID PRIMARY KEY,              -- Matches storage.objects.id
  user_id UUID,
  file_type TEXT,                    -- 'nii' or 'nii.gz'
  parent_nifti_file_id UUID,        -- For .nii.gz linking to .nii
  created_at TIMESTAMP
);
```

**Key Insight**: `nifti_files.id` = `storage.objects.id`

This means the file location is determined by the storage object's `name` field, which uses the inconsistent patterns above.

---

## 🎯 What SHOULD Happen

### Ideal Structure

#### Bucket 1: `nifti_files` (Renamed from nifti_gz_files)
```
{nifti_file_id}/
  ├── source.nii                 # Original uploaded file
  ├── atlas-resampled.nii        # Resampled atlas
  ├── surf/                      # FreeSurfer surface files
  │   ├── lh.pial
  │   ├── rh.pial
  │   └── ...
  ├── mri/                       # FreeSurfer MRI files
  │   ├── brain.mgz
  │   └── ...
  ├── stats/                     # FreeSurfer statistics
  ├── label/                     # FreeSurfer labels
  └── visualization/             # Visualization outputs
      ├── lh.pial.json
      └── ...
```

**Benefits**:
- ✅ All files for ONE nifti scan in ONE directory
- ✅ Easy to download all outputs for a scan
- ✅ Easy to delete all data for a scan
- ✅ File relationships are hierarchical and intuitive

#### Bucket 2: `dicom_files` (NEW)
```
{user_id}/
  └── {series_id}/
      ├── file001.dcm
      ├── file002.dcm
      └── ...
```

**Benefits**:
- ✅ Separate DICOM raw data from processed NIfTI data
- ✅ Can delete DICOM files after conversion to save space
- ✅ Clear naming - this bucket contains DICOM files

---

## 🔧 Migration Plan

### Option A: Full Restructure (RECOMMENDED but HIGH EFFORT)

1. **Create new `dicom_files` bucket**
2. **Migrate DICOM files** from `nifti_gz_files/{user_id}/dicom/` to `dicom_files/{user_id}/{series_id}/`
3. **Restructure nifti_gz_files**:
   - Move `{user_id}/{timestamp}.nii` → `{nifti_file_id}/source.nii`
   - Keep `{nifti_file_id}/...` structure (already correct)
4. **Update all code** to use new paths
5. **Update storage policies** for new bucket

**Timeline**: 2-3 days of dev work + testing

### Option B: Hybrid Approach (MEDIUM EFFORT)

1. **Create new `dicom_files` bucket**
2. **Move future DICOM uploads** to new bucket (app code change only)
3. **Keep existing nifti_gz_files structure** as-is for backward compatibility
4. **Gradually migrate** old DICOM files during cleanup

**Timeline**: 1 day of dev work

### Option C: Document Only (LOW EFFORT, NOT RECOMMENDED)

1. **Document the current mess** (this file)
2. **Keep using current structure**
3. **Accept the confusion**

**Timeline**: Already done!

---

## 📝 Code Changes Required

### For Option A (Full Restructure)

**App Changes**:
```typescript
// brainyes-app/app/api/v1/mri/route.ts:192
// BEFORE
const storagePath = `${userId}/dicom/${seriesId}/${file.name}`
await supabase.storage.from('nifti_gz_files').upload(...)

// AFTER
const storagePath = `${userId}/${seriesId}/${file.name}`
await supabase.storage.from('dicom_files').upload(...)
```

```typescript
// brainyes-app/app/api/v1/mri/route.ts:294
// BEFORE
const storagePath = `${userId}/${timestamp}.nii`
await supabase.storage.from('nifti_gz_files').upload(...)

// AFTER
const storagePath = `${niftiFileId}/source.nii`
await supabase.storage.from('nifti_files').upload(...)
```

**Engine Changes**:
```python
# brainyes-engine/functions/dicom_to_nifti_converter.py:131
# BEFORE
dicom_path = f"{user_id}/dicom/{dicom_series_id}"
files_response = supabase.storage.from_('nifti_gz_files').list(dicom_path)

# AFTER
dicom_path = f"{user_id}/{dicom_series_id}"
files_response = supabase.storage.from_('dicom_files').list(dicom_path)
```

```python
# brainyes-engine/functions/dicom_to_nifti_converter.py:200
# BEFORE
storage_file_name = f"{user_id}/{timestamp}_from_dicom.nii"

# AFTER
storage_file_name = f"{nifti_file_id}/source.nii"
```

**Database Changes**:
```sql
-- Add storage policies for new bucket
CREATE POLICY "Users can upload their DICOM files"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (bucket_id = 'dicom_files' AND (storage.foldername(name))[1] = auth.uid()::text);

-- Rename bucket (via Supabase dashboard or migration)
UPDATE storage.buckets SET name = 'nifti_files' WHERE name = 'nifti_gz_files';
```

---

## 🤔 Recommendation

**Go with Option B (Hybrid Approach)**:

1. ✅ Fixes the most confusing part (DICOM files in wrong bucket)
2. ✅ No migration of existing data required
3. ✅ Future uploads are clean and organized
4. ✅ Can clean up old structure later
5. ✅ Minimal code changes (only app upload logic)

**Why not Option A?**
- Requires migrating existing data (complex, risky)
- Breaks existing file URLs/references
- Need to update all processing code
- Testing is extensive

**Implementation Steps for Option B:**
1. Create `dicom_files` bucket in Supabase
2. Update app code to upload DICOM to new bucket
3. Update `dicom_to_nifti_converter` to read from new bucket (with fallback to old)
4. Test with new uploads
5. Add cleanup script to move old DICOM files (run manually when ready)

---

## 📚 Related Files

- `brainyes-app/app/api/v1/mri/route.ts` - Handles all file uploads
- `brainyes-engine/functions/dicom_to_nifti_converter.py` - DICOM conversion
- `brainyes-engine/functions/upload_nifti.py` - NIfTI upload (legacy)
- `brainyes-engine/utilities/supabase_utilities.py` - Storage helpers
- `brainyes-app/supabase/migrations/20251003100000_add_nifti_gz_files_storage_policies.sql` - Storage policies