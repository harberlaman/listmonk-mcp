"""The server that actually runs exposes every tool, not just the decorator registry."""

from listmonk_mcp.server import create_production_server

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


def test_production_server_exposes_all_70_tools() -> None:
    tools = {tool.name for tool in create_production_server()._tool_manager.list_tools()}

    assert len(PR8_TOOLS) == 41
    assert PR8_TOOLS <= tools
    # fix-core-tools added upload_media and removed rename_media (no media update route in v6.2.0).
    assert "upload_media" in tools and "rename_media" not in tools
    assert len(tools) == 70
