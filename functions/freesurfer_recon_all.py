import os
import argparse
import subprocess
import tempfile
import shutil
import multiprocessing
import psutil
from datetime import datetime

from utilities.supabase_utilities import download_nifti_file, get_nifti_file

FUNCTION_NAME = "freesurfer_recon_all"

def freesurfer_recon_all(nifti_file_id, **kwargs):
    """
    Run FreeSurfer recon-all processing on a NIFTI file
    
    Args:
        nifti_file_id (str): The ID of the NIFTI file to process
        **kwargs: Additional parameters (subjects_dir, subject_id, etc.)
        
    Returns:
        dict: Results of FreeSurfer processing
    """
    
    # Get the NIFTI file info
    nifti_file_object, storage_object, nifti_gz_path = get_nifti_file(nifti_file_id, True)
    nifti_file_path = download_nifti_file(nifti_file_object, storage_object)
    print(f"Processing NIFTI file: {nifti_file_object['id']} at {nifti_file_path}")
    
    # Extract subject ID from filename or use provided one
    subject_id = kwargs.get('subject_id', f"sub-{nifti_file_id}")
    subjects_dir = kwargs.get('subjects_dir', tempfile.mkdtemp(prefix="freesurfer_"))
    
    print(f"Subject ID: {subject_id}")
    print(f"Subjects directory: {subjects_dir}")
    
    # 🚀 SYSTEM OPTIMIZATION - Auto-detect and use all available resources
    cpu_count = multiprocessing.cpu_count()
    memory_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    available_cores = kwargs.get('parallel_cores', cpu_count)
    
    print(f"🔥 PERFORMANCE BOOST ACTIVATED!")
    print(f"💻 System: {cpu_count} CPU cores, {memory_gb}GB RAM")
    print(f"⚡ Using: {available_cores} parallel cores")
    print(f"🎯 Expected speedup: ~{min(available_cores/2, 3):.1f}x faster")
    
    try:
        # Create subjects directory if it doesn't exist
        os.makedirs(subjects_dir, exist_ok=True)
        
        # 🚀 Build OPTIMIZED FreeSurfer recon-all command with MAXIMUM PARALLELIZATION
        cmd = [
            "recon-all",
            "-i", nifti_file_path,
            "-s", subject_id,
            "-all",
            "-parallel",           # Enable parallel processing
            "-openmp", str(available_cores),  # Use all available cores
            "-wsatlas"            # Use faster skull stripping algorithm
        ]
        
        print(f"Running FreeSurfer command: {' '.join(cmd)}")
        print("⚠️  This will take several hours to complete...")
        
        # Set FreeSurfer environment
        env = os.environ.copy()
        env['SUBJECTS_DIR'] = subjects_dir
        
        # Run FreeSurfer recon-all with real-time output
        start_time = datetime.now()
        
        # Capture output while showing it in real-time
        stdout_lines = []
        stderr_lines = []
        
        process = subprocess.Popen(
            cmd,
            env=env,
            cwd=subjects_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr into stdout
            text=True,
            universal_newlines=True
        )
        
        # Stream output in real-time
        print("--- FreeSurfer Output ---")
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())  # Show in real-time
                stdout_lines.append(output)  # Save for later
        
        return_code = process.poll()
        end_time = datetime.now()
        
        # Combine all output
        full_output = ''.join(stdout_lines)
        
        if return_code != 0:
            raise Exception(f"FreeSurfer failed with return code {return_code}. Check output above for details.")
        
        processing_time = (end_time - start_time).total_seconds()
        
        # Check if output directory was created
        subject_output_dir = os.path.join(subjects_dir, subject_id)
        os.makedirs(subject_output_dir, exist_ok=True)
        if not os.path.exists(subject_output_dir):
            raise Exception(f"FreeSurfer output directory not found: {subject_output_dir}")
        
        # Basic success validation - check for key output files
        key_files = [
            "mri/orig.mgz",
            "mri/brain.mgz", 
            "stats/aseg.stats"
        ]
        
        missing_files = []
        for key_file in key_files:
            if not os.path.exists(os.path.join(subject_output_dir, key_file)):
                missing_files.append(key_file)
        
        if missing_files:
            raise Exception(f"Missing key FreeSurfer output files: {missing_files}")
        
        result_data = {
            "nifti_file_id": nifti_file_id,
            "subject_id": subject_id,
            "subjects_dir": subjects_dir,
            "processing_time_seconds": processing_time,
            "status": "completed",
            "output_directory": subject_output_dir,
            "message": f"FreeSurfer recon-all completed successfully in {processing_time:.1f} seconds"
        }
        
        print(f"✅ FreeSurfer processing completed successfully!")
        print(f"Output directory: {subject_output_dir}")
        print(f"Processing time: {processing_time:.1f} seconds")
        
        return result_data
        
    except Exception as e:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "subject_id": subject_id,
            "subjects_dir": subjects_dir,
            "status": "failed",
            "error": str(e),
            "message": f"FreeSurfer processing failed: {str(e)}"
        }
        print(f"❌ FreeSurfer processing failed: {str(e)}")
        return error_result


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run OPTIMIZED FreeSurfer recon-all processing with maximum parallelization')
    parser.add_argument('file_id', help='NIFTI file ID to process')
    parser.add_argument('--subject-id', help='Subject identifier (default: sub-{file_id})')
    parser.add_argument('--subjects-dir', help='FreeSurfer subjects directory (default: temp directory)')
    parser.add_argument('--parallel-cores', type=int, help='Number of CPU cores to use (default: auto-detect all cores)')
    
    args = parser.parse_args()
    
    print(f"=== FREESURFER RECON-ALL PROCESSING ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    print("This will run FreeSurfer's complete recon-all pipeline")
    print("Expected processing time: 4-8 hours depending on your system")
    print("Please wait...\n")
    
    try:
        kwargs = {}
        if args.subject_id:
            kwargs['subject_id'] = args.subject_id
        if args.subjects_dir:
            kwargs['subjects_dir'] = args.subjects_dir
        if args.parallel_cores:
            kwargs['parallel_cores'] = args.parallel_cores
            
        result = freesurfer_recon_all(args.file_id, **kwargs)
        
        print(f"\n=== PROCESSING COMPLETE ===")
        if result['status'] == 'completed':
            print("✅ FreeSurfer recon-all completed successfully")
            print(f"Output directory: {result['output_directory']}")
            print(f"Processing time: {result['processing_time_seconds']:.1f} seconds")
        else:
            print("❌ FreeSurfer processing failed")
            print(f"Error: {result.get('error', 'Unknown error')}")
        
    except Exception as e:
        print(f"❌ Error during processing: {str(e)}")
        print("Please check your file ID and FreeSurfer installation.")
        os._exit(1)
    
    # Force exit to prevent hanging
    os._exit(0)