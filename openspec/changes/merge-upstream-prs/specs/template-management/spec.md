# Spec Delta

## Purpose

Lets MCP clients manage Listmonk email templates (campaign and transactional): update them without losing fields Listmonk requires, select the default template, and preview unsaved template bodies.

## ADDED Requirements

### Requirement: Template update preserves the existing subject
The `update_template` tool SHALL accept an optional `subject`. When `subject` is omitted and the stored template has a non-empty subject, the update request SHALL send the stored subject unchanged, so transactional templates can be updated without restating it.

#### Scenario: Update a tx template body without passing subject
- **WHEN** `update_template` is called with a template ID of a `tx` template whose stored subject is "Message from IT", and only `body` is given
- **THEN** the PUT to `/api/templates/{id}` includes `subject: "Message from IT"` and the new body
- **AND** Listmonk does not reject the request for a missing subject

#### Scenario: Update a template with an explicit subject
- **WHEN** `update_template` is called with `subject` set
- **THEN** the PUT body carries the given subject, replacing the stored one

#### Scenario: Update a campaign template that has no subject
- **WHEN** `update_template` is called for a template whose stored subject is empty and no `subject` is passed
- **THEN** the PUT body contains no `subject` field

### Requirement: Set the default template
The `set_default_template` tool SHALL mark the given template as the default for its type by calling `PUT /api/templates/{id}/default`.

#### Scenario: Make a template the default
- **WHEN** `set_default_template` is called with an existing template ID
- **THEN** Listmonk reports that template as the default, and the tool returns a confirmation naming the template ID

### Requirement: Preview an unsaved template body
The `preview_template_body` tool SHALL render a template body that has not been saved, for a given template type (default `campaign`), using `POST /api/templates/preview` with the form fields `body` and `template_type`, and return the rendered output.

#### Scenario: Preview a campaign template body
- **WHEN** `preview_template_body` is called with a body that contains `{{ template "content" . }}`
- **THEN** the tool returns the HTML Listmonk rendered

#### Scenario: Preview fails on a template error
- **WHEN** the body has a template syntax error
- **THEN** the tool returns an error message containing Listmonk's error text instead of rendered HTML
