# Locust execution

PerfKit does not ask you to write a locustfile per service. `src/perfkit/engine/locustfile.py` reads the redacted profile and builds one `HttpUser`.

What the child process does:

- logs in once per user when `PERF_AUTH_MODE` is `bearer` or `api_key`
- schedules endpoints by repeating tasks according to `weight`
- renders `{{uuid}}`, `{{seq}}`, `{{int:min,max}}`, and `{{choice:...}}` per call
- waits between tasks using the profile's `wait` range
- optionally pads each iteration to `pacing.min_iteration_seconds`
- follows `resolved_stages` in a `LoadTestShape`
- disables redirects and applies `request_timeout_seconds`
- appends one JSON object per request to `samples.jsonl`
- writes `meta.json` with the test start, stop, and Locust's own total RPS

Headless invocation, built only from validated numbers and the allowlisted base URL:

```text
python -m locust -f src/perfkit/engine/locustfile.py --headless --only-summary \
  --users <peak> --spawn-rate <rate> --run-time <safety>s --stop-timeout 5 \
  --host <base_url>
```

`--run-time` is longer than the stage plan so a stuck shape cannot run forever. When the shape returns `None`, Locust stops.

## Run a profile

```bash
export PYTHONPATH=src
export DEMO_API_PASSWORD=demo-local-only
python -m perfkit demo
python -m perfkit run --profile profiles/spike.yaml
```

Useful profiles:

| File | What it shows |
| --- | --- |
| `profiles/baseline.yaml` | One user, one endpoint family |
| `profiles/load.yaml` | Steady mix of reads and a small write |
| `profiles/stress.yaml` | Four explicit steps up to 8 users |
| `profiles/spike.yaml` | 1 user, then 8, then 1 |
| `profiles/soak.yaml` | 3 users for 15 seconds |
| `profiles/concurrent.yaml` | 8 users and a very short wait |
| `profiles/endpoint.yaml` | Only `GET /transactions` |
| `profiles/ci-smoke.yaml` | The bounded CI profile |
| `profiles/threshold-fail-demo.yaml` | A profile that is expected to fail its error budget |

Raise `PERF_MAX_DURATION_SECONDS` before pointing a soak profile at a multi-minute window. Keep the target on the allowlist.

## Direct Locust

You can point Locust at the same file if you need the Locust UI locally. Set `PERF_PROFILE_JSON` to a redacted profile that already contains `resolved_stages`, and set the auth environment variables yourself. Do not point `--host` at a system you do not control. The control-plane runner is the supported path because it enforces the allowlist before the process starts.
