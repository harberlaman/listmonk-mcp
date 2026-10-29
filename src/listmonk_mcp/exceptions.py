"""Exception classes for the Listmonk MCP server."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from mcp.server.fastmcp.exceptions import ToolError

# Import ListmonkAPIError from client module
from .client import ListmonkAPIError


class ListmonkMCPError(Exception):
    """Base exception class for all Listmonk MCP errors."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:
        """Return a formatted error message."""
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for MCP error responses."""
        result: dict[str, Any] = {
            "error_type": self.__class__.__name__,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.cause:
            result["cause"] = str(self.cause)
        return result


class ValidationError(ListmonkMCPError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any | None = None,
        details: dict[str, Any] | None = None
    ):
        super().__init__(message, details)
        self.field = field
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        """Include field and value information in error response."""
        result = super().to_dict()
        if self.field:
            result["field"] = self.field
        if self.value is not None:
            result["value"] = self.value
        return result


class AuthenticationError(ListmonkMCPError):
    """Raised when authentication with Listmonk fails."""

    def __init__(
        self,
        message: str = "Authentication failed",
        status_code: int | None = None,
        details: dict[str, Any] | None = None
    ):
        super().__init__(message, details)
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Include status code in error response."""
        result = super().to_dict()
        if self.status_code:
            result["status_code"] = self.status_code
        return result


class APIError(ListmonkMCPError):
    """Raised when Listmonk API returns an error response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict[str, Any] | None = None,
        endpoint: str | None = None
    ):
        super().__init__(message, response_data)
        self.status_code = status_code
        self.response_data = response_data or {}
        self.endpoint = endpoint

    def to_dict(self) -> dict[str, Any]:
        """Include API-specific information in error response."""
        result = super().to_dict()
        if self.status_code:
            result["status_code"] = self.status_code
        if self.endpoint:
            result["endpoint"] = self.endpoint
        if self.response_data:
            result["response_data"] = self.response_data
        return result


class ConfigurationError(ListmonkMCPError):
    """Raised when server configuration is invalid or missing."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        details: dict[str, Any] | None = None
    ):
        super().__init__(message, details)
        self.config_key = config_key

    def to_dict(self) -> dict[str, Any]:
        """Include configuration key in error response."""
        result = super().to_dict()
        if self.config_key:
            result["config_key"] = self.config_key
        return result


