# Tasks

## 1. Flag and exposure gate (mcp-interface)

- [x] 1.1 Add `allow_dangerous: bool = False` to `Config` (design.md D3). Add tests in `tests/test_config.py`: unset is `False`; `true`/`1`/`yes` is `True`; `maybe` raises a validation error. Verify: `uv run pytest tests/test_config.py` passes.
- [x] 1.2 Add `GuardedFastMCP` with `hidden_tools`, overriding `list_tools` and `call_tool` (D1), and make `mcp` an instance of it. Add `DANGEROUS_TOOLS` with the 12 names, check them against the registry, and give `create_production_server(allow_dangerous=False)` the job of setting `hidden_tools` and writing the one INFO startup line (D2). Verify: `uv run mypy src/` and `uv run ruff check src/` are clean.
- [x] 1.3 Read config in `run()` before building the server, and pass `allow_dangerous`. Make `lifespan` reuse an already-loaded `_config` (D3). Add `LISTMONK_MCP_ALLOW_DANGEROUS` to `run()`'s help text. Verify: `uv run listmonk-mcp --help` lists the variable, and the clean-interpreter test (`test_import_without_config_connects_to_nothing`) still passes.
- [x] 1.4 Rewrite `tests/test_registration.py` to list tools through `await server.list_tools()`. Default build: 59 tools, none of `DANGEROUS_TOOLS`. Flag on: 71 tools. Both orders in one process: build with the flag on, then off, gives 59. `DANGEROUS_TOOLS` equals the exact 12-name set. Verify: `uv run pytest tests/test_registration.py` passes.
- [x] 1.5 In `tests/test_mcp_interface.py`, over a real in-memory session:
  - flag unset: 59 tools listed, 5 resources and 8 templates still listed
  - calling `reload_app` gives `isError` with `Unknown tool` and no request (pytest-httpx would fail on one)
  - flag on: 71 tools

  Change the existing `len(tools) >= 70` assertion to match. Use `caplog` to check the INFO startup line in both states ("disabled … 12 tools hidden" / "enabled"). Verify: `uv run pytest tests/test_mcp_interface.py` passes.
- [x] 1.6 Add the no-secrets-in-log test (D7): call `test_smtp_settings` with `password="s3cr3t-value"` through the session, failing once with a mocked Listmonk 400 and once with a patched client method that raises. Assert the call is `isError` and that `"s3cr3t-value"` is in no `caplog` record (message or formatted traceback). Verify: `uv run pytest tests/test_mcp_interface.py` passes.
- [x] 1.7 Document the flag:
  - README "Configure Environment Variables": `LISTMONK_MCP_ALLOW_DANGEROUS`, its default, and the 12 tools it exposes
  - `CLAUDE.md` Configuration: the new optional variable
  - `CLAUDE.md` "Conventions for tools": the gate, `DANGEROUS_TOOLS`, and deciding whether a new tool belongs there; tests list tools via `server.list_tools()`

  Verify: `grep -n ALLOW_DANGEROUS README.md CLAUDE.md` finds each section.

## 2. Bounce split (bounce-management)

- [x] 2.1 Split the client (D6): `delete_bounces(bounce_ids: list[int])` sends `id=` params only; the new `delete_all_bounces()` sends `all=true`. Verify: `uv run mypy src/` is clean.
- [x] 2.2 Make `bounce_ids` required on the `delete_bounces` tool, and raise `ValidationError` for an empty list. Update its description: at least one ID, never all. Add a `delete_all_bounces` tool (no parameters, returns `listmonk_json`, description says ALL) and add it to `DANGEROUS_TOOLS`. Verify: `grep -n delete_all_bounces src/listmonk_mcp/server.py` shows the tool and the set entry.
- [x] 2.3 Update `tests/test_bounces.py`:
  - replace `test_delete_bounces_without_ids_deletes_all` with: an empty list is a `ToolError` matching `^ValidationError` with no request
  - `delete_all_bounces` sends `DELETE /api/bounces?all=true` and returns the JSON
  - the `delete_bounces` description says at least one ID and never all
  - the `delete_all_bounces` description says ALL

  Verify: `uv run pytest tests/test_bounces.py` passes, and `uv run pytest tests/test_registration.py` still shows 59/71.

## 3. Settings masking and logs (instance-administration)

- [x] 3.1 Add `src/listmonk_mcp/masking.py` with `mask_settings` (D4). Add `tests/test_masking.py` with a settings fixture shaped like v6.2.0 (`smtp[]`, `messengers[]`, `bounce.mailboxes[]`, `upload.s3.*`, `bounce.sendgrid_key`, `bounce.azure`, `bounce.postmark`, `bounce.forwardemail`, `bounce.lettermint`, `security.captcha.hcaptcha`, `security.oidc`). It covers each spec scenario:
  - clear-text secrets masked
  - 12- and 4-bullet values both become `********`
  - an empty secret stays `""`
  - `aws_access_key_id`, `hcaptcha.key` and `client_id` unchanged
  - the three explicit `*key` paths masked
  - the input is not mutated

  Verify: `uv run pytest tests/test_masking.py` passes.
