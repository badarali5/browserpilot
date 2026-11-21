from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from database.connection import connect, initialize_database
from reporting.report_models import (
    ArtifactModel,
    DefectModel,
    StepModel,
    TestRunModel,
    VerificationModel,
    redact_sensitive,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReportRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        initialize_database(self.database)

    def create_run(
        self,
        *,
        goal: str,
        target_url: str,
        status: str = "running",
        user_id: Optional[str] = None,
        browser_config: Optional[dict[str, Any]] = None,
        planner_config: Optional[dict[str, Any]] = None,
        algorithm_config: Optional[dict[str, Any]] = None,
        run_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
    ) -> str:
        run_id = run_id or str(uuid.uuid4())
        started_at = started_at or utc_now()
        with connect(self.database) as connection:
            connection.execute(
                """
                INSERT INTO test_runs (
                    run_id, user_id, goal, target_url, started_at, completed_at,
                    duration_seconds, status, browser_config, planner_config,
                    algorithm_config, summary, evidence_errors
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, '{}', '[]')
                """,
                (
                    run_id, user_id, goal, target_url, started_at.isoformat(), started_at.isoformat(),
                    status,
                    json.dumps(redact_sensitive(browser_config or {})),
                    json.dumps(redact_sensitive(planner_config or {})),
                    json.dumps(redact_sensitive(algorithm_config or {})),
                ),
            )
            connection.commit()
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        completed_at: Optional[datetime] = None,
        summary: Optional[dict[str, Any]] = None,
        evidence_errors: Optional[list[str]] = None,
        browser_config: Optional[dict[str, Any]] = None,
        planner_config: Optional[dict[str, Any]] = None,
        algorithm_config: Optional[dict[str, Any]] = None,
    ) -> None:
        completed_at = completed_at or utc_now()
        with connect(self.database) as connection:
            row = connection.execute(
                "SELECT started_at FROM test_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            started = datetime.fromisoformat(row["started_at"])
            duration = max(0.0, (completed_at - started).total_seconds())
            existing = connection.execute(
                "SELECT browser_config, planner_config, algorithm_config FROM test_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            browser = browser_config if browser_config is not None else json.loads(existing["browser_config"])
            planner = planner_config if planner_config is not None else json.loads(existing["planner_config"])
            algorithm = algorithm_config if algorithm_config is not None else json.loads(existing["algorithm_config"])
            connection.execute(
                """
                UPDATE test_runs SET completed_at = ?, duration_seconds = ?, status = ?,
                    summary = ?, evidence_errors = ?, browser_config = ?, planner_config = ?, algorithm_config = ?
                WHERE run_id = ?
                """,
                (
                    completed_at.isoformat(), duration, status,
                    json.dumps(redact_sensitive(summary or {})),
                    json.dumps(redact_sensitive(evidence_errors or [])),
                    json.dumps(redact_sensitive(browser)),
                    json.dumps(redact_sensitive(planner)),
                    json.dumps(redact_sensitive(algorithm)),
                    run_id,
                ),
            )
            connection.commit()

    def store_step(
        self,
        run_id: str,
        step: dict[str, Any],
        *,
        step_number: Optional[int] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        action_arguments: Optional[dict[str, Any]] = None,
    ) -> int:
        number = int(step_number or step.get("step") or step.get("step_number") or 1)
        completed = completed_at or utc_now()
        started = started_at or completed
        verification_id = None
        verification = step.get("verification")
        if verification:
            verification_id = self.store_verification_result(
                run_id, number, verification
            )
        status = str(step.get("status", "unknown"))
        classification = classify_failure(status, step.get("error", ""), verification)
        with connect(self.database) as connection:
            connection.execute(
                """
                INSERT INTO test_steps (
                    run_id, step_number, action, action_arguments, status,
                    started_at, completed_at, observation, verification_id,
                    error_classification, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, step_number) DO UPDATE SET
                    action = excluded.action,
                    action_arguments = excluded.action_arguments,
                    status = excluded.status,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    observation = excluded.observation,
                    verification_id = excluded.verification_id,
                    error_classification = excluded.error_classification,
                    error = excluded.error
                """,
                (
                    run_id, number, str(step.get("action", step.get("tool", "unknown"))),
                    json.dumps(redact_sensitive(action_arguments or step.get("action", {}))),
                    status, started.isoformat(), completed.isoformat(),
                    json.dumps(redact_sensitive({
                        "before": step.get("observation_before"),
                        "after": step.get("observation_after"),
                        "actual": step.get("evidence", ""),
                    })),
                    verification_id, classification,
                    str(step.get("error", "")),
                ),
            )
            connection.commit()
        return number

    def store_verification_result(
        self,
        run_id: str,
        step_number: Optional[int],
        verification: dict[str, Any],
    ) -> str:
        verification_id = str(uuid.uuid4())
        with connect(self.database) as connection:
            connection.execute(
                """
                INSERT INTO verification_results (
                    verification_id, run_id, step_number, condition, expected, actual,
                    status, failure_type, error, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verification_id, run_id, step_number,
                    str(verification.get("condition", "")),
                    json.dumps(redact_sensitive(verification.get("expected"))),
                    json.dumps(redact_sensitive(verification.get("actual"))),
                    str(verification.get("status", "unknown")),
                    verification.get("failure_type"),
                    str(verification.get("error", "")),
                    str(verification.get("details", "")),
                ),
            )
            connection.commit()
        return verification_id

    def store_artifact(
        self,
        run_id: str,
        *,
        relative_path: str,
        artifact_type: str,
        name: Optional[str] = None,
        step_number: Optional[int] = None,
        mime_type: str = "application/octet-stream",
        collection_error: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> str:
        artifact_id = artifact_id or str(uuid.uuid4())
        path = Path(relative_path)
        size = path.stat().st_size if path.is_file() else 0
        with connect(self.database) as connection:
            connection.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, run_id, step_number, artifact_type, name,
                    relative_path, mime_type, size_bytes, created_at, collection_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id, run_id, step_number, artifact_type,
                    name or path.name, str(path).replace("\\", "/"),
                    mime_type, size, utc_now().isoformat(), collection_error,
                ),
            )
            connection.commit()
        return artifact_id

    def store_defect(
        self,
        run_id: str,
        *,
        step_number: Optional[int],
        classification: str,
        observed_evidence: str,
        inferred_cause: str = "",
        confidence: str = "uncertain",
    ) -> str:
        defect_id = str(uuid.uuid4())
        with connect(self.database) as connection:
            connection.execute(
                """
                INSERT INTO defects (
                    defect_id, run_id, step_number, classification,
                    observed_evidence, inferred_cause, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (defect_id, run_id, step_number, classification,
                 observed_evidence, inferred_cause, confidence),
            )
            connection.commit()
        return defect_id

    def get_run(self, run_id: str, user_id: Optional[str] = None) -> Optional[TestRunModel]:
        with connect(self.database) as connection:
            if user_id is None:
                row = connection.execute("SELECT * FROM test_runs WHERE run_id = ?", (run_id,)).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM test_runs WHERE run_id = ? AND user_id = ?", (run_id, user_id)
                ).fetchone()
            if row is None:
                return None
            run = dict(row)
            step_rows = connection.execute(
                "SELECT * FROM test_steps WHERE run_id = ? ORDER BY step_number",
                (run_id,),
            ).fetchall()
            verification_rows = connection.execute(
                "SELECT * FROM verification_results WHERE run_id = ? ORDER BY step_number",
                (run_id,),
            ).fetchall()
            defect_rows = connection.execute(
                "SELECT * FROM defects WHERE run_id = ? ORDER BY step_number",
                (run_id,),
            ).fetchall()
            artifact_rows = connection.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()

        started = datetime.fromisoformat(run["started_at"])
        completed = datetime.fromisoformat(run["completed_at"])
        verification_by_id = {
            str(row["verification_id"]): {
                "condition": row["condition"], "expected": safe_json(row["expected"]),
                "actual": safe_json(row["actual"]), "status": row["status"],
                "failure_type": row["failure_type"], "error": row["error"], "details": row["details"],
            }
            for row in verification_rows
        }
        steps = []
        for row in step_rows:
            verification = verification_by_id.get(row["verification_id"])
            steps.append(StepModel(
                step_number=row["step_number"], action=row["action"],
                action_arguments=safe_json(row["action_arguments"]),
                status=row["status"], started_at=datetime.fromisoformat(row["started_at"]),
                completed_at=datetime.fromisoformat(row["completed_at"]),
                observation=safe_json(row["observation"]),
                verification=VerificationModel(**verification) if verification else None,
                error_classification=row["error_classification"], error=row["error"],
            ))
        return TestRunModel(
            run_id=run["run_id"], user_id=run["user_id"], goal=run["goal"],
            target_url=run["target_url"], started_at=started, completed_at=completed,
            duration_seconds=run["duration_seconds"], status=run["status"],
            browser_config=safe_json(run["browser_config"]),
            planner_config=safe_json(run["planner_config"]),
            algorithm_config=safe_json(run["algorithm_config"]),
            summary=safe_json(run["summary"]),
            evidence_collection_errors=safe_json(run["evidence_errors"]),
            steps=steps,
            verification_results=[
                VerificationModel(
                    condition=row["condition"], expected=safe_json(row["expected"]),
                    actual=safe_json(row["actual"]), status=row["status"],
                    failure_type=row["failure_type"], error=row["error"], details=row["details"],
                ) for row in verification_rows
            ],
            defects=[
                DefectModel(
                    defect_id=row["defect_id"], run_id=row["run_id"],
                    step_number=row["step_number"], classification=row["classification"],
                    observed_evidence=row["observed_evidence"],
                    inferred_cause=row["inferred_cause"], confidence=row["confidence"],
                ) for row in defect_rows
            ],
            artifacts=[
                ArtifactModel(
                    artifact_id=row["artifact_id"], run_id=row["run_id"],
                    step_number=row["step_number"], artifact_type=row["artifact_type"],
                    name=row["name"], relative_path=row["relative_path"],
                    mime_type=row["mime_type"], size_bytes=row["size_bytes"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    collection_error=row["collection_error"],
                ) for row in artifact_rows
            ],
        )

    def list_runs(self, user_id: Optional[str] = None, limit: int = 100) -> list[TestRunModel]:
        with connect(self.database) as connection:
            if user_id is None:
                rows = connection.execute(
                    "SELECT run_id FROM test_runs ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT run_id FROM test_runs WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
        runs = [self.get_run(row["run_id"], user_id) for row in rows]
        return [run for run in runs if run is not None]

    def delete_expired(self, *, older_than: datetime, user_id: Optional[str] = None) -> int:
        with connect(self.database) as connection:
            if user_id is None:
                cursor = connection.execute(
                    "DELETE FROM test_runs WHERE started_at < ?", (older_than.isoformat(),)
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM test_runs WHERE started_at < ? AND user_id = ?",
                    (older_than.isoformat(), user_id),
                )
            connection.commit()
            return cursor.rowcount

    def get_artifact(self, artifact_id: str, user_id: Optional[str] = None):
        with connect(self.database) as connection:
            if user_id is None:
                row = connection.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT a.* FROM artifacts a
                    JOIN test_runs r ON r.run_id = a.run_id
                    WHERE a.artifact_id = ? AND r.user_id = ?
                    """,
                    (artifact_id, user_id),
                ).fetchone()
        return dict(row) if row else None


def safe_json(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def classify_failure(status: str, error: str, verification: Any) -> str:
    text = f"{error} {json.dumps(verification or {})}".lower()
    if status not in {"fail", "timeout", "error"}:
        return "none"
    if "timeout" in text or status == "timeout":
        return "timeout"
    if "password" in text or "authentication" in text or "login" in text:
        return "authentication_failure"
    if "network" in text or "connection" in text or "http" in text:
        return "network_failure"
    if "javascript" in text or "uncaught" in text:
        return "javascript_error"
    if "validation" in text or "invalid" in text:
        return "form_validation_failure"
    if "assert" in text or "verification" in text or "expected" in text:
        return "assertion_failure"
    if "selector" in text or "not found" in text:
        return "element_not_found"
    if "navigate" in text or "navigation" in text:
        return "navigation_failure"
    return "execution_error"
