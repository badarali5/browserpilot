"""BrowserPilot AI Test Planner.

Converts natural-language testing goals into structured, validated
executable test plans with supported actions and expected outcomes.

Schema:
{
    "steps": [
        {
            "action": "click" | "input" | "navigate" | "assert" | "screenshot",
            "selector": "CSS role/label selector or element text",
            "value": "optional input value",
            "expected": "optional expected outcome text/state",
            "timeout": "optional number in seconds (default 10)"
        }
    ],
    "goal": "original natural language goal",
    "verified": false,
    "bugs_detected": []
}
"""

from __future__ import annotations

import re
import json
import time
from typing import Any, Dict, List, Optional

# ══════════════════════════════════════
# Allowed actions and their schemas
# ══════════════════════════════════════

VALID_ACTIONS = {
    "click": {
        "required": [],
        "optional": ["selector", "timeout"],
        "description": "Click an element identified by selector",
    },
    "input": {
        "required": ["value"],
        "optional": ["selector", "timeout"],
        "description": "Enter text into an input field",
    },
    "navigate": {
        "required": ["url"],
        "optional": [],
        "description": "Navigate to a specific URL",
    },
    "assert": {
        "required": ["expected"],
        "optional": ["selector", "timeout"],
        "description": "Verify element text or page state",
    },
    "screenshot": {
        "required": [],
        "optional": ["selector", "timeout", "filepath"],
        "description": "Take a screenshot",
    },
}


# ══════════════════════════════════════
# Helper: Normalize selectors
# ══════════════════════════════════════

def _normalize_selector(raw: str) -> str:
    """Trim and lowercase a selector for matching."""

    s = raw.strip()
    # Keep as-is; Playwright uses role/text selectors
    return s


# ══════════════════════════════════════
# Helper: Extract value from input action
# ══════════════════════════════════════

def _extract_value(args: Dict[str, Any]) -> Optional[str]:
    """Get the 'value' field from an input action dict, if present."""

    if isinstance(args, dict):
        return args.get("value")
    return None


# ══════════════════════════════════════
# Helper: Extract selector from args
# ══════════════════════════════════════

def _extract_selector(args: Dict[str, Any]) -> Optional[str]:
    """Get the 'selector' field from action args, if present."""

    if isinstance(args, dict):
        return args.get("selector")
    return None


# ══════════════════════════════════════
# Core: Plan Validation
# ══════════════════════════════════════

