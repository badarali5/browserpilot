from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import app
from database.repository import ReportRepository
from reporting.report_generator import generate_html, generate_json


def test_repository_persists_run_steps_verifications_artifacts_and_redacts(tmp_path):
    repository = ReportRepository(tmp_path / "browserpilot.db")
    run_id = repository.create_run(
        goal="Verify login",
        target_url="http://127.0.0.1:8000",
        user_id="user-1",
        browser_config={"headless": True, "password": "do-not-store"},
    )
    repository.store_step(
        run_id,
        {
            "step": 1,
            "action": "input",
            "status": "pass",
            "evidence": "Filled field",
            "verification": {
                "condition": "input_value_equals",
                "expected": "safe",
                "actual": "safe",
                "status": "pass",
            },
        },
        action_arguments={"selector": "#password", "value": "Password123", "token": "secret"},
    )
    screenshot = tmp_path / "step-1.png"
    screenshot.write_bytes(b"png")
    repository.store_artifact(
        run_id,
        relative_path=str(screenshot),
        artifact_type="screenshot",
        step_number=1,
        mime_type="image/png",
    )
    repository.update_run(
        run_id,
        status="passed",
        summary={"total_steps": 1, "passed": 1},
    )

    run = repository.get_run(run_id)
    assert run is not None
    assert run.status == "passed"
    assert len(run.steps) == 1
    assert run.steps[0].verification.status == "pass"
    assert run.steps[0].action_arguments["value"] == "[redacted]"
    assert run.browser_config["password"] == "[redacted]"
    assert len(run.artifacts) == 1

    restarted = ReportRepository(tmp_path / "browserpilot.db")
    assert restarted.get_run(run_id).goal == "Verify login"


def test_repository_isolates_users_and_generates_persisted_reports(tmp_path):
    repository = ReportRepository(tmp_path / "browserpilot.db")
    run_id = repository.create_run(
        goal="Test profile",
        target_url="http://127.0.0.1:8000",
        user_id="owner",
    )
    repository.update_run(run_id, status="failed", summary={"failed": 1})

    assert repository.get_run(run_id, "owner") is not None
    assert repository.get_run(run_id, "other") is None

    run = repository.get_run(run_id)
    html = generate_html(run)
    json_report = generate_json(run)
    assert "Test profile" in html
    assert '"goal": "Test profile"' in json_report


def test_retention_removes_only_expired_runs(tmp_path):
    repository = ReportRepository(tmp_path / "browserpilot.db")
    old_id = repository.create_run(
        goal="Old run",
        target_url="http://127.0.0.1:8000",
        started_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    repository.update_run(old_id, status="passed")
    current_id = repository.create_run(
        goal="Current run",
        target_url="http://127.0.0.1:8000",
    )

    removed = repository.delete_expired(
        older_than=datetime.now(timezone.utc) - timedelta(days=30)
    )
    assert removed == 1
    assert repository.get_run(old_id) is None
    assert repository.get_run(current_id) is not None


def test_api_rejects_cross_user_run_access(tmp_path, monkeypatch):
    repository = ReportRepository(tmp_path / "browserpilot.db")
    run_id = repository.create_run(
        goal="Private",
        target_url="http://127.0.0.1:8000",
        user_id="owner",
    )

    from api import reports
    from fastapi import FastAPI

    isolated_app = FastAPI()
    reports.add_report_routes(isolated_app, repository)
    client = TestClient(isolated_app)
    assert client.get(f"/api/runs/{run_id}", headers={"x-user-id": "owner"}).status_code == 200
    assert client.get(f"/api/runs/{run_id}", headers={"x-user-id": "other"}).status_code == 404
    assert client.get("/api/artifacts/not-a-real-id", headers={"x-user-id": "owner"}).status_code == 404
