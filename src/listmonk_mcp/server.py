"""Listmonk MCP Server using FastMCP framework."""

import json
import logging
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import typer
from mcp.server import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ContentBlock
from mcp.types import Tool as MCPTool
from pydantic import BaseModel

from .client import ListmonkAPIError, ListmonkClient, create_client
from .config import Config, load_config, validate_config
from .exceptions import (
    APIError,
    OperationError,
    ResourceNotFoundError,
    ValidationError,
    run_tool,
)
from .masking import mask_settings
from .uploads import (
    IMPORT_EXTENSIONS,
    IMPORT_MAX_BYTES,
    MEDIA_EXTENSIONS,
    MEDIA_MAX_BYTES,
    content_type_for,
    decode_base64,
    resolve_upload,
)

# Global state
_client: ListmonkClient | None = None
_config: Config | None = None

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _is_rfc3339(value: str) -> bool:
    """True for a full RFC3339 timestamp with a UTC offset, as Listmonk's Go parser requires."""
    if "T" not in value:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def listmonk_json(result: Any) -> str:
    """Listmonk's response for a write tool, as JSON text (not a made-up success message)."""
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


def format_subscribers(result: dict[str, Any], heading: str, page: int = 1, per_page: int = 20) -> str:
    """Render a Listmonk subscriber query page as records (not just a count)."""
    data = result.get("data") or {}
    subscribers = data.get("results") or []
    total = data.get("total", len(subscribers))
    page = data.get("page", page)
    per_page = data.get("per_page", per_page)

    lines = [f"# {heading}", "", f"Page {page}, {per_page} per page, {total} total", ""]
    if not subscribers:
        lines.append("No subscribers." if total == 0 else "No subscribers on this page.")
    for sub in subscribers:
        lines.append(f"- {sub.get('id')} | {sub.get('email')} | {sub.get('name')} | {sub.get('status')}")
        lists = ", ".join(
            f"{lst.get('name')} (ID: {lst.get('id')}, {lst.get('subscription_status', 'unknown')})"
            for lst in sub.get("lists") or []
        )
        lines.append(f"  Lists: {lists or 'none'}")
        lines.append(f"  Attributes: {json.dumps(sub.get('attribs') or {}, ensure_ascii=False)}")
    return "\n".join(lines)


def _require_rfc3339(before_date: str) -> None:
    if not _is_rfc3339(before_date):
        raise ValidationError(
            "before_date must be an RFC3339 timestamp with a UTC offset "
            f"(e.g. 2026-01-01T00:00:00Z), got {before_date!r}",
            field="before_date",
            value=before_date,
        )


@asynccontextmanager
async def lifespan(app: Any) -> Any:
    """Server lifespan context manager."""
    global _client, _config

    try:
        # Reuse the configuration run() loaded; load it here for servers started any other way
        if _config is None:
            _config = load_config()
            validate_config()

        logger.info(f"Connecting to Listmonk at {_config.url}")

        # Create and connect client
        _client = await create_client(_config)

        logger.info("Listmonk MCP Server started successfully")
        yield

    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise
    finally:
        # Cleanup
        if _client:
            await _client.close()
            logger.info("Listmonk client disconnected")


