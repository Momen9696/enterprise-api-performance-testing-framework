"""Execution lifecycle. The live test is the only one that starts Locust."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from perfkit.config.loader import load_profile_file
from perfkit.config.models import TestProfile
from perfkit.engine.runner import execute_locust, prepare_workspace
from perfkit.engine.service import ExecutionBusy, ExecutionService
from perfkit.settings import Settings, project_root
from perfkit.storage.db import Database

ROOT = project_root()


def _smoke(settings: Settings) -> TestProfile:
    return load_profile_file(ROOT / "profiles" / "ci-smoke.yaml", settings)


def test_runner_does_not_use_a_shell(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    captured: dict = {}

    class _Process:
        returncode = 0

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "summary", ""

        def poll(self) -> int:
            return 0

    def _popen(command: list[str], **kwargs: object) -> _Process:
        captured["command"] = command
        captured["shell"] = kwargs.get("shell", False)
        return _Process()

    monkeypatch.setattr("perfkit.engine.runner.subprocess.Popen", _popen)
    prepared = prepare_workspace(_smoke(settings), settings, "runshell")
    execute_locust(prepared)
    assert captured["shell"] is False
    assert captured["command"][1:3] == ["-m", "locust"]
    stored = json.loads((prepared["work"] / "profile.json").read_text(encoding="utf-8"))
    assert stored["auth"]["password"] in (None, "***")
    assert "demo-local-only" not in json.dumps(stored)


def test_second_run_is_rejected_while_one_is_active(settings: Settings) -> None:
    service = ExecutionService(settings, Database(settings))
    worker = threading.Thread(target=time.sleep, args=(1,))
    worker.start()
    service._thread = worker
    with pytest.raises(ExecutionBusy):
        service.start(_smoke(settings))
    worker.join()


def test_failed_locust_is_recorded(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    def _prepare(profile: TestProfile, current: Settings, run_id: str) -> dict:
        work = current.reports_dir / run_id
        work.mkdir(parents=True, exist_ok=True)
        return {"work": work, "secrets": []}

    def _execute(prepared: dict, cancel_event: object = None) -> dict:
        return {"returncode": 2, "stdout": "", "stderr": "locust failed to start"}

    monkeypatch.setattr("perfkit.engine.service.prepare_workspace", _prepare)
    monkeypatch.setattr("perfkit.engine.service.execute_locust", _execute)
    service = ExecutionService(settings, Database(settings))
    run_id = service.run_blocking(_smoke(settings))
    snapshot = service.database.get_run(run_id)
    assert snapshot is not None
    assert snapshot["status"] == "failed"
    assert snapshot["verdict"] == "ERROR"
    assert "locust failed" in snapshot["error_message"]


def test_ingestion_lifecycle_without_locust(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    def _prepare(profile: TestProfile, current: Settings, run_id: str) -> dict:
        work = current.reports_dir / run_id
        work.mkdir(parents=True, exist_ok=True)
        return {"work": work, "secrets": []}

    def _execute(prepared: dict, cancel_event: object = None) -> dict:
        samples = [
            {
                "ts": 10,
                "name": "list_users",
                "method": "GET",
                "response_time_ms": 12,
                "status_code": 200,
                "success": True,
                "error_category": "none",
                "response_length": 10,
            },
            {
                "ts": 11,
                "name": "list_users",
                "method": "GET",
                "response_time_ms": 18,
                "status_code": 200,
                "success": True,
                "error_category": "none",
                "response_length": 10,
            },
        ]
        (prepared["work"] / "samples.jsonl").write_text(
            "\n".join(json.dumps(sample) for sample in samples),
            encoding="utf-8",
        )
        (prepared["work"] / "meta.json").write_text(
            json.dumps({"start": 10, "end": 12, "locust_total_rps": 1}),
            encoding="utf-8",
        )
        return {"returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr("perfkit.engine.service.prepare_workspace", _prepare)
    monkeypatch.setattr("perfkit.engine.service.execute_locust", _execute)
    service = ExecutionService(settings, Database(settings))
    run_id = service.run_blocking(_smoke(settings))
    snapshot = service.database.get_run(run_id)
    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert snapshot["verdict"] == "PASS"
    assert snapshot["metrics"]["total"] == 2
    report = (settings.reports_dir / run_id / "report.html").read_text(encoding="utf-8")
    assert "Measured values" in report
    assert "demo-local-only" not in report


def test_locustfile_registers_weighted_tasks(tmp_path: Path) -> None:
    profile = {
        "wait": {"min_seconds": 0.1, "max_seconds": 0.2},
        "request_timeout_seconds": 5,
        "resolved_stages": [{"duration_seconds": 5, "users": 1, "spawn_rate": 1}],
        "pacing": {},
        "endpoints": [
            {"name": "list_users", "method": "GET", "path": "/users", "weight": 2, "expected_status": [200]},
            {"name": "search", "method": "GET", "path": "/search", "weight": 1, "expected_status": [200]},
        ],
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    env = os.environ.copy()
    env["PERF_PROFILE_JSON"] = str(path)
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from perfkit.engine.locustfile import ConfiguredApiUser; print(len(ConfiguredApiUser.tasks))",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.stdout.strip() == "3"


@pytest.mark.live
def test_live_smoke_against_demo_api(settings: Settings) -> None:
    port = 8765
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_API_USERNAME"] = "demo"
    env["DEMO_API_PASSWORD"] = "demo-local-only"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "perfkit.demo.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
            raise AssertionError(f"demo API did not start\n{stderr}")
        os.environ["DEMO_API_PASSWORD"] = "demo-local-only"
        os.environ["DEMO_API_USERNAME"] = "demo"
        profile = _smoke(settings).model_copy(update={"base_url": f"http://127.0.0.1:{port}"})
        service = ExecutionService(settings, Database(settings))
        run_id = service.run_blocking(profile)
        snapshot = service.database.get_run(run_id)
        assert snapshot is not None
        assert snapshot["status"] == "completed", snapshot.get("error_message")
        assert snapshot["verdict"] == "PASS", snapshot
        metrics = snapshot["metrics"]
        assert metrics["total"] > 5
        assert metrics["error_pct"] <= 2
        assert metrics["p50_ms"] <= metrics["p90_ms"] <= metrics["p95_ms"] <= metrics["p99_ms"]
        assert any(row["name"] == "list_transactions" for row in snapshot["endpoints"])
        report = (settings.reports_dir / run_id / "report.html").read_text(encoding="utf-8")
        assert "Measured values" in report
        assert "demo-local-only" not in report
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
