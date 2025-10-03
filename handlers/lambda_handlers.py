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
import utilities.error_handling as error_handling

error_handling.init()

# Add parent directory to path to import functions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize AWS clients
sqs = boto3.client('sqs')
ecs = boto3.client('ecs')
logs = boto3.client('logs')
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
        import sentry_sdk

        error_msg = str(e)
        error_trace = traceback.format_exc()
        print(f"ERROR: {error_msg}")
        print(f"TRACEBACK: {error_trace}")

        # Capture exception in Sentry
        sentry_sdk.capture_exception(e)

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
            'created_at': datetime.now(timezone.utc).isoformat()
            # logs_url will be set by ECS handler when task starts running
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
        import sentry_sdk
        sentry_sdk.capture_exception(e)
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
        import sentry_sdk
        sentry_sdk.capture_exception(e)
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
        import sentry_sdk
        sentry_sdk.capture_exception(e)
        return create_response(500, {
            'success': False,
            'error': str(e)
        })

def get_task_logs_handler(event, context):
    """Lambda handler for fetching task logs from CloudWatch"""
    try:
        task_id = event['pathParameters']['task_id']

        # Query task from Supabase to get log stream name
        result = supabase.table('async_tasks').select('*').eq('id', task_id).execute()
        if result.data:
            task = result.data[0]
        else:
            return create_response(404, {
                'success': False,
                'error': f'Task not found: {task_id}'
            })

        log_stream = task.get('logs_url')  # This now contains the log stream name
        next_token = event.get('queryStringParameters', {}).get('nextToken') if event.get('queryStringParameters') else None

        # Check if log_stream is valid (not the old generic URL)
        if log_stream and log_stream.startswith('http'):
            # Legacy task with old generic CloudWatch URL
            return create_response(200, {
                'success': True,
                'task_id': task_id,
                'logs': 'This task was created before log streaming was implemented. Logs are only available in CloudWatch console.',
                'status': task['status']
            })

        if log_stream:
            try:
                # Fetch logs from CloudWatch
                params = {
                    'logGroupName': '/ecs/brainyes-task',
                    'logStreamName': log_stream,
                    'startFromHead': True,
                    'limit': 1000
                }

                # Add nextToken for pagination if provided
                if next_token:
                    params['nextToken'] = next_token

                response = logs.get_log_events(**params)

                # Format logs as text
                log_lines = [event['message'] for event in response.get('events', [])]
                log_text = '\n'.join(log_lines)
                next_forward_token = response.get('nextForwardToken')

                return create_response(200, {
                    'success': True,
                    'task_id': task_id,
                    'logs': log_text,
                    'log_stream': log_stream,
                    'next_token': next_forward_token,
                    'status': task['status'],
                    'has_more': len(log_lines) == 1000  # Max limit reached
                })

            except logs.exceptions.ResourceNotFoundException as e:
                return create_response(200, {
                    'success': True,
                    'task_id': task_id,
                    'logs': f'Log stream not found yet (task may be starting).\n\nExpected stream: {log_stream}\n\nNote: Logs may take 30-60 seconds to appear in CloudWatch after task starts.',
                    'log_stream': log_stream,
                    'status': task['status']
                })
            except Exception as e:
                import traceback
                error_details = f'{str(e)}\n\nLog stream: {log_stream}\nLog group: /ecs/brainyes-task\n\nTraceback:\n{traceback.format_exc()}'
                return create_response(200, {
                    'success': True,
                    'task_id': task_id,
                    'logs': f'Could not fetch logs: {error_details}',
                    'log_stream': log_stream,
                    'status': task['status']
                })
        else:
            return create_response(200, {
                'success': True,
                'task_id': task_id,
                'logs': 'Task has not started yet',
                'status': task['status']
            })

    except Exception as e:
        import sentry_sdk
        sentry_sdk.capture_exception(e)
        return create_response(500, {
            'success': False,
            'error': str(e)
        })

