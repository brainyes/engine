# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start the FastAPI server
uvicorn server:app --reload
```

### Python Environment
```bash
# Install dependencies
pip install -r requirements.txt

# Run individual functions directly
python -m functions.function_name FILE_ID

# Example function calls
python -m functions.upload_nifti path/to/file.nii.gz
python -m functions.calculate_roi_volumes FILE_ID
python -m functions.resample_atlas_for_user_nifti FILE_ID
```

### Testing Functions
```bash
# Test with example data
python -m functions.upload_nifti research/input/raw/sub-OASIS10001_ses-M00_T1w.nii.gz
python -m functions.annot-to-json research/input/raw/lh.custom_regions_de_ki.annot

# Get help for any function
python -m functions.function_name --help
```

### FastSurfer Processing (Fast Deep Learning Alternative to FreeSurfer)

FastSurfer is ~10-20x faster than FreeSurfer with comparable accuracy.

```bash
# Quick segmentation only (~5 minutes with GPU)
python -m functions.fastsurfer_recon_all FILE_ID --seg-only --device cuda

# Full pipeline (~60-90 minutes with GPU)
python -m functions.fastsurfer_recon_all FILE_ID --device cuda --parallel-cores 8

# Store FastSurfer outputs
python -m functions.fastsurfer_store_files FILE_ID FASTSURFER_OUTPUT_DIR --storage-mode essential

# Parse and store statistics
python -m functions.fastsurfer_parse_statistics FILE_ID FASTSURFER_OUTPUT_DIR

# Complete workflow example
FILE_ID=d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9
python -m functions.fastsurfer_recon_all $FILE_ID --seg-only --subjects-dir ./___fastsurfer_output
python -m functions.fastsurfer_store_files $FILE_ID ./___fastsurfer_output/sub-$FILE_ID --storage-mode essential
python -m functions.fastsurfer_parse_statistics $FILE_ID ./___fastsurfer_output/sub-$FILE_ID
```

**FastSurfer Requirements**:
- FreeSurfer 7 (installed alongside FreeSurfer 8 in Docker)
- FastSurfer submodule initialized: `git submodule update --init FastSurfer`
- GPU recommended for speed (CPU works but slower)

See `docs/FASTSURFER_INTEGRATION.md` for detailed guide.
### Automated Testing
```bash
# Run quick tests (recommended before commits)
python tests/test_functions.py

# Run all tests including slow ones
python tests/test_functions.py --full

# Test specific function
python tests/test_functions.py --function calculate_roi_volumes

# Show detailed errors
python tests/test_functions.py --verbose
```

The test suite uses pre-existing data:
- NIFTI ID: `d7db5b0a-d967-4dcc-9c7d-43d8d4a48dc9`
- DICOM Series ID: `cb5ff621-12f7-4b80-9d31-4ff96df99fa6`

See `tests/README.md` for more details.

### Population Norms System (Pipeline v2 - Registration-Based)

**IMPORTANT**: As of 2025-10-23, the pipeline uses proper registration for accurate measurements.

```bash
# Check dependencies first
python -m utilities.dependency_checker

# Download population dataset metadata
python -m functions.download_oasis_dataset --dataset oasis-1 --count 100

# NEW: Batch process population scans with v2 pipeline
# (includes preprocessing, registration, atlas warping, and volume calculation)
python -m functions.batch_process_population_dataset \
    research/input/datasets/oasis-1/raw \
    --dataset oasis-1 \
    --metadata research/input/datasets/oasis-1/selected_subjects.csv

# Or run steps individually:
python -m functions.preprocess_native_scan FILE_ID              # N4 + skull-strip + ICV
python -m functions.register_to_template FILE_ID                # ANTs registration
python -m functions.resample_atlas_for_user_nifti FILE_ID --population-mode  # Atlas warping
python -m functions.calculate_roi_volumes FILE_ID               # Volume measurement

# Compute population norms (with ICV-adjusted regression)
python -m functions.compute_population_norms --dataset oasis-1 --min-samples 30

