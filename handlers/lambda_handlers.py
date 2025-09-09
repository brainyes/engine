import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import boto3
from dotenv import load_dotenv

load_dotenv()

# Import Supabase client
from utilities.data import supabase

# Add parent directory to path to import functions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize AWS clients
sqs = boto3.client('sqs')
TASK_QUEUE_URL = os.environ.get('TASK_QUEUE_URL', '')

def create_response(status_code: int, body: Any) -> Dict[str, Any]:
    """Create a standard API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }

def get_function_names():
    """Get list of function names without importing them"""
    functions_dir = Path(__file__).parent.parent / "functions"
    function_names = []
    
    for py_file in functions_dir.glob("*.py"):
        if py_file.name.startswith("__") or py_file.name == "template.py":
            continue
        function_names.append(py_file.stem)
    
    return function_names

def lazy_import_function(function_name):
    """Lazily import a specific function only when needed"""
    try:
        module = importlib.import_module(f"functions.{function_name}")
        if hasattr(module, function_name):
            func = getattr(module, function_name)
            if callable(func):
                return func
    except Exception as e:
        print(f"Could not import {function_name}: {e}")
    return None

# Cache for imported functions
IMPORTED_FUNCTIONS = {}

def generic_function_handler(event, context):
    """Generic Lambda handler that can execute any function"""
    try:
        print(f"Received event: {json.dumps(event, default=str)}")
        
        # Extract function name from path or body
        function_name = None
        if 'pathParameters' in event and 'function_name' in event['pathParameters']:
            function_name = event['pathParameters']['function_name']
        elif 'body' in event and 'function_name' in event['body']:
            body = json.loads(event['body'])
            function_name = body.get('function_name')
            
        if not function_name:
            return create_response(400, {
                'success': False,
                'error': 'Function name is required'
            })
        # Check if function exists (without importing all modules)
        print(f"Checking if function {function_name} exists...")
        available_function_names = get_function_names()
        
        if function_name not in available_function_names:
            return create_response(404, {
                'success': False,
                'error': f'Function not found: {function_name}. Available functions: {available_function_names}',
                'available_functions': available_function_names
            })

        # Check cache first
        if function_name in IMPORTED_FUNCTIONS:
            func = IMPORTED_FUNCTIONS[function_name]
        else:
            func = lazy_import_function(function_name)
            if func:
                IMPORTED_FUNCTIONS[function_name] = func
        
        if not func:
            return create_response(500, {
                'success': False,
                'error': f'Failed to import function: {function_name}'
            })
            
        # Extract parameters
        body = json.loads(event['body']) if 'body' in event else {}
        parameters = body.get('parameters', body)
        
        # Remove function_name from parameters if it exists
        parameters.pop('function_name', None)
        
        print(f"Calling function {function_name} with parameters: {parameters}")
        
        # Call the function with better error handling
        try:
            result = func(**parameters)
        except TypeError as te:
            # Handle invalid parameters error
            import inspect
            sig = inspect.signature(func)
            expected_params = list(sig.parameters.keys())
            
            # Check for unexpected keyword arguments
            if "unexpected keyword argument" in str(te):
                return create_response(400, {
                    'success': False,
                    'error': 'Invalid parameters provided',
                    'message': str(te),
                    'expected_parameters': expected_params,
                    'received_parameters': list(parameters.keys())
                })
            # Check for missing required arguments
            elif "missing" in str(te) and "required" in str(te):
                return create_response(400, {
                    'success': False,
                    'error': 'Missing required parameters',
                    'message': str(te),
                    'expected_parameters': expected_params,
                    'received_parameters': list(parameters.keys())
                })
            else:
                raise  # Re-raise if it's a different TypeError
        
        print(f"Function {function_name} completed successfully")
        return create_response(200, {
            'success': True,
            'function': function_name,
            'data': result
        })
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"ERROR: {error_msg}")
        print(f"TRACEBACK: {error_trace}")
        return create_response(500, {
            'success': False,
            'error': error_msg,
            'traceback': error_trace
        })

def async_task_handler(event, context):
    """Lambda handler for submitting any function as async task to SQS/ECS"""
    try:
        body = json.loads(event['body'])
        
        # Extract parameters
        function_name = body.get('function_name')
        if 'pathParameters' in event and 'function_name' in event['pathParameters']:
            function_name = event['pathParameters']['function_name']
            
        parameters = body.get('parameters', {})
        
        # Validate function exists (without importing all modules)
        available_function_names = get_function_names()
        if function_name not in available_function_names:
            return create_response(404, {
                'success': False,
                'error': f'Function not found: {function_name}',
                'available_functions': available_function_names
            })
        
        # Create task record in Supabase (without ID - let Supabase auto-generate it)
        task_data = {
            'function_name': function_name,
            'parameters': parameters,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'logs_url': f"https://console.aws.amazon.com/cloudwatch/home?region={os.environ.get('AWS_REGION', 'us-east-1')}#logsV2:log-groups"
        }
        
        # Get user_id from parameters if provided
        if 'user_id' in parameters:
            task_data['user_id'] = parameters['user_id']
        
        # Insert into Supabase and get the auto-generated ID
        result = supabase.table('async_tasks').insert(task_data).execute()
        task_id = result.data[0]['id']
        
        # Send message to SQS
        message_body = {
            'task_id': task_id,
            'function_name': function_name,
            'parameters': parameters
        }
        
        sqs.send_message(
            QueueUrl=TASK_QUEUE_URL,
            MessageBody=json.dumps(message_body)
        )
        
        return create_response(200, {
            'success': True,
            'task_id': task_id,
            'status': 'pending',
            'message': f'Task {task_id} submitted successfully'
        })
        
    except Exception as e:
        return create_response(500, {
            'success': False,
            'error': str(e)
        })

def list_functions_handler(event, context):
    """Lambda handler to list all available functions"""
    try:
        # Use the shared function to get function names without importing
        function_names = get_function_names()
        
        return create_response(200, {
            'success': True,
            'functions': function_names,
            'message': 'Function discovery simplified for testing'
        })
        
    except Exception as e:
        return create_response(500, {
            'success': False,
            'error': str(e)
        })

def get_task_status_handler(event, context):
    """Lambda handler for checking task status"""
    try:
        task_id = event['pathParameters']['task_id']
        
        # Query task from Supabase
        result = supabase.table('async_tasks').select('*').eq('id', task_id).execute()
        if result.data:
            task = result.data[0]
        else:
            return create_response(404, {
                'success': False,
                'error': f'Task not found: {task_id}'
            })
        
        return create_response(200, {
            'success': True,
            'task': task
        })
        
    except Exception as e:
        return create_response(500, {
            'success': False,
            'error': str(e)
        })

def get_task_logs_handler(event, context):
    """Lambda handler for fetching task logs from CloudWatch"""
    try:
        task_id = event['pathParameters']['task_id']
        
        # Query task from Supabase to get ECS task ARN
        result = supabase.table('async_tasks').select('*').eq('id', task_id).execute()
        if result.data:
            task = result.data[0]
        else:
            return create_response(404, {
                'success': False,
                'error': f'Task not found: {task_id}'
            })

        # If task has ECS task ARN, fetch logs from CloudWatch
        if task.get('ecs_task_arn'):
            # TODO: Implement CloudWatch logs fetching
            # For now, return a placeholder
            logs = f"Logs for task {task_id} would be fetched from CloudWatch here"
        else:
            logs = "Task has not started yet"
        
        return create_response(200, {
            'success': True,
            'task_id': task_id,
            'logs': logs,
            'status': task['status'],
        })
        
    except Exception as e:
        return create_response(500, {
            'success': False,
            'error': str(e)
        })

def router_handler(event, context):
    """Single router handler that routes requests to appropriate functionality"""
    try:
        # Get the resource path to determine which handler to use
        path = event.get('resource', '')
        method = event.get('httpMethod', '')
        
        print(f"Router received: {method} {path}")
        
        # Route based on path and method
        if path == '/functions' and method == 'GET':
            return list_functions_handler(event, context)
        elif path in ['/function', '/function/{function_name}'] and method == 'POST':
            return generic_function_handler(event, context)
        elif path == '/async/{function_name}' and method == 'POST':
            return async_task_handler(event, context)
        elif path == '/tasks/{task_id}/status' and method == 'GET':
            return get_task_status_handler(event, context)
        elif path == '/tasks/{task_id}/logs' and method == 'GET':
            return get_task_logs_handler(event, context)
        else:
            return create_response(404, {
                'success': False,
                'error': f'Route not found: {method} {path}',
                'available_routes': [
                    'GET /functions',
                    'POST /function',
                    'POST /function/{function_name}',
                    'POST /async/{function_name}',
                    'GET /tasks/{task_id}/status',
                    'GET /tasks/{task_id}/logs'
                ]
            })
            
    except Exception as e:
        return create_response(500, {
            'success': False,
            'error': f'Router error: {str(e)}'
        })