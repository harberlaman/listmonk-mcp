"""subscriber-management: patch_subscriber sends only the given fields; activity rendering."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError
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
    with pytest.raises(ToolError, match="^ValidationError: patch_subscriber needs at least one field"):
        await server.patch_subscriber(3)

    assert httpx_mock.get_requests() == []


async def test_activity_lists_views_and_clicks(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/subscribers/3/activity",
        json={"data": {
            "campaign_views": [{"id": 9, "name": "Training 1", "view_count": 2, "last_viewed_at": "2026-10-20T10:00:00Z"}],
            "link_clicks": [{"url": "https://example.com/t1", "campaign_id": 9, "campaign_name": "Training 1",
                             "click_count": 1, "last_clicked_at": "2026-10-20T10:01:00Z"}],
        }},
    )

    result = await server.get_subscriber_activity(3)

    assert "Training 1 (ID: 9): 2 view(s)" in result
    assert "https://example.com/t1 in Training 1 (ID: 9): 1 click(s)" in result


async def test_activity_empty(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/subscribers/3/activity",
        json={"data": {"campaign_views": [], "link_clicks": []}},
    )

    assert await server.get_subscriber_activity(3) == "No activity recorded for subscriber 3"
