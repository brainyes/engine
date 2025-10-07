#!/usr/bin/env python3
"""
Test script to verify Lambda handlers work locally
"""
import os
import json

# Set environment variables
os.environ['SUPABASE_URL'] = 'https://<your-project>.supabase.co'
os.environ[
    'SUPABASE_KEY'] = '<REDACTED_SUPABASE_KEY>'

from handlers.lambda_handlers import (
    list_functions_handler,
    generic_function_handler,
    get_task_status_handler,
    async_task_handler,
    get_task_logs_handler
)


def test_list_functions():
    print("Testing list_functions_handler...")
    result = list_functions_handler({}, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_calculate_roi_volumes():
    print("Testing test_calculate_roi_volumes...")
    event = {
        'body': json.dumps({
            'function_name': 'calculate_roi_volumes',
            'parameters': {'nifti_file_id': 'd7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9'}
        })
    }
    result = generic_function_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_resample_atlas_for_user_nifti():
    print("Testing test_resample_atlas_for_user_nifti...")
    event = {
        'body': json.dumps({
            'function_name': 'resample_atlas_for_user_nifti',
            'parameters': {'nifti_file_id': 'd7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9'}
        })
    }
    result = generic_function_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_freesurfer_recon_all():
    print("Testing freesurfer_recon_all...")
    event = {
        'body': json.dumps({
            'function_name': 'freesurfer_recon_all',
            'parameters': {'nifti_file_id': 'd7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9'}
        })
    }
    result = generic_function_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_freesurfer_parse_statistics():
    print("Testing freesurfer_parse_statistics...")
    event = {
        'body': json.dumps({
            'function_name': 'freesurfer_parse_statistics',
            'parameters': {'nifti_file_id': 'd7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9', 'freesurfer_output_directory': '/Users/oytuntez/dev/brainyes-engine/research/input/raw/sub-OASIS10001'}
        })
    }
    result = generic_function_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_freesurfer_store_files():
    print("Testing freesurfer_store_files...")
    event = {
        'body': json.dumps({
            'function_name': 'freesurfer_store_files',
            'parameters': {'nifti_file_id': 'd7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9', 'freesurfer_output_directory': '/Users/oytuntez/dev/brainyes-engine/research/input/raw/sub-OASIS10001'}
        })
    }
    result = generic_function_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_task_status():
    print("Testing get_task_status_handler...")
    # Test with non-existent task
    event = {
        'pathParameters': {
            'task_id': '97c821cd-4b6b-4265-b7fe-ee982cef1106'
        }
    }
    result = get_task_status_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_async_task_handler():
    print("Testing async_task_handler...")
    # Set a mock SQS queue URL for testing
    os.environ['TASK_QUEUE_URL'] = 'https://sqs.us-east-1.amazonaws.com/123456789/test-queue'
    
    # Test submitting a valid function
    event = {
        'body': json.dumps({
            'function_name': 'calculate_roi_volumes',
            'parameters': {
                'nifti_file_id': 'd7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9',
                'user_id': '13c794ba-ad74-4dd6-af93-2a5496b71f0d'
            }
        })
    }
    result = async_task_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    
    # Test with function_name in pathParameters
    event = {
        'pathParameters': {
            'function_name': 'freesurfer_recon_all'
        },
        'body': json.dumps({
            'parameters': {
                'nifti_file_id': 'd7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9'
            }
        })
    }
    result = async_task_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    
    # Test with non-existent function
    event = {
        'body': json.dumps({
            'function_name': 'non_existent_function',
            'parameters': {}
        })
    }
    result = async_task_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_get_task_logs_handler():
    print("Testing get_task_logs_handler...")
    # Test with a task ID
    event = {
        'pathParameters': {
            'task_id': '97c821cd-4b6b-4265-b7fe-ee982cef1106'
        }
    }
    result = get_task_logs_handler(event, {})
    print(f"Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


def test_generic_function_handler_edge_cases():
    print("Testing generic_function_handler edge cases...")
    
    # Test with missing function_name
    event = {
        'body': json.dumps({
            'parameters': {}
        })
    }
    result = generic_function_handler(event, {})
    print(f"Missing function_name - Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    
    # Test with function_name in pathParameters
    event = {
        'pathParameters': {
            'function_name': 'list_functions'
        },
        'body': json.dumps({})
    }
    result = generic_function_handler(event, {})
    print(f"Function in pathParameters - Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    
    # Test with non-existent function
    event = {
        'body': json.dumps({
            'function_name': 'invalid_function_name'
        })
    }
    result = generic_function_handler(event, {})
    print(f"Non-existent function - Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    
    # Test with empty body
    event = {}
    result = generic_function_handler(event, {})
    print(f"Empty event - Status: {result['statusCode']}")
    print(f"Response: {result['body']}")
    print()


if __name__ == "__main__":
    print("=== Lambda Handler Local Tests ===\n")

    # Uncomment the tests you want to run
    # test_list_functions()
    # test_calculate_roi_volumes()
    # test_resample_atlas_for_user_nifti()
    # test_freesurfer_recon_all()
    # test_freesurfer_parse_statistics()
    # test_freesurfer_store_files()
    test_task_status()
    # test_async_task_handler()
    # test_get_task_logs_handler()
    # test_generic_function_handler_edge_cases()

    print("\nAll tests completed successfully!")
