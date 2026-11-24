"""Load YAML/JSON profiles and enforce execution caps before a run starts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from perfkit.config.models import TestProfile
from perfkit.security import TargetRejected, validate_base_url
from perfkit.settings import Settings


class ProfileError(ValueError):
    """The profile is syntactically or operationally invalid."""


def _runtime_base_url(base_url: str) -> str:
    """Inside Docker, rewrite loopback targets to PERF_TARGET_URL after it is allowlisted."""
    override = os.environ.get("PERF_TARGET_URL", "").strip()
    if not override:
        return base_url
    host = (urlsplit(base_url).hostname or "").lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        return override
    return base_url


def enforce_caps(profile: TestProfile, settings: Settings) -> TestProfile:
    """Validate the target and reject profiles that exceed the process caps."""
    normalized = validate_base_url(_runtime_base_url(profile.base_url), settings.allowed_hosts)
    if profile.users > settings.max_users:
        raise ProfileError(
            f"users {profile.users} exceeds PERF_MAX_USERS={settings.max_users}"
        )
    if profile.duration_seconds > settings.max_duration_seconds:
        raise ProfileError(
            f"duration {profile.duration_seconds}s exceeds "
            f"PERF_MAX_DURATION_SECONDS={settings.max_duration_seconds}"
        )
    if profile.stages:
        for stage in profile.stages:
            if stage.users > settings.max_users:
                raise ProfileError(
                    f"stage users {stage.users} exceeds PERF_MAX_USERS={settings.max_users}"
                )
    return profile.model_copy(update={"base_url": normalized})


def profile_from_mapping(payload: dict, settings: Settings) -> TestProfile:
    try:
        profile = TestProfile.model_validate(payload)
        return enforce_caps(profile, settings)
    except ProfileError:
        raise
    except (TargetRejected, Exception) as exc:
        raise ProfileError(str(exc)) from exc


def load_profile_file(path: Path, settings: Settings) -> TestProfile:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ProfileError("profile root must be a mapping")
    return profile_from_mapping(payload, settings)


def resolve_profile_name(name: str, settings: Settings) -> Path:
    """Resolve a profile file name inside the profiles directory only."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ProfileError("profile name must be a file name inside the profiles directory")
    root = settings.profiles_dir.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root:
        raise ProfileError("profile path escapes the profiles directory")
    if candidate.suffix.lower() not in {".yaml", ".yml", ".json"}:
        raise ProfileError("profile must be YAML or JSON")
    if not candidate.is_file():
        raise ProfileError(f"profile {name!r} was not found")
    return candidate


def list_profile_files(settings: Settings) -> list[Path]:
    if not settings.profiles_dir.exists():
        return []
    files = [
        path
        for path in settings.profiles_dir.iterdir()
        if path.suffix.lower() in {".yaml", ".yml", ".json"} and path.is_file()
    ]
    return sorted(files, key=lambda item: item.name)