- [x] 3.2 Apply `mask_settings` in `get_settings`, and update its docstring (masked as `********`, never write back). Add a tool-level test in `tests/test_admin.py`: a mocked `/api/settings` with a clear-text SMTP password returns output with `********`, without the password, and with host and username intact. Verify: `uv run pytest tests/test_admin.py` passes.
- [x] 3.3 Rewrite `get_logs(lines: int = 100)` (D5) and update its docstring. Add tests to `tests/test_admin.py`:
  - 4873 mocked lines: the header says `last 100 of 4873`, followed by the last 100 in order
  - 30 lines with `lines=100`: `30 of 30`
  - `lines=0` and `lines=5001`: `ValidationError` with no request
  - `data` not a list: `0 of 0`

  Verify: `uv run pytest tests/test_admin.py` passes.
- [x] 3.4 Update `tests/test_admin.py::test_update_setting_docs_warn_about_reload` and any other test that reaches a gated tool, so they still read descriptions from `server.mcp._tool_manager` (hidden tools stay registered, D1). Verify: `uv run pytest` passes in full.

## 4. Changelog and integration checks

- [x] 4.1 CHANGELOG `[Unreleased]`:
  - **BREAKING** entries for the 12 hidden tools (with the flag to restore them) and for `delete_bounces` requiring IDs
  - Added entries for `delete_all_bounces`, settings masking and `get_logs(lines)`
  - remove the "Not yet changed" note about unguarded tools

  Verify: `grep -n "Not yet changed" CHANGELOG.md` finds nothing about destructive tools.
- [x] 4.2 Run the CI gates locally. Verify: `uv run ruff check src/`, `uv run mypy src/` and `uv build` succeed, and `uv run pytest` passes with no failures.
- [x] 4.3 Live check against local Listmonk v6.2.0 (`docker compose -f docs/listmonk-docker-compose.yml up -d`, API user + token), over stdio with an MCP client:
  - flag unset: 59 tools, `reload_app` unknown
  - flag `true`: 71 tools
  - `get_settings` after setting an SMTP password in the UI shows `********` and not the password
  - `get_logs` shows the header and at most 100 lines
  - `delete_bounces([])` is rejected

  No real email is sent. Verify: record the results under this task, then tear down with `down -v` and delete the credential files.
  - Ran on the local Docker engine only (`--context default`; the active context points at a remote host). Stack `lm-gr-test`: `listmonk/listmonk:v6.2.0` and `postgres:17-alpine`, port bound to `127.0.0.1`, compose file and credentials in the job's tmp folder (not the repo). API user created through the admin session. A random SMTP password was set via `PUT /api/settings` (that's the "UI" step), and its storage confirmed in Postgres. A driver outside the repo ran the real `listmonk-mcp` over stdio. **11/11 passed:**
    - flag unset: 59 tools, `reload_app` not listed, and calling it gives `isError` "Unknown tool: reload_app"
    - `get_settings`: the SMTP password shows as `'********'`, the real value is absent, and the host is still visible
    - `get_logs`: header `Logs: last 4 of 4 lines` (the reload had just reset Listmonk's buffer, so the 100-line cap was only covered by unit tests). `lines=0` is a `ValidationError`
    - `delete_bounces([])` is a `ValidationError`
    - flag `true`: 71 tools, including `delete_all_bounces`
  - Also checked from stderr: the startup line `Dangerous tools disabled (LISTMONK_MCP_ALLOW_DANGEROUS unset): 12 tools hidden`, and `LISTMONK_MCP_ALLOW_DANGEROUS=maybe` exits 1 with a `bool_parsing` config error.
  - Torn down with `down -v`; the compose file, credentials and driver were deleted.
- [x] 4.4 Commit to `master` and push with no tags, after scanning the outgoing history for internal host and container names. Verify: `git status -sb` is level with `origin/master`, and the scan finds nothing.
  - The scan of the outgoing diff and of the unpushed `6908bb0` (fix-core-tools archive) found no internal host, container or user names. Pushed `45314f4..a54bb06` with no tags; the remote tags are still only `v0.0.1`, `v0.0.2` and `v0.1.0`.

## Workflow follow-up

- Archive this change and sync its specs (`/opsx:archive`).
- Then propose the deploy change (handoff §6–§7): pin the fork tag in the Dockerfile, leave `LISTMONK_MCP_ALLOW_DANGEROUS` unset in compose, and check the it-ops plugin for references to the 12 hidden tools and to `delete_bounces([])`.
