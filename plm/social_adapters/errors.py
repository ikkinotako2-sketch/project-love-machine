class AdapterError(RuntimeError):
    """Base error returned by a platform adapter."""

    def __init__(self, message: str, *, code: str = "adapter_error") -> None:
        super().__init__(message)
        self.code = code


class TransientAdapterError(AdapterError):
    """A temporary error that may be retried within policy limits."""


class PermanentAdapterError(AdapterError):
    """A non-retryable request, authentication, or policy error."""


class UnsupportedOperationError(PermanentAdapterError):
    """Raised when a verified adapter capability is not available."""
