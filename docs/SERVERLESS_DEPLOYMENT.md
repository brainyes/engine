# BrainYes Engine Serverless Deployment Guide

This guide explains how to deploy the BrainYes Engine using AWS SAM with Lambda functions for quick operations and ECS Fargate for long-running tasks.

## Architecture Overview

- **Synchronous Operations** (< 15 min): API Gateway → Lambda → Direct Response
- **Asynchronous Operations** (hours): API Gateway → Lambda → SQS → ECS Fargate → Supabase

## Prerequisites

1. AWS CLI installed and configured
2. AWS SAM CLI installed
3. Docker installed
4. Supabase project with service role key
5. Python 3.9+

## Setup Instructions

### 1. Install Dependencies

```bash
# Install AWS SAM CLI
pip install aws-sam-cli

# Install project dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` and `env.json` files, see `.env.example` and `env.example.json` files.

### 3. Develop and Build with SAM

Invoice local Lambda function: 

```
sam local invoke ListFunctionsHandler 
```

Run local API Gateway with Lambda functions: 

```
sam local start-api --warm-containers eager --env-vars env.json
```

### 4. Build Docker Image

```bash
# Build the Docker image for ECS tasks
docker build -t cerebro-engine .

# Create ECR repository
aws ecr create-repository --repository-name brainyes-engine

# Get login token
aws ecr get-login-password --profile brainyes --region us-east-2 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com

# Tag and push image
docker tag brainyes-engine:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/brainyes-engine:latest
docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/brainyes-engine:latest
```

### 5. Deploy with SAM

```bash
# On Mac, SAM CLI needs this environment variable...
export DOCKER_HOST=$(docker context inspect | jq -r '.[0].Endpoints.docker.Host')

# Build the SAM application
sam build --profile brainyes --template-file template-docker.yaml

# Deploy (first time)
sam deploy --profile brainyes --guided \
  --template-file template-docker.yaml \
  --parameter-overrides \
  SupabaseUrl=$SUPABASE_URL \
  SupabaseKey=$SUPABASE_KEY
  
# Or
sam deploy --profile brainyes  \
    --parameter-overrides \
        ECSImageUri="<AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/engine" \
        SupabaseUrl="${SUPABASE_URL}" \
        SupabaseKey="${SUPABASE_KEY}" 
# Or
sam deploy --profile brainyes

# Subsequent deployments (after building with --template-file template-docker.yaml)
sam deploy --profile brainyes 
```

`samconfig.toml ` file contains some default for your `sam` commands. Especially  `image_repository` may be different than what happened in `sam deploy` commands.

### 6. Deploy the CI/CD pipeline infrastructure
If you are starting a new AWS environment from scratch, you probably want to run this first to create ECR images.

```
sam deploy -t codepipeline.yaml --stack-name brainyes-pipeline --capabilities=CAPABILITY_IAM --profile brainyes
```

You can also use the same command to update the CI/CD pipelines defined in `codepipeline.yml` as CloudFormation stack.

CodeBuild will use `buildspec*.yml` files in `./pipeline/` directory.

## Debugging production environment
I typically have these tabs:
- CodePipeline project, to monitor builds
- Lambda and its CloudWatch for monitoring API calls (async stuff also started/monitored there)
- ECS Cluster for async long tasks

## API Endpoints

### List Available Functions
```bash
GET /api/functions

# Returns:
{
  "success": true,
  "functions": {
    "upload_nifti": {
      "parameters": ["nifti_gz", "user_id", "public_id"],
      "doc": "Upload a NIFTI file..."
    },
    "calculate_roi_volumes": {
      "parameters": ["nifti_file_id"],
      "doc": "Calculate ROI volumes..."
    }
  }
}
```

### Synchronous Function Execution

#### Option 1: Function name in path
```bash
POST /api/function/{function_name}
{
  "nifti_gz": "path/to/file.nii.gz",
  "public_id": 1
}
```

#### Option 2: Function name in body
```bash
POST /api/function
{
  "function_name": "upload_nifti",
  "parameters": {
    "nifti_gz": "path/to/file.nii.gz",
    "public_id": 1
  }
}
```

### Asynchronous Function Execution

