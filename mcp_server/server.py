"""MCP Server for VMware AVI — stdio transport.

Exposes 29 tools for AVI Controller + AKO K8s operations.
Entry point: vmware-avi-mcp (defined in pyproject.toml).
"""

from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

_log = logging.getLogger("vmware-avi-mcp")

server = Server("vmware-avi-mcp")


# --- Tool definitions ---

TOOLS = [
    # Traditional mode
    Tool(name="vs_list", description="List all Virtual Services", inputSchema={
        "type": "object", "properties": {"controller": {"type": "string"}},
    }),
    Tool(name="vs_status", description="Show Virtual Service status", inputSchema={
        "type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
    }),
    Tool(name="vs_toggle", description="Enable or disable a Virtual Service", inputSchema={
        "type": "object",
        "properties": {"name": {"type": "string"}, "enable": {"type": "boolean"}},
        "required": ["name", "enable"],
    }),
    Tool(name="pool_members", description="List pool members and health", inputSchema={
        "type": "object", "properties": {"pool": {"type": "string"}}, "required": ["pool"],
    }),
    Tool(name="pool_member_enable", description="Enable a pool member", inputSchema={
        "type": "object",
        "properties": {"pool": {"type": "string"}, "server": {"type": "string"}},
        "required": ["pool", "server"],
    }),
    Tool(name="pool_member_disable", description="Disable a pool member (graceful drain)", inputSchema={
        "type": "object",
        "properties": {"pool": {"type": "string"}, "server": {"type": "string"}},
        "required": ["pool", "server"],
    }),
    Tool(name="ssl_list", description="List all SSL certificates", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ssl_expiry_check", description="Check certificates expiring within N days", inputSchema={
        "type": "object", "properties": {"days": {"type": "integer", "default": 30}},
    }),
    Tool(name="vs_analytics", description="Show VS analytics metrics", inputSchema={
        "type": "object", "properties": {"vs_name": {"type": "string"}}, "required": ["vs_name"],
    }),
    Tool(name="vs_error_logs", description="Show VS request error logs", inputSchema={
        "type": "object",
        "properties": {"vs_name": {"type": "string"}, "since": {"type": "string", "default": "1h"}},
        "required": ["vs_name"],
    }),
    Tool(name="se_list", description="List all Service Engines", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="se_health", description="Check Service Engine health", inputSchema={
        "type": "object", "properties": {},
    }),
    # AKO mode
    Tool(name="ako_status", description="Check AKO pod status", inputSchema={
        "type": "object", "properties": {"context": {"type": "string"}},
    }),
    Tool(name="ako_logs", description="View AKO pod logs", inputSchema={
        "type": "object",
        "properties": {"tail": {"type": "integer", "default": 100}, "since": {"type": "string"}},
    }),
    Tool(name="ako_restart", description="Restart AKO pod (destructive)", inputSchema={
        "type": "object", "properties": {"context": {"type": "string"}},
    }),
    Tool(name="ako_version", description="Show AKO version info", inputSchema={
        "type": "object", "properties": {"context": {"type": "string"}},
    }),
    Tool(name="ako_config_show", description="Show AKO Helm values", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_config_diff", description="Show pending Helm changes", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_config_upgrade", description="Helm upgrade AKO", inputSchema={
        "type": "object", "properties": {"dry_run": {"type": "boolean", "default": True}},
    }),
    Tool(name="ako_ingress_check", description="Validate Ingress annotations", inputSchema={
        "type": "object", "properties": {"namespace": {"type": "string"}}, "required": ["namespace"],
    }),
    Tool(name="ako_ingress_map", description="Show Ingress to VS mapping", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_ingress_diagnose", description="Diagnose Ingress with no VS", inputSchema={
        "type": "object",
        "properties": {"name": {"type": "string"}, "namespace": {"type": "string", "default": "default"}},
        "required": ["name"],
    }),
    Tool(name="ako_ingress_fix_suggest", description="Suggest fix for Ingress issues", inputSchema={
        "type": "object",
        "properties": {"name": {"type": "string"}, "namespace": {"type": "string", "default": "default"}},
        "required": ["name"],
    }),
    Tool(name="ako_sync_status", description="Check K8s-Controller sync status", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_sync_diff", description="Show K8s-Controller inconsistencies", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_sync_force", description="Force AKO resync (destructive)", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_clusters", description="List clusters with AKO deployed", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_cluster_overview", description="Cross-cluster AKO status overview", inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_amko_status", description="Show AMKO GSLB status", inputSchema={
        "type": "object", "properties": {},
    }),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


