"""transactional-email: the full /api/tx request, checked before anything is sent."""

import base64
import json
from typing import Any

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient
from listmonk_mcp.server import TxAttachment

from .conftest import BASE_URL

TX_URL = f"{BASE_URL}/api/tx"


def queued(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=TX_URL, json={"data": True})


def sent_json(httpx_mock: HTTPXMock) -> dict[str, Any]:
    request = httpx_mock.get_request(method="POST", url=TX_URL)
    assert request is not None
    body: dict[str, Any] = json.loads(request.content)
    return body


async def test_send_to_one_subscriber_id(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    queued(httpx_mock)

    result = await server.send_transactional_email(5, subscriber_id=3)

    assert sent_json(httpx_mock) == {"template_id": 5, "content_type": "html", "subscriber_ids": [3]}
    assert json.loads(result) == {"data": True}


@pytest.mark.parametrize(
    "selectors",
    [
        {"subscriber_email": "a@example.com", "subscriber_ids": [3]},
        {},
        {"subscriber_emails": []},
    ],
)
async def test_exactly_one_selector(
    server_client: ListmonkClient, httpx_mock: HTTPXMock, selectors: dict[str, Any]
) -> None:
    with pytest.raises(ToolError, match="^ValidationError: Give exactly one recipient selector"):
        await server.send_transactional_email(5, **selectors)

    assert httpx_mock.get_requests() == []


async def test_external_mode_with_email(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    queued(httpx_mock)

    await server.send_transactional_email(5, subscriber_email="someone@example.com", subscriber_mode="external")

    body = sent_json(httpx_mock)
    assert body["subscriber_mode"] == "external"
    assert body["subscriber_emails"] == ["someone@example.com"]


@pytest.mark.parametrize("mode", ["external", "fallback"])
async def test_ids_rejected_in_email_only_modes(
    server_client: ListmonkClient, httpx_mock: HTTPXMock, mode: str
) -> None:
    with pytest.raises(ToolError, match="^ValidationError: fallback and external modes take subscriber emails only"):
        await server.send_transactional_email(5, subscriber_id=3, subscriber_mode=mode)

    assert httpx_mock.get_requests() == []


async def test_unknown_mode_rejected(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    with pytest.raises(ToolError, match="^ValidationError: subscriber_mode must be one of"):
        await server.send_transactional_email(5, subscriber_id=3, subscriber_mode="broadcast")

    assert httpx_mock.get_requests() == []


async def test_headers_and_overrides_pass_through(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    queued(httpx_mock)

    await server.send_transactional_email(
        5,
        subscriber_id=3,
        subject="Message from IT",
        from_email="IT <it@example.com>",
        headers=[{"X-Training-ID": "TEST-01"}],
        data={"content": "<p>Hi</p>"},
    )

    body = sent_json(httpx_mock)
    assert body["subject"] == "Message from IT"
    assert body["from_email"] == "IT <it@example.com>"
    assert body["headers"] == [{"X-Training-ID": "TEST-01"}]
    assert body["data"] == {"content": "<p>Hi</p>"}


async def test_optional_fields_left_out(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    queued(httpx_mock)

    await server.send_transactional_email(5, subscriber_email="a@example.com")

    body = sent_json(httpx_mock)
    assert not {"subject", "from_email", "headers", "altbody", "messenger", "subscriber_mode", "data"} & body.keys()
    assert body["content_type"] == "html"


async def test_attachment_sends_multipart(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    queued(httpx_mock)
    pdf = b"%PDF-1.4 test"

    await server.send_transactional_email(
        5,
        subscriber_id=3,
        attachments=[TxAttachment(filename="guide.pdf", content_base64=base64.b64encode(pdf).decode())],
    )

    request = httpx_mock.get_request(method="POST", url=TX_URL)
    assert request is not None
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b'name="data"' in request.content
    assert b'"subscriber_ids": [3]' in request.content
    assert b'name="file"; filename="guide.pdf"' in request.content
    assert pdf in request.content
    assert b"Content-Type: application/pdf" in request.content


async def test_bad_attachment_base64_names_it(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    with pytest.raises(ToolError, match="^ValidationError: attachment guide.pdf: content_base64 is not valid base64"):
        await server.send_transactional_email(
            5, subscriber_id=3, attachments=[TxAttachment(filename="guide.pdf", content_base64="%%%")]
        )

    assert httpx_mock.get_requests() == []


def test_description_says_queued_and_points_to_logs() -> None:
    tool = server.mcp._tool_manager.get_tool("send_transactional_email")
    assert tool is not None
    assert "QUEUED" in tool.description and "get_logs" in tool.description
