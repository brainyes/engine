from data import supabase
from utilities import save_to_temp_file, cast_value


def get_all_nifti_files():
    response = supabase.schema("public").table("nifti_files").select("*").execute()
    nifti_files = response.data
    return nifti_files

def get_roi_volumes_for_niftis():
    response = supabase.schema("public").table("roi_volumes").select("*").execute()
    grouped_data = {}
    # group by nifti_file_id, returned dictionary looks like:
    # {nifti_file_id: {label1: volume}}
    for record in response.data:
        nifti_file_id = record['nifti_file_id']
        if nifti_file_id not in grouped_data:
            grouped_data[nifti_file_id] = {}
        grouped_data[nifti_file_id][record['label']] = record['volume']
    return grouped_data

def get_nifti_file(nifti_file_or_id, download = False):
    if not isinstance(nifti_file_or_id, dict):
        response = supabase.schema("public").table("nifti_files").select("*").eq("id", nifti_file_or_id).maybe_single().execute()
        nifti_file = response.data if response else None
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

def get_user_meta(user_id, meta_key):
    return cast_value((supabase.schema("public").table("usermeta")
            .select("meta_value")
            .eq("user_id", user_id).eq("meta_key", meta_key)
            .maybe_single().execute()).data['meta_value'])

def get_roi_volumes(nifti_file_id):
    response = supabase.schema("public").table("roi_volumes").select("*").eq("nifti_file_id", nifti_file_id).execute()
    volumes = response.data
    roi_volumes = {}
    for volume in volumes:
        roi_volumes[volume['label']] = volume['volume']
    return roi_volumes
