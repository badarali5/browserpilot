from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(term in lowered for term in ("password", "passwd", "token", "secret", "cookie", "authorization", "value")):
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


class VerificationModel(BaseModel):
    condition: str = ""
    expected: Any = None
    actual: Any = None
    status: str = "unknown"
    failure_type: Optional[str] = None
    error: str = ""
    details: str = ""


class ArtifactModel(BaseModel):
    artifact_id: str
    run_id: str
    step_number: Optional[int] = None
    artifact_type: str
    name: str
    relative_path: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    created_at: datetime
    collection_error: Optional[str] = None


class StepModel(BaseModel):
    step_number: int
    action: str
    action_arguments: Dict[str, Any] = Field(default_factory=dict)
    status: str
    started_at: datetime
    completed_at: datetime
    observation: Dict[str, Any] = Field(default_factory=dict)
    verification: Optional[VerificationModel] = None
    error_classification: str = "uncertain"
    error: str = ""


class DefectModel(BaseModel):
    defect_id: str
    run_id: str
    step_number: Optional[int] = None
    classification: str = "uncertain"
    observed_evidence: str = ""
    inferred_cause: str = ""
    confidence: str = "uncertain"


class TestRunModel(BaseModel):
    run_id: str
    user_id: Optional[str] = None
    goal: str
    target_url: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    status: str
    browser_config: Dict[str, Any] = Field(default_factory=dict)
    planner_config: Dict[str, Any] = Field(default_factory=dict)
    algorithm_config: Dict[str, Any] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)
    evidence_collection_errors: List[str] = Field(default_factory=list)
    steps: List[StepModel] = Field(default_factory=list)
    verification_results: List[VerificationModel] = Field(default_factory=list)
    defects: List[DefectModel] = Field(default_factory=list)
    artifacts: List[ArtifactModel] = Field(default_factory=list)