# Compare individual scan to population norms
python -m functions.compare_to_population_norms FILE_ID --age 45 --sex M
```

**Workflow Overview (v2)**:
1. **Download**: Get dataset metadata and subject lists
2. **Preprocess**: N4 bias correction + skull-stripping + ICV computation
3. **Register**: Nonlinear registration to template (OASIS for OASIS datasets, MNI152 for others)
4. **Process**: Warp atlas to native space + calculate volumes
5. **Compute**: Calculate ICV-adjusted statistical norms using regression models
6. **Compare**: Match individual scans to age/sex/ICV-stratified norms

**NEW: OASIS Template Support** (as of 2025-10-24):
- Batch processor **automatically uses OASIS template** for OASIS datasets
- Pre-built template from ANTs (age-matched, research-grade quality)
- Better accuracy than generic MNI152 for population norms
- See `docs/OASIS_TEMPLATE_SETUP.md` for details

**Critical Changes from v1**:
- ❌ **v1 (WRONG)**: Geometric atlas resampling → meaningless volumes
- ✅ **v2 (CORRECT)**: Proper registration + inverse warp → accurate anatomy

**Database Tables Required**:
- `population_scans` - Metadata for population scans (age, sex, ICV, registration method)
- `normative_brain_data` - Computed norms (mean, std, percentiles, regression models)
- `population_comparisons` - Individual comparison results (z-scores, percentiles)

**Database Migration**:
```bash
# Run migration to add v2 fields
psql -h your-host -U postgres -d postgres -f migrations/002_population_v2_registration.sql
```

See `docs/POPULATION_NORMS_GUIDE.md` for detailed instructions.
See `docs/DATABASE_SCHEMA_POPULATION_NORMS.md` for database setup.

## Architecture Overview

### Core Components

**1. Function-Based Processing Pipeline**
- `functions/` - Individual neuroimaging processing functions
- Each function follows template pattern (`functions/template.py`)
- Functions can run standalone via CLI
- All functions use standardized utilities for database and file operations

**2. Data Management**
- `utilities/data.py` - Supabase database connection
- `utilities/supabase_utilities.py` - File upload/download helpers
- `research/input/` - Reference datasets and atlases
- Database stores processing results and metadata

**3. Neuroimaging Analysis**
- `insights/` - Research analysis and scientific insights
- `utilities/freesurfer_parsers.py` - FreeSurfer output parsing
- `utilities/volume_labels.py` - Brain region label mappings
- Harvard-Oxford atlas integration for ROI analysis

### Function Development Pattern

All processing functions follow this structure:
1. **Input validation** - Check file IDs and parameters
2. **Data loading** - Use `get_nifti_file()` and `download_nifti_file()`
3. **Processing logic** - Core neuroimaging analysis
4. **Database storage** - Save results to Supabase
5. **CLI interface** - Argparse for scientist-friendly command line

### Key Dependencies
- **FastAPI** - Web framework for API endpoints
- **Supabase** - Database and file storage
- **nibabel** - NIFTI file handling
- **numpy/scipy** - Numerical processing for brain imaging
- **matplotlib/seaborn** - Visualization and plotting

### Data Flow
1. Scientists upload NIFTI files via `upload_nifti` function or web interface
2. Functions can be called individually via CLI for processing steps:
   - Atlas resampling aligns reference brain regions to user data
   - ROI volume calculation extracts quantitative measurements
3. Results stored in database with file ID relationships
4. Insights and analysis functions process results for research

### File Organization
- `functions/` - Processing pipeline components
- `utilities/` - Shared database, file, and parsing utilities  
- `insights/` - Research analysis and scientific studies
- `research/` - Input datasets, processed data, and outputs
- `docs/` - User guides for scientists and developers

### Integration Points
- All functions use shared Supabase utilities for consistency
- Template-based development ensures standardized function structure
- CLI interfaces allow scientists to run individual processing steps
- Functions can be orchestrated via web API or called directly

---

## AWS Deployment & Infrastructure Learnings

### Project Infrastructure Overview
- **Lambda Functions**: Consolidated into single function with router pattern
- **ECS Fargate**: For long-running neuroimaging computations
- **Docker Images**: Separate images for Lambda (AWS runtime) and ECS (Ubuntu)
- **CI/CD**: CodePipeline with CodeBuild for automated deployments
- **Infrastructure**: SAM/CloudFormation for Infrastructure as Code

### Key Deployment Issues & Solutions

#### 1. Docker & Package Version Compatibility

**Problem**: matplotlib 3.9.2 not available for Python 3.9
```
ERROR: Could not find a version that satisfies the requirement matplotlib==3.9.2
```

**Solution**: Upgrade to Ubuntu 24.04 with Python 3.12
```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y python3.12 python3.12-venv
RUN python3.12 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
```

**Package Changes for Ubuntu 24.04**:
- `libtiff5` → `libtiff6`
- `libjpeg62` → `libjpeg62-dev`
- `libgtk2.0-0` → `libgtk-3-0`
- Must use virtual environment (Python 3.12 externally-managed)

#### 2. Lambda Function Optimization

**Problem**: 5 separate Lambda functions with identical codebases
**Solution**: Router pattern in single Lambda function
```python
def router_handler(event, context):
    path = event.get('resource', '')
    method = event.get('httpMethod', '')
    
    if path == '/functions' and method == 'GET':
        return list_functions_handler(event, context)
    elif path == '/function/{function_name}' and method == 'POST':
        return generic_function_handler(event, context)
    # ... more routes
