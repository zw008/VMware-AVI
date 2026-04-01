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
    """Check SE health and resource usage."""
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    resp = session.get("serviceengine-inventory")
    ses = resp.json().get("results", [])

    console.print("\n[bold]Service Engine Health[/bold]")
    for se in ses:
        cfg_data = se.get("config", {})
        runtime = se.get("runtime", {})
        name = cfg_data.get("name", "N/A")
        oper = runtime.get("oper_status", {}).get("state", "N/A")
        vs_count = len(runtime.get("virtualservice_refs", []))

        status_color = "green" if oper == "OPER_UP" else "red"
        console.print(
            f"  [{status_color}]{name}[/{status_color}]: {oper}, "
            f"VS count: {vs_count}"
        )

    console.print()