class GuardedFastMCP(FastMCP):
    """FastMCP that hides some registered tools from clients: not listed, and unknown when called."""

    hidden_tools: frozenset[str] = frozenset()

    async def list_tools(self) -> list[MCPTool]:
        return [tool for tool in await super().list_tools() if tool.name not in self.hidden_tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Sequence[ContentBlock] | dict[str, Any]:
        if name in self.hidden_tools:
            raise ToolError(f"Unknown tool: {name}")
        return await super().call_tool(name, arguments)


# Tools and resources register directly on the server that runs; the lifespan
# only executes when the server starts, so importing this module connects to nothing.
mcp = GuardedFastMCP("Listmonk MCP Server", lifespan=lifespan)

# Hidden unless LISTMONK_MCP_ALLOW_DANGEROUS is set: they act on every record or on
# records chosen by a query, or reload Listmonk (both settings writes do).
DANGEROUS_TOOLS = frozenset({
    "update_settings", "update_setting", "reload_app",
    "delete_subscribers_by_query", "blocklist_subscribers_by_query", "manage_subscriber_lists_by_query",
    "blocklist_bounced_subscribers", "delete_all_bounces", "delete_campaigns",
    "gc_subscribers", "gc_campaign_analytics", "gc_unconfirmed_subscriptions",
})


def create_production_server(allow_dangerous: bool = False) -> FastMCP:
    """Return the MCP server, exposing the dangerous tools only when allowed."""
    missing = sorted(name for name in DANGEROUS_TOOLS if mcp._tool_manager.get_tool(name) is None)
    if missing:
        raise RuntimeError(f"DANGEROUS_TOOLS names unregistered tools: {', '.join(missing)}")

    mcp.hidden_tools = frozenset() if allow_dangerous else DANGEROUS_TOOLS
    if allow_dangerous:
        logger.info("Dangerous tools enabled (LISTMONK_MCP_ALLOW_DANGEROUS is set)")
    else:
        logger.info(
            "Dangerous tools disabled (LISTMONK_MCP_ALLOW_DANGEROUS unset): %d tools hidden",
            len(DANGEROUS_TOOLS),
        )
    return mcp


def get_client() -> ListmonkClient:
    """Get the global Listmonk client."""
    if _client is None:
        raise RuntimeError("Listmonk client not initialized")
    return _client


def get_config() -> Config:
    """Get the global configuration."""
    if _config is None:
        raise RuntimeError("Configuration not loaded")
    return _config


# Health Check Tool
@mcp.tool()
async def check_listmonk_health() -> str:
    """Check if Listmonk server is healthy and accessible."""
    async def _check_health_logic() -> str:
        client = get_client()
        health_data = await client.health_check()
        config = get_config()
        status = f"Listmonk server is healthy at {config.url}. Health data: {health_data}"

        # Health alone doesn't say which Listmonk this is; a failing /api/about must not hide health.
        try:
            about = await client.get_about_info()
        except ListmonkAPIError as e:
            logger.warning("Health check: /api/about failed: %s", e)
            return f"{status}\nVersion unavailable: {e}"
        return f"{status}\nVersion: {about.get('version', 'unknown')}\nBuild: {about.get('build', 'unknown')}"

    return await run_tool(_check_health_logic)


# Subscriber Management Tools
@mcp.tool()
async def add_subscriber(
    email: str,
    name: str,
    lists: list[int],
    status: str = "enabled",
    attributes: dict[str, Any] | None = None,
    preconfirm: bool = False
) -> str:
    """
    Add a new subscriber to Listmonk.

    Args:
        email: Subscriber email address
        name: Subscriber name
        lists: List of mailing list IDs to subscribe to
        status: Subscriber status (enabled, disabled, blocklisted)
        attributes: Custom subscriber attributes
        preconfirm: Whether to preconfirm subscriptions
    """
    async def _add_subscriber_logic() -> str:
        client = get_client()
        result = await client.create_subscriber(
            email=email,
            name=name,
            status=status,
            lists=lists,
            attribs=attributes or {},
            preconfirm_subscriptions=preconfirm
        )

        return listmonk_json(result)

    return await run_tool(_add_subscriber_logic)


@mcp.tool()
async def update_subscriber(
    subscriber_id: int,
    email: str | None = None,
    name: str | None = None,
    status: str | None = None,
    lists: list[int] | None = None,
    attributes: dict[str, Any] | None = None
) -> str:
    """
    Update an existing subscriber.

    Args:
        subscriber_id: ID of the subscriber to update
        email: New email address
        name: New name
        status: New status (enabled, disabled, blocklisted)
        lists: New list of mailing list IDs
        attributes: New custom attributes
    """
    async def _update_subscriber_logic() -> str:
        client = get_client()
        result = await client.update_subscriber(
            subscriber_id=subscriber_id,
            email=email,
            name=name,
            status=status,
            lists=lists,
            attribs=attributes
        )

        return listmonk_json(result)

    return await run_tool(_update_subscriber_logic)


@mcp.tool()
async def remove_subscriber(subscriber_id: int) -> str:
    """
    Remove a subscriber from Listmonk.

    Args:
        subscriber_id: ID of the subscriber to remove
    """
    async def _remove_subscriber_logic() -> str:
        client = get_client()
        result = await client.delete_subscriber(subscriber_id)

        return listmonk_json(result)

    return await run_tool(_remove_subscriber_logic)


@mcp.tool()
async def change_subscriber_status(subscriber_id: int, status: str) -> str:
    """
    Change subscriber status.

    Args:
        subscriber_id: ID of the subscriber
        status: New status (enabled, disabled, blocklisted)
    """
    async def _change_status_logic() -> str:
        client = get_client()
        result = await client.set_subscriber_status(subscriber_id, status)

        return listmonk_json(result)

    return await run_tool(_change_status_logic)


@mcp.tool()
async def patch_subscriber(
    subscriber_id: int,
    email: str | None = None,
    name: str | None = None,
    status: str | None = None,
    attributes: dict[str, Any] | None = None,
    lists: list[int] | None = None,
    preconfirm: bool = False,
) -> str:
    """
    Partially update a subscriber. Only the fields you pass are changed.

    To add or remove lists without replacing them all, use manage_subscriber_lists.

    Args:
        subscriber_id: ID of the subscriber to patch.
        email: New email address.
        name: New name.
        status: New status (enabled, disabled, blocklisted).
        attributes: Attributes to set on the subscriber.
        lists: List IDs that REPLACE the subscriber's current subscriptions.
        preconfirm: Preconfirm subscriptions to the given lists.
    """
    async def _patch_logic() -> str:
        if all(v is None for v in (email, name, status, attributes, lists)):
            raise ValidationError("patch_subscriber needs at least one field to change")
        client = get_client()
        result = await client.patch_subscriber(
            subscriber_id,
            email=email,
            name=name,
            status=status,
            attribs=attributes,
            lists=lists,
            preconfirm_subscriptions=preconfirm,
        )
        return listmonk_json(result)

    return await run_tool(_patch_logic)


@mcp.tool()
async def subscriber_send_optin(subscriber_id: int) -> str:
    """
    Send a fresh opt-in confirmation email to a subscriber.

    Args:
        subscriber_id: ID of the subscriber.
    """
    async def _optin_logic() -> str:
        client = get_client()
        result = await client.subscriber_send_optin(subscriber_id)
        return listmonk_json(result)

    return await run_tool(_optin_logic)


@mcp.tool()
async def blocklist_subscriber(subscriber_id: int) -> str:
    """
    Blocklist a single subscriber (cannot be re-subscribed without manual action).

    Args:
        subscriber_id: ID of the subscriber to blocklist.
    """
    async def _blocklist_logic() -> str:
        client = get_client()
        result = await client.blocklist_subscriber(subscriber_id)
        return listmonk_json(result)

    return await run_tool(_blocklist_logic)


@mcp.tool()
async def blocklist_subscribers(subscriber_ids: list[int]) -> str:
    """
    Blocklist multiple subscribers in one call.

    Args:
        subscriber_ids: List of subscriber IDs to blocklist.
    """
    async def _blocklist_many_logic() -> str:
        client = get_client()
        result = await client.blocklist_subscribers(subscriber_ids)
        return listmonk_json(result)

    return await run_tool(_blocklist_many_logic)


@mcp.tool()
async def manage_subscriber_lists(
    subscriber_ids: list[int],
    target_list_ids: list[int],
    action: str,
    status: str | None = None,
) -> str:
    """
    Bulk add / remove / unsubscribe subscribers from lists.

    Args:
        subscriber_ids: Subscriber IDs to update.
        target_list_ids: Lists to operate on.
        action: One of "add", "remove", "unsubscribe".
        status: Optional subscription status (e.g. "confirmed", "unconfirmed").
    """
    async def _manage_lists_logic() -> str:
        client = get_client()
        result = await client.manage_subscriber_lists(subscriber_ids, target_list_ids, action, status)
        return listmonk_json(result)

    return await run_tool(_manage_lists_logic)


@mcp.tool()
async def get_subscriber_activity(subscriber_id: int) -> str:
    """
    Get a subscriber's campaign views and link clicks.

    Args:
        subscriber_id: ID of the subscriber.
    """
    async def _activity_logic() -> str:
        client = get_client()
        result = await client.get_subscriber_activity(subscriber_id)
        data = result.get("data") or {}
        views = data.get("campaign_views") or []
        clicks = data.get("link_clicks") or []
        if not views and not clicks:
            return f"No activity recorded for subscriber {subscriber_id}"
        lines = [f"Activity for subscriber {subscriber_id}:", f"Campaign views ({len(views)}):"]
        lines += [
            f"- {v.get('name')} (ID: {v.get('id')}): {v.get('view_count')} view(s), last {v.get('last_viewed_at')}"
            for v in views
        ]
        lines.append(f"Link clicks ({len(clicks)}):")
        lines += [
            f"- {c.get('url')} in {c.get('campaign_name')} (ID: {c.get('campaign_id')}): "
            f"{c.get('click_count')} click(s), last {c.get('last_clicked_at')}"
            for c in clicks
        ]
        return "\n".join(lines)

    return await run_tool(_activity_logic)


@mcp.tool()
async def delete_subscribers_by_query(query: str, list_ids: list[int] | None = None) -> str:
    """
    Delete subscribers matching an advanced SQL query expression.

    Args:
        query: Listmonk-style SQL query, e.g. "subscribers.status='disabled'".
        list_ids: Optional restriction to specific list IDs.
    """
    async def _del_query_logic() -> str:
        client = get_client()
        result = await client.delete_subscribers_by_query(query, list_ids)
        return listmonk_json(result)

    return await run_tool(_del_query_logic)


@mcp.tool()
async def blocklist_subscribers_by_query(query: str, list_ids: list[int] | None = None) -> str:
    """
    Blocklist subscribers matching an advanced SQL query expression.

    Args:
        query: Listmonk-style SQL query.
        list_ids: Optional restriction to specific list IDs.
    """
    async def _bl_query_logic() -> str:
        client = get_client()
        result = await client.blocklist_subscribers_by_query(query, list_ids)
        return listmonk_json(result)

    return await run_tool(_bl_query_logic)


@mcp.tool()
async def manage_subscriber_lists_by_query(
    query: str,
    target_list_ids: list[int],
    action: str,
    list_ids: list[int] | None = None,
    status: str | None = None,
) -> str:
    """
    Bulk add / remove / unsubscribe subscribers matching a query.

    Args:
        query: Listmonk-style SQL query.
        target_list_ids: Lists to operate on.
        action: One of "add", "remove", "unsubscribe".
        list_ids: Optional restriction to specific source list IDs.
        status: Optional subscription status.
    """
    async def _ml_query_logic() -> str:
        client = get_client()
        result = await client.manage_subscriber_lists_by_query(query, target_list_ids, action, list_ids, status)
        return listmonk_json(result)

    return await run_tool(_ml_query_logic)


@mcp.tool()
async def get_subscriber_bounces(subscriber_id: int) -> str:
    """
    Get bounce records for a single subscriber.

    Args:
        subscriber_id: ID of the subscriber.
    """
    async def _sb_logic() -> str:
        client = get_client()
        result = await client.get_subscriber_bounces(subscriber_id)
        bounces = result.get("data", [])
        if not bounces:
            return f"No bounces recorded for subscriber {subscriber_id}"
        rows = [
            f"- {b.get('created_at')} | {b.get('type')} | campaign {b.get('campaign_id', '-')} | {b.get('source', '?')}"
            for b in bounces
        ]
        return f"Bounces for subscriber {subscriber_id} ({len(bounces)}):\n" + "\n".join(rows)

    return await run_tool(_sb_logic)


@mcp.tool()
async def delete_subscriber_bounces(subscriber_id: int) -> str:
    """
    Delete all bounce records for a single subscriber.

    Args:
        subscriber_id: ID of the subscriber.
    """
    async def _dsb_logic() -> str:
        client = get_client()
        result = await client.delete_subscriber_bounces(subscriber_id)
        return listmonk_json(result)

    return await run_tool(_dsb_logic)


# Bounce Management Tools
@mcp.tool()
async def list_bounces(
    page: int = 1,
    per_page: int = 20,
    campaign_id: int | None = None,
    source: str | None = None,
) -> str:
    """
    List bounce records with pagination and filtering.

    Args:
        page: Page number.
        per_page: Page size.
        campaign_id: Optional campaign filter.
        source: Optional source filter (e.g. "smtp", "webhook").
    """
    async def _list_bounces_logic() -> str:
        client = get_client()
        result = await client.get_bounces(page=page, per_page=per_page, campaign_id=campaign_id, source=source)
        data = result.get("data", {})
        bounces = data.get("results", []) if isinstance(data, dict) else data
        total = data.get("total", 0) if isinstance(data, dict) else len(bounces)

        if not bounces:
            return "No bounces found."

        rows = []
        for b in bounces:
            rows.append(
                f"- ID: {b.get('id')} | {b.get('created_at')} | {b.get('type')} | "
                f"sub {b.get('subscriber_id')} | campaign {b.get('campaign_id', '-')} | {b.get('source', '?')}"
            )
        return f"Found {total} bounces (showing {len(bounces)}):\n" + "\n".join(rows)

    return await run_tool(_list_bounces_logic)


@mcp.tool()
async def get_bounce(bounce_id: int) -> str:
    """
    Get a single bounce record by ID.

    Args:
        bounce_id: ID of the bounce record.
    """
    async def _get_bounce_logic() -> str:
        client = get_client()
        result = await client.get_bounce(bounce_id)
        b = result.get("data", {})
        return (
            f"Bounce {b.get('id')}\n"
            f"Subscriber: {b.get('subscriber_id')} ({b.get('email', '?')})\n"
            f"Campaign: {b.get('campaign_id', '-')}\n"
            f"Type: {b.get('type')}\n"
            f"Source: {b.get('source')}\n"
            f"Created: {b.get('created_at')}\n\n"
            f"Meta:\n{b.get('meta', {})}"
        )

    return await run_tool(_get_bounce_logic)


@mcp.tool()
async def delete_bounce(bounce_id: int) -> str:
    """
    Delete a single bounce record.

    Args:
        bounce_id: ID of the bounce record.
    """
    async def _del_bounce_logic() -> str:
        client = get_client()
        result = await client.delete_bounce(bounce_id)
        return listmonk_json(result)

    return await run_tool(_del_bounce_logic)


@mcp.tool()
async def delete_bounces(bounce_ids: list[int]) -> str:
    """
    Delete the given bounce records. At least one ID is required; this tool never deletes all bounces.

    Args:
        bounce_ids: Bounce IDs to delete (at least one).
    """
    async def _del_bounces_logic() -> str:
        if not bounce_ids:
            raise ValidationError("At least one bounce ID is required", field="bounce_ids", value=bounce_ids)
        client = get_client()
        result = await client.delete_bounces(bounce_ids)
        return listmonk_json(result)

    return await run_tool(_del_bounces_logic)


@mcp.tool()
async def delete_all_bounces() -> str:
    """Delete ALL bounce records in Listmonk. To delete chosen bounces, use delete_bounces."""
    async def _del_all_bounces_logic() -> str:
        client = get_client()
        result = await client.delete_all_bounces()
        return listmonk_json(result)

    return await run_tool(_del_all_bounces_logic)


@mcp.tool()
async def blocklist_bounced_subscribers() -> str:
    """
    Blocklist ALL bounced subscribers: every subscriber with any bounce record.

    Listmonk cannot limit this to specific bounces. To blocklist chosen
    subscribers, use blocklist_subscriber or blocklist_subscribers instead.
    """
    async def _blbb_logic() -> str:
        client = get_client()
        result = await client.blocklist_bounced_subscribers()
        return listmonk_json(result)

    return await run_tool(_blbb_logic)


# Subscriber Import Tools
@mcp.tool()
async def import_subscribers(
    list_ids: list[int],
    content_base64: str | None = None,
    filename: str | None = None,
    file_path: str | None = None,
    mode: str = "subscribe",
    delim: str = ",",
    overwrite: bool = True,
    subscription_status: str = "confirmed",
) -> str:
    """
    Start a subscriber import from a CSV or .zip file (at most 10 MB).

    Give the file either as content_base64 + filename (works for remote clients) or
    as file_path on the machine running this server - exactly one of the two.

    Args:
        list_ids: Lists to subscribe imported users to.
        content_base64: The file's bytes, base64-encoded.
        filename: File name with extension (.csv or .zip), required with content_base64.
        file_path: Path to a .csv or .zip file on the server's filesystem.
        mode: "subscribe" (default) or "blocklist".
        delim: CSV delimiter (default ",").
        overwrite: Whether to overwrite existing subscribers.
        subscription_status: "confirmed" or "unconfirmed".
    """
    async def _import_logic() -> str:
        upload = resolve_upload(content_base64=content_base64, filename=filename, file_path=file_path,
                                allowed_extensions=IMPORT_EXTENSIONS, max_bytes=IMPORT_MAX_BYTES)
        client = get_client()
        result = await client.import_subscribers(
            upload.filename,
            upload.content,
            upload.content_type,
            mode=mode,
            list_ids=list_ids,
            delim=delim,
            overwrite=overwrite,
            subscription_status=subscription_status,
        )
        return listmonk_json(result)

    return await run_tool(_import_logic)


@mcp.tool()
async def get_import_status() -> str:
    """Get the status of the current/last subscriber import."""
    async def _status_logic() -> str:
        client = get_client()
        result = await client.get_import_status()
        d = result.get("data", {})
        return (
            f"Status: {d.get('status', 'none')}\n"
            f"Total: {d.get('total', 0)}\n"
            f"Imported: {d.get('imported', 0)}"
        )

    return await run_tool(_status_logic)


@mcp.tool()
async def get_import_logs() -> str:
    """Get logs from the current/last subscriber import."""
    async def _logs_logic() -> str:
        client = get_client()
        result = await client.get_import_logs()
        return f"Import logs:\n{result.get('data', '(no logs)')}"

    return await run_tool(_logs_logic)


@mcp.tool()
async def stop_import() -> str:
    """Stop the currently running subscriber import."""
    async def _stop_logic() -> str:
        client = get_client()
        result = await client.stop_import()
        return listmonk_json(result)

    return await run_tool(_stop_logic)


# Subscriber Resources
@mcp.resource("listmonk://subscriber/{subscriber_id}")
async def get_subscriber_by_id(subscriber_id: str) -> str:
    """Get subscriber details by ID."""
    try:
        client = get_client()
        result = await client.get_subscriber(int(subscriber_id))

        subscriber = result.get("data", {})

        lists_items = "\n".join(f"- {lst.get('name')} (ID: {lst.get('id')})" for lst in subscriber.get('lists', []))
        attributes_items = "\n".join(f"- **{k}:** {v}" for k, v in subscriber.get('attribs', {}).items())

        return f"""# Subscriber Details

**ID:** {subscriber.get('id')}
**Email:** {subscriber.get('email')}
**Name:** {subscriber.get('name')}
**Status:** {subscriber.get('status')}
**Created:** {subscriber.get('created_at')}
**Updated:** {subscriber.get('updated_at')}

## Lists
{lists_items}

## Attributes
{attributes_items}
"""

    except ListmonkAPIError as e:
        return f"Error retrieving subscriber {subscriber_id}: {str(e)}"


@mcp.resource("listmonk://subscriber/email/{email}")
async def get_subscriber_by_email(email: str) -> str:
    """Get subscriber details by email address."""
    try:
        client = get_client()
        result = await client.get_subscriber_by_email(email)

        subscriber = result.get("data", {})

        lists_items = "\n".join(f"- {lst.get('name')} (ID: {lst.get('id')})" for lst in subscriber.get('lists', []))
        attributes_items = "\n".join(f"- **{k}:** {v}" for k, v in subscriber.get('attribs', {}).items())

        return f"""# Subscriber Details

**ID:** {subscriber.get('id')}
**Email:** {subscriber.get('email')}
**Name:** {subscriber.get('name')}
**Status:** {subscriber.get('status')}
**Created:** {subscriber.get('created_at')}
**Updated:** {subscriber.get('updated_at')}

## Lists
{lists_items}

## Attributes
{attributes_items}
"""

    except ListmonkAPIError as e:
        return f"Error retrieving subscriber {email}: {str(e)}"


@mcp.resource("listmonk://subscribers")
async def list_subscribers() -> str:
    """List all subscribers with basic information."""
    try:
        client = get_client()
        result = await client.get_subscribers(per_page=50)
        return format_subscribers(result, "Subscribers", per_page=50)

    except ListmonkAPIError as e:
        return f"Error retrieving subscribers: {str(e)}"


# List Management Tools
@mcp.tool()
async def get_mailing_lists() -> str:
    """
    Get all mailing lists.

    Returns a list of all mailing lists with their IDs, UUIDs, names, subscriber counts, and types.
    """
    async def _get_lists_logic() -> str:
        client = get_client()
        result = await client.get_lists()

        data = result.get("data", {})
        lists = data.get("results", []) if isinstance(data, dict) else data

        if not lists:
            return "No mailing lists found."

        list_items = []
        for lst in lists:
            list_items.append(
                f"- ID: {lst.get('id')} | {lst.get('name')} | "
                f"UUID: {lst.get('uuid')} | "
                f"Subscribers: {lst.get('subscriber_count', 0)} | "
                f"Type: {lst.get('type', 'unknown')}"
            )

        return f"Found {len(lists)} mailing lists:\n" + "\n".join(list_items)

    return await run_tool(_get_lists_logic)


@mcp.tool()
async def create_mailing_list(
    name: str,
    type: str = "public",
    optin: str = "single",
    tags: list[str] | None = None,
    description: str | None = None
) -> str:
    """
    Create a new mailing list.

    Args:
        name: List name
        type: List type (public, private)
        optin: Opt-in type (single, double)
        tags: List tags
        description: List description
    """
    async def _create_list_logic() -> str:
        client = get_client()
        result = await client.create_list(
            name=name,
            type=type,
            optin=optin,
            tags=tags or [],
            description=description
        )

        return listmonk_json(result)

    return await run_tool(_create_list_logic)


@mcp.tool()
async def update_mailing_list(
    list_id: int,
    name: str | None = None,
    type: str | None = None,
    optin: str | None = None,
    tags: list[str] | None = None,
    description: str | None = None
) -> str:
    """
    Update an existing mailing list.

    Args:
        list_id: ID of the list to update
        name: New list name
        type: New list type (public, private)
        optin: New opt-in type (single, double)
        tags: New list tags
        description: New list description
    """
    async def _update_list_logic() -> str:
        client = get_client()
        result = await client.update_list(
            list_id=list_id,
            name=name,
            type=type,
            optin=optin,
            tags=tags,
            description=description
        )

        return listmonk_json(result)

    return await run_tool(_update_list_logic)


@mcp.tool()
async def delete_mailing_list(list_id: int) -> str:
    """
    Delete a mailing list.

    Args:
        list_id: ID of the list to delete
    """
    async def _delete_list_logic() -> str:
        client = get_client()
        result = await client.delete_list(list_id)

        return listmonk_json(result)

    return await run_tool(_delete_list_logic)


@mcp.tool()
async def get_list_subscribers_tool(
    list_id: int,
    page: int = 1,
    per_page: int = 20
) -> str:
    """
    Get subscribers for a specific mailing list.

    Args:
        list_id: ID of the mailing list
        page: Page number for pagination
        per_page: Number of subscribers per page
    """
    async def _get_list_subscribers_logic() -> str:
        client = get_client()
        result = await client.get_list_subscribers(
            list_id=list_id,
            page=page,
            per_page=per_page
        )
        return format_subscribers(result, f"Subscribers of list {list_id}", page=page, per_page=per_page)

    return await run_tool(_get_list_subscribers_logic)


# Campaign Management Tools
@mcp.tool()
async def get_campaigns(
    status: str | None = None,
    page: int = 1,
    per_page: int = 20
) -> str:
    """
    Get all campaigns with optional status filter.

    Args:
        status: Filter by status (draft, running, paused, finished, cancelled)
        page: Page number for pagination
        per_page: Number of campaigns per page
    """
    async def _get_campaigns_logic() -> str:
        client = get_client()
        result = await client.get_campaigns(page=page, per_page=per_page, status=status)

        data = result.get("data", {})
        campaigns = data.get("results", []) if isinstance(data, dict) else data
        total = data.get("total", 0) if isinstance(data, dict) else len(campaigns)

        if not campaigns:
            return "No campaigns found."

        campaign_items = []
        for c in campaigns:
            lists_str = ", ".join(str(lst.get("id")) for lst in c.get("lists", []))
            campaign_items.append(
                f"- ID: {c.get('id')} | {c.get('name')} | "
                f"Status: {c.get('status', 'unknown')} | "
                f"Lists: [{lists_str}]"
            )

        return f"Found {total} campaigns (showing {len(campaigns)}):\n" + "\n".join(campaign_items)

    return await run_tool(_get_campaigns_logic)


@mcp.tool()
async def get_campaign(campaign_id: int) -> str:
    """
    Get a specific campaign by ID including its full body content.

    Args:
        campaign_id: ID of the campaign to retrieve
    """
    async def _get_campaign_logic() -> str:
        client = get_client()
        result = await client.get_campaign(campaign_id)

        campaign = result.get("data", {})
        body = campaign.get('body', 'No content')
        lists_str = ", ".join(str(lst.get("id")) for lst in campaign.get("lists", []))

        return f"""Campaign ID: {campaign.get('id')}
Name: {campaign.get('name')}
Subject: {campaign.get('subject')}
Status: {campaign.get('status')}
Template ID: {campaign.get('template_id')}
Lists: [{lists_str}]
Content Type: {campaign.get('content_type', 'richtext')}

Body:
{body}"""

    return await run_tool(_get_campaign_logic)


@mcp.tool()
async def create_campaign(
    name: str,
    subject: str,
    lists: list[int],
    type: str = "regular",
    content_type: str = "richtext",
    body: str | None = None,
    template_id: int | None = None,
    tags: list[str] | None = None
) -> str:
    """
    Create a new email campaign.

    Args:
        name: Campaign name
        subject: Email subject line
        lists: List of mailing list IDs to send to
        type: Campaign type (regular, optin)
        content_type: Content type (richtext, html, markdown, plain)
        body: Campaign content body
        template_id: Template ID to use (optional)
        tags: Campaign tags
    """
    async def _create_campaign_logic() -> str:
        client = get_client()
        result = await client.create_campaign(
            name=name,
            subject=subject,
            lists=lists,
            type=type,
            content_type=content_type,
            body=body,
            template_id=template_id,
            tags=tags or []
        )

        return listmonk_json(result)

    return await run_tool(_create_campaign_logic)


@mcp.tool()
async def update_campaign(
    campaign_id: int,
    name: str | None = None,
    subject: str | None = None,
    lists: list[int] | None = None,
    body: str | None = None,
    tags: list[str] | None = None
) -> str:
    """
    Update an existing campaign.

    Args:
        campaign_id: ID of the campaign to update
        name: New campaign name
        subject: New email subject
        lists: New list of mailing list IDs
        body: New campaign content
        tags: New campaign tags
    """
    async def _update_campaign_logic() -> str:
        client = get_client()
        result = await client.update_campaign(
            campaign_id=campaign_id,
            name=name,
            subject=subject,
            lists=lists,
            body=body,
            tags=tags
        )

        return listmonk_json(result)

    return await run_tool(_update_campaign_logic)


@mcp.tool()
async def send_campaign(campaign_id: int) -> str:
    """
    Send a campaign immediately.

    Args:
        campaign_id: ID of the campaign to send
    """
    async def _send_campaign_logic() -> str:
        client = get_client()
        result = await client.send_campaign(campaign_id)

        return listmonk_json(result)

    return await run_tool(_send_campaign_logic)


@mcp.tool()
async def schedule_campaign(campaign_id: int, send_at: str) -> str:
    """
    Schedule a campaign for future delivery.

    Args:
        campaign_id: ID of the campaign to schedule
        send_at: ISO datetime string for when to send (e.g., '2024-12-25T10:00:00Z')
    """
    async def _schedule_campaign_logic() -> str:
        client = get_client()
        result = await client.schedule_campaign(campaign_id, send_at)

        return listmonk_json(result)

    return await run_tool(_schedule_campaign_logic)


@mcp.tool()
async def test_campaign(campaign_id: int, subscribers: list[str]) -> str:
    """
    Send a test of a campaign to specific email addresses without affecting list members.

    Args:
        campaign_id: ID of the campaign to test.
        subscribers: Recipient emails. IMPORTANT: each must already exist as a
            subscriber on this listmonk instance (the test handler looks them
            up by email and skips unknown addresses). Add them via
            add_subscriber first if needed.
    """
    async def _test_campaign_logic() -> str:
        client = get_client()
        result = await client.test_campaign(campaign_id, subscribers)
        return listmonk_json(result)

    return await run_tool(_test_campaign_logic)


@mcp.tool()
async def change_campaign_status(campaign_id: int, status: str) -> str:
    """
    Change a campaign's status.

    Args:
        campaign_id: ID of the campaign.
        status: One of "draft", "scheduled", "running", "paused", "cancelled".
    """
    async def _change_status_logic() -> str:
        client = get_client()
        result = await client.change_campaign_status(campaign_id, status)
        return listmonk_json(result)

    return await run_tool(_change_status_logic)


@mcp.tool()
async def archive_campaign(
    campaign_id: int,
    archive: bool = True,
    archive_template_id: int | None = None,
    archive_meta: dict[str, Any] | None = None,
    archive_slug: str | None = None,
) -> str:
    """
    Toggle whether a campaign appears on the public archive page.

    Args:
        campaign_id: ID of the campaign.
        archive: True to publish to archive, False to remove.
        archive_template_id: Template to use for the archive page (optional).
        archive_meta: Extra metadata for the archive entry (optional).
        archive_slug: URL slug for the archive page (optional).
    """
    async def _archive_logic() -> str:
        client = get_client()
        result = await client.archive_campaign(
            campaign_id,
            archive=archive,
            archive_template_id=archive_template_id,
            archive_meta=archive_meta,
            archive_slug=archive_slug,
        )
        return listmonk_json(result)

    return await run_tool(_archive_logic)


@mcp.tool()
async def delete_campaign(campaign_id: int) -> str:
    """
    Delete a campaign permanently.

    Args:
        campaign_id: ID of the campaign to delete.
    """
    async def _delete_campaign_logic() -> str:
        client = get_client()
        result = await client.delete_campaign(campaign_id)
        return listmonk_json(result)

    return await run_tool(_delete_campaign_logic)


@mcp.tool()
async def delete_campaigns(campaign_ids: list[int]) -> str:
    """
    Delete multiple campaigns in one call.

    Args:
        campaign_ids: List of campaign IDs to delete.
    """
    async def _delete_campaigns_logic() -> str:
        client = get_client()
        result = await client.delete_campaigns(campaign_ids)
        return listmonk_json(result)

    return await run_tool(_delete_campaigns_logic)


@mcp.tool()
async def get_running_campaign_stats() -> str:
    """Get live stats for currently running campaigns (sent, to_send, rate, ETA)."""
    async def _stats_logic() -> str:
        client = get_client()
        result = await client.get_running_campaign_stats()
        data = result.get("data", [])
        if not data:
            return "No campaigns are currently running."

        rows = []
        for s in data:
            rows.append(
                f"- Campaign {s.get('id')} ({s.get('name', 'unknown')}) — "
                f"sent: {s.get('sent', 0)}/{s.get('to_send', 0)} | "
                f"rate: {s.get('rate', 0)}/min | "
                f"net rate: {s.get('net_rate', 0)}/min | "
                f"started: {s.get('started_at', 'unknown')}"
            )
        return f"Running campaigns ({len(data)}):\n" + "\n".join(rows)

    return await run_tool(_stats_logic)


@mcp.tool()
async def get_campaign_analytics(
    analytics_type: str,
    campaign_ids: list[int],
    from_date: str,
    to_date: str,
) -> str:
    """
    Get campaign analytics (views, clicks, links, or bounces).

    Args:
        analytics_type: One of "views", "clicks", "links", "bounces".
        campaign_ids: Campaigns to fetch analytics for.
        from_date: ISO date lower bound, required (e.g. "2026-01-01").
        to_date: ISO date upper bound, required (e.g. "2026-01-31").
    """
    async def _analytics_logic() -> str:
        client = get_client()
        result = await client.get_campaign_analytics(
            analytics_type, campaign_ids, from_date=from_date, to_date=to_date
        )
        return f"Analytics ({analytics_type}) for campaigns {campaign_ids}: {result.get('data', [])}"

    return await run_tool(_analytics_logic)


# Campaign Resources
@mcp.resource("listmonk://campaigns")
async def list_campaigns() -> str:
    """List all campaigns with basic information."""
    try:
        client = get_client()
        result = await client.get_campaigns(per_page=50)

        data = result.get("data", {})
        campaigns = data.get("results", [])
        total = data.get("total", 0)

        campaign_list = []
        for camp in campaigns:
            lists_str = ", ".join(lst.get('name', '') for lst in camp.get('lists', []))
            status = camp.get('status', 'unknown')
            sent = camp.get('sent', 0)
            to_send = camp.get('to_send', 0)

            campaign_list.append(
                f"- **{camp.get('name')}** - Status: {status} - Sent: {sent}/{to_send} - Lists: {lists_str}"
            )

        campaign_items = "\n".join(campaign_list)

        return f"""# Campaigns List

**Total Campaigns:** {total}
**Showing:** {len(campaigns)} campaigns

{campaign_items}

*Use the get_campaign_by_id resource for detailed information.*
"""

    except ListmonkAPIError as e:
        return f"Error retrieving campaigns: {str(e)}"


@mcp.resource("listmonk://campaign/{campaign_id}")
async def get_campaign_by_id(campaign_id: str) -> str:
    """Get campaign details by ID."""
    try:
        client = get_client()
        result = await client.get_campaign(int(campaign_id))

        campaign = result.get("data", {})

        # Format lists
        lists_info = []
        for lst in campaign.get('lists', []):
            lists_info.append(f"- {lst.get('name')} (ID: {lst.get('id')})")

        # Format tags
        tags = campaign.get('tags', [])
        tags_str = ", ".join(tags) if tags else "None"

        lists_items = "\n".join(lists_info) if lists_info else "No lists assigned"

        return f"""# Campaign Details

**ID:** {campaign.get('id')}
**Name:** {campaign.get('name')}
**Subject:** {campaign.get('subject')}
**Status:** {campaign.get('status')}
**Type:** {campaign.get('type', 'regular')}
**Content Type:** {campaign.get('content_type', 'richtext')}

## Statistics
**To Send:** {campaign.get('to_send', 0)}
**Sent:** {campaign.get('sent', 0)}
**Views:** {campaign.get('views', 0)}
**Clicks:** {campaign.get('clicks', 0)}

## Timing
**Created:** {campaign.get('created_at')}
**Updated:** {campaign.get('updated_at')}
**Started:** {campaign.get('started_at', 'Not started')}

## Lists
{lists_items}

## Tags
{tags_str}

## Template
**Template ID:** {campaign.get('template_id', 'None')}
"""

    except ListmonkAPIError as e:
        return f"Error retrieving campaign {campaign_id}: {str(e)}"


@mcp.resource("listmonk://campaign/{campaign_id}/preview")
async def get_campaign_preview(campaign_id: str) -> str:
    """Get campaign HTML preview."""
    try:
        client = get_client()
        result = await client.get_campaign_preview(int(campaign_id))

        preview_data = result.get("data", {})
        preview_html = preview_data.get("preview", "No preview available")

        return f"""# Campaign Preview

**Campaign ID:** {campaign_id}

## HTML Preview
```html
{preview_html}
```

*This is the rendered HTML content that will be sent to subscribers.*
"""

    except ListmonkAPIError as e:
        return f"Error retrieving campaign preview {campaign_id}: {str(e)}"


# List Resources
@mcp.resource("listmonk://lists")
async def list_mailing_lists() -> str:
    """List all mailing lists with basic information."""
    try:
        client = get_client()
        result = await client.get_lists()

        data = result.get("data", {})
        lists = data.get("results", []) if isinstance(data, dict) else data

        list_items = []
        for lst in lists:
            subscriber_count = lst.get('subscriber_count', 0)
            # status = lst.get('status', 'active')  # unused
            tags = lst.get('tags', [])
            tags_str = ", ".join(tags) if tags else "None"

            list_items.append(
                f"- **{lst.get('name')}** (ID: {lst.get('id')}) - Type: {lst.get('type')} - Subscribers: {subscriber_count} - Tags: {tags_str}"
            )

        list_items_text = "\n".join(list_items)

        return f"""# Mailing Lists

**Total Lists:** {len(lists)}

{list_items_text}

*Use the get_list_by_id resource for detailed information.*
"""

    except ListmonkAPIError as e:
        return f"Error retrieving mailing lists: {str(e)}"


@mcp.resource("listmonk://list/{list_id}")
async def get_list_by_id(list_id: str) -> str:
    """Get mailing list details by ID."""
    try:
        client = get_client()
        result = await client.get_list(int(list_id))

        list_data = result.get("data", {})

        # Format tags
        tags = list_data.get('tags', [])
        tags_str = ", ".join(tags) if tags else "None"

        return f"""# Mailing List Details

**ID:** {list_data.get('id')}
**Name:** {list_data.get('name')}
**Type:** {list_data.get('type', 'public')}
**Opt-in:** {list_data.get('optin', 'single')}
**Status:** {list_data.get('status', 'active')}

## Statistics
**Subscriber Count:** {list_data.get('subscriber_count', 0)}

## Details
**Created:** {list_data.get('created_at')}
**Updated:** {list_data.get('updated_at')}

## Tags
{tags_str}

## Description
{list_data.get('description', 'No description provided')}

*Use get_list_subscribers_tool to see subscribers for this list.*
"""

    except ListmonkAPIError as e:
        return f"Error retrieving list {list_id}: {str(e)}"


@mcp.resource("listmonk://list/{list_id}/subscribers")
async def get_list_subscribers_resource(list_id: str) -> str:
    """Get subscribers for a specific mailing list."""
    try:
        client = get_client()
        result = await client.get_list_subscribers(int(list_id), per_page=50)
        return format_subscribers(result, f"Subscribers of list {list_id}", per_page=50)

    except ListmonkAPIError as e:
        return f"Error retrieving subscribers for list {list_id}: {str(e)}"


# Template Management Tools
@mcp.tool()
async def get_templates() -> str:
    """
    Get all email templates.

    Returns a list of all templates with their IDs, names, types, and default status.
    """
    async def _get_templates_logic() -> str:
        client = get_client()
        result = await client.get_templates()

        data = result.get("data", {})
        templates = data.get("results", []) if isinstance(data, dict) else data

        if not templates:
            return "No templates found."

        template_items = []
        for t in templates:
            default_marker = " (DEFAULT)" if t.get('is_default', False) else ""
            template_items.append(
                f"- ID: {t.get('id')} | {t.get('name')} | "
                f"Type: {t.get('type', 'campaign')}{default_marker}"
            )

        return f"Found {len(templates)} templates:\n" + "\n".join(template_items)

    return await run_tool(_get_templates_logic)


@mcp.tool()
async def get_template(template_id: int) -> str:
    """
    Get a specific template by ID including its full body content.

    Args:
        template_id: ID of the template to retrieve
    """
    async def _get_template_logic() -> str:
        client = get_client()
        result = await client.get_template(template_id)

        template = result.get("data", {})
        body = template.get('body', 'No content')

        return f"""Template ID: {template.get('id')}
Name: {template.get('name')}
Type: {template.get('type', 'campaign')}
Default: {template.get('is_default', False)}

Body:
{body}"""

    return await run_tool(_get_template_logic)


@mcp.tool()
async def create_template(
    name: str,
    body: str,
    type: str = "campaign",
    subject: str | None = None,
    is_default: bool = False
) -> str:
    """
    Create a new email template. The type cannot be changed after creation.

    Args:
        name: Template name
        body: Template HTML body content
        type: Template type: campaign (default), campaign_visual or tx
        subject: Subject line; required for tx (transactional) templates
        is_default: Whether this is the default template
    """
    async def _create_template_logic() -> str:
        if type == "tx" and not (subject and subject.strip()):
            raise ValidationError("Transactional (tx) templates need a subject", field="subject")
        client = get_client()
        result = await client.create_template(
            name=name,
            body=body,
            type=type,
            subject=subject,
            is_default=is_default
        )

        return listmonk_json(result)

    return await run_tool(_create_template_logic)


@mcp.tool()
async def update_template(
    template_id: int,
    name: str | None = None,
    body: str | None = None,
    is_default: bool | None = None,
    subject: str | None = None
) -> str:
    """
    Update an existing email template.

    Args:
        template_id: ID of the template to update
        name: New template name
        body: New template HTML body content
        is_default: Whether this is the default template
        subject: Email subject line (required for transactional templates, carried forward from existing template if omitted)
    """
    async def _update_template_logic() -> str:
        client = get_client()
        result = await client.update_template(
            template_id=template_id,
            name=name,
            body=body,
            is_default=is_default,
            subject=subject
        )

        return listmonk_json(result)

    return await run_tool(_update_template_logic)


@mcp.tool()
async def delete_template(template_id: int) -> str:
    """
    Delete an email template.

    Args:
        template_id: ID of the template to delete
    """
    async def _delete_template_logic() -> str:
        client = get_client()
        result = await client.delete_template(template_id)

        return listmonk_json(result)

    return await run_tool(_delete_template_logic)


@mcp.tool()
async def set_default_template(template_id: int) -> str:
    """
    Mark a template as the default for its type.

    Args:
        template_id: ID of the template to set as default.
    """
    async def _set_default_logic() -> str:
        client = get_client()
        result = await client.set_default_template(template_id)
        return listmonk_json(result)

    return await run_tool(_set_default_logic)


@mcp.tool()
async def preview_template_body(body: str, template_type: str = "campaign") -> str:
    """
    Render a preview of an unsaved template body.

    Args:
        body: Template HTML body.
        template_type: One of "campaign" (default), "campaign_visual", "tx".
    """
    async def _preview_body_logic() -> str:
        client = get_client()
        result = await client.preview_template_body(body, template_type)
        # Listmonk answers with raw HTML, which the client returns under "text".
        rendered = result.get("text", "")
        return f"# Template Preview\n\n{rendered}"

    return await run_tool(_preview_body_logic)


# Settings & System Tools

# Size of Listmonk's in-memory log buffer (v6.2.0 cmd/main.go).
LOG_MAX_LINES = 5000


@mcp.tool()
async def get_settings() -> str:
    """
    Get the full server settings document.

    Secret values (passwords, secrets, API keys) are shown as ******** and empty ones as "".
    Never write this output back to Listmonk: the masks would overwrite the real secrets.
    """
    async def _get_settings_logic() -> str:
        client = get_client()
        result = await client.get_settings()
        return f"Settings:\n{mask_settings(result.get('data', {}))}"

    return await run_tool(_get_settings_logic)


@mcp.tool()
async def update_settings(settings: dict[str, Any]) -> str:
    """
    Replace the full server settings document.

    WARNING: GET /api/settings masks secrets as bullets. PUTting that body back
    overwrites real values with literal bullets. Strip any password/token/secret
    keys from `settings` before calling this — or prefer `update_setting` for
    a single key.

    Listmonk reloads itself after this call unless a campaign is running.
    """
    async def _update_settings_logic() -> str:
        client = get_client()
        result = await client.update_settings(settings)
        return listmonk_json(result)

    return await run_tool(_update_settings_logic)


@mcp.tool()
async def update_setting(key: str, value: Any) -> str:
    """
    Update a single settings key (avoids the password-masking footgun).

    Listmonk reloads itself after this call unless a campaign is running.

    Args:
        key: Dotted setting key (e.g. "appearance.public.custom_css").
        value: New value.
    """
    async def _update_one_logic() -> str:
        client = get_client()
        result = await client.update_setting(key, value)
        return listmonk_json(result)

    return await run_tool(_update_one_logic)


@mcp.tool()
async def test_smtp_settings(settings: dict[str, Any]) -> str:
    """
    Send a test email through provided SMTP settings without persisting them.

    Args:
        settings: SMTP config with host/port/username/password/etc.
    """
    async def _test_smtp_logic() -> str:
        client = get_client()
        result = await client.test_smtp_settings(settings)
        return listmonk_json(result)

    return await run_tool(_test_smtp_logic)


@mcp.tool()
async def reload_app() -> str:
    """Trigger a hot-reload of the Listmonk app (re-reads settings)."""
    async def _reload_logic() -> str:
        client = get_client()
        result = await client.reload_app()
        return listmonk_json(result)

    return await run_tool(_reload_logic)


@mcp.tool()
async def get_logs(lines: int = 100) -> str:
    """
    Get the last lines of Listmonk's server log, oldest first. SMTP delivery errors show up here.

    Args:
        lines: How many of the most recent lines to return, 1 to 5000 (Listmonk keeps at most 5000).
    """
    async def _logs_logic() -> str:
        if not 1 <= lines <= LOG_MAX_LINES:
            raise ValidationError(
                f"lines must be between 1 and {LOG_MAX_LINES}, got {lines}", field="lines", value=lines
            )
        client = get_client()
        result = await client.get_logs()
        entries = result.get("data")
        if not isinstance(entries, list):
            entries = []
        shown = entries[-lines:]
        return "\n".join([f"Logs: last {len(shown)} of {len(entries)} lines", *map(str, shown)])

    return await run_tool(_logs_logic)


@mcp.tool()
async def get_about_info() -> str:
    """Get version / build / runtime info about this Listmonk instance."""
    async def _about_logic() -> str:
        client = get_client()
        result = await client.get_about_info()
        # /api/about is the one endpoint Listmonk returns without a "data" wrapper.
        return f"About:\n{result}"

    return await run_tool(_about_logic)


@mcp.tool()
async def get_dashboard_counts() -> str:
    """Get dashboard counts (subscribers, lists, campaigns, etc)."""
    async def _counts_logic() -> str:
        client = get_client()
        result = await client.get_dashboard_counts()
        d = result.get("data", {})
        return f"Dashboard counts:\n{d}"

    return await run_tool(_counts_logic)


@mcp.tool()
async def get_dashboard_charts() -> str:
    """Get dashboard chart data (campaign views, link clicks over time)."""
    async def _charts_logic() -> str:
        client = get_client()
        result = await client.get_dashboard_charts()
        return f"Dashboard charts:\n{result.get('data', {})}"

    return await run_tool(_charts_logic)


# Maintenance Tools
@mcp.tool()
async def gc_subscribers(gc_type: str) -> str:
    """
    Garbage collect subscribers.

    Args:
        gc_type: One of "blocklisted", "orphan" (subscribers on no list).
    """
    async def _gc_subs_logic() -> str:
        client = get_client()
        result = await client.gc_subscribers(gc_type)
        return listmonk_json(result)

    return await run_tool(_gc_subs_logic)


@mcp.tool()
async def gc_campaign_analytics(analytics_type: str, before_date: str) -> str:
    """
    Delete campaign analytics recorded before a cut-off.

    Args:
        analytics_type: One of "views", "clicks", "all".
        before_date: RFC3339 cut-off, e.g. "2026-01-01T00:00:00Z"; older data is deleted.
    """
    async def _gc_analytics_logic() -> str:
        _require_rfc3339(before_date)
        client = get_client()
        result = await client.gc_campaign_analytics(analytics_type, before_date)
        return listmonk_json(result)

    return await run_tool(_gc_analytics_logic)


@mcp.tool()
async def gc_unconfirmed_subscriptions(before_date: str) -> str:
    """
    Delete unconfirmed double-opt-in subscriptions older than the given timestamp.

    Args:
        before_date: RFC3339 cut-off, e.g. "2026-01-01T00:00:00Z"; older subscriptions are removed.
    """
    async def _gc_unconfirmed_logic() -> str:
        _require_rfc3339(before_date)
        client = get_client()
        result = await client.gc_unconfirmed_subscriptions(before_date)
        return listmonk_json(result)

    return await run_tool(_gc_unconfirmed_logic)


class TxAttachment(BaseModel):
    """A file to attach to a transactional message."""

    filename: str
    content_base64: str
    content_type: str | None = None


TX_SUBSCRIBER_MODES = ("default", "fallback", "external")


@mcp.tool()
async def send_transactional_email(
    template_id: int,
    subscriber_email: str | None = None,
    subscriber_id: int | None = None,
    subscriber_emails: list[str] | None = None,
    subscriber_ids: list[int] | None = None,
    subscriber_mode: str | None = None,
    subject: str | None = None,
    from_email: str | None = None,
    data: dict[str, Any] | None = None,
    headers: list[dict[str, str]] | None = None,
    content_type: str = "html",
    altbody: str | None = None,
    messenger: str | None = None,
    attachments: list[TxAttachment] | None = None,
) -> str:
    """
    Queue a transactional message using a tx template.

    Success means Listmonk QUEUED the message, not that it was delivered; SMTP and
    other delivery errors only appear in Listmonk's logs (use get_logs).

    Give exactly one recipient selector: subscriber_email, subscriber_id,
    subscriber_emails or subscriber_ids. In "fallback" and "external" modes only
    email selectors are allowed ("external" sends to addresses that need not be
    subscribers).

    Args:
        template_id: ID of the tx template
        subscriber_email: One recipient email
        subscriber_id: One recipient subscriber ID
        subscriber_emails: Several recipient emails
        subscriber_ids: Several recipient subscriber IDs
        subscriber_mode: "default", "fallback" or "external"
        subject: Override the template's subject
        from_email: Override the From address, e.g. "IT <it@example.com>"
        data: Any JSON object, available in the template as {{ .Tx.Data.* }}
        headers: Extra headers, one {name: value} object each, e.g. [{"X-Training-ID": "T1"}]
        content_type: "html" (default), "markdown" or "plain"
        altbody: Plain-text alternative body
        messenger: Messenger to send through (default: email)
        attachments: Files to attach, each {filename, content_base64, content_type?}
    """
    async def _send_transactional_logic() -> str:
        selectors = {
            "subscriber_email": subscriber_email,
            "subscriber_id": subscriber_id,
            "subscriber_emails": subscriber_emails,
            "subscriber_ids": subscriber_ids,
        }
        given = [name for name, value in selectors.items() if value]
        if len(given) != 1:
            raise ValidationError(
                "Give exactly one recipient selector: subscriber_email, subscriber_id, "
                f"subscriber_emails or subscriber_ids (got {', '.join(given) or 'none'})"
            )
        if subscriber_mode is not None and subscriber_mode not in TX_SUBSCRIBER_MODES:
            raise ValidationError(
                f"subscriber_mode must be one of {', '.join(TX_SUBSCRIBER_MODES)}", field="subscriber_mode"
            )
        if subscriber_mode in ("fallback", "external") and given[0] in ("subscriber_id", "subscriber_ids"):
            raise ValidationError("fallback and external modes take subscriber emails only, not IDs")

        payload: dict[str, Any] = {"template_id": template_id, "content_type": content_type}
        if subscriber_email:
            payload["subscriber_emails"] = [subscriber_email]
        elif subscriber_emails:
            payload["subscriber_emails"] = subscriber_emails
        elif subscriber_id:
            payload["subscriber_ids"] = [subscriber_id]
        else:
            payload["subscriber_ids"] = subscriber_ids
        optional = {
            "subscriber_mode": subscriber_mode,
            "subject": subject,
            "from_email": from_email,
            "data": data,
            "headers": headers,
            "altbody": altbody,
            "messenger": messenger,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})

        files = [
            (a.filename, decode_base64(a.content_base64, f"attachment {a.filename}"),
             a.content_type or content_type_for(a.filename))
            for a in attachments or []
        ]
        logger.info(
            "Queueing tx message: template=%s recipients=%s mode=%s attachments=%d",
            template_id, given[0], subscriber_mode or "default", len(files),
        )
        client = get_client()
        result = await client.send_transactional_email(payload, files)
        return listmonk_json(result)

    return await run_tool(_send_transactional_logic)


