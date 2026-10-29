"""media-management and the shared upload checks: every rejection happens before any request."""

import base64
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient
from listmonk_mcp.exceptions import ValidationError
from listmonk_mcp.uploads import (
    IMPORT_EXTENSIONS,
    IMPORT_MAX_BYTES,
    MEDIA_EXTENSIONS,
    MEDIA_MAX_BYTES,
    Upload,
    resolve_upload,
)

from .conftest import BASE_URL

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16).decode()


def media(content_base64: str | None = None, filename: str | None = None, file_path: str | None = None) -> Upload:
    return resolve_upload(content_base64=content_base64, filename=filename, file_path=file_path,
                          allowed_extensions=MEDIA_EXTENSIONS, max_bytes=MEDIA_MAX_BYTES)


def test_base64_png_accepted() -> None:
    upload = media(content_base64=PNG, filename="logo.png")

    assert upload.filename == "logo.png"
    assert upload.content.startswith(b"\x89PNG")
    assert upload.content_type == "image/png"


def test_filename_path_parts_are_dropped() -> None:
    assert media(content_base64=PNG, filename="../../etc/logo.png").filename == "logo.png"


@pytest.mark.parametrize(
    ("kw", "match"),
    [
        ({}, "exactly one"),
        ({"content_base64": PNG, "filename": "a.png", "file_path": "/tmp/a.png"}, "exactly one"),
        ({"content_base64": PNG}, "filename is required"),
        ({"content_base64": PNG, "filename": "script.svg"}, "not allowed"),
        ({"content_base64": PNG, "filename": "notes.txt"}, "not allowed"),
        ({"content_base64": "not base64!!", "filename": "a.png"}, "not valid base64"),
        ({"file_path": "/nonexistent/logo.png"}, "File not found"),
    ],
)
def test_rejections(kw: dict[str, str], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        media(**kw)


def test_too_large_base64() -> None:
    big = base64.b64encode(b"\x00" * (MEDIA_MAX_BYTES + 1)).decode()

    with pytest.raises(ValidationError, match="5 MB limit"):
        media(content_base64=big, filename="big.png")


def test_too_large_file_is_rejected_before_reading(tmp_path: Path) -> None:
    path = tmp_path / "big.csv"
    with path.open("wb") as f:
        f.truncate(IMPORT_MAX_BYTES + 1)

    with pytest.raises(ValidationError, match="10 MB limit"):
        resolve_upload(content_base64=None, filename=None, file_path=str(path),
                       allowed_extensions=IMPORT_EXTENSIONS, max_bytes=IMPORT_MAX_BYTES)


def test_local_csv_for_import(tmp_path: Path) -> None:
    path = tmp_path / "subs.csv"
    path.write_text("email,name\n")

    upload = resolve_upload(content_base64=None, filename=None, file_path=str(path),
                            allowed_extensions=IMPORT_EXTENSIONS, max_bytes=IMPORT_MAX_BYTES)

    assert (upload.filename, upload.content_type) == ("subs.csv", "text/csv")


async def test_upload_media_tool_posts_file_and_returns_url(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    media_record = {"data": {"id": 4, "filename": "logo.png", "url": "http://listmonk.test/uploads/logo.png"}}
    httpx_mock.add_response(method="POST", url=f"{BASE_URL}/api/media", json=media_record)

    result = await server.upload_media(PNG, "logo.png")

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b'name="file"; filename="logo.png"' in request.content
    assert json.loads(result) == media_record


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: server.upload_media(PNG, "script.svg"), "not allowed"),
        (lambda: server.upload_media("%%%", "logo.png"), "not valid base64"),
        (lambda: server.upload_media_file("/nonexistent/logo.png"), "File not found"),
    ],
)
async def test_upload_tools_reject_without_request(
    server_client: ListmonkClient, httpx_mock: HTTPXMock, call: Callable[[], Awaitable[str]], match: str
) -> None:
    with pytest.raises(ToolError, match=f"^ValidationError: .*{match}"):
        await call()

    assert httpx_mock.get_requests() == []


def test_no_rename_tool_and_no_title_parameter() -> None:
    tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}

    assert "rename_media" not in tools
    for name in ("upload_media", "upload_media_file"):
        assert "title" not in tools[name].parameters.get("properties", {})
