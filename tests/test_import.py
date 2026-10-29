"""subscriber-import: import from uploaded content or a local path, with clean errors."""

import base64
import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient

from .conftest import BASE_URL

CSV = base64.b64encode(b"email,name\nimp1@example.com,Imp One\n").decode()


async def test_import_uploaded_csv(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    status = {"data": {"status": "importing", "total": 0}}
    httpx_mock.add_response(method="POST", url=f"{BASE_URL}/api/import/subscribers", json=status)

    result = await server.import_subscribers([1], content_base64=CSV, filename="subs.csv")

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b'name="file"; filename="subs.csv"' in request.content
    assert b"imp1@example.com" in request.content
    assert b'"lists": [1]' in request.content
    assert json.loads(result) == status


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({}, "exactly one"),
        ({"content_base64": CSV, "filename": "subs.csv", "file_path": "/tmp/subs.csv"}, "exactly one"),
        ({"file_path": "/nonexistent/subs.csv"}, "File not found"),
        ({"content_base64": CSV, "filename": "subs.xlsx"}, "not allowed"),
    ],
)
async def test_import_rejects_without_request(
    server_client: ListmonkClient, httpx_mock: HTTPXMock, kwargs: dict[str, str], match: str
) -> None:
    with pytest.raises(ToolError, match=f"^ValidationError: .*{match}"):
        await server.import_subscribers([1], **kwargs)

    assert httpx_mock.get_requests() == []
