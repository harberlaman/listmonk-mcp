"""bounce-management: deleting bounces, and blocklisting bounced subscribers (always all)."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient

from .conftest import BASE_URL


async def test_blocklist_bounced_sends_no_body(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(method="PUT", url=f"{BASE_URL}/api/bounces/blocklist", json={"data": True})

    result = await server.blocklist_bounced_subscribers()

    request = httpx_mock.get_request(method="PUT", url=f"{BASE_URL}/api/bounces/blocklist")
    assert request is not None
    assert request.content == b""
    assert json.loads(result) == {"data": True}


def test_blocklist_bounced_has_no_params_and_warns() -> None:
    tool = server.mcp._tool_manager.get_tool("blocklist_bounced_subscribers")
    assert tool is not None
    assert tool.parameters.get("properties", {}) == {}
    assert "ALL bounced subscribers" in tool.description


async def test_delete_bounces_with_ids(client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="DELETE", url=f"{BASE_URL}/api/bounces?id=11&id=12", json={"data": True})

    await client.delete_bounces([11, 12])

    request = httpx_mock.get_request(method="DELETE")
    assert request is not None
    assert "all" not in request.url.params


async def test_delete_bounces_without_ids_is_rejected(server_client: ListmonkClient) -> None:
    # pytest-httpx fails the test if any request is sent.
    with pytest.raises(ToolError, match="^ValidationError: At least one bounce ID is required"):
        await server.delete_bounces([])


async def test_delete_all_bounces_sends_all_flag(
    server_client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(method="DELETE", url=f"{BASE_URL}/api/bounces?all=true", json={"data": True})

    result = await server.delete_all_bounces()

    assert json.loads(result) == {"data": True}


def test_delete_bounces_description_says_never_all() -> None:
    tool = server.mcp._tool_manager.get_tool("delete_bounces")
    assert tool is not None
    assert "At least one ID is required" in tool.description
    assert "never deletes all bounces" in tool.description


def test_delete_all_bounces_description_warns() -> None:
    tool = server.mcp._tool_manager.get_tool("delete_all_bounces")
    assert tool is not None
    assert tool.parameters.get("properties", {}) == {}
    assert "ALL bounce records" in tool.description
