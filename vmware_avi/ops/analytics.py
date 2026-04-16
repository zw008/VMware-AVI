"""VS analytics and error log operations."""

from __future__ import annotations

import re

from rich.console import Console
from rich.table import Table

from vmware_avi.config import load_config
from vmware_avi.connection import AviConnectionManager

console = Console()


def _parse_duration_seconds(value: str | int) -> int:
    """Parse a duration string (e.g. '1h', '30m', '24h', '7d') to seconds.

    The AVI analytics API requires duration as a non-negative integer number
    of seconds. Accept shorthand suffixes so users can pass '1h' naturally.
    """
    if isinstance(value, int):
        if value < 0:
            raise ValueError("duration must be non-negative")
        return value

    s = str(value).strip().lower()
    if not s:
        raise ValueError("duration must be non-empty")

    m = re.fullmatch(r"(\d+)\s*([smhd]?)", s)
    if not m:
        raise ValueError(
            f"invalid duration {value!r}: expected integer seconds or suffix "
            "s/m/h/d (e.g. '1h', '30m', '3600')"
        )
    n = int(m.group(1))
    unit = m.group(2) or "s"
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


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

    # Use the analytics collection endpoint with entity_uuid — this is the
    # canonical AVI metrics API and returns consistent `series` output across
    # Controller versions 22.x/30.x. The per-entity path
    # (analytics/metrics/virtualservice/<uuid>) returns empty `series` on
    # several Controller builds when the entity has no in-band traffic.
    metric_ids = ",".join([
        "l4_client.avg_bandwidth",
        "l4_client.avg_complete_conns",
        "l4_client.avg_new_established_conns",
        "l7_client.avg_resp_latency",
        "l7_client.pct_response_errors",
        "l7_client.sum_total_responses",
    ])
    # AVI 22.x requires POST for /analytics/metrics/collection; GET responds
    # with HTTP 404 "Pl. use Post request". This is the *collections* API,
    # so the body must wrap each query in a metric_requests[] entry —
    # flattening the params at the top level yields HTTP 404
    # {"error": "Empty Request"}.
    resp = session.post("analytics/metrics/collection", data={
        "metric_requests": [{
            "metric_id": metric_ids,
            "entity_uuid": uuid,
            "step": 300,
            "limit": 12,
        }],
    })
    payload = resp.json() if hasattr(resp, "json") else resp

    # Response shape: {"series": {uuid: [ {header, data}, ... ]}} for
    # collection endpoint, or {"series": [ ... ]} for per-entity path.
    # Normalise both into a flat list of series.
    raw_series = payload.get("series", [])
    if isinstance(raw_series, dict):
        series_list: list[dict] = []
        for entries in raw_series.values():
            if isinstance(entries, list):
                series_list.extend(entries)
    else:
        series_list = list(raw_series)

    console.print(f"\n[bold]Analytics: {vs_name}[/bold]")
    if not series_list:
        console.print("  [yellow]No metric data returned — the VS may have no traffic "
                      "in the queried window, or analytics collection is disabled.[/yellow]")
        console.print()
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Latest")
    table.add_column("Avg")
    table.add_column("Unit", style="dim")

    for series in series_list:
        header = series.get("header", {}) or {}
        metric = header.get("name") or header.get("metric_id", "unknown")
        unit = header.get("units", "")
        stats = header.get("statistics", {}) or {}
        values = series.get("data", []) or []
        latest = "N/A"
        if values:
            latest_val = values[-1].get("value")
            if latest_val is not None:
                latest = f"{latest_val:.2f}" if isinstance(latest_val, (int, float)) else str(latest_val)
        avg = stats.get("mean")
        avg_str = f"{avg:.2f}" if isinstance(avg, (int, float)) else "N/A"
        table.add_row(metric, latest, avg_str, unit)

    console.print(table)
    console.print()


def show_error_logs(vs_name: str, since: str = "1h") -> None:
    """Show request error logs for a VS.

    ``since`` accepts an integer number of seconds or a suffixed shorthand
    such as ``'1h'``, ``'30m'``, ``'24h'``, ``'7d'``.
    """
    cfg = load_config()
    mgr = AviConnectionManager(cfg)
    session = mgr.connect()

    vs = session.get_object_by_name("virtualservice", vs_name)
    if not vs:
        console.print(f"[red]Virtual Service '{vs_name}' not found.[/red]")
        raise SystemExit(1)

    try:
        duration_seconds = _parse_duration_seconds(since)
    except ValueError as e:
        console.print(f"[red]Invalid duration: {e}[/red]")
        raise SystemExit(1) from None

    uuid = vs["uuid"]
    # AVI 22.x requires the VS UUID as an explicit ``virtualservice`` URL
    # parameter on /analytics/logs; passing it only inside ``filter`` as
    # ``co(vs_uuid,<uuid>)`` yields HTTP 400 "VirtualService ID required".
    resp = session.get("analytics/logs", params={
        "type": "1",
        "virtualservice": uuid,
        "filter": "ne(response_code,200)",
        "page_size": "50",
        "duration": str(duration_seconds),
    })
    logs = (resp.json() if hasattr(resp, "json") else resp).get("results", [])

    console.print(f"\n[bold]Error Logs: {vs_name} (last {since} = {duration_seconds}s)[/bold]")
    for log in logs:
        ts = log.get("report_timestamp", "")
        code = log.get("response_code", "")
        uri = log.get("uri_path", "")[:80]
        client = log.get("client_ip", "")
        console.print(f"  [{ts}] {code} {uri} from {client}")

    if not logs:
        console.print("  [green]No errors found.[/green]")
    console.print()