# Template Resources
@mcp.resource("listmonk://templates")
async def list_templates() -> str:
    """List all email templates."""
    try:
        client = get_client()
        result = await client.get_templates()

        data = result.get("data", {})
        templates = data.get("results", []) if isinstance(data, dict) else data

        template_list = []
        for template in templates:
            template_type = template.get('type', 'campaign')
            is_default = template.get('is_default', False)
            default_marker = " (DEFAULT)" if is_default else ""

            template_list.append(
                f"- **{template.get('name')}** (ID: {template.get('id')}) - Type: {template_type}{default_marker}"
            )

        template_items = "\n".join(template_list)

        return f"""# Email Templates

**Total Templates:** {len(templates)}

{template_items}

*Use the get_template_by_id resource for detailed template information.*
"""

    except ListmonkAPIError as e:
        return f"Error retrieving templates: {str(e)}"


@mcp.resource("listmonk://template/{template_id}")
async def get_template_by_id(template_id: str) -> str:
    """Get template details by ID."""
    try:
        client = get_client()
        result = await client.get_template(int(template_id))

        template = result.get("data", {})

        # Format the body content preview (truncate if too long)
        body = template.get('body', '')
        body_preview = body[:500] + "..." if len(body) > 500 else body

        return f"""# Template Details

**ID:** {template.get('id')}
**Name:** {template.get('name')}
**Type:** {template.get('type', 'campaign')}
**Default:** {"Yes" if template.get('is_default') else "No"}

## Timing
**Created:** {template.get('created_at')}
**Updated:** {template.get('updated_at')}

## Template Body Preview
```html
{body_preview}
```

*Note: Body content may be truncated for display. Use the template in campaigns or transactional emails to see full content.*
"""

    except ListmonkAPIError as e:
        return f"Error retrieving template {template_id}: {str(e)}"


