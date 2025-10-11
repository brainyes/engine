# Database Schema for Population Norms System

This document describes the database tables required for the population norms system.

## Overview

The population norms system requires two new tables:
1. **`population_scans`** - Tracks which scans are part of the population dataset
2. **`population_comparisons`** - Stores individual vs population comparison results

The existing **`normative_brain_data`** table is updated to include computed statistics.

## Table Schemas

### 1. `population_scans` Table

Stores metadata for each scan in the population dataset, linking it to the processed NIFTI file.

```sql
CREATE TABLE population_scans (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Link to processed NIFTI file
    nifti_file_id UUID NOT NULL UNIQUE,

    -- Dataset provenance
    dataset_source TEXT NOT NULL,  -- e.g., 'oasis-1', 'hcp-young-adult', 'openneuro-ds000114'
    subject_id TEXT NOT NULL,       -- Original subject ID from dataset

    -- Demographics
    age INTEGER,                    -- Age in years (nullable if unknown)
    sex TEXT CHECK (sex IN ('M', 'F', 'U')),  -- M=Male, F=Female, U=Unknown

    -- Clinical information
    diagnosis TEXT,                 -- Clinical diagnosis (nullable)
    scan_quality FLOAT,             -- Quality metric 0-1 (nullable)

    -- Processing metadata
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Foreign key constraint
    FOREIGN KEY (nifti_file_id) REFERENCES nifti_files(id) ON DELETE CASCADE
);

-- Indexes for efficient queries
CREATE INDEX idx_population_scans_dataset ON population_scans(dataset_source);
CREATE INDEX idx_population_scans_age_sex ON population_scans(age, sex);
CREATE INDEX idx_population_scans_age ON population_scans(age);
CREATE INDEX idx_population_scans_sex ON population_scans(sex);

-- Comments
COMMENT ON TABLE population_scans IS 'Metadata for scans used to build population norms';
COMMENT ON COLUMN population_scans.dataset_source IS 'Source dataset (oasis-1, hcp, etc.)';
COMMENT ON COLUMN population_scans.subject_id IS 'Original subject ID from source dataset';
COMMENT ON COLUMN population_scans.scan_quality IS 'Quality metric from 0 (poor) to 1 (excellent)';
```

### 2. Update `normative_brain_data` Table

The existing table is extended to include metadata about computed norms.

```sql
-- Add new columns to existing table
ALTER TABLE normative_brain_data ADD COLUMN IF NOT EXISTS sample_size INTEGER;
ALTER TABLE normative_brain_data ADD COLUMN IF NOT EXISTS dataset_sources TEXT[];
ALTER TABLE normative_brain_data ADD COLUMN IF NOT EXISTS computed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE normative_brain_data ADD COLUMN IF NOT EXISTS roi_label INTEGER;

-- Update existing structure_name to be nullable (we'll use roi_label for Harvard-Oxford)
ALTER TABLE normative_brain_data ALTER COLUMN structure_name DROP NOT NULL;

-- Comments
COMMENT ON COLUMN normative_brain_data.sample_size IS 'Number of subjects used to compute this norm';
COMMENT ON COLUMN normative_brain_data.dataset_sources IS 'Array of dataset names used (e.g., ["oasis-1", "hcp"])';
COMMENT ON COLUMN normative_brain_data.computed_at IS 'When these norms were computed';
COMMENT ON COLUMN normative_brain_data.roi_label IS 'Harvard-Oxford atlas label (0-48)';

-- Index for ROI lookups
CREATE INDEX IF NOT EXISTS idx_normative_brain_data_roi ON normative_brain_data(roi_label, age_min, age_max, sex);
```

### 3. `population_comparisons` Table

Stores results when comparing an individual scan to population norms.

