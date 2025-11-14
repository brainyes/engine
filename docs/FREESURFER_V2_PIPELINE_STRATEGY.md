# FreeSurfer vs V2 Pipeline Strategy

**Last Updated**: 2025-11-11
**Status**: Planning Document

## Executive Summary

The v2 registration-based pipeline (preprocess → register → resample → calculate) can handle region volume calculations for any atlas **without FreeSurfer**. However, FreeSurfer provides unique cortical surface analysis capabilities that cannot be replicated with volume-based methods.

**Recommendation**: Implement a two-tier processing system where v2 pipeline is the fast default, and FreeSurfer is an optional enhancement for surface analysis.

---

## TL;DR: What You Need FreeSurfer For

### FreeSurfer is REQUIRED for:
1. **3D Brain Surface Visualization** - Brain gallery, 3D explorer
2. **Cortical Thickness Measurements** - Clinical biomarkers
3. **Surface-Based Parcellations** - Cortical region mapping
4. **Curvature Analysis** - Brain folding metrics

### v2 Pipeline Provides:
- ✅ Volume measurements (all atlases)
- ✅ Population comparisons
- ✅ Accurate registration-based analysis
- ✅ Fast processing (10-20 mins vs 8 hours)

---

## Dashboard Pages Dependency Matrix

| Page | Requires FreeSurfer | Can Use V2 | Notes |
|------|-------------------|-----------|-------|
| ROI Volumes | ❌ No | ✅ Yes | Uses `roi_volumes` table |
| Population Norms | ❌ No | ✅ Yes | Uses `roi_volumes` + comparisons |
| Memory Analysis | ⚠️ Partial | ✅ Yes | Can migrate to `roi_volumes` |
| Global Measures | ⚠️ Partial | ✅ Yes | V2 computes ICV, can add others |
| Summary/Story | ⚠️ Partial | ✅ Yes | Needs migration to v2 metrics |
| **Cortical Regions** | ✅ **YES** | ❌ No | Thickness, curvature are surface-only |
| **Curvature Stats** | ✅ **YES** | ❌ No | Surface curvature analysis |
| **3D Brain Gallery** | ✅ **YES** | ⚠️ Partial | Surface rendering needs FreeSurfer |
| **3D Explorer** | ✅ **YES** | ⚠️ Partial | Volume viz available, surface needs FS |

---

## FreeSurfer Dependencies Detailed

### Engine Functions

#### Core FreeSurfer Processing (Cannot Replace)
1. **freesurfer_recon_all.py** - Runs 8-hour `recon-all` pipeline
   - Creates surface meshes, thickness maps, parcellations
   - Required for: All surface analysis

2. **freesurfer_store_files.py** - Stores ~50-230MB of FreeSurfer outputs
   - Essential mode: ~50MB (key files only)
   - Complete mode: ~230MB (full output)

3. **generate_surface_files.py** - Uses `mris_convert` to create `.asc` files
   - Converts FreeSurfer binary surfaces to web-friendly format
   - Required for: 3D brain visualization

4. **freesurfer_parse_statistics.py** - Parses `.stats` files into database
   - Populates 5 FreeSurfer-specific database tables
   - Required for: Cortical regions, curvature pages

#### Visualization (FreeSurfer-Dependent)
5. **generate_visualization_data.py** - Converts `.annot` files to JSON
   - Surface-based region definitions
   - Required for: Colored region display on 3D surfaces

#### Can Be Migrated to V2
6. **prepare_visualization_nifti.py** - Currently uses `brain.mgz`
   - Should use v2 preprocessed brain instead

7. **calculate_memory_metrics.py** - Uses FreeSurfer tables
   - Should migrate to use `roi_volumes` table

8. **compare_to_population_norms.py** - Uses `freesurfer_global_measures`
   - Should add v2 global measures computation

---

### Database Tables

#### FreeSurfer-Exclusive (5 tables)
1. **freesurfer_global_measures** - Brain-wide volumes from `aseg.stats`
2. **freesurfer_cortical_regions** - Surface area, thickness, curvature from `lh.aparc.stats`
3. **freesurfer_subcortical_segmentations** - Subcortical volumes from `aseg.stats`
4. **freesurfer_curvature_stats** - Hemisphere curvature from `lh.curv.stats`
5. **freesurfer_summary_stats** - Quick-access summaries

