"""campaign-management: analytics needs Listmonk's required date range."""

import json

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


async def test_test_campaign_sends_saved_campaign_and_recipients(
    client: ListmonkClient, httpx_mock: HTTPXMock
) -> None:
    campaign = {
        "id": 9,
        "name": "Training 1",
        "subject": "Phishing basics",
        "lists": [{"id": 1, "name": "Default"}],
        "from_email": "IT <it@example.com>",
        "body": "<p>hi</p>",
        "altbody": None,
        "content_type": "richtext",
        "messenger": "email",
        "type": "regular",
        "tags": ["training"],
        "template_id": 2,
        "headers": [{"X-Training-ID": "T1"}],
    }
    httpx_mock.add_response(method="GET", url=f"{BASE_URL}/api/campaigns/9", json={"data": campaign})
    httpx_mock.add_response(method="POST", url=f"{BASE_URL}/api/campaigns/9/test", json={"data": True})

    await client.test_campaign(9, ["test@example.com"])

    request = httpx_mock.get_request(method="POST", url=f"{BASE_URL}/api/campaigns/9/test")
    assert request is not None
    body = json.loads(request.content)
    assert body["subscribers"] == ["test@example.com"]
    assert body["lists"] == [1]
    assert body["altbody"] == ""
    for field in ("name", "subject", "from_email", "body", "content_type", "messenger",
                  "type", "tags", "template_id", "headers"):
        assert body[field] == campaign[field], field
