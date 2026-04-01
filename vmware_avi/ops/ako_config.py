"""AKO Helm configuration management."""

from __future__ import annotations

import subprocess

from rich.console import Console

console = Console()


def show_ako_config(namespace: str = "avi-system") -> None:
    """Show current AKO Helm values."""
    result = subprocess.run(
        ["helm", "get", "values", "ako", "-n", namespace, "-o", "yaml"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Failed to get AKO values: {result.stderr.strip()}[/red]")
        raise SystemExit(1)

    console.print("\n[bold]AKO Helm Values[/bold]\n")
    console.print(result.stdout)


def diff_ako_config(namespace: str = "avi-system") -> None:
    """Show pending Helm changes via helm diff."""
    result = subprocess.run(
        ["helm", "diff", "upgrade", "ako", "avi/ako", "-n", namespace],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(
            "[yellow]helm-diff plugin may not be installed. "
            "Install: helm plugin install https://github.com/databus23/helm-diff[/yellow]"
        )
        console.print(f"[red]{result.stderr.strip()}[/red]")
        raise SystemExit(1)

    if not result.stdout.strip():
        console.print("[green]No pending changes.[/green]")
    else:
        console.print("\n[bold]Pending Changes[/bold]\n")
        console.print(result.stdout)


def upgrade_ako(dry_run: bool = True, namespace: str = "avi-system") -> None:
    """Helm upgrade AKO with confirmation."""
    if not dry_run:
        from vmware_avi._safety import double_confirm

        if not double_confirm("Helm upgrade AKO"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    cmd = ["helm", "upgrade", "ako", "avi/ako", "-n", namespace, "--reuse-values"]
    if dry_run:
        cmd.append("--dry-run")
        console.print("[bold]Dry-run mode (preview only):[/bold]\n")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]Helm upgrade failed: {result.stderr.strip()}[/red]")
        raise SystemExit(1)

    console.print(result.stdout)
    if dry_run:
        console.print("\n[yellow]This was a dry-run. Use --no-dry-run to apply.[/yellow]")
