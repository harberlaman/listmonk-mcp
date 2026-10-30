"""mcp-interface: what a real MCP client sees, using an in-memory session against the server object."""

import json
import logging
import os
import subprocess
import sys
import tempfile
from contextlib import AbstractAsyncContextManager

import pytest
from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, ReadResourceResult
from pydantic import AnyUrl
from pytest_httpx import HTTPXMock

from listmonk_mcp import server

from .conftest import BASE_URL


def text(result: CallToolResult | ReadResourceResult) -> str:
    parts = result.content if isinstance(result, CallToolResult) else result.contents
    return "".join(getattr(p, "text", "") for p in parts)


@pytest.fixture
def listmonk_env(monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock) -> None:
    """Config for the lifespan, and a mocked response to its startup health check."""
    monkeypatch.setenv("LISTMONK_MCP_URL", BASE_URL)
    monkeypatch.setenv("LISTMONK_MCP_USERNAME", "api-user")
    monkeypatch.setenv("LISTMONK_MCP_PASSWORD", "api-token")
    monkeypatch.setenv("LISTMONK_MCP_MAX_RETRIES", "0")
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/health", json={"data": True})


def connect(allow_dangerous: bool = False) -> AbstractAsyncContextManager[ClientSession]:
    # Opened inside each test: anyio cancel scopes can't span fixture setup/teardown tasks.
    built = server.create_production_server(allow_dangerous=allow_dangerous)
    return create_connected_server_and_client_session(built._mcp_server)


async def test_running_server_lists_tools_resources_and_templates(listmonk_env: None) -> None:
    async with connect() as session:
        tools = (await session.list_tools()).tools
        resources = {str(r.uri) for r in (await session.list_resources()).resources}
        templates = {t.uriTemplate for t in (await session.list_resource_templates()).resourceTemplates}

        assert len(tools) == 59
        assert not {t.name for t in tools} & server.DANGEROUS_TOOLS
        assert resources == {
            "listmonk://subscribers", "listmonk://lists", "listmonk://campaigns",
            "listmonk://templates", "listmonk://media",
        }
        assert len(templates) == 8
        assert {"listmonk://subscriber/{subscriber_id}", "listmonk://list/{list_id}/subscribers"} <= templates


async def test_hidden_tool_call_is_unknown_and_sends_nothing(
    listmonk_env: None, httpx_mock: HTTPXMock
) -> None:
    async with connect() as session:
        result = await session.call_tool("reload_app", {})

        assert result.isError is True
        assert "Unknown tool: reload_app" in text(result)
        assert [r.url.path for r in httpx_mock.get_requests()] == ["/api/health"]


async def test_flag_on_lists_all_71_tools(listmonk_env: None) -> None:
    async with connect(allow_dangerous=True) as session:
        tools = {t.name for t in (await session.list_tools()).tools}

        assert len(tools) == 71
        assert server.DANGEROUS_TOOLS <= tools


def test_startup_log_reports_dangerous_tools_setting(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="listmonk_mcp.server")

    server.create_production_server(allow_dangerous=False)
    server.create_production_server(allow_dangerous=True)

    lines = [r.getMessage() for r in caplog.records if "Dangerous tools" in r.getMessage()]
    assert all(r.levelno == logging.INFO for r in caplog.records if "Dangerous tools" in r.getMessage())
    assert lines == [
        "Dangerous tools disabled (LISTMONK_MCP_ALLOW_DANGEROUS unset): 12 tools hidden",
        "Dangerous tools enabled (LISTMONK_MCP_ALLOW_DANGEROUS is set)",
    ]


async def test_resource_read_returns_lists(listmonk_env: None, httpx_mock: HTTPXMock) -> None:
    async with connect() as session:
        httpx_mock.add_response(
            method="GET",
            url=f"{BASE_URL}/api/lists",
            json={"data": {"results": [{"id": 1, "name": "Default", "type": "private", "optin": "single",
                                        "subscriber_count": 3}], "total": 1}},
        )

        result = await session.read_resource(AnyUrl("listmonk://lists"))

        assert "Default" in text(result)


