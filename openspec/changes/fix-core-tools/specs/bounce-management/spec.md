# Spec Delta

## MODIFIED Requirements

### Requirement: Delete bounces
The `delete_bounce` tool SHALL delete one bounce. The `delete_subscriber_bounces` tool SHALL delete all bounces of one subscriber. The `delete_bounces` tool SHALL delete the given bounce IDs, or every bounce when no IDs are given, and its description SHALL say that giving no IDs deletes ALL bounces.

#### Scenario: Delete specific bounces
- **WHEN** `delete_bounces` is called with two bounce IDs
- **THEN** only those two bounces are deleted

#### Scenario: Delete all bounces
- **WHEN** `delete_bounces` is called with no IDs or an empty list
- **THEN** every bounce record is deleted, and the tool returns Listmonk's response

#### Scenario: Description warns about deleting all
- **WHEN** an MCP client lists tools
- **THEN** the description of `delete_bounces` says that no IDs means ALL bounces are deleted
