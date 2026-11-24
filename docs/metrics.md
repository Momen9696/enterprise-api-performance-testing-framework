# Metric definitions

All figures below are computed from the JSONL written by the Locust request listener. They are not copied from a hand-written table.

## Population

Every completed attempt with a response time is included, including HTTP errors. A timeout recorded by Locust is included and categorized as `timeout`.

## Duration and throughput

`duration_seconds` is the wall time from Locust `test_start` to `test_stop`. If that metadata is missing, the span from the first sample timestamp to the last is used.

```text
rps = total_requests / duration_seconds
```

Endpoint RPS uses the same full-test duration, so a low-weight endpoint is not made to look faster just because its own calls were close together.

## Response times

`min_ms`, `max_ms`, and `avg_ms` are the minimum, maximum, and arithmetic mean of the sample times.

Percentiles use linear interpolation between adjacent ranks (Hyndman–Fan type 7, the same method as `pandas.Series.quantile` with `interpolation="linear"`):

```text
rank = (percent / 100) * (n - 1)
```

Reported percentiles are P50, P90, P95, and P99. For a single sample, every percentile is that sample. For an empty set, the percentile is null and a threshold that needs it fails closed.

The unit tests check hand-calculated values such as P90 of `[10, 20, 30, 40, 50]` = 46, and they check equality with pandas.

## Errors

```text
error_pct = failed / total * 100
```

Failure means Locust recorded an exception or the status was outside `expected_status`.

| Category | When |
| --- | --- |
| `none` | Sample succeeded |
| `timeout` | Exception text indicates a timeout |
| `connection` | Connection failed or was refused |
| `http_5xx` | Status 500–599 |
| `http_4xx` | Status 400–499 |
| `unexpected_status` | Failure text says unexpected and no status was captured |
| `other` | Anything else |

## Time series

Samples are grouped into 1-second buckets from the first timestamp. Bucket RPS is the count in that bucket divided by 1 second. This is the series drawn on the throughput and error charts.

## Trends

For a profile name, completed runs are ordered by start time. With fewer than two runs the status is `insufficient_history`. Otherwise PerfKit reports the first value, last value, delta, and ordinary least-squares slope per run for P95, RPS, and error percentage.

Direction is `stable` when the relative change is under 5 percent. Lower P95 and error rate are improvements. Higher RPS is an improvement.

The two stored `ci-smoke` runs on 24 November 2026 moved P95 from 8.25 ms to 8.03 ms and RPS from 22.97 to 22.42. Both are `stable`.
