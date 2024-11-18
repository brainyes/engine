from src.data import supabase
from src.utilities import save_to_temp_file


def get_nifti_file(nifti_file_or_id, download = False):
    if not isinstance(nifti_file_or_id, dict):
        response = supabase.schema("public").table("nifti_files").select("*").eq("id", nifti_file_or_id).maybe_single().execute()
        nifti_file = response.data
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
    return (supabase.schema("public").table("usermeta")
            .select("meta_value")
            .eq("user_id", user_id).eq("meta_key", meta_key)
            .maybe_single().execute()).data['meta_value']