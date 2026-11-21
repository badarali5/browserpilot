"""Independent Playwright browser verification helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError


def verification_result(
    condition: str,
    expected: Any,
    actual: Any,
    status: str,
    failure_type: Optional[str] = None,
    error: str = "",
    details: str = "",
) -> Dict[str, Any]:
    return {
        "condition": condition,
        "expected": expected,
        "actual": actual,
        "status": status,
        "failure_type": failure_type,
        "error": error,
        "details": details,
    }


def _selector(step: Dict[str, Any]) -> Optional[str]:
    selector = step.get("selector")
    return selector if isinstance(selector, str) and selector.strip() else None


async def verify(page, step: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
    """Evaluate an explicit condition against actual browser state."""
    condition = str(step.get("condition") or ("text_present" if step.get("action") == "assert" else "")).lower()
    expected = step.get("expected")
    selector = _selector(step)
    timeout_ms = max(100, int(step.get("timeout", timeout) * 1000))

    aliases = {
        "url_equals": "url_equals",
        "url equals": "url_equals",
        "url_contains": "url_contains",
        "url contains": "url_contains",
        "text_present": "text_present",
        "text present": "text_present",
        "text_absent": "text_absent",
        "text absent": "text_absent",
        "visible": "element_visible",
        "element_visible": "element_visible",
        "element visible": "element_visible",
        "hidden": "element_hidden",
        "element_hidden": "element_hidden",
        "element hidden": "element_hidden",
        "enabled": "element_enabled",
        "element_enabled": "element_enabled",
        "element enabled": "element_enabled",
        "disabled": "element_disabled",
        "element_disabled": "element_disabled",
        "element disabled": "element_disabled",
        "input_value_equals": "input_value_equals",
        "input value equals": "input_value_equals",
        "attribute_equals": "attribute_equals",
        "attribute equals": "attribute_equals",
    }
    condition = aliases.get(condition, condition)

    if not condition:
        return verification_result("", expected, None, "error", "invalid_condition", "Missing verification condition")

    try:
        if condition == "url_equals":
            actual = page.url
            return verification_result(condition, expected, actual, "pass" if actual == expected else "fail",
                                       None if actual == expected else "verification_failure",
                                       "" if actual == expected else f"URL did not equal {expected!r}")

        if condition == "url_contains":
            actual = page.url
            matched = str(expected) in actual
            return verification_result(condition, expected, actual, "pass" if matched else "fail",
                                       None if matched else "verification_failure",
                                       "" if matched else f"URL did not contain {expected!r}")

        if condition in {"text_present", "text_absent"}:
            if selector:
                try:
                    await page.wait_for_selector(selector, timeout=timeout_ms)
                except PlaywrightTimeoutError:
                    actual = None
                    return verification_result(condition, expected, actual, "timeout", "timeout",
                                               f"Timed out waiting for selector '{selector}'",
                                               "The selector was not found within the verification timeout.")
                locator = page.locator(selector)
                if condition == "text_present":
                    try:
                        await page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
                    except PlaywrightTimeoutError:
                        actual = await locator.inner_text(timeout=1000)
                        return verification_result(condition, expected, actual, "timeout", "timeout",
                                                   f"Timed out waiting for text {expected!r} in '{selector}'")
                actual = await locator.inner_text(timeout=timeout_ms)
            else:
                if condition == "text_present":
                    actual = await page.locator("body").inner_text(timeout=timeout_ms)
                    title = await page.title()
                    if str(expected).lower() in title.lower():
                        actual = title
                else:
                    actual = await page.locator("body").inner_text(timeout=timeout_ms)

            matched = str(expected).lower() in actual.lower()
            if condition == "text_present":
                passed = matched
                error = "" if passed else f"Expected text {expected!r} was not present"
            else:
                passed = not matched
                error = "" if passed else f"Unexpected text {expected!r} was present"
            return verification_result(condition, expected, actual, "pass" if passed else "fail",
                                       None if passed else "verification_failure", error)

        if condition in {"element_visible", "element_hidden"}:
            if not selector:
                return verification_result(condition, True, None, "error", "missing_selector",
                                           "A selector is required for element visibility verification")
            state = "visible" if condition == "element_visible" else "hidden"
            try:
                await page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                count = await page.locator(selector).count()
                actual = "missing" if count == 0 else ("visible" if await page.locator(selector).first.is_visible() else "hidden")
                return verification_result(condition, state, actual, "timeout", "timeout",
                                           f"Timed out waiting for selector '{selector}'")
            try:
                await page.wait_for_selector(selector, state=state, timeout=timeout_ms)
            except PlaywrightTimeoutError:
                count = await page.locator(selector).count()
                actual = "missing" if count == 0 else ("visible" if await page.locator(selector).first.is_visible() else "hidden")
                return verification_result(condition, state, actual, "timeout", "timeout",
                                           f"Timed out waiting for element state '{state}'")
            count = await page.locator(selector).count()
            actual = "visible" if count and await page.locator(selector).first.is_visible() else "hidden"
            passed = actual == state
            return verification_result(condition, state, actual, "pass" if passed else "fail",
                                       None if passed else "verification_failure",
                                       "" if passed else f"Expected element to be {state}, actual state was {actual}")

        if condition in {"element_enabled", "element_disabled"}:
            if not selector:
                return verification_result(condition, True, None, "error", "missing_selector",
                                           "A selector is required for enabled-state verification")
            locator = page.locator(selector)
            try:
                await locator.wait_for(state="attached", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                return verification_result(condition, condition == "element_enabled", None, "timeout", "timeout",
                                           f"Timed out waiting for selector '{selector}'")
            await page.wait_for_timeout(50)
            enabled = await locator.first.is_enabled()
            actual = "enabled" if enabled else "disabled"
            expected_state = "enabled" if condition == "element_enabled" else "disabled"
            passed = actual == expected_state
            return verification_result(condition, expected_state, actual, "pass" if passed else "fail",
                                       None if passed else "verification_failure",
                                       "" if passed else f"Expected element to be {expected_state}")

        if condition == "input_value_equals":
            if not selector:
                return verification_result(condition, expected, None, "error", "missing_selector",
                                           "A selector is required for input-value verification")
            try:
                await page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                return verification_result(condition, expected, None, "timeout", "timeout",
                                           f"Timed out waiting for input selector '{selector}'")
            actual = await page.locator(selector).input_value(timeout=timeout_ms)
            passed = actual == str(expected)
            return verification_result(condition, expected, actual, "pass" if passed else "fail",
                                       None if passed else "verification_failure",
                                       "" if passed else f"Input value did not equal {expected!r}")

        if condition == "attribute_equals":
            if not selector:
                return verification_result(condition, expected, None, "error", "missing_selector",
                                           "A selector is required for attribute verification")
            attribute = step.get("attribute")
            if not attribute:
                return verification_result(condition, expected, None, "error", "missing_attribute",
                                           "An attribute name is required")
            try:
                await page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                return verification_result(condition, expected, None, "timeout", "timeout",
                                           f"Timed out waiting for selector '{selector}'")
            actual = await page.locator(selector).first.get_attribute(attribute)
            passed = actual == str(expected)
            return verification_result(condition, expected, actual, "pass" if passed else "fail",
                                       None if passed else "verification_failure",
                                       "" if passed else f"Attribute {attribute!r} did not equal {expected!r}")

        return verification_result(condition, expected, None, "error", "unsupported_condition",
                                   f"Unsupported verification condition: {condition}")

    except PlaywrightTimeoutError as exc:
        return verification_result(condition, expected, None, "timeout", "timeout",
                                   f"Playwright timeout during verification: {exc}")
    except Exception as exc:
        return verification_result(condition, expected, None, "error", "execution_error", str(exc))
