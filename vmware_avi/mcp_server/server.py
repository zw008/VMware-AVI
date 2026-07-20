"""MCP Server for VMware AVI — stdio transport.

Exposes 28 tools (22 read, 6 write) for AVI Controller + AKO K8s operations.
Entry point: vmware-avi-mcp (defined in pyproject.toml).
"""

import logging
import os
from pathlib import Path
from io import StringIO
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from vmware_policy import (
    apply_read_only_gate,
    mtime_cached_loader,
    sanitize,
    set_environment_resolver,
    vmware_tool,
)

from vmware_avi.connection import AviApiError

_log = logging.getLogger("vmware-avi-mcp")

mcp = FastMCP("vmware-avi")


# ---------------------------------------------------------------------------
# Output capture helper
# ---------------------------------------------------------------------------


_DOCTOR_HINT = "Run 'vmware-avi doctor' to verify Controller connectivity and credentials."


def _safe_error(exc: Exception, tool: str) -> str:
    """Return an agent-safe error string; log full detail server-side only.

    Raw exception text can carry Controller response bodies, credentials in
    URLs, or internal paths.

    The rule is a property, not a list: every exception this skill raises on
    purpose passes through — the builtin validation errors and this skill's own
    ``AviApiError``, which already carries a teaching message — and only
    genuinely unplanned ones are reduced. The enumeration below is the
    mechanical expression of that rule, and it drifts.

    ``OSError`` is allowed because ``config.py`` raises exactly one — the
    missing-password error, this family's most common first-run failure, whose
    entire remedy is the env var name it carries. Its subclasses
    ``FileNotFoundError``, ``PermissionError``, ``TimeoutError`` and
    ``ConnectionError`` were already allowed, so admitting the base class
    widens exposure only to the remaining OS-level subtypes.

    Anything else is reduced to its type, because an unplanned exception's text
    was written for a developer reading a traceback, not for an agent deciding
    what to do next, and it is the one that can carry credentials.
    """
    _log.error("Tool %s failed", tool, exc_info=True)
    _passthrough = (
        ValueError,
        FileNotFoundError,
        KeyError,
        PermissionError,
        TimeoutError,
        ConnectionError,
        OSError,
        AviApiError,
    )
    if isinstance(exc, _passthrough):
        return sanitize(str(exc), 300)
    return f"{type(exc).__name__}: operation failed."


def _as_error(captured: str, detail: str = "") -> str:
    """Render a failed run as a payload no reader can mistake for output.

    The ops layer reports failure the way a CLI does — print, then exit — so the
    useful teaching text is already in ``captured`` and is kept verbatim. What
    was missing is any marker that the run failed at all: without the prefix the
    model receives a red "not found" message as an ordinary successful result
    and reports it to the user as a finding (issue #31's failure mode).

    ``_DOCTOR_HINT`` is appended only when the captured text names nothing to
    act on. When the ops message already says which tool to run, repeating a
    generic "run doctor" would bury the specific advice under worse advice.
    """
    body = " ".join((captured or "").split()) or detail
    if detail and detail not in body:
        body = f"{body} {detail}".strip()
    if "vmware-avi" not in body:
        body = f"{body} {_DOCTOR_HINT}".strip()
    return f"Error: {body}"


