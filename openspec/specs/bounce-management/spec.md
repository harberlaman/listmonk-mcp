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
The `delete_bounce` tool SHALL delete one bounce. The `delete_subscriber_bounces` tool SHALL delete all bounces of one subscriber. The `delete_bounces` tool SHALL delete the given bounce IDs, or every bounce when no IDs are given.

#### Scenario: Delete specific bounces
- **WHEN** `delete_bounces` is called with two bounce IDs
- **THEN** only those two bounces are deleted

#### Scenario: Delete all bounces
- **WHEN** `delete_bounces` is called with no IDs or an empty list
- **THEN** every bounce record is deleted, and the tool says that ALL bounces were deleted

### Requirement: Blocklist all bounced subscribers
The `blocklist_bounced_subscribers` tool SHALL blocklist every subscriber that has at least one bounce record, via `PUT /api/bounces/blocklist`. It SHALL NOT accept bounce IDs, because Listmonk can't limit this operation to chosen bounces. Its documentation SHALL say that it affects all bounced subscribers.

#### Scenario: Blocklist everyone who bounced
- **WHEN** `blocklist_bounced_subscribers` is called
- **THEN** every subscriber with a bounce record is blocklisted, and subscribers without bounces are unchanged

#### Scenario: Description warns about scope
- **WHEN** an MCP client lists tools
- **THEN** the description of `blocklist_bounced_subscribers` says that it blocklists ALL bounced subscribers, and the tool has no bounce-ID parameter
