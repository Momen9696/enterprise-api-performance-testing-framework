# Measured results

These rows were produced by `python -m perfkit run` on 24 November 2026 against the local HarborLedger demo at `http://127.0.0.1:8090`. Python 3.13. Locust 2.47. The demo's injected latency was 0 ms because the profiles do not send `X-Demo-Latency-Ms`.

Percentiles are type-7 linear interpolation over every sample, including failures. Throughput is total requests divided by the Locust start-to-stop duration.

| Profile | Run | Duration s | Requests | Success | Failed | RPS | Avg ms | P50 | P95 | P99 | Error % | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | `ad1046e0` | 8.06 | 25 | 25 | 0 | 3.10 | 5.56 | 5.83 | 7.51 | 7.97 | 0 | PASS |
| load | `27a35fef` | 10.04 | 384 | 384 | 0 | 38.24 | 4.47 | 4.25 | 7.74 | 10.36 | 0 | PASS |
| stress | `d785fa87` | 12.05 | 582 | 582 | 0 | 48.29 | 2.98 | 2.18 | 7.31 | 12.54 | 0 | PASS |
| spike | `5d92d901` | 9.05 | 570 | 570 | 0 | 63.01 | 3.25 | 2.64 | 7.07 | 11.25 | 0 | PASS |
| soak | `770488e6` | 15.09 | 221 | 221 | 0 | 14.64 | 5.00 | 5.09 | 8.07 | 10.37 | 0 | PASS |
| concurrent | `564863f5` | 8.03 | 2315 | 2315 | 0 | 288.28 | 2.19 | 1.86 | 4.22 | 6.78 | 0 | PASS |
| endpoint-transactions | `e71528e0` | 8.06 | 306 | 306 | 0 | 37.97 | 4.35 | 3.90 | 7.77 | 16.93 | 0 | PASS |
| ci-smoke | `feb46aab` | 8.05 | 185 | 185 | 0 | 22.97 | 5.01 | 4.96 | 8.25 | 9.65 | 0 | PASS |
| ci-smoke | `9a3684c5` | 8.07 | 181 | 181 | 0 | 22.42 | 4.60 | 4.47 | 8.03 | 10.33 | 0 | PASS |
| threshold-fail-demo | `7bda6051` | 6.08 | 142 | 2 | 140 | 23.35 | 4.26 | 4.28 | 7.26 | 8.80 | 98.59 | FAIL |

[`measured-runs.json`](measured-runs.json) has the same runs with minimum, maximum, and each threshold check.

`threshold-fail-demo` categorized all 140 failures as `http_5xx`. The 2 successes are the virtual users' login calls. The profile's error limit is 5 percent, so the verdict is FAIL even though P95 (7.26 ms) and throughput (23.35 rps) were inside their limits.

## Reports

| File | Run |
| --- | --- |
| [baseline-report.html](baseline-report.html) | baseline |
| [load-report.html](load-report.html) | load |
| [stress-report.html](stress-report.html) | stress |
| [spike-report.html](spike-report.html) | spike |
| [soak-report.html](soak-report.html) | soak |
| [concurrent-report.html](concurrent-report.html) | concurrent |
| [endpoint-transactions-report.html](endpoint-transactions-report.html) | endpoint |
| [ci-smoke-1-report.html](ci-smoke-1-report.html) | first ci-smoke |
| [ci-smoke-2-report.html](ci-smoke-2-report.html) | second ci-smoke |
| [threshold-fail-demo-report.html](threshold-fail-demo-report.html) | expected failure |

Charts in those files load Plotly from a CDN. The tables are in the file and do not need the network. The reports do not contain the demo password or an `Authorization` header.
