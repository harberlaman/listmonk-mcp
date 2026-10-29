# subscriber-import Specification

## Purpose

Lets MCP clients start a bulk subscriber import from a CSV or ZIP file, follow its progress and logs, and stop it.

## Requirements

### Requirement: Start an import from a server-local file
The `import_subscribers` tool SHALL upload a `.csv` or `.zip` file, found at a path on the machine running the MCP server, to `POST /api/import/subscribers` with mode (`subscribe` or `blocklist`), target lists, delimiter, overwrite flag and subscription status.

#### Scenario: Import a CSV
- **WHEN** `import_subscribers` is called with the path of an existing CSV and a list ID
- **THEN** Listmonk starts an import, and the tool returns its status and total row count

#### Scenario: File does not exist on the server
- **WHEN** the path does not exist on the machine running the MCP server
- **THEN** no request is sent to Listmonk, and the tool returns an error saying the file was not found

### Requirement: Follow and stop an import
The `get_import_status` tool SHALL return the current or last import's status. The `get_import_logs` tool SHALL return its log. The `stop_import` tool SHALL stop a running import.

#### Scenario: Check a running import
- **WHEN** `get_import_status` is called while an import is running
- **THEN** the tool returns the import's status and progress counts

#### Scenario: Stop an import
- **WHEN** `stop_import` is called while an import is running
- **THEN** the import stops, and `get_import_status` then reports it as stopped
