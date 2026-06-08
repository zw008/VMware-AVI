"""MCP Server for VMware AVI — stdio transport.

Exposes 29 tools for AVI Controller + AKO K8s operations.
Entry point: vmware-avi-mcp (defined in pyproject.toml).
"""


import logging
from io import StringIO
from typing import Optional

from mcp.server.fastmcp import FastMCP
from vmware_policy import vmware_tool

_log = logging.getLogger("vmware-avi-mcp")

mcp = FastMCP("vmware-avi")


# ---------------------------------------------------------------------------
# Output capture helper
# ---------------------------------------------------------------------------

def _capture_output(func, *args, **kwargs) -> str:
    """Run a function and capture its Rich console output as plain text."""
    import importlib  # noqa: F401 — used via sys.modules lookup
    import sys

    buf = StringIO()
    from rich.console import Console
    capture_console = Console(file=buf, force_terminal=False, width=120)

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


# ═══════════════════════════════════════════════════════════════════════════════
# Traditional mode — AVI Controller
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def vs_list(controller: Optional[str] = None) -> str:
    """[READ] List all Virtual Services with name, VIP, enabled state, and health score.

    Use this for an overview before drilling into a specific VS with vs_status.

    Args:
        controller: AVI controller name from config (optional, uses default).
    """
    from vmware_avi.ops.vs_mgmt import list_virtual_services
    return _capture_output(list_virtual_services, controller)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def vs_status(name: str) -> str:
    """[READ] Show detailed status for a specific Virtual Service — VIP, pool, health, connections, and throughput.

    Use vs_list first to find the exact VS name.

    Args:
        name: Exact Virtual Service name.
    """
    from vmware_avi.ops.vs_mgmt import show_vs_status
    return _capture_output(show_vs_status, name)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="high")
def vs_toggle(name: str, enable: bool, confirmed: bool = False) -> str:
    """[WRITE] Enable or disable a Virtual Service. Disabling stops all traffic to this VS.

    Use vs_status first to check current state.

    SAFETY: When enable=False, requires confirmed=True to execute. Default False returns
    a preview message describing the intended action. Enabling a VS is always safe and
    does not require confirmation.

    Args:
        name: Exact Virtual Service name.
        enable: true to enable, false to disable.
        confirmed: Must be True when enable=False to actually disable the VS.
            Default False returns a preview-only message. Ignored when enable=True.
    """
    from vmware_avi.ops.vs_mgmt import toggle_vs
    if not enable and not confirmed:
        return (
            f"[preview] Would disable Virtual Service '{name}', stopping all traffic to this VS. "
            "Re-invoke with confirmed=True to execute."
        )
    return _capture_output(toggle_vs, name, enable=enable, skip_prompt=True)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def pool_list(vs_filter: Optional[str] = None) -> str:
    """[READ] Discover pools on the Controller.

    Use this BEFORE pool_members when you don't know exact pool names — pools often have
    different names from VS. Pass vs_filter to narrow to pools referenced by matching
    Virtual Services.

    Args:
        vs_filter: Optional substring to match VS names (e.g. 'web') — returns pools
            referenced by those VS only.
    """
    from vmware_avi.ops.pool_mgmt import list_pools
    return _capture_output(list_pools, vs_filter)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def pool_members(pool: str) -> str:
    """[READ] List all members of a pool with server IP, port, enabled state, and health status.

    Use this before enabling/disabling individual members during maintenance windows.
    Run pool_list first if you don't know the exact pool name.

    Args:
        pool: Pool name.
    """
    from vmware_avi.ops.pool_mgmt import list_pool_members
    return _capture_output(list_pool_members, pool)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def pool_member_enable(pool: str, server: str) -> str:
    """[WRITE] Enable a pool member to start receiving traffic.

    Use pool_members first to verify server IP and current state.

    Args:
        pool: Pool name.
        server: Server IP address.
    """
    from vmware_avi.ops.pool_mgmt import toggle_pool_member
    return _capture_output(toggle_pool_member, pool, server, enable=True)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="high")
