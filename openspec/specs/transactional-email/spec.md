# transactional-email Specification

## Purpose

Lets MCP clients send transactional messages through a Listmonk `tx` template to subscribers or external addresses, with per-message data, headers, overrides and attachments, while being clear that Listmonk only queues the message.

## Requirements

### Requirement: Exactly one recipient selector
The `send_transactional_email` tool SHALL require `template_id` and exactly one of `subscriber_email`, `subscriber_id`, `subscriber_emails` or `subscriber_ids`. A single email or ID SHALL be sent to Listmonk as a one-item `subscriber_emails` or `subscriber_ids` list.

#### Scenario: Send to one subscriber by ID
- **WHEN** `send_transactional_email` is called with `template_id=5` and `subscriber_id=3`
- **THEN** the POST to `/api/tx` carries `template_id: 5` and `subscriber_ids: [3]`

#### Scenario: Two selectors given
- **WHEN** both `subscriber_email` and `subscriber_ids` are given
- **THEN** no request is sent, and the tool returns an MCP error saying exactly one recipient selector is required

#### Scenario: No selector given
- **WHEN** none of the four selectors is given
- **THEN** no request is sent, and the tool returns an MCP error

### Requirement: Subscriber mode
The tool SHALL accept `subscriber_mode` of `default`, `fallback` or `external`, and pass it to Listmonk. In `fallback` and `external` modes, the tool SHALL accept only email selectors.

#### Scenario: External address
- **WHEN** the tool is called with `subscriber_mode="external"` and `subscriber_email="someone@example.com"`, an address that isn't a subscriber
- **THEN** the request carries `subscriber_mode: "external"` and `subscriber_emails: ["someone@example.com"]`, and Listmonk queues the message

#### Scenario: IDs in external mode
- **WHEN** `subscriber_mode="external"` is combined with `subscriber_id`
- **THEN** no request is sent, and the tool returns an MCP error saying external and fallback modes take emails only

### Requirement: Message overrides and data
The tool SHALL pass through `data` (any JSON object, available as `{{ .Tx.Data.* }}`), `subject`, `from_email`, `headers` (a list of single-pair `{name: value}` objects), `content_type` (`html`, `markdown` or `plain`, default `html`), `altbody` and `messenger`. Optional fields that aren't given SHALL be left out of the request.

#### Scenario: Headers and overrides
- **WHEN** the tool is called with `subject="Message from IT"`, `from_email="IT <it@example.com>"`, `headers=[{"X-Training-ID": "TEST-01"}]` and `data={"content": "<p>Hi</p>"}`
- **THEN** the request body carries those four fields unchanged

#### Scenario: Optional fields omitted
- **WHEN** only `template_id` and a recipient are given
- **THEN** the request body contains no `subject`, `from_email`, `headers`, `altbody` or `messenger` keys, and `content_type` is `html`

### Requirement: Attachments
The tool SHALL accept `attachments` as a list of `{filename, content_base64}` objects (optional `content_type`). When attachments are given, the request SHALL be sent as `multipart/form-data`, with the message JSON in a `data` part and each attachment as a `file` part. Invalid base64 SHALL be rejected before any request is sent.

#### Scenario: Send with one attachment
- **WHEN** the tool is called with one attachment `{filename: "guide.pdf", content_base64: <valid>}`
- **THEN** the POST to `/api/tx` is multipart, with a `data` part holding the message JSON and a `file` part named `guide.pdf` holding the decoded bytes

#### Scenario: Bad base64
- **WHEN** an attachment's `content_base64` isn't valid base64
- **THEN** no request is sent, and the tool returns an MCP error naming that attachment

### Requirement: Queued, not delivered
The tool SHALL return Listmonk's response as-is, and its description SHALL state that success means the message was queued, and that delivery failures appear only in Listmonk's logs.

#### Scenario: Description warns about queuing
- **WHEN** an MCP client lists tools
- **THEN** the description of `send_transactional_email` says the message is queued and points to `get_logs` for delivery errors
