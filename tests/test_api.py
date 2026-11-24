"""Control-plane API validation and error handling."""

from __future__ import annotations

from fastapi.testclient import TestClient

from perfkit.api.app import create_app
from perfkit.settings import Settings


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_dashboard_profiles_and_rejections(settings: Settings) -> None:
    client = _client(settings)
    assert client.get("/health").json()["status"] == "ok"
    page = client.get("/")
    assert page.status_code == 200
    assert "Measured API performance" in page.text
    profiles = client.get("/api/profiles")
    assert profiles.status_code == 200
    names = [item["file"] for item in profiles.json()["profiles"]]
    assert "ci-smoke.yaml" in names
    assert "spike.yaml" in names
    rejected = client.post(
        "/api/profiles/validate",
        json={
            "name": "external",
            "test_type": "load",
            "base_url": "https://example.com",
            "duration_seconds": 8,
            "endpoints": [{"name": "root", "method": "GET", "path": "/"}],
        },
    )
    assert rejected.status_code == 422
    assert "example.com" in rejected.json()["detail"]
    traversal = client.post("/api/runs", json={"profile_name": "../ci-smoke.yaml"})
    assert traversal.status_code == 422
    both = client.post(
        "/api/runs",
        json={"profile_name": "ci-smoke.yaml", "profile": {"name": "x"}},
    )
    assert both.status_code == 422
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/runs/missing/export.json").status_code == 404
    assert client.get("/api/runs/missing/export.csv").status_code == 404
    assert client.get("/api/runs/missing/report").status_code == 404
    assert client.post("/api/runs/missing/cancel").status_code == 404
    bad_view = client.get("/api/runs/missing/export.csv?view=shell")
    assert bad_view.status_code == 422


def test_active_run_is_empty(settings: Settings) -> None:
    client = _client(settings)
    assert client.get("/api/runs/active").json()["active"] is None
    assert client.get("/api/runs").json()["runs"] == []
    trend = client.get("/api/trends", params={"name": "ci-smoke"})
    assert trend.status_code == 200
    assert trend.json()["analysis"]["status"] == "insufficient_history"
