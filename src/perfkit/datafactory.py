"""Tiny template renderer for synthetic request data.

Supported whole-value or embedded tokens:

- ``{{uuid}}``
- ``{{seq}}``
- ``{{int:min,max}}``
- ``{{choice:a,b,c}}``

There is no expression language and no attribute lookup, so profile data cannot
execute code.
"""

from __future__ import annotations

import itertools
import random
import re
import uuid
from typing import Any

_TOKEN = re.compile(r"\{\{([a-z]+)(?::([^{}]*))?\}\}")
_ALLOWED = {"uuid", "seq", "int", "choice"}


class TemplateError(ValueError):
    """A data token is malformed or not on the allowlist."""


def _render_token(kind: str, arg: str | None, rng: random.Random, seq: itertools.count) -> str:
    if kind not in _ALLOWED:
        raise TemplateError(f"unsupported token {kind!r}")
    if kind == "uuid":
        if arg:
            raise TemplateError("uuid does not take arguments")
        return uuid.uuid4().hex[:12]
    if kind == "seq":
        if arg:
            raise TemplateError("seq does not take arguments")
        return str(next(seq))
    if kind == "int":
        if not arg or "," not in arg:
            raise TemplateError("int token requires min,max")
        left, right = arg.split(",", 1)
        start, end = int(left), int(right)
        if end < start or end - start > 1_000_000:
            raise TemplateError("int range is invalid")
        return str(rng.randint(start, end))
    if not arg:
        raise TemplateError("choice token requires options")
    options = [part.strip() for part in arg.split(",") if part.strip()]
    if not options:
        raise TemplateError("choice token has no options")
    return str(rng.choice(options))


def render_value(value: Any, rng: random.Random, seq: itertools.count) -> Any:
    if isinstance(value, dict):
        return {str(key): render_value(item, rng, seq) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, rng, seq) for item in value]
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    whole = _TOKEN.fullmatch(stripped)
    if whole and whole.group(1) == "int":
        return int(_render_token("int", whole.group(2), rng, seq))

    def replace(match: re.Match[str]) -> str:
        return _render_token(match.group(1), match.group(2), rng, seq)

    if "{{" in value and not _TOKEN.search(value):
        raise TemplateError(f"malformed token in {value!r}")
    return _TOKEN.sub(replace, value)


def render_endpoint_payload(
    query: dict[str, Any],
    body: Any,
    headers: dict[str, str],
    rng: random.Random,
    seq: itertools.count,
) -> tuple[dict[str, str], Any, dict[str, str]]:
    rendered_query = {key: str(render_value(item, rng, seq)) for key, item in query.items()}
    rendered_body = render_value(body, rng, seq) if body is not None else None
    rendered_headers = {key: str(render_value(item, rng, seq)) for key, item in headers.items()}
    return rendered_query, rendered_body, rendered_headers
