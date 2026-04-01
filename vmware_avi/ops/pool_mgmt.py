"""Pool member management operations."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from vmware_avi.config import load_config
from vmware_avi.connection import AviConnectionManager

console = Console()


def list_pool_members(pool_name: str) -> None:
    """List pool members with health status."""
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    pool = session.get_object_by_name("pool", pool_name)
    if not pool:
        console.print(f"[red]Pool '{pool_name}' not found.[/red]")
        raise SystemExit(1)

    servers = pool.get("servers", [])

    table = Table(title=f"Pool: {pool_name}")
    table.add_column("Server IP")
    table.add_column("Port")
    table.add_column("Enabled")
    table.add_column("Ratio")

    for s in servers:
        ip = s.get("ip", {}).get("addr", "N/A")
        port = str(s.get("port", "default"))
        enabled = "[green]Yes[/green]" if s.get("enabled", True) else "[red]No[/red]"
        ratio = str(s.get("ratio", 1))
        table.add_row(ip, port, enabled, ratio)

    console.print(table)
    console.print(f"  Total members: {len(servers)}")


def toggle_pool_member(pool_name: str, server_ip: str, *, enable: bool) -> None:
    """Enable or disable a pool member."""
    action = "enable" if enable else "disable"

    if not enable:
        from vmware_avi._safety import double_confirm

        if not double_confirm(f"Disable pool member '{server_ip}' in '{pool_name}'"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    pool = session.get_object_by_name("pool", pool_name)
    if not pool:
        console.print(f"[red]Pool '{pool_name}' not found.[/red]")
        raise SystemExit(1)

    found = False
    for s in pool.get("servers", []):
        if s.get("ip", {}).get("addr") == server_ip:
            s["enabled"] = enable
            found = True
            break

    if not found:
        console.print(f"[red]Server '{server_ip}' not found in pool '{pool_name}'.[/red]")
        raise SystemExit(1)

    session.put(f"pool/{pool['uuid']}", data=pool)
    console.print(f"[green]Pool member '{server_ip}' {action}d in '{pool_name}'.[/green]")
