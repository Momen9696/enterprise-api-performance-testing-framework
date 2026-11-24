# Upwork portfolio description

**Enterprise API Performance and Load Testing Framework (Python, Locust, FastAPI)**

I designed and built a reusable performance framework for HTTP APIs. A YAML profile defines the target, endpoints, weights, auth, think time, pacing, virtual users, and the load shape. The runner executes Locust headlessly, stores each sample, and computes throughput, error rate, and P50, P90, P95, and P99 with the standard linear percentile method. Thresholds are per profile. A missing limit is not treated as a pass.

The system under test is a local FastAPI ledger demo with synthetic users, accounts, transactions, search, pagination, validation, opt-in latency, and a controlled fault endpoint. Profiles cannot target public hosts. Passwords stay in the environment and are redacted from SQLite, HTML, and JSON exports.

Verification on the published code, from runs on 24 November 2026 against `127.0.0.1` with no injected latency:

- 49 pytest tests passed, including percentile checks, threshold verdicts, URL allowlisting, the demo API, the control plane, and a live Locust smoke
- `pip-audit` reported no known vulnerabilities in the runtime requirements
- Bandit completed with no remaining findings after the SQL update path was made static and process starts were kept as argument vectors
- Load, stress, spike, soak, baseline, concurrent, and endpoint profiles all completed with 0 percent errors
- The bounded soak (15 seconds, 3 users) measured 221 requests, 14.64 rps, P95 8.07 ms
- The concurrent profile (8 users, 8 seconds) measured 2315 requests, 288.28 rps, P95 4.22 ms
- A fault-injection profile failed its own 5 percent error budget on a measured 98.59 percent `http_5xx` rate, while P95 still passed
- Two smoke runs were stable: P95 8.25 ms then 8.03 ms

GitHub Actions installs dependencies, runs the suite, executes the bounded smoke again, and uploads the HTML report. Docker Compose runs the demo and the control plane with health checks and a persistent results volume.

**Skills:** Python, Locust, FastAPI, Pydantic, Pytest, Pandas, Plotly, SQLite, Docker, GitHub Actions, performance testing, API test architecture
