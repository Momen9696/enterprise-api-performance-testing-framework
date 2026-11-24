"""Source-of-truth performance math.

Percentiles use linear interpolation between adjacent ranks (Hyndman–Fan type 7,
the same method as ``numpy.percentile`` / ``pandas.Series.quantile`` defaults):

    rank = (p / 100) * (n - 1)

Response-time percentiles include every sample that recorded a time, including
HTTP errors. Throughput is ``total_requests / measured_duration_seconds``.
Endpoint throughput uses the full test duration so endpoints are comparable.
"""

from __future__ import annotations

import math
from typing import Any


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(float(item) for item in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (percent / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def categorize_error(exception_name: str | None, message: str | None, status_code: int | None, success: bool) -> str:
    if success:
        return "none"
    text = f"{exception_name or ''} {message or ''}".lower()
    if "timeout" in text:
        return "timeout"
    if "connection" in text or "refused" in text or "name or service not known" in text:
        return "connection"
    if status_code is not None and status_code >= 500:
        return "http_5xx"
    if status_code is not None and status_code >= 400:
        return "http_4xx"
    if "unexpected" in text:
        return "unexpected_status"
    return "other"


def _times(samples: list[dict[str, Any]]) -> list[float]:
    return [
        float(sample["response_time_ms"])
        for sample in samples
        if sample.get("response_time_ms") is not None
    ]


def summarize(samples: list[dict[str, Any]], duration_seconds: float) -> dict[str, Any]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    total = len(samples)
    failed = sum(1 for sample in samples if not sample.get("success"))
    successful = total - failed
    times = _times(samples)
    categories: dict[str, int] = {}
    for sample in samples:
        if sample.get("success"):
            continue
        category = str(sample.get("error_category") or "other")
        categories[category] = categories.get(category, 0) + 1
    average = (sum(times) / len(times)) if times else None
    return {
        "total": total,
        "successful": successful,
        "failed": failed,
        "rps": total / duration_seconds if total else 0.0,
        "avg_ms": average,
        "min_ms": min(times) if times else None,
        "max_ms": max(times) if times else None,
        "p50_ms": percentile(times, 50),
        "p90_ms": percentile(times, 90),
        "p95_ms": percentile(times, 95),
        "p99_ms": percentile(times, 99),
        "error_pct": (failed / total * 100.0) if total else None,
        "error_categories": categories,
    }


def summarize_endpoints(samples: list[dict[str, Any]], duration_seconds: float) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for sample in samples:
        key = (str(sample.get("method") or ""), str(sample.get("name") or "unknown"))
        grouped.setdefault(key, []).append(sample)
    rows: list[dict[str, Any]] = []
    for (method, name), group in sorted(grouped.items(), key=lambda item: item[0][1]):
        summary = summarize(group, duration_seconds)
        summary["method"] = method
        summary["name"] = name
        rows.append(summary)
    return rows


def build_timeseries(samples: list[dict[str, Any]], bucket_seconds: float = 1.0) -> list[dict[str, Any]]:
    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")
    if not samples:
        return []
    origin = min(float(sample["ts"]) for sample in samples)
    buckets: dict[int, list[dict[str, Any]]] = {}
    for sample in samples:
        index = int((float(sample["ts"]) - origin) // bucket_seconds)
        buckets.setdefault(index, []).append(sample)
    rows: list[dict[str, Any]] = []
    for index in sorted(buckets):
        group = buckets[index]
        summary = summarize(group, bucket_seconds)
        rows.append(
            {
                "bucket_start": origin + index * bucket_seconds,
                "offset_seconds": index * bucket_seconds,
                "total": summary["total"],
                "failed": summary["failed"],
                "rps": summary["rps"],
                "avg_ms": summary["avg_ms"],
                "error_pct": summary["error_pct"] if summary["error_pct"] is not None else 0.0,
            }
        )
    return rows


def measured_duration(samples: list[dict[str, Any]], meta: dict[str, Any] | None) -> float:
    """Prefer Locust test_start/test_stop. Fall back to the sample timestamp span."""
    if meta and meta.get("start") is not None and meta.get("end") is not None:
        span = float(meta["end"]) - float(meta["start"])
        if span > 0:
            return span
    if len(samples) >= 2:
        stamps = [float(sample["ts"]) for sample in samples]
        span = max(stamps) - min(stamps)
        if span > 0:
            return span
    return 0.001