```

**Benefits**: Single Docker build, better Lambda reuse, simplified permissions

#### 3. Environment Variable Issues

**Problem**: `AWS_DEFAULT_PROFILE=brainyes` in `.env` causing Lambda errors
```
ProfileNotFound: The config profile (brainyes) could not be found
```

**Solution**: Remove AWS_DEFAULT_PROFILE from `.env` - Lambda uses IAM roles, not CLI profiles

#### 4. CodePipeline IAM Permission Issues

**ECR Permissions**: Add to CodeBuildServiceRole
```yaml
- PolicyName: ECRAccess
  PolicyDocument:
    Statement:
      - Effect: Allow
        Action:
          - ecr:GetAuthorizationToken
          - ecr:BatchCheckLayerAvailability
          - ecr:GetDownloadUrlForLayer
          - ecr:BatchGetImage
          - ecr:BatchImportLayerPart
          - ecr:UploadLayerPart
          - ecr:InitiateLayerUpload
          - ecr:CompleteLayerUpload
          - ecr:PutImage
        Resource: "*"
```

**CloudFormation & S3 Permissions**: Add for SAM deployments
```yaml
- PolicyName: CloudFormationAccess
  PolicyDocument:
    Statement:
      - Effect: Allow
        Action:
          - cloudformation:*
          - iam:PassRole
        Resource: "*"

- PolicyName: SAMDeploymentBucketAccess
  PolicyDocument:
    Statement:
      - Effect: Allow
        Action:
          - s3:GetObject
          - s3:GetObjectVersion
          - s3:PutObject
          - s3:GetBucketLocation
        Resource:
          - !Sub "arn:${AWS::Partition}:s3:::${TestingArtifactBucket}/*"
          - !Sub "arn:${AWS::Partition}:s3:::${ProdArtifactBucket}/*"
```

#### 5. ECR Repository Management

**Problem**: SAM auto-generates unpredictable ECR repo names like `brainyesengine5b45d9ef`

**Solution**: Manage ECR repositories in CloudFormation
```yaml
LambdaECRRepository:
  Type: AWS::ECR::Repository
  Properties:
    RepositoryName: lambda
    LifecyclePolicy:
      LifecyclePolicyText: |
        {
          "rules": [{
            "rulePriority": 1,
            "description": "Keep last 10 images",
            "selection": {
              "tagStatus": "any",
              "countType": "imageCountMoreThan",
              "countNumber": 10
            },
            "action": {"type": "expire"}
          }]
        }