class OperationError(ListmonkMCPError):
    """Raised when a specific operation cannot be completed."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        resource_id: str | int | None = None,
        details: dict[str, Any] | None = None
    ):
        super().__init__(message, details)
        self.operation = operation
        self.resource_id = resource_id

    def to_dict(self) -> dict[str, Any]:
        """Include operation details in error response."""
        result = super().to_dict()
        if self.operation:
            result["operation"] = self.operation
        if self.resource_id is not None:
            result["resource_id"] = self.resource_id
        return result


class ResourceNotFoundError(OperationError):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str | int,
        details: dict[str, Any] | None = None,
        message: str | None = None
    ):
        message = message or f"{resource_type} with ID '{resource_id}' not found"
        super().__init__(message, "get", resource_id, details)
        self.resource_type = resource_type

    def to_dict(self) -> dict[str, Any]:
        """Include resource type in error response."""
        result = super().to_dict()
        result["resource_type"] = self.resource_type
        return result


class DuplicateResourceError(OperationError):
    """Raised when attempting to create a resource that already exists."""

    def __init__(
        self,
        resource_type: str,
        identifier: str,
        details: dict[str, Any] | None = None,
        message: str | None = None
    ):
        message = message or f"{resource_type} with identifier '{identifier}' already exists"
        super().__init__(message, "create", identifier, details)
        self.resource_type = resource_type
        self.identifier = identifier

    def to_dict(self) -> dict[str, Any]:
        """Include resource type and identifier in error response."""
        result = super().to_dict()
        result["resource_type"] = self.resource_type
        result["identifier"] = self.identifier
        return result


# HTTP Status Code Mapping Utilities

def map_http_status_to_exception(
    status_code: int | None,
    message: str,
    response_data: dict[str, Any] | None = None,
    endpoint: str | None = None
) -> ListmonkMCPError:
    """Map HTTP status codes to appropriate exception types.

    ``status_code`` is None for errors raised before or without an HTTP response
    (a local file not found, a network failure after retries). Listmonk's own
    ``message`` is kept in every branch.
    """

    if status_code is None:
        if "not found" in message.lower():
            return OperationError(message=message, operation="request", details=response_data)
        return APIError(message=message, response_data=response_data, endpoint=endpoint)
    elif status_code == 401:
        return AuthenticationError(
            message=message or "Unauthorized access",
            status_code=status_code,
            details=response_data
        )
    elif status_code == 403:
        return AuthenticationError(
            message=message or "Access forbidden",
            status_code=status_code,
            details=response_data
        )
    elif status_code == 404:
        # Try to determine resource type from endpoint
        resource_type = "Resource"
        if endpoint:
            if "/subscribers/" in endpoint:
                resource_type = "Subscriber"
            elif "/lists/" in endpoint:
                resource_type = "List"
            elif "/campaigns/" in endpoint:
                resource_type = "Campaign"
            elif "/templates/" in endpoint:
                resource_type = "Template"

        return ResourceNotFoundError(
            resource_type=resource_type,
            resource_id="unknown",
            details=response_data,
            message=message or None
        )
    elif status_code == 409:
        return DuplicateResourceError(
            resource_type="Resource",
            identifier="unknown",
            details=response_data,
            message=message or None
        )
    elif status_code == 422:
        return ValidationError(
            message=message or "Validation failed",
            details=response_data
        )
    elif 400 <= status_code < 500:
        return ValidationError(
            message=message or f"Client error: {status_code}",
            details=response_data
        )
    elif 500 <= status_code < 600:
        return APIError(
            message=message or f"Server error: {status_code}",
            status_code=status_code,
            response_data=response_data,
            endpoint=endpoint
        )
    else:
        return APIError(
            message=message or f"HTTP error: {status_code}",
            status_code=status_code,
            response_data=response_data,
            endpoint=endpoint
        )


def handle_httpx_error(error: httpx.RequestError, endpoint: str | None = None) -> ListmonkMCPError:
    """Convert httpx errors to appropriate MCP exceptions."""

    if isinstance(error, httpx.ConnectError):
        return ConfigurationError(
            message="Unable to connect to Listmonk server",
            details={"original_error": str(error), "endpoint": endpoint}
        )
    elif isinstance(error, httpx.TimeoutException):
        return OperationError(
            message="Request timed out",
            operation="request",
            details={"original_error": str(error), "endpoint": endpoint}
        )
    elif isinstance(error, httpx.HTTPStatusError):
        return map_http_status_to_exception(
            status_code=error.response.status_code,
            message=str(error),
            response_data=getattr(error.response, "json", lambda: {})(),
            endpoint=endpoint
        )
    else:
        return APIError(
            message=f"HTTP request failed: {str(error)}",
            endpoint=endpoint,
            response_data={"original_error": str(error)}
        )


def convert_listmonk_api_error(error: Exception) -> ListmonkMCPError:
    """Convert existing ListmonkAPIError to new exception hierarchy."""

    # Handle the existing ListmonkAPIError from client.py
    if hasattr(error, 'status_code') and hasattr(error, 'response'):
        return map_http_status_to_exception(
            status_code=error.status_code,
            message=str(error),
            response_data=error.response if hasattr(error, 'response') else None
        )

    # Handle general exceptions
    return APIError(
        message=str(error),
        response_data={"original_error": str(error)}
    )


# MCP tool runner

logger = logging.getLogger(__name__)


async def run_tool(logic: Callable[[], Awaitable[str]]) -> str:
    """Run a tool's logic and turn every failure into an MCP tool error.

    FastMCP reports a raised ToolError to the client as ``isError: true``.
    Tracebacks for unexpected errors go to the server log only.
    """
    tool = logic.__qualname__.split(".<locals>")[0]
    try:
        return await logic()
    except ListmonkMCPError as e:
        logger.warning("Tool %s failed: %s: %s", tool, type(e).__name__, e.message)
        raise ToolError(f"{type(e).__name__}: {e.message}") from e
    except ListmonkAPIError as e:
        mapped = convert_listmonk_api_error(e)
        logger.warning(
            "Tool %s failed: Listmonk status=%s %s: %s",
            tool, getattr(e, "status_code", None), type(mapped).__name__, mapped.message,
        )
        raise ToolError(f"{type(mapped).__name__}: {mapped.message}") from e
    except Exception as e:
        logger.exception("Tool %s raised an unexpected error", tool)
        raise ToolError(f"UnexpectedError: {e}") from e