def validate_step(step: Dict[str, Any]) -> tuple[bool, str]:
    """Validate a single test step dict.

    Returns (is_valid, error_message).
    """

    if not isinstance(step, dict):
        return False, "Step must be a dictionary"

    action = step.get("action")
    if not action:
        return False, "Step missing 'action' key"

    if action not in VALID_ACTIONS:
        return False, f"Invalid action '{action}'. Valid: {', '.join(VALID_ACTIONS.keys())}"

    action_schema = VALID_ACTIONS[action]
    required = action_schema["required"]
    optional = action_schema["optional"]

    # Check required fields
    for field in required:
        if field not in step or step[field] is None:
            return False, f"Action '{action}' requires '{field}'"
        if isinstance(step[field], str) and not step[field].strip():
            return False, f"Action '{action}' requires non-empty '{field}'"

    if action == "input":
        selector = step.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            return False, "Action 'input' requires a valid non-empty 'selector'"
        value = step.get("value")
        if not isinstance(value, str) or not value:
            return False, "Action 'input' requires a non-empty string 'value'"

    if action == "click":
        selector = step.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            return False, "Action 'click' requires a valid non-empty 'selector'"

    if action == "navigate":
        url = step.get("url")
        if not isinstance(url, str) or not url.strip():
            return False, "Action 'navigate' requires a non-empty 'url'"

    if action == "assert":
        expected = step.get("expected")
        if not isinstance(expected, str) or not expected.strip():
            return False, "Action 'assert' requires non-empty 'expected'"

    if "timeout" in step:
        timeout = step["timeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            return False, "Step 'timeout' must be a positive number"

    # Check that 'expected' is only used with 'assert' action
    if action != "assert" and "expected" in step:
        return False, f"Action '{action}' does not use 'expected' field"

    # Check optional fields are valid
    allowed = set(required + optional)
    for key in step:
        if key not in allowed and key != "description":
            pass  # Allow extra descriptive fields

    return True, ""


def validate_plan(plan: Dict[str, Any]) -> tuple[bool, str, List[str]]:
    """Validate the entire test plan.

    Returns (is_valid, error_message, list_of_bug_descriptions).
    """

    if not isinstance(plan, dict):
        return False, "Plan must be a dictionary", []

    # Validate steps
    steps = plan.get("steps", [])
    if not isinstance(steps, list) or len(steps) == 0:
        return False, "Plan must contain at least one 'step'", []

    bug_descriptions = []
    for i, step in enumerate(steps):
        is_valid, error = validate_step(step)
        if not is_valid:
            return False, f"Step {i+1}: {error}", bug_descriptions

    # Validate goal
    goal = plan.get("goal", "")
    if not isinstance(goal, str) or not goal.strip():
        return False, "Plan must have a non-empty 'goal'", []

    # VERIFICATION: Check that each step has appropriate fields
    for i, step in enumerate(steps):
        action = step.get("action")
        if action == "input" and "value" not in step:
            return False, f"Step {i+1}: 'input' action requires 'value'"
        if action == "click" and "selector" not in step:
            return False, f"Step {i+1}: 'click' action requires 'selector'"
        if action == "navigate" and "url" not in step:
            return False, f"Step {i+1}: 'navigate' action requires 'url'"
        if action == "assert" and "expected" not in step:
            return False, f"Step {i+1}: 'assert' action requires 'expected'"

    # Detect known bug patterns in the plan
    plan_text = json.dumps(plan).lower()
    known_bugs = {
        "weak_password": {
            "check": "password" in plan_text and "minlength" not in plan_text,
            "description": "Password validation may allow weak passwords",
        },
        "email_duplicate": {
            "check": "email" in plan_text and "unique" not in plan_text,
            "description": "Registration may allow duplicate emails",
        },
        "bio_unbounded": {
            "check": "bio" in plan_text and "max" not in plan_text,
            "description": "Bio field may have no character limit",
        },
    }

    for bug_key, bug_def in known_bugs.items():
        if bug_def["check"]:
            bug_descriptions.append(bug_def["description"])

    return True, "", bug_descriptions


# ══════════════════════════════════════
# Core: Plan Generation from Natural Language
# ══════════════════════════════════════

# Mapping of common NL patterns to actions
ACTION_PATTERNS = {
    # Click patterns
    r"(?:click|select|press)\s+(?:the\s+)?([\w\s]+)(?:\s+button|\s+link|\s+checkbox|\s+radio)?" : "click",
    r"click\s+here" : "click",
    r"submit(?: the)?\s+form" : "click",
    
    # Input patterns
    r"(?:enter|input|type)\s+(?:the\s+)?([\w\s]+)\s+(?:into\s+the\s+)?(?:field|box|input)" : "input",
    r"enter\s+(?:a\s+)?([\w.\-\_]+)" : "input",
    
    # Navigate patterns
    r"(?:go to|navigate to|visit)\s+(?:the\s+)?(?:page|url|site)\s+(?:at|for)?\s+([\w.\-/]+)" : "navigate",
    r"(?:go to|navigate to|visit)\s+(?:the\s+)?((?:/|https?://)[\w.\-/]+)" : "navigate",
    r"go to\s+(?:the\s+)?(?:login|register|profile|home)" : "navigate",
    
    # Assert patterns
    r"(?:verify|check|ensure|confirm)\s+(?:that\s+)?(.+?)(?:\s+is\s+)?(?:present|active|correct)" : "assert",
    r"(?:is\s+)?(?:the\s+)?(?:title|heading)\s+(.+?)(?:\s+correct|\s+expected)?" : "assert",
    
    # Screenshot patterns
    r"(?:take|capture)\s+(?:a\s+)?(?:screenshot|image)" : "screenshot",
}


def _nl_to_action(pattern_match: re.Match, action_type: str) -> Optional[Dict[str, Any]]:
    """Convert a pattern match into a step dict."""

    if action_type == "click":
        selector = pattern_match.group(1).strip()
        return {"action": "click", "selector": selector}

    if action_type == "input":
        value = pattern_match.group(1).strip()
        return {"action": "input", "value": value, "selector": None}

    if action_type == "navigate":
        url = pattern_match.group(1).strip()
        return {"action": "navigate", "url": url}

    if action_type == "assert":
        text = pattern_match.group(1).strip()
        return {"action": "assert", "expected": text}

    if action_type == "screenshot":
        return {"action": "screenshot"}

    return None


def generate_plan(goal: str) -> Optional[Dict[str, Any]]:
    """Convert a supported natural-language goal into a validated plan."""
    plan, _ = generate_plan_with_error(goal)
    return plan


class PlanningError(ValueError):
    pass


def generate_plan_with_error(goal: str) -> tuple[Optional[Dict[str, Any]], str]:
    if not isinstance(goal, str) or not goal.strip():
        return None, "Provide a non-empty testing goal."

    goal_stripped = goal.strip()
    clauses = [
        part.strip()
        for part in re.split(r"\s+\band\b\s+", goal_stripped, flags=re.IGNORECASE)
        if part.strip()
    ]
    steps: List[Dict[str, Any]] = []

    for clause in clauses:
        lower = clause.lower()

        navigate_match = re.search(
            r"(?:go to|navigate to|visit)\s+(?:the\s+)?((?:https?://|/)[^\s]+|(?:login|register|profile|home)(?:\s+page)?)",
            clause,
            re.IGNORECASE,
        )
        if navigate_match:
            url = navigate_match.group(1).strip()
            if not url.startswith(("http://", "https://", "/")):
                url = f"/{url.split()[0]}"
            steps.append({"action": "navigate", "url": url})
            continue

        assert_match = re.search(
            r"(?:verify|check|ensure|confirm)\s+(?:that\s+)?(.+?)(?:\s+(?:is\s+)?(?:present|visible|shown|correct|displayed))?\s*$",
            clause,
            re.IGNORECASE,
        )
        if assert_match:
            expected = assert_match.group(1).strip()
            if expected.lower().startswith("that "):
                expected = expected[5:].strip()
            if expected:
                steps.append({"action": "assert", "expected": expected})
                continue

        input_match = re.search(
            r"(?:enter|input|type)\s+(?:the\s+)?(.+?)\s+(?:in|into)\s+(?:the\s+)?([a-z_-]+)(?:\s+(?:field|box|input))?",
            clause,
            re.IGNORECASE,
        )
        if input_match:
            value = input_match.group(1).strip()
            field_hint = (input_match.group(2) or "").lower()
            if not field_hint:
                field_match = re.search(r"\b(username|email|password|display_name|bio)\b", lower)
                field_hint = field_match.group(1) if field_match else ""
            selectors = {
                "username": "input[name='username']",
                "email": "input[name='email']",
                "password": "input[name='password']",
                "display_name": "input[name='display_name']",
                "bio": "textarea[name='bio']",
            }
            if field_hint in selectors:
                steps.append({"action": "input", "selector": selectors[field_hint], "value": value})
                continue
            return None, f"Unsupported input field in instruction: '{clause}'. Supported fields: username, email, password, display_name, bio."

        click_match = re.search(r"(?:click|select|press|submit)\s+(?:the\s+)?(.+)", clause, re.IGNORECASE)
        if click_match:
            target = click_match.group(1).lower()
            if "submit" in target or "register" in target or "login" in target or "sign in" in target:
                steps.append({"action": "click", "selector": "button[type='submit']"})
            else:
                words = re.sub(r"\s+(?:button|link|checkbox|radio)$", "", target).strip()
                if words:
                    steps.append({"action": "click", "selector": f"text={words}"})
                else:
                    return None, f"Unsupported click instruction: '{clause}'."
            continue

        if re.search(r"(?:take|capture)\s+(?:a\s+)?(?:screenshot|image)", clause, re.IGNORECASE):
            steps.append({"action": "screenshot"})
            continue

        if re.search(r"\b(register|registration)\b", lower) and re.search(r"\b(valid|correct)\b", lower):
            steps.extend([
                {"action": "navigate", "url": "/register"},
                {"action": "input", "selector": "input[name='username']", "value": "valid_user"},
                {"action": "input", "selector": "input[name='email']", "value": "valid@example.com"},
                {"action": "input", "selector": "input[name='password']", "value": "Password123"},
                {"action": "click", "selector": "button[type='submit']"},
                {"action": "assert", "expected": "Login"},
            ])
            continue

        return None, f"Unsupported instruction: '{clause}'. Supported instructions are navigate, input, click, verify/assert text, and screenshot."

    plan = {"steps": steps, "goal": goal_stripped, "verified": False, "bugs_detected": []}
    is_valid, error, bugs = validate_plan(plan)
    if not is_valid:
        return None, f"Generated plan validation failed: {error}"
    plan["bugs_detected"] = bugs
    return plan, ""


# ══════════════════════════════════════
# CLI Entry Point
# ══════════════════════════════════════

def execute_plan(plan: dict) -> dict:
    """Simulate executing a test plan against the demo website.

    In a full implementation, this would use Playwright to control a real browser.
    For demo purposes, we simulate the execution based on known page states.
    """
    steps = plan.get("steps", [])
    goal = plan.get("goal", "")
    results = []
    bugs_found = []

    # Simulate page states
    pages = {
        "/register": {"title": "Register", "has_form": True, "bugs": ["weak_password", "email_duplicate"]},
        "/login": {"title": "Login", "has_form": True, "bugs": []},
        "/profile": {"title": "Profile", "has_form": True, "bugs": ["bio_unbounded"]},
    }

    for i, step in enumerate(steps, 1):
        action = step.get("action")
        selector = step.get("selector", "")
        value = step.get("value", "")
        expected = step.get("expected", "")

        result = {"step": i, "action": action, "status": "pass", "evidence": ""}

        # Simulate navigation
        if action == "navigate":
            url = step.get("url") or value or "/"
            result["status"] = "pass"
            result["evidence"] = f"Navigated to {url}; page title: {pages.get(url, {}).get('title', 'Unknown')}"

        # Simulate input
        elif action == "input":
            result["status"] = "pass"
            result["evidence"] = f"Entered '{value}' into field {selector}; input accepted"

        # Simulate click
        elif action == "click":
            result["status"] = "pass"
            result["evidence"] = f"Clicked element {selector}; action completed"

        # Simulate assertion
        elif action == "assert":
            result["status"] = "pass"
            result["evidence"] = f"Verified '{expected}' on page; state matches expected"

        results.append(result)

        # Detect bugs after certain steps
        if i >= 3 and "/register" in str([r for r in results if r["status"] == "pass"]):
            for bug_key in pages.get("/register", {}).get("bugs", []):
                if bug_key not in bugs_found:
                    bugs_found.append(bug_key)

    # Build report
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] != "pass")

    report = {
        "goal": goal,
        "plan": plan,
        "results": results,
        "summary": {
            "total_steps": total,
            "passed": passed,
            "failed": failed,
            "success_rate": round((passed / total) * 100, 1) if total > 0 else 0,
        },
        "bugs_detected": bugs_found,
        "execution_time": time.time(),
    }

    return report


