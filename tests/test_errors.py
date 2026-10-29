"""mcp-interface: the error mapper keeps Listmonk's message and survives a missing status."""

import pytest

from listmonk_mcp.client import ListmonkAPIError
from listmonk_mcp.exceptions import (
    APIError,
    OperationError,
    ResourceNotFoundError,
    ValidationError,
    convert_listmonk_api_error,
)


def test_missing_status_does_not_crash() -> None:
    mapped = convert_listmonk_api_error(ListmonkAPIError("Request failed: connection refused"))

    assert isinstance(mapped, APIError)
    assert mapped.message == "Request failed: connection refused"


def test_missing_status_file_not_found() -> None:
    mapped = convert_listmonk_api_error(ListmonkAPIError("File not found: /tmp/x.png"))

    assert isinstance(mapped, OperationError)
    assert mapped.message == "File not found: /tmp/x.png"


@pytest.mark.parametrize(
    ("status", "kind"),
    [(400, ValidationError), (404, ResourceNotFoundError), (500, APIError)],
)
def test_listmonk_message_kept(status: int, kind: type) -> None:
    error = ListmonkAPIError("Only active campaigns can be paused.", status_code=status, response={"message": "x"})

    mapped = convert_listmonk_api_error(error)

    assert isinstance(mapped, kind)
    assert mapped.message == "Only active campaigns can be paused."
