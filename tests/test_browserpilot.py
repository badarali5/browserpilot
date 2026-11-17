from fastapi.testclient import TestClient

from app import app
from planner import generate_plan, validate_plan


client = TestClient(app)


def test_health_and_landing_pages_load():
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.get("/")
    assert response.status_code == 200
    assert "BrowserPilot" in response.text


def test_run_test_rejects_empty_goal():
    response = client.post("/api/run-test", data={"goal": ""})
    assert response.status_code == 400
    assert "error" in response.json()


def test_run_test_returns_plan_and_report():
    response = client.post(
        "/api/run-test",
        data={"goal": "navigate to /login and verify Login is present"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["steps"][0] == {"action": "navigate", "url": "/login"}
    assert payload["report"]["summary"]["total_steps"] >= 1


def test_generated_plan_is_valid():
    plan = generate_plan("Test user can register with valid email")
    assert plan is not None
    assert validate_plan(plan)[0] is True
    assert all(step["action"] in {"click", "input", "navigate", "assert", "screenshot"} for step in plan["steps"])
