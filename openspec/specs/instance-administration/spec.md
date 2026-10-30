# instance-administration Specification

## Purpose

Lets MCP clients inspect and administer the Listmonk instance itself: settings, SMTP testing, logs, version and build info, dashboard figures, and maintenance (garbage collection and reload).

## Requirements

### Requirement: Read settings
The `get_settings` tool SHALL return the full settings document from `GET /api/settings`, with secret values masked by key name on top of Listmonk's own masking. A value SHALL be masked when its key name contains `password` or `secret` (case-insensitive, at any depth, including inside list items), or when it is the top-level `bounce.sendgrid_key` or the `key` inside `bounce.forwardemail` or `bounce.lettermint`. A masked non-empty value SHALL be replaced with the fixed string `********`. An empty value SHALL be returned empty. No other value SHALL be changed.

#### Scenario: Read settings
- **WHEN** `get_settings` is called
- **THEN** the tool returns the settings, including the SMTP block, with each SMTP `password` shown as `********` and the host, port and username unchanged

#### Scenario: Secret not masked by Listmonk
- **WHEN** Listmonk returns an SMTP `password`, a `bounce.mailboxes` `password` or `security.oidc` `client_secret` in clear text
- **THEN** the tool output shows `********` for it, and the clear-text value does not appear anywhere in the output

#### Scenario: Length is not revealed
- **WHEN** Listmonk returns a password masked as 12 bullets and another as 4 bullets
- **THEN** both appear as `********`

#### Scenario: Secret not set
- **WHEN** the S3 `upload.s3.aws_secret_access_key` is an empty string
- **THEN** the tool output shows it as an empty string, not `********`

#### Scenario: Keys that are not secrets stay visible
- **WHEN** settings contain `upload.s3.aws_access_key_id`, `security.captcha` `hcaptcha.key` and `security.oidc` `client_id`
- **THEN** their values appear unchanged

#### Scenario: Explicit key fields
- **WHEN** settings contain non-empty `bounce.sendgrid_key`, `bounce.forwardemail.key` and `bounce.lettermint.key`
- **THEN** all three appear as `********`

### Requirement: Update a single setting
The `update_setting` tool SHALL change one settings key via `PUT /api/settings/{key}`, sending the raw JSON value as the request body (not wrapped in `{"value": ...}`). Other settings SHALL stay unchanged. Its documentation SHALL say that Listmonk reloads after the change unless a campaign is running. The tool SHALL be exposed only when dangerous tools are allowed, because the reload makes it as disruptive as `reload_app`.

#### Scenario: Change one key
- **WHEN** `update_setting` is called with a key and a new value
- **THEN** only that key changes in Listmonk's settings, and stored secrets elsewhere in the document are not overwritten

#### Scenario: Not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** `update_setting` is not in the tool list

### Requirement: Replace the full settings document
The `update_settings` tool SHALL replace the whole settings document via `PUT /api/settings`. Its documentation SHALL warn that sending back masked bullet values overwrites the real secrets. The tool SHALL be exposed only when dangerous tools are allowed.

#### Scenario: Warning is visible to the client
- **WHEN** dangerous tools are allowed and an MCP client lists tools
- **THEN** the description of `update_settings` contains that warning

#### Scenario: Not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** `update_settings` is not in the tool list

### Requirement: Test SMTP settings without saving them
The `test_smtp_settings` tool SHALL send a test email using the SMTP settings given in the call, via `POST /api/settings/smtp/test`, without saving those settings.

#### Scenario: SMTP server unreachable
- **WHEN** `test_smtp_settings` is called with a host that does not answer
- **THEN** the tool returns an error message containing Listmonk's connection error, and the stored settings are unchanged

### Requirement: Read logs
The `get_logs` tool SHALL return the last `lines` entries (default 100) of Listmonk's server log from `GET /api/logs`, oldest first, one entry per line, under a header stating how many lines are shown and how many Listmonk returned. `lines` SHALL be between 1 and 5000. A value outside that range SHALL be rejected before any request is sent. Log lines SHALL be returned without filtering.