async def test_listmonk_error_is_mcp_error_with_message(
    listmonk_env: None, httpx_mock: HTTPXMock
) -> None:
    async with connect() as session:
        httpx_mock.add_response(
            method="PUT",
            url=f"{BASE_URL}/api/campaigns/2/status",
            status_code=400,
            json={"message": "Only active campaigns can be paused."},
        )

        result = await session.call_tool("change_campaign_status", {"campaign_id": 2, "status": "paused"})

        assert result.isError is True
        assert "Only active campaigns can be paused." in text(result)


async def test_validation_error_is_mcp_error_without_request(
    listmonk_env: None, httpx_mock: HTTPXMock
) -> None:
    async with connect(allow_dangerous=True) as session:
        result = await session.call_tool("gc_unconfirmed_subscriptions", {"before_date": "2026-01-01"})

        assert result.isError is True
        assert "ValidationError" in text(result)
        assert [r.url.path for r in httpx_mock.get_requests()] == ["/api/health"]


async def test_unexpected_exception_has_no_traceback(
    listmonk_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with connect() as session:
        async def boom(*args: object, **kwargs: object) -> dict[str, object]:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(server.get_client(), "get_templates", boom)

        result = await session.call_tool("get_templates", {})

        assert result.isError is True
        assert "UnexpectedError: kaboom" in text(result)
        assert "Traceback" not in text(result)


def test_import_without_config_connects_to_nothing() -> None:
    # A clean interpreter with no LISTMONK_MCP_* settings: building the server must not need Listmonk.
    env = {k: v for k, v in os.environ.items() if not k.startswith("LISTMONK_MCP_")}
    code = "from listmonk_mcp.server import create_production_server; create_production_server()"

    done = subprocess.run([sys.executable, "-c", code], env=env, cwd=tempfile.gettempdir(),
                          capture_output=True, text=True, timeout=60)

    assert done.returncode == 0, done.stderr
    assert "Connecting to Listmonk" not in done.stderr


async def test_write_tool_returns_listmonk_json(listmonk_env: None, httpx_mock: HTTPXMock) -> None:
    created = {"data": {"id": 7, "name": "Training", "type": "private", "optin": "single"}}
    httpx_mock.add_response(method="POST", url=f"{BASE_URL}/api/lists", json=created)

    async with connect() as session:
        result = await session.call_tool("create_mailing_list", {"name": "Training"})

    assert result.isError is False
    assert json.loads(text(result)) == created


async def test_read_tool_returns_formatted_text(listmonk_env: None, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/templates",
        json={"data": [{"id": 5, "name": "TT-Tx-Shell", "type": "tx", "is_default": False}]},
    )

    async with connect() as session:
        result = await session.call_tool("get_templates", {})

    assert result.isError is False
    assert "TT-Tx-Shell" in text(result)
    try:
        json.loads(text(result))
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("read tool returned raw JSON")


async def test_secret_tool_arguments_never_reach_the_log(
    listmonk_env: None, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "s3cr3t-value"
    smtp = {"host": "smtp.invalid", "port": 587, "username": "relay", "password": secret}
    caplog.set_level(logging.DEBUG)
    httpx_mock.add_response(
        method="POST", url=f"{BASE_URL}/api/settings/smtp/test", status_code=400,
        json={"message": "dial tcp: lookup smtp.invalid: no such host"},
    )

    async with connect() as session:
        rejected = await session.call_tool("test_smtp_settings", {"settings": smtp})

        async def boom(*args: object, **kwargs: object) -> dict[str, object]:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(server.get_client(), "test_smtp_settings", boom)
        crashed = await session.call_tool("test_smtp_settings", {"settings": smtp})

    assert rejected.isError is True and crashed.isError is True
    assert any(r.exc_info for r in caplog.records), "the unexpected-error path should log a traceback"
    assert secret not in caplog.text
    assert all(secret not in r.getMessage() for r in caplog.records)
