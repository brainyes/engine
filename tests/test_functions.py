#!/usr/bin/env python3
"""
Simple test runner for brainyes-engine functions

Tests each function with known good test data to ensure code changes don't break existing functionality.

Usage:
    python tests/test_functions.py              # Run quick tests (skip slow functions)
    python tests/test_functions.py --full       # Run all tests including slow ones
    python tests/test_functions.py --function calculate_roi_volumes  # Test specific function
"""

import sys
import os
import argparse
from typing import Dict, List, Callable, Optional
import traceback
import io
from contextlib import redirect_stdout, redirect_stderr

# Add project root to Python path so we can import functions
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Test data - these IDs are already in the database
TEST_NIFTI_ID = "d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9"
TEST_DICOM_SERIES_ID = "cb5ff621-12f7-4b80-9d31-4ff96df99fa6"


class TestResult:
    """Store test result information"""
    def __init__(self, name: str, success: bool, error: Optional[str] = None, skipped: bool = False,
                 stdout: str = "", stderr: str = ""):
        self.name = name
        self.success = success
        self.error = error
        self.skipped = skipped
        self.stdout = stdout
        self.stderr = stderr


class FunctionTest:
    """Define a function test"""
    def __init__(
        self,
        name: str,
        module_path: str,
        function_name: str,
        args: List,
        kwargs: Dict = None,
        slow: bool = False,
        skip: bool = False,
        skip_reason: str = ""
    ):
        self.name = name
        self.module_path = module_path
        self.function_name = function_name
        self.args = args
        self.kwargs = kwargs or {}
        self.slow = slow
        self.skip = skip
        self.skip_reason = skip_reason


# Define all function tests
FUNCTION_TESTS = [
    # DICOM Processing
    FunctionTest(
        name="dicom_to_nifti_converter",
        module_path="functions.dicom_to_nifti_converter",
        function_name="dicom_to_nifti_converter",
        args=[TEST_DICOM_SERIES_ID],
        slow=False,
        skip=False
    ),

    # Atlas and Volume Calculations
    FunctionTest(
        name="resample_atlas_for_user_nifti",
        module_path="functions.resample_atlas_for_user_nifti",
        function_name="resample_atlas_for_user_nifti",
        args=[TEST_NIFTI_ID],
        slow=False
    ),

    FunctionTest(
        name="calculate_roi_volumes",
        module_path="functions.calculate_roi_volumes",
        function_name="calculate_roi_volumes",
        args=[TEST_NIFTI_ID],
        slow=False
    ),

    # Memory Metrics
    FunctionTest(
        name="calculate_memory_metrics",
        module_path="functions.calculate_memory_metrics",
        function_name="calculate_memory_metrics",
        args=[TEST_NIFTI_ID],
        slow=False
    ),

    # FreeSurfer Functions (slow - only run with --full)
    FunctionTest(
        name="freesurfer_recon_all",
        module_path="functions.freesurfer_recon_all",
        function_name="freesurfer_recon_all",
        args=[TEST_NIFTI_ID],
        slow=True,
        skip=True,
        skip_reason="Very slow (hours), requires FreeSurfer installation"
    ),

    FunctionTest(
        name="freesurfer_parse_statistics",
        module_path="functions.freesurfer_parse_statistics",
        function_name="freesurfer_parse_statistics",
        args=[TEST_NIFTI_ID, "/tmp/freesurfer_output"],  # Would need actual FreeSurfer output
        slow=False,
        skip=True,
        skip_reason="Requires FreeSurfer output directory"
    ),

    FunctionTest(
        name="freesurfer_store_files",
        module_path="functions.freesurfer_store_files",
        function_name="freesurfer_store_files",
        args=[TEST_NIFTI_ID, "/tmp/freesurfer_output"],
        slow=False,
        skip=True,
        skip_reason="Requires FreeSurfer output directory"
    ),

    # Visualization Functions
    FunctionTest(
        name="generate_surface_files",
        module_path="functions.generate_surface_files",
        function_name="generate_surface_files",
        args=[TEST_NIFTI_ID],
        slow=False,
        skip=True,
        skip_reason="Requires FreeSurfer output directory"
    ),

    FunctionTest(
        name="generate_visualization_data",
        module_path="functions.generate_visualization_data",
        function_name="generate_visualization_data",
        args=[TEST_NIFTI_ID],
        slow=False,
        skip=True,
        skip_reason="Requires FreeSurfer output and surface files"
    ),
]


