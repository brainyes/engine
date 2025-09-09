# BrainYes engine

## Infinitely scalable MRI processing engine

See `./docs`.


# Deployment notes

CI/CD deployment:
```
sam deploy --profile brainyes -t codepipeline.yaml --parameter-overrides SupabaseUrl="${SUPABASE_URL}" SupabaseKey="${SUPABASE_KEY}" --stack-name brainyes-engine-pipeline-stacksam
```
