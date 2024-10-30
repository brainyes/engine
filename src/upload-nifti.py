from data import supabase


def upload_nifti(nifti_gz, owner_id, owner_type='sample'):
    user = supabase.auth.sign_in_anonymously(
        {"options": {"data": {"owner_id": owner_id, "owner_type": owner_type}}}
    )

    with open(nifti_gz, 'rb') as f:
        return supabase.storage.from_("nifti_gz_files").upload(file=f, path=(user.id + "/"))
