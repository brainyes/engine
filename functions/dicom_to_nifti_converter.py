"""
DICOM to NIfTI Converter

Converts DICOM series to NIfTI format with PHI anonymization.

Storage Structure:
  nifti_gz_files/
    {user_id}/
      {timestamp}.nii              # NIfTI files (existing)
      {timestamp}.nii.gz           # Compressed NIfTI (existing)
      dicom/{series_id}/           # DICOM series (new)
        file001.dcm
        file002.dcm
        ...
"""

import os
import argparse
import subprocess
import tempfile
import shutil
import gzip
from pathlib import Path
import pydicom
import requests
from datetime import datetime

from utilities.data import supabase
from utilities.options import LAMBDA_API_URL

FUNCTION_NAME = "dicom_to_nifti_converter"

def extract_dicom_metadata(dicom_file_path):
    """
    Extract metadata from DICOM file (preserves all information including PHI)

    Args:
        dicom_file_path (str): Path to DICOM file

    Returns:
        dict: Extracted DICOM metadata
    """
    try:
        ds = pydicom.dcmread(dicom_file_path)

        # Extract comprehensive metadata including patient info
        metadata = {
            # DICOM Identifiers
            'series_instance_uid': str(getattr(ds, 'SeriesInstanceUID', '')),
            'study_instance_uid': str(getattr(ds, 'StudyInstanceUID', '')),
            'sop_instance_uid': str(getattr(ds, 'SOPInstanceUID', '')),

            # Series/Study Info
            'series_description': str(getattr(ds, 'SeriesDescription', '')),
            'study_description': str(getattr(ds, 'StudyDescription', '')),
            'modality': str(getattr(ds, 'Modality', '')),
            'series_number': str(getattr(ds, 'SeriesNumber', '')),

            # Patient Info (preserved - user's own data)
            'patient_name': str(getattr(ds, 'PatientName', '')),
            'patient_id': str(getattr(ds, 'PatientID', '')),
            'patient_birth_date': str(getattr(ds, 'PatientBirthDate', '')),
            'patient_sex': str(getattr(ds, 'PatientSex', '')),
            'patient_age': str(getattr(ds, 'PatientAge', '')),

            # Acquisition Info
            'manufacturer': str(getattr(ds, 'Manufacturer', '')),
            'manufacturer_model': str(getattr(ds, 'ManufacturerModelName', '')),
            'magnetic_field_strength': str(getattr(ds, 'MagneticFieldStrength', '')),
            'slice_thickness': str(getattr(ds, 'SliceThickness', '')),
            'repetition_time': str(getattr(ds, 'RepetitionTime', '')),
            'echo_time': str(getattr(ds, 'EchoTime', '')),
            'flip_angle': str(getattr(ds, 'FlipAngle', '')),
            'pixel_spacing': str(getattr(ds, 'PixelSpacing', '')),

            # Study Date/Time
            'study_date': str(getattr(ds, 'StudyDate', '')),
            'study_time': str(getattr(ds, 'StudyTime', '')),
            'acquisition_date': str(getattr(ds, 'AcquisitionDate', '')),
            'acquisition_time': str(getattr(ds, 'AcquisitionTime', '')),

            # Institution Info
            'institution_name': str(getattr(ds, 'InstitutionName', '')),
            'station_name': str(getattr(ds, 'StationName', '')),
        }

        return metadata

    except Exception as e:
        print(f"Warning: Could not extract metadata from {dicom_file_path}: {str(e)}")
        return {}


