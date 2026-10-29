# Spec Delta

## ADDED Requirements

### Requirement: Health check reports version
The `check_listmonk_health` tool SHALL call `GET /api/health` and `GET /api/about`, and report that Listmonk is reachable along with its version and build. If `/api/about` fails while health succeeds, the tool SHALL still report healthy and say the version is unavailable.

#### Scenario: Healthy instance
- **WHEN** `check_listmonk_health` is called against Listmonk v6.2.0
- **THEN** the result says Listmonk is healthy and contains `v6.2.0` and the build string

#### Scenario: About endpoint not permitted
- **WHEN** `/api/health` succeeds but `/api/about` returns an error
- **THEN** the result still says Listmonk is healthy, and states that the version is unavailable with the reason
