"""Runtime settings. Caps and allowlists come from the environment, not from profile authors."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root: Path
    db_path: Path
    reports_dir: Path
    profiles_dir: Path
    max_users: int
    max_duration_seconds: int
    allowed_hosts: frozenset[str]
    locust_grace_seconds: int

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)


def _csv_set(value: str) -> frozenset[str]:
    return frozenset(part.strip().lower() for part in value.split(",") if part.strip())


def load_settings() -> Settings:
    root = Path(os.environ.get("PERF_ROOT", project_root())).resolve()
    db_path = Path(os.environ.get("PERF_DB", root / "data" / "perfkit.sqlite")).resolve()
    reports_dir = Path(os.environ.get("PERF_REPORTS_DIR", root / "reports")).resolve()
    profiles_dir = Path(os.environ.get("PERF_PROFILES_DIR", root / "profiles")).resolve()
    max_users = int(os.environ.get("PERF_MAX_USERS", "25"))
    max_duration = int(os.environ.get("PERF_MAX_DURATION_SECONDS", "180"))
    default_hosts = "localhost,127.0.0.1,::1,demo-api,host.docker.internal"
    allowed = _csv_set(os.environ.get("PERF_ALLOWED_HOSTS", default_hosts))
    if max_users < 1 or max_duration < 5:
        raise ValueError("PERF_MAX_USERS and PERF_MAX_DURATION_SECONDS are too small")
    return Settings(
        root=root,
        db_path=db_path,
        reports_dir=reports_dir,
        profiles_dir=profiles_dir,
        max_users=max_users,
        max_duration_seconds=max_duration,
        allowed_hosts=allowed,
        locust_grace_seconds=int(os.environ.get("PERF_LOCUST_GRACE_SECONDS", "45")),
    )