#### V2-Compatible (1 table)
- **roi_volumes** - Used by both pipelines
  - Has `atlas_name` field to distinguish sources
  - Has `processing_version` field ('v1_geometric' vs 'v2_registered')

---

### Storage Structure

**freesurfer-outputs** bucket:
```
{nifti_file_id}/
├── mri/
│   ├── brain.mgz           [Used by calculate_roi_volumes]
│   ├── aparc+aseg.mgz      [Used by resample_atlas_for_user_nifti]
│   └── transforms/
│       └── talairach.xfm   [Used by prepare_visualization_nifti]
├── surf/
│   ├── lh.pial, rh.pial    [Used by generate_surface_files]
│   ├── lh.white, rh.white
│   └── lh.thickness, rh.thickness
├── label/
│   ├── lh.aparc.annot      [Used by generate_visualization_data]
│   └── rh.aparc.annot
├── stats/
│   ├── aseg.stats          [Parsed by freesurfer_parse_statistics]
│   ├── lh.aparc.stats
│   ├── rh.aparc.stats
│   └── lh.curv.stats, rh.curv.stats
└── visualization/
    ├── lh.asc, rh.asc      [Used by frontend 3D viewer]
    └── lh.aparc.regions.json, rh.aparc.regions.json
```

---

## Two-Tier Processing Strategy (RECOMMENDED)

### Tier 1: Fast Track (v2 only) - 10-20 minutes

**Pipeline**:
```bash
preprocess_native_scan          # N4 + skull-strip + ICV (5 mins)
register_to_template            # ANTs registration (5 mins)
resample_atlas_for_user_nifti   # MNI atlases only (2 mins)
calculate_roi_volumes           # All MNI atlases (5 mins)
compare_to_population_norms     # Population analysis (1 min)
```

**Provides**:
- ✅ ROI volumes for all MNI atlases (harvard-oxford, hcpex)
- ✅ Population norm comparisons
- ✅ Memory metrics (from volumes)
- ✅ Global measures (ICV, brain volume)
- ✅ NiiVue 2D/3D volume visualization

**Dashboard Pages Available**:
- ROI Volumes
- Population Norms
- Memory Analysis
- Global Measures
- Summary/Story (with v2 metrics)

**Cost**: ~$0.10-0.20 per scan (Fargate)
**Storage**: ~50 MB (preprocessed brain + atlases)
**Value**: 80% of clinical value

---

### Tier 2: Complete Analysis (v2 + FreeSurfer) - 8+ hours (Optional)

**Additional Pipeline**:
```bash
freesurfer_recon_all           # Full FreeSurfer pipeline (8 hrs)
freesurfer_store_files         # Store outputs (2 mins)
generate_surface_files         # Create .asc meshes (5 mins)
freesurfer_parse_statistics    # Parse stats to DB (2 mins)
generate_visualization_data    # Create region JSONs (2 mins)
```

**Adds**:
- ✅ 3D cortical surface visualization
- ✅ Cortical thickness measurements
- ✅ Surface-based parcellations
- ✅ Curvature and folding analysis
- ✅ FreeSurfer-validated metrics

**Additional Dashboard Pages**:
- 3D Brain Gallery
- Cortical Regions
- Curvature Statistics
- Enhanced visualizations

**Additional Cost**: ~$5-10 per scan (Fargate with 16 vCPU)
**Additional Storage**: ~230 MB (FreeSurfer outputs)
**Value**: 100% comprehensive analysis

---

## Implementation Plan

### Phase 1: Database Schema Updates

#### Add Processing Flags
```sql
ALTER TABLE nifti_files
ADD COLUMN v2_processed BOOLEAN DEFAULT FALSE,
ADD COLUMN v2_processed_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN freesurfer_processed BOOLEAN DEFAULT FALSE,
ADD COLUMN freesurfer_processed_at TIMESTAMP WITH TIME ZONE;
```

#### Create Global Measures Table
```sql
CREATE TABLE scan_global_measures (
  id BIGSERIAL PRIMARY KEY,
  nifti_file_id UUID REFERENCES nifti_files(id) ON DELETE CASCADE,
  source TEXT NOT NULL, -- 'v2_preprocessing' or 'freesurfer'
  brain_volume_mm3 DOUBLE PRECISION,
  icv_mm3 DOUBLE PRECISION,
  gray_matter_estimate_mm3 DOUBLE PRECISION,
  white_matter_estimate_mm3 DOUBLE PRECISION,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(nifti_file_id, source)
);
```

