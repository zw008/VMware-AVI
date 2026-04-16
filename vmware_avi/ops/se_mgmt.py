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

    VS count is reconstructed by inverting the VS→SE placement map from
    ``/virtualservice-inventory`` (``runtime.vip_summary[].service_engine[]``).
    On 22.x Controllers the per-SE ``runtime`` object does not expose any
    VS list field, so the previous attempts at ``se_vs_list`` / ``vs_ref`` /
    ``virtualservice_refs`` always produced 0 and gave false "idle SE"
    signals.
    """
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    # Build SE-UUID → set of VS-UUIDs it hosts, then collapse to counts.
    # De-duping per VS (not per (VS, VIP) pair) ensures a VS with multiple
    # VIPs landing on the same SE still only counts once.
    vs_resp = session.get("virtualservice-inventory")
    se_vs_map: dict[str, set[str]] = {}
    for vs in (vs_resp.json() if hasattr(vs_resp, "json") else vs_resp).get("results", []):
        vs_uuid = vs.get("uuid") or (vs.get("config") or {}).get("uuid", "")
        if not vs_uuid:
            continue
        runtime = vs.get("runtime") or {}
        for vip in runtime.get("vip_summary") or []:
            for se in vip.get("service_engine") or []:
                se_uuid = se.get("uuid")
                if se_uuid:
                    se_vs_map.setdefault(se_uuid, set()).add(vs_uuid)

    resp = session.get("serviceengine-inventory")
    ses = (resp.json() if hasattr(resp, "json") else resp).get("results", [])

    console.print("\n[bold]Service Engine Health[/bold]")
    for se in ses:
        cfg_data = se.get("config", {}) or {}
        runtime = se.get("runtime", {}) or {}
        name = cfg_data.get("name", "N/A")
        uuid = se.get("uuid") or cfg_data.get("uuid", "")
        oper = (runtime.get("oper_status", {}) or {}).get("state", "N/A")
        vs_count = len(se_vs_map.get(uuid, set()))

        status_color = "green" if oper == "OPER_UP" else "red"
        console.print(
            f"  [{status_color}]{name}[/{status_color}]: {oper}, "
            f"VS count: {vs_count}"
        )

    console.print()
