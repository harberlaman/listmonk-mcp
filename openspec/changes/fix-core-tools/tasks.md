# Tasks

## 1. Errors and server wiring (mcp-interface)

- [x] 1.1 Fix `map_http_status_to_exception` for `status_code=None`, and keep Listmonk's `message` in every branch (design.md D2). Add `tests/test_errors.py` covering a missing status, 400, 404 and 500 with Listmonk messages. Verify: `uv run pytest tests/test_errors.py` passes.
  - `status_code=None` maps to `OperationError` (file not found) or `APIError`, with no range comparisons. 404 and 409 now keep Listmonk's message. `tests/test_errors.py`: 5 passed.
- [x] 1.2 Replace `safe_execute_async` with `run_tool` (D1): log, then raise `ToolError` for Listmonk, validation and unexpected errors, with no traceback in the message. Switch all 70 tools to it. Turn the two `"Error: ValidationError"` returns (`_invalid_before_date`, `patch_subscriber`) into `raise ValidationError`. Verify: `grep -c safe_execute_async src/` is 0, and `grep -n '"Error:' src/listmonk_mcp/server.py` finds nothing.
  - `run_tool` is in `exceptions.py`. It logs at WARNING (Listmonk and validation errors) or logs the exception (unexpected), then raises `ToolError("<Type>: <message>")`. All 70 tools switched. Also converted a third normal-result error string in `get_media_list` to `raise APIError`. Removed the old runner helpers `safe_execute`, `safe_execute_async` and `format_mcp_error`. Resources keep their "Error retrieving …" text, as the design says.
- [x] 1.3 Use a single `FastMCP` with the lifespan, and have `create_production_server()` return it, with no `_tool_manager` copying (D4). Verify: an in-memory session test (`tests/test_mcp_interface.py`, using `create_connected_server_and_client_session`, with health mocked) lists 70 tools, 5 resources and 8 resource templates, and reading `listmonk://lists` returns formatted lists.
  - `mcp = FastMCP(..., lifespan=lifespan)` at module level, and `create_production_server()` returns it. The in-memory session lists 70 tools, 5 resources and 8 templates, and `listmonk://lists` reads correctly.
- [x] 1.4 In `tests/test_mcp_interface.py`, add the failure scenarios: a 4xx with a Listmonk message gives `isError` with that message; a bad `before_date` gives `isError` and no request; an unexpected exception gives `isError` with no `Traceback`. Add a test that importing `listmonk_mcp.server` with no `LISTMONK_MCP_*` env set makes no request. Verify: `uv run pytest tests/test_mcp_interface.py` passes.
  - Sessions are opened inside each test, because anyio cancel scopes can't span fixture setup and teardown. The import check runs in a clean subprocess with no `LISTMONK_MCP_*` settings, rather than reloading the module. 6 passed.
- [x] 1.5 Update the existing tests that assert `"Error: ValidationError"` (`test_admin`, `test_subscribers`) to expect `ValidationError` or `ToolError` instead. Verify: `uv run pytest` passes.
  - `test_admin` and `test_subscribers` now expect `ToolError` matching `^ValidationError: …`. Full suite: 35 passed.

## 2. Write tools return Listmonk's JSON (mcp-interface)

- [ ] 2.1 Add `listmonk_json()` and make every write tool (the 48 non-GET tools, excluding `preview_template_body`) return Listmonk's response (D3). Add the "no IDs deletes ALL bounces" warning to the `delete_bounces` description. Verify: `grep -n 'Successfully' src/listmonk_mcp/server.py` finds nothing.
- [ ] 2.2 Update the tests that assert "Successfully …" text (`test_admin`, `test_bounces`, `test_subscribers`) to assert the JSON result. Add `create_mailing_list` (returns the JSON with the new `id`) and `get_templates` (still formatted text) to `tests/test_mcp_interface.py`. Verify: `uv run pytest` passes.

## 3. HTTP client and uploads (media-management, subscriber-import)

