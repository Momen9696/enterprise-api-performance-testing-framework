"""SQLite history for runs, samples, and assessments."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from perfkit.settings import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    test_type TEXT NOT NULL,
    status TEXT NOT NULL,
    base_url TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    duration_seconds REAL,
    verdict TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_metrics (
    run_id TEXT PRIMARY KEY,
    total INTEGER,
    successful INTEGER,
    failed INTEGER,
    rps REAL,
    avg_ms REAL,
    min_ms REAL,
    max_ms REAL,
    p50_ms REAL,
    p90_ms REAL,
    p95_ms REAL,
    p99_ms REAL,
    error_pct REAL,
    locust_rps REAL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS endpoint_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    method TEXT NOT NULL,
    total INTEGER,
    successful INTEGER,
    failed INTEGER,
    rps REAL,
    avg_ms REAL,
    min_ms REAL,
    max_ms REAL,
    p50_ms REAL,
    p90_ms REAL,
    p95_ms REAL,
    p99_ms REAL,
    error_pct REAL
);
CREATE TABLE IF NOT EXISTS timeseries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    bucket_start REAL,
    offset_seconds REAL,
    total INTEGER,
    failed INTEGER,
    rps REAL,
    avg_ms REAL,
    error_pct REAL
);
CREATE TABLE IF NOT EXISTS error_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    category TEXT NOT NULL,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS threshold_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    limit_value REAL,
    actual_value REAL,
    passed INTEGER NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts REAL,
    name TEXT,
    method TEXT,
    response_time_ms REAL,
    status_code INTEGER,
    success INTEGER,
    error_category TEXT,
    response_length INTEGER
);
"""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_dirs()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.settings.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def create_run(self, run_id: str, name: str, test_type: str, base_url: str, profile: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, name, test_type, status, base_url, profile_json, created_at, verdict)
                VALUES (?, ?, ?, 'queued', ?, ?, ?, NULL)
                """,
                (run_id, name, test_type, base_url, json.dumps(profile), utc_now()),
            )

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = (
            "status",
            "started_at",
            "finished_at",
            "duration_seconds",
            "verdict",
            "error_message",
        )
        unknown = set(fields) - set(allowed)
        if unknown:
            raise ValueError(f"cannot update {unknown}")
        with self.connect() as conn:
            current = conn.execute(
                """
                SELECT status, started_at, finished_at, duration_seconds, verdict, error_message
                FROM runs WHERE id=?
                """,
                (run_id,),
            ).fetchone()
            if current is None:
                raise KeyError(run_id)
            merged = {key: fields.get(key, current[key]) for key in allowed}
            conn.execute(
                """
                UPDATE runs
                SET status=?, started_at=?, finished_at=?, duration_seconds=?, verdict=?, error_message=?
                WHERE id=?
                """,
                (
                    merged["status"],
                    merged["started_at"],
                    merged["finished_at"],
                    merged["duration_seconds"],
                    merged["verdict"],
                    merged["error_message"],
                    run_id,
                ),
            )

    def store_results(
        self,
        run_id: str,
        summary: dict[str, Any],
        endpoints: list[dict[str, Any]],
        series: list[dict[str, Any]],
        checks: list[dict[str, Any]],
        samples: list[dict[str, Any]],
        locust_rps: float | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM endpoint_metrics WHERE run_id=?", (run_id,))
            conn.execute("DELETE FROM timeseries WHERE run_id=?", (run_id,))
            conn.execute("DELETE FROM error_categories WHERE run_id=?", (run_id,))
            conn.execute("DELETE FROM threshold_results WHERE run_id=?", (run_id,))
            conn.execute("DELETE FROM samples WHERE run_id=?", (run_id,))
            conn.execute("DELETE FROM run_metrics WHERE run_id=?", (run_id,))
            conn.execute(
                """
                INSERT INTO run_metrics (
                    run_id, total, successful, failed, rps, avg_ms, min_ms, max_ms,
                    p50_ms, p90_ms, p95_ms, p99_ms, error_pct, locust_rps
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    summary["total"],
                    summary["successful"],
                    summary["failed"],
                    summary["rps"],
                    summary["avg_ms"],
                    summary["min_ms"],
                    summary["max_ms"],
                    summary["p50_ms"],
                    summary["p90_ms"],
                    summary["p95_ms"],
                    summary["p99_ms"],
                    summary["error_pct"],
                    locust_rps,
                ),
            )
            for row in endpoints:
                conn.execute(
                    """
                    INSERT INTO endpoint_metrics (
                        run_id, name, method, total, successful, failed, rps, avg_ms, min_ms,
                        max_ms, p50_ms, p90_ms, p95_ms, p99_ms, error_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        row["name"],
                        row["method"],
                        row["total"],
                        row["successful"],
                        row["failed"],
                        row["rps"],
                        row["avg_ms"],
                        row["min_ms"],
                        row["max_ms"],
                        row["p50_ms"],
                        row["p90_ms"],
                        row["p95_ms"],
                        row["p99_ms"],
                        row["error_pct"],
                    ),
                )
            for row in series:
                conn.execute(
                    """
                    INSERT INTO timeseries (
                        run_id, bucket_start, offset_seconds, total, failed, rps, avg_ms, error_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        row["bucket_start"],
                        row["offset_seconds"],
                        row["total"],
                        row["failed"],
                        row["rps"],
                        row["avg_ms"],
                        row["error_pct"],
                    ),
                )
            for category, count in sorted((summary.get("error_categories") or {}).items()):
                conn.execute(
                    "INSERT INTO error_categories (run_id, category, count) VALUES (?, ?, ?)",
                    (run_id, category, count),
                )
            for check in checks:
                conn.execute(
                    """
                    INSERT INTO threshold_results (
                        run_id, metric, operator, limit_value, actual_value, passed, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        check["metric"],
                        check["operator"],
                        check["limit"],
                        check["actual"],
                        1 if check["passed"] else 0,
                        check.get("reason") or "",
                    ),
                )
            for sample in samples:
                conn.execute(
                    """
                    INSERT INTO samples (
                        run_id, ts, name, method, response_time_ms, status_code, success,
                        error_category, response_length
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        sample.get("ts"),
                        sample.get("name"),
                        sample.get("method"),
                        sample.get("response_time_ms"),
                        sample.get("status_code"),
                        1 if sample.get("success") else 0,
                        sample.get("error_category"),
                        sample.get("response_length"),
                    ),
                )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None
            return self._hydrate(conn, row)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.*, m.total, m.successful, m.failed, m.rps, m.avg_ms, m.p95_ms, m.error_pct
                FROM runs r
                LEFT JOIN run_metrics m ON m.run_id = r.id
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def history_for_name(self, name: str, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.name, r.started_at, r.verdict, m.p95_ms, m.p99_ms, m.rps, m.error_pct, m.avg_ms
                FROM runs r
                JOIN run_metrics m ON m.run_id = r.id
                WHERE r.name=? AND r.status='completed'
                ORDER BY r.started_at ASC
                LIMIT ?
                """,
                (name, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _hydrate(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["profile"] = json.loads(payload.pop("profile_json"))
        metrics = conn.execute("SELECT * FROM run_metrics WHERE run_id=?", (payload["id"],)).fetchone()
        payload["metrics"] = dict(metrics) if metrics else None
        payload["endpoints"] = [
            dict(item)
            for item in conn.execute(
                "SELECT * FROM endpoint_metrics WHERE run_id=? ORDER BY name",
                (payload["id"],),
            ).fetchall()
        ]
        payload["timeseries"] = [
            dict(item)
            for item in conn.execute(
                "SELECT * FROM timeseries WHERE run_id=? ORDER BY offset_seconds",
                (payload["id"],),
            ).fetchall()
        ]
        payload["error_categories"] = [
            dict(item)
            for item in conn.execute(
                "SELECT category, count FROM error_categories WHERE run_id=? ORDER BY count DESC",
                (payload["id"],),
            ).fetchall()
        ]
        payload["thresholds"] = [
            dict(item)
            for item in conn.execute(
                "SELECT * FROM threshold_results WHERE run_id=? ORDER BY id",
                (payload["id"],),
            ).fetchall()
        ]
        return payload

    def samples_for(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM samples WHERE run_id=? ORDER BY ts",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]
