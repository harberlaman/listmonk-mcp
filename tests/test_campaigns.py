"""campaign-management: analytics needs Listmonk's required date range."""

from pytest_httpx import HTTPXMock

from listmonk_mcp import server
from listmonk_mcp.client import ListmonkClient

from .conftest import BASE_URL


async def test_campaign_analytics_sends_ids_and_required_dates(
    client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/api/campaigns/analytics/clicks?id=4&from=2026-10-01&to=2026-10-28",
        json={"data": [{"campaign_id": 4, "count": 12}]},
    )

    result = await client.get_campaign_analytics("clicks", [4], "2026-10-01", "2026-10-28")

    assert result["data"][0]["count"] == 12


def test_campaign_analytics_dates_are_required_in_tool_schema() -> None:
    tool = server.mcp._tool_manager.get_tool("get_campaign_analytics")
    assert tool is not None
    assert {"from_date", "to_date"} <= set(tool.parameters["required"])
