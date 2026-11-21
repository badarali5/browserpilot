from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    action: str
    url: str | None = None
    selector: str | None = None
    value: Any = None
    expected: Any = None
    condition: str | None = None
    timeout: int | None = None


class TestPlan(BaseModel):
    plan_id: str | None = None
    goal: str
    steps: List[PlanStep] = Field(default_factory=list)
    verified: bool = False
    bugs_detected: List[Any] = Field(default_factory=list)
