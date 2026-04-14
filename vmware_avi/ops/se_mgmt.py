"""Service Engine management operations."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from vmware_avi.config import load_config
from vmware_avi.connection import AviConnectionManager

console = Console()


def list_service_engines() -> None:
    """List all Service Engines."""
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    resp = session.get("serviceengine")
    ses = resp.json().get("results", [])

    table = Table(title="Service Engines")
    table.add_column("Name")
    table.add_column("IP")
    table.add_column("Status")
    table.add_column("SE Group")

    for se in ses:
        name = se.get("name", "")
        mgmt_ip = se.get("mgmt_vnic", {}).get("vnic_networks", [{}])[0].get(
            "ip", {}).get("ip_addr", {}).get("addr", "N/A")
        oper = se.get("oper_status", {}).get("state", "N/A")
        se_group = se.get("se_group_ref", "").split("/")[-1].split("?")[0]
        table.add_row(name, mgmt_ip, oper, se_group)

    console.print(table)


def check_se_health() -> None:
    """Check SE health and resource usage.

    VS count is derived from serviceengine-inventory ``runtime.se_vs_list`` or
    ``runtime.vs_ref`` (name varies by Controller version). The previous
    ``runtime.virtualservice_refs`` path is not populated on 22.x builds and
    always returned 0, giving false "idle SE" signals.
    """
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    resp = session.get("serviceengine-inventory")
    ses = (resp.json() if hasattr(resp, "json") else resp).get("results", [])

    console.print("\n[bold]Service Engine Health[/bold]")
    for se in ses:
        cfg_data = se.get("config", {}) or {}
        runtime = se.get("runtime", {}) or {}
        name = cfg_data.get("name", "N/A")
        oper = (runtime.get("oper_status", {}) or {}).get("state", "N/A")

        # VS count — try multiple known field names across Controller versions.
        # Fall back to aggregate counters if per-SE list is absent.
        vs_list = (
            runtime.get("se_vs_list")
            or runtime.get("vs_ref")
            or runtime.get("virtualservice_refs")
            or []
        )
        vs_count = len(vs_list) if isinstance(vs_list, list) else 0
        if vs_count == 0:
            # Aggregate from vip_summary if available
            vs_count = runtime.get("num_vs") or runtime.get("num_se_dps", 0)

        status_color = "green" if oper == "OPER_UP" else "red"
        console.print(
            f"  [{status_color}]{name}[/{status_color}]: {oper}, "
            f"VS count: {vs_count}"
        )

    console.print()
