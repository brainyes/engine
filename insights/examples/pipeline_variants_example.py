# Pipeline Variants Approach
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class ProcessingConfig:
    atlas_type: str = "harvard_oxford"
    resolution: str = "2mm" 
    smoothing_kernel: float = 0.0
    normalization: str = "none"
    custom_regions: List[str] = None
    
class PipelineFactory:
    """Factory for creating different processing pipelines"""
    
    @staticmethod
    def get_pipeline(pipeline_name: str):
        pipelines = {
            "standard": StandardPipeline(),
            "pediatric": PediatricPipeline(), 
            "high_res": HighResolutionPipeline(),
            "custom_atlas": CustomAtlasPipeline(),
            "longitudinal": LongitudinalPipeline()
        }
        return pipelines.get(pipeline_name, pipelines["standard"])

class StandardPipeline:
    """Your current pipeline - Harvard Oxford, 2mm, basic volumes"""
    def process(self, nifti_id: str) -> Dict[str, Any]:
        from functions.upload_nifti import upload_nifti
        from functions.resample_atlas_for_user_nifti import resample_atlas_for_user_nifti
        from functions.calculate_roi_volumes import calculate_roi_volumes
        
        # Standard pipeline
        resample_atlas_for_user_nifti(nifti_id)
        return calculate_roi_volumes(nifti_id)

class PediatricPipeline:
    """Pipeline optimized for children - different atlas, different processing"""
    def process(self, nifti_id: str) -> Dict[str, Any]:
        # Use pediatric atlas, different normalization
        config = ProcessingConfig(
            atlas_type="pediatric_template",
            resolution="1mm",
            normalization="age_corrected"
        )
        return self._process_with_config(nifti_id, config)

class HighResolutionPipeline:
    """For studies requiring high precision"""
    def process(self, nifti_id: str) -> Dict[str, Any]:
        config = ProcessingConfig(
            atlas_type="harvard_oxford",
            resolution="1mm",
            smoothing_kernel=2.0
        )
        return self._process_with_config(nifti_id, config)

# Usage in insights:
def insight_with_custom_pipeline(**parameters):
    pipeline_name = parameters.get("pipeline", "standard")
    pipeline = PipelineFactory.get_pipeline(pipeline_name)
    
    # Process data with chosen pipeline
    data = pipeline.process(parameters["nifti_id"])
    
    # Then do your analysis
    return analyze_data(data, parameters)

# Examples of different research needs:
RESEARCH_CONFIGS = {
    "adhd_study": {
        "pipeline": "pediatric",
        "focus_regions": ["caudate", "putamen", "amygdala"]
    },
    "aging_study": {
        "pipeline": "high_res", 
        "normalization": "age_corrected",
        "focus_regions": ["hippocampus", "frontal_cortex"]
    },
    "tumor_study": {
        "pipeline": "custom_atlas",
        "atlas_path": "/path/to/tumor_specific_atlas.nii",
        "exclude_regions": ["lesion_mask"]
    }
} 