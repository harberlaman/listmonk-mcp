# instance-administration Specification

## Purpose

Lets MCP clients inspect and administer the Listmonk instance itself: settings, SMTP testing, logs, version and build info, dashboard figures, and maintenance (garbage collection and reload).

## Requirements

### Requirement: Read settings
The `get_settings` tool SHALL return the full settings document from `GET /api/settings`. This change relies on Listmonk's own masking of secret values. Masking by key name is not part of this change.

#### Scenario: Read settings
- **WHEN** `get_settings` is called
- **THEN** the tool returns the settings, including the SMTP block, with password fields as Listmonk returned them (masked with bullets)

### Requirement: Update a single setting
The `update_setting` tool SHALL change one settings key via `PUT /api/settings/{key}`, sending the raw JSON value as the request body (not wrapped in `{"value": ...}`). Other settings SHALL stay unchanged. Its documentation SHALL say that Listmonk reloads after the change unless a campaign is running.

#### Scenario: Change one key
- **WHEN** `update_setting` is called with a key and a new value
- **THEN** only that key changes in Listmonk's settings, and stored secrets elsewhere in the document are not overwritten

### Requirement: Replace the full settings document
The `update_settings` tool SHALL replace the whole settings document via `PUT /api/settings`. Its documentation SHALL warn that sending back masked bullet values overwrites the real secrets.

#### Scenario: Warning is visible to the client
- **WHEN** an MCP client lists tools
- **THEN** the description of `update_settings` contains that warning

### Requirement: Test SMTP settings without saving them
The `test_smtp_settings` tool SHALL send a test email using the SMTP settings given in the call, via `POST /api/settings/smtp/test`, without saving those settings.

#### Scenario: SMTP server unreachable
- **WHEN** `test_smtp_settings` is called with a host that does not answer
- **THEN** the tool returns an error message containing Listmonk's connection error, and the stored settings are unchanged

### Requirement: Read logs
The `get_logs` tool SHALL return Listmonk's recent server log lines from `GET /api/logs`.

#### Scenario: SMTP failure is visible
- **WHEN** a send has failed at SMTP and `get_logs` is called
- **THEN** the returned log includes the `error sending message` line

### Requirement: Version and dashboard information
The `get_about_info` tool SHALL return version, build and runtime details from `GET /api/about`. The `get_dashboard_counts` and `get_dashboard_charts` tools SHALL return the dashboard counts and chart data.

#### Scenario: Report the Listmonk version
- **WHEN** `get_about_info` is called against Listmonk v6.2.0
- **THEN** the result contains version `v6.2.0` and the build identifier

### Requirement: Garbage-collect subscribers
The `gc_subscribers` tool SHALL delete `orphan` subscribers (on no list) or `blocklisted` subscribers via `DELETE /api/maintenance/subscribers/{type}`, and return how many were deleted. No other type is offered.

#### Scenario: Delete orphan subscribers
- **WHEN** `gc_subscribers` is called with `gc_type="orphan"`
- **THEN** subscribers on no list are deleted, and the tool reports the count Listmonk returned

### Requirement: Garbage-collect analytics and unconfirmed subscriptions before a date
The `gc_campaign_analytics` tool (`all`, `views` or `clicks`) and the `gc_unconfirmed_subscriptions` tool SHALL require an RFC3339 cut-off timestamp and send it to Listmonk as `before_date`. Only data older than the cut-off SHALL be deleted.

#### Scenario: Delete old view analytics
- **WHEN** `gc_campaign_analytics` is called with `analytics_type="views"` and `before_date="2026-01-01T00:00:00Z"`
- **THEN** the DELETE to `/api/maintenance/analytics/views` carries `before_date=2026-01-01T00:00:00Z`, and only views older than that are removed

#### Scenario: Delete old unconfirmed subscriptions
- **WHEN** `gc_unconfirmed_subscriptions` is called with a cut-off timestamp
- **THEN** the request carries it as `before_date`, and Listmonk returns the number of subscriptions deleted

### Requirement: Reload the app
The `reload_app` tool SHALL make Listmonk reload its settings via `POST /api/admin/reload`.

#### Scenario: Reload the app
- **WHEN** `reload_app` is called
- **THEN** Listmonk reloads, and the MCP server's next request succeeds once Listmonk is back
