"""CSV and JSON exports of measured results. Secrets are already absent from the snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def export_payload(run: dict[str, Any]) -> dict[str, Any]:
    metrics = run.get("metrics") or {}
    return {
        "id": run["id"],
        "name": run["name"],
        "test_type": run["test_type"],
        "status": run["status"],
        "verdict": run["verdict"],
        "base_url": run["base_url"],
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "duration_seconds": run.get("duration_seconds"),
        "metrics": {key: metrics.get(key) for key in metrics if key != "run_id"},
        "endpoints": run.get("endpoints") or [],
        "timeseries": run.get("timeseries") or [],
        "error_categories": run.get("error_categories") or [],
        "thresholds": run.get("thresholds") or [],
        "notes": [
            "Response times are measured by Locust around each HTTP call.",
            "The demo API injects latency only when a request asks for it. Bundled profiles do not.",
            "Thresholds were taken from this run's profile and are not global targets.",
        ],
    }


def write_json(run: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(export_payload(run), indent=2, default=str), encoding="utf-8")


def write_csv(run: dict[str, Any], path: Path, view: str = "endpoints") -> None:
    if view == "timeseries":
        frame = pd.DataFrame(run.get("timeseries") or [])
    elif view == "thresholds":
        frame = pd.DataFrame(run.get("thresholds") or [])
    else:
        frame = pd.DataFrame(run.get("endpoints") or [])
    if frame.empty:
        path.write_text("", encoding="utf-8")
        return
    drop = [column for column in ("id", "run_id") if column in frame.columns]
    frame.drop(columns=drop).to_csv(path, index=False)
