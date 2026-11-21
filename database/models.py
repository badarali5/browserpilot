from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RunRecord:
    run_id: str
    user_id: Optional[str]
    goal: str
    target_url: str
    started_at: str
    completed_at: str
    duration_seconds: float
    status: str
    browser_config: dict[str, Any]
    planner_config: dict[str, Any]
    algorithm_config: dict[str, Any]
    summary: dict[str, Any]
    evidence_errors: list[str]
