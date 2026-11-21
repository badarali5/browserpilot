

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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

# Import planner generation/validation and the real Playwright executor
from planner import generate_plan_with_error, validate_plan
from browser_engine import execute_plan as execute_browser_plan, validate_target_url

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
        return JSONResponse(
            {"error": f"Browser execution could not start: {exc}", "plan": plan},
            status_code=502,
        )

    return JSONResponse({
        "plan": plan,
        "report": report,
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
async def demo_register_post(request: Request):
    """Handle registration."""
    return templates.TemplateResponse(request=request, name="demo_register.html", context={"title": "Register", "error": None})


@app.get("/demo/login", include_in_schema=False)
async def demo_login_get(request: Request):
    """Login page."""
    return templates.TemplateResponse(request=request, name="demo_login.html", context={"title": "Login", "error": None})


@app.post("/demo/login", include_in_schema=False)
async def demo_login_post(request: Request):
    """Handle login."""
    return templates.TemplateResponse(request=request, name="demo_login.html", context={"title": "Login", "error": None})


@app.get("/demo/profile", include_in_schema=False)
async def demo_profile_get(request: Request):
    """Profile page."""
    return templates.TemplateResponse(request=request, name="demo_profile.html", context={"title": "Profile", "user": {}})


@app.get("/demo/logout", include_in_schema=False)
async def demo_logout(request: Request):
    """Logout."""
    return templates.TemplateResponse(request=request, name="demo_index.html", context={"title": "BrowserPilot Demo"})


# Short demo aliases keep the existing demo usable at the natural test URLs.
@app.get("/register", include_in_schema=False)
async def register_alias(request: Request):
    return templates.TemplateResponse(request=request, name="demo_register.html", context={"title": "Register", "error": None})


@app.post("/register", include_in_schema=False)
async def register_alias_post(request: Request):
    return templates.TemplateResponse(request=request, name="demo_register.html", context={"title": "Register", "error": None})


@app.get("/login", include_in_schema=False)
async def login_alias(request: Request):
    return templates.TemplateResponse(request=request, name="demo_login.html", context={"title": "Login", "error": None})


@app.post("/login", include_in_schema=False)
async def login_alias_post(request: Request):
    return templates.TemplateResponse(request=request, name="demo_login.html", context={"title": "Login", "error": None})


@app.get("/profile", include_in_schema=False)
async def profile_alias(request: Request):
    return templates.TemplateResponse(request=request, name="demo_profile.html", context={"title": "Profile", "user": {}})


# ══════════════════════════════════════
# Startup
# ══════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    # Ensure data directory exists
    Path("data").mkdir(parents=True, exist_ok=True)

    # Initialize database if needed
    db_path = Path("data/browserpilot.db")
    if not db_path.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_text("{}")

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