- [ ] 3.1 Stop setting a default `Content-Type` in `connect()`, add `files=` to `_request`, remove the explicit form header, and drop the separate `AsyncClient`s in media upload and import (D5). Update `tests/conftest.py` to match `connect()`'s headers. Add tests asserting the content type of a JSON request, a form request (`preview_template_body`) and a multipart request. Verify: `uv run pytest` passes.
- [ ] 3.2 Add the shared upload-source helper (D6): exactly one source, strict base64, extension allow-list, size limit, all raising `ValidationError` before any request. Add `tests/test_uploads.py` for each rejection. Verify: `uv run pytest tests/test_uploads.py` passes.
- [ ] 3.3 Add the `upload_media(content_base64, filename, title?)` tool, and move `upload_media_file` onto the helper. Add a follow-up `update_media` call when a title is given. Test: a PNG upload returns a response with `url`; a title triggers the PUT; `.svg`, `.txt`, more than 5 MB, bad base64 and a missing path are each rejected with no request. Update `tests/test_registration.py` to 71 tools. Verify: `uv run pytest` passes.
- [ ] 3.4 Add `content_base64` + `filename` to `import_subscribers`, make `file_path` optional, and use the helper (csv/zip, 10 MB). Test: an uploaded CSV sends a multipart request with `params` and `file`; both or neither source is rejected; a missing path gives an MCP error, not a `TypeError`. Verify: `uv run pytest` passes.

## 4. Templates and transactional email

- [ ] 4.1 `create_template` gains `subject`, rejects a `tx` template without a subject, and documents that the type can't be changed (template-management). Test both scenarios in `tests/test_templates.py`. Verify: `uv run pytest tests/test_templates.py` passes.
- [ ] 4.2 Rewrite `send_transactional_email` in the client and server (D7): selectors, mode rules, optional fields left out, `content_type` defaulting to `html`, multipart attachments, and the "queued" description. Add `tests/test_transactional.py` covering every scenario in `specs/transactional-email`. Verify: `uv run pytest tests/test_transactional.py` passes.

## 5. Subscriber records and health

- [ ] 5.1 Add `format_subscribers` (D8), and use it in `get_list_subscribers_tool`, `listmonk://subscribers` and `listmonk://list/{list_id}/subscribers`. Test: 3 records with lists and subscription status, paging (page 2, per_page 2, total 3), and an empty list. Verify: `uv run pytest tests/test_subscribers.py` passes.
- [ ] 5.2 Make `check_listmonk_health` include version and build from `/api/about`, still reporting healthy with "version unavailable" when about fails (D9). Test both cases in `tests/test_admin.py`. Verify: `uv run pytest tests/test_admin.py` passes.

## 6. Integration checks

- [ ] 6.1 Run `uv run ruff check src/ tests/ && uv run mypy src/ && uv build && uv run pytest`. Verify: all pass.
- [ ] 6.2 Live run on the local Docker engine (`--context default`): Listmonk `v6.2.0` plus `axllent/mailpit`, ports on `127.0.0.1` only, with Listmonk's SMTP pointed at mailpit. Over stdio, check that the server lists 71 tools, 5 resources and 8 templates; create a tx template with a subject; send a tx message with `subject`, `from_email`, `X-Training-ID: TEST-01` and one attachment, then confirm in mailpit's API that the message arrived with that header and attachment; send in `external` mode to a non-subscriber; upload a PNG with `upload_media` and get a `url`; import a CSV with `content_base64`; list subscribers with lists shown; health shows v6.2.0; a failing call shows `isError`. Tear the stack down afterwards. Verify: each check is recorded here as pass, or fail with a `NOTE:`.
- [ ] 6.3 Update `CLAUDE.md`: the `run_tool`, `ValidationError` and `ToolError` error pattern; write tools returning `listmonk_json`; the single `FastMCP` with resources served; no default `Content-Type`; the upload helper. Verify: the documented test commands run.
- [ ] 6.4 Commit to `master` and push with no tags. Before pushing, scan the outgoing history for internal host and container names. Verify: `git status -sb` is level with `origin/master`, and the scan finds nothing.

## Workflow follow-up

- Archive this change and sync its specs (`/opsx:archive`).
- Then propose the guardrails change, using the "Carried forward" items in `openspec/changes/archive/2026-10-28-merge-upstream-prs/tasks.md`.