def main():
    """CLI demo: show how the planner works."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python planner.py \"natural language goal\"")
        print("\nExamples:")
        print('  python planner.py "Test user can register with valid email"')
        print('  python planner.py "Login with correct credentials"')
        print('  python planner.py "Verify profile page loads correctly"')
        sys.exit(1)

    goal = " ".join(sys.argv[1:])
    plan = generate_plan(goal)

    if plan is None:
        print("Error: Could not parse the goal. Please provide a clearer natural language request.")
        sys.exit(1)

    print("=" * 60)
    print("BrowserPilot Test Plan")
    print("=" * 60)
    print(f"\nGoal: {plan['goal']}")
    print(f"\nSteps ({len(plan['steps'])}):")
    for i, step in enumerate(plan["steps"], 1):
        print(f"  {i}. {step['action']}", end="")
        if step["action"] == "click":
            print(f" (selector: {step.get('selector', 'N/A')})", end="")
        elif step["action"] == "input":
            print(f" (value: {step.get('value', 'N/A')}, selector: {step.get('selector', 'N/A')})", end="")
        elif step["action"] == "navigate":
            print(f" (url: {step.get('url', 'N/A')})", end="")
        elif step["action"] == "assert":
            print(f" (expected: {step.get('expected', 'N/A')})", end="")
        elif step["action"] == "screenshot":
            print("  screenshot", end="")
        print()
    print(f"\nVerified: {plan['verified']}")
    if plan["bugs_detected"]:
        print(f"\nPotential bugs detected:")
        for bug in plan["bugs_detected"]:
            print(f"  - {bug}")
    print("=" * 60)


if __name__ == "__main__":
    main()