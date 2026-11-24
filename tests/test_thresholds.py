"""Threshold verdicts and trend direction."""

from __future__ import annotations

from perfkit.metrics.thresholds import evaluate_thresholds
from perfkit.metrics.trends import analyze_trend


def test_pass_and_fail_are_per_profile() -> None:
    metrics = {"p95_ms": 120, "p99_ms": 240, "rps": 8, "error_pct": 1}
    passed = evaluate_thresholds(
        metrics,
        {"max_p95_ms": 200, "max_p99_ms": 400, "min_rps": 5, "max_error_pct": 2},
    )
    assert passed["verdict"] == "PASS"
    assert len(passed["checks"]) == 4
    failed = evaluate_thresholds(metrics, {"max_p95_ms": 100, "min_rps": 1})
    assert failed["verdict"] == "FAIL"
    assert [item["metric"] for item in failed["checks"] if not item["passed"]] == ["p95_ms"]


def test_missing_metric_fails_closed() -> None:
    result = evaluate_thresholds({"p95_ms": None, "rps": 1}, {"max_p95_ms": 10, "min_rps": 1})
    assert result["verdict"] == "FAIL"
    assert result["checks"][0]["reason"] == "metric was not measured"


def test_no_thresholds_is_not_a_pass() -> None:
    result = evaluate_thresholds({"p95_ms": 1, "rps": 1, "error_pct": 0}, {})
    assert result["verdict"] == "NOT_EVALUATED"
    assert result["checks"] == []


def test_trend_directions() -> None:
    history = [
        {"p95_ms": 100, "rps": 5, "error_pct": 4, "started_at": "t1"},
        {"p95_ms": 140, "rps": 9, "error_pct": 1, "started_at": "t2"},
    ]
    trend = analyze_trend(history)
    assert trend["status"] == "ok"
    assert trend["p95_ms"]["direction"] == "degrading"
    assert trend["rps"]["direction"] == "improving"
    assert trend["error_pct"]["direction"] == "improving"
    assert analyze_trend(history[:1])["status"] == "insufficient_history"


def test_trend_stable_band() -> None:
    history = [
        {"p95_ms": 100, "rps": 10, "error_pct": 1},
        {"p95_ms": 103, "rps": 10.2, "error_pct": 1.02},
    ]
    trend = analyze_trend(history)
    assert trend["p95_ms"]["direction"] == "stable"
