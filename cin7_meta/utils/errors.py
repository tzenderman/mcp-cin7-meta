"""Custom exceptions for Cin7 Core API interactions."""


class Cin7Error(Exception):
    """Base exception for Cin7-related errors."""


class Cin7AuthError(Cin7Error):
    """Raised when authentication fails or credentials are invalid."""


class Cin7NotFoundError(Cin7Error):
    """Raised when a requested resource doesn't exist."""


class Cin7RateLimitError(Cin7Error):
    """Raised when rate limits are exceeded after retries."""


class Cin7APIError(Cin7Error):
    """Raised for generic Cin7 API errors."""


class Cin7ReadOnlyError(Cin7Error):
    """Raised when a write is attempted while `CIN7_READ_ONLY` is set.

    Not a transport failure and not retryable — the server is configured to
    execute GET only. See `cin7_meta.utils.read_only`.
    """
