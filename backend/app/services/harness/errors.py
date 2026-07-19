class HarnessError(Exception):
    """Base class for service harness errors."""


class NotFoundError(HarnessError):
    """Raised when a scoped harness resource cannot be found."""


class ValidationFailedError(HarnessError):
    """Raised when a validation gate blocks progress."""


class PermissionScopeError(HarnessError):
    """Raised when a request is outside its authorized scope."""


class UnsafeExecutionError(HarnessError):
    """Raised when a requested execution violates harness safety rules."""
