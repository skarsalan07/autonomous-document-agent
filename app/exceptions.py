"""Application-specific errors with explicit retry semantics."""


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is unavailable."""


class PlanningError(RuntimeError):
    """Raised when the model cannot produce a valid executable plan."""


class PlanValidationError(ValueError):
    """Raised when a plan contains invalid tasks, tools, or dependencies."""


class RetryableOperationError(RuntimeError):
    """Raised only for operations known to be transient."""


class WorkflowError(RuntimeError):
    """Raised when execution cannot produce a validated document."""