---

### Phase 2: Engine Function Updates

#### 1. Update preprocess_native_scan.py
```python
# ADD: Store global measures during preprocessing
def store_global_measures(nifti_file_id, brain_img, icv_mm3):
    global_measures = {
        'brain_volume_mm3': compute_brain_volume(brain_img),
        'icv_mm3': icv_mm3,
        'gray_matter_estimate_mm3': estimate_gray_matter(brain_img),
        'white_matter_estimate_mm3': estimate_white_matter(brain_img)
    }

    supabase.table('scan_global_measures').upsert({
        'nifti_file_id': nifti_file_id,
        'source': 'v2_preprocessing',
        **global_measures
    }).execute()

    # Update processing flag
    supabase.table('nifti_files').update({
        'v2_processed': True,
        'v2_processed_at': 'now()'
    }).eq('id', nifti_file_id).execute()
```

#### 2. Update calculate_memory_metrics.py
```python
# CHANGE: Use roi_volumes instead of freesurfer_* tables
def get_hippocampus_volume(nifti_file_id, hemisphere):
    # Try v2 roi_volumes first
    result = supabase.table('roi_volumes')\
        .eq('nifti_file_id', nifti_file_id)\
        .eq('atlas_name', 'harvard-oxford')\
        .eq('label', HIPPOCAMPUS_LABEL[hemisphere])\
        .single().execute()

    if result.data:
        return result.data['volume']

    # Fallback to FreeSurfer
    result = supabase.table('freesurfer_subcortical_segmentations')\
        .eq('nifti_file_id', nifti_file_id)\
        .eq('structure_name', f'{hemisphere}-Hippocampus')\
        .single().execute()

    return result.data['volume'] if result.data else None
```

#### 3. Update compare_to_population_norms.py
```python
# CHANGE: Try v2 measures first, fall back to FreeSurfer
def get_global_measures(nifti_file_id):
    # Try v2 measures
    v2_measures = supabase.table('scan_global_measures')\
        .eq('source', 'v2_preprocessing')\
        .eq('nifti_file_id', nifti_file_id)\
        .single().execute()

    if v2_measures.data:
        return v2_measures.data

    # Fall back to FreeSurfer
    fs_measures = supabase.table('freesurfer_global_measures')\
        .eq('nifti_file_id', nifti_file_id)\
        .single().execute()

    return fs_measures.data
```

#### 4. Update calculate_roi_volumes.py
```python
# CHANGE: Prefer v2 preprocessed brain over FreeSurfer brain.mgz
def get_brain_image(nifti_file_id):
    # Try v2 preprocessed brain (preferred)
    scan = supabase.table('population_scans')\
        .select('preprocessed_brain_path')\
        .eq('nifti_file_id', nifti_file_id)\
        .single().execute()

    if scan.data and scan.data.get('preprocessed_brain_path'):
        path = download_from_storage(scan.data['preprocessed_brain_path'])
        return path, "v2_preprocessed"

    # Fall back to FreeSurfer brain.mgz
    try:
        brain_mgz_data = supabase.storage\
            .from_("freesurfer-outputs")\
            .download(f"{nifti_file_id}/mri/brain.mgz")
        path = save_temp_file(brain_mgz_data)
        return path, "freesurfer_brain.mgz"
    except:
        # Final fallback to user's original upload
        return download_user_nifti(nifti_file_id), "user_upload"
```

---

### Phase 3: Frontend Updates

#### 1. Update Scan Card Component
```typescript
// app/dashboard/scans/scan-card.tsx
export function ScanCard({ scan }) {
  return (
    <Card>
      {/* ... existing content ... */}

      {/* Processing Status */}
      <div className="flex gap-2 items-center">
        {scan.v2_processed ? (
          <>
            <Badge variant="success">Fast Analysis Complete</Badge>

            {scan.freesurfer_processed ? (
              <Badge variant="success">Surface Analysis Complete</Badge>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={() => triggerFreeSurfer(scan.id)}
              >
                Add Surface Analysis (+8 hours)
              </Button>
            )}
          </>
        ) : (
          <Badge variant="secondary">Processing...</Badge>
        )}
      </div>
    </Card>
  )
}
```

