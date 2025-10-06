import inngest
import os
import argparse
import shutil
import gzip
from datetime import datetime
from pathlib import Path

from utilities.inngest import client as inngest_client
from utilities.data import supabase

FUNCTION_NAME = "freesurfer_store_files"

def freesurfer_store_files(nifti_file_id, freesurfer_output_directory, subject_id=None, storage_mode="complete", **kwargs):
    """
    Upload FreeSurfer binary outputs to object storage and create file inventory.
    
    Args:
        nifti_file_id (str): The ID of the original NIFTI file
        freesurfer_output_directory (str): Path to FreeSurfer subject output directory
        subject_id (str): FreeSurfer subject identifier
        storage_mode (str): "essential" (~50MB) or "complete" (~230MB)
        **kwargs: Additional parameters
        
    Returns:
        dict: Results of file storage operation
    """
    
    print(f"Storing FreeSurfer files for NIFTI file: {nifti_file_id}")
    print(f"FreeSurfer output directory: {freesurfer_output_directory}")
    print(f"Storage mode: {storage_mode}")
    
    if not os.path.exists(freesurfer_output_directory):
        raise FileNotFoundError(f"FreeSurfer output directory not found: {freesurfer_output_directory}")
    
    # Extract subject ID from directory if not provided
    if not subject_id:
        subject_id = os.path.basename(freesurfer_output_directory)
    
    # Define file categories for storage modes
    essential_files = {
        # Core volumes (most important)
        "mri/orig.mgz": "volumes",
        "mri/brain.mgz": "volumes", 
        "mri/aseg.mgz": "volumes",
        "mri/aparc+aseg.mgz": "volumes",
        "mri/norm.mgz": "volumes",
        
        # Key surfaces
        "surf/lh.white": "surfaces",
        "surf/rh.white": "surfaces",
        "surf/lh.pial": "surfaces", 
        "surf/rh.pial": "surfaces",
        "surf/lh.inflated": "surfaces",
        "surf/rh.inflated": "surfaces",
        "surf/lh.thickness": "surfaces",
        "surf/rh.thickness": "surfaces",
        
        # Main parcellations
        "label/lh.aparc.annot": "labels",
        "label/rh.aparc.annot": "labels",
        "label/lh.cortex.label": "labels",
        "label/rh.cortex.label": "labels",
        
        # Statistics (already in database, but good to have files)
        "stats/aseg.stats": "statistics",
        "stats/lh.aparc.stats": "statistics",
        "stats/rh.aparc.stats": "statistics"
    }
    
    complete_directories = ["mri", "surf", "label", "stats", "scripts"]
    
    try:
        # Determine which files to upload
        if storage_mode == "essential":
            files_to_upload = essential_files
            print(f"📦 Essential mode: Uploading {len(files_to_upload)} key files")
        elif storage_mode == "complete":
            files_to_upload = {}
            for directory in complete_directories:
                dir_path = os.path.join(freesurfer_output_directory, directory)
                if os.path.exists(dir_path):
                    for root, dirs, files in os.walk(dir_path):
                        for file in files:
                            # Skip temp files and duplicates
                            if file.startswith('.') or file.endswith('.bak'):
                                continue
                            
                            rel_path = os.path.relpath(os.path.join(root, file), freesurfer_output_directory)
                            category = directory
                            files_to_upload[rel_path] = category
            
            print(f"📦 Complete mode: Uploading {len(files_to_upload)} files from all directories")
        else:
            raise ValueError(f"Invalid storage_mode: {storage_mode}. Use 'essential' or 'complete'")
        
        # Create storage path structure: freesurfer-outputs/{nifti_file_id}/
        storage_base_path = f"{nifti_file_id}"
        
        uploaded_files = []
        upload_errors = []
        total_size = 0
        
        print(f"🚀 Starting file uploads to storage bucket...")
        
        for rel_file_path, category in files_to_upload.items():
            local_file_path = os.path.join(freesurfer_output_directory, rel_file_path)
            
            if not os.path.exists(local_file_path):
                print(f"⚠️  Skipping missing file: {rel_file_path}")
                continue
            
            try:
                # Get file info
                file_size = os.path.getsize(local_file_path)
                total_size += file_size
                
                # Create storage path
                storage_path = f"{storage_base_path}/{rel_file_path}"
                
                # Read and upload file
                with open(local_file_path, 'rb') as f:
                    file_data = f.read()
                
                # Upload to Supabase storage
                response = supabase.storage.from_("freesurfer-outputs").upload(
                    file=file_data,
                    path=storage_path,
                    file_options={"upsert": "true"}
                )
                
                # Record successful upload
                uploaded_files.append({
                    "local_path": rel_file_path,
                    "storage_path": storage_path,
                    "category": category,
                    "size_bytes": file_size,
                    "uploaded_at": datetime.now().isoformat()
                })
                
                print(f"✅ Uploaded: {rel_file_path} ({file_size:,} bytes)")
                
            except Exception as e:
                error_info = {
                    "file_path": rel_file_path,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                upload_errors.append(error_info)
                print(f"❌ Failed to upload {rel_file_path}: {e}")
        
        # Files are automatically tracked in storage.objects table by Supabase
        print(f"📝 Files stored in bucket 'freesurfer-outputs' under path: {storage_base_path}")
        print(f"💡 Query storage.objects table with path LIKE '{storage_base_path}%' to find files")
        
        # Calculate storage statistics
        total_size_mb = total_size / (1024 * 1024)
        success_rate = len(uploaded_files) / len(files_to_upload) * 100 if files_to_upload else 100
        
        result = {
            "nifti_file_id": nifti_file_id,
            "subject_id": subject_id,
            "freesurfer_output_directory": freesurfer_output_directory,
            "storage_mode": storage_mode,
            "status": "completed" if len(upload_errors) == 0 else "partial",
            "storage_stats": {
                "files_attempted": len(files_to_upload),
                "files_uploaded": len(uploaded_files),
                "files_failed": len(upload_errors),
                "total_size_mb": round(total_size_mb, 1),
                "success_rate_percent": round(success_rate, 1),
                "storage_base_path": storage_base_path
            },
            "uploaded_files": uploaded_files,
            "upload_errors": upload_errors,
            "message": f"Uploaded {len(uploaded_files)} files ({total_size_mb:.1f}MB) to object storage"
        }
        
        print(f"✅ File storage completed!")
        print(f"📊 Stats: {len(uploaded_files)}/{len(files_to_upload)} files, {total_size_mb:.1f}MB")
        print(f"🎯 Success rate: {success_rate:.1f}%")
        if upload_errors:
            print(f"⚠️  {len(upload_errors)} files failed to upload")
        
        return result
        
    except Exception as e:
        error_result = {
            "nifti_file_id": nifti_file_id,
            "subject_id": subject_id,
            "freesurfer_output_directory": freesurfer_output_directory,
            "storage_mode": storage_mode,
            "status": "failed",
            "error": str(e),
            "message": f"FreeSurfer file storage failed: {str(e)}"
        }
        print(f"❌ File storage failed: {str(e)}")
        return error_result


@inngest_client.create_function(
    fn_id=FUNCTION_NAME,
    trigger=inngest.TriggerEvent(event=f"{FUNCTION_NAME}_requested"),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    """Inngest function wrapper for FreeSurfer file storage"""
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    result = await step.run("store-files", lambda: freesurfer_store_files(**parameters))
    
    return result


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Store FreeSurfer binary outputs to object storage')
    parser.add_argument('nifti_file_id', help='NIFTI file ID')
    parser.add_argument('freesurfer_output_directory', help='Path to FreeSurfer subject output directory')
    parser.add_argument('--subject-id', help='FreeSurfer subject identifier')
    parser.add_argument('--storage-mode', choices=['essential', 'complete'], default='complete',
                       help='Storage mode: essential (~50MB) or complete (default, ~230MB)')
    
    args = parser.parse_args()
    
    print(f"=== FREESURFER FILE STORAGE ===")
    print(f"NIFTI file ID: {args.nifti_file_id}")
    print(f"FreeSurfer output directory: {args.freesurfer_output_directory}")
    print(f"Storage mode: {args.storage_mode}")
    print("This will upload binary files to object storage")
    print("Please wait...\n")
    
    try:
        kwargs = {}
        if args.subject_id:
            kwargs['subject_id'] = args.subject_id
            
        result = freesurfer_store_files(
            args.nifti_file_id, 
            args.freesurfer_output_directory,
            storage_mode=args.storage_mode,
            **kwargs
        )
        
        print(f"\n=== STORAGE COMPLETE ===")
        if result['status'] in ['completed', 'partial']:
            print("✅ FreeSurfer files stored successfully")
            stats = result['storage_stats']
            print(f"Files uploaded: {stats['files_uploaded']}/{stats['files_attempted']}")
            print(f"Total size: {stats['total_size_mb']}MB")
            print(f"Success rate: {stats['success_rate_percent']}%")
            print(f"Storage path: {stats['storage_base_path']}")
            
            if result['status'] == 'partial':
                print(f"⚠️  {stats['files_failed']} files failed to upload")
        else:
            print("❌ File storage failed")
            print(f"Error: {result.get('error', 'Unknown error')}")
        
    except Exception as e:
        print(f"❌ Error during storage: {str(e)}")
        print("Please check your paths and storage configuration.")
        os._exit(1)
    
    # Force exit to prevent hanging
    os._exit(0)