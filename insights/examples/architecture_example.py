# Example of layered insight architecture
import inngest
from utilities.inngest import client as inngest_client
from utilities.supabase_utilities import save_insight_type

# Different processing "modes" for different insights
class InsightBase:
    def __init__(self, insight_name):
        self.insight_name = insight_name
        save_insight_type(insight_name)
    
    def get_data(self, parameters):
        """Override this for custom data processing"""
        # Default: use standard pipeline
        from functions.calculate_roi_volumes import calculate_roi_volumes
        from utilities.supabase_utilities import get_roi_volumes
        return get_roi_volumes(parameters["nifti_id"])
    
    def analyze(self, data, parameters):
        """Override this for insight-specific analysis"""
        raise NotImplementedError("Each insight must implement analyze()")

# EXAMPLE 1: Pure analysis (like your ADHD comparison)
class ADHDInsight(InsightBase):
    def analyze(self, data, parameters):
        # Pure statistical analysis, no custom preprocessing
        return self.compare_to_adhd_patterns(data)

# EXAMPLE 2: Custom preprocessing + analysis  
class CustomAtlasInsight(InsightBase):
    def get_data(self, parameters):
        # Custom preprocessing pipeline
        from functions.upload_nifti import upload_nifti
        from functions.custom_atlas_resample import resample_custom_atlas  # hypothetical
        from functions.custom_volume_calc import calculate_custom_volumes   # hypothetical
        
        # Use custom pipeline instead of standard one
        nifti_file = self.get_nifti_file(parameters["nifti_id"])
        custom_atlas = resample_custom_atlas(nifti_file, atlas_type="pediatric")
        return calculate_custom_volumes(nifti_file, custom_atlas)
    
    def analyze(self, data, parameters):
        return self.pediatric_specific_analysis(data)

# EXAMPLE 3: Multi-modal data integration
class MultiModalInsight(InsightBase):
    def get_data(self, parameters):
        # Combine standard volumes with external data
        standard_volumes = super().get_data(parameters)
        external_data = self.load_external_dataset(parameters.get("dataset_name"))
        return self.merge_data(standard_volumes, external_data)
    
    def analyze(self, data, parameters):
        return self.cross_modal_analysis(data)

# Usage in actual insights:
class ConcretePaperInsight(MultiModalInsight):
    def __init__(self):
        super().__init__("paper-xyz-multimodal")
    
    def analyze(self, data, parameters):
        # Your specific paper implementation
        return "Analysis results"

# Standard template that works for any approach:
def create_insight_template(insight_class):
    def main(**parameters):
        insight = insight_class()
        data = insight.get_data(parameters)
        results = insight.analyze(data, parameters)
        return results
    
    @inngest_client.create_function(
        fn_id=f"insights/{insight.insight_name}",
        trigger=inngest.TriggerEvent(event=insight.insight_name),
    )
    async def fn(ctx: inngest.Context, step: inngest.Step):
        parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
        return main(**parameters)
    
    return main, fn 