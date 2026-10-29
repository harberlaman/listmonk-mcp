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


def subscriber(n: int, email: str) -> dict[str, object]:
    return {"id": n, "email": email, "name": f"Sub {n}", "status": "enabled",
            "lists": [{"id": 1, "name": "Default", "subscription_status": "confirmed"}],
            "attribs": {"dept": "IT"}}


async def test_list_subscribers_returns_records(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    subs = [subscriber(1, "a@example.com"), subscriber(2, "b@example.com"), subscriber(3, "c@example.com")]
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/subscribers?page=1&per_page=20&list_id=1",
        json={"data": {"results": subs, "total": 3, "page": 1, "per_page": 20}},
    )

    result = await server.get_list_subscribers_tool(1)

    for email in ("a@example.com", "b@example.com", "c@example.com"):
        assert email in result
    assert "Default (ID: 1, confirmed)" in result
    assert '"dept": "IT"' in result
    assert "page 1, 20 per page, 3 total" in result.lower()


async def test_list_subscribers_paging(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/subscribers?page=2&per_page=2&list_id=1",
        json={"data": {"results": [subscriber(3, "c@example.com")], "total": 3, "page": 2, "per_page": 2}},
    )

    result = await server.get_list_subscribers_tool(1, page=2, per_page=2)

    assert "c@example.com" in result and "a@example.com" not in result
    assert "page 2, 2 per page, 3 total" in result.lower()


async def test_list_subscribers_empty(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/subscribers?page=1&per_page=20&list_id=9",
        json={"data": {"results": [], "total": 0, "page": 1, "per_page": 20}},
    )

    assert "No subscribers." in await server.get_list_subscribers_tool(9)


async def test_list_subscribers_resource_uses_records(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/subscribers?page=1&per_page=50&list_id=1",
        json={"data": {"results": [subscriber(1, "a@example.com")], "total": 1, "page": 1, "per_page": 50}},
    )

    result = await server.get_list_subscribers_resource("1")

    assert "a@example.com" in result and "Default (ID: 1, confirmed)" in result
