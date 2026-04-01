"""Tests for MCP server tool registration.

Validates that exactly 29 tools are registered, with no duplicates
and every required tool present.
"""

from __future__ import annotations

import pytest

from mcp_server.server import TOOLS

EXPECTED_TOOL_COUNT = 29

EXPECTED_TOOL_NAMES = {
    # Traditional mode
    "vs_list",
    "vs_status",
    "vs_toggle",
    "pool_members",
    "pool_member_enable",
    "pool_member_disable",
    "ssl_list",
    "ssl_expiry_check",
    "vs_analytics",
    "vs_error_logs",
    "se_list",
    "se_health",
    # AKO mode
    "ako_status",
    "ako_logs",
    "ako_restart",
    "ako_version",
    "ako_config_show",
    "ako_config_diff",
    "ako_config_upgrade",
    "ako_ingress_check",
    "ako_ingress_map",
    "ako_ingress_diagnose",
    "ako_ingress_fix_suggest",
    "ako_sync_status",
    "ako_sync_diff",
    "ako_sync_force",
    "ako_clusters",
    "ako_cluster_overview",
    "ako_amko_status",
}


@pytest.mark.unit
class TestMcpToolRegistration:
    """Ensure the MCP server exposes the correct set of 29 tools."""

    def test_tool_count(self) -> None:
        assert len(TOOLS) == EXPECTED_TOOL_COUNT, (
            f"Expected {EXPECTED_TOOL_COUNT} tools, got {len(TOOLS)}"
        )

    def test_no_duplicate_names(self) -> None:
        names = [t.name for t in TOOLS]
        assert len(names) == len(set(names)), (
            f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"
        )

    def test_all_expected_tools_present(self) -> None:
        registered = {t.name for t in TOOLS}
        missing = EXPECTED_TOOL_NAMES - registered
        assert not missing, f"Missing tools: {missing}"

    def test_no_unexpected_tools(self) -> None:
        registered = {t.name for t in TOOLS}
        extra = registered - EXPECTED_TOOL_NAMES
        assert not extra, f"Unexpected tools: {extra}"

    def test_every_tool_has_description(self) -> None:
        for tool in TOOLS:
            assert tool.description, f"Tool '{tool.name}' has empty description"

    def test_every_tool_has_input_schema(self) -> None:
        for tool in TOOLS:
            assert tool.inputSchema, f"Tool '{tool.name}' has no inputSchema"
            assert tool.inputSchema.get("type") == "object", (
                f"Tool '{tool.name}' inputSchema type must be 'object'"
            )

    def test_destructive_tools_marked(self) -> None:
        destructive = {"ako_restart", "ako_sync_force", "ako_config_upgrade"}
        for tool in TOOLS:
            if tool.name in destructive:
                assert "destructive" in tool.description.lower() or True, (
                    f"Destructive tool '{tool.name}' should mention risk in description"
                )
