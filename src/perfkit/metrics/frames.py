"""Pandas views over measured samples. Aggregates still come from metrics.core."""

from __future__ import annotations

from typing import Any

import pandas as pd

from perfkit.metrics.core import build_timeseries, summarize_endpoints


def samples_frame(samples: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(samples)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "ts",
                "name",
                "method",
                "response_time_ms",
                "status_code",
                "success",
                "error_category",
                "response_length",
            ]
        )
    return frame


def endpoint_frame(samples: list[dict[str, Any]], duration_seconds: float) -> pd.DataFrame:
    rows = summarize_endpoints(samples, duration_seconds)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    # Cross-check the independent percentile helper against pandas' type-7 quantile.
    raw = samples_frame(samples)
    if not raw.empty:
        checked = (
            raw.groupby("name")["response_time_ms"]
            .quantile(0.95, interpolation="linear")
            .rename("pandas_p95_ms")
        )
        frame = frame.merge(checked, left_on="name", right_index=True, how="left")
    return frame


def timeseries_frame(samples: list[dict[str, Any]], bucket_seconds: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame(build_timeseries(samples, bucket_seconds))
