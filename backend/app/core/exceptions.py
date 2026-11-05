"""Application exceptions."""

from typing import Any


class UZEXException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        code: str = "internal_error",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(UZEXException):
    """Resource not found."""

    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            message=f"{resource} with identifier '{identifier}' not found",
            code="not_found",
            status_code=404,
            details={"resource": resource, "identifier": str(identifier)},
        )


class AlreadyExistsError(UZEXException):
    """Resource already exists."""

    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            message=f"{resource} with identifier '{identifier}' already exists",
            code="already_exists",
            status_code=409,
            details={"resource": resource, "identifier": str(identifier)},
        )


class ValidationError(UZEXException):
    """Business validation error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message, code="validation_error", status_code=400, details=details or {}
        )


class ImportError(UZEXException):
    """CSV import error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message, code="import_error", status_code=422, details=details or {}
        )


class AIError(UZEXException):
    """AI engine error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message, code="ai_error", status_code=502, details=details or {}
        )


class RateLimitError(UZEXException):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(
            message=message, code="rate_limit_exceeded", status_code=429
        )


class ConfigurationError(UZEXException):
    """Configuration error."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message, code="configuration_error", status_code=500
        )
