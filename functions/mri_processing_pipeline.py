import os
import traceback
from datetime import datetime

# Import all processing functions
from functions.resample_atlas_for_user_nifti import resample_atlas_for_user_nifti
from functions.calculate_roi_volumes import calculate_roi_volumes
from functions.freesurfer_recon_all import freesurfer_recon_all
from functions.freesurfer_store_files import freesurfer_store_files
from functions.generate_surface_files import generate_surface_files
from functions.freesurfer_parse_statistics import freesurfer_parse_statistics
from functions.generate_visualization_data import generate_visualization_data
from functions.calculate_memory_metrics import calculate_memory_metrics

FUNCTION_NAME = "mri_processing_pipeline"

def mri_processing_pipeline(nifti_file_id, user_id=None, **kwargs):
    """
    Complete MRI processing pipeline - runs all functions locally/synchronously
    Designed to run in ECS Fargate with all dependencies available

    Args:
        nifti_file_id (str): The ID of the NIFTI file to process
        user_id (str): Optional user ID for tracking

    Returns:
        dict: Complete pipeline results
    """

    print("="*80)
    print(f"🧠 CEREBRO MRI PROCESSING PIPELINE (LOCAL/SYNC)")
    print(f"NIFTI File ID: {nifti_file_id}")
    print(f"ECS Task ID: {os.environ.get('TASK_ID', 'unknown')}")
    print(f"Started: {datetime.now().isoformat()}")
    print("="*80)

    results = {
        'nifti_file_id': nifti_file_id,
        'pipeline_version': '2.0-local',
        'steps_completed': []
    }

    try:
        # STEP 1: Resample Atlas
        print("\n" + "="*80)
        print("STEP 1/8: Resampling Atlas")
        print("="*80)
        results['resample_atlas'] = resample_atlas_for_user_nifti(nifti_file_id)
        results['steps_completed'].append('resample_atlas')

        # STEP 2: Calculate ROI Volumes
        print("\n" + "="*80)
        print("STEP 2/8: Calculating ROI Volumes")
        print("="*80)
        results['roi_volumes'] = calculate_roi_volumes(nifti_file_id)
        results['steps_completed'].append('roi_volumes')

        # STEP 3: FreeSurfer Recon-All (LONG!)
        print("\n" + "="*80)
        print("STEP 3/8: FreeSurfer Recon-All")
        print("⚠️  This step takes 4-8 hours")
        print("="*80)
        freesurfer_result = freesurfer_recon_all(nifti_file_id, user_id=user_id)
        results['freesurfer'] = freesurfer_result
        results['steps_completed'].append('freesurfer_recon_all')

        # Extract FreeSurfer outputs for next steps
        freesurfer_dir = freesurfer_result['output_directory']
        subject_id = freesurfer_result['subject_id']

        print(f"  📁 FreeSurfer output: {freesurfer_dir}")
        print(f"  👤 Subject ID: {subject_id}")

        # STEP 4: Store FreeSurfer Files
        print("\n" + "="*80)
        print("STEP 4/8: Storing FreeSurfer Files")
        print("="*80)
        results['store_files'] = freesurfer_store_files(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=freesurfer_dir,
            subject_id=subject_id
        )
        results['steps_completed'].append('store_files')

        # STEP 5: Generate Surface Files (.asc)
        print("\n" + "="*80)
        print("STEP 5/8: Generating Surface Files (.asc)")
        print("="*80)
        results['surface_files'] = generate_surface_files(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=freesurfer_dir,
            subject_id=subject_id
        )
        results['steps_completed'].append('surface_files')

        # STEP 6: Parse Statistics
        print("\n" + "="*80)
        print("STEP 6/8: Parsing Statistics")
        print("="*80)
        results['parse_statistics'] = freesurfer_parse_statistics(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=freesurfer_dir,
            subject_id=subject_id
        )
        results['steps_completed'].append('parse_statistics')

        # STEP 7: Generate Visualization Data
        print("\n" + "="*80)
        print("STEP 7/8: Generating Visualization Data")
        print("="*80)
        results['visualization'] = generate_visualization_data(
            nifti_file_id=nifti_file_id,
            parcellation='custom_regions_de_ki'
        )
        results['steps_completed'].append('visualization_data')

        # STEP 8: Calculate Memory Metrics
        print("\n" + "="*80)
        print("STEP 8/8: Calculating Memory Metrics")
        print("="*80)
        results['memory_metrics'] = calculate_memory_metrics(nifti_file_id)
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

        import sentry_sdk
        sentry_sdk.capture_exception(e)

        raise


# CLI for testing
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Run MRI processing pipeline locally (all steps in one process)')
    parser.add_argument('nifti_file_id', help='NIFTI file ID')
    parser.add_argument('--user-id', help='User ID (optional)')

    args = parser.parse_args()

    print("=== MRI PROCESSING PIPELINE (LOCAL) ===")
    print("This will run the complete processing pipeline in this process:")
    print("1. Resample atlas (~30s)")
    print("2. Calculate ROI volumes (~30s)")
    print("3. FreeSurfer recon-all (4-8 hours)")
    print("4. Store FreeSurfer files (~1 min)")
    print("5. Generate surface files (.asc) (~1 min)")
    print("6. Parse statistics (~30s)")
    print("7. Generate visualization data (custom_regions_de_ki) (~30s)")
    print("8. Calculate memory metrics (~30s)")
    print("\nTotal expected time: 4-8 hours")
    print("All steps run directly without API calls\n")

    try:
        result = mri_processing_pipeline(args.nifti_file_id, args.user_id)
        print("\n✅ Pipeline successful!")
        print(f"Completed steps: {result['steps_completed']}")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {str(e)}")
        os._exit(1)

    os._exit(0)