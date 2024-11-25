import gzip
import inngest
import time

from functions.calculate_roi_volumes import fn as calculate_roi_volumes
from functions.resample_atlas_for_user_nifti import fn as resample_atlas_for_user_nifti
from utilities.data import supabase
from utilities.inngest import client as inngest_client

# todo owner_id needs refactor. it's actually sth like users.slug or users.nickname.
#   and maybe a users.type kind of a thing to differentiate between anonymous/public people
#   and our own users
# public_id is for anonymous entries/users/persons.
#   we still represent them in our supabase user/owner system.
def upload_nifti(nifti_gz, user_id = None, public_id = None):
    if user_id is None and public_id is None:
        raise Exception('Must specify either user_id or public_id')

    if user_id is not None:
        raise Exception('Non-sample users are not supported yet')

    if user_id is not None:
        user_response = supabase.auth.admin.get_user_by_id(user_id)
        user = user_response.user
    else:
        new_anonymous_user_auth = supabase.auth.sign_in_anonymously(
            {"options": {"data": {"user_type_public_id": public_id, "user_type": "sample",
                                  "username": "sample-" + str(public_id),
                                  "full_name": "sample-" + str(public_id), "email": "sample-" + str(public_id)}}}
        )
        user = new_anonymous_user_auth.user

    storage_file_name = user.id + "/" + str(time.time());
    with open(nifti_gz, 'rb') as f:
        file_content = f.read()
        unzipped_content = gzip.decompress(file_content)

    upload_res = supabase.storage.from_("nifti_gz_files").upload(
        file=unzipped_content, path=storage_file_name + ".nii",
        file_options={"content-type": "application/octet-stream; charset=binary", "upsert": "true"}, )
    upload_obj = upload_res.json()
    nifti_file = supabase.schema("public").table("nifti_files").upsert(
        {"id": upload_obj['Id'], "user_id": user.id,
         "file_type": "nii"}).execute().data[0]

    upload_res = supabase.storage.from_("nifti_gz_files").upload(
        file=file_content, path=storage_file_name + ".nii.gz",
        file_options={"content-type": "application/gzip", "upsert": "true"},)
    upload_obj = upload_res.json()
    nifti_file_zipped = supabase.schema("public").table("nifti_files").upsert(
        {"id": upload_obj['Id'], "parent_nifti_file_id": nifti_file['id'], "user_id": user.id, "file_type": "nii.gz"}).execute().data

    return nifti_file, nifti_file_zipped


@inngest_client.create_function(
    fn_id="upload_nifti",
    trigger=inngest.TriggerEvent(event="nifti_file_uploaded"),
)
async def fn(ctx: inngest.Context, step: inngest.Step):
    parameters = {k: v for k, v in ctx.event.data.items() if not k.startswith('_')}
    nifti_file, nifti_file_zipped = await step.run("upload-from-path", lambda: upload_nifti(**parameters))
    res1 = await step.invoke("resample_atlas_for_user_nifti", function=resample_atlas_for_user_nifti, data={
        "nifti_file_id": nifti_file['id']
    })
    res2 = await step.invoke("calculate_roi_volumes", function=calculate_roi_volumes, data={
        "nifti_file_id": nifti_file['id']
    })
    return res1, res2



# example:
if __name__=="__main__":
    res = upload_nifti("/Users/oytuntez/dev/cerebro-oasis-test/research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz",                   None, 1)
    print(res)
