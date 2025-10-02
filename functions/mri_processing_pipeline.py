import os
import time
import requests
import traceback
from datetime import datetime

FUNCTION_NAME = "mri_processing_pipeline"
LAMBDA_API_URL = os.environ.get('LAMBDA_API_URL', 'https://<api-id>.execute-api.us-east-2.amazonaws.com/prod')

def call_lambda_sync(function_name, parameters):
    """Call Lambda function synchronously and return result"""
    print(f"  → Calling {function_name}...")

    url = f"{LAMBDA_API_URL}/function/{function_name}"
    response = requests.post(url, json=parameters, timeout=900)  # 15 min timeout

    if response.status_code != 200:
        raise Exception(f"Lambda call failed: {response.status_code} - {response.text}")

    result = response.json()
    print(f"  ✅ {function_name} completed")
    return result

def call_lambda_async(function_name, parameters):
    """
    Call Lambda async endpoint, wait for completion, return result
    Polls every 30 seconds
    """
    print(f"  → Starting async task: {function_name}...")

    # Start async task
    url = f"{LAMBDA_API_URL}/async/{function_name}"
    response = requests.post(url, json=parameters, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Async task start failed: {response.status_code} - {response.text}")

    task_data = response.json()
    task_id = task_data['task_id']
    print(f"  📋 Async task started: {task_id}")
    print(f"  ⏳ Polling for completion (checking every 30s)...")

    # Poll until complete
    poll_count = 0
    while True:
        time.sleep(30)  # Wait 30 seconds between polls
        poll_count += 1

        status_url = f"{LAMBDA_API_URL}/tasks/{task_id}/status"
        status_response = requests.get(status_url, timeout=10)

        if status_response.status_code != 200:
            print(f"  ⚠️  Warning: Failed to get task status (will retry)")
            continue

        status_data = status_response.json()
        task_status = status_data['task']['status']

        if poll_count % 10 == 0:  # Print update every 5 minutes
            print(f"  ⏳ Still waiting... (status: {task_status}, checked {poll_count} times)")

        if task_status == 'completed':
            print(f"  ✅ {function_name} completed after {poll_count * 30}s")
            return status_data['task']['result']

        elif task_status == 'failed':
            error = status_data['task'].get('error', 'Unknown error')
            raise Exception(f"{function_name} failed: {error}")

        # Continue polling if still running/pending

def mri_processing_pipeline(nifti_file_id, user_id=None, **kwargs):
    """
    Complete MRI processing pipeline orchestrator
    Calls Lambda API for each step, monitoring them individually

    Args:
        nifti_file_id (str): The ID of the NIFTI file to process
        user_id (str): Optional user ID for tracking

    Returns:
        dict: Complete pipeline results with all task IDs
    """

    print("="*80)
    print(f"🧠 CEREBRO MRI PROCESSING PIPELINE")
    print(f"NIFTI File ID: {nifti_file_id}")
    print(f"Pipeline Task: {os.environ.get('TASK_ID', 'unknown')}")
    print(f"Started: {datetime.now().isoformat()}")
    print("="*80)

    results = {
        'nifti_file_id': nifti_file_id,
        'pipeline_version': '1.0',
        'task_ids': {},  # Track all sub-task IDs
        'steps_completed': []
    }

    try:
        # STEP 1: Resample Atlas (Lambda sync)
        print("\n" + "="*80)
        print("STEP 1/8: Resampling Atlas")
        print("="*80)
        results['resample_atlas'] = call_lambda_sync(
            'resample_atlas_for_user_nifti',
            {'nifti_file_id': nifti_file_id}
        )
        results['steps_completed'].append('resample_atlas')

        # STEP 2: Calculate ROI Volumes (Lambda sync)
        print("\n" + "="*80)
        print("STEP 2/8: Calculating ROI Volumes")
        print("="*80)
        results['roi_volumes'] = call_lambda_sync(
            'calculate_roi_volumes',
            {'nifti_file_id': nifti_file_id}
        )
        results['steps_completed'].append('roi_volumes')

        # STEP 3: FreeSurfer Recon-All (ECS async - LONG!)
        print("\n" + "="*80)
        print("STEP 3/8: FreeSurfer Recon-All")
        print("⚠️  This step takes 4-8 hours")
        print("="*80)
        results['freesurfer'] = call_lambda_async(
            'freesurfer_recon_all',
            {'nifti_file_id': nifti_file_id, 'user_id': user_id}
        )
        results['steps_completed'].append('freesurfer_recon_all')

        # Extract FreeSurfer outputs for next steps
        freesurfer_result = results['freesurfer'].get('function_result', results['freesurfer'])
        freesurfer_dir = freesurfer_result['output_directory']
        subject_id = freesurfer_result['subject_id']

        print(f"  📁 FreeSurfer output: {freesurfer_dir}")
        print(f"  👤 Subject ID: {subject_id}")

        # STEP 4: Store FreeSurfer Files (Lambda sync)
        print("\n" + "="*80)
        print("STEP 4/8: Storing FreeSurfer Files")
        print("="*80)
        results['store_files'] = call_lambda_sync(
            'freesurfer_store_files',
            {
                'nifti_file_id': nifti_file_id,
                'freesurfer_output_directory': freesurfer_dir,
                'subject_id': subject_id
            }
        )
        results['steps_completed'].append('store_files')

        # STEP 5: Generate Surface Files (Lambda sync)
        print("\n" + "="*80)
        print("STEP 5/8: Generating Surface Files (.asc)")
        print("="*80)
        results['surface_files'] = call_lambda_sync(
            'generate_surface_files',
            {
                'nifti_file_id': nifti_file_id,
                'freesurfer_output_directory': freesurfer_dir,
                'subject_id': subject_id
            }
        )
        results['steps_completed'].append('surface_files')

        # STEP 6: Parse Statistics (Lambda sync)
        print("\n" + "="*80)
        print("STEP 6/8: Parsing Statistics")
        print("="*80)
        results['parse_statistics'] = call_lambda_sync(
            'freesurfer_parse_statistics',
            {
                'nifti_file_id': nifti_file_id,
                'freesurfer_output_directory': freesurfer_dir,
                'subject_id': subject_id
            }
        )
        results['steps_completed'].append('parse_statistics')

        # STEP 7: Generate Visualization Data (Lambda sync)
        print("\n" + "="*80)
        print("STEP 7/8: Generating Visualization Data")
        print("="*80)
        results['visualization'] = call_lambda_sync(
            'generate_visualization_data',
            {
                'nifti_file_id': nifti_file_id,
                'parcellation': 'custom_regions_de_ki'
            }
        )
        results['steps_completed'].append('visualization_data')

        # STEP 8: Calculate Memory Metrics (Lambda sync)
        print("\n" + "="*80)
        print("STEP 8/8: Calculating Memory Metrics")
        print("="*80)
        results['memory_metrics'] = call_lambda_sync(
            'calculate_memory_metrics',
            {'nifti_file_id': nifti_file_id}
        )
        results['steps_completed'].append('memory_metrics')

        # SUCCESS!
        print("\n" + "="*80)
        print("🎉 PIPELINE COMPLETE!")
        print(f"Steps completed: {len(results['steps_completed'])}/8")
        print(f"Finished: {datetime.now().isoformat()}")
        print("="*80)

        results['status'] = 'completed'
        results['message'] = 'All processing steps completed successfully'

        return results

    except Exception as e:
        print("\n" + "="*80)
        print(f"❌ PIPELINE FAILED")
        print(f"Failed after completing: {results['steps_completed']}")
        print(f"Error: {str(e)}")
        print(f"Traceback:\n{traceback.format_exc()}")
        print("="*80)

        results['status'] = 'failed'
        results['error'] = str(e)
        results['failed_at_step'] = len(results['steps_completed']) + 1

        raise


# CLI for testing
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Run MRI processing pipeline')
    parser.add_argument('nifti_file_id', help='NIFTI file ID')
    parser.add_argument('--user-id', help='User ID (optional)')

    args = parser.parse_args()

    print("=== MRI PROCESSING PIPELINE ===")
    print("This will run the complete processing pipeline:")
    print("1. Resample atlas (~30s)")
    print("2. Calculate ROI volumes (~30s)")
    print("3. FreeSurfer recon-all (4-8 hours)")
    print("4. Store FreeSurfer files (~1 min)")
    print("5. Generate surface files (.asc) (~1 min)")
    print("6. Parse statistics (~30s)")
    print("7. Generate visualization data (custom_regions_de_ki) (~30s)")
    print("8. Calculate memory metrics (~30s)")
    print("\nTotal expected time: 4-8 hours")
    print("All steps will be tracked as separate tasks in the dashboard\n")

    try:
        result = mri_processing_pipeline(args.nifti_file_id, args.user_id)
        print("\n✅ Pipeline successful!")
        print(f"Completed steps: {result['steps_completed']}")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {str(e)}")
        os._exit(1)

    os._exit(0)