```

Set in samconfig.toml:
```toml
resolve_image_repos = false  # Disable auto-creation
image_repository = "<AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/lambda"
```

#### 6. Pipeline Optimization

**Problem**: UpdatePipeline stage adds 2-3 minutes per run checking for changes
**Solution**: Comment out and manually deploy pipeline changes when needed

**Problem**: Test environment doesn't exist
**Solution**: Comment out DeployTest stage until test environment is ready

### Docker Image Strategy

**Lambda Image** (`Dockerfile.lambda`):
- Base: `public.ecr.aws/lambda/python:3.12`
- Optimized for quick starts, minimal dependencies
- Entry: `handlers.lambda_handlers.router_handler`

**ECS Image** (`Dockerfile`):
- Base: `ubuntu:24.04`
- Full system dependencies, FreeSurfer support
- Entry: `handlers/ecs_handler.py`

**Key**: Don't try to use one image for both - they have different optimization goals

### Essential Commands

#### Local Development
```bash
# Build Docker images
docker build -t brainyes-engine .
docker build -f Dockerfile.lambda -t brainyes-lambda .

# SAM local testing
sam build --profile brainyes --template-file template-docker.yaml
sam local start-api
```

#### Deployment
```bash
# Update pipeline (when codepipeline.yaml changes)
sam deploy -t codepipeline.yaml --stack-name brainyes-pipeline \
  --capabilities=CAPABILITY_IAM --profile brainyes \
  --parameter-overrides "FullRepositoryId=brainyes/engine"

# Manual application deployment (if needed)
sam build --profile brainyes --template-file template-docker.yaml
sam deploy --profile brainyes
```

#### ECR Management
```bash
# Login to ECR
aws ecr get-login-password --region us-east-2 --profile brainyes | \
  docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com

# Push images
docker tag brainyes-lambda:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/lambda:latest
docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/lambda:latest
```

### Best Practices Learned

1. **Always use virtual environments** in Docker for Python 3.12+
2. **Keep Lambda and ECS Docker images separate** - different optimization needs
3. **Define ECR repositories in CloudFormation** for predictable names
4. **Use router pattern** for multiple Lambda endpoints in same codebase
5. **Don't include AWS_DEFAULT_PROFILE** in production .env files
6. **Start with minimal IAM permissions** and add iteratively as needed
7. **Comment out unused pipeline stages** rather than deleting
8. **Use parameter overrides** for environment-specific values

### Cost Optimization

- Single Lambda function reduces cold starts and provisioned concurrency needs
- No NAT Gateway - use public subnets for ECS with public IPs
- Lifecycle policies on ECR - keep only last 10 images
- Comment out test environment if not actively used
- Use Fargate Spot for non-critical ECS tasks

### Security Considerations

- Secrets in CloudFormation: Use `NoEcho: true` for sensitive parameters
- IAM roles: Follow least privilege principle
- VPC security groups: Restrict to necessary traffic only
- S3 buckets: Encrypted with AES256
- Never commit secrets: Keep Supabase keys in parameters, not code

### Troubleshooting Tips

1. **Check CloudWatch Logs** first - most errors are logged there
2. **Use AWS Console** to view pipeline execution details
3. **Check IAM permissions** when getting access denied errors
4. **Verify Docker images pushed** to correct ECR repositories
5. **Check environment variables** in Lambda console
6. **Use `sam validate`** before deploying templates
7. **Review CloudFormation events** for stack creation failures

### Pipeline Architecture Final State

Current pipeline stages:
1. **Source** - Pull from GitHub (brainyes/engine)
2. **BuildAndPackage** - SAM build and create deployment artifacts
3. **DeployProd** - Deploy to production Lambda/ECS stack
4. **BuildAndPushEngine** - Build and push ECS container image

Commented out stages:
- UpdatePipeline (takes 2-3 minutes, rarely needed)
- DeployTest (test environment not configured)

---

*Last Updated: 2025-10-14 - Removed Inngest orchestration dependencies*
- supabase database migrations are kept in `app` app directory, not in `engine`.