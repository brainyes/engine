# FreeSurfer Output Analysis & Storage Strategy

## Overview
Complete analysis of FreeSurfer `recon-all` pipeline outputs based on experiment: `sub-OASIS10001`

**Total Output Size:** ~230MB per subject  
**Total Files:** 336 files across 8 directories  
**Processing Time:** 6+ hours  

---

## 📊 Statistics Files (19 total)

### Core Volume/Segmentation Statistics
- **`aseg.stats`** - Subcortical segmentation volumes (hippocampus, amygdala, thalamus, etc.)
- **`brainvol.stats`** - Global brain volume measures (total brain, cortex, white matter)
- **`wmparc.stats`** - White matter parcellation statistics

### Cortical Parcellation Statistics (Per Hemisphere)
- **`lh/rh.aparc.stats`** - Desikan-Killiany atlas (34 regions per hemisphere)
- **`lh/rh.aparc.DKTatlas.stats`** - DKT atlas (31 regions per hemisphere)  
- **`lh/rh.aparc.a2009s.stats`** - Destrieux atlas (74 regions per hemisphere)
- **`lh/rh.aparc.pial.stats`** - Pial surface measurements

### Specialized Region Statistics
- **`lh/rh.BA_exvivo.stats`** - Brodmann areas (cytoarchitectonic regions)
- **`lh/rh.BA_exvivo.thresh.stats`** - Thresholded Brodmann areas

### Surface Property Statistics  
- **`lh/rh.curv.stats`** - Curvature statistics (mean, std, min, max)
- **`lh/rh.w-g.pct.stats`** - White-gray matter contrast measurements

---

## 🧠 Binary Data Files

### MRI Volumes (32 MGZ files, ~70MB)
**Raw Inputs:**
- `orig.mgz` - Original T1 image (conformed to 256³)
- `rawavg.mgz` - Motion corrected average
- `T1.mgz` - Intensity normalized

**Processed Volumes:**
- `brain.mgz` - Skull-stripped brain
- `norm.mgz` - Intensity normalized
- `nu.mgz` - Non-uniformity corrected

**Segmentation Volumes:**
- `aseg.mgz` - Subcortical segmentation
- `aparc+aseg.mgz` - Combined cortical + subcortical
- `wmparc.mgz` - White matter parcellation
- `filled.mgz` - Filled white matter

**Surface-related:**
- `lh/rh.ribbon.mgz` - Cortical ribbon masks

### Surface Meshes (90 files, ~116MB)
**Core Surfaces:**
- `lh/rh.white` - Gray/white matter boundary
- `lh/rh.pial` - Pial (outer cortical) surface  
- `lh/rh.inflated` - Inflated surface for visualization
- `lh/rh.sphere` - Spherical topology

**Surface Metrics:**
- `lh/rh.thickness` - Cortical thickness at each vertex
- `lh/rh.area` - Surface area at each vertex
- `lh/rh.curv` - Curvature at each vertex
- `lh/rh.sulc` - Sulcal depth

**Registration:**
- `lh/rh.sphere.reg` - Registered to fsaverage
- `lh/rh.fsaverage.sphere.reg` - fsaverage registration

### Labels & Annotations (100 files, ~44MB)
**Parcellation Annotations:**
- `lh/rh.aparc.annot` - Desikan-Killiany parcellation
- `lh/rh.aparc.DKTatlas.annot` - DKT atlas
- `lh/rh.aparc.a2009s.annot` - Destrieux atlas

**Region Labels:**
- `lh/rh.cortex.label` - Cortical mask
- `lh/rh.cortex+hipamyg.label` - Cortex + hippocampus/amygdala
- Individual region labels (e.g., `lh.BA1_exvivo.label`)

**Specialized Regions:**
- `lh/rh.BA_exvivo.annot` - Brodmann areas
- Visual area labels (`lh.V1_exvivo.label`, etc.)
- Multimodal parcellation (`lh.mpm.vpnl.annot`)

---

## 💾 Storage Strategy

### Database Storage (Parsed Statistics)
**Global Brain Metrics:**
- Total brain volume, cortical volume, white matter volume
- Brain segmentation ratios (e.g., BrainSegVol-to-eTIV)
- Surface quality metrics (holes, defects)

**Regional Measurements:**
- Per-region volume, surface area, cortical thickness
- Parcellation-specific tables for different atlases
- Hemisphere-specific metrics

**Surface Statistics:**
- Curvature statistics per hemisphere
- White-gray contrast measurements
- Vertex counts and surface areas

### Object Storage (Binary Files)

**Essential Package (~50MB):**
- Core volumes: `orig.mgz`, `brain.mgz`, `aseg.mgz`
- Key surfaces: `lh/rh.white`, `lh/rh.pial`, `lh/rh.thickness`
- Main parcellations: `lh/rh.aparc.annot`

**Complete Package (~230MB):**
- All MRI volumes (mri/ directory)
- All surface files (surf/ directory)  
- All labels and annotations (label/ directory)

**Storage Organization:**
```
freesurfer-outputs/
├── {nifti_file_id}/
│   ├── {subject_id}/
│   │   ├── mri/          # Volume data
│   │   ├── surf/         # Surface meshes & metrics  
│   │   ├── label/        # Parcellations & ROI labels
│   │   └── stats/        # Statistics files (also parsed to DB)
```

---

## 🔄 Processing Pipeline Integration

1. **Execute FreeSurfer** - Run `recon-all` function (6+ hours)
2. **Parse Statistics** - Extract measurements to database tables
3. **Store Binary Data** - Upload essential/complete packages to object storage
4. **Index & Catalog** - Create file inventory and metadata
5. **Trigger Analysis** - Launch downstream analysis functions

---

## 📋 Implementation Priority

### Phase 1: Statistics Parsing
- [ ] Parse global brain metrics (`aseg.stats`, `brainvol.stats`)
- [ ] Parse cortical parcellation statistics (`aparc.stats`)
- [ ] Create database schema for measurements

### Phase 2: Binary Storage  
- [ ] Implement essential package storage
- [ ] Create file inventory system
- [ ] Add object storage integration

### Phase 3: Integration
- [ ] Add parsing to FreeSurfer function
- [ ] Implement complete package storage
- [ ] Add downstream analysis triggers

---

*Generated from experiment: sub-OASIS10001*  
*Total analysis time: 6+ hours*  
*Output directory: /research/input/raw/sub-OASIS10001*