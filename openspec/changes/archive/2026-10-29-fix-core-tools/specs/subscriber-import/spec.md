# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Start an import from a server-local file`
- TO: `### Requirement: Start an import from uploaded content or a local file`

## MODIFIED Requirements

### Requirement: Start an import from uploaded content or a local file
The `import_subscribers` tool SHALL take either `content_base64` + `filename`, or a `file_path` on the machine running the server (exactly one). The file must be `.csv` or `.zip` and at most 10 MB. The tool uploads it to `POST /api/import/subscribers` with mode (`subscribe` or `blocklist`), target lists, delimiter, overwrite flag and subscription status, and returns Listmonk's response.

#### Scenario: Import uploaded CSV content
- **WHEN** `import_subscribers` is called with the base64 of a CSV, `filename="subs.csv"` and a list ID
- **THEN** Listmonk starts an import, and the result is Listmonk's import status response

#### Scenario: Import a CSV
- **WHEN** `import_subscribers` is called with the path of an existing CSV and a list ID
- **THEN** Listmonk starts an import, and the result is Listmonk's import status response

#### Scenario: File does not exist on the server
- **WHEN** the path does not exist on the machine running the MCP server
- **THEN** no request is sent to Listmonk, and the tool returns an MCP error saying the file was not found

#### Scenario: Both or neither source given
- **WHEN** both `content_base64` and `file_path` are given, or neither is
- **THEN** no request is sent, and the tool returns an MCP error

#### Scenario: Wrong type or too large
- **WHEN** the file isn't `.csv` or `.zip`, or is larger than 10 MB
- **THEN** no request is sent, and the tool returns an MCP error stating the rule
