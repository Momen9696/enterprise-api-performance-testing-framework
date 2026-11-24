"""Self-contained HTML report. Charts use Plotly.js from a CDN; tables do not."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from perfkit.reports.charts import endpoint_figure, error_figure, histogram_figure, timeseries_figure
from perfkit.reports.export import export_payload


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{html.escape(item)}</th>" for item in headers)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(_fmt(cell))}</td>" for cell in row)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _chart(figure_dict: dict[str, Any], include_js: bool) -> str:
    figure = go.Figure(figure_dict)
    return figure.to_html(full_html=False, include_plotlyjs="cdn" if include_js else False)


def write_html_report(run: dict[str, Any], path: Path, samples: list[dict[str, Any]] | None = None) -> None:
    metrics = run.get("metrics") or {}
    payload = export_payload(run)
    endpoints = run.get("endpoints") or []
    checks = run.get("thresholds") or []
    categories = run.get("error_categories") or []
    endpoint_rows = [
        [
            row["method"],
            row["name"],
            row["total"],
            row["failed"],
            row["rps"],
            row["avg_ms"],
            row["p50_ms"],
            row["p95_ms"],
            row["p99_ms"],
            row["error_pct"],
        ]
        for row in endpoints
    ]
    check_rows = [
        [row["metric"], row["operator"], row["limit_value"], row["actual_value"], "PASS" if row["passed"] else "FAIL"]
        for row in checks
    ]
    category_rows = [[row["category"], row["count"]] for row in categories]
    charts = ""
    if run.get("timeseries"):
        charts += _chart(timeseries_figure(run["timeseries"]), include_js=True)
        charts += _chart(error_figure(run["timeseries"]), include_js=False)
    if endpoints:
        charts += _chart(endpoint_figure(endpoints), include_js=not bool(run.get("timeseries")))
    if samples:
        charts += _chart(histogram_figure(samples), include_js=False)
    kpi = _table(
        ["Total", "Success", "Failed", "RPS", "Avg ms", "Min", "Max", "P50", "P90", "P95", "P99", "Error %"],
        [[
            metrics.get("total"),
            metrics.get("successful"),
            metrics.get("failed"),
            metrics.get("rps"),
            metrics.get("avg_ms"),
            metrics.get("min_ms"),
            metrics.get("max_ms"),
            metrics.get("p50_ms"),
            metrics.get("p90_ms"),
            metrics.get("p95_ms"),
            metrics.get("p99_ms"),
            metrics.get("error_pct"),
        ]],
    )
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>PerfKit report {html.escape(str(run['name']))}</title>
  <style>
    body {{ font-family: "Segoe UI", sans-serif; margin: 2rem; color: #14202b; background: #f6f8f7; }}
    h1 {{ margin-bottom: 0.2rem; }}
    .meta {{ color: #445; }}
    .verdict {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-weight: 700; }}
    .PASS {{ background: #d8f3df; color: #0d5c2e; }}
    .FAIL {{ background: #fde2e1; color: #8a1c13; }}
    .NOT_EVALUATED, .ERROR {{ background: #eee; color: #333; }}
    table {{ border-collapse: collapse; width: 100%; background: white; margin: 1rem 0 2rem; }}
    th, td {{ border: 1px solid #d5ddd8; padding: 0.45rem 0.6rem; text-align: left; font-size: 0.92rem; }}
    th {{ background: #e7f2ec; }}
    .note {{ background: #fff; border-left: 4px solid #1f7a4d; padding: 0.8rem 1rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(str(run['name']))}</h1>
  <p class="meta">
    {html.escape(str(run['test_type']))} · {html.escape(str(run['base_url']))}<br/>
    {html.escape(str(run.get('started_at') or ''))} → {html.escape(str(run.get('finished_at') or ''))}
    · measured duration {_fmt(run.get('duration_seconds'))}s
    · <span class="verdict {html.escape(str(run.get('verdict') or ''))}">{html.escape(str(run.get('verdict') or ''))}</span>
  </p>
  <div class="note">
    <strong>Measured values.</strong>
    Response times and throughput come from this Locust execution (run {html.escape(str(run['id']))}).
    The local demo API does not add artificial latency unless a request sets <code>X-Demo-Latency-Ms</code>.
    Bundled profiles do not set that header. Thresholds below are the ones stored on this profile, not a universal SLO.
  </div>
  <h2>Run metrics</h2>
  {kpi}
  <h2>Threshold assessment</h2>
  {_table(["Metric", "Operator", "Limit", "Actual", "Result"], check_rows) if check_rows else "<p>No thresholds were configured for this profile.</p>"}
  <h2>Endpoints</h2>
  {_table(["Method", "Name", "Total", "Failed", "RPS", "Avg", "P50", "P95", "P99", "Error %"], endpoint_rows)}
  <h2>Error categories</h2>
  {_table(["Category", "Count"], category_rows) if category_rows else "<p>No failed requests.</p>"}
  <h2>Charts</h2>
  {charts}
  <h2>Machine-readable summary</h2>
  <pre>{html.escape(json_dumps(payload))}</pre>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, default=str)