#### Scenario: SMTP failure is visible
- **WHEN** a send has failed at SMTP and `get_logs` is called
- **THEN** the returned log includes the `error sending message` line

#### Scenario: Default tail
- **WHEN** Listmonk holds 4873 log lines and `get_logs` is called with no arguments
- **THEN** the result has a header saying the last 100 of 4873 lines are shown, followed by those 100 lines in their original order, with the newest last

#### Scenario: Fewer lines than requested
- **WHEN** Listmonk holds 30 log lines and `get_logs` is called with `lines=100`
- **THEN** all 30 lines are returned, and the header says 30 of 30

#### Scenario: Out of range
- **WHEN** `get_logs` is called with `lines=0` or `lines=5001`
- **THEN** no request is sent, and the result is a tool error stating the allowed range

### Requirement: Version and dashboard information
The `get_about_info` tool SHALL return version, build and runtime details from `GET /api/about`. The `get_dashboard_counts` and `get_dashboard_charts` tools SHALL return the dashboard counts and chart data.

#### Scenario: Report the Listmonk version
- **WHEN** `get_about_info` is called against Listmonk v6.2.0
- **THEN** the result contains version `v6.2.0` and the build identifier

### Requirement: Garbage-collect subscribers
The `gc_subscribers` tool SHALL delete `orphan` subscribers (on no list) or `blocklisted` subscribers via `DELETE /api/maintenance/subscribers/{type}`, and return how many were deleted. No other type is offered. The tool SHALL be exposed only when dangerous tools are allowed.

#### Scenario: Delete orphan subscribers
- **WHEN** dangerous tools are allowed and `gc_subscribers` is called with `gc_type="orphan"`
- **THEN** subscribers on no list are deleted, and the tool reports the count Listmonk returned

#### Scenario: Not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** `gc_subscribers` is not in the tool list

### Requirement: Garbage-collect analytics and unconfirmed subscriptions before a date
The `gc_campaign_analytics` tool (`all`, `views` or `clicks`) and the `gc_unconfirmed_subscriptions` tool SHALL require an RFC3339 cut-off timestamp and send it to Listmonk as `before_date`. Only data older than the cut-off SHALL be deleted. Both tools SHALL be exposed only when dangerous tools are allowed.

#### Scenario: Delete old view analytics
- **WHEN** `gc_campaign_analytics` is called with `analytics_type="views"` and `before_date="2026-01-01T00:00:00Z"`
- **THEN** the DELETE to `/api/maintenance/analytics/views` carries `before_date=2026-01-01T00:00:00Z`, and only views older than that are removed

#### Scenario: Delete old unconfirmed subscriptions
- **WHEN** `gc_unconfirmed_subscriptions` is called with a cut-off timestamp
- **THEN** the request carries it as `before_date`, and Listmonk returns the number of subscriptions deleted

#### Scenario: Not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** neither `gc_campaign_analytics` nor `gc_unconfirmed_subscriptions` is in the tool list

### Requirement: Reload the app
The `reload_app` tool SHALL make Listmonk reload its settings via `POST /api/admin/reload`. The tool SHALL be exposed only when dangerous tools are allowed.

#### Scenario: Reload the app
- **WHEN** dangerous tools are allowed and `reload_app` is called
- **THEN** Listmonk reloads, and the MCP server's next request succeeds once Listmonk is back

#### Scenario: Not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** `reload_app` is not in the tool list

### Requirement: Health check reports version
The `check_listmonk_health` tool SHALL call `GET /api/health` and `GET /api/about`, and report that Listmonk is reachable along with its version and build. If `/api/about` fails while health succeeds, the tool SHALL still report healthy and say the version is unavailable.

#### Scenario: Healthy instance
- **WHEN** `check_listmonk_health` is called against Listmonk v6.2.0
- **THEN** the result says Listmonk is healthy and contains `v6.2.0` and the build string

#### Scenario: About endpoint not permitted
- **WHEN** `/api/health` succeeds but `/api/about` returns an error
- **THEN** the result still says Listmonk is healthy, and states that the version is unavailable with the reason
