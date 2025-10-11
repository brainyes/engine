import inngest
import os
import argparse

from functions.calculate_roi_volumes import fn as calculate_roi_volumes
from functions.resample_atlas_for_user_nifti import fn as resample_atlas_for_user_nifti
from utilities.data import supabase
from utilities.supabase_utilities import upload_nifti_to_storage
from utilities.inngest import client as inngest_client

# todo owner_id needs refactor. it's actually sth like users.slug or users.nickname.
#   and maybe a users.type kind of a thing to differentiate between anonymous/public people
#   and our own users
# public_id is for anonymous entries/users/persons.
#   we still represent them in our supabase user/owner system.
def upload_nifti(nifti_gz, user_id = None, public_id = None):
    """
    Upload a NIFTI file from a file path.

    This function handles user creation/auth and delegates the actual upload
    to the upload_nifti_to_storage utility function.

    Args:
        nifti_gz: Path to NIFTI file (.nii or .nii.gz)
        user_id: User ID (not yet supported)
        public_id: Public ID for anonymous user creation

    Returns:
        tuple: (nifti_file, nifti_file_zipped) database records
    """
    if user_id is None and public_id is None:
        raise Exception('Must specify either user_id or public_id')

    if user_id is not None:
        raise Exception('Non-sample users are not supported yet')

    # Create or get anonymous user
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

    # Read file and upload using utility function
    with open(nifti_gz, 'rb') as f:
        file_data = f.read()

    return upload_nifti_to_storage(file_data, user.id)


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
    parser = argparse.ArgumentParser(description='Upload a NIFTI brain scan file to BrainYes for analysis')
    parser.add_argument('nifti_file', help='Path to the NIFTI file (.nii or .nii.gz)')
    parser.add_argument('--public-id', type=int, default=1, help='Public ID for the analysis session (default: 1)')
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.nifti_file):
        print(f"❌ Error: File not found: {args.nifti_file}")
        print("Please check the file path and try again.")
        os._exit(1)
    
    print("=== BRAINYES NIFTI UPLOAD ===")
    print(f"Uploading NIFTI file: {args.nifti_file}")
    print("This will upload your brain scan and prepare it for analysis...")
    print("Please wait, this may take 30-60 seconds...\n")
    
    try:
        res = upload_nifti(args.nifti_file, None, args.public_id)
        
        print("upload_nifti result:")
        print(res)
        
        print("\n=== UPLOAD COMPLETE ===")
        print("IMPORTANT: Save these IDs for the next steps!")
        print(f"📋 Main file ID: {res[0]['id']}")
        print(f"👤 User ID: {res[0]['user_id']}")
        
    except Exception as e:
        print(f"❌ Error during upload: {str(e)}")
        print("Please check your file and try again.")
        os._exit(1)
    
    os._exit(0)
