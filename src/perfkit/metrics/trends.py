"""Trend direction from historical measured runs of the same profile name."""

from __future__ import annotations

from typing import Any


def _slope(values: list[float]) -> float:
    count = len(values)
    if count < 2:
        return 0.0
    xs = list(range(count))
    mean_x = sum(xs) / count
    mean_y = sum(values) / count
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=True))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _direction(first: float, last: float, *, lower_is_better: bool) -> str:
    if first == 0:
        delta_ratio = 0.0 if last == 0 else 1.0
    else:
        delta_ratio = (last - first) / abs(first)
    if abs(last - first) < 1e-9 or abs(delta_ratio) < 0.05:
        return "stable"
    improved = delta_ratio < 0 if lower_is_better else delta_ratio > 0
    return "improving" if improved else "degrading"


def analyze_trend(history: list[dict[str, Any]]) -> dict[str, Any]:
    """``history`` items need p95_ms, rps, and error_pct in chronological order."""
    usable = [
        row
        for row in history
        if row.get("p95_ms") is not None and row.get("rps") is not None and row.get("error_pct") is not None
    ]
    if len(usable) < 2:
        return {
            "status": "insufficient_history",
            "points": len(usable),
            "series": usable,
        }
    p95 = [float(row["p95_ms"]) for row in usable]
    rps = [float(row["rps"]) for row in usable]
    errors = [float(row["error_pct"]) for row in usable]
    return {
        "status": "ok",
        "points": len(usable),
        "p95_ms": {
            "first": p95[0],
            "last": p95[-1],
            "delta": p95[-1] - p95[0],
            "slope_per_run": _slope(p95),
            "direction": _direction(p95[0], p95[-1], lower_is_better=True),
        },
        "rps": {
            "first": rps[0],
            "last": rps[-1],
            "delta": rps[-1] - rps[0],
            "slope_per_run": _slope(rps),
            "direction": _direction(rps[0], rps[-1], lower_is_better=False),
        },
        "error_pct": {
            "first": errors[0],
            "last": errors[-1],
            "delta": errors[-1] - errors[0],
            "slope_per_run": _slope(errors),
            "direction": _direction(errors[0], errors[-1], lower_is_better=True),
        },
        "series": usable,
    }
