import os
from dotenv import load_dotenv

load_dotenv()

# Options
silent_run = True
save_assets = True


# Get the script's directory
script_dir = os.path.join(os.path.dirname(__file__), '../../research')
dataset_dir = os.path.join(script_dir, 'input')
output_dir = os.path.join(script_dir, 'output')

atlas_file_path = os.path.join(dataset_dir, 'HarvardOxford-cort-maxprob-thr25-2mm.nii.gz')
oasis_bids_tsv_path = os.path.join(dataset_dir, 'tsv_files', 'lab_1', 'OASIS_BIDS.tsv')