#### Option 1: Function name in path
```bash
POST /api/async/{function_name}
{
  "parameters": {
    "nifti_file_id": "uuid-here",
    "other_params": "value"
  }
}
```

#### Option 2: Function name in body
```bash
POST /api/async
{
  "function_name": "freesurfer_recon_all",
  "parameters": {
    "nifti_file_id": "uuid-here",
    "other_params": "value"
  }
}

# Returns:
{
  "success": true,
  "task_id": "task-uuid",
  "status": "pending"
}
```

#### Check Task Status
```bash
GET /api/tasks/{task_id}/status

# Returns:
{
  "success": true,
  "task": {
    "id": "task-uuid",
    "status": "running|completed|failed",
    "result": {...},
    "error": "error message if failed"
  }
}
```

#### Get Task Logs
```bash
GET /api/tasks/{task_id}/logs
```

## Using from BrainYes App

### Synchronous Call Example (TypeScript)
```typescript
// Option 1: Function name in path (cleaner)
const response = await fetch(`${CEREBRO_ENGINE_URL}/api/function/calculate_roi_volumes`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    nifti_file_id: fileId
  })
});

// Option 2: Function name in body (more flexible)
const response = await fetch(`${CEREBRO_ENGINE_URL}/api/function`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    function_name: 'calculate_roi_volumes',
    parameters: {
      nifti_file_id: fileId
    }
  })
});

const result = await response.json();
```

### Asynchronous Call Example (TypeScript)
```typescript
// For long-running operations
// 1. Submit task (using path method)
const submitResponse = await fetch(`${CEREBRO_ENGINE_URL}/api/async/freesurfer_recon_all`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    parameters: {
      nifti_file_id: fileId
    }
  })
});

// Or using body method
const submitResponse = await fetch(`${CEREBRO_ENGINE_URL}/api/async`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    function_name: 'freesurfer_recon_all',
    parameters: {
      nifti_file_id: fileId
    }
  })
});

const { task_id } = await submitResponse.json();

// 2. Poll for status
const checkStatus = async () => {
  const statusResponse = await fetch(`${CEREBRO_ENGINE_URL}/api/tasks/${task_id}/status`);
  const { task } = await statusResponse.json();
  
  if (task.status === 'completed') {
    console.log('Task completed:', task.result);
  } else if (task.status === 'failed') {
    console.error('Task failed:', task.error);
  } else {
    // Still running, check again later
    setTimeout(checkStatus, 30000); // Check every 30 seconds
  }
};

checkStatus();

// 3. List available functions
const functionsResponse = await fetch(`${CEREBRO_ENGINE_URL}/api/functions`);
const { functions } = await functionsResponse.json();
console.log('Available functions:', functions);
```

## Monitoring

### CloudWatch Logs
- Lambda logs: `/aws/lambda/brainyes-*`
- ECS logs: `/ecs/brainyes-tasks`

### Task Status in Supabase
```sql
-- View all tasks
SELECT * FROM tasks ORDER BY created_at DESC;

-- View task statistics
SELECT * FROM task_statistics;
```

### SNS Notifications
Configure email notifications by subscribing to the SNS topic created by the stack.

## Cost Optimization

1. **Lambda**: Billed per invocation and duration
   - Quick functions cost pennies per thousands of requests
   
2. **ECS Fargate**: Billed per vCPU and memory per second
   - Long-running tasks only charged for actual runtime
   - Uses Fargate Spot for 66% cost savings

3. **API Gateway**: $3.50 per million requests
4. **SQS**: $0.40 per million messages

## Troubleshooting

### Lambda Function Timeout
- Increase timeout in `template.yaml` (max 15 minutes)
- Consider moving to async/ECS for longer operations

### ECS Task Failures
- Check CloudWatch logs
- Verify Docker image has all dependencies
- Check Supabase connection

### Missing FreeSurfer
- The Dockerfile has a placeholder for FreeSurfer
- Install actual FreeSurfer in production Docker image

## Security Best Practices

1. Use IAM roles, not access keys
2. Enable VPC endpoints for private communication
3. Encrypt environment variables
4. Use Supabase RLS policies
5. Rotate credentials regularly

## Next Steps

1. Install actual FreeSurfer in Docker image
2. Add more long-running functions
3. Implement CloudWatch log streaming to UI
4. Add more granular IAM permissions
