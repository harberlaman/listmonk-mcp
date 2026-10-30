# Spec Delta

## MODIFIED Requirements

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