def sqs_to_ecs_handler(event, context):
    """Handle SQS messages and launch ECS tasks"""
    try:
        print(f"Received SQS event: {json.dumps(event, default=str)}")

        # Process each SQS record
        for record in event.get('Records', []):
            try:
                # Parse the SQS message body
                message_body = json.loads(record['body'])
                task_id = message_body.get('task_id')
                function_name = message_body.get('function_name')
                parameters = message_body.get('parameters', {})

                print(f"Processing task {task_id}: {function_name}")

                if not task_id:
                    print("No task_id in message, skipping")
                    continue

                # Launch ECS task
                ecs_response = ecs.run_task(
                    cluster='brainyes-cluster',
                    taskDefinition='brainyes-task',
                    launchType='FARGATE',
                    networkConfiguration={
                        'awsvpcConfiguration': {
                            'subnets': [
                                # We'll get these from environment variables
                                os.environ.get('SUBNET_1'),
                                os.environ.get('SUBNET_2')
                            ],
                            'securityGroups': [
                                os.environ.get('SECURITY_GROUP')
                            ],
                            'assignPublicIp': 'ENABLED'
                        }
                    },
                    overrides={
                        'containerOverrides': [
                            {
                                'name': 'brainyes-container',
                                'environment': [
                                    {'name': 'TASK_ID', 'value': task_id},
                                    {'name': 'FUNCTION_NAME', 'value': function_name},
                                    {'name': 'PARAMETERS', 'value': json.dumps(parameters)}
                                ]
                            }
                        ]
                    }
                )

                # Extract task ARN from response
                if ecs_response.get('tasks'):
                    task_arn = ecs_response['tasks'][0]['taskArn']
                    print(f"Started ECS task: {task_arn}")

                    # Update database with ECS task ARN
                    update_data = {
                        'ecs_task_arn': task_arn,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    supabase.table('async_tasks').update(update_data).eq('id', task_id).execute()
                    print(f"Updated task {task_id} with ECS task ARN")

                else:
                    print(f"Failed to start ECS task for {task_id}")
                    # Mark task as failed
                    update_data = {
                        'status': 'failed',
                        'error': 'Failed to start ECS task',
                        'completed_at': datetime.now(timezone.utc).isoformat()
                    }
                    supabase.table('async_tasks').update(update_data).eq('id', task_id).execute()

            except Exception as e:
                print(f"Error processing SQS record: {str(e)}")
                import traceback
                import sentry_sdk
                print(f"Traceback: {traceback.format_exc()}")
                sentry_sdk.capture_exception(e)
                continue

        return {
            'statusCode': 200,
            'body': json.dumps({'success': True, 'processed': len(event.get('Records', []))})
        }

    except Exception as e:
        print(f"Error in sqs_to_ecs_handler: {str(e)}")
        import traceback
        import sentry_sdk
        print(f"Traceback: {traceback.format_exc()}")
        sentry_sdk.capture_exception(e)
        return {
            'statusCode': 500,
            'body': json.dumps({'success': False, 'error': str(e)})
        }

def ecs_task_event_handler(event, context):
    """Handle ECS task state change events from EventBridge"""
    try:
        print(f"Received ECS task event: {json.dumps(event, default=str)}")

        # Extract event details
        detail = event.get('detail', {})
        task_arn = detail.get('taskArn', '')
        last_status = detail.get('lastStatus', '')
        stop_code = detail.get('stopCode', '')
        stopped_reason = detail.get('stoppedReason', '')
        containers = detail.get('containers', [])

        if not task_arn:
            print("No task ARN in event, skipping")
            return

        print(f"Task {task_arn} status: {last_status}")

        # Find the corresponding task in our database
        result = supabase.table('async_tasks').select('*').eq('ecs_task_arn', task_arn).execute()

        if not result.data:
            print(f"No matching task found for ECS task ARN: {task_arn}")
            return

        task = result.data[0]
        task_id = task['id']

        # Handle different ECS task states
        if last_status == 'RUNNING':
            # Task started successfully
            if task.get('status') == 'pending':
                update_data = {
                    'status': 'running',
                    'started_at': datetime.now(timezone.utc).isoformat()
                }
                supabase.table('async_tasks').update(update_data).eq('id', task_id).execute()
                print(f"Updated task {task_id} to running")

        elif last_status == 'STOPPED':
            # Task stopped - check if it was successful or failed
            failed_containers = [c for c in containers if c.get('exitCode', 0) != 0]

            if failed_containers:
                # Task failed
                exit_codes = [str(c.get('exitCode', 'unknown')) for c in failed_containers]
                error_msg = f"Container failed with exit code(s): {', '.join(exit_codes)}"
                if stopped_reason:
                    error_msg += f". Reason: {stopped_reason}"

                update_data = {
                    'status': 'failed',
                    'error': error_msg,
                    'completed_at': datetime.now(timezone.utc).isoformat()
                }
                supabase.table('async_tasks').update(update_data).eq('id', task_id).execute()
                print(f"Updated task {task_id} to failed: {error_msg}")

            elif stop_code in ['UserInitiated', 'SpotInterruption', 'TerminationNotice']:
                # Task was stopped externally
                update_data = {
                    'status': 'failed',
                    'error': f"Task stopped: {stopped_reason}",
                    'completed_at': datetime.now(timezone.utc).isoformat()
                }
                supabase.table('async_tasks').update(update_data).eq('id', task_id).execute()
                print(f"Updated task {task_id} to failed (external stop): {stopped_reason}")

            else:
                # Task completed successfully (exit code 0)
                # Note: Successful tasks should already be marked as completed by the ECS handler itself
                # This is just a safety net
                if task.get('status') not in ['completed', 'failed']:
                    update_data = {
                        'status': 'completed',
                        'completed_at': datetime.now(timezone.utc).isoformat()
                    }
                    supabase.table('async_tasks').update(update_data).eq('id', task_id).execute()
                    print(f"Updated task {task_id} to completed (safety net)")

        return {
            'statusCode': 200,
            'body': json.dumps({'success': True, 'processed': task_id})
        }

    except Exception as e:
        print(f"Error processing ECS task event: {str(e)}")
        import traceback
        import sentry_sdk
        print(f"Traceback: {traceback.format_exc()}")
        sentry_sdk.capture_exception(e)
        return {
            'statusCode': 500,
            'body': json.dumps({'success': False, 'error': str(e)})
        }

def router_handler(event, context):
    """Single router handler that routes requests to appropriate functionality"""
    try:
        # Check if this is an EventBridge event (ECS task state change)
        if 'source' in event and event.get('source') == 'aws.ecs':
            print("Routing to ECS task event handler")
            return ecs_task_event_handler(event, context)

        # Check if this is an SQS event
        if 'Records' in event and event['Records'] and event['Records'][0].get('eventSource') == 'aws:sqs':
            print("Routing to SQS to ECS handler")
            return sqs_to_ecs_handler(event, context)

        # Otherwise, handle as API Gateway event
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
        import sentry_sdk
        sentry_sdk.capture_exception(e)
        return create_response(500, {
            'success': False,
            'error': f'Router error: {str(e)}'
        })