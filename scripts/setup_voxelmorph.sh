#!/bin/bash
# Setup VoxelMorph with PyTorch backend for Apple Silicon (MPS) support
#
# This script:
# 1. Installs VoxelMorph from GitHub (master branch)
# 2. Patches it for Python 3.12 compatibility
# 3. Downloads pre-trained models

set -e

echo "=== VoxelMorph Setup for Apple Silicon ==="

# Install VoxelMorph from master branch
echo "1. Installing VoxelMorph (PyTorch backend)..."
pip install --quiet git+https://github.com/voxelmorph/voxelmorph.git@master

# Patch for Python 3.12
echo "2. Patching for Python 3.12 compatibility..."
python -m utilities.patch_voxelmorph

# Download pre-trained models
echo "3. Downloading pre-trained models..."
mkdir -p ~/.voxelmorph/models

# Download brain MRI registration model (if available)
# TODO: Add model download URLs when identified

echo "✅ VoxelMorph setup complete!"
echo ""
echo "To use VoxelMorph with PyTorch backend:"
echo "  export VXM_BACKEND=pytorch"
echo "  export NEURITE_BACKEND=pytorch"
