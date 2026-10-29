# Proposal

## Why

Upstream `rhnvrm/listmonk-mcp` (v0.1.0) has been inactive since 2026-01-13, but two open PRs already fix or add much of what the IT training-email project needs: carrying `subject` forward on tx template updates (P2) and settings/logs/about/campaign test-send coverage (P6, P7, P8). Merging them into the `harberlaman/listmonk-mcp` fork first gives later changes (core tool fixes, guardrails, deploy) a stable base, and keeps "what upstream wrote" separate from "what we changed".

## What Changes

- Merge upstream PR **#11** (ohm-meter, +14/−3): `update_template` carries the existing `subject` forward, so tx templates can be edited.
- Merge upstream PR **#8** (jlxq0, +1192/−5): 41 new tools (29 → 70) and a version bump to 0.2.0. New tools by area:
  - Subscribers: `patch_subscriber`, `subscriber_send_optin`, `blocklist_subscriber(s)`, `manage_subscriber_lists`, `get_subscriber_activity`, `*_by_query` (delete, blocklist, manage lists)
  - Bounces: `list_bounces`, `get_bounce`, `get_subscriber_bounces`, `delete_bounce(s)`, `delete_subscriber_bounces`, `blocklist_bounced_subscribers`
  - Import: `import_subscribers`, `get_import_status`, `get_import_logs`, `stop_import`
  - Campaigns: `test_campaign`, `change_campaign_status`, `archive_campaign`, `delete_campaign(s)`, `get_running_campaign_stats`, `get_campaign_analytics`
  - Templates: `set_default_template`, `preview_template_body`
  - Instance admin: `get_settings`, `update_settings`, `update_setting`, `test_smtp_settings`, `reload_app`, `get_logs`, `get_about_info`, `get_dashboard_counts`, `get_dashboard_charts`, `gc_subscribers`, `gc_campaign_analytics`, `gc_unconfirmed_subscriptions`
- A test merge (`git merge-tree`, 2026-10-28) shows that #8 and #11 merge cleanly, but both touch `update_template`. The merged result must be reviewed by hand, not trusted because there were no conflicts.
- Fix the seven #8 tools that the review against the Listmonk v6.2.0 source found to send requests Listmonk rejects or handles differently than described (GC cut-off dates, analytics dates, template preview encoding, `patch_subscriber`, `blocklist_bounced_subscribers`). **BREAKING** relative to #8: `patch_subscriber` loses `action`/`target_list_ids`, and `blocklist_bounced_subscribers` loses `bounce_ids`.
- Review #8 before merging. It is large and AI-written. Its claims that ruff and mypy pass are checked locally, not taken on trust.
- Commits go directly to `master` on `harberlaman/listmonk-mcp`, with no PRs.
- **Not deployable on its own.** #8 registers destructive tools (`update_settings`, `reload_app`, `delete_subscribers_by_query`, `blocklist_subscribers_by_query`, `delete_bounces`, `delete_campaigns`, `gc_*`) with no gate. No tag may be deployed from this change until the guardrails change is done.

## Capabilities

### New Capabilities
- `template-management`: create, update, preview, default-select and delete templates, including that a tx template's `subject` survives an update
- `campaign-management`: campaign lifecycle beyond create/send: test send, status changes, archive, delete, stats and analytics
- `subscriber-management`: per-subscriber and query-based subscriber operations, list membership, blocklisting and activity
- `bounce-management`: listing, inspecting, deleting and acting on bounces
- `subscriber-import`: starting, monitoring and stopping bulk subscriber imports
- `instance-administration`: reading and changing Listmonk settings, SMTP tests, logs, version/about, dashboard counts and maintenance (`gc_*`, reload)

### Modified Capabilities
- None. There are no existing specs.

## Out of scope

- **PR #10** (KVSocial, paginated mailing-list search) is not being merged (decided 2026-10-28).

## Impact

- Code: `src/listmonk_mcp/client.py` (+~425 lines), `src/listmonk_mcp/server.py` (+~775 lines), `pyproject.toml` (version 0.2.0), `uv.lock`, `README.md`.
- MCP surface: the tool count rises from 29 to 70. The 13 resources are unchanged. Clients that use this server see the new tool names. No existing tool is renamed.
- Not affected yet: the deployed server stays on the upstream clone until the deploy change.
- Known issues carried forward, not fixed here: resources are not copied to the production server, and errors come back as ordinary text rather than marked as errors. Both belong to later changes.