@mcp.resource("listmonk://template/{template_id}/preview")
async def get_template_preview(template_id: str) -> str:
    """Get full template body content."""
    try:
        client = get_client()
        result = await client.get_template(int(template_id))

        template = result.get("data", {})
        body = template.get('body', 'No content available')

        return f"""# Template Full Content

**Template ID:** {template_id}
**Template Name:** {template.get('name')}

## Full HTML Body
```html
{body}
```

*This is the complete template HTML that can be used for campaigns and transactional emails.*
"""

    except ListmonkAPIError as e:
        return f"Error retrieving template content {template_id}: {str(e)}"


# Media Management Tools
@mcp.tool()
async def get_media_list() -> str:
    """
    Get all media files from Listmonk.

    Returns a list of all uploaded media with their IDs, filenames, URLs, and metadata.
    """
    async def _get_media_logic() -> str:
        client = get_client()
        result = await client.get_media()

        if not isinstance(result, dict):
            raise APIError(f"Unexpected response type from Listmonk: {type(result).__name__}")

        data = result.get("data", [])

        # Handle both list and dict formats (Listmonk can return either)
        if isinstance(data, dict):
            # If it's a dict, it might be empty or have numbered keys
            if not data:
                return "No media files found."
            # Convert dict values to list
            media_list = list(data.values()) if data else []
        else:
            # It's already a list
            media_list = data

        # Flatten if the first element is itself a list (nested structure)
        if media_list and isinstance(media_list[0], list):
            media_list = media_list[0]

        if not media_list:
            return "No media files found."

        media_items = []
        for media in media_list:
            created = media.get('created_at', 'Unknown')[:10]  # Just the date part
            size_bytes = media.get('meta', {}).get('size', 0) if isinstance(media.get('meta'), dict) else 0
            size_kb = size_bytes / 1024 if size_bytes > 0 else 0
            media_items.append(
                f"- ID: {media.get('id')} | {media.get('filename')} | "
                f"Title: {media.get('title', media.get('filename', 'No title'))} | "
                f"Size: {size_kb:.1f} KB | "
                f"Created: {created}\n"
                f"  URL: {media.get('url', 'No URL')}"
            )

        return f"Found {len(media_list)} media files:\n" + "\n".join(media_items)

    return await run_tool(_get_media_logic)