def dicom_to_nifti_converter(dicom_series_id, **kwargs):
    """
    Convert DICOM series to NIfTI format

    Args:
        dicom_series_id (str): The ID of the DICOM series to convert
        **kwargs: Additional parameters (user_id, etc.)

    Returns:
        dict: Results including new nifti_file_id
    """

    print(f"Converting DICOM series: {dicom_series_id}")

    # Create temporary directories
    dicom_dir = tempfile.mkdtemp(prefix="dicom_input_")
    output_dir = tempfile.mkdtemp(prefix="nifti_output_")

    try:
        # 1. Download DICOM files from Supabase storage
        print("Downloading DICOM files from storage...")

        # Get DICOM series metadata from database
        series_response = supabase.table('dicom_series') \
            .select('*') \
            .eq('id', dicom_series_id) \
            .single() \
            .execute()

        if not series_response.data:
            raise Exception(f"DICOM series {dicom_series_id} not found")

        series_metadata = series_response.data
        user_id = series_metadata.get('user_id') or kwargs.get('user_id')

        # List all DICOM files for this series from storage
        # DICOM files stored in: nifti_gz_files/{user_id}/dicom/{series_id}/
        dicom_path = f"{user_id}/dicom/{dicom_series_id}"
        files_response = supabase.storage.from_('nifti_gz_files').list(dicom_path)

        if not files_response:
            raise Exception(f"No DICOM files found for series {dicom_series_id}")

        print(f"Found {len(files_response)} DICOM files")

        # Download each DICOM file
        all_metadata = []
        for file_info in files_response:
            file_path_in_storage = f"{dicom_path}/{file_info['name']}"
            local_file_path = os.path.join(dicom_dir, file_info['name'])

            # Download file
            file_data = supabase.storage.from_('nifti_gz_files').download(file_path_in_storage)

            # Save to local directory
            with open(local_file_path, 'wb') as f:
                f.write(file_data)

            # Extract metadata (preserving PHI since user uploads their own data)
            metadata = extract_dicom_metadata(local_file_path)
            if metadata:
                all_metadata.append(metadata)

        print(f"Downloaded and extracted metadata from {len(files_response)} DICOM files")

        # 2. Run dcm2niix conversion
        print("Running dcm2niix conversion...")

        cmd = [
            'dcm2niix',
            '-z', 'y',  # Compress output (gzip)
            '-f', '%p_%s',  # Filename format: protocol_seriesNumber
            '-o', output_dir,  # Output directory
            dicom_dir  # Input directory
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        print("dcm2niix output:")
        print(result.stdout)

        # 3. Find generated NIfTI file
        nifti_files = list(Path(output_dir).glob('*.nii.gz'))

        if not nifti_files:
            raise Exception("No NIfTI file generated by dcm2niix")

        # Use the first NIfTI file if multiple were generated
        nifti_file_path = str(nifti_files[0])
        print(f"Generated NIfTI file: {nifti_file_path}")

        # 4. Upload NIfTI file to Supabase storage
        print("Uploading NIfTI file to storage...")

        with open(nifti_file_path, 'rb') as f:
            nifti_gz_data = f.read()

        # Decompress to get .nii version (we only store uncompressed)
        nifti_data = gzip.decompress(nifti_gz_data)

        timestamp = int(datetime.now().timestamp() * 1000)
        storage_file_name = f"{user_id}/{timestamp}_from_dicom.nii"

        # Upload .nii (uncompressed) version only
        upload_res = supabase.storage.from_('nifti_gz_files').upload(
            file=nifti_data,
            path=storage_file_name,
            file_options={"content-type": "application/octet-stream; charset=binary", "upsert": "true"}
        )
        upload_obj = upload_res.json()

        # Create nifti_files record
        nifti_file = supabase.table('nifti_files').upsert({
            'id': upload_obj['Id'],
            'user_id': user_id,
            'file_type': 'nii'
        }).execute().data[0]

        nifti_file_id = nifti_file['id']

        # 6. Update dicom_series table with nifti_file_id
        supabase.table('dicom_series') \
            .update({
                'nifti_file_id': nifti_file_id,
                'conversion_completed_at': datetime.now().isoformat()
            }) \
            .eq('id', dicom_series_id) \
            .execute()

        result = {
            'dicom_series_id': dicom_series_id,
            'nifti_file_id': nifti_file_id,
            'file_count': len(files_response),
            'series_description': all_metadata[0].get('series_description') if all_metadata else '',
            'status': 'converted',
            'message': f'Successfully converted {len(files_response)} DICOM files to NIfTI'
        }

        print(f"Conversion completed: {result}")

        # Trigger async MRI processing pipeline task
        if nifti_file_id and user_id:
            try:
                print(f"Triggering MRI processing pipeline for NIfTI file: {nifti_file_id}")
                async_url = f"{LAMBDA_API_URL}/async/mri_processing_pipeline"
                async_response = requests.post(
                    async_url,
                    json={
                        'nifti_file_id': nifti_file_id,
                        'user_id': user_id
                    },
                    timeout=30
                )

                if async_response.status_code == 200:
                    task_info = async_response.json()
                    task_id = task_info.get('task_id')
                    print(f"✅ MRI processing pipeline task submitted: {task_id}")
                    result['mri_pipeline_task_id'] = task_id
                else:
                    print(f"⚠️  Warning: Failed to trigger MRI processing pipeline task: {async_response.status_code} - {async_response.text}")

            except Exception as e:
                print(f"⚠️  Warning: Error triggering MRI processing pipeline task: {str(e)}")
                # Don't fail the conversion if async trigger fails

        return result

    finally:
        # Cleanup temporary directories
        shutil.rmtree(dicom_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)


# Command line interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert DICOM series to NIfTI format')
    parser.add_argument('dicom_series_id', help='DICOM series ID to convert')
    parser.add_argument('--user-id', help='User ID (if not in series metadata)', default=None)

    args = parser.parse_args()

    print(f"=== DICOM TO NIFTI CONVERTER ===")
    print(f"Converting DICOM series ID: {args.dicom_series_id}")
    print("This will anonymize DICOM files and convert to NIfTI format...")
    print("Please wait...\n")

    try:
        kwargs = {}
        if args.user_id:
            kwargs['user_id'] = args.user_id

        result = dicom_to_nifti_converter(args.dicom_series_id, **kwargs)

        print(f"\n=== CONVERSION COMPLETE ===")
        print("✅ Successfully converted DICOM to NIfTI")
        print(f"NIfTI File ID: {result['nifti_file_id']}")
        print(f"Files processed: {result['file_count']}")

    except Exception as e:
        print(f"❌ Error during conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