def pool_member_disable(pool: str, server: str, confirmed: bool = False) -> str:
    """[WRITE] Disable a pool member with graceful drain — existing connections complete, no new traffic.

    Use during maintenance windows or rolling deployments.

    SAFETY: Requires confirmed=True to execute. Default False returns a preview message
    describing the intended action.

    Args:
        pool: Pool name.
        server: Server IP address.
        confirmed: Must be True to actually disable the pool member.
            Default False returns a preview-only message.
    """
    if not confirmed:
        return (
            f"[preview] Would disable pool member {server} in pool '{pool}' "
            "(graceful drain — existing connections complete, no new traffic). "
            "Re-invoke with confirmed=True to execute."
        )
    from vmware_avi.ops.pool_mgmt import toggle_pool_member
    return _capture_output(toggle_pool_member, pool, server, enable=False, skip_prompt=True)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ssl_list() -> str:
    """[READ] List all SSL/TLS certificates stored on the AVI Controller.

    Returns a table of certificate Name, Subject common name, Expiry date, and Type
    (e.g. CA vs virtual-service certificate), plus a total count. The full set is
    returned in one call — no pagination or filtering. No parameters required;
    connects to the default controller from config. Use for certificate inventory
    or to find a certificate's exact name; use ssl_expiry_check instead when you
    only need certificates expiring within the next N days.
    """
    from vmware_avi.ops.ssl_mgmt import list_certificates
    return _capture_output(list_certificates)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ssl_expiry_check(days: int = 30) -> str:
    """[READ] Check which SSL certificates expire within N days (default 30).

    Returns certificate name, expiry date, and days remaining. Run regularly to prevent outages.

    Args:
        days: Check certs expiring within this many days (default 30).
    """
    from vmware_avi.ops.ssl_mgmt import check_expiry
    return _capture_output(check_expiry, days)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def vs_analytics(vs_name: str) -> str:
    """[READ] Show performance metrics for one Virtual Service over the last hour.

    Queries the AVI analytics collection API with a fixed window: 12 samples at
    5-minute granularity. Returns L4 metrics (avg bandwidth, completed and new
    connections) and L7 metrics (avg client transaction latency, % response errors,
    total responses). Empty output means the VS had no traffic in the window or analytics
    collection is disabled — not an error. Use when investigating throughput or
    latency issues after vs_status shows degraded health; use vs_error_logs for
    per-request error detail with a configurable time window.

    Args:
        vs_name: Exact Virtual Service name, case-sensitive, as shown by vs_list.
            Fails with a 'not found' message if no VS matches.
    """
    from vmware_avi.ops.analytics import show_analytics
    return _capture_output(show_analytics, vs_name)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def vs_error_logs(vs_name: str, since: str = "1h") -> str:
    """[READ] Show recent request error logs for a Virtual Service — HTTP status codes, client IPs, URIs, and response times.

    Use to diagnose 5xx errors or latency spikes.

    Args:
        vs_name: Virtual Service name.
        since: Time window, e.g. '1h', '30m', '2d' (default '1h').
    """
    from vmware_avi.ops.analytics import show_error_logs
    return _capture_output(show_error_logs, vs_name, since)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def se_list() -> str:
    """[READ] List all Service Engines (AVI data-plane VMs) on the Controller.

    Returns one row per SE: Name, management IP, operational status (e.g. OPER_UP),
    and SE Group, sourced from the serviceengine-inventory endpoint (config +
    runtime merged). The full list is returned in one call — no pagination or
    filtering. No parameters required; connects to the default controller from
    config. Use to inventory data-plane capacity or find an SE's name and IP; use
    se_health instead for per-SE operational status and connected-VS counts when
    investigating degraded Virtual Service health.
    """
    from vmware_avi.ops.se_mgmt import list_service_engines
    return _capture_output(list_service_engines)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def se_health() -> str:
    """[READ] Check health of all Service Engines — operational status and connected-VS counts.

    VS placement is reconstructed from the virtualservice-inventory placement map
    (vip_summary[].service_engine[]). Use when VS health degrades to check if the
    issue is at the SE level.
    """
    from vmware_avi.ops.se_mgmt import check_se_health
    return _capture_output(check_se_health)


