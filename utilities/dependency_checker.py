"""
Check which neuroimaging dependencies are available

This utility helps determine which optional dependencies are installed
and what capabilities are available for the population pipeline.
"""

import subprocess
import sys


def check_ants():
    """Check if ANTsPy is available"""
    try:
        import ants
        return {
            'available': True,
            'version': ants.__version__,
            'method': 'antspyx (Python wrapper)'
        }
    except ImportError:
        return {
            'available': False,
            'error': 'antspyx not installed',
            'install': 'pip install antspyx'
        }


def check_simpleitk():
    """Check if SimpleITK is available"""
    try:
        import SimpleITK as sitk
        return {
            'available': True,
            'version': sitk.Version.VersionString(),
            'method': 'SimpleITK'
        }
    except ImportError:
        return {
            'available': False,
            'error': 'SimpleITK not installed',
            'install': 'pip install SimpleITK'
        }


def check_sklearn():
    """Check if scikit-learn is available"""
    try:
        import sklearn
        return {
            'available': True,
            'version': sklearn.__version__,
            'method': 'scikit-learn'
        }
    except ImportError:
        return {
            'available': False,
            'error': 'scikit-learn not installed',
            'install': 'pip install scikit-learn'
        }


def check_hdbet():
    """Check if HD-BET is available"""
    try:
        result = subprocess.run(['hd-bet', '--version'], capture_output=True, timeout=5)
        version = result.stdout.decode().strip() if result.returncode == 0 else 'unknown'
        return {
            'available': True,
            'version': version,
            'method': 'HD-BET (command-line)'
        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {
            'available': False,
            'error': 'HD-BET not installed',
            'install': 'pip install HD-BET'
        }


def check_fsl():
    """Check if FSL is available"""
    try:
        result = subprocess.run(['bet', '-h'], capture_output=True, timeout=5)
        return {
            'available': result.returncode == 0,
            'method': 'FSL BET (command-line)'
        }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {
            'available': False,
            'error': 'FSL not installed',
            'install': 'See https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslInstallation'
        }




def get_capabilities():
    """
    Get available capabilities based on installed dependencies

    Returns:
        Dictionary with dependency status and recommended methods
    """
    caps = {
        'ants': check_ants(),
        'simpleitk': check_simpleitk(),
        'sklearn': check_sklearn(),
        'hdbet': check_hdbet(),
        'fsl': check_fsl()
    }

    # Determine best registration method
    if caps['ants']['available']:
        caps['best_registration'] = {
            'method': 'ants_syn',
            'name': 'ANTs Symmetric Normalization (nonlinear)',
            'description': 'Most accurate nonlinear registration'
        }
    elif caps['simpleitk']['available']:
        caps['best_registration'] = {
            'method': 'sitk_affine',
            'name': 'SimpleITK Affine Registration',
            'description': 'Linear registration only (less accurate but faster)'
        }
    else:
        caps['best_registration'] = {
            'method': 'none',
            'name': 'No registration available',
            'description': 'Install ANTsPy or SimpleITK for registration'
        }

    # Determine best skull-stripping
    if caps['hdbet']['available']:
        caps['best_skullstrip'] = {
            'method': 'hdbet',
            'name': 'HD-BET',
            'description': 'Deep learning-based (most robust)'
        }
    elif caps['fsl']['available']:
        caps['best_skullstrip'] = {
            'method': 'fsl_bet',
            'name': 'FSL BET',
            'description': 'Classic algorithm (good for most cases)'
        }
    elif caps['simpleitk']['available']:
        caps['best_skullstrip'] = {
            'method': 'threshold',
            'name': 'Simple Threshold',
            'description': 'Basic threshold-based (fallback only)'
        }
    else:
        caps['best_skullstrip'] = {
            'method': 'none',
            'name': 'No skull-stripping available',
            'description': 'Install SimpleITK for basic functionality'
        }

    # Check if statistical modeling is possible
    caps['statistical_modeling'] = caps['sklearn']['available']

    # Overall readiness
    caps['ready_for_v2_pipeline'] = (
        caps['simpleitk']['available'] and  # Required for preprocessing
        (caps['ants']['available'] or caps['simpleitk']['available']) and  # Registration
        caps['sklearn']['available']  # Statistical models
    )

    return caps


def print_status():
    """Print a human-readable status report"""
    caps = get_capabilities()

    print("=" * 70)
    print("NEUROIMAGING DEPENDENCIES STATUS")
    print("=" * 70)
    print()

    print("Core Dependencies:")
    print("-" * 70)
    for dep in ['ants', 'simpleitk', 'sklearn']:
        status = caps[dep]
        if status['available']:
            print(f"  ✓ {dep.upper()}: {status.get('version', 'installed')} ({status['method']})")
        else:
            print(f"  ✗ {dep.upper()}: Not installed")
            print(f"    Install: {status.get('install', 'see documentation')}")

    print()
    print("Optional Dependencies:")
    print("-" * 70)
    for dep in ['hdbet', 'fsl']:
        status = caps[dep]
        if status['available']:
            version = status.get('version', 'installed')
            print(f"  ✓ {dep.upper()}: {version}")
        else:
            print(f"  ○ {dep.upper()}: Not installed (optional)")

    print()
    print("Recommended Methods:")
    print("-" * 70)
    reg = caps['best_registration']
    print(f"  Registration: {reg['name']}")
    print(f"    → {reg['description']}")

    skull = caps['best_skullstrip']
    print(f"  Skull-stripping: {skull['name']}")
    print(f"    → {skull['description']}")

    print()
    print("Pipeline Readiness:")
    print("-" * 70)
    if caps['ready_for_v2_pipeline']:
        print("  ✓ Ready for Population Pipeline v2")
        print("    All required dependencies are installed.")
    else:
        print("  ✗ Not ready for Population Pipeline v2")
        print("    Missing required dependencies:")
        if not caps['simpleitk']['available']:
            print("      - SimpleITK (required for preprocessing)")
        if not (caps['ants']['available'] or caps['simpleitk']['available']):
            print("      - ANTsPy or SimpleITK (required for registration)")
        if not caps['sklearn']['available']:
            print("      - scikit-learn (required for statistical models)")
        print()
        print("  Install missing dependencies:")
        print("    pip install -r requirements.txt")

    print()
    print("=" * 70)


if __name__ == '__main__':
    import json

    if len(sys.argv) > 1 and sys.argv[1] == '--json':
        # JSON output for programmatic use
        caps = get_capabilities()
        print(json.dumps(caps, indent=2))
    else:
        # Human-readable output
        print_status()
