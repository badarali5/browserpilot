"""Compatibility import for the reorganized browser package."""

from browser.observer import (
    capture_page_snapshot,
    extract_visible_interactive_elements,
)

__all__ = ["capture_page_snapshot", "extract_visible_interactive_elements"]
