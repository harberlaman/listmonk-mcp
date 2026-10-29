# Design

## Context

- Tool pattern today: each of the 70 tools wraps its logic in `safe_execute_async`. On a `ListmonkAPIError` it returns the string `"Error: <type> - <message>"`. On any other exception it returns `"Unexpected error: …"` plus a full traceback. Both look like normal results to MCP clients. Two tools also return `"Error: ValidationError - …"` strings themselves (`_invalid_before_date`, `patch_subscriber`).
- `map_http_status_to_exception` compares `400 <= status_code` without checking for `None`. A `ListmonkAPIError` with no status, raised for a missing file or a network failure after retries, therefore raises `TypeError` inside the error handler. It also replaces Listmonk's message with generic text for 404 and 409 (`"Resource with ID 'unknown' not found"`).
- 48 tools make non-GET requests, not counting `preview_template_body`, which uses POST but only reads. Most return a "Successfully …" string.
- `create_production_server()` builds a second `FastMCP` with the lifespan and copies only `_tool_manager._tools` across, so the running server has 0 resources and 0 templates (checked 2026-10-28).
- `ListmonkClient.connect()` sets a default `Content-Type: application/json` on the shared client. That's why `upload_media` and `import_subscribers` each build a separate `AsyncClient` with their own auth header for multipart, and why `_request(form_data=…)` has to set its own header.
- Listmonk v6.2.0 facts this design relies on (from `knadh/listmonk` `cmd/tx.go`, `cmd/media.go`, `models/messages.go`):
  - `/api/tx` takes JSON, or multipart with a `data` JSON part plus `file` parts.
  - Recipients are `subscriber_emails` or `subscriber_ids`. The singular forms are deprecated.
  - `fallback` and `external` modes reject IDs.
  - `headers` is a list of `{name: value}` maps.
  - There's no default `content_type`.
  - Success returns `{"data": true}`, meaning queued.
  - `POST /api/media` reads only the `file` part and ignores any title, and there's no media update route.

## Goals / Non-Goals

**Goals:**
- One place decides how failures reach the client and how write results are returned, so all 70 tools behave the same.
- Remote clients can do everything the IT training-email work needs (tx templates, tx sends, logo upload, list membership) without sharing a filesystem with the server.

**Non-Goals:**
- How resources report failures. Resource reads keep returning formatted error text. This change only makes resources visible.
- Restricting which tools are registered, or masking settings secrets (guardrails change).
- Converting read tools to JSON.

## Decisions

### D1. One shared tool runner that raises MCP errors
Replace `safe_execute_async` with `run_tool(logic)`:
1. It awaits `logic()`.
2. A `ListmonkMCPError` (including a new local `ValidationError` raised by tool code) is logged at WARNING with the tool name, then re-raised as `ToolError("<ErrorType>: <message>")`.
3. A `ListmonkAPIError` is mapped through the fixed mapper (D2) first.
4. Any other exception is logged at ERROR with its traceback, in the server log only, and raised as `ToolError("UnexpectedError: <message>")`.

FastMCP turns `ToolError` into `isError: true`.
- *Why:* a single place to change means no tool can return an error string by mistake. Tracebacks stay in the server log, where operators can see them, and out of client output.
- *Alternative:* add `try/except` in each of the 70 tools. Rejected because it's repetitive and easy to get wrong.
- The two existing `"Error: ValidationError"` returns become `raise ValidationError(...)`.

### D2. Fix the error mapper
`map_http_status_to_exception` gets `status_code: int | None`. `None` maps to `APIError` (or `OperationError` when the message says a file was not found), with no range comparisons. Every branch keeps the message Listmonk sent (taken from `response["message"]`, falling back to the generic text).
- *Why:* this fixes P3's crash for media and N9's for import at the root, and the spec requires Listmonk's message to reach the client.

### D3. Write tools return Listmonk's JSON
Add `listmonk_json(result) -> str` (`json.dumps(result, ensure_ascii=False, indent=2, default=str)`). Every write tool returns `listmonk_json(<client result>)`. Tools that read before they write (the `*_replace_in_campaign_body` tools) return the write's response.
- *Why:* this is the handoff §5 rule. Clients and models can see exactly what Listmonk accepted.
- *Alternative:* MCP structured output (return a `dict`). Rejected for now, because the 22 read tools return `str` and mixing the two would change every schema at once.
- Tool descriptions are unchanged except where a spec requires a warning (`send_transactional_email`, `delete_bounces`).

### D4. One `FastMCP` instance with the lifespan
Create `mcp = FastMCP("Listmonk MCP Server", lifespan=lifespan)` at module level, and have `create_production_server()` return it. The private copying of `_tool_manager` goes away.
- *Why:* tools, resources and templates are then all registered on the server that runs, with no private API. The lifespan only runs when the server starts, so importing `server` in tests still doesn't connect to anything.
- *Alternative:* also copy `_resource_manager._resources` and `_templates`. Rejected because it depends on even more private API.

