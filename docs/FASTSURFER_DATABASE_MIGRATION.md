# FastSurfer Database Migration

## Problem
When running `fastsurfer_parse_statistics`, you encountered an error:
```
Warning: Failed to store global measure BrainSeg: {'message': "Could not find the 'processing_method' column of 'freesurfer_global_measures' in the schema cache", 'code': 'PGRST204', 'hint': None, 'details': None}
```

This occurs because the `fastsurfer_parse_statistics.py` function tries to insert a `processing_method` column to distinguish between FreeSurfer (traditional) and FastSurfer (deep learning) results, but the database tables don't have this column.

## Solution
A migration has been created to add the `processing_method` column to all FreeSurfer tables.

### Migration Details
**File:** `/Users/oytuntez/brainyes/app/supabase/migrations/20251115000000_add_processing_method_to_freesurfer_tables.sql`

**What it does:**
1. Adds `processing_method` column to 5 tables:
   - `freesurfer_global_measures`
   - `freesurfer_cortical_regions`
   - `freesurfer_subcortical_segmentations`
   - `freesurfer_curvature_stats`
   - `freesurfer_summary_stats`

2. Column specification:
   - Type: `TEXT`
   - Default: `'freesurfer'`
   - Constraint: `CHECK (processing_method IN ('freesurfer', 'fastsurfer'))`

3. Creates indexes on the new column for efficient filtering

4. Adds documentation comments explaining the column

### Schema Updates
The schema file has also been updated:
**File:** `/Users/oytuntez/brainyes/app/supabase/schemas/public/freesurfer_measurements.sql`

All 5 tables now include the `processing_method` column definition.

## How to Apply the Migration

### Option 1: Using Supabase CLI (Recommended)
```bash
cd /Users/oytuntez/brainyes/app
supabase db push
```

### Option 2: Manual SQL Execution
Run the migration file directly in your Supabase SQL editor or via psql:
```bash
psql -h your-supabase-host -U postgres -d postgres -f /Users/oytuntez/brainyes/app/supabase/migrations/20251115000000_add_processing_method_to_freesurfer_tables.sql
```

### Option 3: Supabase Dashboard
1. Go to your Supabase project dashboard
2. Navigate to SQL Editor
3. Copy and paste the contents of the migration file
4. Execute the SQL

## After Migration

Once the migration is applied, you can re-run the FastSurfer statistics parser:

```bash
python -m functions.fastsurfer_parse_statistics \
    d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9 \
    /Users/oytuntez/brainyes/engine/___fastsurfer_output_full/sub-d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9 \
    --subject-id sub-d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9
```

The parser will now successfully store all statistics with `processing_method='fastsurfer'`.

## Benefits

1. **Data Provenance**: You can now distinguish between results from traditional FreeSurfer vs. FastSurfer deep learning
2. **Comparison**: Enables future comparisons between FreeSurfer and FastSurfer results on the same scan
3. **Filtering**: Efficient queries to filter by processing method
4. **Backward Compatibility**: Default value 'freesurfer' ensures existing data continues to work

## Verification

After applying the migration, verify it worked:

```sql
-- Check that the column exists
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'freesurfer_global_measures'
AND column_name = 'processing_method';

-- Should return:
-- column_name        | data_type | column_default
-- -------------------|-----------|----------------
-- processing_method  | text      | 'freesurfer'::text
```

## Files Modified

1. **Migration (NEW):** `/Users/oytuntez/brainyes/app/supabase/migrations/20251115000000_add_processing_method_to_freesurfer_tables.sql`
2. **Schema (UPDATED):** `/Users/oytuntez/brainyes/app/supabase/schemas/public/freesurfer_measurements.sql`

## Next Steps

After running the migration:
1. Re-run `fastsurfer_parse_statistics` - it should now complete without errors
2. Verify data was stored correctly by querying the database
3. Continue with the next step: `fastsurfer_store_files` if needed
