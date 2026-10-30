# Proposal

## Why

`merge-upstream-prs` brought in upstream PR #8, which added tools that can wipe or rewrite a whole Listmonk instance in one call. Examples: replacing the settings document, deleting every subscriber a SQL query matches, deleting all bounces, garbage collection, reloading the app. None of them has a guard. `get_settings` also relies only on Listmonk's own masking of secrets, and `get_logs` returns all of Listmonk's 5000-line log buffer as a single Python list. No tag may be deployed until this is fixed (the merge-upstream-prs proposal, "Not deployable on its own").

## What Changes

- **Dangerous-tools flag:** a new setting, `LISTMONK_MCP_ALLOW_DANGEROUS` (default `false`). When it is off, the server **does not expose** these 12 tools: they are missing from the tool list, and calling one by name fails as an unknown tool:
  - settings and app: `update_settings`, `update_setting`, `reload_app`
  - by query: `delete_subscribers_by_query`, `blocklist_subscribers_by_query`, `manage_subscriber_lists_by_query`
  - all records: `blocklist_bounced_subscribers`, `delete_all_bounces` (new)
  - bulk: `delete_campaigns`
  - maintenance: `gc_subscribers`, `gc_campaign_analytics`, `gc_unconfirmed_subscriptions`

  The rule: a tool is gated if it acts on records chosen by a query or on every record, if it reloads Listmonk (both settings writes do, unless a campaign is running), or if the handoff names it. Tools limited to explicit IDs stay available, and so does `test_smtp_settings`. **BREAKING** for clients that use these tools without setting the flag.
- **Startup log:** one INFO line saying whether dangerous tools are on, and how many tools are hidden.
- **`delete_bounces` split:** `delete_bounces(bounce_ids)` requires at least one ID. An empty or missing list is rejected before any request is sent. Deleting every bounce moves to a new, gated `delete_all_bounces` tool. **BREAKING:** `delete_bounces([])` no longer deletes all bounces.
- **Settings secrets masked by key name:** `get_settings` replaces the value of every key whose name contains `password` or `secret` (at any depth, including list items), plus `bounce.sendgrid_key` and the `key` of `bounce.forwardemail` and `bounce.lettermint`, with a fixed `********`. Empty values stay empty, so a client can still see that a secret is not set. This is a second layer on top of Listmonk's masking, and the fixed length hides the length that Listmonk's bullets reveal.
- **`get_logs(lines=100)`:** returns the last `lines` log lines (1 to 5000), oldest first, one per line, under a header that gives how many lines are shown out of how many exist. A value out of range is rejected before any request is sent. Log lines are not filtered.
- **No secrets in the server's own log:** tool arguments (for example a setting value or SMTP password) are never written to the server log. That holds today, and this change locks it in with tests.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `mcp-interface`: the dangerous-tools flag decides which tools are exposed, the startup log reports it, and tool arguments never reach the server log
- `instance-administration`: `get_settings` masks secrets by key name, `get_logs` returns the last N lines, and the settings, reload and garbage-collection tools are available only with the flag
- `bounce-management`: `delete_bounces` requires IDs, the new `delete_all_bounces` deletes every bounce, and that tool and `blocklist_bounced_subscribers` are available only with the flag
- `subscriber-management`: the three by-query tools are available only with the flag
- `campaign-management`: `delete_campaigns` is available only with the flag

## Out of scope

- The `--config/-c` CLI option, which is accepted but never used (`server.py:2425`). The flag, like every other setting, is read only from the environment or `.env`.
- Gating `send_campaign`, the delete-by-ID tools, `import_subscribers` or `test_smtp_settings`.
- Filtering secrets out of Listmonk's log lines.
- Changing the read format of `get_settings` beyond masking.
- Deploying, tagging and checking the plugin: that's the deploy change.

## Impact

- Code: `config.py` (new field), `server.py` (marking the gated tools, building the server from config, `delete_bounces`/`delete_all_bounces`, `get_settings` masking, `get_logs`, startup logging), and possibly a small helper module for masking. `client.py` keeps `delete_bounces`, and a separate client method is added for deleting all bounces.
- Tool count: 71 tools exist (`delete_all_bounces` is new), and 59 are exposed by default. `tests/test_registration.py` pins both states.
- Clients: the deployed it-ops plugin sees 12 fewer tools unless the flag is set. Checking it for references to them belongs to the deploy change.
- Docs: the README and `CLAUDE.md` (configuration) document `LISTMONK_MCP_ALLOW_DANGEROUS`, and the CHANGELOG note about unguarded tools (`CHANGELOG.md:40`) is resolved.
