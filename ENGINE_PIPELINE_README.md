# ECS Engine Image Pipeline

This is a separate, dedicated pipeline for building the ECS Engine Docker images. These images include FreeSurfer, FastSurfer, and all neuroimaging processing tools. They take ~10 minutes to build and are deployed infrequently.

## Overview

The ECS Engine image pipeline builds the heavy Docker image that includes:
- FreeSurfer 8.1.0 (or FreeSurfer 7.4.1)
- FastSurfer (your custom fork from brainyes/FastSurfer)
- All Python processing functions
- Research input files and atlases

The image is pushed to ECR at:
- `<AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/engine:latest`

After building, the pipeline automatically:
1. Pushes the new image to ECR
2. Updates the ECS task definition
3. Registers the new task definition version

## Deployment

### First Time Setup

1. Get your CodeStar connection ARN from the main pipeline:
```bash
aws cloudformation describe-stacks \
  --stack-name brainyes-pipeline \
  --query 'Stacks[0].Outputs[?OutputKey==`CodeStarConnectionArn`].OutputValue' \
  --output text --profile brainyes
```

2. Deploy the Engine pipeline:
```bash
sam deploy \
  -t codepipeline-engine.yaml \
  --stack-name brainyes-pipeline-engine \
  --capabilities=CAPABILITY_IAM \
  --profile brainyes \
  --parameter-overrides "CodeStarConnectionArn=<connection-arn-from-step-1>"
```

### Running the Pipeline

1. Go to AWS CodePipeline console
2. Find pipeline: `brainyes-engine`
3. Click "Release change" to manually trigger a build
4. Approve the manual approval step when you're ready to build
5. Wait ~10 minutes for the Engine image to build and deploy

## When to Rebuild

Rebuild the Engine image when:
- You've updated FreeSurfer base images (from codepipeline-freesurfer.yaml)
- You've made changes to FastSurfer submodule
- You've updated Python dependencies (requirements.txt)
- You've changed Dockerfile build steps
- You've updated research input files or atlases
- You need to deploy updated processing functions

You do NOT need to rebuild when:
- Making changes only to Lambda functions
- Updating SAM template (template-docker.yaml)
- Changing API endpoints or handlers

## Architecture

Pipeline stages:
1. **Source**: Pulls from `brainyes/engine` main branch
2. **BuildEngine**:
   - Manual approval (to avoid accidental expensive builds)
   - CodeBuild project using `BUILD_GENERAL1_LARGE` (8 vCPUs, 15 GB RAM)
   - Runs `pipeline/buildspec_engine.yml`
   - Takes ~10 minutes
   - Pushes to ECR `engine` repository
   - Updates ECS task definition

## Important Notes

### FastSurfer Submodule
The build automatically initializes the FastSurfer git submodule pointing to your fork:
- `https://github.com/brainyes/FastSurfer.git`

To update FastSurfer in the image:
1. Make changes in FastSurfer submodule locally
2. Commit and push to brainyes/FastSurfer
3. In engine repo: `cd FastSurfer && git pull origin main`
4. In engine repo: `git add FastSurfer && git commit -m "Update FastSurfer"`
5. Push engine repo
6. Trigger this pipeline to rebuild with new FastSurfer

### ECS Task Updates
The pipeline automatically updates the ECS task definition but does NOT restart running tasks. To deploy the new image:

**Option 1: Manual update (recommended for production)**
```bash
aws ecs update-service \
  --cluster brainyes-cluster \
  --service brainyes-service \
  --force-new-deployment \
  --profile brainyes
```

**Option 2: Stop existing tasks (forces immediate restart)**
```bash
# List running tasks
aws ecs list-tasks \
  --cluster brainyes-cluster \
  --service-name brainyes-service \
  --profile brainyes

# Stop task to force restart with new image
aws ecs stop-task \
  --cluster brainyes-cluster \
  --task <task-id> \
  --profile brainyes
```

## Cost Optimization

- Manual trigger only (no automatic builds on every commit)
- Manual approval step prevents accidental runs
- Uses BUILD_GENERAL1_LARGE for faster builds (~10 min vs 30+ min on smaller instances)
- ECR lifecycle policy keeps only last 10 images

## Troubleshooting

### Pipeline fails at manual approval
- This is expected - you must approve before the build starts
- Check your email (info@brainyes.com) for approval notification

### Build fails with "FastSurfer directory not found"
- Check that buildspec_engine.yml includes git submodule initialization
- Verify FastSurfer submodule is configured in .gitmodules
- Ensure submodule URL is accessible: https://github.com/brainyes/FastSurfer.git

### ECS service not using new image
- Pipeline only updates task definition, not running tasks
- Use `aws ecs update-service --force-new-deployment` to deploy
- Or manually stop tasks to force restart with new image

### Build times out
- Increase timeout in `CodeBuildProjectEngineImage` resource
- Default is 60 minutes which should be sufficient
- Check FreeSurfer base images are properly cached in ECR

## Related Files

- `codepipeline-engine.yaml` - Pipeline CloudFormation template
- `pipeline/buildspec_engine.yml` - Build instructions
- `Dockerfile` - Engine image build steps
- `.gitmodules` - FastSurfer submodule configuration
- `codepipeline.yaml` - Main Lambda pipeline (no longer includes Engine builds)
- `codepipeline-freesurfer.yaml` - FreeSurfer base image pipeline
