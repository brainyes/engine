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


`engine` Dockerfile supports both FreeSurfer 7 and 8. During build, you can specify which version you want like this:
```shell
  docker build --target runtime .        # Builds FS 8 path only
  docker build --target runtime-7 .      # Builds FS 7 path only
```