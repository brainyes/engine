import inngest
import os
import argparse

from utilities.inngest import client as inngest_client
from utilities.data import supabase
from utilities.supabase_utilities import download_nifti_file, get_nifti_file  # Common utility


# TODO: Replace with your function name
FUNCTION_NAME = "my_new_function"

def my_new_function(nifti_file_id, **kwargs):
    """
    TODO: Replace with your function description
    
    Args:
        nifti_file_id (str): The ID of the NIFTI file to process
        **kwargs: Additional parameters specific to your function
        
    Returns:
        dict: Results of your processing
    """
    
    # Get the NIFTI file info
    nifti_file_object, storage_object, nifti_gz_path = get_nifti_file(nifti_file_id, True)
    nifti_file_path = download_nifti_file(nifti_file_id)
    print(f"Processing NIFTI file: {nifti_file_object['id']} at {nifti_file_path}")
    
    ########## YOUR FUNCTION LOGIC STARTS ##########
    
    # TODO: Implement your processing logic here
    
    # 1. Load user's brain scan (always use helper function)
    # import nibabel as nib
    # nifti_img = nib.load(nifti_file_path)  # from download_nifti_file above
    # data = nifti_img.get_fdata()
    
    # 2. Load reference data from research/input (if needed)
    # from utilities.options import atlas_file_path
    # atlas = nib.load(atlas_file_path)
    
    # 3. Process the data
    # result = your_analysis_function(data)
    
    # 4. Save results to database (ask admin to create table first)
    # record = {
    #     "nifti_file_id": nifti_file_id,
    #     "result_value": result,
    #     "created_at": datetime.now().isoformat()
    # }
    # response = supabase.table("my_results_table").insert(record).execute()
    
    # For template - just return a placeholder
    result = {
        "nifti_file_id": nifti_file_id,
        "status": "processed",
        "message": "Template function executed successfully"
    }
    
    ########## YOUR FUNCTION LOGIC ENDS ##########
    
    print(f"Function completed for file: {nifti_file_id}")
    return result


@inngest_client.create_function(
    fn_id=FUNCTION_NAME,
    trigger=inngest.TriggerEvent(event=f"{FUNCTION_NAME}_requested"),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    """Inngest function wrapper for workflow automation"""
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    result = await step.run("execute-function", lambda: my_new_function(**parameters))
    
    # TODO: Optionally trigger next step in pipeline
    # await inngest_client.send(
    #     inngest.Event(name="next_function_requested", data={"nifti_file_id": parameters["nifti_file_id"]})
    # )
    
    return result


# Command line interface for scientists
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TODO: Add description of what this function does')
    parser.add_argument('file_id', help='NIFTI file ID to process')
    
    # TODO: Add function-specific arguments
    # parser.add_argument('--threshold', type=float, default=0.5, help='Processing threshold')
    # parser.add_argument('--method', choices=['fast', 'accurate'], default='fast', help='Processing method')
    
    args = parser.parse_args()
    
    print(f"=== {FUNCTION_NAME.upper().replace('_', ' ')} ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    print("TODO: Add description of what this will do...")
    print("Please wait...\n")
    
    try:
        # TODO: Pass additional arguments if you added any
        result = my_new_function(args.file_id)
        
        print(f"\n=== PROCESSING COMPLETE ===")
        print("✅ Function executed successfully")
        print("Result:", result)
        
        # TODO: Show next steps if this is part of a pipeline
        # print("\nNext step: Run the next function with the same file ID:")
        # print(f"python -m functions.next_function {args.file_id}")
        
    except Exception as e:
        print(f"❌ Error during processing: {str(e)}")
        print("Please check your file ID and try again.")
        os._exit(1)
    
    # Force exit to prevent hanging
    os._exit(0) 