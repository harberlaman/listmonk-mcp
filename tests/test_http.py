"""The shared HTTP client sends the right Content-Type per request (no client-wide default)."""

from pathlib import Path

from pytest_httpx import HTTPXMock

from listmonk_mcp.client import ListmonkClient

from .conftest import BASE_URL


async def test_json_request(client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=f"{BASE_URL}/api/settings/app.site_name", json={"data": True})

    await client.update_setting("app.site_name", "Site")

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Content-Type"] == "application/json"


async def test_form_request(client: ListmonkClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=f"{BASE_URL}/api/templates/preview", html="<p>x</p>")

    await client.preview_template_body('{{ template "content" . }}')

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"


async def test_multipart_request(client: ListmonkClient, httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    csv = tmp_path / "subs.csv"
    csv.write_text("email,name\na@example.com,A\n")
    httpx_mock.add_response(method="POST", url=f"{BASE_URL}/api/import/subscribers", json={"data": {"status": "importing"}})

    await client.import_subscribers(str(csv), list_ids=[1])

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="params"' in request.content and b'filename="subs.csv"' in request.content
    # Sent through the shared, authenticated client rather than a one-off client.
    assert request.headers["Authorization"] == "token api-user:api-token"
