"""template-management: subject carry-forward (upstream PR #11) and body preview."""

import json
from typing import Any
from urllib.parse import parse_qs

from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient

from .conftest import BASE_URL

TEMPLATE_URL = f"{BASE_URL}/api/templates/5"


def stored_template(**overrides: Any) -> dict[str, Any]:
    template = {
        "id": 5,
        "name": "TT-Tx-Shell",
        "type": "tx",
        "subject": "Message from IT",
        "body": "<p>old</p>",
        "is_default": False,
    }
    template.update(overrides)
    return {"data": template}


def put_body(httpx_mock: HTTPXMock) -> dict[str, Any]:
    request = httpx_mock.get_request(method="PUT", url=TEMPLATE_URL)
    assert request is not None
    body: dict[str, Any] = json.loads(request.content)
    return body


async def test_tx_update_without_subject_carries_stored_subject(
    client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(method="GET", url=TEMPLATE_URL, json=stored_template())
    httpx_mock.add_response(method="PUT", url=TEMPLATE_URL, json={"data": {}})

    await client.update_template(5, body="<p>new</p>")

    body = put_body(httpx_mock)
    assert body["subject"] == "Message from IT"
    assert body["body"] == "<p>new</p>"
    assert body["type"] == "tx"


async def test_explicit_subject_replaces_stored_subject(
    client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(method="GET", url=TEMPLATE_URL, json=stored_template())
    httpx_mock.add_response(method="PUT", url=TEMPLATE_URL, json={"data": {}})

    await client.update_template(5, subject="New subject")

    assert put_body(httpx_mock)["subject"] == "New subject"


async def test_template_without_stored_subject_sends_no_subject(
    client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET", url=TEMPLATE_URL, json=stored_template(type="campaign", subject="")
    )
    httpx_mock.add_response(method="PUT", url=TEMPLATE_URL, json={"data": {}})

    await client.update_template(5, body="<p>new</p>")

    assert "subject" not in put_body(httpx_mock)


async def test_preview_template_body_posts_form_and_returns_html(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/api/templates/preview",
        html="<html><p>rendered</p></html>",
    )

    result = await server.preview_template_body('<p>{{ template "content" . }}</p>', "campaign")

    request = httpx_mock.get_request(method="POST", url=f"{BASE_URL}/api/templates/preview")
    assert request is not None
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.content.decode()) == {
        "body": ['<p>{{ template "content" . }}</p>'],
        "template_type": ["campaign"],
    }
    assert "<p>rendered</p>" in result
