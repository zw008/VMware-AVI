"""AKO Helm configuration management."""

from __future__ import annotations

import json
import subprocess

from rich.console import Console

console = Console()

# Official AKO chart location (Broadcom OCI registry). The legacy repo-alias
# form `avi/ako` was never the published install path.
AKO_OCI_CHART = "oci://projects.packages.broadcom.com/ako/helm-charts/ako"


def _find_ako_release(namespace: str) -> str:
    """Discover the AKO Helm release name in the given namespace.

    Official AKO installs use ``helm install --generate-name``, so the
    release is not reliably named 'ako'. Find it via ``helm list`` by
    matching the chart name prefix. Exits with a teaching error if no AKO
    release exists.
    """
    result = subprocess.run(
        ["helm", "list", "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        console.print(f"[red]helm list failed: {result.stderr.strip()}[/red]")
        raise SystemExit(1)

    try:
        releases = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        releases = []

    for rel in releases:
        if str(rel.get("chart", "")).startswith("ako"):
            return str(rel.get("name", ""))

    console.print(
        f"[red]No AKO Helm release found in namespace '{namespace}'.[/red]\n"
        f"Inspect installed releases with: helm list -n {namespace}\n"
        f"Install AKO with: helm install --generate-name {AKO_OCI_CHART} "
        f"--version <ako-version> -f values.yaml -n {namespace}"
    )
    raise SystemExit(1)


def show_ako_config(namespace: str = "avi-system") -> None:
    """Show current AKO Helm values."""
    release = _find_ako_release(namespace)
    result = subprocess.run(
        ["helm", "get", "values", release, "-n", namespace, "-o", "yaml"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        console.print(f"[red]Failed to get AKO values: {result.stderr.strip()}[/red]")
        raise SystemExit(1)

    console.print(f"\n[bold]AKO Helm Values (release: {release})[/bold]\n")
    console.print(result.stdout)


def diff_ako_config(namespace: str = "avi-system") -> None:
    """Show pending Helm changes via helm diff."""
    release = _find_ako_release(namespace)
    result = subprocess.run(
        ["helm", "diff", "upgrade", release, AKO_OCI_CHART, "-n", namespace],
        capture_output=True,
        text=True,
        timeout=120,
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


def upgrade_ako(
    dry_run: bool = True, namespace: str = "avi-system", *, skip_prompt: bool = False
) -> None:
    """Helm upgrade AKO with confirmation.

    Args:
        dry_run: Preview changes without applying (default True).
        namespace: K8s namespace hosting the AKO release.
        skip_prompt: When True, bypass the interactive double-confirm prompt.
            Used by MCP callers that enforce confirmation via the ``confirmed``
            parameter before reaching this function.
    """
    release = _find_ako_release(namespace)

    if not dry_run and not skip_prompt:
        from vmware_avi._safety import double_confirm

        if not double_confirm(f"Helm upgrade AKO release '{release}'"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    cmd = ["helm", "upgrade", release, AKO_OCI_CHART, "-n", namespace, "--reuse-values"]
    if dry_run:
        cmd.append("--dry-run")
        console.print("[bold]Dry-run mode (preview only):[/bold]\n")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        console.print(f"[red]Helm upgrade failed: {result.stderr.strip()}[/red]")
        raise SystemExit(1)

    console.print(result.stdout)
    if dry_run:
        console.print("\n[yellow]This was a dry-run. Use --no-dry-run to apply.[/yellow]")
