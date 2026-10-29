# Proposal

## Why

After `merge-upstream-prs`, the server still can't do what the IT training-email work needs:
- transactional templates can't be created
- transactional sends only expose a fraction of `/api/tx`
- remote clients can't upload media or import files, and a missing file crashes the error mapper
- list-subscriber tools return only a count

Two problems also affect every tool:
- **Failures come back as ordinary text.** A client can't tell an error from a success.
- **Write tools return made-up "Successfully…" messages** instead of Listmonk's response. A tx send that is only *queued* is reported as sent, and a write that errors may still have landed.

The same check showed that the 13 `listmonk://` resources never reach clients. The production server exposes 0 of them.

## What Changes

- **Errors, server-wide:** every failure (a Listmonk error response, network failure, local validation, or an unexpected exception) is raised as an MCP tool error (`isError: true`) with a readable message. No tracebacks reach the client, and no tool returns an "Error: …" string as a normal result. **BREAKING** for clients that parse error strings.
- **Write tools return Listmonk's response:** the 48 tools that change state return Listmonk's JSON response instead of "Successfully …" text. Read tools keep their formatted text. **BREAKING** for clients that match the old success strings.
- **Error mapper:** an error with no HTTP status (for example, a local file not found) no longer crashes with a `TypeError`.
- **Resources served:** all 5 resources and 8 resource templates are exposed by the server that actually runs.
- **P1:** `create_template` accepts `subject`. A `tx` template without a subject is rejected before any request is sent.
- **P4:** `send_transactional_email` exposes the full `/api/tx` request:
  - recipients: exactly one of `subscriber_email`, `subscriber_id`, `subscriber_emails` or `subscriber_ids`
  - `subscriber_mode` (`default`, `fallback` or `external`)
  - optional `subject` and `from_email` overrides
  - `data`, `headers`, `content_type`, `altbody` and `messenger`
  - attachments as base64

  `content_type` still defaults to `html`, because Listmonk sets no default for transactional sends.
- **P3:** a new `upload_media` tool takes `content_base64` + `filename`, limited to image types and 5 MB, and returns the media URL. `upload_media_file(file_path)` stays as a fallback for local stdio use, with the same checks. Neither takes a `title`, because Listmonk v6.2.0 can't store one. **BREAKING:** `upload_media_file` loses its `title` argument, which Listmonk always ignored, and the `rename_media` tool is removed, because it called an endpoint v6.2.0 doesn't have.
- **N9:** `import_subscribers` also accepts `content_base64` + `filename` (CSV or ZIP, up to 10 MB), keeping `file_path` as the local fallback.
- **P5:** `get_list_subscribers_tool` and the `listmonk://subscribers` and `listmonk://list/{id}/subscribers` resources return records page by page (id, email, name, status, lists with subscription status, attributes) instead of a count.
- **P7:** `check_listmonk_health` also reports Listmonk's version and build from `/api/about`.

## Capabilities

### New Capabilities
- `mcp-interface`: how the server presents itself to MCP clients: error signaling, the return format of write and read tools, and which resources are exposed
- `transactional-email`: sending transactional messages through Listmonk templates to subscribers or external addresses, with headers, overrides and attachments
- `media-management`: uploading media from remote clients, and what Listmonk v6.2.0 supports for media (upload, list and delete; no rename)

### Modified Capabilities
- `template-management`: adds creating templates with a subject (tx requires one); `set_default_template` returns Listmonk's response instead of a confirmation string
- `subscriber-import`: imports accept uploaded content as well as a server-local path, and a missing file is a clean error
- `subscriber-management`: list-subscriber tools and resources return subscriber records, paginated
- `bounce-management`: `delete_bounces` returns Listmonk's response, and the "deletes ALL" warning moves into the tool description
- `instance-administration`: the health check includes version and build

## Out of scope

- Gating destructive tools and masking settings secrets: that's the guardrails change.
- Deploying, tagging and checking the plugin: that's the deploy change.
- The other upstream tools' read formats, beyond the records added by P5.

## Impact

- Code: `src/listmonk_mcp/exceptions.py` (error mapping and the shared tool wrapper), `server.py` (all write tools' return values, the new and changed tools, how the server is built), `client.py` (tx, media, import, template, connection headers). `models.py` is unchanged.
- Clients: any MCP client or skill that reads tool output will see errors flagged as errors and JSON from write tools. The plugin-side check belongs to the deploy change.
- Tests: the existing 24 mocked tests need updating where they assert "Successfully …" or "Error: …" strings. New tests cover each item above.
