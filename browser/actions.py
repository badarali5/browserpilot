"""Controlled browser tools and the Playwright-backed autonomous agent."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from browser.browser_engine import resolve_navigation_url, validate_target_url
from browser.observer import capture_page_snapshot
from verification.verifier import verify


class BrowserTools:
    """The only browser operations exposed to the LLM."""

    ALLOWED = {"navigate", "observe_page", "click", "fill", "screenshot", "verify"}

    def __init__(self, page, target_url: str, artifact_dir: str = "artifacts") -> None:
        self.page = page
        self.target_url = validate_target_url(target_url)
        self.target_origin = self.target_url
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, action: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
        tool = action.get("tool")
        args = action.get("arguments", {})
        if tool not in self.ALLOWED:
            return {"status": "error", "error": f"Tool '{tool}' is not permitted"}

        before = await self.observe_page()
        try:
            if tool == "navigate":
                url = resolve_navigation_url(self.target_url, args["url"])
                await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                result = {"status": "pass", "evidence": f"Navigated to {url}"}
            elif tool == "observe_page":
                result = {"status": "pass", "observation": before}
            elif tool == "click":
                await self._click(args["selector"], timeout)
                result = {"status": "pass", "evidence": f"Clicked {args['selector']}"}
            elif tool == "fill":
                await self._fill(args["selector"], args["value"], timeout)
                redacted = "[redacted]" if "password" in args["selector"].lower() else args["value"]
                result = {"status": "pass", "evidence": f"Filled {args['selector']} with {redacted}"}
            elif tool == "screenshot":
                path = self.artifact_dir / f"agent_{int(time.time() * 1000)}.png"
                await self.page.screenshot(path=str(path))
                result = {"status": "pass", "evidence": f"Screenshot saved to {path}"}
            elif tool == "verify":
                verification = await verify(
                    self.page,
                    {
                        "condition": args["condition"],
                        "expected": args.get("expected"),
                        "selector": args.get("selector"),
                        "attribute": args.get("attribute"),
                        "timeout": args.get("timeout", timeout),
                    },
                    timeout=timeout,
                )
                result = {
                    "status": verification["status"],
                    "evidence": verification["details"] or verification["error"],
                    "verification": verification,
                }
            else:
                return {"status": "error", "error": "Unsupported controlled tool"}
        except Exception as exc:
            result = {"status": "error", "error": exc.__class__.__name__}

        after = await self.observe_page()
        result["observation_before"] = before
        result["observation_after"] = after
        return result

    async def observe_page(self) -> Dict[str, Any]:
        return await capture_page_snapshot(self.page)

    async def _click(self, selector: str, timeout: int) -> None:
        try:
            await self.page.locator(selector).first.click(timeout=timeout * 1000)
            return
        except Exception:
            if selector.startswith("text="):
                await self.page.get_by_text(selector[5:], exact=False).first.click(timeout=timeout * 1000)
                return
            raise

    async def _fill(self, selector: str, value: str, timeout: int) -> None:
        locator = self.page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout * 1000)
        await locator.fill(value)
