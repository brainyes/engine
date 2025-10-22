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
from functions.prepare_volume_visualization import prepare_volume_visualization
from functions.calculate_memory_metrics import calculate_memory_metrics
from functions.compare_to_population_norms import compare_to_population_norms

FUNCTION_NAME = "mri_processing_pipeline"

def mri_processing_pipeline(
    nifti_file_id,
    user_id=None,
    age=None,
    sex='U',
    **kwargs
):
    """
    Complete MRI processing pipeline - runs all functions locally/synchronously
    Designed to run in ECS Fargate with all dependencies available

    Automatically processes with ALL available brain atlases.

    Args:
        nifti_file_id (str): The ID of the NIFTI file to process
        user_id (str): Optional user ID for tracking
        age (int): Optional age for population comparison
        sex (str): Optional sex ('M', 'F', or 'U') for population comparison

    Returns:
        dict: Complete pipeline results
    """

    print("="*80)
    print(f"🧠 BRAINYES MRI PROCESSING PIPELINE (LOCAL/SYNC)")
    print(f"NIFTI File ID: {nifti_file_id}")
    print(f"Atlas Processing: All available atlases")
    print(f"ECS Task ID: {os.environ.get('TASK_ID', 'unknown')}")
    print(f"Started: {datetime.now().isoformat()}")
    print("="*80)

    results = {
        'nifti_file_id': nifti_file_id,
        'pipeline_version': '2.2-multi-atlas-volume-viz',
        'steps_completed': []
    }

    try:
        # STEP 1: Resample Atlas (all atlases)
        print("\n" + "="*80)
        print(f"STEP 1/10: Resampling Atlases (all available)")
        print("="*80)
        results['resample_atlas'] = resample_atlas_for_user_nifti(nifti_file_id)
        results['steps_completed'].append('resample_atlas')

        # STEP 2: Calculate ROI Volumes (all atlases)
        print("\n" + "="*80)
        print(f"STEP 2/10: Calculating ROI Volumes (all atlases)")
        print("="*80)
        results['roi_volumes'] = calculate_roi_volumes(nifti_file_id)
        results['steps_completed'].append('roi_volumes')

        # STEP 3: FreeSurfer Recon-All (LONG!)
        print("\n" + "="*80)
        print("STEP 3/10: FreeSurfer Recon-All")
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
        print("STEP 4/10: Storing FreeSurfer Files")
        print("="*80)
        results['store_files'] = freesurfer_store_files(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=freesurfer_dir,
            subject_id=subject_id
        )
        results['steps_completed'].append('store_files')

        # STEP 5: Generate Surface Files (.asc)
        print("\n" + "="*80)
        print("STEP 5/10: Generating Surface Files (.asc)")
        print("="*80)
        results['surface_files'] = generate_surface_files(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=freesurfer_dir,
            subject_id=subject_id
        )
        results['steps_completed'].append('surface_files')

        # STEP 6: Parse Statistics
        print("\n" + "="*80)
        print("STEP 6/10: Parsing Statistics")
        print("="*80)
        results['parse_statistics'] = freesurfer_parse_statistics(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=freesurfer_dir,
            subject_id=subject_id
        )
        results['steps_completed'].append('parse_statistics')

        # STEP 7: Generate Visualization Data
        print("\n" + "="*80)
        print("STEP 7/10: Generating Visualization Data")
        print("="*80)
        results['visualization'] = generate_visualization_data(
            nifti_file_id=nifti_file_id,
            parcellation='aparc'  # Use standard Desikan-Killiany atlas
        )
        results['steps_completed'].append('visualization_data')

        # STEP 8: Prepare Volume Visualization (NEW!)
        print("\n" + "="*80)
        print("STEP 8/10: Preparing Volume Visualization (Region Meshes)")
        print("="*80)
        results['volume_visualization'] = prepare_volume_visualization(nifti_file_id)
        results['steps_completed'].append('volume_visualization')

        # STEP 9: Calculate Memory Metrics
        print("\n" + "="*80)
        print("STEP 9/10: Calculating Memory Metrics")
        print("="*80)
        results['memory_metrics'] = calculate_memory_metrics(nifti_file_id)
        results['steps_completed'].append('memory_metrics')

        # STEP 10: Compare to Population Norms (all atlases)
        print("\n" + "="*80)
        print(f"STEP 10/10: Comparing to Population Norms (all atlases)")
        print("="*80)
        try:
            # Note: age and sex are optional - will fetch from user profile if not provided
            # Automatically processes all available atlases
            population_comparison = compare_to_population_norms(
                nifti_file_id=nifti_file_id,
                age=age,  # Optional: will fetch from user profile if None
                sex=sex,  # Optional: will fetch from user profile if None
                save_to_db=True,
                include_global_measures=True
            )
            results['population_comparison'] = population_comparison
            results['steps_completed'].append('population_comparison')
            print("  ✓ Population comparison completed successfully")
        except Exception as pop_error:
            print(f"  ⚠️  Population comparison skipped: {str(pop_error)}")
            print("     This is optional and may not be available for all scans")
            results['population_comparison_skipped'] = str(pop_error)

        # SUCCESS!
        print("\n" + "="*80)
        print("🎉 PIPELINE COMPLETE!")
        print(f"Steps completed: {len(results['steps_completed'])}/10")
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
    parser.add_argument('--age', type=int, help='Age in years (optional - will fetch from user profile if not provided)')
    parser.add_argument('--sex', choices=['M', 'F', 'U'], help='Sex (M/F/U, optional - will fetch from user profile if not provided)')

    args = parser.parse_args()

    print("=== MRI PROCESSING PIPELINE (LOCAL) ===")
    print("This will run the complete processing pipeline in this process:")
    print("1. Resample ALL atlases (~1 min)")
    print("2. Calculate ROI volumes for ALL atlases (~1 min)")
    print("3. FreeSurfer recon-all (4-8 hours)")
    print("4. Store FreeSurfer files (~1 min)")
    print("5. Generate surface files (.asc) (~1 min)")
    print("6. Parse statistics (~30s)")
    print("7. Generate visualization data (aparc) (~30s)")
    print("8. Calculate memory metrics (~30s)")
    print("9. Compare to population norms for ALL atlases (~1 min)")
    print("\nAtlases: All available (Harvard-Oxford, HCPex)")
    print("Total expected time: 4-8 hours")
    print("All steps run directly without API calls\n")

    try:
        result = mri_processing_pipeline(
            nifti_file_id=args.nifti_file_id,
            user_id=args.user_id,
            age=args.age,
            sex=args.sex
        )
        print("\n✅ Pipeline successful!")
        print(f"Completed steps: {result['steps_completed']}")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {str(e)}")
        os._exit(1)

    os._exit(0)