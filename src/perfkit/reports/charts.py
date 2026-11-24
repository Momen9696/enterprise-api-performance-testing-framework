"""Plotly figures built only from stored measurements."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go


def _base_layout(title: str, x_title: str, y_title: str) -> dict[str, Any]:
    return dict(
        title=title,
        xaxis_title=x_title,
        yaxis_title=y_title,
        template="plotly_white",
        margin=dict(l=48, r=24, t=48, b=48),
        height=360,
    )


def timeseries_figure(series: list[dict[str, Any]]) -> dict[str, Any]:
    offsets = [row["offset_seconds"] for row in series]
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=offsets, y=[row["rps"] for row in series], name="Requests / s", mode="lines+markers"))
    figure.add_trace(
        go.Scatter(
            x=offsets,
            y=[row["avg_ms"] for row in series],
            name="Avg response ms",
            mode="lines+markers",
            yaxis="y2",
        )
    )
    figure.update_layout(
        **_base_layout("Throughput and average response time", "Seconds from first sample", "Requests / s"),
        yaxis2=dict(title="Average ms", overlaying="y", side="right"),
        legend=dict(orientation="h"),
    )
    return figure.to_dict()


def error_figure(series: list[dict[str, Any]]) -> dict[str, Any]:
    figure = go.Figure(
        data=[
            go.Bar(
                x=[row["offset_seconds"] for row in series],
                y=[row["error_pct"] for row in series],
                name="Error %",
            )
        ]
    )
    figure.update_layout(**_base_layout("Error percentage by second", "Seconds from first sample", "Error %"))
    return figure.to_dict()


def endpoint_figure(endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    names = [row["name"] for row in endpoints]
    figure = go.Figure()
    figure.add_trace(go.Bar(x=names, y=[row["p50_ms"] for row in endpoints], name="P50"))
    figure.add_trace(go.Bar(x=names, y=[row["p95_ms"] for row in endpoints], name="P95"))
    figure.add_trace(go.Bar(x=names, y=[row["p99_ms"] for row in endpoints], name="P99"))
    figure.update_layout(
        **_base_layout("Endpoint response-time comparison", "Endpoint", "Milliseconds"),
        barmode="group",
    )
    return figure.to_dict()


def histogram_figure(samples: list[dict[str, Any]]) -> dict[str, Any]:
    times = [row["response_time_ms"] for row in samples if row.get("response_time_ms") is not None]
    figure = go.Figure(data=[go.Histogram(x=times, nbinsx=30, name="Response time")])
    figure.update_layout(**_base_layout("Response-time distribution", "Milliseconds", "Requests"))
    return figure.to_dict()


def trend_figure(series: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [row.get("started_at") or row.get("id", "") for row in series]
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=labels, y=[row["p95_ms"] for row in series], name="P95 ms", mode="lines+markers"))
    figure.add_trace(
        go.Scatter(
            x=labels,
            y=[row["error_pct"] for row in series],
            name="Error %",
            mode="lines+markers",
            yaxis="y2",
        )
    )
    figure.update_layout(
        **_base_layout("Historical P95 and error rate", "Run", "P95 ms"),
        yaxis2=dict(title="Error %", overlaying="y", side="right"),
    )
    return figure.to_dict()


def figures_for_run(run: dict[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "throughput": timeseries_figure(run.get("timeseries") or []),
        "errors": error_figure(run.get("timeseries") or []),
        "endpoints": endpoint_figure(run.get("endpoints") or []),
        "distribution": histogram_figure(samples),
    }
