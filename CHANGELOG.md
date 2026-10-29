# Changelog

Changes to this fork of [`rhnvrm/listmonk-mcp`](https://github.com/rhnvrm/listmonk-mcp), newest first. Breaking changes are marked **BREAKING**. Planning records for each change are in `openspec/changes/archive/`.

## [Unreleased] (0.2.0)

Built on upstream v0.1.0 and tested against Listmonk v6.2.0.

### Breaking changes

- **BREAKING: tool failures are MCP errors.** Every failure (a Listmonk error, a network failure, rejected input or an unexpected exception) is returned with `isError: true` and text of the form `<ErrorType>: <message>`. Tools no longer return `Error: …` or `Unexpected error: … Traceback …` as normal results.
- **BREAKING: write tools return Listmonk's JSON response.** The 48 tools that change state return Listmonk's response body as JSON text instead of a `Successfully …` message. Read tools still return formatted text.
- **BREAKING: `send_transactional_email` takes recipient selectors.** `subscriber_email` is no longer a required positional argument. Give exactly one of `subscriber_email`, `subscriber_id`, `subscriber_emails` or `subscriber_ids`.
- **BREAKING: `rename_media` is removed.** Listmonk v6.2.0 has no media update endpoint, so it always failed.
- **BREAKING: `upload_media_file` has no `title` argument.** Listmonk ignores titles on upload.
- **BREAKING: `patch_subscriber` takes subscriber fields** (`email`, `name`, `status`, `attributes`, `lists`, `preconfirm`) instead of upstream PR #8's `action`/`target_list_ids`, which Listmonk ignored. `lists` replaces the subscriber's subscriptions.
- **BREAKING: `blocklist_bounced_subscribers` takes no bounce IDs.** Listmonk always blocklists every subscriber that has a bounce record, so the tool now says so.
- **BREAKING:** `gc_campaign_analytics` requires `before_date` (RFC3339). `gc_unconfirmed_subscriptions` takes `before_date` instead of `before`. `get_campaign_analytics` requires `from_date` and `to_date`.

### Added

- 41 tools from upstream PR #8: campaign test sends, status, archive, analytics and deletion; per-subscriber and query-based subscriber operations; bounces; subscriber import; settings, logs, version info, dashboard and maintenance.
- `upload_media(content_base64, filename)` for remote clients: png/jpg/jpeg/gif/webp, up to 5 MB, returns the media `url`.
- `import_subscribers` accepts `content_base64` + `filename` (CSV/ZIP, up to 10 MB) as well as `file_path`.
- `send_transactional_email` covers the full `/api/tx` request: `subscriber_mode` (`default`/`fallback`/`external`), `subject` and `from_email` overrides, `headers`, `altbody`, `messenger` and base64 `attachments`. Success means the message was queued; delivery errors appear only in `get_logs`.
- `create_template` takes `subject`, required for `tx` templates.
- `check_listmonk_health` reports Listmonk's version and build.
- `get_list_subscribers_tool` and the subscriber resources show each subscriber (id, email, name, status, lists with subscription status, attributes), with page and total.

### Fixed

- The 5 `listmonk://` resources and 8 resource templates are now served; the running server previously exposed none.
- `update_template` keeps a transactional template's stored `subject` (upstream PR #11).
- An error without an HTTP status (for example a missing local file) no longer crashes with a `TypeError`.
- Several upstream PR #8 tools now send what Listmonk v6.2.0 expects: template preview (form fields and HTML response), version info (unwrapped response), subscriber activity (views and clicks), and the GC cut-off date (`before_date`).
- `update_setting` and `update_settings` say that Listmonk reloads after a settings change unless a campaign is running.

### Not yet changed

- Destructive tools (`update_settings`, `reload_app`, query-based deletes and blocklists, deleting all bounces, `delete_campaigns`, `gc_*`) are registered with no guard, and `get_settings` relies on Listmonk's own masking of secrets. A guardrails change is planned before this is deployed.
