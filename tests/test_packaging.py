"""Packaging, secret scan, and Docker configuration checks."""

from __future__ import annotations

import yaml

from perfkit.scan import scan_repository
from perfkit.settings import project_root

ROOT = project_root()


def test_secret_scan_is_clean() -> None:
    assert scan_repository(ROOT) == []


def test_compose_and_dockerfiles_are_constrained() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "demo-api" in compose["services"]
    assert "engine" in compose["services"]
    assert compose["services"]["demo-api"]["healthcheck"]
    assert compose["services"]["engine"]["healthcheck"]
    assert "perfkit-data" in compose["volumes"]
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "privileged" not in text
    for name in ("Dockerfile.demo", "Dockerfile.engine", "Dockerfile.dashboard"):
        docker = (ROOT / "docker" / name).read_text(encoding="utf-8")
        assert "HEALTHCHECK" in docker
        assert "python:3.12-slim" in docker
        assert "USER perfkit" in docker
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest" in workflow
    assert "ci-smoke.yaml" in workflow
    assert "pip-audit" in workflow


def test_env_example_has_no_live_secret() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "demo-local-only" in example
    assert "ghp_" not in example
    assert "BEGIN PRIVATE KEY" not in example
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert ".venv/" in gitignore
    assert "data/" in gitignore