@mcp.tool()
async def upload_media(content_base64: str, filename: str) -> str:
    """
    Upload an image to Listmonk's media library from base64 content.

    Works for remote clients (no shared filesystem needed). Allowed types: png, jpg,
    jpeg, gif, webp; at most 5 MB. Returns Listmonk's response, including the media `url`
    to reference in templates and campaigns. Listmonk does not store a title.

    Args:
        content_base64: The file's bytes, base64-encoded
        filename: File name including extension, e.g. "logo.png"
    """
    async def _upload_media_logic() -> str:
        upload = resolve_upload(content_base64=content_base64, filename=filename, file_path=None,
                                allowed_extensions=MEDIA_EXTENSIONS, max_bytes=MEDIA_MAX_BYTES)
        client = get_client()
        result = await client.upload_media(upload.filename, upload.content, upload.content_type)
        return listmonk_json(result)

    return await run_tool(_upload_media_logic)


@mcp.tool()
async def upload_media_file(file_path: str) -> str:
    """
    Upload an image from a path on the machine running this server (local stdio use).

    Remote clients should use upload_media instead. Same rules: png, jpg, jpeg, gif,
    webp; at most 5 MB. Returns Listmonk's response, including the media `url`.

    Args:
        file_path: Path to the image file on the server's filesystem
    """
    async def _upload_media_file_logic() -> str:
        upload = resolve_upload(content_base64=None, filename=None, file_path=file_path,
                                allowed_extensions=MEDIA_EXTENSIONS, max_bytes=MEDIA_MAX_BYTES)
        client = get_client()
        result = await client.upload_media(upload.filename, upload.content, upload.content_type)
        return listmonk_json(result)

    return await run_tool(_upload_media_file_logic)


