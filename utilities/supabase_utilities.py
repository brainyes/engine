import base64
import gzip
import time

from io import BytesIO

from utilities.data import supabase
from utilities.utilities import save_to_temp_file, cast_value

OUTPUT_TYPE_FILE = "file"
OUTPUT_TYPE_PANDAS = "pandas"


def retry_on_timeout(func, max_retries=3, backoff_base=2):
    """
    Retry wrapper for Supabase operations that may timeout

    Args:
        func: Lambda/function to execute (should take no arguments)
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_base: Base for exponential backoff in seconds (default: 2)

    Returns:
        Result from func() if successful

    Raises:
        Exception: Re-raises the last exception if all retries fail

    Example:
        retry_on_timeout(lambda: supabase.storage.from_("bucket").upload(path, data))
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_exception = e
            error_msg = str(e).lower()

            # Only retry on timeout errors
            if 'timed out' in error_msg or 'timeout' in error_msg:
                if attempt < max_retries - 1:
                    wait_time = backoff_base ** attempt  # Exponential backoff: 1s, 2s, 4s
                    print(f"  ⚠️  Timeout error, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue

            # Re-raise immediately if not a timeout or last attempt
            raise

    # If we get here, all retries failed
    raise last_exception


def upload_nifti_to_storage(file_data, user_id, file_suffix=""):
    """
    Upload NIFTI file data to storage with automatic compression handling.

    Creates both .nii (uncompressed) and .nii.gz (compressed) versions in storage
    and corresponding records in nifti_files table.

    Args:
        file_data: Raw file bytes (can be compressed or uncompressed)
        user_id: User ID for storage path and database record
        file_suffix: Optional suffix for filename (e.g., "_from_dicom")

    Returns:
        tuple: (nifti_file, nifti_file_zipped) - Database records for both versions

    Example:
        with open('scan.nii.gz', 'rb') as f:
            data = f.read()
        nifti_file, nifti_gz = upload_nifti_to_storage(data, user_id, "_from_dicom")
    """
    # Try to decompress first (handles .nii.gz or misnamed files)
    try:
        unzipped_content = gzip.decompress(file_data)
        zipped_content = file_data
    except (gzip.BadGzipFile, OSError):
        # File is already uncompressed (.nii)
        unzipped_content = file_data
        zipped_content = gzip.compress(file_data)

    # Generate storage paths
    timestamp = int(time.time() * 1000)
    storage_file_name = f"{user_id}/{timestamp}{file_suffix}"
    nii_path = storage_file_name + ".nii"
    nii_gz_path = storage_file_name + ".nii.gz"

    # Upload uncompressed version
    supabase.storage.from_("nifti_gz_files").upload(
        file=unzipped_content,
        path=nii_path,
        file_options={"content-type": "application/octet-stream; charset=binary", "upsert": "true"}
    )

    # Query storage.objects to get the storage ID
    storage_objects = supabase.schema('storage').table('objects').select('id').eq('bucket_id', 'nifti_gz_files').eq('name', nii_path).execute()
    if not storage_objects.data or len(storage_objects.data) == 0:
        raise Exception(f"Could not find storage object for path: {nii_path}")
    storage_id = storage_objects.data[0]['id']

    # Create nifti_files record
    nifti_file = supabase.schema("public").table("nifti_files").upsert(
        {"id": storage_id, "user_id": user_id, "file_type": "nii"}
    ).execute().data[0]

    # Upload compressed version
    supabase.storage.from_("nifti_gz_files").upload(
        file=zipped_content,
        path=nii_gz_path,
        file_options={"content-type": "application/gzip", "upsert": "true"}
    )

    # Query storage.objects to get the storage ID
    storage_objects_gz = supabase.schema('storage').table('objects').select('id').eq('bucket_id', 'nifti_gz_files').eq('name', nii_gz_path).execute()
    if not storage_objects_gz.data or len(storage_objects_gz.data) == 0:
        raise Exception(f"Could not find storage object for path: {nii_gz_path}")
    storage_id_gz = storage_objects_gz.data[0]['id']

    # Create nifti_files record for compressed version
    nifti_file_zipped = supabase.schema("public").table("nifti_files").upsert(
        {"id": storage_id_gz, "parent_nifti_file_id": nifti_file['id'], "user_id": user_id, "file_type": "nii.gz"}
    ).execute().data

    return nifti_file, nifti_file_zipped

def get_all_nifti_files():
    response = supabase.schema("public").table("nifti_files").select("*").execute()
    nifti_files = response.data
    return nifti_files

def get_roi_volumes_for_niftis(atlas_name=None):
    """
    Get ROI volumes for all NIFTI files, optionally filtered by atlas

    Args:
        atlas_name: Optional atlas name to filter by. If None, returns all atlases.

    Returns:
        Dictionary: {nifti_file_id: {label: volume}}
        If atlas_name is None: {nifti_file_id: {atlas_name: {label: volume}}}

    Example:
        # Get volumes for specific atlas
        volumes = get_roi_volumes_for_niftis('hcpex')
        # Returns: {nifti_id: {label: volume, ...}, ...}

        # Get all volumes (grouped by atlas)
        all_volumes = get_roi_volumes_for_niftis()
        # Returns: {nifti_id: {'harvard-oxford': {label: volume}, 'hcpex': {label: volume}}, ...}
    """
    query = supabase.schema("public").table("roi_volumes").select("*")

    if atlas_name:
        query = query.eq("atlas_name", atlas_name)

    response = query.execute()
    grouped_data = {}

    for record in response.data:
        nifti_file_id = record['nifti_file_id']
        current_atlas = record.get('atlas_name', 'harvard-oxford')  # Handle legacy data

        if atlas_name:
            # Simple grouping by nifti_file_id only
            if nifti_file_id not in grouped_data:
                grouped_data[nifti_file_id] = {}
            grouped_data[nifti_file_id][record['label']] = record['volume']
        else:
            # Group by nifti_file_id and atlas_name
            if nifti_file_id not in grouped_data:
                grouped_data[nifti_file_id] = {}
            if current_atlas not in grouped_data[nifti_file_id]:
                grouped_data[nifti_file_id][current_atlas] = {}
            grouped_data[nifti_file_id][current_atlas][record['label']] = record['volume']

    return grouped_data

def get_nifti_file(nifti_file_or_id, download = False):
    if not isinstance(nifti_file_or_id, dict):
        response = supabase.schema("public").table("nifti_files").select("*").eq("id", nifti_file_or_id).maybe_single().execute()
        nifti_file = response.data if response else None
        print("found nifti file: ", nifti_file)
    else:
        nifti_file = nifti_file_or_id

    response = supabase.schema("storage").table("objects").select("*").eq("id",
                                                                          nifti_file['id']).maybe_single().execute()
    storage_object = response.data

    nifti_gz_path = None
    if download:
        nifti_gz_data = supabase.storage.from_("nifti_gz_files").download(storage_object['name'])
        nifti_gz_path = save_to_temp_file(nifti_gz_data, storage_object['name'])

    return nifti_file, storage_object, nifti_gz_path

def download_nifti_file(nifti_file = None, storage_object = None):
    if nifti_file is None and storage_object is None:
        raise Exception('Must specify either nifti_file or storage_object')

    if storage_object is None:
        response = supabase.schema("storage").table("objects").select("*").eq("id",
                                                                              nifti_file['id']).maybe_single().execute()
        storage_object = response.data

    nifti_gz_data = supabase.storage.from_("nifti_gz_files").download(storage_object['name'])
    return save_to_temp_file(nifti_gz_data, storage_object['name'])

def upload_resampled_atlas(user_id, nifti_file_id, file_data, atlas_name='hcpex'):
    """
    Upload resampled atlas for a given nifti file.
    Uses known storage path pattern: {user_id}/{nifti_file_id}/{atlas_name}-resampled.nii.gz

    Args:
        user_id: The user ID (for RLS compliance)
        nifti_file_id: The nifti file ID
        file_data: The file data (bytes) to upload - should be gzipped
        atlas_name: Name of the atlas (default: 'hcpex')

    Returns:
        The storage path where the file was uploaded

    Example:
        upload_resampled_atlas(user_id, nifti_id, data, 'hcpex')
        # Creates: user_id/nifti_id/hcpex-resampled.nii.gz
    """
    storage_path = f"{user_id}/{nifti_file_id}/{atlas_name}-resampled.nii.gz"
    supabase.storage.from_("nifti_gz_files").upload(
        file=file_data,
        path=storage_path,
        file_options={"content-type": "application/gzip", "upsert": "true"}
    )
    return storage_path

def download_resampled_atlas(user_id, nifti_file_id, atlas_name='hcpex'):
    """
    Download resampled atlas for a given nifti file.
    Uses known storage path pattern: {user_id}/{nifti_file_id}/{atlas_name}-resampled.nii.gz

    Args:
        user_id: The user ID
        nifti_file_id: The nifti file ID
        atlas_name: Name of the atlas (default: 'hcpex')

    Returns:
        Path to temporary file containing atlas data

    Example:
        atlas_path = download_resampled_atlas(user_id, nifti_id, 'hcpex')
    """
    storage_path = f"{user_id}/{nifti_file_id}/{atlas_name}-resampled.nii.gz"
    atlas_data = supabase.storage.from_("nifti_gz_files").download(storage_path)
    # Use .nii.gz extension explicitly (save_to_temp_file only catches single extensions)
    return save_to_temp_file(atlas_data, ".nii.gz")

def get_user_meta(user_id, meta_key):
    meta_value = (supabase.schema("public").table("usermeta")
            .select("meta_value")
            .eq("user_id", user_id).eq("meta_key", meta_key)
            .maybe_single().execute())
    if meta_value:
        return cast_value(meta_value.data['meta_value'])
    return None

def get_roi_volumes(nifti_file_id, atlas_name=None):
    """
    Get ROI volumes for a specific NIFTI file

    Args:
        nifti_file_id: The NIFTI file ID
        atlas_name: Optional atlas name to filter by. If None, returns all atlases.

    Returns:
        Dictionary mapping label -> volume

    Example:
        # Get volumes for specific atlas
        volumes = get_roi_volumes(nifti_id, 'hcpex')

        # Get all volumes (all atlases)
        all_volumes = get_roi_volumes(nifti_id)
    """
    query = supabase.schema("public").table("roi_volumes").select("*").eq("nifti_file_id", nifti_file_id)

    if atlas_name:
        query = query.eq("atlas_name", atlas_name)

    response = query.execute()
    volumes = response.data
    roi_volumes = {}
    for volume in volumes:
        roi_volumes[volume['label']] = volume['volume']
    return roi_volumes

def save_insight_type(slug):
    response = supabase.schema("public").table("insights").select("*").eq("slug",
                                                                          slug).maybe_single().execute()
    if response is None:
        response = (supabase.schema("public").table("insights").upsert({
            "slug": slug
        }).execute())
        response = response.data[0]
    return response

def get_user_insight(name, user_id, nifti_file_id = None):
    response = supabase.schema("public").table("insights").select("*").eq("slug",
                                                                          name).maybe_single().execute()
    if response is None:
        raise Exception('Insight type {} not found'.format(name))
    insight = response.data
    response = (supabase.schema("public").table("user_insights")
                    .upsert({
        "insight_id": insight['id'],
        "user_id": user_id,
        "nifti_file_id": nifti_file_id,
    }, on_conflict="insight_id, user_id, nifti_file_id").execute())
    return response.data[0]

def save_insight_output_file(user_insight_id, output_name, file):
    storage_file_name = str(user_insight_id) + "/" + str(output_name)
    supabase.storage.from_("user_insight_outputs").upload(
        file=file, path=storage_file_name,
        file_options={"upsert": "true"})
    print('Uploaded file for insight: ', output_name, storage_file_name)
    return save_insight_output_typed(user_insight_id, output_name, storage_file_name, OUTPUT_TYPE_FILE)

def save_insight_output_pandas(user_insight_id, output_name, pandas_obj):
    buffer = BytesIO()
    pandas_obj.to_csv(buffer)
    base64_encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return save_insight_output_typed(user_insight_id, output_name, base64_encoded, OUTPUT_TYPE_PANDAS)

def save_insight_output_typed(user_insight_id, output_name, output_value, output_type = None):
    response = (supabase.schema("public").table("user_insight_outputs")
                .upsert({
        "user_insight_id": user_insight_id,
        "name": output_name,
        "value": output_value,
        "type": output_type,
    }, on_conflict="user_insight_id, name").execute())
    print('Saved insight'+(" " + output_type + " " if output_type else " ")+'output: ', output_name)
    return response.data[0]

def save_insight_output(user_insight_id, output_name, output_value):
    return save_insight_outputs(user_insight_id, {output_name: output_value})

def save_insight_outputs(user_insight_id, outputs):
    upserts = []
    for key in outputs:
        upserts.append({
            "user_insight_id": user_insight_id,
            "name": key,
            "value": outputs[key],
        })
    response = (supabase.schema("public").table("user_insight_outputs")
                .upsert(upserts, on_conflict="user_insight_id, name").execute())
    print('Saved insight output(s):', outputs.keys())
    return response.data


def get_user_profile(nifti_file_id):
    """
    Get user profile (age, sex, date_of_birth, health_status) from the nifti_file's owner

    This utility function retrieves health and demographic information from the user profile
    which can be used for analytics, population comparisons, and personalized insights.

    Args:
        nifti_file_id: ID of NIFTI file (used to lookup the owner)

    Returns:
        Dictionary with user profile data including:
        - age: Age in years (int or None)
        - sex: 'M', 'F', or 'U' (unknown)
        - date_of_birth: ISO date string or None
        - health_status: Health status string (e.g., 'healthy', 'cognitive_impairment')
        - age_source: 'profile' or 'calculated_from_dob' (if age was calculated)

        Returns None if user or nifti file not found.

    Example:
        profile = get_user_profile(nifti_file_id)
        if profile and profile.get('age'):
            print(f"User age: {profile['age']}, sex: {profile['sex']}")
    """
    from datetime import datetime
    from typing import Optional

    # Get user_id from nifti_file
    nifti_response = supabase.table('nifti_files')\
        .select('user_id')\
        .eq('id', nifti_file_id)\
        .maybe_single()\
        .execute()

    if not nifti_response.data:
        return None

    user_id = nifti_response.data.get('user_id')
    if not user_id:
        return None

    # Get user profile
    user_response = supabase.table('users')\
        .select('age, sex, date_of_birth, health_status')\
        .eq('id', user_id)\
        .maybe_single()\
        .execute()

    if not user_response.data:
        return None

    profile = user_response.data

    # Calculate age from date_of_birth if available and age not set
    if profile.get('date_of_birth') and not profile.get('age'):
        try:
            dob = datetime.fromisoformat(profile['date_of_birth'].replace('Z', '+00:00'))
            today = datetime.now()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            profile['age'] = age
            profile['age_source'] = 'calculated_from_dob'
        except Exception as e:
            print(f"  ⚠️  Could not calculate age from date_of_birth: {e}")
    elif profile.get('age'):
        profile['age_source'] = 'profile'

    return profile