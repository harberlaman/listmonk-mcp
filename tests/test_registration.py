"""The server that actually runs: which tools it exposes, with and without LISTMONK_MCP_ALLOW_DANGEROUS."""

from listmonk_mcp.server import DANGEROUS_TOOLS, create_production_server

# The 41 tools added by upstream PR #8 (see the merge-upstream-prs proposal).
PR8_TOOLS = {
    "patch_subscriber", "subscriber_send_optin", "blocklist_subscriber", "blocklist_subscribers",
    "manage_subscriber_lists", "get_subscriber_activity", "delete_subscribers_by_query",
    "blocklist_subscribers_by_query", "manage_subscriber_lists_by_query",
    "list_bounces", "get_bounce", "get_subscriber_bounces", "delete_bounce", "delete_bounces",
    "delete_subscriber_bounces", "blocklist_bounced_subscribers",
    "import_subscribers", "get_import_status", "get_import_logs", "stop_import",
    "test_campaign", "change_campaign_status", "archive_campaign", "delete_campaign",
    "delete_campaigns", "get_running_campaign_stats", "get_campaign_analytics",
    "set_default_template", "preview_template_body",
    "get_settings", "update_settings", "update_setting", "test_smtp_settings", "reload_app",
    "get_logs", "get_about_info", "get_dashboard_counts", "get_dashboard_charts",
    "gc_subscribers", "gc_campaign_analytics", "gc_unconfirmed_subscriptions",
}


EXPECTED_DANGEROUS = {
    "update_settings", "update_setting", "reload_app",
    "delete_subscribers_by_query", "blocklist_subscribers_by_query", "manage_subscriber_lists_by_query",
    "blocklist_bounced_subscribers", "delete_all_bounces", "delete_campaigns",
    "gc_subscribers", "gc_campaign_analytics", "gc_unconfirmed_subscriptions",
}


async def exposed_tools(allow_dangerous: bool) -> set[str]:
    server = create_production_server(allow_dangerous=allow_dangerous)
    return {tool.name for tool in await server.list_tools()}


def test_dangerous_tools_are_exactly_the_twelve() -> None:
    assert DANGEROUS_TOOLS == EXPECTED_DANGEROUS


async def test_default_server_exposes_59_tools_and_no_dangerous_ones() -> None:
    tools = await exposed_tools(allow_dangerous=False)

    assert len(tools) == 59
    assert not tools & DANGEROUS_TOOLS


async def test_allowed_server_exposes_all_71_tools() -> None:
    tools = await exposed_tools(allow_dangerous=True)

    assert len(PR8_TOOLS) == 41
    assert PR8_TOOLS <= tools
    # fix-core-tools added upload_media and removed rename_media (no media update route in v6.2.0).
    assert "upload_media" in tools and "rename_media" not in tools
    # guardrails added delete_all_bounces.
    assert DANGEROUS_TOOLS <= tools
    assert len(tools) == 71


async def test_building_with_flag_off_after_flag_on_hides_them_again() -> None:
    await exposed_tools(allow_dangerous=True)

    assert len(await exposed_tools(allow_dangerous=False)) == 59
