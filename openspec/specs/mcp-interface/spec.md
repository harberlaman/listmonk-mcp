# mcp-interface Specification

## Purpose

Defines how the Listmonk MCP server presents itself to MCP clients: how failures are signaled, what write and read tools return, and which resources the running server exposes.

## Requirements

### Requirement: Failures are MCP tool errors
Every tool failure SHALL be returned as an MCP tool error (`isError: true`) whose text names the error type and gives Listmonk's message or the local reason. This covers Listmonk error responses, network failures, local validation and unexpected exceptions. No tool SHALL return an error as a normal (non-error) result.

#### Scenario: Listmonk rejects a request
- **WHEN** a tool's request gets a 4xx response from Listmonk with a `message`
- **THEN** the tool call result has `isError: true`, and its text contains that message

#### Scenario: Local validation fails
- **WHEN** a tool rejects its input before calling Listmonk (for example, a non-RFC3339 `before_date`)
- **THEN** no request is sent, and the result has `isError: true` with the reason

#### Scenario: Unexpected exception
- **WHEN** a tool raises an exception that isn't a Listmonk or validation error
- **THEN** the result has `isError: true` with a one-line message, and no Python traceback is included

### Requirement: Errors without an HTTP status are handled
An error that has no HTTP status code (for example, a local file not found or a connection failure) SHALL be reported as an MCP tool error with its message, and SHALL NOT cause a secondary exception while it is mapped.

#### Scenario: Error with no status code
- **WHEN** a tool fails with an error that carries no HTTP status
- **THEN** the result has `isError: true` with the original message, not a `TypeError` about comparing `int` and `None`

### Requirement: Write tools return Listmonk's response
Every tool that changes state in Listmonk (any non-GET request, except `preview_template_body`) SHALL return Listmonk's JSON response body, serialized as JSON text, instead of a made-up success message.

#### Scenario: Queued transactional send
- **WHEN** `send_transactional_email` succeeds
- **THEN** the result text is Listmonk's response (`{"data": true}`), and no wording claims the message was delivered

#### Scenario: Create returns the new record
- **WHEN** `create_mailing_list` succeeds
- **THEN** the result text is the JSON Listmonk returned, including the new list's `id`

### Requirement: Read tools return formatted text
Tools that only read from Listmonk SHALL keep returning human-readable formatted text.

#### Scenario: Read tool output
- **WHEN** `get_templates` succeeds
- **THEN** the result is formatted text listing the templates, not raw JSON

### Requirement: Resources are served by the running server
The server started by `listmonk-mcp` SHALL expose every `listmonk://` resource and resource template defined in the code, alongside all tools.

#### Scenario: Resources listed
- **WHEN** an MCP client lists resources and resource templates on a running server
- **THEN** it sees 5 resources (including `listmonk://subscribers`, `listmonk://lists`, `listmonk://campaigns`, `listmonk://templates` and `listmonk://media`) and 8 resource templates (including `listmonk://subscriber/{subscriber_id}` and `listmonk://list/{list_id}/subscribers`)

#### Scenario: Resource read
- **WHEN** a client reads `listmonk://lists`
- **THEN** it receives the formatted list of mailing lists from Listmonk

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
