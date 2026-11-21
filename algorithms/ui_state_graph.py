"""Browser UI state graph primitives."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UIState:
    state_id: str
    observation: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UITransition:
    source: str
    action: Mapping[str, Any]
    target: str
    cost: float = 1.0


class UIStateGraph:
    """In-memory graph keyed by a stable observation-derived state ID."""

    def __init__(self) -> None:
        self.states: dict[str, UIState] = {}
        self.transitions: dict[str, list[UITransition]] = {}
        self.initial_states: list[str] = []
        self.visited: set[str] = set()

    @staticmethod
    def state_id(observation: Mapping[str, Any]) -> str:
        url = str(observation.get("url", ""))
        title = str(observation.get("title", ""))
        text = str(observation.get("visible_text", ""))[:5000]
        elements = []
        interactive = observation.get("interactive", {})
        if isinstance(interactive, Mapping):
            for element in interactive.get("elements", [])[:200]:
                if isinstance(element, Mapping):
                    elements.append({
                        "kind": element.get("kind"),
                        "name": element.get("name"),
                        "selector_hint": element.get("selector_hint"),
                        "enabled": element.get("enabled"),
                    })
        canonical = json.dumps(
            {"url": url, "title": title, "text": text, "elements": elements},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

    def add_state(self, observation: Mapping[str, Any], *, initial: bool = False) -> str:
        sid = self.state_id(observation)
        self.states[sid] = UIState(sid, observation)
        self.transitions.setdefault(sid, [])
        if initial and sid not in self.initial_states:
            self.initial_states.append(sid)
        return sid

    def add_transition(
        self,
        source: str,
        action: Mapping[str, Any],
        target: str,
        cost: float = 1.0,
    ) -> None:
        if source not in self.states or target not in self.states:
            raise KeyError("Both transition endpoints must be added to the graph.")
        if cost < 0:
            raise ValueError("Transition cost cannot be negative.")
        self.transitions.setdefault(source, []).append(
            UITransition(source, dict(action), target, float(cost))
        )

    def neighbors(self, state_id: str) -> Iterable[UITransition]:
        return tuple(self.transitions.get(state_id, []))


GoalPredicate = Callable[[UIState], bool]
