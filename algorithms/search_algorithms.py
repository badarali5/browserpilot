"""BFS and A* strategies for BrowserPilot UI state graphs."""

from __future__ import annotations

import heapq
import time
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any

from .ui_state_graph import GoalPredicate, UIStateGraph


def _goal(goal: str | GoalPredicate | Mapping[str, Any]):
    if callable(goal):
        return goal
    needle = str(goal).lower()
    if isinstance(goal, Mapping):
        needle = str(goal.get("goal", goal.get("objective", ""))).lower()

    def predicate(state):
        text = str(state.observation.get("visible_text", "")).lower()
        title = str(state.observation.get("title", "")).lower()
        url = str(state.observation.get("url", "")).lower()
        return needle and (needle in text or needle in title or needle in url)

    return predicate


def bfs(
    graph: UIStateGraph,
    goal: str | GoalPredicate,
    initial: str | None = None,
) -> dict[str, Any]:
    """Minimum-transition-count search. BFS is unweighted despite stored edge costs."""
    started = time.perf_counter()
    start = initial or (graph.initial_states[0] if graph.initial_states else None)
    if start is None:
        return {"path": [], "actions": [], "nodes_explored": 0, "path_length": 0,
                "total_cost": 0.0, "runtime_seconds": 0.0, "goal_reachable": False}

    predicate = _goal(goal)
    queue = deque([start])
    parent: dict[str, str | None] = {start: None}
    via_action: dict[str, Mapping[str, Any]] = {}
    explored = 0
    found: str | None = None

    while queue:
        sid = queue.popleft()
        explored += 1
        graph.visited.add(sid)
        if predicate(graph.states[sid]):
            found = sid
            break
        for transition in graph.neighbors(sid):
            if transition.target not in parent:
                parent[transition.target] = sid
                via_action[transition.target] = transition.action
                queue.append(transition.target)

    if found is None:
        return {"path": [], "actions": [], "nodes_explored": explored, "path_length": 0,
                "total_cost": 0.0, "runtime_seconds": time.perf_counter() - started,
                "goal_reachable": False}

    path = []
    actions = []
    sid = found
    while sid is not None:
        path.append(sid)
        sid = parent[sid]
    path.reverse()
    for index in range(1, len(path)):
        source, target = path[index - 1], path[index]
        actions.append(via_action[target])

    total_cost = sum(
        next(t.cost for t in graph.neighbors(path[i]) if t.target == path[i + 1])
        for i in range(len(path) - 1)
    )
    return {"path": path, "actions": actions, "nodes_explored": explored,
            "path_length": len(path) - 1, "total_cost": total_cost,
            "runtime_seconds": time.perf_counter() - started, "goal_reachable": True}


def astar(
    graph: UIStateGraph,
    goal: str | GoalPredicate,
    heuristic: Callable[[Any], float] | None = None,
    initial: str | None = None,
) -> dict[str, Any]:
    """Lowest-cost search; set an admissible heuristic for guaranteed optimality."""
    started = time.perf_counter()
    start = initial or (graph.initial_states[0] if graph.initial_states else None)
    if start is None:
        return {"path": [], "actions": [], "nodes_explored": 0, "path_length": 0,
                "total_cost": 0.0, "runtime_seconds": 0.0, "goal_reachable": False}

    predicate = _goal(goal)
    heuristic = heuristic or (lambda state: 0.0)
    counter = 0
    queue = [(heuristic(graph.states[start]), 0.0, counter, start)]
    best_cost: dict[str, float] = {start: 0.0}
    parent: dict[str, str | None] = {start: None}
    via_action: dict[str, Mapping[str, Any]] = {}
    explored = 0
    found: str | None = None

    while queue:
        _, cost, _, sid = heapq.heappop(queue)
        if cost != best_cost.get(sid):
            continue
        explored += 1
        graph.visited.add(sid)
        if predicate(graph.states[sid]):
            found = sid
            break
        for transition in graph.neighbors(sid):
            new_cost = cost + transition.cost
            if new_cost < best_cost.get(transition.target, float("inf")):
                best_cost[transition.target] = new_cost
                parent[transition.target] = sid
                via_action[transition.target] = transition.action
                counter += 1
                estimate = heuristic(graph.states[transition.target])
                heapq.heappush(queue, (new_cost + estimate, new_cost, counter, transition.target))

    if found is None:
        return {"path": [], "actions": [], "nodes_explored": explored, "path_length": 0,
                "total_cost": 0.0, "runtime_seconds": time.perf_counter() - started,
                "goal_reachable": False}

    path = []
    sid = found
    while sid is not None:
        path.append(sid)
        sid = parent[sid]
    path.reverse()
    actions = [via_action[path[i]] for i in range(1, len(path))]
    return {"path": path, "actions": actions, "nodes_explored": explored,
            "path_length": len(path) - 1, "total_cost": best_cost[found],
            "runtime_seconds": time.perf_counter() - started, "goal_reachable": True}


class BFSSearchStrategy:
    """TestingStrategy adapter for controlled-action integration."""

    def __init__(self, graph: UIStateGraph, initial: str | None = None) -> None:
        self.graph = graph
        self.initial = initial

    async def generate_next_action(
        self,
        state: Mapping[str, Any],
        goal: Mapping[str, Any] | str,
    ) -> dict[str, Any]:
        sid = self.graph.add_state(state)
        result = bfs(self.graph, goal, initial=sid)
        action = result["actions"][0] if result["actions"] else {
            "tool": "observe_page",
            "arguments": {},
            "objective_status": "achieved" if result["goal_reachable"] else "blocked",
            "reason": "Goal reached or no reachable action found.",
        }
        action.setdefault("objective_status", "continue")
        action.setdefault("reason", "BFS selected the next shortest-transition action.")
        action.setdefault("metrics", result)
        return action


class AStarSearchStrategy:
    """TestingStrategy adapter using configurable admissible/documented heuristics."""

    def __init__(
        self,
        graph: UIStateGraph,
        heuristic: Callable[[Any], float] | None = None,
        initial: str | None = None,
    ) -> None:
        self.graph = graph
        self.heuristic = heuristic
        self.initial = initial

    async def generate_next_action(
        self,
        state: Mapping[str, Any],
        goal: Mapping[str, Any] | str,
    ) -> dict[str, Any]:
        sid = self.graph.add_state(state)
        result = astar(self.graph, goal, heuristic=self.heuristic, initial=sid)
        action = result["actions"][0] if result["actions"] else {
            "tool": "observe_page",
            "arguments": {},
            "objective_status": "achieved" if result["goal_reachable"] else "blocked",
            "reason": "Goal reached or no reachable action found.",
        }
        action.setdefault("objective_status", "continue")
        action.setdefault("reason", "A* selected the next lowest-cost action.")
        action.setdefault("metrics", result)
        return action