```sql
CREATE TABLE population_comparisons (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Link to user's scan
    nifti_file_id UUID NOT NULL,

    -- ROI information
    roi_label INTEGER NOT NULL,      -- Harvard-Oxford atlas label
    roi_name TEXT,                    -- Human-readable ROI name

    -- User's measurement
    user_volume FLOAT NOT NULL,       -- Volume in mm³

    -- Population norms (from normative_brain_data)
    norm_mean FLOAT NOT NULL,
    norm_std FLOAT NOT NULL,
    norm_p10 FLOAT,
    norm_p25 FLOAT,
    norm_p50 FLOAT,
    norm_p75 FLOAT,
    norm_p90 FLOAT,

    -- Comparison statistics
    z_score FLOAT NOT NULL,           -- (user_volume - mean) / std
    percentile INTEGER,                -- Percentile rank (0-100)
    is_outlier BOOLEAN,                -- |z_score| > 2

    -- Metadata
    age_bin TEXT,                      -- Age bin used for comparison (e.g., '40-50')
    sex_used TEXT,                     -- Sex used for comparison ('M', 'F', 'U')
    sample_size INTEGER,               -- Population sample size

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Foreign key constraint
    FOREIGN KEY (nifti_file_id) REFERENCES nifti_files(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_population_comparisons_nifti ON population_comparisons(nifti_file_id);
CREATE INDEX idx_population_comparisons_outliers ON population_comparisons(is_outlier) WHERE is_outlier = TRUE;
CREATE INDEX idx_population_comparisons_created ON population_comparisons(created_at DESC);

-- Comments
COMMENT ON TABLE population_comparisons IS 'Results of comparing individual scans to population norms';
COMMENT ON COLUMN population_comparisons.z_score IS 'Standard deviations from population mean';
COMMENT ON COLUMN population_comparisons.percentile IS 'Percentile rank in population (0-100)';
COMMENT ON COLUMN population_comparisons.is_outlier IS 'True if |z_score| > 2 (outside 95% of population)';
```

## Sample Data

### `population_scans` Example
```sql
INSERT INTO population_scans (nifti_file_id, dataset_source, subject_id, age, sex) VALUES
  ('a1b2c3d4...', 'oasis-1', 'OAS1_0001', 45, 'M'),
  ('e5f6g7h8...', 'oasis-1', 'OAS1_0002', 52, 'F'),
  ('i9j0k1l2...', 'hcp-young-adult', 'HCP_100307', 28, 'M');
```

### `normative_brain_data` Example
```sql
INSERT INTO normative_brain_data (
    roi_label, age_min, age_max, sex, mean, std, p10, p25, p50, p75, p90,
    sample_size, dataset_sources, computed_at, unit, source
) VALUES (
    17,  -- Left Hippocampus
    40, 50, 'M',
    7600, 690,
    6750, 7100, 7600, 8100, 8450,
    150,  -- sample size
    ARRAY['oasis-1', 'oasis-3'],
    NOW(),
    'mm³',
    'Computed from OASIS datasets'
);
```

### `population_comparisons` Example
```sql
INSERT INTO population_comparisons (
    nifti_file_id, roi_label, roi_name,
    user_volume, norm_mean, norm_std,
    z_score, percentile, is_outlier,
    age_bin, sex_used, sample_size
) VALUES (
    'user-nifti-id',
    17, 'Left_Hippocampus',
    6500, 7600, 690,
    -1.59, 6, FALSE,  -- Slightly below average
    '40-50', 'M', 150
);
```

## SQL Migration Script

To create all tables and indexes:

