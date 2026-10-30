# Spec Delta

## ADDED Requirements

### Requirement: Dangerous tools are exposed only when allowed
The server SHALL read a boolean setting `LISTMONK_MCP_ALLOW_DANGEROUS` (default `false`) before it starts serving. When it is false, the 12 dangerous tools SHALL NOT be exposed: clients SHALL NOT see them in the tool list, and a call to one by name SHALL fail as an unknown tool. When it is true, all 71 tools SHALL be exposed. Every other tool and every resource SHALL be exposed in both cases.

#### Scenario: Flag unset
- **WHEN** the server starts without `LISTMONK_MCP_ALLOW_DANGEROUS` and an MCP client lists tools
- **THEN** it sees 59 tools, and none of `update_settings`, `update_setting`, `reload_app`, `delete_subscribers_by_query`, `blocklist_subscribers_by_query`, `manage_subscriber_lists_by_query`, `blocklist_bounced_subscribers`, `delete_all_bounces`, `delete_campaigns`, `gc_subscribers`, `gc_campaign_analytics` or `gc_unconfirmed_subscriptions`

#### Scenario: Calling a gated tool while the flag is off
- **WHEN** the flag is off and a client calls `reload_app` by name
- **THEN** the call fails as an unknown tool, and no request is sent to Listmonk

#### Scenario: Flag on
- **WHEN** the server starts with `LISTMONK_MCP_ALLOW_DANGEROUS=true` and a client lists tools
- **THEN** it sees all 71 tools, including the 12 dangerous ones

#### Scenario: Resources unaffected
- **WHEN** the flag is off and a client lists resources and resource templates
- **THEN** it still sees 5 resources and 8 resource templates

#### Scenario: Invalid flag value
- **WHEN** `LISTMONK_MCP_ALLOW_DANGEROUS` is set to a value that is not a boolean (for example `maybe`)
- **THEN** the server fails to start with a configuration error, and does not fall back to either setting

### Requirement: Startup log reports the dangerous-tools setting
At startup the server SHALL write one INFO log line saying whether dangerous tools are enabled and, when they are not, how many tools are hidden.

#### Scenario: Flag off
- **WHEN** the server starts with the flag off
- **THEN** the server log contains one INFO line saying that dangerous tools are disabled and that 12 tools are hidden

#### Scenario: Flag on
- **WHEN** the server starts with the flag on
- **THEN** the server log contains one INFO line saying that dangerous tools are enabled

### Requirement: Tool arguments are not written to the server log
The server SHALL NOT write tool argument values to its log, for successful or failed calls. A failure log entry SHALL name the tool and the error type and message only.

#### Scenario: Failed call with a secret argument
- **WHEN** `test_smtp_settings` is called with a settings object whose `password` is a known value, and Listmonk rejects it
- **THEN** the call fails as a tool error, and no server log record contains that password value