@mcp.tool()
async def delete_media_file(media_id: int) -> str:
    """
    Delete a media file from Listmonk.

    Args:
        media_id: ID of the media file to delete

    Returns:
        Success message
    """
    async def _delete_media_logic() -> str:
        client = get_client()
        result = await client.delete_media(media_id)

        return listmonk_json(result)

    return await run_tool(_delete_media_logic)


# Media Resources
@mcp.resource("listmonk://media")
async def list_media_files() -> str:
    """List all media files with details."""
    try:
        client = get_client()
        result = await client.get_media()

        data = result.get("data", [])

        # Handle both list and dict formats
        if isinstance(data, dict):
            if not data:
                return "# Media Files\n\nNo media files found."
            media_list = list(data.values())
        else:
            media_list = data

        # Flatten if the first element is itself a list (nested structure)
        if media_list and isinstance(media_list[0], list):
            media_list = media_list[0]

        if not media_list:
            return "# Media Files\n\nNo media files found."

        media_items = []
        for media in media_list:
            size_bytes = media.get('meta', {}).get('size', 0) if isinstance(media.get('meta'), dict) else 0
            size_kb = size_bytes / 1024 if size_bytes > 0 else 0
            created = media.get('created_at', 'Unknown')
            media_items.append(
                f"- **{media.get('filename')}** (ID: {media.get('id')})\n"
                f"  - Title: {media.get('title', media.get('filename', 'No title'))}\n"
                f"  - Size: {size_kb:.1f} KB\n"
                f"  - Created: {created}\n"
                f"  - URL: {media.get('url', 'No URL')}"
            )

        media_items_text = "\n\n".join(media_items)

        return f"""# Media Files

**Total Files:** {len(media_list)}

{media_items_text}

*Use upload_media (or upload_media_file for a local path) to add files, or delete_media_file to remove them.*
"""

    except ListmonkAPIError as e:
        return f"Error retrieving media files: {str(e)}"


