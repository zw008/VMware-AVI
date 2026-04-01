"""Virtual Service management operations."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from vmware_avi.config import load_config
from vmware_avi.connection import AviConnectionManager

console = Console()


def _sanitize(text: str, max_len: int = 500) -> str:
    """Truncate and strip control characters from API text."""
    cleaned = "".join(c for c in text[:max_len] if c.isprintable() or c in "\n\t")
    return cleaned


def list_virtual_services(controller_name: str | None = None) -> None:
    """List all Virtual Services with status."""
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect(controller_name)

    resp = session.get("virtualservice", params={"fields": "name,enabled,uuid,vip"})
    results = resp.json().get("results", [])

    table = Table(title="Virtual Services")
    table.add_column("Name")
    table.add_column("Enabled")
    table.add_column("VIP")
    table.add_column("UUID", style="dim")

    for vs in results:
        name = _sanitize(vs.get("name", ""))
        enabled = "[green]Yes[/green]" if vs.get("enabled", True) else "[red]No[/red]"
        vips = vs.get("vip", [])
        vip_str = vips[0].get("ip_address", {}).get("addr", "N/A") if vips else "N/A"
        uuid = vs.get("uuid", "")[:12]
        table.add_row(name, enabled, vip_str, uuid)

    console.print(table)


def show_vs_status(name: str) -> None:
    """Show detailed VS status."""
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    vs = session.get_object_by_name("virtualservice", name)
    if not vs:
        console.print(f"[red]Virtual Service '{name}' not found.[/red]")
        raise SystemExit(1)

    console.print(f"\n[bold]{_sanitize(vs['name'])}[/bold]")
    console.print(f"  Enabled: {vs.get('enabled', True)}")
    console.print(f"  UUID: {vs.get('uuid', 'N/A')}")

    vips = vs.get("vip", [])
    if vips:
        console.print(f"  VIP: {vips[0].get('ip_address', {}).get('addr', 'N/A')}")

    pool_ref = vs.get("pool_ref", "")
    if pool_ref:
        pool_name = pool_ref.split("/")[-1].split("?")[0]
        console.print(f"  Pool: {pool_name}")

    console.print()


def toggle_vs(name: str, *, enable: bool) -> None:
    """Enable or disable a Virtual Service."""
    action = "enable" if enable else "disable"

    if not enable:
        from vmware_avi._safety import double_confirm

        if not double_confirm(f"Disable Virtual Service '{name}'"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    vs = session.get_object_by_name("virtualservice", name)
    if not vs:
        console.print(f"[red]Virtual Service '{name}' not found.[/red]")
        raise SystemExit(1)

    vs["enabled"] = enable
    session.put(f"virtualservice/{vs['uuid']}", data=vs)
    console.print(f"[green]Virtual Service '{name}' {action}d.[/green]")
