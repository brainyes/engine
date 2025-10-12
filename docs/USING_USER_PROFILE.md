# Using User Profile in Functions

## Overview

The `get_user_profile()` utility function provides easy access to user demographic and health information from any processing function. This enables personalized analytics, age/sex-matched comparisons, and health-aware processing.

## Import

```python
from utilities.supabase_utilities import get_user_profile
```

## Usage

```python
def your_analytics_function(nifti_file_id):
    """Example function using user profile"""

    # Get user profile
    profile = get_user_profile(nifti_file_id)

    if not profile:
        print("⚠️  User profile not found")
        return

    # Access profile fields
    age = profile.get('age')                    # int or None
    sex = profile.get('sex', 'U')               # 'M', 'F', or 'U'
    health_status = profile.get('health_status')  # string or None
    age_source = profile.get('age_source')      # 'profile' or 'calculated_from_dob'

    print(f"User: age={age}, sex={sex}, health={health_status}")

    # Use in your analytics
    if age and age > 65:
        print("Applying age-adjusted thresholds for older adults")

    if health_status == 'cognitive_impairment':
        print("Comparing to cognitive impairment norms")
```

## Profile Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `age` | int or None | Age in years | 45 |
| `sex` | str | Biological sex | 'M', 'F', or 'U' |
| `health_status` | str or None | Diagnosis status | 'healthy', 'dementia', etc. |
| `date_of_birth` | str or None | ISO date | '1980-05-15' |
| `age_source` | str | How age was determined | 'profile' or 'calculated_from_dob' |

## Age Calculation

The function automatically calculates age from `date_of_birth` if age is not set in profile:

```python
profile = get_user_profile(nifti_file_id)

if profile.get('age_source') == 'calculated_from_dob':
    print(f"Age calculated from DOB: {profile['age']}")
elif profile.get('age_source') == 'profile':
    print(f"Age from profile: {profile['age']}")
```

## Real-World Examples

### Example 1: Age-Stratified Analysis

```python
from utilities.supabase_utilities import get_user_profile

def analyze_brain_volume(nifti_file_id):
    profile = get_user_profile(nifti_file_id)
    age = profile.get('age') if profile else None

    # Use age-appropriate reference ranges
    if not age:
        reference_range = (1000000, 1600000)  # General range
    elif age < 30:
        reference_range = (1200000, 1650000)  # Young adults
    elif age < 60:
        reference_range = (1100000, 1550000)  # Middle age
    else:
        reference_range = (1000000, 1450000)  # Older adults

    # ... rest of analysis
```

### Example 2: Sex-Specific Metrics

```python
from utilities.supabase_utilities import get_user_profile

def calculate_hippocampus_ratio(nifti_file_id):
    profile = get_user_profile(nifti_file_id)
    sex = profile.get('sex', 'U') if profile else 'U'

    # Get volumes
    left_hippo = get_volume(nifti_file_id, 'left_hippocampus')
    right_hippo = get_volume(nifti_file_id, 'right_hippocampus')

    # Apply sex-specific normalization
    if sex == 'M':
        norm_factor = 1.08  # Males tend to have ~8% larger
    elif sex == 'F':
        norm_factor = 1.00
    else:
        norm_factor = 1.04  # Combined average

    normalized_volume = (left_hippo + right_hippo) / norm_factor
    return normalized_volume
```

### Example 3: Health-Aware Processing

```python
from utilities.supabase_utilities import get_user_profile

def generate_brain_health_report(nifti_file_id):
    profile = get_user_profile(nifti_file_id)
    health_status = profile.get('health_status') if profile else 'healthy'

    # Adjust recommendations based on health status
    if health_status == 'dementia':
        recommendations = [
            "Monitor hippocampal volume changes over time",
            "Consider longitudinal tracking",
            "Consult with neurologist about findings"
        ]
    elif health_status == 'cognitive_impairment':
        recommendations = [
            "Track cortical thickness patterns",
            "Monitor for progression signs",
            "Consider follow-up scan in 6-12 months"
        ]
    else:
        recommendations = [
            "Maintain cognitive health with exercise",
            "Annual scan recommended after age 60"
        ]

    return {
        'health_status': health_status,
        'recommendations': recommendations
    }
```

### Example 4: Personalized Insights

```python
from utilities.supabase_utilities import get_user_profile

def generate_personalized_summary(nifti_file_id):
    profile = get_user_profile(nifti_file_id)

    if not profile:
        return "Complete your health profile for personalized insights!"

    age = profile.get('age')
    sex = profile.get('sex')

    # Generate age/sex-aware summary
    intro = f"For a {age}-year-old {'male' if sex == 'M' else 'female' if sex == 'F' else 'individual'}"

    volumes = get_brain_volumes(nifti_file_id)
    comparisons = compare_to_norms(volumes, age, sex)

    insights = [intro]

    if comparisons['hippocampus']['percentile'] < 25:
        insights.append("Your hippocampal volume is below average for your age group")
        if age and age > 50:
            insights.append("This is common with aging but should be monitored")

    return " ".join(insights)
```

## Error Handling

```python
profile = get_user_profile(nifti_file_id)

if not profile:
    # User or scan not found
    print("⚠️  Could not load user profile")
    # Use defaults or skip personalized features
    age, sex = None, 'U'
else:
    age = profile.get('age')
    sex = profile.get('sex', 'U')

    if not age:
        print("💡 Tip: User should complete age in profile for better accuracy")
```

## User Privacy

- Diagnosis status is optional and self-reported
- Users can set sex to 'U' (Prefer not to say)
- Age can be omitted
- All profile data is protected by Row Level Security (RLS)
- Only the scan owner's profile can be accessed

## When to Use

**Use `get_user_profile()` when you need:**
- Age-matched comparisons
- Sex-specific normalization
- Health-aware analysis
- Personalized recommendations
- Clinical context for results

**Don't use when:**
- Processing population dataset scans (use metadata CSV instead)
- Performing generic/universal analysis
- User privacy is a concern for the specific use case

## Related Functions

- `compare_to_population_norms()` - Uses user profile automatically
- `mri_processing_pipeline()` - Passes profile data to downstream functions
- `get_roi_volumes()` - Gets ROI volumes (often used with profile data)

## Database Schema

The profile data comes from the `users` table:

```sql
SELECT age, sex, date_of_birth, health_status
FROM users
WHERE id = (SELECT user_id FROM nifti_files WHERE id = 'scan_id');
```

## Migration

If you have an existing function that takes `age` and `sex` as parameters, you can easily migrate:

**Before:**
```python
def my_function(nifti_file_id, age=None, sex='U'):
    # Use age and sex
    pass
```

**After:**
```python
from utilities.supabase_utilities import get_user_profile

def my_function(nifti_file_id, age=None, sex=None):
    # Get from profile if not provided
    if age is None or sex is None:
        profile = get_user_profile(nifti_file_id)
        if profile:
            if age is None:
                age = profile.get('age')
            if sex is None:
                sex = profile.get('sex', 'U')

    # Set defaults if still None
    if sex is None:
        sex = 'U'

    # Use age and sex
    pass
```

---

**Last Updated**: 2025-10-11
**Version**: 1.0
