# bounce-management Specification

## Purpose

Lets MCP clients inspect and clean up bounce records Listmonk has recorded, and blocklist the subscribers behind them.

## Requirements

### Requirement: List and read bounces
The `list_bounces` tool SHALL return bounce records with pagination (`page`, `per_page`) and optional filters by `campaign_id` and `source`. The `get_bounce` tool SHALL return one bounce by ID. The `get_subscriber_bounces` tool SHALL return all bounces for one subscriber.

#### Scenario: No bounces recorded
- **WHEN** `list_bounces` is called and Listmonk has no bounces
- **THEN** the tool returns "No bounces found."

#### Scenario: Bounces for one campaign
- **WHEN** `list_bounces` is called with a `campaign_id`
- **THEN** only bounces for that campaign are returned, with the total count

### Requirement: Delete bounces
The `delete_bounce` tool SHALL delete one bounce. The `delete_subscriber_bounces` tool SHALL delete all bounces of one subscriber. The `delete_bounces` tool SHALL delete the given bounce IDs and SHALL require at least one ID. A call with no IDs or an empty list SHALL be rejected before any request is sent. Its description SHALL say that it never deletes all bounces.

#### Scenario: Delete specific bounces
- **WHEN** `delete_bounces` is called with two bounce IDs
- **THEN** only those two bounces are deleted, and the tool returns Listmonk's response

#### Scenario: Delete all bounces
- **WHEN** `delete_bounces` is called with no IDs or an empty list
- **THEN** no request is sent, the result is a tool error saying at least one bounce ID is required, and no bounce is deleted

#### Scenario: Description warns about deleting all
- **WHEN** an MCP client lists tools
- **THEN** the description of `delete_bounces` says that at least one ID is required and that it never deletes all bounces

### Requirement: Blocklist all bounced subscribers
The `blocklist_bounced_subscribers` tool SHALL blocklist every subscriber that has at least one bounce record, via `PUT /api/bounces/blocklist`. It SHALL NOT accept bounce IDs, because Listmonk can't limit this operation to chosen bounces. Its documentation SHALL say that it affects all bounced subscribers. The tool SHALL be exposed only when dangerous tools are allowed.

#### Scenario: Blocklist everyone who bounced
- **WHEN** dangerous tools are allowed and `blocklist_bounced_subscribers` is called
- **THEN** every subscriber with a bounce record is blocklisted, and subscribers without bounces are unchanged

#### Scenario: Description warns about scope
- **WHEN** dangerous tools are allowed and an MCP client lists tools
- **THEN** the description of `blocklist_bounced_subscribers` says that it blocklists ALL bounced subscribers, and the tool has no bounce-ID parameter

#### Scenario: Not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** `blocklist_bounced_subscribers` is not in the tool list

### Requirement: Delete all bounces
The `delete_all_bounces` tool SHALL delete every bounce record via `DELETE /api/bounces` with `all=true`, take no parameters, and return Listmonk's response. Its description SHALL say that it deletes ALL bounces. The tool SHALL be exposed only when dangerous tools are allowed.

#### Scenario: Delete every bounce
- **WHEN** dangerous tools are allowed and `delete_all_bounces` is called
- **THEN** a DELETE to `/api/bounces` with `all=true` is sent, and the tool returns Listmonk's response

#### Scenario: Not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** `delete_all_bounces` is not in the tool list