def _capture_output(func, *args, **kwargs) -> str:
    """Run a function and capture its Rich console output as plain text."""
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    capture_console = Console(file=buf, force_terminal=False, width=120)

    # Temporarily patch the module's console
    import importlib
    import sys

    mod_name = func.__module__
    mod = sys.modules.get(mod_name)
    original_console = getattr(mod, "console", None) if mod else None

    if mod and original_console is not None:
        mod.console = capture_console

    try:
        func(*args, **kwargs)
    except SystemExit:
        pass
    finally:
        if mod and original_console is not None:
            mod.console = original_console

    return buf.getvalue()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to the appropriate ops function."""
    from vmware_avi.notify.audit import log_operation

    try:
        output = _dispatch(name, arguments)
        log_operation(operation=name, resource=json.dumps(arguments), result="success")
        return [TextContent(type="text", text=output)]
    except Exception as exc:
        log_operation(operation=name, resource=json.dumps(arguments), result=f"error: {exc}")
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]


def _dispatch(name: str, args: dict) -> str:
    """Dispatch tool call to the corresponding ops function."""
    # Traditional mode
    if name == "vs_list":
        from vmware_avi.ops.vs_mgmt import list_virtual_services
        return _capture_output(list_virtual_services, args.get("controller"))
    if name == "vs_status":
        from vmware_avi.ops.vs_mgmt import show_vs_status
        return _capture_output(show_vs_status, args["name"])
    if name == "vs_toggle":
        from vmware_avi.ops.vs_mgmt import toggle_vs
        return _capture_output(toggle_vs, args["name"], enable=args["enable"])
    if name == "pool_members":
        from vmware_avi.ops.pool_mgmt import list_pool_members
        return _capture_output(list_pool_members, args["pool"])
    if name == "pool_member_enable":
        from vmware_avi.ops.pool_mgmt import toggle_pool_member
        return _capture_output(toggle_pool_member, args["pool"], args["server"], enable=True)
    if name == "pool_member_disable":
        from vmware_avi.ops.pool_mgmt import toggle_pool_member
        return _capture_output(toggle_pool_member, args["pool"], args["server"], enable=False)
    if name == "ssl_list":
        from vmware_avi.ops.ssl_mgmt import list_certificates
        return _capture_output(list_certificates)
    if name == "ssl_expiry_check":
        from vmware_avi.ops.ssl_mgmt import check_expiry
        return _capture_output(check_expiry, args.get("days", 30))
    if name == "vs_analytics":
        from vmware_avi.ops.analytics import show_analytics
        return _capture_output(show_analytics, args["vs_name"])
    if name == "vs_error_logs":
        from vmware_avi.ops.analytics import show_error_logs
        return _capture_output(show_error_logs, args["vs_name"], args.get("since", "1h"))
    if name == "se_list":
        from vmware_avi.ops.se_mgmt import list_service_engines
        return _capture_output(list_service_engines)
    if name == "se_health":
        from vmware_avi.ops.se_mgmt import check_se_health
        return _capture_output(check_se_health)

    # AKO mode
    ctx = args.get("context")
    if name == "ako_status":
        from vmware_avi.ops.ako_pod import check_ako_status
        return _capture_output(check_ako_status, ctx)
    if name == "ako_logs":
        from vmware_avi.ops.ako_pod import view_ako_logs
        return _capture_output(view_ako_logs, args.get("tail", 100), args.get("since", ""), ctx)
    if name == "ako_restart":
        from vmware_avi.ops.ako_pod import restart_ako
        return _capture_output(restart_ako, ctx)
    if name == "ako_version":
        from vmware_avi.ops.ako_pod import show_ako_version
        return _capture_output(show_ako_version, ctx)
    if name == "ako_config_show":
        from vmware_avi.ops.ako_config import show_ako_config
        return _capture_output(show_ako_config)
    if name == "ako_config_diff":
        from vmware_avi.ops.ako_config import diff_ako_config
        return _capture_output(diff_ako_config)
    if name == "ako_config_upgrade":
        from vmware_avi.ops.ako_config import upgrade_ako
        return _capture_output(upgrade_ako, args.get("dry_run", True))
    if name == "ako_ingress_check":
        from vmware_avi.ops.ako_ingress import check_ingress_annotations
        return _capture_output(check_ingress_annotations, args["namespace"], ctx)
    if name == "ako_ingress_map":
        from vmware_avi.ops.ako_ingress import show_ingress_map
        return _capture_output(show_ingress_map, ctx)
    if name == "ako_ingress_diagnose":
        from vmware_avi.ops.ako_ingress import diagnose_ingress
        return _capture_output(diagnose_ingress, args["name"], args.get("namespace", "default"), ctx)
    if name == "ako_ingress_fix_suggest":
        from vmware_avi.ops.ako_ingress import diagnose_ingress
        return _capture_output(diagnose_ingress, args["name"], args.get("namespace", "default"), ctx)
    if name == "ako_sync_status":
        from vmware_avi.ops.ako_sync import check_sync_status
        return _capture_output(check_sync_status, ctx)
    if name == "ako_sync_diff":
        from vmware_avi.ops.ako_sync import show_sync_diff
        return _capture_output(show_sync_diff, ctx)
    if name == "ako_sync_force":
        from vmware_avi.ops.ako_sync import force_resync
        return _capture_output(force_resync, ctx)
    if name in ("ako_clusters", "ako_cluster_overview"):
        from vmware_avi.ops.ako_multi_cluster import list_clusters
        return _capture_output(list_clusters)
    if name == "ako_amko_status":
        from vmware_avi.ops.ako_multi_cluster import show_amko_status
        return _capture_output(show_amko_status)

    return json.dumps({"error": f"Unknown tool: {name}"})


def main() -> None:
    """Entry point for vmware-avi-mcp."""
    import asyncio

    async def _run() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
