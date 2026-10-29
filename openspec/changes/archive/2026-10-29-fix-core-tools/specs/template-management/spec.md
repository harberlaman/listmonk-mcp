# Spec Delta

## ADDED Requirements

### Requirement: Create a template with a subject
The `create_template` tool SHALL accept `name`, `body`, `type` (`campaign`, `campaign_visual` or `tx`, default `campaign`), `subject` and `is_default`, and create the template via `POST /api/templates`. A `tx` template without a non-empty `subject` SHALL be rejected before any request is sent. The template type can't be changed later, and the tool documentation SHALL say so.

#### Scenario: Create a tx template
- **WHEN** `create_template` is called with `type="tx"`, `subject="Message from IT"` and a body
- **THEN** the POST body carries `type: "tx"` and that subject, and the result is Listmonk's response with the new template's `id`

#### Scenario: tx template without subject
- **WHEN** `create_template` is called with `type="tx"` and no subject
- **THEN** no request is sent, and the tool returns an MCP error saying transactional templates need a subject

## MODIFIED Requirements

### Requirement: Set the default template
The `set_default_template` tool SHALL mark the given template as the default for its type by calling `PUT /api/templates/{id}/default`.

#### Scenario: Make a template the default
- **WHEN** `set_default_template` is called with an existing template ID
- **THEN** Listmonk reports that template as the default, and the tool returns Listmonk's response
