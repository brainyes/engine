# Dashboard Population Norms Integration Guide

This guide explains how to integrate population normative comparisons into the Brainyes dashboard for the Summary and Global Measures pages.

## Overview

The population norms system provides age and sex-matched comparisons of brain measurements to help identify volumes that are unusual compared to a healthy population. This addresses radiologist feedback to add:

- ✅ Normative comparisons (Z-scores and percentiles)
- ✅ Age-adjusted and sex-based reference data
- ✅ Visual indicators (green/orange/red status)
- ✅ Interpretation text explaining what values mean

## Quick Start

### Backend Setup

1. **Compute Population Norms** (one-time setup per dataset):
```bash
# First, process population scans (if not already done)
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/raw \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv

# Compute ROI-level norms
python -m functions.compute_population_norms --dataset oasis-1 --min-samples 30

# Compute global measure norms (NEW)
python -m functions.compute_population_norms_global --dataset oasis-1 --min-samples 30
```

2. **Run Comparison for User Scans**:
```bash
# Option 1: Run comparison manually for existing scan
python -m functions.compare_to_population_norms FILE_ID --age 45 --sex M

# Option 2: Include in pipeline (automatic)
python -m functions.mri_processing_pipeline FILE_ID --age 45 --sex M
```

### Dashboard API Integration

**Endpoint**: `GET /api/v1/population-comparison/{nifti_file_id}`

**Note**: This is a Next.js API route that handles authentication automatically via cookies.

**Example Request**:
```javascript
// Simple fetch - authentication handled via session cookies
const response = await fetch(
  `/api/v1/population-comparison/${niftiFileId}`
);

const data = await response.json();
```

**Example Response**:
```json
{
  "success": true,
  "data": {
    "global_measures": [
      {
        "measure_name": "BrainSeg",
        "display_name": "Total Brain Volume",
        "user_value": 1234567.8,
        "norm_mean": 1250000,
        "norm_std": 85000,
        "norm_p50": 1248500,
        "z_score": -0.18,
        "percentile": 43,
        "status": "normal",
        "status_label": "Normal",
        "status_color": "#10B981",
        "interpretation": "Your total brain volume is within the normal range for your age and sex (at the 43rd percentile).",
        "age_bin": "40-50",
        "sex_used": "M",
        "sample_size": 150,
        "unit": "mm³"
      },
      {
        "measure_name": "Cortex",
        "display_name": "Total Cortical Volume",
        "user_value": 520000,
        "norm_mean": 545000,
        "norm_std": 48000,
        "z_score": -0.52,
        "percentile": 30,
        "status": "normal",
        "status_label": "Normal",
        "status_color": "#10B981",
        "interpretation": "Your total cortical volume is within the normal range...",
        "age_bin": "40-50",
        "sex_used": "M",
        "sample_size": 150,
        "unit": "mm³"
      }
    ],
    "summary": {
      "total_comparisons": 52,
      "normal_count": 48,
      "outlier_count": 4,
      "normal_percentage": 92.3,
      "overall_status": "excellent",
      "overall_color": "#10B981",
      "age": 45,
      "sex": "M"
    },
    "metadata": {
      "nifti_file_id": "abc-123",
      "total_rois": 48
    }
  }
}
```

## Dashboard Implementation

### Summary Page Enhancements

