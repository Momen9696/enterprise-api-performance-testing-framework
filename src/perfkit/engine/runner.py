"""Spawn Locust with a fixed argument vector. No shell, no user-controlled flags."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
import uuid
from pathlib import Path
from typing import Any

from perfkit.config.models import TestProfile
from perfkit.engine.plan import resolve_stages, stage_peak, stage_total_seconds
from perfkit.security import redact, scrub_text
from perfkit.settings import Settings

LOCUSTFILE = Path(__file__).with_name("locustfile.py")


class RunCancelled(RuntimeError):
    """The operator cancelled the run before Locust finished."""


def build_command(peak_users: int, spawn_rate: float, safety_seconds: int, base_url: str) -> list[str]:
    """Argument vector for a headless Locust run. Every value is already validated."""
    if peak_users < 1 or spawn_rate <= 0 or safety_seconds < 1:
        raise ValueError("invalid locust command parameters")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must be http(s)")
    return [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(LOCUSTFILE),
        "--headless",
        "--only-summary",
        "--users",
        str(int(peak_users)),
        "--spawn-rate",
        str(float(spawn_rate)),
        "--run-time",
        f"{int(safety_seconds)}s",
        "--stop-timeout",
        "5",
        "--host",
        base_url,
    ]


def _resolve_secret(direct: str | None, env_name: str | None) -> str:
    if env_name:
        value = os.environ.get(env_name, "")
        if value:
            return value
    return direct or ""


def prepare_workspace(profile: TestProfile, settings: Settings, run_id: str) -> dict[str, Any]:
    stages = resolve_stages(profile)
    work = settings.reports_dir / run_id
    work.mkdir(parents=True, exist_ok=True)
    stored = redact(profile.model_dump(mode="json"))
    assert isinstance(stored, dict)
    stored["resolved_stages"] = [stage.model_dump(mode="json") for stage in stages]
    stored["base_url"] = profile.base_url
    profile_path = work / "profile.json"
    # The child locustfile needs resolved stages and endpoint definitions, not secrets.
    profile_path.write_text(json.dumps(stored), encoding="utf-8")
    password = None
    api_key = None
    if profile.auth.mode == "bearer":
        password = _resolve_secret(profile.auth.password, profile.auth.password_env)
        if not password:
            raise ValueError(
                f"bearer password was empty (env {profile.auth.password_env or 'inline'} is unset)"
            )
    if profile.auth.mode == "api_key":
        api_key = _resolve_secret(profile.auth.api_key, profile.auth.api_key_env)
        if not api_key:
            raise ValueError("api key was empty")
    env = os.environ.copy()
    env["PERF_PROFILE_JSON"] = str(profile_path)
    env["PERF_RESULTS_JSONL"] = str(work / "samples.jsonl")
    env["PERF_META_JSON"] = str(work / "meta.json")
    env["PERF_AUTH_MODE"] = profile.auth.mode
    env["PERF_AUTH_USERNAME"] = profile.auth.username or ""
    env["PERF_AUTH_PASSWORD"] = password or ""
    env["PERF_AUTH_LOGIN_PATH"] = profile.auth.login_path
    env["PERF_AUTH_HEADER"] = profile.auth.api_key_header
    env["PERF_AUTH_API_KEY"] = api_key or ""
    env["PYTHONPATH"] = str(settings.root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    peak = stage_peak(stages)
    safety = stage_total_seconds(stages) + settings.locust_grace_seconds
    command = build_command(peak, max(stage.spawn_rate for stage in stages), safety, profile.base_url)
    return {
        "run_id": run_id,
        "work": work,
        "stages": stages,
        "command": command,
        "env": env,
        "secrets": [value for value in (password, api_key) if value],
        "stored_profile": stored,
    }


def execute_locust(
    prepared: dict[str, Any],
    cancel_event: Any | None = None,
) -> dict[str, Any]:
    """Run Locust to completion. ``cancel_event`` is a threading.Event when called from the API."""
    if cancel_event is not None and cancel_event.is_set():
        raise RunCancelled("cancelled before start")
    command = prepared["command"]
    process = subprocess.Popen(  # nosec B603
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=prepared["env"],
        cwd=str(prepared["work"]),
        text=True,
    )
    prepared["process"] = process
    safety = _safety_seconds(command)
    try:
        stdout, stderr = process.communicate(timeout=safety + 30)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout_b, stderr_b = process.communicate()
        stdout = (exc.stdout or "") + (stdout_b or "")
        stderr = (exc.stderr or "") + (stderr_b or "")
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        _write_logs(prepared["work"], stdout, stderr, prepared["secrets"])
        raise TimeoutError("Locust exceeded the safety timeout and was killed") from exc
    finally:
        prepared.pop("process", None)
    _write_logs(prepared["work"], stdout, stderr, prepared["secrets"])
    if cancel_event is not None and cancel_event.is_set():
        raise RunCancelled("cancelled")
    return {
        "returncode": process.returncode,
        "stdout": scrub_text(stdout or "", prepared["secrets"]),
        "stderr": scrub_text(stderr or "", prepared["secrets"]),
    }


def terminate_process(prepared: dict[str, Any]) -> None:
    process = prepared.get("process")
    if process is None or process.poll() is not None:
        return
    process.terminate()


def _safety_seconds(command: list[str]) -> int:
    token = command[command.index("--run-time") + 1]
    return int(token.rstrip("s"))


def _write_logs(work: Path, stdout: str, stderr: str, secrets: list[str]) -> None:
    (work / "stdout.log").write_text(scrub_text(stdout or "", secrets), encoding="utf-8")
    (work / "stderr.log").write_text(scrub_text(stderr or "", secrets), encoding="utf-8")


def new_run_id() -> str:
    return uuid.uuid4().hex
