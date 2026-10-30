"""instance-administration: GC tools send Listmonk's required before_date."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient
from listmonk_mcp.config import Config

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

    assert json.loads(result) == {"data": True}


async def test_gc_unconfirmed_sends_before_date_and_returns_response(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/api/maintenance/subscriptions/unconfirmed?before_date=2026-01-01T00%3A00%3A00%2B00%3A00",
        json={"data": {"count": 7}},
    )

    result = await server.gc_unconfirmed_subscriptions("2026-01-01T00:00:00+00:00")

    assert json.loads(result) == {"data": {"count": 7}}


async def test_gc_rejects_non_rfc3339_before_any_request(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    for bad in ("2026-01-01", "2026-01-01T00:00:00", "yesterday"):
        with pytest.raises(ToolError, match="^ValidationError: before_date"):
            await server.gc_campaign_analytics("all", bad)
        with pytest.raises(ToolError, match="^ValidationError: before_date"):
            await server.gc_unconfirmed_subscriptions(bad)

    assert httpx_mock.get_requests() == []


async def test_gc_subscribers_returns_response(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{BASE_URL}/api/maintenance/subscribers/orphan",
        json={"data": {"count": 3}},
    )

    assert json.loads(await server.gc_subscribers("orphan")) == {"data": {"count": 3}}


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


async def test_health_reports_version_and_build(
    server_client: ListmonkClient, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch, config: Config
) -> None:
    monkeypatch.setattr(server, "_config", config)
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/health", json={"data": True})
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/about",
                            json={"version": "v6.2.0", "build": "v6.2.0 (ef0a7587)"})

    result = await server.check_listmonk_health()

    assert "healthy" in result
    assert "Version: v6.2.0" in result and "Build: v6.2.0 (ef0a7587)" in result


async def test_health_still_healthy_when_about_fails(
    server_client: ListmonkClient, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch, config: Config
) -> None:
    monkeypatch.setattr(server, "_config", config)
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/health", json={"data": True})
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/about", status_code=403,
                            json={"message": "permission denied"})

    result = await server.check_listmonk_health()

    assert "healthy" in result
    assert "Version unavailable: permission denied" in result


async def test_get_settings_masks_clear_text_smtp_password(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/settings",
        json={"data": {"smtp": [{"host": "smtp.example.com", "port": 587, "username": "relay-user",
                                 "password": "hunter2-real"}]}},
    )

    result = await server.get_settings()

    assert "hunter2-real" not in result
    assert "********" in result
    assert "smtp.example.com" in result and "relay-user" in result


def log_lines(count: int) -> list[str]:
    return [f"2026/10/28 09:00:00 manager.go:{n}: line {n}" for n in range(1, count + 1)]


async def test_get_logs_returns_last_100_in_order(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/logs", json={"data": log_lines(4873)})

    result = (await server.get_logs()).splitlines()

    assert result[0] == "Logs: last 100 of 4873 lines"
    assert result[1:] == log_lines(4873)[-100:]


async def test_get_logs_with_fewer_lines_than_requested(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/logs", json={"data": log_lines(30)})

    result = (await server.get_logs(lines=100)).splitlines()

    assert result[0] == "Logs: last 30 of 30 lines"
    assert result[1:] == log_lines(30)


@pytest.mark.parametrize("lines", [0, 5001])
async def test_get_logs_rejects_out_of_range(server_client: ListmonkClient, lines: int) -> None:
    # pytest-httpx fails the test if any request is sent.
    with pytest.raises(ToolError, match="^ValidationError: lines must be between 1 and 5000"):
        await server.get_logs(lines=lines)


async def test_get_logs_with_non_list_data(server_client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/logs", json={"data": None})

    assert await server.get_logs() == "Logs: last 0 of 0 lines"
