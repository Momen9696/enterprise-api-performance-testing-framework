"""Percentile and aggregation accuracy."""

from __future__ import annotations

import pandas as pd
import pytest

from perfkit.metrics.core import (
    build_timeseries,
    categorize_error,
    measured_duration,
    percentile,
    summarize,
    summarize_endpoints,
)
from perfkit.metrics.frames import endpoint_frame


def test_percentile_matches_type7_examples() -> None:
    values = [10, 20, 30, 40, 50]
    assert percentile(values, 50) == 30
    assert percentile(values, 90) == pytest.approx(46)
    assert percentile(values, 95) == pytest.approx(48)
    assert percentile(values, 99) == pytest.approx(49.6)
    assert percentile(values, 0) == 10
    assert percentile(values, 100) == 50


def test_percentile_matches_pandas_quantile() -> None:
    values = [4, 8, 15, 16, 23, 42]
    series = pd.Series(values)
    for percent in (50, 90, 95, 99):
        assert percentile(values, percent) == pytest.approx(series.quantile(percent / 100, interpolation="linear"))


def test_percentile_edges() -> None:
    assert percentile([], 95) is None
    assert percentile([7], 99) == 7
    with pytest.raises(ValueError):
        percentile([1, 2], 101)


def test_summarize_rates_and_categories() -> None:
    samples = [
        {"response_time_ms": 10, "success": True, "error_category": "none", "name": "a", "method": "GET", "ts": 1},
        {"response_time_ms": 30, "success": True, "error_category": "none", "name": "a", "method": "GET", "ts": 2},
        {"response_time_ms": 50, "success": False, "error_category": "http_5xx", "name": "b", "method": "POST", "ts": 3},
    ]
    summary = summarize(samples, duration_seconds=2)
    assert summary["total"] == 3
    assert summary["successful"] == 2
    assert summary["failed"] == 1
    assert summary["rps"] == pytest.approx(1.5)
    assert summary["error_pct"] == pytest.approx(100 / 3)
    assert summary["min_ms"] == 10
    assert summary["max_ms"] == 50
    assert summary["avg_ms"] == pytest.approx(30)
    assert summary["error_categories"] == {"http_5xx": 1}
    assert summary["p50_ms"] == 30


def test_endpoint_rps_uses_full_duration() -> None:
    samples = [
        {"response_time_ms": 10, "success": True, "error_category": "none", "name": "a", "method": "GET", "ts": 0},
        {"response_time_ms": 20, "success": False, "error_category": "timeout", "name": "b", "method": "GET", "ts": 1},
    ]
    rows = summarize_endpoints(samples, duration_seconds=4)
    by_name = {row["name"]: row for row in rows}
    assert by_name["a"]["rps"] == pytest.approx(0.25)
    assert by_name["b"]["error_pct"] == 100
    frame = endpoint_frame(samples, 4)
    assert frame.loc[frame["name"] == "a", "p95_ms"].iloc[0] == pytest.approx(
        frame.loc[frame["name"] == "a", "pandas_p95_ms"].iloc[0]
    )


def test_timeseries_buckets() -> None:
    samples = [
        {"ts": 10.1, "response_time_ms": 5, "success": True, "error_category": "none"},
        {"ts": 10.4, "response_time_ms": 15, "success": False, "error_category": "http_4xx"},
        {"ts": 11.2, "response_time_ms": 8, "success": True, "error_category": "none"},
    ]
    rows = build_timeseries(samples, bucket_seconds=1)
    assert len(rows) == 2
    assert rows[0]["total"] == 2
    assert rows[0]["rps"] == pytest.approx(2)
    assert rows[0]["error_pct"] == pytest.approx(50)
    assert rows[1]["total"] == 1


def test_measured_duration_prefers_meta() -> None:
    samples = [{"ts": 5}, {"ts": 9}]
    assert measured_duration(samples, {"start": 1, "end": 3}) == pytest.approx(2)
    assert measured_duration(samples, {}) == pytest.approx(4)
    assert measured_duration([{"ts": 1}], {}) == pytest.approx(0.001)


@pytest.mark.parametrize(
    ("exception_name", "message", "status", "success", "expected"),
    [
        (None, "", 200, True, "none"),
        ("ReadTimeout", "timed out", None, False, "timeout"),
        ("ConnectionError", "connection refused", None, False, "connection"),
        (None, "unexpected status 503", 503, False, "http_5xx"),
        (None, "unexpected status 404", 404, False, "http_4xx"),
        ("CatchResponseError", "no status", None, False, "other"),
    ],
)
def test_error_categories(exception_name, message, status, success, expected) -> None:
    assert categorize_error(exception_name, message, status, success) == expected
