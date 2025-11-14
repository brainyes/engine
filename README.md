# BrainYes engine


## Cloning

You need to clone this `engine` repo with submodules for FastSurfer:
```
git clone --recurse-submodules https://github.com/brainyes/engine.git
```

## Infinitely scalable MRI processing engine

See `./docs`.


# Deployment notes

CI/CD deployment:
```
sam deploy --profile brainyes -t codepipeline.yaml --parameter-overrides SupabaseUrl="${SUPABASE_URL}" SupabaseKey="${SUPABASE_KEY}" --stack-name brainyes-engine-pipeline-stacksam
```
