from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from database.repository import ReportRepository


def add_history_routes(app, repository: ReportRepository, templates) -> None:
    @app.get("/api/dashboard-stats")
    async def dashboard_stats(request: Request):
        runs = repository.list_runs(request.headers.get("x-user-id"), limit=100)
        passed = sum(run.status in {"passed", "completed", "achieved"} for run in runs)
        failed = sum(run.status not in {"passed", "completed", "achieved", "running"} for run in runs)
        bugs = sum(len(run.defects) for run in runs)
        durations = [run.duration_seconds for run in runs]
        return {
            "total_runs": len(runs),
            "pass_rate": round(passed / len(runs) * 100, 1) if runs else 0.0,
            "failed_runs": failed,
            "bugs_found": bugs,
            "avg_duration": round(sum(durations) / len(durations), 3) if durations else 0.0,
        }

    @app.get("/api/run-history")
    async def run_history(request: Request):
        runs = repository.list_runs(request.headers.get("x-user-id"), limit=100)
        return {"runs": [run.model_dump(mode="json") for run in runs]}

    @app.get("/app/overview")
    async def overview(request: Request):
        runs = repository.list_runs(request.headers.get("x-user-id"), limit=100)
        passed = sum(run.status in {"passed", "completed", "achieved"} for run in runs)
        bugs = sum(len(run.defects) for run in runs)
        avg = sum(run.duration_seconds for run in runs) / len(runs) if runs else 0.0
        recent = [
            {
                "goal": run.goal,
                "algorithm": run.algorithm_config.get("name", "Browser execution"),
                "bug_injection": None,
                "status": run.status,
                "created_at": run.started_at,
            }
            for run in runs[:20]
        ]
        return templates.TemplateResponse(
            request=request,
            name="overview.html",
            context={
                "title": "Mission Control",
                "total_runs": len(runs),
                "pass_rate": round(passed / len(runs) * 100, 1) if runs else 0.0,
                "bugs_found": bugs,
                "avg_duration": f"{avg:.2f} s",
                "recent_runs": recent,
            },
        )
