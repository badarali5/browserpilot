

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import sys
import os
from pathlib import Path

app = FastAPI(
    title="BrowserPilot",
    description="AI Browser Automation & Quality Assurance Platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

templates.env.filters["datetimeformat"] = lambda value: (
    value.strftime("%Y-%m-%d %H:%M") if hasattr(value, "strftime")
    else str(value).replace("T", " ")[:16]
)

# Small in-memory account store for the built-in demo application.
users_db: dict[str, dict] = {}


def is_valid_email(email: str) -> bool:
    return "@" in email and "." in email.rsplit("@", 1)[-1]

# Import planner generation/validation and the real Playwright executor
from planner.planner import generate_plan_with_error, validate_plan
from browser.browser_engine import execute_plan as execute_browser_plan, validate_target_url
from browser.actions import BrowserTools
from browser.session import AutonomousAgent
from planner.llm_planner import LLMPlanner
from benchmarks.benchmark_m4 import benchmark
from algorithms.failure_ml import kmeans_cluster, load_persisted_failures

from database.repository import ReportRepository
from reporting.evidence import EvidenceCollector
from config import BASE_DIR as CONFIG_BASE_DIR, DATABASE_PATH

BASE_DIR = CONFIG_BASE_DIR
REPORT_REPOSITORY = ReportRepository(DATABASE_PATH)


def persist_execution_report(
    *,
    goal: str,
    target_url: str,
    report: dict,
    plan: dict | None = None,
    browser_config: dict | None = None,
    planner_config: dict | None = None,
    algorithm_config: dict | None = None,
    artifact_dir: str | Path = "artifacts",
    user_id: str | None = None,
) -> str:
    """Persist a real executor report and its evidence without changing its public shape."""
    from datetime import datetime, timezone

    summary = report.get("summary") or {}
    started = datetime.now(timezone.utc)
    status = "running"
    if summary:
        status = "passed" if summary.get("failed", 0) == 0 and summary.get("errors", 0) == 0 and summary.get("timeouts", 0) == 0 else "failed"
    else:
        status = str(report.get("status", "unknown"))

    run_id = REPORT_REPOSITORY.create_run(
        goal=goal,
        target_url=target_url,
        status=status,
        user_id=user_id,
        browser_config=browser_config or {"headless": True},
        planner_config=planner_config or {"source": "existing planner"},
        algorithm_config=algorithm_config or {"name": "browser execution"},
    )
    collector = EvidenceCollector(REPORT_REPOSITORY, run_id, artifact_dir)

    plan_steps = (plan or {}).get("steps", []) if plan else []
    for index, step_result in enumerate(report.get("steps", []), 1):
        arguments = plan_steps[index - 1] if index - 1 < len(plan_steps) else {}
        step_number = REPORT_REPOSITORY.store_step(
            run_id,
            step_result,
            step_number=step_result.get("step", index),
            action_arguments=arguments,
        )
        if step_result.get("status") in {"fail", "timeout", "error"}:
            REPORT_REPOSITORY.store_defect(
                run_id,
                step_number=step_number,
                classification=REPORT_REPOSITORY.get_run(run_id).steps[index - 1].error_classification,
                observed_evidence=step_result.get("evidence") or step_result.get("error") or "",
                inferred_cause="",
                confidence="uncertain",
            )

    screenshots = report.get("screenshots", [])
    collector.collect_screenshots(screenshots)
    trace_path = report.get("trace_path")
    if trace_path:
        collector.collect_artifact(trace_path, "trace", mime_type="application/zip")
    evidence_payload = {
        "console_errors": report.get("console_errors", []),
        "failed_network_requests": report.get("failed_network_requests", []),
        "http_responses": report.get("http_responses", []),
        "current_url": report.get("current_url"),
    }
    import json as _json
    evidence_path = Path(artifact_dir) / f"evidence_{run_id}.json"
    evidence_path.write_text(_json.dumps(evidence_payload, indent=2), encoding="utf-8")
    collector.collect_artifact(evidence_path, "browser_evidence", mime_type="application/json")
    evidence_errors = list(dict.fromkeys([*report.get("evidence_errors", []), *collector.errors]))
    REPORT_REPOSITORY.update_run(
        run_id,
        status=status,
        summary=summary or report,
        evidence_errors=evidence_errors,
    )
    return run_id


from api.reports import add_report_routes
from api.history import add_history_routes

add_report_routes(app, REPORT_REPOSITORY)
add_history_routes(app, REPORT_REPOSITORY, templates)

# ══════════════════════════════════════
# API Routes
# ══════════════════════════════════════

@app.get("/api/health", include_in_schema=False)
async def api_health():
    """Health check API."""
    return JSONResponse({"status": "ok", "version": "1.0.0"})


@app.post("/api/run-test", include_in_schema=False)
async def run_test(request: Request):
    """Generate, validate, and execute a plan in a real browser."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)

    goal = str(payload.get("goal", "")).strip()
    if not goal:
        return JSONResponse({"error": "Provide a non-empty testing goal."}, status_code=400)

    target_url = str(payload.get("target_url") or os.getenv("BROWSERPILOT_TARGET_URL", "http://127.0.0.1:8000")).strip()
    try:
        target_url = validate_target_url(target_url)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    try:
        timeout = int(payload.get("timeout", 30))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Browser timeout must be an integer."}, status_code=400)
    if timeout <= 0 or timeout > 300:
        return JSONResponse({"error": "Browser timeout must be between 1 and 300 seconds."}, status_code=400)

    artifact_name = str(payload.get("artifact_dir", "artifacts")).strip().replace("\\", "/")
    base_dir = Path(__file__).resolve().parent
    artifact_root = (base_dir / "artifacts").resolve()
    requested_dir = (base_dir / artifact_name).resolve()
    if (
        not artifact_name
        or Path(artifact_name).is_absolute()
        or ".." in Path(artifact_name).parts
        or (requested_dir != artifact_root and artifact_root not in requested_dir.parents)
    ):
        return JSONResponse({"error": "artifact_dir must be a subdirectory of the artifacts directory."}, status_code=400)
    requested_dir.mkdir(parents=True, exist_ok=True)

    plan, planning_error = generate_plan_with_error(goal)
    if not plan:
        return JSONResponse({"error": planning_error}, status_code=400)

    is_valid, validation_error, bugs_detected = validate_plan(plan)
    if not is_valid:
        return JSONResponse({"error": f"Invalid plan: {validation_error}"}, status_code=400)
    plan["bugs_detected"] = bugs_detected

    try:
        report = await execute_browser_plan(
            plan,
            headless=True,
            timeout=timeout,
            target_url=target_url,
            screenshot_dir=str(requested_dir),
        )
    except Exception as exc:
        try:
            failed_run_id = persist_execution_report(
                goal=goal,
                target_url=target_url,
                report={"status": "failed", "steps": [], "summary": {"errors": 1}, "evidence_errors": [str(exc)]},
                plan=plan,
                browser_config={"headless": True, "timeout_seconds": timeout},
                artifact_dir=requested_dir,
                user_id=payload.get("user_id"),
            )
        except Exception:
            failed_run_id = None
        return JSONResponse(
            {"error": f"Browser execution could not start: {exc}", "plan": plan, "run_id": failed_run_id},
            status_code=502,
        )

    run_id = persist_execution_report(
        goal=goal,
        target_url=target_url,
        report=report,
        plan=plan,
        browser_config={"headless": True, "timeout_seconds": timeout},
        planner_config={"source": "existing planner", "algorithm": str(payload.get("algorithm") or "A*")},
        algorithm_config={
            "name": str(payload.get("algorithm") or "A*"),
            "bug_injection": str(payload.get("bug") or "") or None,
        },
        artifact_dir=requested_dir,
        user_id=payload.get("user_id"),
    )
    return JSONResponse({
        "plan": plan,
        "report": report,
        "run_id": run_id,
    })


@app.post("/api/run-agent-test", include_in_schema=False)
async def run_agent_test(request: Request):
    """Run an observation-driven, LLM-selected browser test."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)

    goal = str(payload.get("goal", "")).strip()
    if not goal:
        return JSONResponse({"error": "Provide a non-empty testing goal."}, status_code=400)

    target_url = str(payload.get("target_url") or os.getenv("BROWSERPILOT_TARGET_URL", "http://127.0.0.1:8000")).strip()
    try:
        target_url = validate_target_url(target_url)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    try:
        max_actions = int(payload.get("max_actions", 12))
        max_duration = float(payload.get("max_duration", 120))
        timeout = int(payload.get("timeout", 10))
    except (TypeError, ValueError):
        return JSONResponse({"error": "max_actions, max_duration, and timeout must be numeric."}, status_code=400)
    if max_actions <= 0 or max_actions > 50:
        return JSONResponse({"error": "max_actions must be between 1 and 50."}, status_code=400)
    if max_duration <= 0 or max_duration > 600:
        return JSONResponse({"error": "max_duration must be between 1 and 600 seconds."}, status_code=400)
    if timeout <= 0 or timeout > 300:
        return JSONResponse({"error": "timeout must be between 1 and 300 seconds."}, status_code=400)

    artifact_name = str(payload.get("artifact_dir", "artifacts")).strip().replace("\\", "/")
    base_dir = Path(__file__).resolve().parent
    artifact_root = (base_dir / "artifacts").resolve()
    requested_dir = (base_dir / artifact_name).resolve()
    if (
        not artifact_name
        or Path(artifact_name).is_absolute()
        or ".." in Path(artifact_name).parts
        or (requested_dir != artifact_root and artifact_root not in requested_dir.parents)
    ):
        return JSONResponse({"error": "artifact_dir must be a subdirectory of the artifacts directory."}, status_code=400)
    requested_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(base_url=target_url)
            page = await context.new_page()
            try:
                tools = BrowserTools(page, target_url, str(requested_dir))
                agent = AutonomousAgent(
                    LLMPlanner(timeout=timeout),
                    tools,
                    max_actions=max_actions,
                    max_duration=max_duration,
                )
                report = await agent.run(goal)
            finally:
                await context.close()
                await browser.close()
        normalized_steps = []
        for index, item in enumerate(report.get("history", []), 1):
            action = item.get("action") or {}
            result = item.get("result") or {}
            normalized_steps.append({
                "step": item.get("step", index),
                "action": action.get("tool", "unknown"),
                "status": result.get("status", "pass" if "action" not in item else "unknown"),
                "evidence": item.get("evidence") or result.get("evidence", ""),
                "error": result.get("error", ""),
                "observation_before": result.get("observation_before"),
                "observation_after": result.get("observation_after"),
                "verification": item.get("verification") if isinstance(item.get("verification"), dict) else result.get("verification"),
            })
        agent_status = "passed" if report.get("status") == "achieved" else "failed"
        normalized_report = {
            "status": agent_status,
            "steps": normalized_steps,
            "summary": {
                "total_steps": len(normalized_steps),
                "passed": sum(s["status"] == "pass" for s in normalized_steps),
                "failed": sum(s["status"] == "fail" for s in normalized_steps),
                "errors": sum(s["status"] == "error" for s in normalized_steps),
                "timeouts": sum(s["status"] == "timeout" for s in normalized_steps),
            },
        }
        run_id = persist_execution_report(
            goal=goal,
            target_url=target_url,
            report=normalized_report,
            browser_config={"headless": True, "timeout_seconds": timeout},
            planner_config={"type": "LLMPlanner", "max_actions": max_actions, "max_duration": max_duration},
            algorithm_config={"name": "autonomous-agent"},
            artifact_dir=requested_dir,
            user_id=payload.get("user_id"),
        )
        return JSONResponse({**report, "run_id": run_id})
    except Exception as exc:
        return JSONResponse(
            {"error": f"Autonomous browser execution could not start: {exc}"},
            status_code=502,
        )


@app.get("/api/m4/benchmark", include_in_schema=False)
async def milestone4_benchmark():
    """Expose the reproducible synthetic BFS/A*/GA benchmark."""
    return JSONResponse(benchmark(seed=1729))


@app.get("/api/m4/failures/analysis", include_in_schema=False)
async def milestone4_failure_analysis():
    """Analyze only failure records persisted in the Milestone 5 database."""
    base_dir = Path(__file__).resolve().parent
    database = base_dir / "data" / "browserpilot.db"
    records = load_persisted_failures(database)
    clustering = kmeans_cluster(records, k=min(3, len(records) or 1), seed=1729)
    return JSONResponse({
        "database": str(database),
        "persisted_record_count": len(records),
        "clustering": {
            "seed": clustering["seed"],
            "k": clustering["k"],
            "clusters": clustering["clusters"],
            "assignments": clustering["assignments"],
        },
        "classification": "No supervised evaluation: no persisted labeled failure records.",
    })


# ══════════════════════════════════════
# Core Routes
# ══════════════════════════════════════

@app.get("/", include_in_schema=False)
async def landing(request: Request):
    """Landing page with professional design."""
    return templates.TemplateResponse(request=request, name="landing.html", context={"title": "BrowserPilot", "version": "1.0.0"})


@app.get("/app", include_in_schema=False)
async def app_shell(request: Request):
    """Application shell page."""
    return templates.TemplateResponse(request=request, name="app_shell.html", context={"title": "BrowserPilot - App", "version": "1.0.0"})


@app.get("/app/run", include_in_schema=False)
async def live_run(request: Request, goal: str = ""):
    return templates.TemplateResponse(request=request, name="live_run.html", context={"title": "Live Run", "goal_preset": goal})


@app.get("/app/runs", include_in_schema=False)
async def runs_page(request: Request):
    runs = REPORT_REPOSITORY.list_runs(request.headers.get("x-user-id"), limit=100)
    passed = sum(run.status in {"passed", "completed", "achieved"} for run in runs)
    bugs = sum(len(run.defects) for run in runs)
    avg = sum(run.duration_seconds for run in runs) / len(runs) if runs else 0.0
    recent = [
        {
            "goal": run.goal,
            "algorithm": run.algorithm_config.get("name", "Browser execution"),
            "bug_injection": run.algorithm_config.get("bug_injection"),
            "status": run.status,
            "created_at": run.started_at,
        }
        for run in runs[:20]
    ]
    return templates.TemplateResponse(
        request=request,
        name="overview.html",
        context={
            "title": "Run History",
            "total_runs": len(runs),
            "pass_rate": round(passed / len(runs) * 100, 1) if runs else 0.0,
            "bugs_found": bugs,
            "avg_duration": f"{avg:.2f} s",
            "recent_runs": recent,
        },
    )


@app.post("/api/run", include_in_schema=False)
async def run_alias(request: Request):
    response = await run_test(request)
    if request.headers.get("hx-request") != "true":
        return response
    try:
        import json
        import html
        payload = json.loads(response.body)
        if response.status_code >= 400:
            message = html.escape(str(payload.get("error") or "The run could not start."))
            return HTMLResponse(
                f'<div class="p-4 text-danger" role="alert">{message}</div>',
                status_code=response.status_code,
            )
        report = payload.get("report") or {}
        summary = report.get("summary") or {}
        return HTMLResponse(
            f'<div class="p-4">'
            f'<strong class="text-success">{summary.get("passed", 0)}/{summary.get("total_steps", 0)} steps passed</strong>'
            f'<p class="mt-2 text-sm text-fg-secondary">Run ID: {payload.get("run_id") or "none"}</p>'
            f'</div>',
            status_code=response.status_code,
        )
    except Exception:
        return response


@app.get("/about", include_in_schema=False)
async def about(request: Request):
    """About page."""
    return templates.TemplateResponse(request=request, name="about.html", context={"title": "About BrowserPilot", "version": "1.0.0"})


@app.get("/features", include_in_schema=False)
async def features(request: Request):
    """Features page."""
    return templates.TemplateResponse(request=request, name="features.html", context={"title": "Features", "version": "1.0.0"})


@app.get("/contact", include_in_schema=False)
async def contact(request: Request):
    """Contact page."""
    return templates.TemplateResponse(request=request, name="contact.html", context={"title": "Contact", "version": "1.0.0"})


# ══════════════════════════════════════
# Demo Routes (merged from demo_website.py)
# ══════════════════════════════════════

@app.get("/demo", include_in_schema=False)
async def demo_root(request: Request):
    """Demo website root."""
    return templates.TemplateResponse(request=request, name="demo_index.html", context={"title": "BrowserPilot Demo"})


@app.get("/demo/register", include_in_schema=False)
async def demo_register_get(request: Request):
    """Registration page."""
    return templates.TemplateResponse(request=request, name="demo_register.html", context={"title": "Register", "error": None})


@app.post("/demo/register", include_in_schema=False)
async def demo_register_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    """Handle registration."""
    error = None
    if not username.strip():
        error = "Username is required"
    elif not is_valid_email(email):
        error = "Please enter a valid email"
    elif len(password) < 6:
        error = "Password must be at least 6 characters"
    elif username in users_db:
        error = "Username already taken"

    if error:
        return templates.TemplateResponse(
            request=request,
            name="demo_register.html",
            context={"title": "Register", "error": error},
        )

    users_db[username] = {
        "email": email,
        "password": password,
        "profile": {"display_name": username, "bio": ""},
    }
    return RedirectResponse(url="/demo/login", status_code=302)


@app.get("/demo/login", include_in_schema=False)
async def demo_login_get(request: Request):
    """Login page."""
    return templates.TemplateResponse(request=request, name="demo_login.html", context={"title": "Login", "error": None})


@app.post("/demo/login", include_in_schema=False)
async def demo_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Handle login."""
    user = users_db.get(username)
    if not user or user["password"] != password:
        return templates.TemplateResponse(
            request=request,
            name="demo_login.html",
            context={"title": "Login", "error": "Invalid username or password"},
        )
    response = RedirectResponse(url="/demo/profile", status_code=302)
    response.set_cookie("demo_user", username, httponly=True, samesite="lax")
    return response


@app.get("/demo/profile", include_in_schema=False)
async def demo_profile_get(request: Request):
    """Profile page."""
    username = request.cookies.get("demo_user", "")
    user = users_db.get(username)
    return templates.TemplateResponse(
        request=request,
        name="demo_profile.html",
        context={"title": "Profile", "user": user["profile"] if user else {}},
    )


@app.get("/demo/logout", include_in_schema=False)
async def demo_logout(request: Request):
    """Logout."""
    response = RedirectResponse(url="/demo", status_code=302)
    response.delete_cookie("demo_user")
    return response


# Short demo aliases keep the existing demo usable at the natural test URLs.
@app.get("/register", include_in_schema=False)
async def register_alias(request: Request):
    return templates.TemplateResponse(request=request, name="demo_register.html", context={"title": "Register", "error": None})


@app.post("/register", include_in_schema=False)
async def register_alias_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    return await demo_register_post(request, username, email, password)


@app.get("/login", include_in_schema=False)
async def login_alias(request: Request):
    return templates.TemplateResponse(request=request, name="demo_login.html", context={"title": "Login", "error": None})


@app.post("/login", include_in_schema=False)
async def login_alias_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    return await demo_login_post(request, username, password)


@app.get("/profile", include_in_schema=False)
async def profile_alias(request: Request):
    username = request.cookies.get("demo_user", "")
    user = users_db.get(username)
    return templates.TemplateResponse(
        request=request,
        name="demo_profile.html",
        context={"title": "Profile", "user": user["profile"] if user else {}},
    )


@app.post("/profile", include_in_schema=False)
async def profile_alias_post(
    request: Request,
    display_name: str = Form(...),
    bio: str = Form(...),
):
    username = request.cookies.get("demo_user", "")
    user = users_db.get(username)
    if user:
        user["profile"] = {"display_name": display_name, "bio": bio}
    return templates.TemplateResponse(
        request=request,
        name="demo_profile.html",
        context={"title": "Profile", "user": user["profile"] if user else {}},
    )


@app.post("/demo/profile", include_in_schema=False)
async def demo_profile_post(
    request: Request,
    display_name: str = Form(...),
    bio: str = Form(...),
):
    return await profile_alias_post(request, display_name, bio)


@app.get("/logout", include_in_schema=False)
async def logout_alias(request: Request):
    response = RedirectResponse(url="/demo", status_code=302)
    response.delete_cookie("demo_user")
    return response


# ══════════════════════════════════════
# Startup
# ══════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    # Ensure data directory exists
    db_path = BASE_DIR / "data" / "browserpilot.db"
    REPORT_REPOSITORY.__init__(db_path)

    print(f"\nStarting BrowserPilot...")
    print("=" * 50)
    print("Opening browser in a moment...")
    print("=" * 50)
    print(f"\n  BrowserPilot v1.0.0")
    print(f"  AI Browser Automation & QA Platform")
    print("=" * 50)
    print(f"  Open at: http://127.0.0.1:8000")
    print(f"  Docs:    http://127.0.0.1:8000/api/docs\n")


# ══════════════════════════════════════
# Main
# ══════════════════════════════════════

if __name__ == "__main__":
    print("\nStarting BrowserPilot...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")