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

import inngest
import os
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path
import pydicom
from datetime import datetime

from utilities.inngest import client as inngest_client
from utilities.data import supabase

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

            # Anonymize and extract metadata
            metadata = anonymize_dicom(local_file_path)
            if metadata:
                all_metadata.append(metadata)

        print(f"Downloaded and anonymized {len(files_response)} DICOM files")

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
            nifti_data = f.read()

        timestamp = int(datetime.now().timestamp() * 1000)
        storage_path = f"{user_id}/{timestamp}_from_dicom.nii.gz"

        upload_response = supabase.storage.from_('nifti_gz_files').upload(
            storage_path,
            nifti_data,
            {'contentType': 'application/gzip'}
        )

        # 5. Create nifti_files database record
        nifti_record = {
            'id': upload_response.data['id'],
            'user_id': user_id,
            'file_type': 'nii',
        }

        nifti_response = supabase.table('nifti_files') \
            .insert(nifti_record) \
            .execute()

        nifti_file_id = nifti_response.data[0]['id']

        # 6. Update dicom_series table with nifti_file_id
        supabase.table('dicom_series') \
            .update({
                'nifti_file_id': nifti_file_id,
                'conversion_completed_at': datetime.now().isoformat()
            }) \
            .eq('id', dicom_series_id) \
            .execute()

        # 7. Optionally delete DICOM files from storage (to save space)
        # Uncomment if you want to delete after successful conversion
        # files_to_delete = [f"{dicom_path}/{file_info['name']}" for file_info in files_response]
        # supabase.storage.from_('nifti_gz_files').remove(files_to_delete)

        result = {
            'dicom_series_id': dicom_series_id,
            'nifti_file_id': nifti_file_id,
            'file_count': len(files_response),
            'series_description': all_metadata[0].get('series_description') if all_metadata else '',
            'status': 'converted',
            'message': f'Successfully converted {len(files_response)} DICOM files to NIfTI'
        }

        print(f"Conversion completed: {result}")
        return result

    finally:
        # Cleanup temporary directories
        shutil.rmtree(dicom_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)


@inngest_client.create_function(
    fn_id=FUNCTION_NAME,
    trigger=inngest.TriggerEvent(event=f"{FUNCTION_NAME}_requested"),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    """Inngest function wrapper for workflow automation"""
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    result = await step.run("execute-function", lambda: dicom_to_nifti_converter(**parameters))

    # Trigger FreeSurfer pipeline with the new NIfTI file
    if result.get('nifti_file_id'):
        await inngest_client.send(
            inngest.Event(
                name="mri_processing_pipeline_requested",
                data={
                    "nifti_file_id": result['nifti_file_id'],
                    "user_id": parameters.get('user_id')
                }
            )
        )

    return result


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
        print(f"\nNext step: FreeSurfer processing will start automatically")

    except Exception as e:
        print(f"❌ Error during conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        os._exit(1)

    os._exit(0)
