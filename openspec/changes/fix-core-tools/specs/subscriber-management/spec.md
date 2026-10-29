# Spec Delta

## ADDED Requirements

### Requirement: List subscribers as records
The `get_list_subscribers_tool` tool and the `listmonk://subscribers` and `listmonk://list/{list_id}/subscribers` resources SHALL return the subscribers themselves, not only a count. Each entry SHALL show id, email, name, status, lists (with subscription status) and attributes. The tool SHALL accept `page` and `per_page`, and every output SHALL state the page, the page size and the total number of subscribers.

#### Scenario: Subscribers of a list
- **WHEN** `get_list_subscribers_tool` is called for list 1, which has 3 subscribers
- **THEN** the result lists all 3 with their emails and statuses, and each one's lists with subscription status (for example `Default (ID: 1, confirmed)`), and states "page 1", the page size and "3 total"

#### Scenario: Paging
- **WHEN** `get_list_subscribers_tool` is called with `page=2` and `per_page=2` for a list of 3
- **THEN** the result shows only the third subscriber and states page 2 of a total of 3

#### Scenario: Empty list
- **WHEN** the list has no subscribers
- **THEN** the result says the list has no subscribers
