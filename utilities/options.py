import os
from dotenv import load_dotenv

load_dotenv()

# Options
silent_run = True
save_assets = True


# Get the script's directory
script_dir = os.path.join(os.path.dirname(__file__), '../research')
dataset_dir = os.path.join(script_dir, 'input')

# Use /tmp for output in Lambda (read-only filesystem except /tmp)
# Otherwise use research/output for local development
if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
    output_dir = '/tmp'
else:
    output_dir = os.path.join(script_dir, 'output')

atlas_file_path = os.path.join(dataset_dir, 'HarvardOxford-cort-maxprob-thr25-2mm.nii.gz')
oasis_bids_tsv_path = os.path.join(dataset_dir, 'tsv_files', 'lab_1', 'OASIS_BIDS.tsv')