# campaign-management Specification

## Purpose

Lets MCP clients run a Listmonk campaign through its lifecycle beyond create and send: test sends to chosen subscribers, status changes, archive publishing, deletion, and live and historical analytics.

## Requirements

### Requirement: Test-send a campaign to existing subscribers
The `test_campaign` tool SHALL send a test of a saved campaign to a list of email addresses via `POST /api/campaigns/{id}/test`, sending the saved campaign's full payload (name, subject, lists, from, body, altbody, content type, messenger, type, tags, template, headers) with the recipients. Campaign list members SHALL NOT receive it.

#### Scenario: Test send to an existing subscriber
- **WHEN** `test_campaign` is called with a campaign ID and `["test@example.com"]`, and that address is a subscriber
- **THEN** Listmonk queues one test message to that address, and the campaign's status and stats do not change

#### Scenario: Recipient is not a subscriber
- **WHEN** a recipient address does not belong to any subscriber
- **THEN** Listmonk sends nothing to that address. The tool's documentation states that recipients must already be subscribers.

### Requirement: Change campaign status
The `change_campaign_status` tool SHALL set a campaign's status (`draft`, `scheduled`, `running`, `paused` or `cancelled`) via `PUT /api/campaigns/{id}/status`.

#### Scenario: Pause a running campaign
- **WHEN** `change_campaign_status` is called with `status="paused"` for a running campaign
- **THEN** the campaign's status becomes `paused`

#### Scenario: Invalid status transition
- **WHEN** Listmonk rejects the transition
- **THEN** the tool returns an error message containing Listmonk's reason

### Requirement: Publish or unpublish a campaign on the public archive
The `archive_campaign` tool SHALL turn a campaign's public archive listing on or off, with optional archive template, metadata and slug, via `PUT /api/campaigns/{id}/archive`.

#### Scenario: Archive a campaign
- **WHEN** `archive_campaign` is called with `archive=true`
- **THEN** the campaign is listed on Listmonk's public archive

### Requirement: Delete campaigns
The `delete_campaign` tool SHALL permanently delete one campaign via `DELETE /api/campaigns/{id}`. The `delete_campaigns` tool SHALL delete several campaigns by ID in one call via `DELETE /api/campaigns`. `delete_campaigns` SHALL be exposed only when dangerous tools are allowed. `delete_campaign` SHALL always be exposed.

#### Scenario: Delete one campaign
- **WHEN** `delete_campaign` is called with an existing campaign ID
- **THEN** that campaign no longer exists in Listmonk

#### Scenario: Bulk delete
- **WHEN** dangerous tools are allowed and `delete_campaigns` is called with several IDs
- **THEN** all of those campaigns are deleted and no others

#### Scenario: Bulk delete not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** `delete_campaigns` is not in the tool list, and `delete_campaign` is

### Requirement: Campaign statistics and analytics
The `get_running_campaign_stats` tool SHALL return live stats for running campaigns from `GET /api/campaigns/running/stats`. The `get_campaign_analytics` tool SHALL return `views`, `clicks`, `links` or `bounces` analytics for given campaign IDs over a required `from_date`/`to_date` range, from `GET /api/campaigns/analytics/{type}` (sent as `id`, `from` and `to` query parameters).

#### Scenario: No campaign running
- **WHEN** `get_running_campaign_stats` is called while no campaign is running
- **THEN** the tool returns an empty result rather than an error

#### Scenario: Click analytics for one campaign
- **WHEN** `get_campaign_analytics` is called with `analytics_type="clicks"`, one campaign ID, `from_date="2026-10-01"` and `to_date="2026-10-28"`
- **THEN** the tool returns Listmonk's click analytics data for that campaign
