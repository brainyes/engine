"""
Atlas Configuration and Management System

This module provides a registry for brain atlases used in the processing pipeline.
Supports multiple atlases with different parcellation schemes and region definitions.
"""

import os
from dataclasses import dataclass
from typing import Dict, Optional

# Get the script's directory
script_dir = os.path.join(os.path.dirname(__file__), '../research')
dataset_dir = os.path.join(script_dir, 'input')


@dataclass
class AtlasConfig:
    """Configuration for a brain atlas"""
    name: str  # Unique identifier (e.g., 'harvard-oxford', 'hcpex')
    display_name: str  # Human-readable name
    file_path: str  # Path to atlas NIfTI file
    description: str  # Description of the atlas
    resolution_mm: str  # Resolution (e.g., '2mm', '1mm')
    num_regions: int  # Number of labeled regions
    label_dict_name: str  # Name of label dictionary in volume_labels module
    lookup_file: Optional[str] = None  # Optional lookup table file


# Atlas Registry
AVAILABLE_ATLASES: Dict[str, AtlasConfig] = {
    'freesurfer': AtlasConfig(
        name='freesurfer',
        display_name='FreeSurfer Automatic Parcellation (aparc+aseg)',
        file_path='',  # Loaded from FreeSurfer outputs, not a static file
        description='Subject-specific cortical and subcortical segmentation (GUARANTEED ALIGNMENT) - Recommended',
        resolution_mm='1mm',
        num_regions=80,
        label_dict_name='freesurfer_labels'  # TODO: create this
    ),
    'harvard-oxford': AtlasConfig(
        name='harvard-oxford',
        display_name='Harvard-Oxford Cortical Atlas',
        file_path=os.path.join(dataset_dir, 'atlases', 'harvard-oxford', 'HarvardOxford-cort-maxprob-thr25-2mm.nii.gz'),
        description='Harvard-Oxford cortical and subcortical structural atlas (EXPERIMENTAL - may have alignment issues)',
        resolution_mm='2mm',
        num_regions=69,  # 48 cortical + 21 subcortical
        label_dict_name='harvard_oxford_labels'
    ),
    'hcpex': AtlasConfig(
        name='hcpex',
        display_name='HCPex Atlas v1.1',
        file_path=os.path.join(dataset_dir, 'atlases', 'hcpex', 'HCPex.nii.gz'),
        description='HCP-based extended parcellation atlas (EXPERIMENTAL - may have alignment issues)',
        resolution_mm='variable',
        num_regions=427,  # 360 cortical + 67 subcortical regions
        label_dict_name='hcpex_labels',
        lookup_file=os.path.join(dataset_dir, 'atlases', 'hcpex', 'HCPex_LookUpTable.txt')
    )
}

# Default atlas (HCPex preferred for its higher resolution and more regions)
DEFAULT_ATLAS = 'hcpex'


def get_atlas(atlas_name: str = None) -> AtlasConfig:
    """
    Get atlas configuration by name

    Args:
        atlas_name: Name of the atlas (e.g., 'harvard-oxford', 'hcpex')
                   If None, returns default atlas

    Returns:
        AtlasConfig object

    Raises:
        ValueError: If atlas_name is not found in registry

    Example:
        atlas = get_atlas('hcpex')
        img = nib.load(atlas.file_path)
    """
    if atlas_name is None:
        atlas_name = DEFAULT_ATLAS

    if atlas_name not in AVAILABLE_ATLASES:
        raise ValueError(
            f"Atlas '{atlas_name}' not found. Available atlases: {list(AVAILABLE_ATLASES.keys())}"
        )

    return AVAILABLE_ATLASES[atlas_name]


def list_atlases() -> Dict[str, str]:
    """
    List all available atlases

    Returns:
        Dictionary mapping atlas names to display names
    """
    return {name: config.display_name for name, config in AVAILABLE_ATLASES.items()}


def validate_atlas_exists(atlas_name: str) -> bool:
    """
    Check if an atlas exists in the registry

    Args:
        atlas_name: Name of the atlas to check

    Returns:
        True if atlas exists, False otherwise
    """
    return atlas_name in AVAILABLE_ATLASES


def get_atlas_file_path(atlas_name: str = None, template: str = 'mni152') -> str:
    """
    Get the file path for an atlas

    Args:
        atlas_name: Name of the atlas (uses default if None)
        template: Template space to use ('mni152' or 'oasis')
                 If 'oasis' and OASIS-space atlas exists, returns that path

    Returns:
        Path to atlas NIfTI file (empty string for FreeSurfer - loaded from outputs)
    """
    atlas = get_atlas(atlas_name)
    if atlas_name == 'freesurfer':
        return ''  # FreeSurfer atlas loaded from storage, not a static file

    # For OASIS template, check if OASIS-space version exists
    if template.lower() == 'oasis' and atlas_name in ['harvard-oxford', 'hcpex']:
        oasis_path = atlas.file_path.replace('.nii.gz', '-oasis.nii.gz')
        if os.path.exists(oasis_path):
            return oasis_path
        else:
            print(f"⚠️  Warning: OASIS-space {atlas_name} atlas not found: {oasis_path}")
            print(f"   Run: python -m utilities.prepare_oasis_atlases")
            print(f"   Falling back to MNI-space atlas (may produce incorrect results)")

    return atlas.file_path


def get_atlas_label_dict_name(atlas_name: str = None) -> str:
    """
    Get the label dictionary name for an atlas

    Args:
        atlas_name: Name of the atlas (uses default if None)

    Returns:
        Name of the label dictionary in volume_labels module
    """
    atlas = get_atlas(atlas_name)
    return atlas.label_dict_name
