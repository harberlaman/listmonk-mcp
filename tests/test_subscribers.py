"""subscriber-management: patch_subscriber sends only the given fields."""

import json

from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient

from .conftest import BASE_URL

PATCH_URL = f"{BASE_URL}/api/subscribers/3"


async def test_patch_only_status(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PATCH", url=PATCH_URL, json={"data": {"id": 3}})

    await server.patch_subscriber(3, status="disabled")

    request = httpx_mock.get_request(method="PATCH", url=PATCH_URL)
    assert request is not None
    assert json.loads(request.content) == {"status": "disabled"}


async def test_patch_lists_replaces_subscriptions(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(method="PATCH", url=PATCH_URL, json={"data": {"id": 3}})

    await server.patch_subscriber(3, lists=[1, 4])

    request = httpx_mock.get_request(method="PATCH", url=PATCH_URL)
    assert request is not None
    assert json.loads(request.content) == {"lists": [1, 4]}


async def test_patch_with_nothing_to_change_sends_nothing(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    result = await server.patch_subscriber(3)

    assert result.startswith("Error: ValidationError")
    assert httpx_mock.get_requests() == []
