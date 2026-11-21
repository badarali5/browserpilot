"""Bounded execution loop for the LLM-powered BrowserPilot agent."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from agent import BrowserTools
from llm_planner import LLMPlanner
from algorithms.testing_strategy import TestingStrategy


class AutonomousAgent:
    def __init__(
        self,
        planner: LLMPlanner,
        tools: BrowserTools,
        max_actions: int = 12,
        max_duration: float = 120.0,
        max_retries: int = 2,
        strategy: Optional[TestingStrategy] = None,
    ) -> None:
        self.planner = planner
        self.tools = tools
        self.max_actions = max_actions
        self.max_duration = max_duration
        self.max_retries = max_retries
        self.strategy = strategy

    async def run(self, goal: str) -> Dict[str, Any]:
        started = time.monotonic()
        history: list[Dict[str, Any]] = []
        try:
            objective = await self.planner.convert_goal(goal)
        except Exception as exc:
            return self._report(goal, "planning_error", history, str(exc), started)

        objective_text = objective["objective"]
        repeated: Dict[str, int] = {}
        retries = 0
        independent_verification_passed = False

        for action_number in range(1, self.max_actions + 1):
            if time.monotonic() - started >= self.max_duration:
                return self._report(goal, "duration_limit", history, "Maximum execution duration reached.", started)

            observation = await self.tools.observe_page()
            try:
                if self.strategy is not None:
                    action = await self.strategy.generate_next_action(
                        observation,
                        {"objective": objective_text},
                    )
                else:
                    action = await self.planner.plan_action(objective_text, observation, history)
            except Exception as exc:
                retries += 1
                history.append({"step": action_number, "planning_error": exc.__class__.__name__})
                if retries > self.max_retries:
                    return self._report(goal, "llm_error", history, str(exc), started)
                await asyncio.sleep(0.1)
                continue

            signature = self._signature(action)
            repeated[signature] = repeated.get(signature, 0) + 1
            if repeated[signature] >= 3:
                return self._report(goal, "repeated_action", history, "Stopped because the agent repeated the same action.", started)

            if action["objective_status"] == "achieved":
                if independent_verification_passed:
                    history.append({"step": action_number, "action": action, "verification": "Independent verifier passed."})
                    return self._report(goal, "achieved", history, "Objective achieved.", started)
                history.append({"step": action_number, "action": action, "verification": "Achievement rejected: independent verification required."})
                retries += 1
                if retries > self.max_retries:
                    return self._report(goal, "retry_limit", history, "Achievement was not independently verified.", started)
                continue
            if action["objective_status"] == "blocked":
                history.append({"step": action_number, "action": action, "verification": "Planner could not continue."})
                return self._report(goal, "blocked", history, action.get("reason", "Objective blocked."), started)

            result = await self.tools.execute(action)
            history.append({
                "step": action_number,
                "action": action,
                "result": result,
                "url": result.get("observation_after", {}).get("url"),
                "title": result.get("observation_after", {}).get("title"),
                "evidence": result.get("evidence", ""),
                "verification": result.get("verification"),
            })

            if action.get("tool") == "verify" and result.get("status") == "pass":
                verification = result.get("verification") or {}
                if verification.get("status") == "pass":
                    independent_verification_passed = True

            if result["status"] in {"fail", "timeout", "error"}:
                retries += 1
                if retries > self.max_retries:
                    return self._report(goal, "retry_limit", history, "Maximum bounded retries reached.", started)
                continue
            retries = 0

        return self._report(goal, "action_limit", history, "Maximum action count reached.", started)

    @staticmethod
    def _signature(action: Dict[str, Any]) -> str:
        return f"{action.get('tool')}:{repr(action.get('arguments', {}))}"

    @staticmethod
    def _report(
        goal: str,
        status: str,
        history: list[Dict[str, Any]],
        message: str,
        started: float,
    ) -> Dict[str, Any]:
        return {
            "goal": goal,
            "status": status,
            "message": message,
            "history": history,
            "execution_time": round(time.monotonic() - started, 3),
        }
