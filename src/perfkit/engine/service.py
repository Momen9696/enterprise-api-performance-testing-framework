"""Orchestrate one run: validate, execute Locust, ingest, assess, persist, report."""

from __future__ import annotations

import threading
from typing import Any

from perfkit.config.loader import enforce_caps
from perfkit.config.models import TestProfile
from perfkit.engine.ingest import ingest_files
from perfkit.engine.runner import (
    RunCancelled,
    execute_locust,
    new_run_id,
    prepare_workspace,
    terminate_process,
)
from perfkit.metrics.thresholds import evaluate_thresholds
from perfkit.reports.html_report import write_html_report
from perfkit.security import redact
from perfkit.settings import Settings
from perfkit.storage.db import Database, utc_now


class ExecutionBusy(RuntimeError):
    """Only one Locust run is allowed at a time."""


class ExecutionService:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._active_id: str | None = None
        self._prepared: dict[str, Any] | None = None
        self._cancel = threading.Event()

    @property
    def active_id(self) -> str | None:
        return self._active_id

    def start(self, profile: TestProfile) -> str:
        profile = enforce_caps(profile, self.settings)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ExecutionBusy("a performance run is already active")
            run_id = new_run_id()
            stored = redact(profile.model_dump(mode="json"))
            assert isinstance(stored, dict)
            self.database.create_run(run_id, profile.name, profile.test_type, profile.base_url, stored)
            self._cancel = threading.Event()
            self._active_id = run_id
            thread = threading.Thread(
                target=self._execute,
                args=(run_id, profile),
                name=f"perfkit-{run_id[:8]}",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return run_id

    def run_blocking(self, profile: TestProfile) -> str:
        """Used by the CLI and tests. Still rejects overlapping runs."""
        run_id = self.start(profile)
        assert self._thread is not None
        self._thread.join()
        return run_id

    def cancel(self, run_id: str) -> None:
        with self._lock:
            if self._active_id != run_id:
                raise KeyError(run_id)
            self._cancel.set()
            if self._prepared is not None:
                terminate_process(self._prepared)

    def _execute(self, run_id: str, profile: TestProfile) -> None:
        try:
            self.database.update_run(run_id, status="running", started_at=utc_now())
            prepared = prepare_workspace(profile, self.settings, run_id)
            with self._lock:
                self._prepared = prepared
            outcome = execute_locust(prepared, self._cancel)
            self.database.update_run(run_id, status="ingesting")
            ingested = ingest_files(
                prepared["work"] / "samples.jsonl",
                prepared["work"] / "meta.json",
            )
            if ingested["summary"]["total"] == 0:
                message = outcome["stderr"] or outcome["stdout"] or "Locust produced no samples"
                if outcome["returncode"] not in (0, None):
                    message = f"locust exit {outcome['returncode']}: {message}"
                self.database.update_run(
                    run_id,
                    status="failed",
                    finished_at=utc_now(),
                    verdict="ERROR",
                    error_message=message[:1500],
                )
                return
            assessment = evaluate_thresholds(
                ingested["summary"],
                profile.thresholds.model_dump(),
            )
            self.database.store_results(
                run_id,
                ingested["summary"],
                ingested["endpoints"],
                ingested["timeseries"],
                assessment["checks"],
                ingested["samples"],
                ingested["locust_rps"],
            )
            self.database.update_run(
                run_id,
                status="completed",
                finished_at=utc_now(),
                duration_seconds=ingested["duration_seconds"],
                verdict=assessment["verdict"],
                error_message=None,
            )
            snapshot = self.database.get_run(run_id)
            if snapshot is not None:
                write_html_report(
                    snapshot,
                    prepared["work"] / "report.html",
                    samples=ingested["samples"],
                )
        except RunCancelled:
            self.database.update_run(
                run_id,
                status="cancelled",
                finished_at=utc_now(),
                verdict="NOT_EVALUATED",
                error_message="cancelled by operator",
            )
        except Exception as exc:
            self.database.update_run(
                run_id,
                status="failed",
                finished_at=utc_now(),
                verdict="ERROR",
                error_message=str(exc)[:1500],
            )
        finally:
            with self._lock:
                self._prepared = None
                self._active_id = None
