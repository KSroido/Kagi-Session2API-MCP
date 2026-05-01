"""Custom exceptions for Kagi Session MCP Server."""

from enum import Enum


class ErrorType(Enum):
    """Structured error types for programmatic error handling."""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    PARSE = "parse"
    CONFIG = "config"
    API = "api"


class KagiSessionError(Exception):
    """Base exception for Kagi session errors."""

    def __init__(self, message: str, error_type: ErrorType = ErrorType.API):
        self.message = message
        self.error_type = error_type
        self.provider = "kagi-session"
        super().__init__(message)


class TokenExpiredError(KagiSessionError):
    """Session token has expired or is invalid."""

    def __init__(self, message: str = "Session token is invalid or expired"):
        super().__init__(message, ErrorType.AUTH)


class TokenNotFoundError(KagiSessionError):
    """No session token found in config or environment."""

    def __init__(self, message: str = "No session token found"):
        super().__init__(message, ErrorType.AUTH)


class ConfigError(KagiSessionError):
    """Configuration file error."""

    def __init__(self, message: str = "Configuration error"):
        super().__init__(message, ErrorType.CONFIG)


class ParseError(KagiSessionError):
    """Failed to parse Kagi HTML response."""

    def __init__(self, message: str = "Failed to parse Kagi response"):
        super().__init__(message, ErrorType.PARSE)


class RateLimitError(KagiSessionError):
    """Rate limited by Kagi."""

    def __init__(self, message: str = "Rate limited by Kagi"):
        super().__init__(message, ErrorType.RATE_LIMIT)


class NetworkError(KagiSessionError):
    """Network connectivity issue."""

    def __init__(self, message: str = "Network error"):
        super().__init__(message, ErrorType.NETWORK)