#### 2. Add Conditional Rendering to FreeSurfer Pages
```typescript
// app/dashboard/results/cortical-regions/page.tsx
export default function CorticalRegionsPage({ searchParams }) {
  const { scan } = useSelectedScan()

  if (!scan.freesurfer_processed) {
    return (
      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          <div className="space-y-2">
            <p>
              Cortical thickness and curvature analysis requires FreeSurfer
              surface processing.
            </p>
            <Button onClick={() => triggerFreeSurfer(scan.id)}>
              Enable Surface Analysis (+8 hours, +$5)
            </Button>
          </div>
        </AlertDescription>
      </Alert>
    )
  }

  // ... existing page content ...
}
```

#### 3. Update Navigation to Show Available Pages
```typescript
// app/dashboard/components/results-navigation.tsx
const resultsPages = [
  { name: 'Summary', path: '/summary', requiresFreeSurfer: false },
  { name: 'ROI Volumes', path: '/roi-volumes', requiresFreeSurfer: false },
  { name: 'Population Norms', path: '/population-norms', requiresFreeSurfer: false },
  { name: 'Memory', path: '/memory', requiresFreeSurfer: false },
  { name: 'Global Measures', path: '/global-measures', requiresFreeSurfer: false },
  { name: 'Cortical Regions', path: '/cortical-regions', requiresFreeSurfer: true },
  { name: 'Curvature', path: '/curvature', requiresFreeSurfer: true },
  { name: '3D Brain', path: '/brain-gallery', requiresFreeSurfer: true },
]

export function ResultsNavigation({ scan }) {
  return (
    <nav>
      {resultsPages.map(page => {
        const isDisabled = page.requiresFreeSurfer && !scan.freesurfer_processed

        return (
          <Link
            key={page.path}
            href={`${page.path}?scan=${scan.id}`}
            className={isDisabled ? 'opacity-50 cursor-not-allowed' : ''}
            onClick={(e) => isDisabled && e.preventDefault()}
          >
            {page.name}
            {isDisabled && <Lock className="h-3 w-3 ml-1" />}
          </Link>
        )
      })}
    </nav>
  )
}
```

---

### Phase 4: API Updates

#### 1. Add FreeSurfer Trigger Endpoint
```typescript
// app/api/v1/scans/[scanId]/trigger-freesurfer/route.ts
export async function POST(
  request: NextRequest,
  { params }: { params: { scanId: string } }
) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // Verify scan ownership and v2 processing complete
  const { data: scan } = await supabase
    .from('nifti_files')
    .select('*')
    .eq('id', params.scanId)
    .eq('user_id', user.id)
    .single()

  if (!scan) {
    return NextResponse.json({ error: 'Scan not found' }, { status: 404 })
  }

  if (!scan.v2_processed) {
    return NextResponse.json(
      { error: 'Basic processing must complete first' },
      { status: 400 }
    )
  }

  if (scan.freesurfer_processed) {
    return NextResponse.json(
      { message: 'FreeSurfer processing already complete' },
      { status: 200 }
    )
  }

  // Trigger FreeSurfer pipeline via Lambda/ECS
  const lambdaApiUrl = process.env.LAMBDA_API_URL
  const response = await fetch(`${lambdaApiUrl}/async/freesurfer_recon_all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      parameters: { nifti_file_id: params.scanId }
    })
  })

  if (!response.ok) {
    return NextResponse.json(
      { error: 'Failed to trigger FreeSurfer processing' },
      { status: 500 }
    )
  }

  return NextResponse.json({
    success: true,
    message: 'FreeSurfer processing started. This will take 8-10 hours.',
    estimated_completion: new Date(Date.now() + 8 * 60 * 60 * 1000)
  })
}
```

---

### Phase 5: Infrastructure Updates

#### 1. Consider Separate Docker Images
```yaml
# template-docker.yaml
Resources:
  # Fast v2-only container (no FreeSurfer)
  FastProcessingTaskDefinition:
    Type: AWS::ECS::TaskDefinition
    Properties:
      ContainerDefinitions:
        - Image: !Ref V2OnlyECRImage  # Smaller image without FreeSurfer
          Cpu: 4096
          Memory: 8192

  # Complete analysis container (with FreeSurfer)
  CompleteAnalysisTaskDefinition:
    Type: AWS::ECS::TaskDefinition
    Properties:
      ContainerDefinitions:
        - Image: !Ref CompleteECRImage  # Full image with FreeSurfer
          Cpu: 16384
          Memory: 32768
