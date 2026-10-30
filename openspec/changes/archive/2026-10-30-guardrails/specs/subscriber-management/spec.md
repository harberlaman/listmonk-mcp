# Spec Delta

## MODIFIED Requirements

### Requirement: Bulk operations by query
The `delete_subscribers_by_query`, `blocklist_subscribers_by_query` and `manage_subscriber_lists_by_query` tools SHALL act on every subscriber matching a Listmonk SQL query expression, optionally limited to given lists. All three tools SHALL be exposed only when dangerous tools are allowed.

#### Scenario: Blocklist by query
- **WHEN** dangerous tools are allowed and `blocklist_subscribers_by_query` is called with `query="subscribers.email LIKE '%@example.com'"`
- **THEN** every matching subscriber is blocklisted and no others

#### Scenario: Invalid query
- **WHEN** dangerous tools are allowed and the query expression is not valid SQL for Listmonk
- **THEN** the tool returns an error message containing Listmonk's error, and no subscriber is changed

#### Scenario: Not available by default
- **WHEN** the server runs with dangerous tools not allowed
- **THEN** none of `delete_subscribers_by_query`, `blocklist_subscribers_by_query` or `manage_subscriber_lists_by_query` is in the tool list, and `blocklist_subscribers` and `manage_subscriber_lists` (by ID) still are
