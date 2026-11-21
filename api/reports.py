from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from database.repository import ReportRepository
from reporting.report_generator import generate_html, generate_json


def user_id(request: Request) -> str | None:
    value = request.headers.get("x-user-id")
    return value.strip() if value and value.strip() else None


def add_report_routes(app, repository: ReportRepository) -> None:
    @app.get("/api/runs")
    async def list_runs(request: Request, limit: int = 100):
        if limit < 1 or limit > 1000:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
        runs = repository.list_runs(user_id=request.headers.get("x-user-id"), limit=limit)
        return {"runs": [run.model_dump(mode="json") for run in runs]}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str, request: Request):
        run = repository.get_run(run_id, user_id(request))
        if run is None:
            raise HTTPException(status_code=404, detail="Test run not found")
        return run.model_dump(mode="json")

    @app.get("/api/runs/{run_id}/steps")
    async def get_steps(run_id: str, request: Request):
        run = repository.get_run(run_id, user_id(request))
        if run is None:
            raise HTTPException(status_code=404, detail="Test run not found")
        return {"steps": [step.model_dump(mode="json") for step in run.steps]}

    @app.get("/api/runs/{run_id}/artifacts")
    async def get_artifacts(run_id: str, request: Request):
        run = repository.get_run(run_id, user_id(request))
        if run is None:
            raise HTTPException(status_code=404, detail="Test run not found")
        return {"artifacts": [artifact.model_dump(mode="json") for artifact in run.artifacts]}

    @app.get("/api/runs/{run_id}/report.html")
    async def download_html(run_id: str, request: Request):
        run = repository.get_run(run_id, user_id(request))
        if run is None:
            raise HTTPException(status_code=404, detail="Test run not found")
        return HTMLResponse(generate_html(run), headers={
            "Content-Disposition": f'attachment; filename="browserpilot-{run_id}.html"'
        })

    @app.get("/api/runs/{run_id}/report.json")
    async def download_json(run_id: str, request: Request):
        run = repository.get_run(run_id, user_id(request))
        if run is None:
            raise HTTPException(status_code=404, detail="Test run not found")
        return JSONResponse(
            json.loads(generate_json(run)),
            headers={"Content-Disposition": f'attachment; filename="browserpilot-{run_id}.json"'},
        )

    @app.get("/api/artifacts/{artifact_id}")
    async def download_artifact(artifact_id: str, request: Request):
        artifact = repository.get_artifact(artifact_id, user_id(request))
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        relative = Path(str(artifact["relative_path"]))
        base = Path.cwd().resolve()
        if relative.is_absolute():
            raise HTTPException(status_code=400, detail="Invalid artifact path")
        path = (base / relative).resolve()
        root = (base / "artifacts").resolve()
        if root not in path.parents and path != root:
            raise HTTPException(status_code=400, detail="Invalid artifact path")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Artifact file not found")
        return FileResponse(
            str(path),
            media_type=artifact["mime_type"],
            filename=artifact["name"],
        )

    @app.delete("/api/runs/{run_id}")
    async def delete_run(run_id: str, request: Request, older_than_days: int = 0):
        run = repository.get_run(run_id, user_id(request))
        if run is None:
            raise HTTPException(status_code=404, detail="Test run not found")
        if older_than_days > 0:
            cutoff = datetime.now(run.started_at.tzinfo)
        else:
            cutoff = run.completed_at
        # Explicit run deletion is denied here unless a future auth policy explicitly authorizes it.
        raise HTTPException(status_code=403, detail="Authorized retention deletion is not exposed")
