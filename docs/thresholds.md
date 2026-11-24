# Thresholds

Thresholds belong to the profile. PerfKit does not ship a universal P95 or error target.

| Profile field | Check |
| --- | --- |
| `max_p95_ms` | measured P95 must be less than or equal to the limit |
| `max_p99_ms` | measured P99 must be less than or equal to the limit |
| `min_rps` | measured throughput must be greater than or equal to the limit |
| `max_error_pct` | measured error percentage must be less than or equal to the limit |

Omitted fields are not checked. If a profile sets none of them, the verdict is `NOT_EVALUATED` rather than a default PASS.

If a configured metric was not measured, that check fails.

The run verdict:

| Verdict | Meaning |
| --- | --- |
| `PASS` | Every configured check passed |
| `FAIL` | At least one configured check failed |
| `NOT_EVALUATED` | No thresholds were set, or the run was cancelled |
| `ERROR` | The run produced no samples or Locust failed before ingestion |

## Example that passes

`profiles/ci-smoke.yaml` allows P95 up to 1000 ms, P99 up to 2000 ms, at least 1 request/second, and at most 2 percent errors. The 24 November run measured P95 at 8.25 ms, P99 at 9.65 ms, 22.97 rps, and 0 percent errors. Verdict: PASS.

Those limits are wide on purpose so a small CI runner can still detect a broken demo without pretending that 1000 ms is an acceptable production SLO. Replace them per service.

## Example that fails

`profiles/threshold-fail-demo.yaml` allows at most 5 percent errors and calls `/demo/fault?status=500` while expecting 200. The measured run had 140 `http_5xx` failures out of 142 requests (98.59 percent). P95 and throughput passed. The error check failed, so the verdict is FAIL.

## Where the verdict appears

- the `perfkit run` stdout line
- `runs.verdict` in SQLite
- the badge on the dashboard
- the threshold table in the HTML report
- `GET /api/runs/{id}`
