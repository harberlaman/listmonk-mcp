# Spec Delta

## Purpose

Lets MCP clients, including remote ones that share no filesystem with the server, upload images to Listmonk's media library and get back the URL that templates and campaigns reference. It covers only what Listmonk v6.2.0 supports: upload, list and delete.

## ADDED Requirements

### Requirement: Upload media from content
The `upload_media` tool SHALL accept `content_base64` and `filename`, upload the decoded bytes to `POST /api/media` as a `file` part, and return Listmonk's response, which includes the media `url`.

#### Scenario: Upload a PNG
- **WHEN** `upload_media` is called with the base64 of a PNG and `filename="logo.png"`
- **THEN** Listmonk stores the file, and the result includes the media record with its `url`

#### Scenario: Invalid base64
- **WHEN** `content_base64` isn't valid base64
- **THEN** no request is sent, and the tool returns an MCP error

### Requirement: Upload media from a server-local path
The `upload_media_file` tool SHALL keep accepting a `file_path` on the machine running the server, as a fallback for local stdio use, with the same checks and response as `upload_media`.

#### Scenario: Path does not exist
- **WHEN** `upload_media_file` is called with a path that doesn't exist on the server
- **THEN** no request is sent, and the tool returns an MCP error saying the file was not found, not a `TypeError`

### Requirement: Allowed types and size
Both upload tools SHALL accept only `.png`, `.jpg`, `.jpeg`, `.gif` and `.webp` files of at most 5 MB (after decoding). Anything else SHALL be rejected before any request is sent.

#### Scenario: Disallowed type
- **WHEN** `upload_media` is called with `filename="script.svg"` or `filename="notes.txt"`
- **THEN** no request is sent, and the tool returns an MCP error listing the allowed types

#### Scenario: Too large
- **WHEN** the decoded content is larger than 5 MB
- **THEN** no request is sent, and the tool returns an MCP error stating the 5 MB limit

### Requirement: No media rename or title
The server SHALL NOT offer a tool to rename media or set a media title, and the upload tools SHALL NOT take a `title`, because Listmonk v6.2.0 stores no title and has no media update endpoint.

#### Scenario: No rename tool
- **WHEN** an MCP client lists tools
- **THEN** there is no `rename_media` tool, and neither `upload_media` nor `upload_media_file` has a `title` parameter
