"""Result ingestion and exports."""

from __future__ import annotations

import json
from pathlib import Path

from perfkit.engine.ingest import ingest_files
from perfkit.reports.export import export_payload, write_csv, write_json
from perfkit.storage.db import Database


def test_ingest_skips_bad_lines_and_computes_metrics(tmp_path: Path) -> None:
    jsonl = tmp_path / "samples.jsonl"
    rows = [
        {"ts": 1, "name": "list", "method": "GET", "response_time_ms": 10, "status_code": 200, "success": True, "error_category": "none", "response_length": 4},
        {"ts": 2, "name": "list", "method": "GET", "response_time_ms": 30, "status_code": 500, "success": False, "error_category": "http_5xx", "response_length": 2},
        "not-json",
    ]
    jsonl.write_text("\n".join(json.dumps(row) if not isinstance(row, str) else row for row in rows), encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"start": 0, "end": 2, "locust_total_rps": 1.0}), encoding="utf-8")
    ingested = ingest_files(jsonl, meta)
    assert ingested["skipped_lines"] == 1
    assert ingested["summary"]["total"] == 2
    assert ingested["summary"]["failed"] == 1
    assert ingested["duration_seconds"] == 2
    assert ingested["endpoints"][0]["name"] == "list"
    assert len(ingested["timeseries"]) == 2


def test_exports_and_history(settings, tmp_path: Path) -> None:
    database = Database(settings)
    database.create_run("run1", "ci-smoke", "load", "http://127.0.0.1:8090", {"name": "ci-smoke"})
    summary = {
        "total": 4,
        "successful": 4,
        "failed": 0,
        "rps": 2,
        "avg_ms": 12,
        "min_ms": 8,
        "max_ms": 20,
        "p50_ms": 11,
        "p90_ms": 18,
        "p95_ms": 19,
        "p99_ms": 20,
        "error_pct": 0,
        "error_categories": {},
    }
    endpoints = [{**summary, "name": "list_users", "method": "GET"}]
    database.store_results("run1", summary, endpoints, [], [], [], None)
    database.update_run("run1", status="completed", started_at="2026-01-01T00:00:00+00:00", verdict="PASS")
    database.create_run("run2", "ci-smoke", "load", "http://127.0.0.1:8090", {"name": "ci-smoke"})
    worse = {**summary, "p95_ms": 40, "rps": 1, "error_pct": 3}
    database.store_results("run2", worse, [{**worse, "name": "list_users", "method": "GET"}], [], [], [], None)
    database.update_run("run2", status="completed", started_at="2026-01-02T00:00:00+00:00", verdict="FAIL")
    history = database.history_for_name("ci-smoke")
    assert [row["p95_ms"] for row in history] == [19, 40]
    snapshot = database.get_run("run2")
    assert snapshot is not None
    payload = export_payload(snapshot)
    assert "password" not in json.dumps(payload).lower()
    json_path = tmp_path / "out.json"
    csv_path = tmp_path / "out.csv"
    write_json(snapshot, json_path)
    write_csv(snapshot, csv_path, view="endpoints")
    assert json.loads(json_path.read_text())["verdict"] == "FAIL"
    assert "list_users" in csv_path.read_text()
