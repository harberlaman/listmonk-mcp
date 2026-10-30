"""Config: the LISTMONK_MCP_ALLOW_DANGEROUS flag."""

import pydantic
import pytest

from listmonk_mcp.config import Config

from .conftest import BASE_URL


@pytest.fixture(autouse=True)
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LISTMONK_MCP_URL", BASE_URL)
    monkeypatch.setenv("LISTMONK_MCP_USERNAME", "api-user")
    monkeypatch.setenv("LISTMONK_MCP_PASSWORD", "api-token")
    monkeypatch.delenv("LISTMONK_MCP_ALLOW_DANGEROUS", raising=False)


def test_allow_dangerous_defaults_to_false() -> None:
    assert Config(_env_file=None).allow_dangerous is False  # type: ignore[call-arg]


@pytest.mark.parametrize("value", ["true", "1", "yes"])
def test_allow_dangerous_true_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LISTMONK_MCP_ALLOW_DANGEROUS", value)
    assert Config(_env_file=None).allow_dangerous is True  # type: ignore[call-arg]


def test_allow_dangerous_rejects_non_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LISTMONK_MCP_ALLOW_DANGEROUS", "maybe")
    with pytest.raises(pydantic.ValidationError):
        Config(_env_file=None)  # type: ignore[call-arg]
