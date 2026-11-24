"""Compare measured metrics with the limits declared on a single profile."""

from __future__ import annotations

from typing import Any

# metric key, operator, threshold field
_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("p95_ms", "<=", "max_p95_ms"),
    ("p99_ms", "<=", "max_p99_ms"),
    ("rps", ">=", "min_rps"),
    ("error_pct", "<=", "max_error_pct"),
)


def evaluate_thresholds(metrics: dict[str, Any], thresholds: dict[str, Any] | None) -> dict[str, Any]:
    configured = []
    for metric, operator, field in _CHECKS:
        if not thresholds or thresholds.get(field) is None:
            continue
        limit = float(thresholds[field])
        actual = metrics.get(metric)
        if actual is None:
            passed = False
            reason = "metric was not measured"
        elif operator == "<=":
            passed = float(actual) <= limit
            reason = ""
        else:
            passed = float(actual) >= limit
            reason = ""
        configured.append(
            {
                "metric": metric,
                "operator": operator,
                "limit": limit,
                "actual": None if actual is None else float(actual),
                "passed": passed,
                "reason": reason,
            }
        )
    if not configured:
        return {"verdict": "NOT_EVALUATED", "checks": []}
    verdict = "PASS" if all(item["passed"] for item in configured) else "FAIL"
    return {"verdict": verdict, "checks": configured}
