"""AKO Ingress annotation validation and diagnostics."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from vmware_avi.config import load_config
from vmware_avi.k8s_connection import K8sConnectionManager

console = Console()

KNOWN_AKO_ANNOTATIONS = {
    "ako.vmware.com/enable-tls",
    "ako.vmware.com/pool-name-prefix",
    "ako.vmware.com/vs-name-prefix",
    "kubernetes.io/ingress.class",
}


def check_ingress_annotations(namespace: str, context: str | None = None) -> None:
    """Validate Ingress annotations in a namespace."""
    cfg = load_config()
    k8s = K8sConnectionManager(cfg)

    from kubernetes.client import NetworkingV1Api

    net_v1 = NetworkingV1Api(k8s.get_client(context))

    ingresses = net_v1.list_namespaced_ingress(namespace)

    table = Table(title=f"Ingress Annotations Check: {namespace}")
    table.add_column("Ingress")
    table.add_column("IngressClass")
    table.add_column("Issues")
    table.add_column("Status")

    for ing in ingresses.items:
        name = ing.metadata.name
        annotations = ing.metadata.annotations or {}
        ingress_class = ing.spec.ingress_class_name or annotations.get(
            "kubernetes.io/ingress.class", ""
        )

        issues: list[str] = []

        if not ingress_class:
            issues.append("No IngressClass specified")
        elif ingress_class not in ("avi", "avi-lb"):
            issues.append(f"IngressClass '{ingress_class}' may not be AKO")

        if ing.spec.tls:
            for tls in ing.spec.tls:
                if tls.secret_name:
                    try:
                        k8s.core_v1(context).read_namespaced_secret(
                            tls.secret_name, namespace
                        )
                    except Exception as exc:
                        err_msg = str(exc)
                        if "404" in err_msg or "Not Found" in err_msg:
                            issues.append(f"TLS secret '{tls.secret_name}' not found")
                        else:
                            issues.append(f"TLS secret '{tls.secret_name}' check failed: {err_msg[:100]}")

        status = "[green]OK[/green]" if not issues else "[red]ISSUES[/red]"
        table.add_row(name, ingress_class or "N/A", "; ".join(issues) or "-", status)

    console.print(table)


def show_ingress_map(context: str | None = None) -> None:
    """Show Ingress to VS mapping across all namespaces."""
    cfg = load_config()
    k8s = K8sConnectionManager(cfg)

    from kubernetes.client import NetworkingV1Api

    net_v1 = NetworkingV1Api(k8s.get_client(context))
    ingresses = net_v1.list_ingress_for_all_namespaces()

    table = Table(title="Ingress → VS Mapping")
    table.add_column("Namespace")
    table.add_column("Ingress")
    table.add_column("Host")
    table.add_column("IngressClass")

    for ing in ingresses.items:
        ns = ing.metadata.namespace
        name = ing.metadata.name
        annotations = ing.metadata.annotations or {}
        ingress_class = ing.spec.ingress_class_name or annotations.get(
            "kubernetes.io/ingress.class", ""
        )
        hosts = []
        if ing.spec.rules:
            hosts = [r.host or "*" for r in ing.spec.rules]

        table.add_row(ns, name, ", ".join(hosts), ingress_class or "N/A")

    console.print(table)


def diagnose_ingress(
    name: str, namespace: str = "default", context: str | None = None
) -> None:
    """Deep diagnosis of a specific Ingress."""
    cfg = load_config()
    k8s = K8sConnectionManager(cfg)

    from kubernetes.client import NetworkingV1Api

    net_v1 = NetworkingV1Api(k8s.get_client(context))

    try:
        ing = net_v1.read_namespaced_ingress(name, namespace)
    except Exception:
        console.print(f"[red]Ingress '{name}' not found in namespace '{namespace}'.[/red]")
        raise SystemExit(1)

    console.print(f"\n[bold]Diagnosing Ingress: {namespace}/{name}[/bold]\n")

    annotations = ing.metadata.annotations or {}
    console.print("[bold]Annotations:[/bold]")
    for k, v in annotations.items():
        console.print(f"  {k}: {v}")

    issues: list[str] = []
    suggestions: list[str] = []

    # Check IngressClass
    ingress_class = ing.spec.ingress_class_name or annotations.get(
        "kubernetes.io/ingress.class", ""
    )
    if not ingress_class:
        issues.append("No IngressClass specified")
        suggestions.append("Add spec.ingressClassName: 'avi-lb' or annotation kubernetes.io/ingress.class: 'avi'")
    elif ingress_class not in ("avi", "avi-lb"):
        issues.append(f"IngressClass '{ingress_class}' is not AKO")
        suggestions.append(f"Change to 'avi' or 'avi-lb'")

    # Check TLS secrets
    if ing.spec.tls:
        for tls in ing.spec.tls:
            if tls.secret_name:
                try:
                    k8s.core_v1(context).read_namespaced_secret(tls.secret_name, namespace)
                except Exception as exc:
                    err_msg = str(exc)
                    if "404" in err_msg or "Not Found" in err_msg:
                        issues.append(f"TLS secret '{tls.secret_name}' missing")
                        suggestions.append(f"Create secret: kubectl create secret tls {tls.secret_name} ...")
                    else:
                        issues.append(f"TLS secret '{tls.secret_name}' check failed: {err_msg[:100]}")

    # Check backend services exist
    if ing.spec.rules:
        for rule in ing.spec.rules:
            if rule.http and rule.http.paths:
                for path in rule.http.paths:
                    if not path.backend or not path.backend.service or not path.backend.service.name:
                        issues.append("Path has no backend service configured")
                        continue
                    svc_name = path.backend.service.name
                    try:
                        k8s.core_v1(context).read_namespaced_service(svc_name, namespace)
                    except Exception:
                        issues.append(f"Backend service '{svc_name}' not found")
                        suggestions.append(f"Verify service '{svc_name}' exists in namespace '{namespace}'")

    if issues:
        console.print(f"\n[red]Issues Found ({len(issues)}):[/red]")
        for i, issue in enumerate(issues, 1):
            console.print(f"  {i}. {issue}")
        console.print(f"\n[yellow]Suggestions:[/yellow]")
        for i, sug in enumerate(suggestions, 1):
            console.print(f"  {i}. {sug}")
    else:
        console.print("\n[green]No issues found with Ingress configuration.[/green]")
        console.print("If VS is still not created, check AKO logs and sync status:")
        console.print("  vmware-avi ako logs --since 5m")
        console.print("  vmware-avi ako sync status")
    console.print()
