"""Shared fixtures: a ListmonkClient wired to pytest-httpx instead of a live server."""

from collections.abc import AsyncIterator

import httpx
import pytest

from listmonk_mcp.client import ListmonkClient
from listmonk_mcp.config import Config

BASE_URL = "http://listmonk.test"


@pytest.fixture
def config() -> Config:
    return Config(url=BASE_URL, username="api-user", password="api-token", max_retries=0)


@pytest.fixture
async def client(config: Config) -> AsyncIterator[ListmonkClient]:
    """A client with an open HTTP session, skipping connect()'s live health check."""
    listmonk = ListmonkClient(config)
    # Same default headers as connect() (no Content-Type), so per-request encoding is exercised.
    listmonk._client = httpx.AsyncClient(
        timeout=config.timeout,
        headers={"Accept": "application/json", "Authorization": f"token {config.username}:{config.password}"},
    )
    yield listmonk
    await listmonk.close()


@pytest.fixture
def server_client(client: ListmonkClient, monkeypatch: pytest.MonkeyPatch) -> ListmonkClient:
    """Install the mocked client as the server's global so MCP tool functions use it."""
    from listmonk_mcp import server

    monkeypatch.setattr(server, "_client", client)
    return client