### D5. No default `Content-Type` on the shared HTTP client
`connect()` stops setting `Content-Type`. httpx sets the right header per request (JSON, form or multipart). `_request` gains `files=` for multipart. The separate `AsyncClient`s in `upload_media` and `import_subscribers` are removed, so all requests share auth, timeouts, retries and error handling. The explicit form header added for N5 becomes unnecessary and is removed.

### D6. Upload checks shared by media and import
A helper resolves the upload source:
- exactly one of `content_base64` + `filename`, or `file_path`
- base64 decoded strictly (`validate=True`)
- the extension checked against an allow-list
- the decoded size checked against a limit

It raises `ValidationError` before any request is sent.

| | Allowed | Limit |
|---|---|---|
| Media | `png`, `jpg`, `jpeg`, `gif`, `webp` | 5 MB |
| Import | `csv`, `zip` | 10 MB |

- **SVG is excluded** from media, because Listmonk serves uploads from a public URL and SVG can carry script.
- **No title:** Listmonk v6.2.0 has no media update route (`GET`, `POST /api/media` and `DELETE /api/media/:id` only), and the upload reads only the `file` part. So neither upload tool takes a `title`. The broken `rename_media` tool and `client.update_media`, which called the non-existent `PUT /api/media/{id}`, are removed (decided 2026-10-29). `upload_media` returns the upload response, which includes the `url`.
- `upload_media` is a new tool. `upload_media_file(file_path)` keeps its name and goes through the same helper. `import_subscribers` gains `content_base64` and `filename`, and `file_path` becomes optional.

### D7. Transactional send
`send_transactional_email(template_id, subscriber_email?, subscriber_id?, subscriber_emails?, subscriber_ids?, subscriber_mode?, subject?, from_email?, data?, headers?, content_type="html", altbody?, messenger?, attachments?)`:
- **Recipients:** exactly one selector is required. The singular forms are normalized to the list forms. IDs are rejected in `fallback` and `external` modes. Listmonk enforces these rules too, but checking locally gives a clear message and sends nothing.
- **Request body:** only the fields that were given.
- **Attachments:** with attachments, the request is multipart (`data` = the JSON body, a `file` part per attachment, each decoded with D6's strict base64 and with no type allow-list). Without them, it's JSON.
- **Description:** says that success means queued, and points to `get_logs` for delivery errors.

### D8. Subscriber records formatter
One function, `format_subscribers(result, page, per_page, heading)`, renders Listmonk's `data.results`, `total`, `page` and `per_page`. Each subscriber gets one line, `id | email | name | status`, followed by its lists as `Name (ID: n, subscription_status)` and its attributes as compact JSON. It's used by `get_list_subscribers_tool` and by the `listmonk://subscribers` and `listmonk://list/{id}/subscribers` resources.

### D9. Health includes about
`check_listmonk_health` calls `/api/health`, then `/api/about`. If about fails, the tool still reports healthy and adds "version unavailable: <reason>". `get_about_info` is unchanged.

### D10. Testing
- **Mocked unit tests** (pytest-httpx) for every spec scenario. The existing 24 tests are updated where they assert "Successfully …" or "Error: …" strings.
- **In-process MCP tests:** `mcp.shared.memory.create_connected_server_and_client_session` runs the real server object in memory. These check `isError`, that no traceback appears, and that resources and templates are listed. The lifespan's health check is answered by a pytest-httpx mock.
- **Live check:** a throwaway Listmonk v6.2.0 on the local Docker engine (`--context default`, as in the last change), plus a local SMTP catcher (`axllent/mailpit`), so a tx send's headers and attachment can be checked in the delivered message. The production host is not used for writes.

## Risks / Trade-offs

- [The return-format change breaks clients that parse "Successfully …" or "Error: …"] → the proposal flags it as BREAKING. The deploy change checks consuming clients for string matching before the tag is used.
- [Dropping the default `Content-Type` changes every request] → httpx sets `application/json` whenever `json=` is used, and the mocked tests assert the headers for JSON, form and multipart requests. The live run covers every endpoint again.
- [Making all write tools return JSON touches 48 functions] → it's mechanical. A grep check (no `"Successfully` left in `server.py`) plus the registration test keeps it complete.
- [A single `FastMCP` with the lifespan could connect to Listmonk on import] → the lifespan only runs in `run()`/sessions. A test imports the module with no Listmonk configured, to prove nothing connects.
- [The 5 MB and 10 MB limits are our choice, not Listmonk's] → they're constants in one place. Listmonk's own media extension setting still applies on top.
