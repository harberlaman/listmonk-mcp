# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MCP server (Python 3.11+, FastMCP) that exposes a Listmonk instance's REST API as MCP tools and resources. Packaged with hatchling, published to PyPI as `listmonk-mcp`. This repo is a fork of `rhnvrm/listmonk-mcp`.

## Commands

Uses `uv`. A Nix flake (`flake.nix`) plus `.envrc` (direnv) provide a dev shell that loads `.env` and activates `.venv`.

```bash
uv sync --extra dev                         # install with dev deps
uv run ruff check src/                      # lint (CI gate)
uv run ruff check src/ --fix
uv run mypy src/                            # strict type check (CI gate)
uv build                                    # build wheel/sdist (CI gate)
uv run listmonk-mcp --help                  # CLI: --config/-c <.env path>, --debug/-d, --version/-v
uv run python -m listmonk_mcp.server        # run server (stdio transport)
```

```bash
uv run pytest                                                            # all tests
uv run pytest tests/test_templates.py::test_explicit_subject_replaces_stored_subject
```

Tests mock Listmonk with pytest-httpx; nothing talks to a real server. `tests/conftest.py` provides `client` (a `ListmonkClient` with an open session, skipping `connect()`'s health check) and `server_client` (the same client installed as `server._client`, so `@mcp.tool` functions can be awaited directly). pytest-httpx fails a test on any request that has no matching mocked response, which is how "no request sent" is asserted.

CI (`.github/workflows/publish.yml`) only runs on `v*` tags: ruff → mypy → build → PyPI trusted publish → GitHub release. Lint/type checks do not run on push or PR. Release = bump `version` in `pyproject.toml`, commit, tag `vX.Y.Z`, push tag. `docs.yml` builds the mkdocs site from `docs/` on pushes/PRs to `master` that touch the docs.

Local Listmonk for manual testing: `docker compose -f docs/listmonk-docker-compose.yml up -d` (http://localhost:9000, admin/listmonk), then create an API user + token in Admin → Users.

## Configuration

`config.py` — pydantic-settings `Config` with env prefix `LISTMONK_MCP_` and automatic `.env` loading. Required: `URL`, `USERNAME`, `PASSWORD`. `PASSWORD` is the Listmonk **API token**, not the login password; the client sends `Authorization: token <username>:<token>`. Optional: `TIMEOUT`, `MAX_RETRIES`, `DEBUG`, `LOG_LEVEL`, `SERVER_NAME`.

## Architecture

Layers, in call order:

1. **`server.py`** (~2.4k lines, 70 tools and 13 resources, almost all of the surface area)
   - A module-level `mcp = FastMCP(...)` is used only as a registration target for `@mcp.tool()` / `@mcp.resource()` decorators.
   - `create_production_server()` builds a second `FastMCP` with the `lifespan` context manager and copies tools over by reaching into the private `mcp._tool_manager._tools`. **Only tools are copied — resources registered on `mcp` are not transferred to the production server.** Keep this in mind when adding resources or upgrading the `mcp` package (private API).
   - `lifespan` loads config, creates/connects the global `_client`, and closes it on shutdown. Tools access it via `get_client()` / `get_config()` module globals.
   - The typer `cli_app` (`main()` entry point) calls `create_production_server().run()`.

2. **`client.py`** — `ListmonkClient`, async httpx wrapper with one method per Listmonk endpoint. `connect()` performs a health check, so the server fails at startup if Listmonk is unreachable or credentials are wrong. `_request()` retries only on `httpx.RequestError` (network errors) with exponential backoff; non-2xx responses raise `ListmonkAPIError` immediately. `json_data` is typed `Any` because some endpoints (e.g. `PUT /api/settings/{key}`) take a raw JSON value, not an object; pass `form_data` instead for endpoints that read form fields (e.g. `POST /api/templates/preview`). Non-JSON responses (HTML previews) come back as `{"text": ...}`.

3. **`exceptions.py`** — `ListmonkMCPError` hierarchy plus HTTP status mapping. Imports `ListmonkAPIError` from `client.py` (dependency goes exceptions → client).

4. **`models.py`** — Pydantic models/enums. Re-exported from `__init__.py` but **not used by `server.py` or `client.py`**; tools take primitive args and the client returns raw `dict[str, Any]`.

### Conventions for tools and resources

- Tool pattern: an `@mcp.tool()` async function with typed args and a docstring (FastMCP derives the tool schema from these), defining an inner `async def _x_logic() -> str`, then `return await safe_execute_async(_x_logic)  # type: ignore[no-any-return]`. `safe_execute_async` turns exceptions into an error **string** rather than raising.
- Resources use `listmonk://...` URIs, take path params as `str` (cast to `int` themselves), catch `ListmonkAPIError` directly, and return Markdown-formatted strings.
- Every tool/resource returns a human-readable `str`, not JSON.
- Adding an endpoint: add a method to `ListmonkClient`, then a tool/resource in `server.py` following the pattern above. mypy runs in `strict` mode, so everything needs full type annotations.
- Verify request shapes against the Listmonk handlers for the target version (`knadh/listmonk`, `cmd/*.go` at the release tag), not only the docs: several endpoints read form fields or query params rather than JSON, some ignore body fields entirely, and `PUT /api/settings` / `PUT /api/settings/{key}` reload Listmonk unless a campaign is running.
- Input validation that must happen before any request (e.g. RFC3339 dates) returns an `"Error: ValidationError - ..."` string from the tool logic rather than raising, because `ListmonkAPIError` without a `status_code` currently crashes the error mapper.
