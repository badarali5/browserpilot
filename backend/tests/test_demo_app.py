from pathlib import Path

from playwright.sync_api import Page, expect


DEMO_URL = "http://127.0.0.1:5173"


def test_user_can_register_and_update_profile(page: Page) -> None:
    page.goto(DEMO_URL)
    page.get_by_role("button", name="Register").click()
    page.get_by_label("Name").fill("Ada Lovelace")
    page.get_by_label("Email").fill("ada@example.com")
    page.get_by_label("Password").fill("correct-horse-battery-staple")
    page.get_by_role("button", name="Create account").click()

    expect(page.get_by_role("heading", name="Your profile")).to_be_visible()
    expect(page.get_by_label("Display name")).to_have_value("Ada Lovelace")

    page.get_by_label("Display name").fill("Ada Byron Lovelace")
    page.get_by_role("button", name="Save profile").click()
    expect(page.get_by_text("Profile saved")).to_be_visible()


def test_registered_user_can_log_in(page: Page) -> None:
    page.goto(DEMO_URL)
    page.get_by_role("button", name="Login").click()
    page.get_by_label("Email").fill("ada@example.com")
    page.get_by_label("Password").fill("correct-horse-battery-staple")
    page.get_by_role("button", name="Log in").click()

    expect(page.get_by_role("heading", name="Your profile")).to_be_visible()


def test_user_can_request_password_reset(page: Page) -> None:
    page.goto(DEMO_URL)
    page.get_by_role("button", name="Login").click()
    page.get_by_role("button", name="Reset password").click()
    page.get_by_label("Email").fill("ada@example.com")
    page.get_by_role("button", name="Send reset link").click()

    expect(page.get_by_text("Reset link sent")).to_be_visible()
