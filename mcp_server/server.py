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
    # === Traditional mode (AVI Controller) ===
    Tool(name="vs_list", description=(
        "[READ] List all Virtual Services with name, VIP, enabled state, and health score. "
        "Use this for an overview before drilling into a specific VS with vs_status."
    ), inputSchema={
        "type": "object", "properties": {"controller": {"type": "string", "description": "AVI controller name from config (optional, uses default)"}},
    }),
    Tool(name="vs_status", description=(
        "[READ] Show detailed status for a specific Virtual Service — VIP, pool, health, "
        "connections, and throughput. Use vs_list first to find the exact VS name."
    ), inputSchema={
        "type": "object", "properties": {"name": {"type": "string", "description": "Exact Virtual Service name"}}, "required": ["name"],
    }),
    Tool(name="vs_toggle", description=(
        "[WRITE] Enable or disable a Virtual Service. Disabling stops all traffic to this VS. "
        "Requires double confirmation. Use vs_status first to check current state."
    ), inputSchema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Exact Virtual Service name"}, "enable": {"type": "boolean", "description": "true to enable, false to disable"}},
        "required": ["name", "enable"],
    }),
    Tool(name="pool_members", description=(
        "[READ] List all members of a pool with server IP, port, enabled state, and health status. "
        "Use this before enabling/disabling individual members during maintenance windows."
    ), inputSchema={
        "type": "object", "properties": {"pool": {"type": "string", "description": "Pool name"}}, "required": ["pool"],
    }),
    Tool(name="pool_member_enable", description=(
        "[WRITE] Enable a pool member to start receiving traffic. "
        "Use pool_members first to verify server IP and current state."
    ), inputSchema={
        "type": "object",
        "properties": {"pool": {"type": "string", "description": "Pool name"}, "server": {"type": "string", "description": "Server IP address"}},
        "required": ["pool", "server"],
    }),
    Tool(name="pool_member_disable", description=(
        "[WRITE] Disable a pool member with graceful drain — existing connections complete, no new traffic. "
        "Use during maintenance windows or rolling deployments. Requires double confirmation."
    ), inputSchema={
        "type": "object",
        "properties": {"pool": {"type": "string", "description": "Pool name"}, "server": {"type": "string", "description": "Server IP address"}},
        "required": ["pool", "server"],
    }),
    Tool(name="ssl_list", description=(
        "[READ] List all SSL/TLS certificates on the AVI Controller with name, type, issuer, and expiry date."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ssl_expiry_check", description=(
        "[READ] Check which SSL certificates expire within N days (default 30). "
        "Returns certificate name, expiry date, and days remaining. Run regularly to prevent outages."
    ), inputSchema={
        "type": "object", "properties": {"days": {"type": "integer", "default": 30, "description": "Check certs expiring within this many days (default 30)"}},
    }),
    Tool(name="vs_analytics", description=(
        "[READ] Show analytics for a Virtual Service — throughput, latency percentiles, connection rate, "
        "and error breakdown. Use to investigate performance issues."
    ), inputSchema={
        "type": "object", "properties": {"vs_name": {"type": "string", "description": "Virtual Service name"}}, "required": ["vs_name"],
    }),
    Tool(name="vs_error_logs", description=(
        "[READ] Show recent request error logs for a Virtual Service — HTTP status codes, client IPs, "
        "URIs, and response times. Use to diagnose 5xx errors or latency spikes."
    ), inputSchema={
        "type": "object",
        "properties": {"vs_name": {"type": "string", "description": "Virtual Service name"}, "since": {"type": "string", "default": "1h", "description": "Time window, e.g. '1h', '30m', '2d'"}},
        "required": ["vs_name"],
    }),
    Tool(name="se_list", description=(
        "[READ] List all Service Engines with name, status, connected VS count, and resource usage."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="se_health", description=(
        "[READ] Check health of all Service Engines — CPU, memory, disk usage, and connectivity. "
        "Use when VS health degrades to check if the issue is at the SE level."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    # === AKO mode (K8s) ===
    Tool(name="ako_status", description=(
        "[READ] Check AKO (AVI Kubernetes Operator) pod status — running, restarts, age, and ready state. "
        "First step when troubleshooting Ingress or LoadBalancer issues in Tanzu/K8s."
    ), inputSchema={
        "type": "object", "properties": {"context": {"type": "string", "description": "K8s context name (optional, uses current context)"}},
    }),
    Tool(name="ako_logs", description=(
        "[READ] View AKO pod logs to debug Ingress creation failures, sync errors, or AVI Controller "
        "connectivity issues. Use 'since' to narrow the time window."
    ), inputSchema={
        "type": "object",
        "properties": {"tail": {"type": "integer", "default": 100, "description": "Number of log lines to show (default 100)"}, "since": {"type": "string", "description": "Time filter, e.g. '30m', '1h'"}},
    }),
    Tool(name="ako_restart", description=(
        "[WRITE] Restart AKO pod by deleting it (K8s recreates automatically). "
        "Use when AKO is stuck or after config changes. Requires double confirmation. "
        "Brief traffic disruption possible during restart."
    ), inputSchema={
        "type": "object", "properties": {"context": {"type": "string", "description": "K8s context name (optional)"}},
    }),
    Tool(name="ako_version", description=(
        "[READ] Show AKO version, Helm chart version, and container image tag. "
        "Use to verify AKO version compatibility with AVI Controller."
    ), inputSchema={
        "type": "object", "properties": {"context": {"type": "string", "description": "K8s context name (optional)"}},
    }),
    Tool(name="ako_config_show", description=(
        "[READ] Show current AKO Helm values.yaml configuration — controller IP, cloud name, "
        "network settings, and feature flags."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_config_diff", description=(
        "[READ] Show pending Helm value changes that haven't been applied yet. "
        "Use before ako_config_upgrade to review what will change."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_config_upgrade", description=(
        "[WRITE] Apply AKO Helm upgrade with updated values. Defaults to dry_run=true for safety. "
        "Set dry_run=false to apply. Requires double confirmation for non-dry-run."
    ), inputSchema={
        "type": "object", "properties": {"dry_run": {"type": "boolean", "default": True, "description": "Preview changes without applying (default true)"}},
    }),
    Tool(name="ako_ingress_check", description=(
        "[READ] Validate Ingress annotations in a namespace — checks for unsupported or misspelled "
        "AKO annotations that prevent VS creation."
    ), inputSchema={
        "type": "object", "properties": {"namespace": {"type": "string", "description": "K8s namespace to check"}}, "required": ["namespace"],
    }),
    Tool(name="ako_ingress_map", description=(
        "[READ] Show mapping between K8s Ingress resources and AVI Virtual Services. "
        "Use to verify which Ingresses have corresponding VS objects."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_ingress_diagnose", description=(
        "[READ] Diagnose why a specific Ingress has no corresponding Virtual Service. "
        "Checks annotations, TLS config, service endpoints, and AKO logs for errors."
    ), inputSchema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Ingress resource name"}, "namespace": {"type": "string", "default": "default", "description": "K8s namespace (default 'default')"}},
        "required": ["name"],
    }),
    Tool(name="ako_ingress_fix_suggest", description=(
        "[READ] Suggest specific fixes for Ingress issues — returns actionable kubectl commands "
        "or annotation corrections based on the diagnosed problem."
    ), inputSchema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Ingress resource name"}, "namespace": {"type": "string", "default": "default", "description": "K8s namespace (default 'default')"}},
        "required": ["name"],
    }),
    Tool(name="ako_sync_status", description=(
        "[READ] Check sync status between K8s resources and AVI Controller objects. "
        "Shows in-sync, pending, and error counts."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_sync_diff", description=(
        "[READ] Show specific inconsistencies between K8s Ingress/Service definitions and "
        "AVI Controller VS/Pool objects. Use to identify drift."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_sync_force", description=(
        "[WRITE] Force AKO to resync all K8s resources with AVI Controller. "
        "Use when drift is detected. Requires double confirmation. May cause brief traffic disruption."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_clusters", description=(
        "[READ] List all K8s clusters that have AKO deployed, with version and status."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_cluster_overview", description=(
        "[READ] Cross-cluster AKO overview — VS count, pool count, health summary per cluster. "
        "Use for multi-cluster fleet health assessment."
    ), inputSchema={
        "type": "object", "properties": {},
    }),
    Tool(name="ako_amko_status", description=(
        "[READ] Show AMKO (AVI Multi-Cluster Kubernetes Operator) GSLB status — global services, "
        "member clusters, and federation health."
    ), inputSchema={
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
