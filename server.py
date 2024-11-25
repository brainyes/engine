import inngest.fast_api
from fastapi import FastAPI

from functions.calculate_roi_volumes import fn as calculate_roi_volumes
from functions.resample_atlas_for_user_nifti import fn as resample_atlas_for_user_nifti
from functions.upload_nifti import fn as upload_nifti
from insights.paper_1_oasis import fn as paper_1_oasis
from utilities.inngest import client as inngest_client

app = FastAPI()
# Serve the Inngest endpoint
inngest.fast_api.serve(app, inngest_client,[upload_nifti, resample_atlas_for_user_nifti, calculate_roi_volumes,
    paper_1_oasis])
