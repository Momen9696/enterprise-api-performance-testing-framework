"""Register profile endpoints as Locust tasks after the class is created.

Locust collects ``tasks`` when the class body executes. Endpoints are known only
from the profile, so the runner assigns ``tasks`` explicitly.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import threading
import time
from pathlib import Path

from locust import HttpUser, LoadTestShape, between, events, task

from perfkit.datafactory import render_endpoint_payload
from perfkit.engine.plan import weighted_names
from perfkit.metrics.core import categorize_error

_PROFILE_PATH = os.environ.get("PERF_PROFILE_JSON", "")
_RESULTS_PATH = os.environ.get("PERF_RESULTS_JSONL", "")
_META_PATH = os.environ.get("PERF_META_JSON", "")
_LOCK = threading.Lock()
_STATE: dict[str, float | None] = {"start": None}


def _load_profile() -> dict | None:
    if not _PROFILE_PATH:
        return None
    payload = json.loads(Path(_PROFILE_PATH).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("profile JSON must be an object")
    return payload


PROFILE = _load_profile()


def _append(record: dict) -> None:
    if not _RESULTS_PATH:
        return
    line = json.dumps(record, separators=(",", ":"))
    with _LOCK:
        with open(_RESULTS_PATH, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


@events.request.add_listener
def _on_request(
    request_type,
    name,
    response_time,
    response_length,
    response,
    exception,
    start_time=None,
    **kwargs,
):
    status = getattr(response, "status_code", None) if response is not None else None
    success = exception is None
    exc_name = type(exception).__name__ if exception is not None else None
    message = str(exception) if exception is not None else ""
    _append(
        {
            "ts": time.time() if start_time is None else float(start_time),
            "name": name,
            "method": request_type,
            "response_time_ms": float(response_time),
            "status_code": status,
            "success": success,
            "error_category": categorize_error(exc_name, message, status, success),
            "response_length": int(response_length or 0),
        }
    )


@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    _STATE["start"] = time.time()


@events.test_stop.add_listener
def _on_test_stop(environment, **kwargs):
    if not _META_PATH:
        return
    total = environment.stats.total
    meta = {
        "start": _STATE["start"],
        "end": time.time(),
        "locust_total_rps": float(getattr(total, "total_rps", 0) or 0),
        "locust_requests": int(getattr(total, "num_requests", 0) or 0),
        "locust_failures": int(getattr(total, "num_failures", 0) or 0),
    }
    Path(_META_PATH).write_text(json.dumps(meta), encoding="utf-8")


def _call(user: HttpUser, endpoint: dict) -> None:
    assert PROFILE is not None
    query, body, headers = render_endpoint_payload(
        endpoint.get("query") or {},
        endpoint.get("json_body"),
        endpoint.get("headers") or {},
        user._rng,  # noqa: SLF001
        user._seq,  # noqa: SLF001
    )
    started = time.perf_counter()
    with user.client.request(
        endpoint["method"],
        endpoint["path"],
        params=query or None,
        json=body,
        headers=headers or None,
        name=endpoint["name"],
        catch_response=True,
        allow_redirects=False,
        timeout=float(PROFILE.get("request_timeout_seconds", 10)),
    ) as response:
        expected = endpoint.get("expected_status") or [200]
        if response.status_code not in expected:
            response.failure(f"unexpected status {response.status_code}")
        else:
            response.success()
    minimum = (PROFILE.get("pacing") or {}).get("min_iteration_seconds")
    if minimum:
        remaining = float(minimum) - (time.perf_counter() - started)
        if remaining > 0:
            time.sleep(remaining)


def build_tasks(endpoints: list[dict]) -> list:
    """Return a Locust task list. Weight is repetition, which Locust samples uniformly."""
    by_name = {endpoint["name"]: endpoint for endpoint in endpoints}

    def _make(spec: dict):
        def _task(self: HttpUser) -> None:
            _call(self, spec)

        _task.__name__ = f"task_{spec['name']}"
        return task(1)(_task)

    return [_make(by_name[name]) for name in weighted_names(endpoints)]


class ConfiguredApiUser(HttpUser):
    """Virtual user whose tasks and wait time come from the active profile."""

    wait_time = between(
        float(PROFILE["wait"]["min_seconds"]) if PROFILE else 0.1,
        float(PROFILE["wait"]["max_seconds"]) if PROFILE else 0.2,
    )
    tasks = build_tasks(PROFILE["endpoints"]) if PROFILE else []

    def on_start(self) -> None:
        self._rng = random.Random()  # nosec B311
        self._seq = itertools.count(1)
        if not PROFILE:
            raise RuntimeError("PERF_PROFILE_JSON is not set")
        mode = os.environ.get("PERF_AUTH_MODE", "none")
        timeout = float(PROFILE.get("request_timeout_seconds", 10))
        if mode == "bearer":
            with self.client.post(
                os.environ.get("PERF_AUTH_LOGIN_PATH", "/auth/token"),
                json={
                    "username": os.environ.get("PERF_AUTH_USERNAME", ""),
                    "password": os.environ.get("PERF_AUTH_PASSWORD", ""),
                },
                name="auth_token",
                catch_response=True,
                allow_redirects=False,
                timeout=timeout,
            ) as response:
                if response.status_code != 200:
                    response.failure(f"unexpected status {response.status_code}")
                    return
                response.success()
                token = response.json().get("access_token", "")
                if token:
                    self.client.headers["Authorization"] = f"Bearer {token}"
        elif mode == "api_key":
            header = os.environ.get("PERF_AUTH_HEADER", "X-Api-Key")
            value = os.environ.get("PERF_AUTH_API_KEY", "")
            if header and value:
                self.client.headers[header] = value


class ProfileLoadShape(LoadTestShape):
    """Follow ``resolved_stages`` and stop by returning None when they are exhausted."""

    def tick(self):
        if not PROFILE:
            return None
        stages = PROFILE.get("resolved_stages") or []
        elapsed_limit = 0
        run_time = self.get_run_time()
        if run_time is None:
            return None
        for stage in stages:
            elapsed_limit += int(stage["duration_seconds"])
            if run_time < elapsed_limit:
                return int(stage["users"]), float(stage["spawn_rate"])
        return None
