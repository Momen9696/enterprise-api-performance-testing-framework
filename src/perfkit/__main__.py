"""Command line for the demo API, the control plane, and one-shot runs."""

from __future__ import annotations

import argparse
import os
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

import httpx

from perfkit.config.loader import load_profile_file, resolve_profile_name
from perfkit.engine.service import ExecutionService
from perfkit.scan import scan_repository
from perfkit.settings import load_settings, project_root
from perfkit.storage.db import Database


def _healthy(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    try:
        response = httpx.get(url, timeout=1.0)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _wait_healthy(url: str, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _healthy(url):
            return
        time.sleep(0.2)
    raise SystemExit(f"timed out waiting for {url}")


def _start_demo(port: int) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root() / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("DEMO_API_USERNAME", "demo")
    env.setdefault("DEMO_API_PASSWORD", "demo-local-only")
    return subprocess.Popen(  # nosec B603
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
    )


def _cmd_run(args: argparse.Namespace) -> int:
    os.environ.setdefault("DEMO_API_USERNAME", "demo")
    os.environ.setdefault("DEMO_API_PASSWORD", "demo-local-only")
    settings = load_settings()
    path = Path(args.profile)
    if not path.is_file():
        path = resolve_profile_name(args.profile, settings)
    profile = load_profile_file(path, settings)
    demo: subprocess.Popen[bytes] | None = None
    if args.start_demo:
        health = profile.base_url.rstrip("/") + "/health"
        if not _healthy(health):
            port = int(profile.base_url.rsplit(":", 1)[-1])
            demo = _start_demo(port)
            _wait_healthy(health, 20)
    try:
        service = ExecutionService(settings, Database(settings))
        run_id = service.run_blocking(profile)
        snapshot = service.database.get_run(run_id)
        if snapshot is None:
            print("run disappeared")
            return 1
        metrics = snapshot.get("metrics") or {}
        print(
            f"run {run_id} status={snapshot['status']} verdict={snapshot['verdict']} "
            f"total={metrics.get('total')} rps={metrics.get('rps')} "
            f"p95_ms={metrics.get('p95_ms')} error_pct={metrics.get('error_pct')}"
        )
        if snapshot.get("error_message"):
            print(snapshot["error_message"])
        report = settings.reports_dir / run_id / "report.html"
        if report.exists():
            print(f"report {report}")
        return 0 if snapshot["status"] == "completed" else 1
    finally:
        if demo is not None:
            demo.terminate()
            try:
                demo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                demo.kill()


def _cmd_serve(args: argparse.Namespace) -> int:
    _validate_bind(args.host, args.port)
    os.execvp(  # nosec B606
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "perfkit.api.app:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
    )
    return 0


def _validate_bind(host: str, port: int) -> None:
    if host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        raise SystemExit("host must be 127.0.0.1, localhost, or 0.0.0.0")
    if port < 1 or port > 65535:
        raise SystemExit("port is out of range")


def _cmd_demo(args: argparse.Namespace) -> int:
    _validate_bind(args.host, args.port)
    os.environ.setdefault("DEMO_API_USERNAME", "demo")
    os.environ.setdefault("DEMO_API_PASSWORD", "demo-local-only")
    os.execvp(  # nosec B606
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "perfkit.demo.app:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
    )
    return 0


def _cmd_scan(_: argparse.Namespace) -> int:
    findings = scan_repository(project_root())
    if not findings:
        print("secret scan: no findings")
        return 0
    for finding in findings:
        print(f"{finding.path}:{finding.line} {finding.rule}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="perfkit", description="API performance testing framework")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="execute one profile")
    run_parser.add_argument("--profile", required=True)
    run_parser.add_argument("--start-demo", action="store_true")
    run_parser.set_defaults(func=_cmd_run)
    serve_parser = sub.add_parser("serve", help="start the control plane and dashboard")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)
    serve_parser.set_defaults(func=_cmd_serve)
    demo_parser = sub.add_parser("demo", help="start the local demo API")
    demo_parser.add_argument("--host", default="127.0.0.1")
    demo_parser.add_argument("--port", type=int, default=8090)
    demo_parser.set_defaults(func=_cmd_demo)
    scan_parser = sub.add_parser("scan", help="scan the repository for secret material")
    scan_parser.set_defaults(func=_cmd_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