# Campaign Body Editing Tools

@mcp.tool()
async def replace_in_campaign_body(
    campaign_id: int,
    search: str,
    replace: str
) -> str:
    """
    Search and replace text in a campaign body (simple string matching).

    This is much more token-efficient than updating the entire campaign body.

    Args:
        campaign_id: ID of the campaign to edit
        search: Text to search for (exact string match)
        replace: Text to replace it with

    Returns:
        Success message with number of replacements made

    Example:
        replace_in_campaign_body(
            campaign_id=11,
            search="</p>",
            replace="</p>\n<img src='https://...' style='...'>"
        )
    """
    async def _replace_logic() -> str:
        client = get_client()

        # Fetch current campaign
        result = await client.get_campaign(campaign_id)
        campaign = result.get("data", {})

        if not campaign:
            raise ResourceNotFoundError("Campaign", campaign_id)

        current_body = campaign.get("body", "")

        # Perform replacement
        new_body = current_body.replace(search, replace)
        count = current_body.count(search)

        if count == 0:
            raise OperationError(
                f"Search text not found in campaign {campaign_id}; nothing was changed",
                operation="replace",
                resource_id=campaign_id,
            )

        # Update campaign with new body
        updated = await client.update_campaign(
            campaign_id=campaign_id,
            name=campaign.get("name"),
            subject=campaign.get("subject"),
            lists=[lst["id"] for lst in campaign.get("lists", [])],
            body=new_body
        )

        return listmonk_json(updated)

    return await run_tool(_replace_logic)


