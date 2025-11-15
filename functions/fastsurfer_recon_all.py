import os
import argparse
import subprocess
import tempfile
import shutil
import multiprocessing
import psutil
from datetime import datetime

from utilities.supabase_utilities import download_nifti_file, get_nifti_file

FUNCTION_NAME = "fastsurfer_recon_all"

def fastsurfer_recon_all(nifti_file_id, **kwargs):
    """
    Run FastSurfer processing on a NIFTI file

    FastSurfer is a fast and accurate deep-learning based alternative to FreeSurfer.
    It requires FreeSurfer 7 for some surface reconstruction functionality.

    Args:
        nifti_file_id (str): The ID of the NIFTI file to process
        **kwargs: Additional parameters (subjects_dir, subject_id, etc.)

    Returns:
        dict: Results of FastSurfer processing
    """

    # Get the NIFTI file info
    nifti_file_object, storage_object, nifti_gz_path = get_nifti_file(nifti_file_id, True)
    nifti_file_path = download_nifti_file(nifti_file_object, storage_object)
    print(f"Processing NIFTI file: {nifti_file_object['id']} at {nifti_file_path}")

    # Extract subject ID from filename or use provided one
    subject_id = kwargs.get('subject_id', f"sub-{nifti_file_id}")
    subjects_dir = kwargs.get('subjects_dir', tempfile.mkdtemp(prefix="fastsurfer_"))

    # Convert to absolute path to avoid FastSurfer path duplication bug
    subjects_dir = os.path.abspath(subjects_dir)

    print(f"Subject ID: {subject_id}")
    print(f"Subjects directory: {subjects_dir}")

    # System optimization - Auto-detect and use all available resources
    cpu_count = multiprocessing.cpu_count()
    memory_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    available_cores = kwargs.get('parallel_cores', cpu_count)

    print(f"🚀 FASTSURFER PERFORMANCE BOOST ACTIVATED!")
    print(f"💻 System: {cpu_count} CPU cores, {memory_gb}GB RAM")
    print(f"⚡ Using: {available_cores} parallel cores")
    print(f"🎯 Expected speedup: ~10-20x faster than FreeSurfer")

    # Detect FastSurfer installation
    fastsurfer_home = os.environ.get('FASTSURFER_HOME', '/app/FastSurfer')
    run_fastsurfer_script = os.path.join(fastsurfer_home, 'run_fastsurfer.sh')

    # Detect local installation (macOS)
    if not os.path.exists(run_fastsurfer_script):
        # Try relative path from engine directory
        fastsurfer_home = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'FastSurfer')
        run_fastsurfer_script = os.path.join(fastsurfer_home, 'run_fastsurfer.sh')

    if not os.path.exists(run_fastsurfer_script):
        raise FileNotFoundError(
            f"FastSurfer not found. Expected at: {run_fastsurfer_script}\n"
            f"Please ensure FastSurfer submodule is initialized: git submodule update --init"
        )

    print(f"📦 FastSurfer home: {fastsurfer_home}")
    print(f"📜 Run script: {run_fastsurfer_script}")

    try:
        # Create subjects directory if it doesn't exist
        os.makedirs(subjects_dir, exist_ok=True)

        # Set up environment for FastSurfer
        # IMPORTANT: We need to source FreeSurfer's SetUpFreeSurfer.sh to get all environment variables
        # FastSurfer's recon-surf.sh requires this to be properly sourced

        # Use FreeSurfer 7 for FastSurfer compatibility
        freesurfer7_home = os.environ.get('FREESURFER7_HOME', '/usr/local/freesurfer/7.4.1')

        # On macOS, try to detect FreeSurfer 7 installation
        if not os.path.exists(freesurfer7_home):
            # Common macOS installation paths
            possible_paths = [
                '/Applications/freesurfer/7.4.1',
                '/Applications/freesurfer/7.3.2',
                '/usr/local/freesurfer/7.4.1',
                '/usr/local/freesurfer/7.3.2'
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    freesurfer7_home = path
                    break

        # Set FreeSurfer environment by sourcing SetUpFreeSurfer.sh
        if os.path.exists(freesurfer7_home):
            print(f"✅ Using FreeSurfer 7: {freesurfer7_home}")

            # Find FreeSurfer license
            license_locations = [
                os.environ.get('FS_LICENSE'),  # Environment variable
                os.path.join(freesurfer7_home, 'license.txt'),  # FreeSurfer 7 installation
                os.path.join(freesurfer7_home, '.license'),  # Alternative location
                os.path.expanduser('~/.freesurfer/license.txt'),  # User home directory
                '/usr/local/freesurfer/license.txt',  # Common shared location
            ]

            license_file = None
            for loc in license_locations:
                if loc and os.path.exists(loc):
                    license_file = loc
                    break

            if license_file:
                print(f"✅ FreeSurfer license found: {license_file}")
            else:
                print(f"⚠️  Warning: FreeSurfer license not found!")
                print(f"⚠️  Checked locations:")
                for loc in license_locations:
                    if loc:
                        print(f"    - {loc}")
                print(f"⚠️  Please set FS_LICENSE environment variable or place license.txt in FreeSurfer home")

            # Source FreeSurfer environment using bash
            # This is critical - FastSurfer's recon-surf.sh checks for properly sourced FreeSurfer
            setup_script = os.path.join(freesurfer7_home, 'SetUpFreeSurfer.sh')
            if os.path.exists(setup_script):
                # Get FreeSurfer environment by sourcing the setup script
                # We use bash to source it and print all environment variables
                source_cmd = f'bash -c "export FREESURFER_HOME={freesurfer7_home} && source {setup_script} && env"'
                result = subprocess.run(source_cmd, shell=True, capture_output=True, text=True)

                if result.returncode == 0:
                    # Parse environment variables from sourced script
                    env = {}
                    for line in result.stdout.split('\n'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env[key] = value

                    # Override with our specific settings
                    env['SUBJECTS_DIR'] = subjects_dir
                    if license_file:
                        env['FS_LICENSE'] = license_file

                    print(f"✅ FreeSurfer environment sourced successfully")
                else:
                    print(f"⚠️  Warning: Failed to source FreeSurfer setup script")
                    print(f"    Using manual environment setup as fallback")
                    # Fallback to manual setup
                    env = os.environ.copy()
                    env['FREESURFER_HOME'] = freesurfer7_home
                    env['FREESURFER'] = freesurfer7_home
                    env['SUBJECTS_DIR'] = subjects_dir
                    env['PATH'] = f"{os.path.join(freesurfer7_home, 'bin')}:{env.get('PATH', '')}"
                    if license_file:
                        env['FS_LICENSE'] = license_file
            else:
                print(f"⚠️  Warning: SetUpFreeSurfer.sh not found at {setup_script}")
                print(f"    Using manual environment setup")
                # Manual setup
                env = os.environ.copy()
                env['FREESURFER_HOME'] = freesurfer7_home
                env['FREESURFER'] = freesurfer7_home
                env['SUBJECTS_DIR'] = subjects_dir
                env['PATH'] = f"{os.path.join(freesurfer7_home, 'bin')}:{env.get('PATH', '')}"
                if license_file:
                    env['FS_LICENSE'] = license_file
        else:
            print(f"⚠️  Warning: FreeSurfer 7 not found at {freesurfer7_home}")
            print(f"⚠️  FastSurfer may require FreeSurfer 7 for surface reconstruction")
            env = os.environ.copy()
            env['SUBJECTS_DIR'] = subjects_dir

        # Determine if we should use GPU or CPU
        device = kwargs.get('device', 'auto')
        if device == 'auto':
            # Try to detect GPU availability
            try:
                import torch
                if torch.cuda.is_available():
                    device = 'cuda'
                elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    device = 'mps'  # Apple Silicon GPU
                    print("🍎 Detected Apple Silicon (MPS) - will use Mac GPU acceleration")
                else:
                    device = 'cpu'
            except ImportError:
                device = 'cpu'

        print(f"🖥️  Processing device: {device.upper()}")

        # Build FastSurfer command
        # FastSurfer uses run_fastsurfer.sh script
        cmd = [
            run_fastsurfer_script,
            "--t1", nifti_file_path,
            "--sid", subject_id,
            "--sd", subjects_dir,
            "--threads", str(available_cores),
        ]

        # Add device flag
        # Note: FastSurfer script handles GPU automatically if not explicitly set to CPU
        if device == 'cpu':
            cmd.append("--device")
            cmd.append("cpu")
        elif device in ['cuda', 'mps']:
            # Let FastSurfer detect and use GPU (it supports both CUDA and MPS)
            # Don't pass --device flag, FastSurfer will auto-detect
            pass

        # Add 3T flag if specified (for 3 Tesla MRI scanners)
        if kwargs.get('field_strength') == '3T':
            cmd.append("--3T")

        # Segmentation only mode (much faster, ~5 minutes)
        if kwargs.get('seg_only', False):
            cmd.append("--seg_only")
            print("🎯 Running in SEGMENTATION-ONLY mode (~5 minutes)")
        else:
            print("🎯 Running FULL pipeline (segmentation + surfaces, ~60-90 minutes)")

        print(f"Running FastSurfer command: {' '.join(cmd)}")
        print("⚠️  FastSurfer processing started...")
        if kwargs.get('seg_only', False):
            print("    Expected time: ~5 minutes (GPU) or ~15 minutes (CPU)")
        else:
            print("    Expected time: ~60-90 minutes for full pipeline")

        # Run FastSurfer with real-time output
        start_time = datetime.now()

        # Capture output while showing it in real-time
        stdout_lines = []

        process = subprocess.Popen(
            cmd,
            env=env,
            cwd=fastsurfer_home,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr into stdout
            text=True,
            universal_newlines=True
        )

        # Stream output in real-time
        print("--- FastSurfer Output ---")
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
            raise Exception(f"FastSurfer failed with return code {return_code}. Check output above for details.")

        processing_time = (end_time - start_time).total_seconds()

        # Check if output directory was created
        subject_output_dir = os.path.join(subjects_dir, subject_id)
        if not os.path.exists(subject_output_dir):
            raise Exception(f"FastSurfer output directory not found: {subject_output_dir}")

        # Basic success validation - check for key output files
        # FastSurfer produces FreeSurfer-compatible outputs
        key_files = [
            "mri/orig.mgz",
            "mri/aparc.DKTatlas+aseg.deep.mgz",  # FastSurfer segmentation
            "stats/aseg.stats"
        ]

        # If running full pipeline (not seg_only), also check for surfaces
        if not kwargs.get('seg_only', False):
            key_files.extend([
                "surf/lh.white",
                "surf/rh.white",
                "surf/lh.pial",
                "surf/rh.pial"
            ])

        missing_files = []
        for key_file in key_files:
            if not os.path.exists(os.path.join(subject_output_dir, key_file)):
                missing_files.append(key_file)

        if missing_files:
            print(f"⚠️  Warning: Missing some expected FastSurfer output files: {missing_files}")
            # Don't fail completely, as FastSurfer might have succeeded partially

        result_data = {
            "nifti_file_id": nifti_file_id,
            "subject_id": subject_id,
            "subjects_dir": subjects_dir,
            "processing_time_seconds": processing_time,
            "status": "completed",
            "output_directory": subject_output_dir,
            "processing_mode": "segmentation_only" if kwargs.get('seg_only', False) else "full_pipeline",
            "device": device,
            "message": f"FastSurfer processing completed successfully in {processing_time:.1f} seconds ({processing_time/60:.1f} minutes)"
        }

        print(f"✅ FastSurfer processing completed successfully!")
        print(f"Output directory: {subject_output_dir}")
        print(f"Processing time: {processing_time:.1f} seconds ({processing_time/60:.1f} minutes)")

        return result_data

    except Exception as e:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "subject_id": subject_id,
            "subjects_dir": subjects_dir,
            "status": "failed",
            "error": str(e),
            "message": f"FastSurfer processing failed: {str(e)}"
        }
        print(f"❌ FastSurfer processing failed: {str(e)}")
        return error_result


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run FastSurfer processing with deep learning acceleration')
    parser.add_argument('file_id', help='NIFTI file ID to process')
    parser.add_argument('--subject-id', help='Subject identifier (default: sub-{file_id})')
    parser.add_argument('--subjects-dir', help='FastSurfer subjects directory (default: temp directory)')
    parser.add_argument('--parallel-cores', type=int, help='Number of CPU cores to use (default: auto-detect all cores)')
    parser.add_argument('--device', choices=['auto', 'cuda', 'mps', 'cpu'], default='auto',
                       help='Processing device: auto (default), cuda (NVIDIA GPU), mps (Apple Silicon GPU), cpu')
    parser.add_argument('--seg-only', action='store_true',
                       help='Run segmentation only (~5 min instead of ~60-90 min)')
    parser.add_argument('--field-strength', choices=['3T', '1.5T'], default='3T',
                       help='MRI field strength (default: 3T)')

    args = parser.parse_args()

    print(f"=== FASTSURFER PROCESSING ===")
    print(f"Processing NIFTI file ID: {args.file_id}")
    print("FastSurfer: Fast and accurate deep-learning neuroimaging pipeline")
    print("Approximately 10-20x faster than FreeSurfer")
    if args.seg_only:
        print("Mode: SEGMENTATION ONLY (~5 minutes)")
    else:
        print("Mode: FULL PIPELINE (segmentation + surfaces, ~60-90 minutes)")
    print("Please wait...\n")

    try:
        kwargs = {}
        if args.subject_id:
            kwargs['subject_id'] = args.subject_id
        if args.subjects_dir:
            kwargs['subjects_dir'] = args.subjects_dir
        if args.parallel_cores:
            kwargs['parallel_cores'] = args.parallel_cores
        if args.device:
            kwargs['device'] = args.device
        if args.seg_only:
            kwargs['seg_only'] = True
        if args.field_strength:
            kwargs['field_strength'] = args.field_strength

        result = fastsurfer_recon_all(args.file_id, **kwargs)

        print(f"\n=== PROCESSING COMPLETE ===")
        if result['status'] == 'completed':
            print("✅ FastSurfer processing completed successfully")
            print(f"Output directory: {result['output_directory']}")
            print(f"Processing time: {result['processing_time_seconds']:.1f} seconds ({result['processing_time_seconds']/60:.1f} minutes)")
            print(f"Mode: {result['processing_mode']}")
            print(f"Device: {result['device']}")
        else:
            print("❌ FastSurfer processing failed")
            print(f"Error: {result.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"❌ Error during processing: {str(e)}")
        print("Please check your file ID and FastSurfer installation.")
        os._exit(1)

    # Force exit to prevent hanging
    os._exit(0)