# ═══════════════════════════════════════════════════════════════════════════════
# AKO mode — Kubernetes
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_status(context: Optional[str] = None) -> str:
    """[READ] Check AKO (AVI Kubernetes Operator) pod status — running, restarts, age, and ready state.

    First step when troubleshooting Ingress or LoadBalancer issues in Tanzu/K8s.

    Args:
        context: K8s context name (optional, uses current context).
    """
    from vmware_avi.ops.ako_pod import check_ako_status
    return _capture_output(check_ako_status, context)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_logs(tail: int = 100, since: Optional[str] = None) -> str:
    """[READ] View AKO pod logs to debug Ingress creation failures, sync errors, or AVI Controller connectivity issues.

    Use 'since' to narrow the time window.

    Args:
        tail: Number of log lines to show (default 100).
        since: Time filter, e.g. '30m', '1h'.
    """
    from vmware_avi.ops.ako_pod import view_ako_logs
    return _capture_output(view_ako_logs, tail, since or "", None)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="high")
def ako_restart(context: Optional[str] = None, confirmed: bool = False) -> str:
    """[WRITE] Restart AKO pod by deleting it (its StatefulSet recreates it automatically).

    Use when AKO is stuck or after config changes. Brief traffic disruption possible during restart.

    SAFETY: Requires confirmed=True to execute. Default False returns a preview message
    describing the intended action.

    Args:
        context: K8s context name (optional).
        confirmed: Must be True to actually restart the AKO pod.
            Default False returns a preview-only message.
    """
    if not confirmed:
        ctx_hint = f" in context '{context}'" if context else ""
        return (
            f"[preview] Would delete the AKO pod{ctx_hint} — its StatefulSet will recreate it automatically. "
            "Brief traffic disruption is possible during restart. "
            "Re-invoke with confirmed=True to execute."
        )
    from vmware_avi.ops.ako_pod import restart_ako
    return _capture_output(restart_ako, context, skip_prompt=True)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_version(context: Optional[str] = None) -> str:
    """[READ] Show AKO version, Helm chart version, and container image tag.

    Use to verify AKO version compatibility with AVI Controller.

    Args:
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_pod import show_ako_version
    return _capture_output(show_ako_version, context)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_config_show() -> str:
    """[READ] Show current AKO Helm values.yaml configuration — controller IP, cloud name, network settings, and feature flags."""
    from vmware_avi.ops.ako_config import show_ako_config
    return _capture_output(show_ako_config)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_config_diff() -> str:
    """[READ] Show pending Helm value changes that haven't been applied yet.

    Use before ako_config_upgrade to review what will change.
    """
    from vmware_avi.ops.ako_config import diff_ako_config
    return _capture_output(diff_ako_config)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="medium")
def ako_config_upgrade(dry_run: bool = True) -> str:
    """[WRITE] Apply AKO Helm upgrade with updated values. Defaults to dry_run=true for safety.

    Discovers the AKO Helm release in avi-system automatically (official installs
    use --generate-name) and upgrades from the official Broadcom OCI chart with
    --reuse-values. Set dry_run=false to apply. Requires double confirmation for
    non-dry-run. Fails with a teaching error if no AKO release is installed.

    Args:
        dry_run: Preview changes without applying (default true).
    """
    from vmware_avi.ops.ako_config import upgrade_ako
    return _capture_output(upgrade_ako, dry_run)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_ingress_check(namespace: str, context: Optional[str] = None) -> str:
    """[READ] Validate Ingress annotations in a namespace — checks for unsupported or misspelled AKO annotations that prevent VS creation.

    Args:
        namespace: K8s namespace to check.
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_ingress import check_ingress_annotations
    return _capture_output(check_ingress_annotations, namespace, context)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_ingress_map(context: Optional[str] = None) -> str:
    """[READ] Show mapping between K8s Ingress resources and AVI Virtual Services.

    Use to verify which Ingresses have corresponding VS objects.

    Args:
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_ingress import show_ingress_map
    return _capture_output(show_ingress_map, context)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_ingress_diagnose(name: str, namespace: str = "default", context: Optional[str] = None) -> str:
    """[READ] Diagnose why a specific Ingress has no corresponding AVI Virtual Service.

    Reads the Ingress and validates three things: IngressClass is 'avi' or 'avi-lb',
    each referenced TLS secret exists, and every backend Service exists in the
    namespace. Returns the Ingress annotations, a numbered issue list, and concrete
    fix suggestions (kubectl commands). If configuration is clean, it points you to
    ako_logs and ako_sync_status as next steps. Use ako_ingress_map first to find
    which Ingresses are missing a VS, then diagnose one here.

    Args:
        name: Exact Ingress resource name. Fails with 'not found' if absent.
        namespace: K8s namespace containing the Ingress (default 'default').
        context: kubeconfig context name (optional; uses current context).
            Discover context names with ako_clusters.
    """
    from vmware_avi.ops.ako_ingress import diagnose_ingress
    return _capture_output(diagnose_ingress, name, namespace, context)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_ingress_fix_suggest(name: str, namespace: str = "default", context: Optional[str] = None) -> str:
    """[READ] Suggest specific fixes for Ingress issues — returns actionable kubectl commands or annotation corrections based on the diagnosed problem.

    Args:
        name: Ingress resource name.
        namespace: K8s namespace (default 'default').
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_ingress import diagnose_ingress
    return _capture_output(diagnose_ingress, name, namespace, context)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_sync_status(context: Optional[str] = None) -> str:
    """[READ] Check sync status between K8s resources and AVI Controller objects.

    Shows in-sync, pending, and error counts.

    Args:
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_sync import check_sync_status
    return _capture_output(check_sync_status, context)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_sync_diff(context: Optional[str] = None) -> str:
    """[READ] Show specific inconsistencies between K8s Ingress/Service definitions and AVI Controller VS/Pool objects.

    Use to identify drift.

    Args:
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_sync import show_sync_diff
    return _capture_output(show_sync_diff, context)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
