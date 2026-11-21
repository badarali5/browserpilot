import os
import subprocess
import sys
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app import app
from planner import generate_plan, generate_plan_with_error, validate_plan


client = TestClient(app)


def test_health_and_landing_pages_load():
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.get("/")
    assert response.status_code == 200, response.text
    assert "BrowserPilot" in response.text


def test_run_test_rejects_empty_goal():
    response = client.post("/api/run-test", data={"goal": ""})
    assert response.status_code == 400
    assert "error" in response.json()


def test_run_test_rejects_internal_unlisted_target():
    response = client.post(
        "/api/run-test",
        data={"goal": "navigate to /login", "target_url": "http://10.0.0.1"},
    )
    assert response.status_code == 400
    assert "allowlist" in response.json()["error"]


def test_unknown_goal_is_rejected_without_fake_plan():
    plan, error = generate_plan_with_error("dance on the moon")
    assert plan is None
    assert "Unsupported instruction" in error
    assert generate_plan("dance on the moon") is None


def test_generated_input_and_click_steps_have_valid_selectors():
    plan = generate_plan("Test user can register with valid email")
    assert plan is not None
    assert validate_plan(plan)[0] is True
    assert all(step["action"] in {"click", "input", "navigate", "assert", "screenshot"} for step in plan["steps"])
    assert all(
        isinstance(step["selector"], str) and step["selector"].strip()
        for step in plan["steps"]
        if step["action"] in {"input", "click"}
    )


@pytest.fixture(scope="module")
def browser_server():
    port = 8765
    origin = f"http://127.0.0.1:{port}"
    previous_allowed = os.environ.get("BROWSERPILOT_ALLOWED_ORIGINS")
    os.environ["BROWSERPILOT_ALLOWED_ORIGINS"] = origin
    env = os.environ.copy()
    env["BROWSERPILOT_ALLOWED_ORIGINS"] = origin
    env["BROWSERPILOT_TARGET_URL"] = origin

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for _ in range(50):
        try:
            response = httpx.get(f"{origin}/api/health", timeout=0.5)
            if response.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        process.terminate()
        raise RuntimeError("Browser test server did not start")

    yield origin
    process.terminate()
    process.wait(timeout=10)
    if previous_allowed is None:
        os.environ.pop("BROWSERPILOT_ALLOWED_ORIGINS", None)
    else:
        os.environ["BROWSERPILOT_ALLOWED_ORIGINS"] = previous_allowed


@pytest.mark.integration
def test_real_browser_navigation_assertion_and_failed_assertion(browser_server):
    pytest.importorskip("playwright.async_api")

    response = client.post(
        "/api/run-test",
        data={
            "goal": "navigate to /login and verify Login is present",
            "target_url": browser_server,
            "timeout": "30",
        },
    )
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    assert report["summary"]["passed"] >= 1
    assert any(step["action"] == "navigate" and step["status"] == "pass" for step in report["steps"])
    assert any(step["action"] == "assert" and step["status"] == "pass" for step in report["steps"])

    failed = client.post(
        "/api/run-test",
        data={
            "goal": "navigate to /login and verify This text does not exist is present",
            "target_url": browser_server,
        },
    )
    assert failed.status_code == 200
    failed_report = failed.json()["report"]
    assert any(step["status"] == "fail" for step in failed_report["steps"])


@pytest.mark.integration
def test_real_browser_input_and_click(browser_server):
    pytest.importorskip("playwright.async_api")

    response = client.post(
        "/api/run-test",
        data={
            "goal": "navigate to /register and enter valid_user into the username field and enter valid@example.com into the email field and enter Password123 into the password field and click submit",
            "target_url": browser_server,
            "timeout": "30",
        },
    )
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    assert any(step["action"] == "input" and step["status"] == "pass" for step in report["steps"])
    assert any(step["action"] == "click" and step["status"] == "pass" for step in report["steps"])


def test_api_does_not_use_simulated_executor():
    with patch.dict(os.environ, {"BROWSERPILOT_ALLOWED_ORIGINS": "http://127.0.0.1:8000"}):
        with patch("app.execute_browser_plan", new_callable=AsyncMock) as browser_execute:
            browser_execute.return_value = {"steps": [], "summary": {"passed": 0}}
            response = client.post(
                "/api/run-test",
                data={"goal": "navigate to /login", "target_url": "http://127.0.0.1:8000"},
            )
    assert response.status_code == 200, response.text
    browser_execute.assert_awaited_once()
