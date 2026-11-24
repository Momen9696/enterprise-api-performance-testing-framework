"""Lightweight secret scan used before publication and in CI. Not a full DLP product."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("stripe-live", re.compile(r"sk_live_[A-Za-z0-9]{16,}")),
)
_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "data"}
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".sqlite", ".db", ".pyc"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str


def scan_repository(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in _SKIP_SUFFIXES:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for index, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in _RULES:
                if pattern.search(line):
                    findings.append(Finding(str(path.relative_to(root)), index, rule))
    return findings