```sql
-- Migration: Population Norms System
-- Date: 2025-10-10
-- Description: Creates tables for population normative data system

BEGIN;

-- 1. Create population_scans table
CREATE TABLE IF NOT EXISTS population_scans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nifti_file_id UUID NOT NULL UNIQUE,
    dataset_source TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    age INTEGER,
    sex TEXT CHECK (sex IN ('M', 'F', 'U')),
    diagnosis TEXT,
    scan_quality FLOAT,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (nifti_file_id) REFERENCES nifti_files(id) ON DELETE CASCADE
);

CREATE INDEX idx_population_scans_dataset ON population_scans(dataset_source);
CREATE INDEX idx_population_scans_age_sex ON population_scans(age, sex);
CREATE INDEX idx_population_scans_age ON population_scans(age);
CREATE INDEX idx_population_scans_sex ON population_scans(sex);

-- 2. Update normative_brain_data table
ALTER TABLE normative_brain_data ADD COLUMN IF NOT EXISTS sample_size INTEGER;
ALTER TABLE normative_brain_data ADD COLUMN IF NOT EXISTS dataset_sources TEXT[];
ALTER TABLE normative_brain_data ADD COLUMN IF NOT EXISTS computed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE normative_brain_data ADD COLUMN IF NOT EXISTS roi_label INTEGER;
ALTER TABLE normative_brain_data ALTER COLUMN structure_name DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_normative_brain_data_roi
    ON normative_brain_data(roi_label, age_min, age_max, sex);

-- 3. Create population_comparisons table
CREATE TABLE IF NOT EXISTS population_comparisons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nifti_file_id UUID NOT NULL,
    roi_label INTEGER NOT NULL,
    roi_name TEXT,
    user_volume FLOAT NOT NULL,
    norm_mean FLOAT NOT NULL,
    norm_std FLOAT NOT NULL,
    norm_p10 FLOAT,
    norm_p25 FLOAT,
    norm_p50 FLOAT,
    norm_p75 FLOAT,
    norm_p90 FLOAT,
    z_score FLOAT NOT NULL,
    percentile INTEGER,
    is_outlier BOOLEAN,
    age_bin TEXT,
    sex_used TEXT,
    sample_size INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (nifti_file_id) REFERENCES nifti_files(id) ON DELETE CASCADE
);

CREATE INDEX idx_population_comparisons_nifti ON population_comparisons(nifti_file_id);
CREATE INDEX idx_population_comparisons_outliers ON population_comparisons(is_outlier)
    WHERE is_outlier = TRUE;
CREATE INDEX idx_population_comparisons_created ON population_comparisons(created_at DESC);

COMMIT;
```

## Usage Queries

### Find all population scans from a specific dataset
```sql
SELECT ps.*, nf.id as nifti_id
FROM population_scans ps
JOIN nifti_files nf ON ps.nifti_file_id = nf.id
WHERE ps.dataset_source = 'oasis-1';
```

### Get population stats for age group and sex
```sql
SELECT roi_label, mean, std, p50, sample_size
FROM normative_brain_data
WHERE age_min <= 45 AND age_max >= 45
  AND sex = 'M';
```

### Find outlier ROIs for a user
```sql
SELECT roi_name, user_volume, norm_mean, z_score, percentile
FROM population_comparisons
WHERE nifti_file_id = 'user-scan-id'
  AND is_outlier = TRUE
ORDER BY ABS(z_score) DESC;
```

### Get age distribution of population scans
```sql
SELECT
    FLOOR(age / 10) * 10 as age_decade,
    COUNT(*) as scan_count,
    COUNT(CASE WHEN sex = 'M' THEN 1 END) as male_count,
    COUNT(CASE WHEN sex = 'F' THEN 1 END) as female_count
FROM population_scans
WHERE age IS NOT NULL
GROUP BY age_decade
ORDER BY age_decade;
```

## Row-Level Security (Optional)

If implementing RLS for multi-tenant usage:

```sql
-- Population scans are public (used for norms)
ALTER TABLE population_scans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Population scans are viewable by all" ON population_scans
    FOR SELECT USING (true);

CREATE POLICY "Only admins can insert population scans" ON population_scans
    FOR INSERT WITH CHECK (auth.jwt() ->> 'role' = 'admin');

-- Population comparisons are private to user
ALTER TABLE population_comparisons ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own comparisons" ON population_comparisons
    FOR SELECT USING (
        nifti_file_id IN (
            SELECT id FROM nifti_files WHERE user_id = auth.uid()
        )
    );
```

## Maintenance

### Clean up old comparisons
```sql
-- Delete comparisons older than 90 days
DELETE FROM population_comparisons
WHERE created_at < NOW() - INTERVAL '90 days';
```

### Recompute norms when new scans added
```sql
-- Mark norms as outdated (to be recomputed)
UPDATE normative_brain_data
SET computed_at = NULL
WHERE dataset_sources @> ARRAY['oasis-1'];
```

## Related Tables

- **`nifti_files`** - Stores uploaded NIFTI files (both population and user scans)
- **`roi_volumes`** - Stores calculated ROI volumes for each scan
- **`users`** - User accounts (population scans use special population user IDs)

## References

- Harvard-Oxford Atlas labels: See `utilities/volume_labels.py`
- ROI volume calculation: `functions/calculate_roi_volumes.py`
- Normative data generation: `functions/compute_population_norms.py`