def run_test(test: FunctionTest) -> TestResult:
    """Run a single function test"""

    if test.skip:
        return TestResult(test.name, success=True, skipped=True)

    # Capture stdout and stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    try:
        # Import the module
        module = __import__(test.module_path, fromlist=[test.function_name])
        func = getattr(module, test.function_name)

        # Run the function with output capture
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            result = func(*test.args, **test.kwargs)

        # If we got here, it succeeded
        return TestResult(
            test.name,
            success=True,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue()
        )

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        tb = traceback.format_exc()
        return TestResult(
            test.name,
            success=False,
            error=f"{error_msg}\n{tb}",
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue()
        )


def print_results(results: List[TestResult], verbose: bool = False):
    """Print test results"""

    passed = [r for r in results if r.success and not r.skipped]
    failed = [r for r in results if not r.success and not r.skipped]
    skipped = [r for r in results if r.skipped]

    print("\n" + "="*70)
    print("TEST RESULTS")
    print("="*70)

    if passed:
        print(f"\n✅ PASSED ({len(passed)}):")
        for r in passed:
            print(f"   • {r.name}")

    if failed:
        print(f"\n❌ FAILED ({len(failed)}):")
        for r in failed:
            print(f"\n   • {r.name}")

            # Always show error message (not just with verbose)
            if r.error:
                print(f"\n     Error:")
                for line in r.error.split('\n'):
                    if line.strip():
                        print(f"       {line}")

            # Show stdout if present
            if r.stdout:
                print(f"\n     STDOUT:")
                for line in r.stdout.split('\n'):
                    if line.strip():
                        print(f"       {line}")

            # Show stderr if present
            if r.stderr:
                print(f"\n     STDERR:")
                for line in r.stderr.split('\n'):
                    if line.strip():
                        print(f"       {line}")

    if skipped:
        print(f"\n⏭️  SKIPPED ({len(skipped)}):")
        for r in skipped:
            test = next(t for t in FUNCTION_TESTS if t.name == r.name)
            print(f"   • {r.name} - {test.skip_reason}")

    print("\n" + "="*70)
    print(f"Total: {len(results)} | Passed: {len(passed)} | Failed: {len(failed)} | Skipped: {len(skipped)}")
    print("="*70 + "\n")

    return len(failed) == 0


def main():
    parser = argparse.ArgumentParser(description='Test brainyes-engine functions')
    parser.add_argument('--full', action='store_true', help='Run all tests including slow ones')
    parser.add_argument('--function', type=str, help='Test only a specific function')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed error messages')

    args = parser.parse_args()

    # Filter tests based on arguments
    tests_to_run = FUNCTION_TESTS

    if args.function:
        tests_to_run = [t for t in FUNCTION_TESTS if t.name == args.function]
        if not tests_to_run:
            print(f"❌ Function '{args.function}' not found in test suite")
            print(f"\nAvailable functions:")
            for t in FUNCTION_TESTS:
                print(f"   • {t.name}")
            sys.exit(1)

    if not args.full:
        # Skip slow tests in quick mode
        for test in tests_to_run:
            if test.slow and not test.skip:
                test.skip = True
                test.skip_reason = "Slow test - use --full to run"

    # Print test plan
    print("\n" + "="*70)
    print("BRAINYES-ENGINE FUNCTION TESTS")
    print("="*70)
    print(f"Mode: {'FULL' if args.full else 'QUICK'}")
    print(f"Test data: NIFTI ID={TEST_NIFTI_ID}, DICOM ID={TEST_DICOM_SERIES_ID}")
    print(f"Tests to run: {len([t for t in tests_to_run if not t.skip])}")
    print(f"Tests to skip: {len([t for t in tests_to_run if t.skip])}")
    print("="*70 + "\n")

    # Run tests
    results = []
    for i, test in enumerate(tests_to_run, 1):
        if test.skip:
            print(f"[{i}/{len(tests_to_run)}] ⏭️  Skipping {test.name}...")
            results.append(TestResult(test.name, success=True, skipped=True))
        else:
            print(f"[{i}/{len(tests_to_run)}] 🧪 Testing {test.name}...", end=" ", flush=True)
            result = run_test(test)
            results.append(result)

            if result.success:
                print("✅ PASS")
            else:
                print("❌ FAIL")

    # Print summary
    all_passed = print_results(results, verbose=args.verbose)

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()