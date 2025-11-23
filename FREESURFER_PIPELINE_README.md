# FreeSurfer Base Image Pipeline

This is a separate, dedicated pipeline for building FreeSurfer base Docker images. These base images are rarely updated and take 30-45 minutes to build, so they've been moved out of the main pipeline to keep it fast.

## Overview

The FreeSurfer base image pipeline builds:
- FreeSurfer 7.4.1 base image (for FastSurfer)
- FreeSurfer 8.1.0 base image (for full FreeSurfer processing)

These images are pushed to ECR at:
- `<AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/freesurfer:7`
- `<AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/freesurfer:8`

## Deployment

### First Time Setup

1. Get your CodeStar connection ARN from the main pipeline:
```bash
aws cloudformation describe-stacks \
  --stack-name brainyes-pipeline \
  --query 'Stacks[0].Outputs[?OutputKey==`CodeStarConnectionArn`].OutputValue' \
  --output text --profile brainyes
```

2. Deploy the FreeSurfer pipeline:
```bash
sam deploy \
  -t codepipeline-freesurfer.yaml \
  --stack-name brainyes-pipeline-freesurfer \
  --capabilities=CAPABILITY_IAM \
  --profile brainyes \
  --parameter-overrides "CodeStarConnectionArn=<connection-arn-from-step-1>"
```

### Running the Pipeline

1. Go to AWS CodePipeline console
2. Find pipeline: `brainyes-freesurfer-base`
3. Click "Release change" to manually trigger a build
4. Approve the manual approval step when you're ready to build
5. Wait ~30-45 minutes for FreeSurfer images to build

## When to Rebuild

Rebuild FreeSurfer base images when:
- FreeSurfer releases a new version
- You need to change system dependencies in the FreeSurfer images
- You're troubleshooting FreeSurfer installation issues

You do NOT need to rebuild when:
- Making changes to your application code
- Updating Python dependencies
- Building the main engine Docker image

## Architecture

Pipeline stages:
1. **Source**: Pulls from `brainyes/engine` main branch
2. **BuildFreesurferBase**:
   - Manual approval (to avoid accidental expensive builds)
   - CodeBuild project using `BUILD_GENERAL1_LARGE` (8 vCPUs, 15 GB RAM)
   - Runs `pipeline/buildspec_freesurfer_base.yml`
   - Takes ~30-45 minutes
   - Pushes to ECR `freesurfer` repository

## Cost Optimization

- Manual trigger only (no automatic builds on every commit)
- Manual approval step prevents accidental runs
- Uses large instance for faster builds (time vs cost tradeoff)
- ECR lifecycle policy keeps only last 10 images

## Troubleshooting

### Pipeline fails at manual approval
- This is expected - you must approve before the build starts
- Check your email (info@brainyes.com) for approval notification

### Build times out
- Increase timeout in `CodeBuildProjectFreesurferBase` resource
- Default is 60 minutes which should be sufficient

### Out of disk space during build
- FreeSurfer downloads are large (~2GB each)
- BUILD_GENERAL1_LARGE has 128GB disk which should be enough
- Check buildspec for cleanup steps

## Related Files

- `codepipeline-freesurfer.yaml` - Pipeline CloudFormation template
- `pipeline/buildspec_freesurfer_base.yml` - Build instructions
- `Dockerfile` (stages `freesurfer-7-build` and `freesurfer-8-build`) - FreeSurfer installation
- `codepipeline.yaml` - Main pipeline (no longer includes FreeSurfer builds)
