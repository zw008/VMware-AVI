"""Multi-cluster AKO and AMKO status operations."""

from __future__ import annotations

import subprocess

from rich.console import Console
from rich.table import Table

console = Console()


def list_clusters() -> None:
    """List all K8s contexts and their AKO deployment status."""
    result = subprocess.run(
        ["kubectl", "config", "get-contexts", "-o", "name"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        console.print(f"[red]Failed to list contexts: {result.stderr.strip()}[/red]")
        raise SystemExit(1)

    contexts = [c.strip() for c in result.stdout.strip().split("\n") if c.strip()]

    table = Table(title="AKO Cluster Overview")
    table.add_column("Context")
    table.add_column("AKO Status")
    table.add_column("AKO Version")

    for ctx in contexts:
        pod_check = subprocess.run(
            [
                "kubectl", "--context", ctx,
                "get", "pods", "-n", "avi-system",
                "-l", "app.kubernetes.io/name=ako",
                "-o", "jsonpath={.items[0].status.phase}:{.items[0].spec.containers[0].image}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if pod_check.returncode == 0 and pod_check.stdout:
            parts = pod_check.stdout.split(":", 1)
            phase = parts[0] if parts else "Unknown"
            image = parts[1] if len(parts) > 1 else "N/A"
            version = image.split(":")[-1] if ":" in image else "latest"
            status_color = "green" if phase == "Running" else "red"
            table.add_row(ctx, f"[{status_color}]{phase}[/{status_color}]", version)
        else:
            table.add_row(ctx, "[dim]Not deployed[/dim]", "-")

    console.print(table)


def show_amko_status() -> None:
    """Show AMKO (multi-cluster GSLB) status."""
    result = subprocess.run(
        [
            "kubectl", "get", "pods", "-n", "avi-system",
            "-l", "app=amko",
            "-o", "wide",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    console.print("\n[bold]AMKO Status[/bold]\n")
    if result.returncode != 0 or not result.stdout.strip():
        console.print("  [dim]AMKO not deployed in avi-system namespace.[/dim]")
    else:
        console.print(result.stdout)

    gslb_check = subprocess.run(
        ["kubectl", "get", "gslbconfig", "-n", "avi-system", "-o", "yaml"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if gslb_check.returncode == 0 and gslb_check.stdout.strip():
        console.print("\n[bold]GSLBConfig:[/bold]\n")
        console.print(gslb_check.stdout)
    console.print()
