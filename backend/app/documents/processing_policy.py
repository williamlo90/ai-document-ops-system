from app.providers.contracts import ProviderFailure


def should_retry(error: Exception) -> bool:
    return isinstance(error, ProviderFailure) and error.retryable
