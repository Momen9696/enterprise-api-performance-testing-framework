"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from perfkit.settings import Settings, project_root

ROOT = project_root()


@pytest.fixture(autouse=True)
def demo_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_API_USERNAME", "demo")
    monkeypatch.setenv("DEMO_API_PASSWORD", "demo-local-only")
    monkeypatch.setenv("DEMO_TOKEN_SECRET", "demo-token-secret-local")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        root=ROOT,
        db_path=tmp_path / "perfkit.sqlite",
        reports_dir=tmp_path / "reports",
        profiles_dir=ROOT / "profiles",
        max_users=25,
        max_duration_seconds=180,
        allowed_hosts=frozenset({"localhost", "127.0.0.1", "::1", "demo-api", "host.docker.internal"}),
        locust_grace_seconds=30,
    )
