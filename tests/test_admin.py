"""instance-administration: GC tools send Listmonk's required before_date."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient

from .conftest import BASE_URL


async def test_gc_campaign_analytics_sends_before_date(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/api/maintenance/analytics/views?before_date=2026-01-01T00%3A00%3A00Z",
        json={"data": True},
    )

    result = await server.gc_campaign_analytics("views", "2026-01-01T00:00:00Z")

    assert result.startswith("Successfully")


async def test_gc_unconfirmed_sends_before_date_and_reports_count(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/api/maintenance/subscriptions/unconfirmed?before_date=2026-01-01T00%3A00%3A00%2B00%3A00",
        json={"data": {"count": 7}},
    )

    result = await server.gc_unconfirmed_subscriptions("2026-01-01T00:00:00+00:00")

    assert "7 deleted" in result


async def test_gc_rejects_non_rfc3339_before_any_request(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    for bad in ("2026-01-01", "2026-01-01T00:00:00", "yesterday"):
        with pytest.raises(ToolError, match="^ValidationError: before_date"):
            await server.gc_campaign_analytics("all", bad)
        with pytest.raises(ToolError, match="^ValidationError: before_date"):
            await server.gc_unconfirmed_subscriptions(bad)

    assert httpx_mock.get_requests() == []


async def test_gc_subscribers_reports_count(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/api/maintenance/subscribers/orphan",
        json={"data": {"count": 3}},
    )

    assert "3 deleted" in await server.gc_subscribers("orphan")


def test_update_setting_docs_warn_about_reload() -> None:
    for name in ("update_setting", "update_settings"):
        tool = server.mcp._tool_manager.get_tool(name)
        assert tool is not None
        assert "reloads itself" in tool.description


async def test_update_setting_sends_raw_value_not_wrapped(
    client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    url = f"{BASE_URL}/api/settings/app.from_email"
    httpx_mock.add_response(method="PUT", url=url, json={"data": True})

    await client.update_setting("app.from_email", "IT <it@example.com>")

    request = httpx_mock.get_request(method="PUT", url=url)
    assert request is not None
    assert json.loads(request.content) == "IT <it@example.com>"


async def test_about_reads_unwrapped_response(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET", url=f"{BASE_URL}/api/about", json={"version": "v6.2.0", "build": "v6.2.0 (ef0a7587)"}
    )

    assert "v6.2.0" in await server.get_about_info()
