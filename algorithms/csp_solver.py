"""Constraint satisfaction for valid and deliberately invalid test payloads."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any


Constraint = Callable[[Mapping[str, Any]], bool]


class CSPSolver:
    def __init__(
        self,
        variables: Sequence[str],
        domains: Mapping[str, Sequence[Any]],
        constraints: Sequence[Constraint],
    ) -> None:
        self.variables = list(variables)
        self.domains = {name: list(values) for name, values in domains.items()}
        self.constraints = list(constraints)
        missing = set(self.variables) - set(self.domains)
        if missing:
            raise ValueError(f"Missing domains: {sorted(missing)}")

    def solve(self, limit: int | None = None) -> list[dict[str, Any]]:
        solutions: list[dict[str, Any]] = []
        assignment: dict[str, Any] = {}
        remaining = {name: list(domain) for name, domain in self.domains.items()}

        def consistent(candidate: Mapping[str, Any]) -> bool:
            for constraint in self.constraints:
                if not constraint(candidate):
                    return False
            return True

        def backtrack() -> None:
            if limit is not None and len(solutions) >= limit:
                return
            if len(assignment) == len(self.variables):
                if consistent(assignment):
                    solutions.append(dict(assignment))
                return

            name = min(
                (v for v in self.variables if v not in assignment),
                key=lambda v: len([x for x in remaining[v] if
                                   consistent({**assignment, v: x})]),
            )
            for value in remaining[name]:
                trial = {**assignment, name: value}
                if not consistent(trial):
                    continue

                # Forward checking: remove values unsupported by assigned constraints.
                saved = {key: list(values) for key, values in remaining.items()}
                assignment[name] = value
                empty = False
                for future in (v for v in self.variables if v not in assignment):
                    remaining[future] = [
                        future_value
                        for future_value in remaining[future]
                        if consistent({**assignment, future: future_value})
                    ]
                    if not remaining[future]:
                        empty = True
                if not empty:
                    backtrack()
                del assignment[name]
                remaining.clear()
                remaining.update(saved)

        backtrack()
        return solutions

    def generate_invalid(
        self,
        base_payload: Mapping[str, Any],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return boundary/invalid payloads and violated constraint tags."""
        invalid: list[dict[str, Any]] = []
        for name in self.variables:
            values = [None, "", " ", "x" * 4096]
            values.extend(value for value in self.domains[name] if value not in values)
            for value in values:
                payload = dict(base_payload)
                payload[name] = value
                violated = [f"constraint_{i}" for i, c in enumerate(self.constraints) if not c(payload)]
                if violated:
                    invalid.append({
                        "payload": payload,
                        "violated_constraints": violated,
                        "boundary": name,
                    })
                    if len(invalid) >= limit:
                        return invalid
        return invalid
