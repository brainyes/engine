import inngest
import os
import argparse
import pandas as pd
import numpy as np
import nibabel as nib
from datetime import datetime

from utilities.inngest import client as inngest_client
from utilities.data import supabase
from utilities.helpers import download_nifti_file, get_roi_volumes
from utilities.supabase_utilities import get_user_insight, save_insight_output, save_insight_outputs, save_insight_output_file, save_insight_output_pandas

FUNCTION_NAME = "user_analysis"

def user_analysis(nifti_file_id, user_id, **kwargs):
    """
    Analyze individual user's brain MRI against population thresholds
    
    This function takes a user's brain scan and compares their features
    to the population norms established by the population analysis script.
    
    Args:
        nifti_file_id (str): ID of the user's NIFTI file in Supabase storage
        user_id (str): ID of the user
        
    Returns:
        dict: User-specific analysis results and insights
    """
    
    print("=== USER BRAIN ANALYSIS ===")
    print(f"Analyzing brain scan for user {user_id}, NIFTI file ID: {nifti_file_id}")
    
    ########## TODO: IMPLEMENT USER ANALYSIS ##########
    
    # TODO 1: Get user's brain scan
    print("Downloading user's brain scan...")
    nifti_file_path = download_nifti_file(nifti_file_id)
    print(f"✅ Downloaded: {nifti_file_path}")

        # do your analysis here...
    
    # TODO: Save user insights using helpers
    # Get or create user insight record
    # user_insight_strength = get_user_insight("strength", user_id, nifti_file_id)
    # save_insight_output(user_insight_strength['id'], 'strength', "STRENGTH_SCORE")
    
    # Save your analysis outputs using the helpers:
    
    # Method 1: Save simple key-value results
    # results = {
    #     'total_brain_volume': 1234567.89,
    #     'gray_matter_volume': 678901.23,
    #     'white_matter_volume': 555666.77,
    #     'abnormal_features_count': 3,
    #     'risk_score': 0.25
    # }
    # save_insight_outputs(user_insight['id'], results)
    
    # Method 2: Save DataFrame/CSV data  
    # features_df = pd.DataFrame({
    #     'feature_name': ['volume_1', 'volume_2', 'thickness_1'],
    #     'user_value': [123.4, 567.8, 2.45],
    #     'z_score': [-1.2, 0.8, 2.1],
    #     'is_normal': [True, True, False]
    # })
    # save_insight_output_pandas(user_insight['id'], 'feature_analysis', features_df)
    
    # Method 3: Save plot/image files
    # import matplotlib.pyplot as plt
    # plt.figure(figsize=(10, 6))
    # plt.plot(your_data)
    # plt.title('Brain Analysis Results')
    # save_insight_output_file(user_insight['id'], 'analysis_plot.png', plot_to_image())
    
    print("✅ Results saved using insight helpers!")
   
    
    ########## TODO IMPLEMENTATION ENDS ##########
    
    # Placeholder return for template
    result = {
        "nifti_file_id": nifti_file_id,
        "status": "completed",
        "features_analyzed": 0,  # TODO: Replace with actual count
        "insights_generated": 0,  # TODO: Replace with actual count
        "abnormal_features": 0,  # TODO: Replace with actual count
        "analysis_date": datetime.now().isoformat()
    }
    
    print("✅ User analysis completed!")
    return result


@inngest_client.create_function(
    fn_id=FUNCTION_NAME,
    trigger=inngest.TriggerEvent(event=f"{FUNCTION_NAME}_requested"),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    """Inngest function wrapper"""
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    
    # Extract required parameters
    nifti_file_id = parameters.get('nifti_file_id')
    user_id = parameters.get('user_id')
    if not nifti_file_id:
        raise ValueError("nifti_file_id is required")
    if not user_id:
        raise ValueError("user_id is required")
    
    result = await step.run("execute-analysis", lambda: user_analysis(nifti_file_id, user_id, **parameters))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Analyze user brain MRI against population thresholds')
    parser.add_argument('nifti_file_id', help='ID of the user NIFTI file in Supabase storage')
    parser.add_argument('user_id', help='ID of the user')
    
    args = parser.parse_args()
    
    print("=== USER BRAIN ANALYSIS ===")
    print(f"Analyzing brain scan: {args.nifti_file_id} for user: {args.user_id}")
    print("This will compare the user's features to population norms...")
    print("Please wait while we process the analysis...\n")
    
    try:
        result = user_analysis(args.nifti_file_id, args.user_id)
        
        print(f"\n=== ANALYSIS COMPLETE FOR USER {args.nifti_file_id} ===")
        print("✅ User brain analysis completed successfully")
        print(f"📊 Features analyzed: {result['features_analyzed']}")
        print(f"🧠 Insights generated: {result['insights_generated']}")
        print(f"⚠️  Abnormal features: {result['abnormal_features']}")
        print(f"📅 Analysis date: {result['analysis_date']}")
        print("\n💾 Results saved to database for this user")
        
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        print("Please check your implementation and try again.")
        os._exit(1)
    
    os._exit(0) 