@vmware_tool(risk_level="high")
def ako_sync_force(context: Optional[str] = None, confirmed: bool = False) -> str:
    """[WRITE] Force AKO to resync all K8s resources with AVI Controller.

    Use when drift is detected. May cause brief traffic disruption.

    SAFETY: Requires confirmed=True to execute. Default False returns a preview message
    describing the intended action.

    Args:
        context: K8s context name (optional).
        confirmed: Must be True to actually force the resync.
            Default False returns a preview-only message.
    """
    if not confirmed:
        ctx_hint = f" in context '{context}'" if context else ""
        return (
            f"[preview] Would force AKO to resync all K8s resources with AVI Controller{ctx_hint} "
            "(restarts AKO pod — may cause brief traffic disruption). "
            "Re-invoke with confirmed=True to execute."
        )
    from vmware_avi.ops.ako_sync import force_resync
    return _capture_output(force_resync, context, skip_prompt=True)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_clusters() -> str:
    """[READ] List every Kubernetes context in the active kubeconfig and whether AKO is deployed there.

    Iterates contexts from `kubectl config get-contexts` (KUBECONFIG env var or
    ~/.kube/config) and probes the avi-system namespace in each. Returns a table of
    Context, AKO Status (pod phase, or 'Not deployed'), and AKO Version (image tag).
    No parameters or filtering — all contexts are checked, so unreachable clusters
    add latency. Requires kubectl on PATH. Start here to discover context names,
    then pass one as `context` to ako_status, ako_logs, or ako_ingress_diagnose.
    """
    from vmware_avi.ops.ako_multi_cluster import list_clusters
    return _capture_output(list_clusters)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_cluster_overview() -> str:
    """[READ] Fleet-wide AKO health summary across all Kubernetes contexts in the active kubeconfig.

    Returns one row per context (from KUBECONFIG env var or ~/.kube/config): AKO pod
    phase (Running / Pending / 'Not deployed') and AKO version from the container
    image tag. No parameters; every context is probed via kubectl, so slow or
    unreachable clusters add latency. Use for a quick multi-cluster health check
    answering "is AKO up everywhere, and on which version?". For single-cluster
    detail, follow up with ako_status or ako_version passing a specific `context`;
    for GSLB federation health use ako_amko_status.
    """
    from vmware_avi.ops.ako_multi_cluster import list_clusters
    return _capture_output(list_clusters)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
@vmware_tool(risk_level="low")
def ako_amko_status() -> str:
    """[READ] Show AMKO (AVI Multi-Cluster Kubernetes Operator) GSLB status — global services, member clusters, and federation health."""
    from vmware_avi.ops.ako_multi_cluster import show_amko_status
    return _capture_output(show_amko_status)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Entry point for vmware-avi-mcp."""
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
