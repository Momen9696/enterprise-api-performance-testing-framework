"""HarborLedger demo API behavior. These tests do not measure performance."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from perfkit.demo.app import app

client = TestClient(app)


def _token() -> str:
    response = client.post("/auth/token", json={"username": "demo", "password": "demo-local-only"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_health_is_public_and_users_require_auth() -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/users").status_code == 401
    denied = client.post("/auth/token", json={"username": "demo", "password": "wrong-password"})
    assert denied.status_code == 401


def test_pagination_search_and_validation() -> None:
    headers = {"Authorization": f"Bearer {_token()}"}
    page = client.get("/transactions", params={"page": 2, "page_size": 10}, headers=headers)
    assert page.status_code == 200
    assert page.json()["page"] == 2
    assert len(page.json()["items"]) == 10
    missing = client.get("/users/usr-missing", headers=headers)
    assert missing.status_code == 404
    invalid = client.post(
        "/transactions",
        headers=headers,
        json={"account_id": "acct-1001", "amount": 0, "description": "nope"},
    )
    assert invalid.status_code == 422
    overdraft = client.post(
        "/transactions",
        headers=headers,
        json={"account_id": "acct-2001", "amount": 6, "description": "too much"},
    )
    assert overdraft.status_code == 409
    found = client.get("/search", params={"q": "quinn"}, headers=headers)
    assert found.status_code == 200
    assert found.json()["users"][0]["id"] == "usr-1001"
    empty = client.get("/search", params={"q": "a"}, headers=headers)
    assert empty.status_code == 422


def test_controlled_fault_and_opt_in_latency() -> None:
    headers = {"Authorization": f"Bearer {_token()}", "X-Demo-Latency-Ms": "80"}
    started = time.perf_counter()
    response = client.get("/demo/fault", params={"status": 503}, headers=headers)
    elapsed = time.perf_counter() - started
    assert response.status_code == 503
    assert response.headers["X-Demo-Injected-Latency-Ms"] == "80"
    assert elapsed >= 0.07
    rejected = client.get("/demo/fault", params={"status": 418}, headers=headers)
    assert rejected.status_code == 400
