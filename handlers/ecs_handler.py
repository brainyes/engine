#!/usr/bin/env python3
"""
Task runner for ECS Fargate tasks.
Reads messages from SQS, executes long-running functions, and updates status in Supabase.
"""

import json
import os
import sys
import time
import traceback
import boto3
import importlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Import utilities
from utilities.data import supabase


def get_function_names():
    """Get list of function names without importing them"""
    functions_dir = Path(__file__).parent / "functions"
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
                print(f"Successfully imported function: {function_name}")
                return func
    except Exception as e:
        print(f"Could not import {function_name}: {e}")
    return None

# Cache for imported functions (persists across multiple task executions in same container)
IMPORTED_FUNCTIONS = {}

# Initialize AWS clients
sqs = boto3.client('sqs')
sns = boto3.client('sns')
ecs = boto3.client('ecs')

# Environment variables
TASK_QUEUE_URL = os.environ.get('TASK_QUEUE_URL', '')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
ECS_TASK_ARN = os.environ.get('ECS_TASK_ARN', '')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

class TaskRunner:
    def __init__(self):
        self.task_id = None
        self.function_name = None
        self.parameters = {}
        self.start_time = datetime.now(timezone.utc)
        
    def update_task_status(self, status: str, result: Optional[Dict] = None, error: Optional[str] = None):
        """Update task status in Supabase"""
        try:
            update_data = {
                'status': status,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            if status == 'running':
                update_data['started_at'] = datetime.now(timezone.utc).isoformat()
                update_data['ecs_task_arn'] = ECS_TASK_ARN
                update_data['logs_url'] = f"https://console.aws.amazon.com/cloudwatch/home?region={AWS_REGION}#logsV2:log-groups"
            elif status == 'completed':
                update_data['completed_at'] = datetime.now(timezone.utc).isoformat()
                if result:
                    update_data['result'] = result
            elif status == 'failed':
                update_data['completed_at'] = datetime.now(timezone.utc).isoformat()
                if error:
                    update_data['error'] = error
            
            supabase.table('async_tasks').update(update_data).eq('id', self.task_id).execute()
            print(f"Updated task {self.task_id} status to {status}")
            
        except Exception as e:
            print(f"Error updating task status: {str(e)}")
    
    def send_notification(self, subject: str, message: str):
        """Send SNS notification"""
        if not SNS_TOPIC_ARN:
            return
            
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=subject,
                Message=message
            )
            print(f"Sent notification: {subject}")
        except Exception as e:
            print(f"Error sending notification: {str(e)}")
    
    def process_message(self, message: Dict[str, Any]):
        """Process a single SQS message"""
        try:
            # Extract task details
            body = json.loads(message['Body'])
            self.task_id = body.get('task_id')
            self.function_name = body.get('function_name')
            self.parameters = body.get('parameters', {})
            
            # Validate required fields
            if not self.task_id:
                raise ValueError("task_id is required in message body")
            if not self.function_name:
                raise ValueError("function_name is required in message body")
            
            print(f"Processing task {self.task_id}: {self.function_name}")
            print(f"Parameters: {json.dumps(self.parameters, default=str)}")
            
            # Update status to running
            self.update_task_status('running')
            
            # Check if function exists (without importing all modules)
            available_function_names = get_function_names()
            if self.function_name not in available_function_names:
                raise ValueError(f"Unknown function: {self.function_name}. Available functions: {available_function_names}")
            
            # Check cache first, then lazy import if needed
            if self.function_name in IMPORTED_FUNCTIONS:
                func = IMPORTED_FUNCTIONS[self.function_name]
                print(f"Using cached function: {self.function_name}")
            else:
                func = lazy_import_function(self.function_name)
                if func:
                    IMPORTED_FUNCTIONS[self.function_name] = func
                else:
                    raise ImportError(f"Failed to import function: {self.function_name}")
            
            # Execute the function with proper error handling
            start_time = time.time()
            try:
                result = func(**self.parameters)
            except TypeError as e:
                # Handle parameter mismatch errors specifically
                raise ValueError(f"Parameter error calling {self.function_name}: {str(e)}")
            execution_time = time.time() - start_time
            
            # Update status to completed
            self.update_task_status('completed', result={
                'execution_time_seconds': execution_time,
                'function_result': result
            })
            
            # Send success notification
            self.send_notification(
                f"Task {self.task_id} completed successfully",
                f"Function: {self.function_name}\nExecution time: {execution_time:.2f} seconds\nResult: {json.dumps(result, indent=2)}"
            )
            
            # Delete message from queue
            receipt_handle = message['ReceiptHandle']
            sqs.delete_message(
                QueueUrl=TASK_QUEUE_URL,
                ReceiptHandle=receipt_handle
            )
            print(f"Message deleted from queue")
            
            print(f"Task {self.task_id} completed successfully in {execution_time:.2f} seconds")
            print(f"Total container runtime: {(datetime.now(timezone.utc) - self.start_time).total_seconds():.2f} seconds")
            
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            full_error = f"Error processing task: {error_msg}\n{error_trace}"
            print(f"ERROR: {error_msg}")
            print(f"TRACEBACK: {error_trace}")
            
            # Update status to failed (only if we have a task_id)
            if self.task_id:
                self.update_task_status('failed', error=full_error)
            
            # Send failure notification (only if we have task_id)
            if self.task_id:
                self.send_notification(
                    f"Task {self.task_id} failed",
                    f"Function: {self.function_name}\nError: {full_error}"
                )
            
            # Don't delete the message - let it go to DLQ after retries
            raise
    
    def run(self):
        """Main loop to process messages from SQS"""
        print("Task runner started")
        if not TASK_QUEUE_URL:
            print("ERROR: TASK_QUEUE_URL environment variable not set")
            sys.exit(1)

        print(f"Queue URL: {TASK_QUEUE_URL}")
        print(f"Available functions: {get_function_names()}")
        
        # Process a single message (ECS task is triggered per message)
        try:
            # Receive message from SQS with error handling
            print("Polling SQS for messages...")
            response = sqs.receive_message(
                QueueUrl=TASK_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,  # Long polling
                VisibilityTimeout=43200  # 12 hours
            )
            
            messages = response.get('Messages', [])
            
            if not messages:
                print("No messages in queue, exiting gracefully")
                return
            
            # Process the message
            message = messages[0]
            self.process_message(message)
            
        except Exception as e:
            print(f"Fatal error in task runner: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            # Send notification if possible
            if self.task_id:
                self.send_notification(
                    "Task runner fatal error",
                    f"Task: {self.task_id}\nError: {str(e)}\n{traceback.format_exc()}"
                )
            sys.exit(1)

def main():
    """Entry point"""
    print(f"Task Runner Starting - {datetime.now(timezone.utc).isoformat()}")
    print(f"Environment: AWS_REGION={AWS_REGION}, ECS_TASK_ARN={ECS_TASK_ARN}")
    
    runner = TaskRunner()
    runner.run()
    
    print(f"Task Runner Completed - {datetime.now(timezone.utc).isoformat()}")

if __name__ == '__main__':
    main()