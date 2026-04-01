"""VS analytics and error log operations."""

from __future__ import annotations

from rich.console import Console

from vmware_avi.config import load_config
from vmware_avi.connection import AviConnectionManager

console = Console()


def show_analytics(vs_name: str) -> None:
    """Show VS metrics overview."""
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    vs = session.get_object_by_name("virtualservice", vs_name)
    if not vs:
        console.print(f"[red]Virtual Service '{vs_name}' not found.[/red]")
        raise SystemExit(1)

    uuid = vs["uuid"]
    resp = session.get(f"analytics/metrics/virtualservice/{uuid}", params={
        "metric_id": "l4_client.avg_bandwidth,l7_client.avg_resp_latency,"
                     "l7_client.pct_response_errors,l7_client.sum_total_responses",
        "step": "300",
        "limit": "12",
    })
    data = resp.json()

    console.print(f"\n[bold]Analytics: {vs_name}[/bold]")
    for series in data.get("series", []):
        metric = series.get("header", {}).get("name", "unknown")
        values = series.get("data", [])
        if values:
            latest = values[-1].get("value", "N/A")
            console.print(f"  {metric}: {latest}")

    console.print()


def show_error_logs(vs_name: str, since: str = "1h") -> None:
    """Show request error logs for a VS."""
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    vs = session.get_object_by_name("virtualservice", vs_name)
    if not vs:
        console.print(f"[red]Virtual Service '{vs_name}' not found.[/red]")
        raise SystemExit(1)

    uuid = vs["uuid"]
    resp = session.get(f"analytics/logs", params={
        "type": "1",
        "filter": f"co(vs_uuid,{uuid}),ne(response_code,200)",
        "page_size": "50",
        "duration": since,
    })
    logs = resp.json().get("results", [])

    console.print(f"\n[bold]Error Logs: {vs_name} (last {since})[/bold]")
    for log in logs:
        ts = log.get("report_timestamp", "")
        code = log.get("response_code", "")
        uri = log.get("uri_path", "")[:80]
        client = log.get("client_ip", "")
        console.print(f"  [{ts}] {code} {uri} from {client}")

    if not logs:
        console.print("  [green]No errors found.[/green]")
    console.print()
