import asyncio

import pytest

from observer import capture_page_snapshot, extract_visible_interactive_elements
from verifier import verify


pytestmark = pytest.mark.integration


async def launch_page():
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page()
    return playwright, browser, page


def test_observer_and_verifier():
    asyncio.run(_test_observer_and_verifier())


async def _test_observer_and_verifier():
    playwright, browser, page = await launch_page()
    try:
        await page.set_content(
            """
            <title>Observer Test</title>
            <main>
              <button id="save">Save changes</button>
              <a id="link" href="/help">Help</a>
              <label for="email">Email</label>
              <input id="email" name="email" type="email" value="ada@example.com">
              <label for="password">Password</label>
              <input id="password" name="password" type="password" value="correct-horse" disabled>
              <button id="hidden" style="display:none">Hidden action</button>
            </main>
            """
        )
        await page.goto("data:text/html,")

        await page.set_content(
            """
            <title>Observer Test</title>
            <main>
              <button id="save">Save changes</button>
              <a id="link" href="/help">Help</a>
              <label for="email">Email</label>
              <input id="email" name="email" type="email" value="ada@example.com">
              <label for="password">Password</label>
              <input id="password" name="password" type="password" value="correct-horse" disabled>
              <button id="hidden" style="display:none">Hidden action</button>
            </main>
            """
        )

        snapshot = await capture_page_snapshot(page)
        assert snapshot["title"] == "Observer Test"
        kinds = {item["kind"] for item in snapshot["interactive"]["elements"]}
        assert "button" in kinds
        assert "input" in kinds
        assert "link" in kinds
        assert all(item["name"] != "Hidden action" for item in snapshot["interactive"]["elements"])
        assert "correct-horse" not in snapshot["visible_text"]
        assert "correct-horse" not in snapshot["dom"]

        url_result = await verify(page, {"condition": "url_contains", "expected": "text/html"})
        assert url_result["status"] in {"pass", "fail"}
        actual_url = page.url
        url_equal = await verify(page, {"condition": "url_equals", "expected": actual_url})
        assert url_equal["status"] == "pass"
        url_fail = await verify(page, {"condition": "url_equals", "expected": "https://example.invalid/"})
        assert url_fail["status"] == "fail"
        assert url_fail["failure_type"] == "verification_failure"

        text_pass = await verify(page, {"condition": "text_present", "expected": "Save changes"})
        assert text_pass["status"] == "pass", repr(text_pass)

        text_fail = await verify(page, {"condition": "text_absent", "expected": "Save changes", "timeout": 0.1})
        assert text_fail["status"] == "fail"

        visible = await verify(page, {"condition": "element_visible", "selector": "#save", "expected": True})
        assert visible["status"] == "pass"
        hidden = await verify(page, {"condition": "element_hidden", "selector": "#hidden", "expected": True})
        assert hidden["status"] == "pass"

        input_value = await verify(page, {
            "condition": "input_value_equals",
            "selector": "#email",
            "expected": "ada@example.com",
        })
        assert input_value["status"] == "pass"

        missing = await verify(page, {
            "condition": "element_visible",
            "selector": "#missing",
            "expected": True,
            "timeout": 0.1,
        })
        assert missing["status"] == "timeout"
        assert "selector" in missing["error"].lower()

        disabled = await verify(page, {
            "condition": "element_disabled",
            "selector": "#password",
            "expected": True,
            "timeout": 0.1,
        })
        assert disabled["status"] == "pass"

        attribute = await verify(page, {
            "condition": "attribute_equals",
            "selector": "#email",
            "attribute": "type",
            "expected": "email",
            "timeout": 0.1,
        })
        assert attribute["status"] == "pass"
    finally:
        await browser.close()
        await playwright.stop()
