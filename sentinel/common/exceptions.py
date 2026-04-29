"""
Sentinel custom exceptions.

Defines a hierarchy of application-specific exceptions so that error handling
is explicit and consistent across all modules.
"""


class SentinelError(Exception):
    """Base exception for all Sentinel application errors."""

    def __init__(self, message: str = "An internal error occurred"):
        self.message = message
        super().__init__(self.message)


class AuthenticationError(SentinelError):
    """Raised when JWT validation or token parsing fails."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class AuthorizationError(SentinelError):
    """Raised when a user attempts to access content outside their scope."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(message)


class SourceNotFoundError(SentinelError):
    """Raised when a requested source or document does not exist."""

    def __init__(self, message: str = "Source not found"):
        super().__init__(message)


class IngestionError(SentinelError):
    """Raised when a connector or ingestion pipeline encounters a failure."""

    def __init__(self, message: str = "Ingestion failed"):
        super().__init__(message)


class RetrievalError(SentinelError):
    """Raised when the retrieval module cannot complete a search."""

    def __init__(self, message: str = "Retrieval failed"):
        super().__init__(message)


class InsufficientEvidenceError(SentinelError):
    """Raised when there is not enough evidence to generate a grounded answer."""

    def __init__(self, message: str = "Insufficient evidence to answer"):
        super().__init__(message)
