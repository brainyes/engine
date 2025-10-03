import sentry_sdk
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

def init():
    sentry_sdk.init(
        dsn="<REDACTED_SENTRY_DSN>",
        send_default_pii=True,
        integrations=[AwsLambdaIntegration(timeout_warning=True)],
        traces_sample_rate=1.0,  # Capture 100% of transactions for performance monitoring
        profiles_sample_rate=1.0,  # Capture 100% of profiles
    )