**Population Comparison Card**:
```jsx
// Example React component
import { CheckCircleIcon, ExclamationCircleIcon } from '@heroicons/react/24/outline';

function PopulationComparisonCard({ summary }) {
  const statusConfig = {
    excellent: { icon: CheckCircleIcon, text: 'Excellent Match' },
    good: { icon: CheckCircleIcon, text: 'Good Match' },
    fair: { icon: ExclamationCircleIcon, text: 'Some Variations' },
    needs_attention: { icon: ExclamationCircleIcon, text: 'Needs Review' }
  };

  const config = statusConfig[summary.overall_status];

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Population Comparison</h3>

      <div className="flex items-center gap-3 mb-4">
        <config.icon
          className="w-8 h-8"
          style={{ color: summary.overall_color }}
        />
        <div>
          <div className="text-2xl font-bold">{summary.normal_percentage}%</div>
          <div className="text-sm text-gray-500">within normal range</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <div className="text-gray-500">Normal</div>
          <div className="font-semibold">{summary.normal_count} regions</div>
        </div>
        <div>
          <div className="text-gray-500">Outliers</div>
          <div className="font-semibold">{summary.outlier_count} regions</div>
        </div>
      </div>

      <div className="mt-4 text-xs text-gray-500">
        Compared to {summary.sex === 'M' ? 'males' : 'females'} aged {summary.age} years
      </div>
    </div>
  );
}
```

### Global Measures Page Enhancements

**Enhanced Measure Display**:
```jsx
function GlobalMeasureCard({ measure }) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold">{measure.display_name}</h3>
          <div className="text-3xl font-bold mt-2">
            {formatVolume(measure.user_value)}
          </div>
        </div>

        {/* Status Badge */}
        <span
          className="px-3 py-1 rounded-full text-sm font-semibold"
          style={{
            backgroundColor: measure.status_color + '20',
            color: measure.status_color
          }}
        >
          {measure.status_label}
        </span>
      </div>

      {/* Z-score and Percentile */}
      <div className="flex gap-6 mb-4">
        <div>
          <div className="text-sm text-gray-500">Z-Score</div>
          <div className="font-mono text-lg">
            {measure.z_score > 0 ? '+' : ''}{measure.z_score.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-sm text-gray-500">Percentile</div>
          <div className="text-lg font-semibold">
            {measure.percentile}th
          </div>
        </div>
      </div>

      {/* Interpretation Text */}
      <div className="p-4 bg-gray-50 rounded-lg text-sm">
        {measure.interpretation}
      </div>

      {/* Reference Info */}
      <div className="mt-4 text-xs text-gray-500">
        Population reference: {measure.sample_size} scans,
        ages {measure.age_bin}, sex: {measure.sex_used}
      </div>
    </div>
  );
}
```

**Visual Reference Curve** (optional advanced feature):
```jsx
import { Line } from 'react-chartjs-2';

function ReferenceCurve({ measure }) {
  // Request curve data from backend (requires additional endpoint)
  // Or generate client-side using normal distribution

  const data = {
    labels: generateXAxis(measure.norm_mean, measure.norm_std),
    datasets: [
      {
        label: 'Population Distribution',
        data: generateNormalCurve(measure.norm_mean, measure.norm_std),
        borderColor: '#9CA3AF',
        backgroundColor: '#9CA3AF20',
        fill: true
      },
      {
        label: 'Your Value',
        data: [{ x: measure.user_value, y: 0 }],
        pointRadius: 8,
        pointBackgroundColor: measure.status_color,
        showLine: false
      }
    ]
  };

  return (
    <div className="mt-6">
      <h4 className="text-sm font-semibold mb-2">Population Distribution</h4>
      <Line data={data} options={chartOptions} />
    </div>
  );
}
```

## Status Indicators

The system provides three status levels based on z-scores:

| Status | Z-Score Range | Color | Meaning |
|--------|--------------|-------|---------|
| Normal | \|z\| < 1.5 | Green (#10B981) | Within typical range |
| Borderline | 1.5 ≤ \|z\| < 2.0 | Orange (#F59E0B) | Slightly outside typical |
| Outlier | \|z\| ≥ 2.0 | Red (#EF4444) | Notably different |

## Global Measures Available

The following global measures are compared:

1. **BrainSeg** - Total Brain Volume
2. **Cortex** - Total Cortical Volume
3. **CerebralWhiteMatter** - Total White Matter Volume
4. **EstimatedTotalIntraCranialVol** - eTIV

Each measure is stored with a special ROI label (996-999) in the database.

## Error Handling

Handle these scenarios gracefully in the dashboard:

### No Population Data Available
```json
{
  "success": false,
  "error": "No population comparison data found for this scan"
}
```

**UI Response**: Show message "Population comparison not available for this scan. Run comparison: python -m functions.compare_to_population_norms FILE_ID"

### Age/Sex Not Provided
If age or sex is unknown, comparisons use combined (sex='U') norms which are less precise.

**UI Response**: Show warning "Age/sex not specified - using general population norms (less accurate)"

### Insufficient Population Data
Some age/sex combinations may not have enough samples.

**UI Response**: Show message "Limited population data available for this age/sex combination"

## Best Practices

1. **Always Display Context**:
   - Show which age bin and sex were used for comparison
   - Display sample size used to compute norms
   - Indicate if using combined vs sex-specific norms

2. **Use Colors Consistently**:
   - Green: Normal/good
   - Orange: Borderline/attention
   - Red: Outlier/review needed

3. **Provide Interpretation**:
   - Use the `interpretation` field from API
   - Avoid medical diagnostic language
   - Focus on statistical comparison

4. **Handle Missing Data**:
   - Not all scans will have FreeSurfer global measures
   - Population norms may not exist for all age ranges
   - Gracefully degrade when data unavailable

5. **Performance**:
   - Cache API responses (they don't change frequently)
   - Use `include_rois=false` by default (faster, smaller payload)
   - Only load detailed ROI data when user requests drill-down

## Testing

### Test with Sample Data

1. **Create test comparison**:
```bash
# Use the test NIFTI ID from docs
python -m functions.compare_to_population_norms \
    d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9 \
    --age 45 --sex M
```

2. **Test API endpoint**:
```bash
# Test via Next.js app (requires authentication)
curl -X GET \
  "https://app.brainyes.com/api/v1/population-comparison/d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9" \
  -H "Cookie: YOUR_SESSION_COOKIE"
```

3. **Verify Dashboard Display**:
   - Check all status colors render correctly
   - Verify interpretation text is readable
   - Test with different z-scores (normal, borderline, outlier)
   - Check responsive layout on mobile

## Migration Notes

### Updating Existing Dashboard

1. **Add API call** in data fetching layer
2. **Create new components** for population comparison display
3. **Update Summary page** to show overall comparison card
4. **Enhance Global Measures page** with z-scores and percentiles
5. **Test thoroughly** before deploying to production

### Backwards Compatibility

- Dashboard should gracefully handle scans without population data
- Old scans won't have comparisons until re-run
- API returns 404 if no comparison data exists (handle gracefully)

## Advanced Features (Future)

1. **Longitudinal Tracking**: Compare multiple scans over time
2. **Regional Heatmaps**: Visualize which brain regions are outliers
3. **Downloadable Reports**: PDF export with population comparison
4. **Customizable Thresholds**: Allow users to adjust z-score thresholds

## Support and Troubleshooting

### Common Issues

**Issue**: API returns 404
- **Cause**: Comparison not run yet
- **Solution**: Run `compare_to_population_norms` function

**Issue**: All measures show "Unknown"
- **Cause**: FreeSurfer not run or statistics not parsed
- **Solution**: Ensure full pipeline completed

**Issue**: Using combined norms when sex-specific expected
- **Cause**: Insufficient samples for sex-specific norms
- **Solution**: Add more population scans or use combined norms

## Related Documentation

- **Backend Functions**: `docs/POPULATION_NORMS_GUIDE.md`
- **Database Schema**: `docs/DATABASE_SCHEMA_POPULATION_NORMS.md`
- **API Documentation**: (to be created)

## Contact

For questions or issues:
- Check function help: `python -m functions.compare_to_population_norms --help`
- Review source code: `functions/compare_to_population_norms.py`
- Check utilities: `utilities/population_utilities.py`

---

**Last Updated**: 2025-10-11
**Version**: 1.0
