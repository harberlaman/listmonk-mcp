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