```

#### 2. Update Dockerfile Strategy
```dockerfile
# Dockerfile.v2 (lightweight - no FreeSurfer)
FROM ubuntu:24.04
# ... only v2 pipeline dependencies ...
# Size: ~2GB

# Dockerfile.complete (with FreeSurfer)
FROM ubuntu:24.04
# ... v2 dependencies + FreeSurfer 8.1.0 ...
# Size: ~4GB
```

---

## Cost/Benefit Analysis

| Metric | v2 Only | v2 + FreeSurfer |
|--------|---------|-----------------|
| Processing Time | 10-20 minutes | 8-10 hours |
| Compute Cost | $0.10-0.20 | $5-10 |
| Storage | ~50 MB | ~280 MB |
| Clinical Value | 80% | 100% |
| Use Cases | Volume analysis, population norms | + Surface analysis, thickness |

---

## User Segments & Recommendations

### Consumer Users (Most Common)
**Recommendation**: v2 only by default
**Rationale**: Fast results, affordable, covers most needs
**FreeSurfer Option**: Opt-in if they want detailed visualization

### Researchers
**Recommendation**: v2 + FreeSurfer optional
**Rationale**: May need comprehensive analysis for publications
**Pricing**: Offer discounts for batch processing

### Clinical Users
**Recommendation**: Case-by-case
**Rationale**: Cortical thickness important for diagnosis
**Consideration**: May need to make FreeSurfer standard for clinical tier

---

## Migration Checklist

### Database
- [ ] Add `v2_processed` and `freesurfer_processed` flags to `nifti_files`
- [ ] Create `scan_global_measures` table for v2 global metrics
- [ ] Add indexes for performance

### Engine Functions
- [ ] Update `preprocess_native_scan` to store global measures and set v2_processed flag
- [ ] Update `calculate_memory_metrics` to prefer `roi_volumes` over FreeSurfer tables
- [ ] Update `compare_to_population_norms` to use v2 global measures
- [ ] Update `calculate_roi_volumes` to prefer v2 preprocessed brain
- [ ] Add `freesurfer_processed` flag setting to `freesurfer_recon_all`

### Frontend
- [ ] Add processing status badges to scan cards
- [ ] Add "Enable FreeSurfer" button
- [ ] Add conditional rendering to cortical-regions page
- [ ] Add conditional rendering to curvature page
- [ ] Add conditional rendering to 3D brain pages
- [ ] Update navigation to show locked/unlocked state
- [ ] Add FreeSurfer trigger API endpoint

### Infrastructure
- [ ] Consider creating separate Docker images (v2-only vs complete)
- [ ] Update ECS task definitions for different processing tiers
- [ ] Add cost tracking for FreeSurfer vs v2 processing

### Documentation
- [ ] Update user documentation explaining two-tier system
- [ ] Add pricing page explaining tier differences
- [ ] Update developer docs with new architecture
- [ ] Create migration guide for existing scans

### Testing
- [ ] Test v2-only pipeline end-to-end
- [ ] Test v2 + FreeSurfer pipeline
- [ ] Test conditional page rendering
- [ ] Test FreeSurfer trigger flow
- [ ] Load test cost implications

---

## Open Questions

1. **Pricing Model**: Should FreeSurfer be pay-per-use or subscription?
2. **Existing Scans**: How to handle scans that only have FreeSurfer data (no v2)?
3. **Priority Queue**: Should FreeSurfer processing have lower priority?
4. **Notification**: How to notify users when FreeSurfer completes (8 hours later)?
5. **Cancellation**: Should users be able to cancel FreeSurfer mid-processing?
6. **Refunds**: Refund policy if FreeSurfer fails after payment?

---

## Success Metrics

- **Processing Time P50**: < 15 minutes for v2 pipeline
- **User Adoption**: > 80% of users satisfied with v2-only results
- **FreeSurfer Opt-in Rate**: Target 20-30% of users upgrade
- **Cost per Scan**: Reduce average cost from $5-10 to $0.50-2.00
- **User Satisfaction**: Measure via survey after results delivery

---

## References

- v2 Pipeline Documentation: `docs/POPULATION_NORMS_GUIDE.md`
- FreeSurfer Integration: `functions/freesurfer_recon_all.py`
- Database Schema: `app/supabase/migrations/`
- Original Analysis Report: See agent task output 2025-11-11