def _capture_output(func, *args, **kwargs) -> str:
    """Run a function and capture its Rich console output as plain text.

    Failures come back as an ``Error: ...`` payload rather than as the text the
    function happened to print before dying.
    """
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
    except SystemExit as exc:
        # A CLI ops function signals failure by exiting non-zero. `SystemExit(0)`
        # is an early return — "nothing to do" — and is not a failure.
        if exc.code:
            return _as_error(buf.getvalue())
    except Exception as exc:  # noqa: BLE001 — reduced to a safe string below
        return _as_error(buf.getvalue(), _safe_error(exc, getattr(func, "__name__", "?")))
    finally:
        if mod and original_console is not None:
            mod.console = original_console

    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# Traditional mode — AVI Controller
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def vs_list(controller: Optional[str] = None) -> str:
    """[READ] List all Virtual Services with name, VIP, enabled state, and health score.

    Use this for an overview before drilling into a specific VS with vs_status.

    Args:
        controller: AVI controller name from config (optional, uses default).
    """
    from vmware_avi.ops.vs_mgmt import list_virtual_services

    return _capture_output(list_virtual_services, controller)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def vs_status(name: str) -> str:
    """[READ] Show detailed status for a specific Virtual Service — VIP, pool,
    health, connections, and throughput.

    Use vs_list first to find the exact VS name.

    Args:
        name: Exact Virtual Service name.
    """
    from vmware_avi.ops.vs_mgmt import show_vs_status

    return _capture_output(show_vs_status, name)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
@vmware_tool(
    risk_level="high",
    undo=lambda params, result: (
        None
        if isinstance(result, str) and result.startswith("[preview]")
        else {
            "tool": "vs_toggle",
            "params": {
                "name": params.get("name"),
                "enable": not params.get("enable"),
                "confirmed": True,
            },
            "skill": "avi",
            "note": "Inverse of vs_toggle: toggle the Virtual Service back to its prior state.",
        }
    ),
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="high")
def pool_member_disable(pool: str, server: str, confirmed: bool = False) -> str:
    """[WRITE] Disable a pool member with graceful drain — existing connections
    complete, no new traffic.

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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ssl_expiry_check(days: int = 30) -> str:
    """[READ] Check which SSL certificates expire within N days (default 30).

    Returns certificate name, expiry date, and days remaining. Run regularly to prevent outages.

    Args:
        days: Check certs expiring within this many days (default 30).
    """
    from vmware_avi.ops.ssl_mgmt import check_expiry

    return _capture_output(check_expiry, days)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def vs_error_logs(vs_name: str, since: str = "1h") -> str:
    """[READ] Show recent request error logs for a Virtual Service — HTTP status
    codes, client IPs, URIs, and response times.

    Use to diagnose 5xx errors or latency spikes.

    Args:
        vs_name: Virtual Service name.
        since: Time window, e.g. '1h', '30m', '2d' (default '1h').
    """
    from vmware_avi.ops.analytics import show_error_logs

    return _capture_output(show_error_logs, vs_name, since)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_status(context: Optional[str] = None) -> str:
    """[READ] Check AKO (AVI Kubernetes Operator) pod status — running, restarts,
    age, and ready state.

    First step when troubleshooting Ingress or LoadBalancer issues in Tanzu/K8s.

    Args:
        context: K8s context name (optional, uses current context).
    """
    from vmware_avi.ops.ako_pod import check_ako_status

    return _capture_output(check_ako_status, context)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_logs(tail: int = 100, since: Optional[str] = None, context: Optional[str] = None) -> str:
    """[READ] View AKO pod logs to debug Ingress creation failures, sync errors,
    or AVI Controller connectivity issues.

    Use 'since' to narrow the time window.

    Args:
        tail: Number of log lines to show (default 100).
        since: Time filter, e.g. '30m', '1h'.
        context: K8s context name (optional, uses current context).
    """
    from vmware_avi.ops.ako_pod import view_ako_logs

    return _capture_output(view_ako_logs, tail, since or "", context)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
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
            f"[preview] Would delete the AKO pod{ctx_hint} — "
            "its StatefulSet will recreate it automatically. "
            "Brief traffic disruption is possible during restart. "
            "Re-invoke with confirmed=True to execute."
        )
    from vmware_avi.ops.ako_pod import restart_ako

    return _capture_output(restart_ako, context, skip_prompt=True)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_version(context: Optional[str] = None) -> str:
    """[READ] Show AKO version, Helm chart version, and container image tag.

    Use to verify AKO version compatibility with AVI Controller.

    Args:
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_pod import show_ako_version

    return _capture_output(show_ako_version, context)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_config_show() -> str:
    """[READ] Show current AKO Helm values.yaml configuration — controller IP,
    cloud name, network settings, and feature flags."""
    from vmware_avi.ops.ako_config import show_ako_config

    return _capture_output(show_ako_config)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_config_diff(chart_version: str = "") -> str:
    """[READ] Show pending Helm value changes that haven't been applied yet.

    Use before ako_config_upgrade to review what will change. Runs the same
    helm command ako_config_upgrade does, --reuse-values included, so the
    preview describes the actual upgrade rather than the chart's defaults.

    Gotcha: with chart_version empty this resolves whatever the Broadcom
    registry currently tags latest, so two runs can differ with no local
    change. Read the installed version with ako_version and pass it to both
    tools when you need the preview and the apply to target one chart.

    Args:
        chart_version: Pin the chart version to compare against, e.g. "1.11.1".
            Empty (default) uses the registry's current latest.
    """
    from vmware_avi.ops.ako_config import diff_ako_config

    return _capture_output(diff_ako_config, chart_version=chart_version)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="medium")
