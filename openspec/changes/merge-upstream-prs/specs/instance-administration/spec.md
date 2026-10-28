# Spec Delta

## Purpose

Lets MCP clients inspect and administer the Listmonk instance itself: settings, SMTP testing, logs, version and build info, dashboard figures, and maintenance (garbage collection and reload).

## ADDED Requirements

### Requirement: Read settings
The `get_settings` tool SHALL return the full settings document from `GET /api/settings`. This change relies on Listmonk's own masking of secret values. Masking by key name is not part of this change.

#### Scenario: Read settings
- **WHEN** `get_settings` is called
- **THEN** the tool returns the settings, including the SMTP block, with password fields as Listmonk returned them (masked with bullets)

### Requirement: Update a single setting
The `update_setting` tool SHALL change one settings key via `PUT /api/settings/{key}`, sending the raw JSON value as the request body (not wrapped in `{"value": ...}`). Other settings SHALL stay unchanged.

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

### Requirement: Maintenance operations
The `gc_subscribers` (`orphan`, `blocklisted` or `unconfirmed`), `gc_campaign_analytics` (by analytics type) and `gc_unconfirmed_subscriptions` (older than a timestamp) tools SHALL delete the matching data. The `reload_app` tool SHALL restart Listmonk in place to reload its settings.

#### Scenario: Delete orphan subscribers
- **WHEN** `gc_subscribers` is called with `gc_type="orphan"`
- **THEN** subscribers on no list are deleted, and the tool reports success

#### Scenario: Reload the app
- **WHEN** `reload_app` is called
- **THEN** Listmonk reloads, and the MCP server's next request succeeds once Listmonk is back
