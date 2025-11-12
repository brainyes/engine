"""
Patch VoxelMorph for Python 3.12 compatibility

VoxelMorph uses inspect.getargspec() which was removed in Python 3.11+
This script patches it to use inspect.getfullargspec() instead.

Run this after pip install.
"""

import os
import sys

def find_voxelmorph_path():
    """Find the installed voxelmorph package path"""
    try:
        # Set PyTorch backend to avoid TensorFlow import errors
        os.environ['VXM_BACKEND'] = 'pytorch'
        os.environ['NEURITE_BACKEND'] = 'pytorch'

        import voxelmorph
        vxm_path = os.path.dirname(voxelmorph.__file__)
        return vxm_path
    except ImportError as e:
        print(f"❌ VoxelMorph not installed: {e}")
        return None

def patch_modelio():
    """Patch torch/modelio.py for Python 3.12 compatibility"""
    vxm_path = find_voxelmorph_path()
    if not vxm_path:
        return False

    torch_modelio = os.path.join(vxm_path, 'torch', 'modelio.py')

    if not os.path.exists(torch_modelio):
        print(f"⚠️  File not found: {torch_modelio}")
        return False

    # Read file
    with open(torch_modelio, 'r') as f:
        content = f.read()

    # Check if already patched
    if 'getfullargspec' in content:
        print(f"✓ Already patched: {torch_modelio}")
        return True

    # Apply patch
    content = content.replace(
        'inspect.getargspec(func)',
        'inspect.getfullargspec(func)[:4]'
    )

    # Write back
    with open(torch_modelio, 'w') as f:
        f.write(content)

    print(f"✅ Patched: {torch_modelio}")
    return True

if __name__ == '__main__':
    print("Patching VoxelMorph for Python 3.12 compatibility...")
    success = patch_modelio()
    sys.exit(0 if success else 1)
