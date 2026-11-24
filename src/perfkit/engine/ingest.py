"""Read the JSONL written by the Locust process and compute metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perfkit.metrics.core import build_timeseries, measured_duration, summarize, summarize_endpoints


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    samples: list[dict[str, Any]] = []
    skipped = 0
    if not path.exists():
        return samples, skipped
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if "response_time_ms" not in payload or "success" not in payload:
            skipped += 1
            continue
        samples.append(payload)
    return samples, skipped


def load_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def ingest_files(jsonl_path: Path, meta_path: Path) -> dict[str, Any]:
    samples, skipped = load_jsonl(jsonl_path)
    meta = load_meta(meta_path)
    duration = measured_duration(samples, meta)
    summary = summarize(samples, duration)
    return {
        "samples": samples,
        "skipped_lines": skipped,
        "meta": meta,
        "duration_seconds": duration,
        "summary": summary,
        "endpoints": summarize_endpoints(samples, duration),
        "timeseries": build_timeseries(samples, 1.0),
        "locust_rps": meta.get("locust_total_rps"),
    }
