# subscriber-management Specification

## Purpose

Lets MCP clients manage Listmonk subscribers individually, in bulk by ID, and in bulk by query: list membership, status, blocklisting, opt-in and activity history.

## Requirements

### Requirement: Patch a subscriber's fields
The `patch_subscriber` tool SHALL send only the fields given (`email`, `name`, `status`, `attributes`, `lists`, `preconfirm`) to `PATCH /api/subscribers/{id}`. Fields that aren't given SHALL keep their stored values. When `lists` is given, it SHALL replace the subscriber's list subscriptions. When it isn't, the subscriptions SHALL stay unchanged.

#### Scenario: Change only the status
- **WHEN** `patch_subscriber` is called with only `status="disabled"`
- **THEN** the PATCH body is `{"status": "disabled"}`, and the subscriber's name, email, attributes and lists are unchanged

#### Scenario: Replace list subscriptions
- **WHEN** `patch_subscriber` is called with `lists=[1, 4]`
- **THEN** the PATCH body carries `lists: [1, 4]`, and afterwards the subscriber is subscribed to exactly lists 1 and 4

#### Scenario: Nothing to change
- **WHEN** `patch_subscriber` is called with no fields besides the subscriber ID
- **THEN** no request is sent, and the tool returns an error saying at least one field is required

### Requirement: Send a fresh opt-in email
The `subscriber_send_optin` tool SHALL trigger a new double-opt-in confirmation email for a subscriber via `POST /api/subscribers/{id}/optin`.

#### Scenario: Resend opt-in
- **WHEN** `subscriber_send_optin` is called for a subscriber with unconfirmed double-opt-in subscriptions
- **THEN** Listmonk queues an opt-in email to that subscriber

### Requirement: Blocklist subscribers by ID
The `blocklist_subscriber` tool SHALL blocklist one subscriber. The `blocklist_subscribers` tool SHALL blocklist several subscribers by ID in one call. Blocklisted subscribers SHALL be unsubscribed from all lists.

#### Scenario: Blocklist one subscriber
- **WHEN** `blocklist_subscriber` is called with a subscriber ID
- **THEN** that subscriber's status is `blocklisted`

### Requirement: Bulk list membership by ID
The `manage_subscriber_lists` tool SHALL `add`, `remove` or `unsubscribe` several subscribers for the given lists in one call, with an optional subscription status for `add`, via `PUT /api/subscribers/lists`.

#### Scenario: Add three subscribers to a list
- **WHEN** `manage_subscriber_lists` is called with three subscriber IDs, one list ID and `action="add"`
- **THEN** all three subscribers are members of that list

### Requirement: Bulk operations by query
The `delete_subscribers_by_query`, `blocklist_subscribers_by_query` and `manage_subscriber_lists_by_query` tools SHALL act on every subscriber matching a Listmonk SQL query expression, optionally limited to given lists.

#### Scenario: Blocklist by query
- **WHEN** `blocklist_subscribers_by_query` is called with `query="subscribers.email LIKE '%@example.com'"`
- **THEN** every matching subscriber is blocklisted and no others

#### Scenario: Invalid query
- **WHEN** the query expression is not valid SQL for Listmonk
- **THEN** the tool returns an error message containing Listmonk's error, and no subscriber is changed

### Requirement: Subscriber activity history
The `get_subscriber_activity` tool SHALL return a subscriber's campaign views (campaign, view count, last viewed) and link clicks (URL, campaign, click count, last clicked) from `GET /api/subscribers/{id}/activity`.

#### Scenario: Read activity
- **WHEN** `get_subscriber_activity` is called for a subscriber who viewed one campaign and clicked one link
- **THEN** the tool lists that campaign with its view count and that link with its click count

#### Scenario: No activity
- **WHEN** the subscriber has no views or clicks
- **THEN** the tool says no activity is recorded
