"""Compatibility import for the reorganized browser package."""

from browser.browser_engine import (
    execute_plan,
    make_result,
    resolve_navigation_url,
    validate_target_url,
)

__all__ = [
    "execute_plan",
    "make_result",
    "resolve_navigation_url",
    "validate_target_url",
]
