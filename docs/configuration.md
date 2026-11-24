# Profile configuration

Profiles are YAML or JSON. The loader validates them with Pydantic, then checks the target and the process caps.

```yaml
name: load
test_type: load          # load, stress, spike, soak, baseline, concurrent, endpoint
base_url: http://127.0.0.1:8090
users: 5
spawn_rate: 5
duration_seconds: 10
request_timeout_seconds: 5
wait:
  min_seconds: 0.05
  max_seconds: 0.2
pacing:
  min_iteration_seconds: 0.2   # optional floor between task starts
auth:
  mode: bearer                 # none, bearer, api_key
  login_path: /auth/token
  username: demo
  password_env: DEMO_API_PASSWORD
thresholds:
  max_p95_ms: 1000
  max_p99_ms: 2000
  min_rps: 2
  max_error_pct: 2
endpoints:
  - name: list_users
    method: GET
    path: /users
    weight: 3
    headers:
      X-Perfkit-Scenario: load
    query:
      page: "1"
  - name: create_transaction
    method: POST
    path: /transactions
    weight: 1
    expected_status: [201]
    json_body:
      account_id: "acct-{{choice:1001,1002,1003}}"
      amount: "{{int:1,5}}"
      description: "load-{{uuid}}"
```

## Fields

| Field | Role |
| --- | --- |
| `users`, `spawn_rate`, `duration_seconds` | Peak users, spawn slope, and safety window |
| `wait` | Locust think time between tasks |
| `pacing.min_iteration_seconds` | Extra sleep so an iteration cannot finish faster than this |
| `endpoints[].weight` | Relative chance the user picks that endpoint |
| `expected_status` | Anything else is a failed sample |
| `stages` | Optional explicit shape. The sum of stage durations cannot exceed `duration_seconds`, and no stage can ask for more users than `users` |

`baseline` requires `users: 1`. `endpoint` requires exactly one endpoint.

## Dynamic data

Tokens are allowlisted. There is no expression language.

| Token | Result |
| --- | --- |
| `{{uuid}}` | Short random id |
| `{{seq}}` | Per-user counter |
| `{{int:1,5}}` | Integer in the inclusive range. A whole-value int token stays an integer |
| `{{choice:a,b}}` | One of the options |

`{{os.system(...)}}` is rejected.

## Authentication

Prefer `password_env` or `api_key_env`. The value is copied into the Locust process environment and is not written to the stored profile, the HTML report, or the JSON export. Inline `password` is accepted and redacted before storage.

Do not put `Authorization` on an endpoint header if you also use `auth.mode`. The runner adds the header after login.

## Caps and targets

| Variable | Default | Effect |
| --- | --- | --- |
| `PERF_MAX_USERS` | 25 | Rejects larger profiles |
| `PERF_MAX_DURATION_SECONDS` | 180 | Rejects longer profiles |
| `PERF_ALLOWED_HOSTS` | localhost, 127.0.0.1, ::1, demo-api, host.docker.internal | Names that may be targeted if they resolve privately |
| `PERF_TARGET_URL` | unset | Rewrites loopback profile URLs, then allowlists the result |

Literal IP targets must be loopback. `example.com`, `169.254.169.254`, and URLs with embedded passwords are rejected.

## API

`POST /api/runs` accepts `{"profile_name": "load.yaml"}` or an inline `profile` object. `profile_name` is a file name inside `profiles/`, not a path. `POST /api/profiles/validate` checks a document without starting Locust.
