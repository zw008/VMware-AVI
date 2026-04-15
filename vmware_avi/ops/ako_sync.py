"""K8s-Controller sync diagnostics."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from vmware_avi.config import load_config
from vmware_avi.connection import AviConnectionManager
from vmware_avi.k8s_connection import K8sConnectionManager

console = Console()


def check_sync_status(context: str | None = None) -> None:
    """Check whether K8s Ingress objects are in sync with AVI Controller VS objects."""
    cfg = load_config()
    k8s = K8sConnectionManager(cfg)

    from kubernetes.client import NetworkingV1Api

    net_v1 = NetworkingV1Api(k8s.get_client(context))
    ingresses = net_v1.list_ingress_for_all_namespaces()
    k8s_count = len(ingresses.items)

    mgr = AviConnectionManager(cfg)
    session = mgr.connect()
    resp = session.get("virtualservice", params={"page_size": "1000"})
    vs_list = resp.json().get("results", [])
    avi_count = len(vs_list)

    console.print("\n[bold]Sync Status[/bold]")
    console.print(f"  K8s Ingress objects: {k8s_count}")
    console.print(f"  AVI Virtual Services: {avi_count}")

    if k8s_count == avi_count:
        console.print("  [green]Counts match (basic check OK).[/green]")
    else:
        console.print(
            f"  [yellow]Count mismatch: {k8s_count} Ingresses vs {avi_count} VS. "
            "Run 'vmware-avi ako sync diff' for details.[/yellow]"
        )
    console.print()


def show_sync_diff(context: str | None = None) -> None:
    """Show specific inconsistencies between K8s and AVI Controller."""
    cfg = load_config()
    k8s = K8sConnectionManager(cfg)

    from kubernetes.client import NetworkingV1Api

    net_v1 = NetworkingV1Api(k8s.get_client(context))
    ingresses = net_v1.list_ingress_for_all_namespaces()
    k8s_names = {
        f"{ing.metadata.namespace}/{ing.metadata.name}" for ing in ingresses.items
    }

    mgr = AviConnectionManager(cfg)
    session = mgr.connect()
    resp = session.get("virtualservice", params={"page_size": "1000"})
    vs_list = resp.json().get("results", [])
    avi_names = {vs.get("name", "") for vs in vs_list}

    table = Table(title="Sync Diff")
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Status")

    for name in sorted(k8s_names):
        short = name.split("/")[-1]
        if not any(short in avi_name for avi_name in avi_names):
            table.add_row("Ingress", name, "[red]Missing on Controller[/red]")

    console.print(table)
    console.print()


def force_resync(context: str | None = None, *, skip_prompt: bool = False) -> None:
    """Force AKO to resync by restarting the pod.

    Args:
        context: K8s context name (optional, uses current context).
        skip_prompt: When True, bypass the interactive double-confirm prompt.
            Used by MCP callers that enforce confirmation via the ``confirmed``
            parameter before reaching this function.
    """
    if not skip_prompt:
        from vmware_avi._safety import double_confirm

        if not double_confirm("Force AKO resync (restarts AKO pod)"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    cfg = load_config()
    k8s = K8sConnectionManager(cfg)
    v1 = k8s.core_v1(context)
    ns = k8s.namespace

    from vmware_avi.ops.ako_pod import _get_ako_pod_name

    pod_name = _get_ako_pod_name(v1, ns)
    v1.delete_namespaced_pod(pod_name, ns)
    console.print(
        f"[green]AKO pod '{pod_name}' deleted to trigger full resync. "
        "Deployment will recreate it.[/green]"
    )
