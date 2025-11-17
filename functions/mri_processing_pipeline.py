import os
import traceback
from datetime import datetime

# Import all processing functions
from functions.preprocess_native_scan import preprocess_native_scan
from functions.register_to_template import register_to_template
from functions.resample_atlas_for_user_nifti import resample_atlas_for_user_nifti
from functions.calculate_roi_volumes import calculate_roi_volumes
from functions.compute_global_measures_from_rois import compute_global_measures_from_rois
from functions.prepare_volume_visualization import prepare_volume_visualization
from functions.calculate_memory_metrics import calculate_memory_metrics
from functions.compare_to_population_norms import compare_to_population_norms

# FastSurfer functions (default, ~10-20x faster)
from functions.fastsurfer_recon_all import fastsurfer_recon_all

# FreeSurfer functions (fallback)
from functions.freesurfer_recon_all import freesurfer_recon_all
from functions.freesurfer_store_files import freesurfer_store_files
from functions.freesurfer_parse_statistics import freesurfer_parse_statistics

# Shared post-processing (works with both FastSurfer and FreeSurfer)
from functions.generate_surface_files import generate_surface_files
from functions.generate_visualization_data import generate_visualization_data

FUNCTION_NAME = "mri_processing_pipeline"

def mri_processing_pipeline(
    nifti_file_id,
    user_id=None,
    age=None,
    sex='U',
    surface_pipeline='fastsurfer',  # 'fastsurfer' (default, 10-20x faster) or 'freesurfer'
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
        surface_pipeline (str): Surface processing method - 'fastsurfer' (default, ~60-90 min) or 'freesurfer' (~4-8 hours)

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

    CORE_PIPELINE_STEPS = 7
    FREESURFER_POST_STEPS = 5

    try:
        # STEP 1: Preprocess Native Scan
        print("\n" + "="*80)
        print(f"STEP 1/{CORE_PIPELINE_STEPS}: Preprocessing Native Scan")
        print("="*80)
        results['preprocessing'] = preprocess_native_scan(nifti_file_id)
        results['steps_completed'].append('preprocess_native_scan')

        # STEP 2: Register to Template
        print("\n" + "="*80)
        print(f"STEP 2/{CORE_PIPELINE_STEPS}: Registering to Template (MNI152)")
        print("="*80)
        results['registration'] = register_to_template(nifti_file_id)
        results['steps_completed'].append('register_to_template')

        # STEP 3: Resample Atlas (all atlases)
        print("\n" + "="*80)
        print(f"STEP 3/{CORE_PIPELINE_STEPS}: Resampling Atlases (all available)")
        print("="*80)
        results['resample_atlas'] = resample_atlas_for_user_nifti(nifti_file_id)
        results['steps_completed'].append('resample_atlas')

        # STEP 4: Calculate ROI Volumes (all atlases)
        print("\n" + "="*80)
        print(f"STEP 4/{CORE_PIPELINE_STEPS}: Calculating ROI Volumes (all atlases)")
        print("="*80)
        results['roi_volumes'] = calculate_roi_volumes(nifti_file_id)
        results['steps_completed'].append('roi_volumes')

        # Derive global measures from ROI volumes (for scans without FreeSurfer stats yet)
        try:
            results['global_measures'] = compute_global_measures_from_rois(
                nifti_file_id,
                overwrite=False,
                verbose=True
            )
        except Exception as gm_error:
            print(f"  ⚠️  Skipped ROI-derived global measures: {gm_error}")

        # STEP 5: Prepare Volume Visualization
        print("\n" + "="*80)
        print(f"STEP 5/{CORE_PIPELINE_STEPS}: Preparing Volume Visualization (Region Meshes)")
        print("="*80)
        results['volume_visualization'] = prepare_volume_visualization(nifti_file_id)
        results['steps_completed'].append('volume_visualization')

        # STEP 6: Calculate Memory Metrics
        print("\n" + "="*80)
        print(f"STEP 6/{CORE_PIPELINE_STEPS}: Calculating Memory Metrics")
        print("="*80)
        results['memory_metrics'] = calculate_memory_metrics(nifti_file_id)
        results['steps_completed'].append('memory_metrics')

        # STEP 7: Compare to Population Norms (all atlases)
        print("\n" + "="*80)
        print(f"STEP 7/{CORE_PIPELINE_STEPS}: Comparing to Population Norms (all atlases)")
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

        core_steps_completed = len(results['steps_completed'])

        # Surface Processing Post-Pipeline (FastSurfer or FreeSurfer)
        print("\n" + "="*80)
        print("CORE PIPELINE COMPLETE ✅")
        print(f"Core steps completed: {core_steps_completed}/{CORE_PIPELINE_STEPS}")
        if surface_pipeline == 'fastsurfer':
            print("Initiating FastSurfer post-processing (10-20x faster)...")
        else:
            print("Initiating FreeSurfer post-processing...")
        print("="*80)

        # POST 1: Surface Reconstruction (FastSurfer or FreeSurfer)
        print("\n" + "="*80)
        if surface_pipeline == 'fastsurfer':
            print("SURFACE POST 1/5: FastSurfer Recon-All")
            print("⚠️  This step takes 60-90 minutes (full pipeline)")
            print("="*80)
            surface_result = fastsurfer_recon_all(nifti_file_id, user_id=user_id)
            results['fastsurfer'] = surface_result
            results['steps_completed'].append('fastsurfer_recon_all')
            results['processing_method'] = 'fastsurfer'
        else:
            print("SURFACE POST 1/5: FreeSurfer Recon-All")
            print("⚠️  This step takes 4-8 hours")
            print("="*80)
            surface_result = freesurfer_recon_all(nifti_file_id, user_id=user_id)
            results['freesurfer'] = surface_result
            results['steps_completed'].append('freesurfer_recon_all')
            results['processing_method'] = 'freesurfer'

        # Extract surface processing outputs for next steps
        surface_dir = surface_result['output_directory']
        subject_id = surface_result['subject_id']

        print(f"  📁 Surface output: {surface_dir}")
        print(f"  👤 Subject ID: {subject_id}")

        # POST 2: Store Surface Files
        print("\n" + "="*80)
        print("SURFACE POST 2/5: Storing Surface Files")
        print("="*80)
        results['store_files'] = freesurfer_store_files(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=surface_dir,
            subject_id=subject_id
        )
        results['steps_completed'].append('store_files')

        # POST 3: Generate Surface Files (.asc)
        print("\n" + "="*80)
        print("SURFACE POST 3/5: Generating Surface Files (.asc)")
        print("="*80)
        results['surface_files'] = generate_surface_files(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=surface_dir,  # Works with both FastSurfer and FreeSurfer
            subject_id=subject_id
        )
        results['steps_completed'].append('surface_files')

        # POST 4: Parse Statistics
        print("\n" + "="*80)
        print("SURFACE POST 4/5: Parsing Statistics")
        print("="*80)
        results['parse_statistics'] = freesurfer_parse_statistics(
            nifti_file_id=nifti_file_id,
            freesurfer_output_directory=surface_dir,
            subject_id=subject_id
        )
        results['steps_completed'].append('parse_statistics')

        # POST 5: Generate Visualization Data
        print("\n" + "="*80)
        print("SURFACE POST 5/5: Generating Visualization Data from FreeSurfer output")
        print("="*80)
        results['visualization'] = generate_visualization_data(
            nifti_file_id=nifti_file_id,
            parcellation='aparc'  # Use standard Desikan-Killiany atlas
        )
        results['steps_completed'].append('visualization_data')

        post_steps_completed = len(results['steps_completed']) - core_steps_completed

        # SUCCESS!
        print("\n" + "="*80)
        print("🎉 PIPELINE COMPLETE!")
        print(f"Core steps completed: {core_steps_completed}/{CORE_PIPELINE_STEPS}")
        print(f"FreeSurfer post steps completed: {post_steps_completed}/{FREESURFER_POST_STEPS}")
        print(f"Total steps completed: {len(results['steps_completed'])}")
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
    parser.add_argument('--surface-pipeline', choices=['fastsurfer', 'freesurfer'], default='fastsurfer',
                       help='Surface processing method: fastsurfer (default, ~60-90 min) or freesurfer (~4-8 hours)')

    args = parser.parse_args()

    print("=== MRI PROCESSING PIPELINE (LOCAL) ===")
    print("This will run the complete processing pipeline in this process:")
    print("1. Preprocess native scan (~5 min)")
    print("2. Register to template (~5-10 min)")
    print("3. Resample ALL atlases (~1 min)")
    print("4. Calculate ROI volumes for ALL atlases (~1 min)")
    print("5. Prepare volume visualization (~30s)")
    print("6. Calculate memory metrics (~30s)")
    print("7. Compare to population norms for ALL atlases (~1 min)")

    if args.surface_pipeline == 'fastsurfer':
        print("\nSurface post-processing with FastSurfer (DEFAULT, 10-20x faster):")
        print("  a. FastSurfer recon-all (60-90 minutes)")
    else:
        print("\nSurface post-processing with FreeSurfer (SLOWER, traditional):")
        print("  a. FreeSurfer recon-all (4-8 hours)")

    print("  b. Store FastSurfer files (~1 min)")
    print("  c. Generate surface files (.asc) (~1 min)")
    print("  d. Parse statistics (~30s)")
    print("  e. Generate visualization data (aparc) (~30s)")

    print("\nAtlases: All available (Harvard-Oxford, HCPex)")
    print("All steps run directly without API calls\n")

    try:
        result = mri_processing_pipeline(
            nifti_file_id=args.nifti_file_id,
            user_id=args.user_id,
            age=args.age,
            sex=args.sex,
            surface_pipeline=args.surface_pipeline
        )
        print("\n✅ Pipeline successful!")
        print(f"Completed steps: {result['steps_completed']}")
        print(f"Processing method: {result['processing_method']}")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {str(e)}")
        os._exit(1)

    os._exit(0)
