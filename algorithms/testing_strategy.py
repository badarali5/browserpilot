"""Shared interface for browser-testing strategies."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class TestingStrategy(Protocol):
    """A strategy proposes one controlled BrowserTools action for a browser state."""

    async def generate_next_action(
        self,
        state: Mapping[str, Any],
        goal: Mapping[str, Any] | str,
    ) -> Dict[str, Any]:
        ...