def ako_config_upgrade(
    dry_run: bool = True, confirmed: bool = False, chart_version: str = ""
) -> str:
    """[WRITE] Apply AKO Helm upgrade with updated values. Defaults to dry_run=true for safety.

    Discovers the AKO Helm release in avi-system automatically (official installs
    use --generate-name) and upgrades from the official Broadcom OCI chart with
    --reuse-values. Set dry_run=false to apply. Fails with a teaching error if no
    AKO release is installed.

    SAFETY: When dry_run=False, requires confirmed=True to execute. Default False
    returns a preview message describing the intended action. Dry-run is always
    safe and does not require confirmation.

    Args:
        dry_run: Preview changes without applying (default true).
        confirmed: Must be True when dry_run=False to actually apply the upgrade.
            Default False returns a preview-only message. Ignored when dry_run=True.
        chart_version: Pin the chart version to upgrade to, e.g. "1.11.1". Empty
            (default) takes the registry's current latest, which can move
            between an ako_config_diff call and this one.
    """
    from vmware_avi.ops.ako_config import upgrade_ako

    if not dry_run and not confirmed:
        return (
            "[preview] Would helm-upgrade the AKO release in avi-system from the "
            f"official Broadcom OCI chart ({chart_version or 'registry latest'}) "
            "with --reuse-values. "
            "Re-invoke with confirmed=True to execute, or use dry_run=True to preview."
        )
    return _capture_output(
        upgrade_ako, dry_run, chart_version=chart_version, skip_prompt=True
    )


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_ingress_check(namespace: str, context: Optional[str] = None) -> str:
    """[READ] Validate Ingress annotations in a namespace — checks for unsupported
    or misspelled AKO annotations that prevent VS creation.

    Args:
        namespace: K8s namespace to check.
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_ingress import check_ingress_annotations

    return _capture_output(check_ingress_annotations, namespace, context)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_ingress_map(context: Optional[str] = None) -> str:
    """[READ] Show mapping between K8s Ingress resources and AVI Virtual Services.

    Use to verify which Ingresses have corresponding VS objects.

    Args:
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_ingress import show_ingress_map

    return _capture_output(show_ingress_map, context)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_ingress_diagnose(
    name: str, namespace: str = "default", context: Optional[str] = None
) -> str:
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_sync_status(context: Optional[str] = None) -> str:
    """[READ] Check sync status between K8s resources and AVI Controller objects.

    Shows in-sync, pending, and error counts.

    Args:
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_sync import check_sync_status

    return _capture_output(check_sync_status, context)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_sync_diff(context: Optional[str] = None) -> str:
    """[READ] Show specific inconsistencies between K8s Ingress/Service definitions
    and AVI Controller VS/Pool objects.

    Use to identify drift.

    Args:
        context: K8s context name (optional).
    """
    from vmware_avi.ops.ako_sync import show_sync_diff

    return _capture_output(show_sync_diff, context)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_clusters() -> str:
    """[READ] List every Kubernetes context in the active kubeconfig and whether
    AKO is deployed there.

    Iterates contexts from `kubectl config get-contexts` (KUBECONFIG env var or
    ~/.kube/config) and probes the avi-system namespace in each. Returns a table of
    Context, AKO Status (pod phase, or 'Not deployed'), and AKO Version (image tag).
    No parameters or filtering — all contexts are checked, so unreachable clusters
    add latency. Requires kubectl on PATH. Start here to discover context names,
    then pass one as `context` to ako_status, ako_logs, or ako_ingress_diagnose.
    """
    from vmware_avi.ops.ako_multi_cluster import list_clusters

    return _capture_output(list_clusters)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
@vmware_tool(risk_level="low")
def ako_amko_status() -> str:
    """[READ] Show AMKO (AVI Multi-Cluster Kubernetes Operator) GSLB status —
    global services, member clusters, and federation health."""
    from vmware_avi.ops.ako_multi_cluster import show_amko_status

    return _capture_output(show_amko_status)


# ═══════════════════════════════════════════════════════════════════════════════
# Read-only gate
# ═══════════════════════════════════════════════════════════════════════════════


def _config_read_only() -> Optional[bool]:
    """Best-effort read of ``read_only`` from the config file.

    Runs at import time, when no config file need exist yet (tests, ``--help``,
    smoke checks), so every failure degrades to "not configured" and lets the
    env vars decide. None and False are equivalent here — config is the last
    link in the precedence chain — but None keeps 'not configured'
    distinguishable from 'configured off' in logs and debugging.

    Resolved through the same VMWARE_AVI_CONFIG override the connection layer
    uses. Reading the default path instead would silently ignore settings in an
    operator's custom config file — a control that appears configured and does
    nothing, which is the exact failure this work exists to remove.
    """
    try:
        from vmware_avi.config import load_config

        _cfg_path = os.environ.get("VMWARE_AVI_CONFIG")
        return load_config(Path(_cfg_path) if _cfg_path else None).read_only
    except Exception:  # noqa: BLE001 — absent/unreadable config is not an error here
        return None


# Applied once, after every tool module above has registered. In read-only mode
# the write tools are removed from the registry, so list_tools() never offers
# them — the guarantee is structural rather than a prompt instruction the model
# may ignore (VMware-AIops issue #31).
WITHHELD_WRITE_TOOLS: list[str] = apply_read_only_gate(
    mcp, "vmware-avi", config_flag=_config_read_only()
)


# ═══════════════════════════════════════════════════════════════════════════════
# Environment declaration
# ═══════════════════════════════════════════════════════════════════════════════


def _load_config(config_path: Optional[Path]) -> Any:
    """Deferred-import shim for the mtime cache — this module keeps
    vmware_avi imports inside functions, matching the gate section above."""
    from vmware_avi.config import load_config

    return load_config(config_path)


_cached_config = mtime_cached_loader(
    "VMWARE_AVI_CONFIG",
    Path.home() / ".vmware-avi" / "config.yaml",  # mirrors vmware_avi.config.CONFIG_FILE
    _load_config,
)


def _environment_for(target: Optional[str]) -> str:
    """Report the environment a controller declares, for policy scoping.

    Policy rules scope by environment ("irreversible work in production needs a
    second person"), and vmware-policy cannot read this skill's config itself.
    Registering this lookup is what lets those rules fire at all. Reloaded on
    config.yaml mtime change so an edit takes effect without restarting the
    server, and resolved through the same VMWARE_AVI_CONFIG override the
    connection layer uses so both agree on which file is in force. The config
    is cached via :func:`vmware_policy.mtime_cached_loader`, so repeated tool
    calls pay one ``os.stat`` instead of a full YAML parse.
    """
    try:
        return _cached_config().environment_for(target)
    except Exception:  # noqa: BLE001 — an unreadable config means "undeclared"
        return ""


set_environment_resolver(_environment_for)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    """Entry point for vmware-avi-mcp."""
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
