"""Target allowlisting, header masking, and secret redaction.

Profiles cannot aim the runner at arbitrary public hosts. Only loopback addresses
and explicitly configured hostnames that resolve to loopback or private addresses
are accepted. That keeps a misconfigured profile from generating load against
systems the operator does not control.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit

SENSITIVE_KEYS = {
    "password",
    "api_key",
    "token",
    "access_token",
    "authorization",
    "secret",
    "cookie",
    "set-cookie",
    "proxy-authorization",
}
SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "proxy-authorization",
}
_BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.google.com",
}
_HEADER_BREAK = re.compile(r"[\r\n\x00]")


class TargetRejected(ValueError):
    """The profile target is outside the configured allowlist."""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # ::1 is both loopback and reserved in the stdlib. Loopback is allowed.
    if ip.is_loopback:
        return False
    return bool(
        ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
        or ip.is_link_local
        or str(ip) == "169.254.169.254"
    )


def validate_base_url(base_url: str, allowed_hosts: frozenset[str] | set[str]) -> str:
    """Return a normalized base URL or raise TargetRejected."""
    if not isinstance(base_url, str) or not base_url.strip():
        raise TargetRejected("base_url is required")
    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"http", "https"}:
        raise TargetRejected("base_url scheme must be http or https")
    if parts.username or parts.password:
        raise TargetRejected("credentials embedded in base_url are not allowed")
    if parts.query or parts.fragment:
        raise TargetRejected("base_url must not include a query or fragment")
    host = parts.hostname
    if host is None:
        raise TargetRejected("base_url host is missing")
    host_l = host.lower().rstrip(".")
    if host_l in _BLOCKED_HOSTS:
        raise TargetRejected("metadata service hosts are blocked")
    try:
        port = parts.port
    except ValueError as exc:
        raise TargetRejected("base_url port is invalid") from exc
    if port is None:
        port = 443 if parts.scheme == "https" else 80

    allowed = {item.lower() for item in allowed_hosts}
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    try:
        ip_obj = ipaddress.ip_address(host_l)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        if _is_blocked_ip(ip_obj) or not ip_obj.is_loopback:
            raise TargetRejected("only loopback IP addresses are allowed as literal targets")
    else:
        if host_l not in allowed and not host_l.endswith(".localhost"):
            raise TargetRejected(
                f"host {host_l!r} is not in PERF_ALLOWED_HOSTS; external targets are rejected"
            )
        try:
            infos = socket.getaddrinfo(host_l, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise TargetRejected(f"host {host_l!r} did not resolve") from exc
        for info in infos:
            resolved = ipaddress.ip_address(info[4][0])
            if _is_blocked_ip(resolved):
                raise TargetRejected(f"host {host_l!r} resolves to a blocked address")
            # Allowlisted names may be a docker bridge (private) or loopback.
            # Public addresses stay blocked so an allowlist typo cannot hit the internet.
            if not (resolved.is_loopback or resolved.is_private):
                raise TargetRejected(
                    f"host {host_l!r} resolves to a public address and is blocked"
                )

    netloc = host_l if ip_obj is None else str(ip_obj)
    if ":" in netloc and not netloc.startswith("["):
        netloc = f"[{netloc}]"
    default_port = 443 if parts.scheme == "https" else 80
    if port != default_port:
        netloc = f"{netloc}:{port}"
    path = parts.path.rstrip("/")
    return f"{parts.scheme}://{netloc}{path}"


def validate_header(name: str, value: str) -> None:
    if not name or _HEADER_BREAK.search(name) or _HEADER_BREAK.search(value or ""):
        raise ValueError(f"invalid header {name!r}")
    if name.strip() != name or value != value.strip():
        raise ValueError(f"header {name!r} must not have surrounding whitespace")


def mask_headers(headers: dict[str, str] | None) -> dict[str, str]:
    masked: dict[str, str] = {}
    for key, value in (headers or {}).items():
        if key.lower() in SENSITIVE_HEADERS:
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def redact(value: object) -> object:
    """Recursively mask secret-like keys. Used before profiles are stored or reported."""
    if isinstance(value, dict):
        cleaned: dict[object, object] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in SENSITIVE_KEYS or key_text in SENSITIVE_HEADERS:
                cleaned[key] = "***" if item not in (None, "") else item
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def scrub_text(text: str, extra_secrets: list[str] | None = None) -> str:
    cleaned = text or ""
    cleaned = re.sub(
        r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)(\S+)",
        r"\1***",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)((?:password|api_key|token|secret)[\"']?\s*[:=]\s*[\"']?)([^\"'\s,}]+)",
        r"\1***",
        cleaned,
    )
    for secret in extra_secrets or []:
        if secret and len(secret) >= 4:
            cleaned = cleaned.replace(secret, "***")
    if len(cleaned) > 4000:
        cleaned = cleaned[-4000:]
    return cleaned