@mcp.tool()
async def regex_replace_in_campaign_body(
    campaign_id: int,
    pattern: str,
    replace: str
) -> str:
    """
    Search and replace in campaign body using regex patterns.

    More powerful than simple replace - supports capturing groups and complex patterns.

    Args:
        campaign_id: ID of the campaign to edit
        pattern: Regex pattern to search for
        replace: Replacement string (can use \\1, \\2 for capture groups)

    Returns:
        Success message with number of replacements made

    Example:
        regex_replace_in_campaign_body(
            campaign_id=11,
            pattern=r"(Bondeni.*?</p>)",
            replace=r"\\1\n<img src='https://...'>"
        )
    """
    async def _regex_replace_logic() -> str:
        import re

        client = get_client()

        # Fetch current campaign
        result = await client.get_campaign(campaign_id)
        campaign = result.get("data", {})

        if not campaign:
            raise ResourceNotFoundError("Campaign", campaign_id)

        current_body = campaign.get("body", "")

        # Perform regex replacement
        new_body, count = re.subn(pattern, replace, current_body)

        if count == 0:
            raise OperationError(
                f"Pattern not found in campaign {campaign_id}; nothing was changed",
                operation="replace",
                resource_id=campaign_id,
            )

        # Update campaign with new body
        updated = await client.update_campaign(
            campaign_id=campaign_id,
            name=campaign.get("name"),
            subject=campaign.get("subject"),
            lists=[lst["id"] for lst in campaign.get("lists", [])],
            body=new_body
        )

        return listmonk_json(updated)

    return await run_tool(_regex_replace_logic)


@mcp.tool()
async def batch_replace_in_campaign_body(
    campaign_id: int,
    replacements: list[dict[str, str]]
) -> str:
    """
    Perform multiple search-and-replace operations in one go.

    Even more efficient - fetches campaign once, does all replacements, updates once.

    Args:
        campaign_id: ID of the campaign to edit
        replacements: List of dicts with 'search' and 'replace' keys

    Returns:
        Success message with total replacements made

    Example:
        batch_replace_in_campaign_body(
            campaign_id=11,
            replacements=[
                {"search": "Text A", "replace": "Text B"},
                {"search": "Text C", "replace": "Text D"}
            ]
        )
    """
    async def _batch_replace_logic() -> str:
        client = get_client()

        # Fetch current campaign
        result = await client.get_campaign(campaign_id)
        campaign = result.get("data", {})

        if not campaign:
            raise ResourceNotFoundError("Campaign", campaign_id)

        current_body = campaign.get("body", "")
        new_body = current_body
        total_count = 0

        # Perform all replacements
        for replacement in replacements:
            search = replacement.get("search", "")
            replace = replacement.get("replace", "")

            if not search:
                continue

            count = new_body.count(search)
            new_body = new_body.replace(search, replace)
            total_count += count

        if total_count == 0:
            raise OperationError(
                f"Search text not found in campaign {campaign_id}; nothing was changed",
                operation="replace",
                resource_id=campaign_id,
            )

        # Update campaign with new body
        updated = await client.update_campaign(
            campaign_id=campaign_id,
            name=campaign.get("name"),
            subject=campaign.get("subject"),
            lists=[lst["id"] for lst in campaign.get("lists", [])],
            body=new_body
        )

        return listmonk_json(updated)

    return await run_tool(_batch_replace_logic)


# CLI application
cli_app = typer.Typer(
    name="listmonk-mcp",
    help="Listmonk MCP Server - Connect Claude Code to Listmonk via Model Context Protocol",
    add_completion=False
)


@cli_app.command()
def run(
    config_file: str = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file (.env format)"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug logging"
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit"
    )
) -> None:
    """
    Start the Listmonk MCP server.

    The server requires configuration via environment variables:
    - LISTMONK_MCP_URL: Listmonk server URL (e.g., http://localhost:9000)
    - LISTMONK_MCP_USERNAME: Listmonk API username
    - LISTMONK_MCP_PASSWORD: Listmonk API password/token

    Optional environment variables:
    - LISTMONK_MCP_TIMEOUT: Request timeout in seconds (default: 30)
    - LISTMONK_MCP_MAX_RETRIES: Maximum retry attempts (default: 3)
    - LISTMONK_MCP_DEBUG: Enable debug mode (default: false)
    - LISTMONK_MCP_LOG_LEVEL: Logging level (default: INFO)
    - LISTMONK_MCP_ALLOW_DANGEROUS: Expose the 12 tools that act on every record,
      act by query or reload Listmonk (default: false)
    """
    global _config

    if version:
        # Import here to avoid circular imports
        try:
            from importlib.metadata import version as get_version
            pkg_version = get_version("listmonk-mcp")
        except ImportError:
            pkg_version = "0.0.1"  # fallback
        typer.echo(f"listmonk-mcp {pkg_version}")
        raise typer.Exit()

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    try:
        logger.info("Starting Listmonk MCP Server...")
        # The dangerous-tools flag must be known before the server lists any tool
        _config = load_config()
        validate_config()
        server = create_production_server(allow_dangerous=_config.allow_dangerous)
        server.run()
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
        raise typer.Exit(0) from None
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise typer.Exit(1) from e


def main() -> None:
    """Main entry point for the CLI script."""
    cli_app()


if __name__ == "__main__":
    main()
