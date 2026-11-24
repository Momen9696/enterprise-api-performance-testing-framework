# Troubleshooting

## `host is not in PERF_ALLOWED_HOSTS`

The profile's `base_url` is not loopback and not on the allowlist. Add the hostname to `PERF_ALLOWED_HOSTS` only when you control that host. It must resolve to a loopback or private address. Public DNS answers are rejected even if the name is listed.

## `users N exceeds PERF_MAX_USERS`

Raise `PERF_MAX_USERS` deliberately. The default is 25 so a profile cannot fork a large load by accident.

## `bearer password was empty`

Export the variable named by `auth.password_env` before `perfkit run`. For the bundled profiles that variable is `DEMO_API_PASSWORD`. The demo process must use the same value. The default fixture value is `demo-local-only` when the variable is unset in the demo, and the CLI sets that default for local runs.

## Locust produced no samples

Check `reports/<run-id>/stderr.log`. Common causes are a demo that is not listening, a wrong port, or an import error because `PYTHONPATH` does not include `src`. The runner adds `src` for the child when you use `python -m perfkit`.

## Dashboard charts are empty but the table has numbers

The page loads Plotly from a CDN. The KPI and endpoint tables are rendered from the API and do not need that script. Connect to the network or open the HTML report, which also uses the CDN for charts and still contains the numeric tables offline.

## A run stays `running`

Only one run is active. `POST /api/runs/{id}/cancel` terminates the Locust process PerfKit started. It will not kill unrelated processes.

## Docker target still hits 127.0.0.1

Set `PERF_TARGET_URL=http://demo-api:8090` on the engine container. Compose does this. The rewrite applies only when the profile host is loopback, and the new URL is allowlisted before the run.

## Port 8090 is already in use

Stop the other demo or change both the demo port and the profile `base_url`. Inside Compose the published host port can be changed without editing profiles, because the engine uses the Docker DNS name.

## CI smoke is slower than the workstation numbers

The committed examples were measured on a local macOS loopback with no injected latency. GitHub-hosted runners are slower. `ci-smoke.yaml` limits are 1000 ms P95 and 1 rps so the smoke still checks for real failures without depending on this workstation's 8 ms P95.

## Secret scan failure

`python -m perfkit scan` flags private keys and common token prefixes. Do not commit `.env`. The fixture password string is intentionally not a live credential pattern.
