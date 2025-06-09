import inngest

from utilities.inngest import client as inngest_client
from utilities.supabase_utilities import save_insight_type

# Simple parameters - just what you need
PARAMETERS = {
    "nifti_id": "27c1ae7e-184e-4fd5-989b-b193003d3de2",  # example
    "user_id": "d480e950-fb57-4ad8-9797-17e5aa8fc1cf",   # example
}
INSIGHT_NAME = "my-insight-name"
save_insight_type(INSIGHT_NAME)

def main(**parameters):
    print("PARAMETERS: ", parameters)
    if not parameters:
        parameters = PARAMETERS

    ########## PAPER STARTS ##########
    
    # Option 1: Use standard processing (like ADHD insight)
    from utilities.supabase_utilities import get_roi_volumes
    volumes = get_roi_volumes(parameters["nifti_id"])
    
    # Option 2: Use custom processing (like paper_1_oasis)
    # from functions.upload_nifti import upload_nifti
    # from functions.resample_atlas_for_user_nifti import resample_atlas_for_user_nifti
    # from functions.calculate_roi_volumes import calculate_roi_volumes
    # resample_atlas_for_user_nifti(parameters["nifti_id"])
    # volumes = calculate_roi_volumes(parameters["nifti_id"])
    
    # Option 3: Completely custom (call whatever functions you need)
    # your_custom_function(parameters["nifti_id"])
    
    # Do your analysis
    print("Analysis results:", volumes)
    
    ########## PAPER ENDS ##########
    return volumes


@inngest_client.create_function(
    fn_id="insights/" + INSIGHT_NAME,
    trigger=inngest.TriggerEvent(event=INSIGHT_NAME),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    return main(**parameters)

# example:
if __name__=="__main__":
    main() 