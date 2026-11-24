"""Control-plane API. Profiles are validated; Locust is started only by ExecutionService."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, ValidationError

from perfkit import __version__
from perfkit.config.loader import (
    ProfileError,
    list_profile_files,
    load_profile_file,
    profile_from_mapping,
    resolve_profile_name,
)
from perfkit.config.models import TestProfile
from perfkit.engine.service import ExecutionBusy, ExecutionService
from perfkit.metrics.trends import analyze_trend
from perfkit.reports.charts import figures_for_run, trend_figure
from perfkit.reports.export import export_payload, write_csv, write_json
from perfkit.security import TargetRejected
from perfkit.settings import Settings, load_settings
from perfkit.storage.db import Database

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard" / "index.html"


class RunRequest(BaseModel):
    profile_name: str | None = None
    profile: dict[str, Any] | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    database = Database(settings)
    service = ExecutionService(settings, database)
    app = FastAPI(title="PerfKit Control Plane", version=__version__)
    app.state.settings = settings
    app.state.db = database
    app.state.service = service

    @app.exception_handler(ProfileError)
    async def _profile_error(_: Request, exc: ProfileError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(TargetRejected)
    async def _target_error(_: Request, exc: TargetRejected) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ExecutionBusy)
    async def _busy(_: Request, exc: ExecutionBusy) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "perfkit", "version": __version__}

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        if not DASHBOARD.exists():
            raise HTTPException(status_code=500, detail="dashboard asset missing")
        return HTMLResponse(DASHBOARD.read_text(encoding="utf-8"))

    @app.get("/api/profiles")
    def profiles() -> dict[str, Any]:
        items = []
        for path in list_profile_files(settings):
            try:
                profile = load_profile_file(path, settings)
                items.append(
                    {
                        "file": path.name,
                        "name": profile.name,
                        "test_type": profile.test_type,
                        "users": profile.users,
                        "duration_seconds": profile.duration_seconds,
                        "base_url": profile.base_url,
                    }
                )
            except (ProfileError, TargetRejected, OSError) as exc:
                items.append({"file": path.name, "error": str(exc)})
        return {"profiles": items}

    @app.post("/api/profiles/validate")
    def validate(body: dict[str, Any]) -> dict[str, Any]:
        profile = profile_from_mapping(body, settings)
        return {"valid": True, "name": profile.name, "base_url": profile.base_url}

    @app.post("/api/runs", status_code=202)
    def start_run(body: RunRequest) -> dict[str, str]:
        profile = _resolve_request(body, settings)
        run_id = service.start(profile)
        return {"id": run_id, "status": "running"}

    @app.get("/api/runs")
    def list_runs(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        return {"runs": database.list_runs(limit)}

    @app.get("/api/runs/active")
    def active() -> dict[str, Any]:
        run_id = service.active_id
        if run_id is None:
            return {"active": None}
        return {"active": database.get_run(run_id)}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = database.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.post("/api/runs/{run_id}/cancel")
    def cancel(run_id: str) -> dict[str, str]:
        try:
            service.cancel(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run is not active") from exc
        return {"id": run_id, "status": "cancelling"}

    @app.get("/api/runs/{run_id}/export.json")
    def export_json(run_id: str) -> JSONResponse:
        run = _require(database, run_id)
        return JSONResponse(export_payload(run))

    @app.get("/api/runs/{run_id}/export.csv")
    def export_csv(run_id: str, view: str = Query(default="endpoints")) -> PlainTextResponse:
        if view not in {"endpoints", "timeseries", "thresholds"}:
            raise HTTPException(status_code=422, detail="view must be endpoints, timeseries, or thresholds")
        run = _require(database, run_id)
        target = settings.reports_dir / run_id / f"{view}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        write_csv(run, target, view=view)
        return PlainTextResponse(target.read_text(encoding="utf-8"), media_type="text/csv")

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str) -> FileResponse:
        _require(database, run_id)
        path = settings.reports_dir / run_id / "report.html"
        if not path.exists():
            raise HTTPException(status_code=404, detail="report not ready")
        return FileResponse(path, media_type="text/html")

    @app.get("/api/runs/{run_id}/charts")
    def charts(run_id: str) -> dict[str, Any]:
        run = _require(database, run_id)
        samples = database.samples_for(run_id)
        return figures_for_run(run, samples)

    @app.get("/api/trends")
    def trends(name: str = Query(min_length=1, max_length=80)) -> dict[str, Any]:
        history = database.history_for_name(name)
        analysis = analyze_trend(history)
        figure = trend_figure(analysis["series"]) if analysis.get("status") == "ok" else None
        return {"name": name, "analysis": analysis, "chart": figure}

    @app.post("/api/runs/{run_id}/files.json")
    def materialize_json(run_id: str) -> dict[str, str]:
        run = _require(database, run_id)
        path = settings.reports_dir / run_id / "summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(run, path)
        return {"path": str(path)}

    return app


def _require(database: Database, run_id: str) -> dict[str, Any]:
    run = database.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


def _resolve_request(body: RunRequest, settings: Settings) -> TestProfile:
    if body.profile_name and body.profile:
        raise ProfileError("send profile_name or profile, not both")
    if body.profile_name:
        path = resolve_profile_name(body.profile_name, settings)
        return load_profile_file(path, settings)
    if body.profile:
        try:
            return profile_from_mapping(body.profile, settings)
        except ValidationError as exc:
            raise ProfileError(str(exc)) from exc
    raise ProfileError("profile_name or profile is required")


app = create_app()
