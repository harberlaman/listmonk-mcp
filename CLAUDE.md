# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MCP server (Python 3.11+, FastMCP) that exposes a Listmonk instance's REST API as MCP tools and resources. Packaged with hatchling as `listmonk-mcp`. This repo is a separate fork of `rhnvrm/listmonk-mcp`: it is not published to PyPI (upstream owns that name) and is not sent back upstream.

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

CI (`.github/workflows/publish.yml`) only runs on `v*` tags: ruff → mypy → build → GitHub release. Lint/type checks do not run on push or PR. Versions are the upstream base plus a PEP 440 local suffix (`0.2.0+hl.1`, then `+hl.2`, ...), so they never collide with an upstream release. Release = bump `version` in `pyproject.toml` and `__version__`, run `uv lock`, update the CHANGELOG heading, commit, tag `v<version>` (e.g. `v0.2.0+hl.1`), push the tag. `docs.yml` builds the mkdocs site from `docs/` on pushes/PRs to `master` that touch the docs.

Local Listmonk for manual testing: `docker compose -f docs/listmonk-docker-compose.yml up -d` (http://localhost:9000, admin/listmonk), then create an API user + token in Admin → Users.

## Configuration

`config.py` — pydantic-settings `Config` with env prefix `LISTMONK_MCP_` and automatic `.env` loading. Required: `URL`, `USERNAME`, `PASSWORD`. `PASSWORD` is the Listmonk **API token**, not the login password; the client sends `Authorization: token <username>:<token>`. Optional: `TIMEOUT`, `MAX_RETRIES`, `DEBUG`, `LOG_LEVEL`, `SERVER_NAME`, `ALLOW_DANGEROUS` (default `false`; exposes the 12 tools in `DANGEROUS_TOOLS`).

## Architecture

Layers, in call order:

1. **`server.py`** (~2.5k lines, 71 tools (59 exposed by default), 5 resources and 8 resource templates, almost all of the surface area)
   - A single module-level `mcp = GuardedFastMCP("Listmonk MCP Server", lifespan=lifespan)`; `@mcp.tool()` / `@mcp.resource()` register directly on the server that runs. `GuardedFastMCP` hides the names in `hidden_tools` from `list_tools` and answers `call_tool` for them with `Unknown tool`; the tools stay registered, so tests can still read them from `mcp._tool_manager`. `create_production_server(allow_dangerous=False)` sets `hidden_tools` to `DANGEROUS_TOOLS` (or nothing), checks every name is registered, logs one INFO line and returns `mcp`. The lifespan only runs when the server starts, so importing the module connects to nothing.
   - `lifespan` reuses the config `run()` loaded (or loads it), creates/connects the global `_client`, and closes it on shutdown. Tools access it via `get_client()` / `get_config()` module globals.
   - The typer `cli_app` (`main()` entry point) loads config, then calls `create_production_server(allow_dangerous=config.allow_dangerous).run()`.

2. **`client.py`**: `ListmonkClient`, an async httpx wrapper with one method per Listmonk endpoint. `connect()` performs a health check, so the server fails at startup if Listmonk is unreachable or credentials are wrong. `_request()` retries only on `httpx.RequestError` (network errors) with exponential backoff; non-2xx responses raise `ListmonkAPIError` immediately. The shared client sets **no default `Content-Type`**: `_request` sends `json_data` as JSON (typed `Any`, because e.g. `PUT /api/settings/{key}` takes a raw value), `form_data` form-encoded, and `form_data` + `files` as multipart. All uploads go through it; don't create one-off `AsyncClient`s. Non-JSON responses (HTML previews) come back as `{"text": ...}`.

3. **`exceptions.py`**: `ListmonkMCPError` hierarchy, the HTTP status mapper (handles `status_code=None` and keeps Listmonk's message), and `run_tool`. Imports `ListmonkAPIError` from `client.py` (dependency goes exceptions → client).

4. **`uploads.py`**: `resolve_upload` (exactly one of `content_base64` + `filename` or `file_path`; strict base64; extension allow-list; size cap) and `decode_base64`. Media allows png/jpg/jpeg/gif/webp up to 5 MB (no SVG); imports allow csv/zip up to 10 MB.

5. **`masking.py`**: `mask_settings`, used by `get_settings`: replaces non-empty values whose key contains `password`/`secret`, plus `bounce.sendgrid_key` and the `key` of `bounce.forwardemail`/`bounce.lettermint`, with `********`. Empty values stay empty.

6. **`models.py`**: Pydantic models/enums. Re-exported from `__init__.py` but **not used by `server.py` or `client.py`**; tools take primitive args (plus `TxAttachment` in `server.py`) and the client returns raw `dict[str, Any]`.

### Conventions for tools and resources

- Tool pattern: an `@mcp.tool()` async function with typed args and a docstring (FastMCP derives the tool schema from these), defining an inner `async def _x_logic() -> str`, then `return await run_tool(_x_logic)`.
- **Errors:** never return an error string from a tool. Raise `ValidationError` (from `exceptions.py`) for input that must be rejected before any request; let `ListmonkAPIError` propagate. `run_tool` logs and re-raises everything as `ToolError("<Type>: <message>")`, which clients see as `isError: true`; tracebacks stay in the server log.
- **Return values:** tools that change state (non-GET, except `preview_template_body`) return `listmonk_json(<Listmonk response>)`, never a made-up "Successfully ..." message. Read tools return formatted text. List-subscriber output goes through `format_subscribers`.
- Resources use `listmonk://...` URIs, take path params as `str` (cast to `int` themselves), catch `ListmonkAPIError` directly, and return Markdown-formatted strings (including their error text).
- Adding an endpoint: add a method to `ListmonkClient`, then a tool/resource in `server.py` following the pattern above, and update `tests/test_registration.py` (it pins the exposed tool counts, 59 by default and 71 with the flag; list tools with `await server.list_tools()`, not `_tool_manager`). Decide whether the new tool belongs in `DANGEROUS_TOOLS`: it does if it acts on every record or on records chosen by a query, or reloads Listmonk. mypy runs in `strict` mode, so everything needs full type annotations.
- Verify request and response shapes against the Listmonk handlers for the target version (`knadh/listmonk`, `cmd/*.go` and `models/*.go` at the release tag), not only the docs. Several endpoints read form fields or query params rather than JSON, some ignore body fields entirely, `/api/about` is returned without a `data` wrapper, v6.2.0 has no media update route, and `PUT /api/settings` / `PUT /api/settings/{key}` reload Listmonk unless a campaign is running.
- Media URLs returned by Listmonk are built from its `root_url` setting.
