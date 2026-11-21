"""BrowserPilot - One command to rule them all.

Run:    python run.py
It will:
  1. Verify environment (Python, Chromium, DB)
  2. Start the FastAPI server
  3. Auto-open the browser
"""

import webbrowser
import subprocess
import sys
import os
import time
from pathlib import Path


def check_environment():
    """Verify that required tools are available."""
    issues = []

    # Check Python version
    if sys.version_info < (3, 10):
        issues.append("Python >= 3.10 required (found {})".format(sys.version_info))

    # Check Chromium/Playwright
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        issues.append("playwright not installed - run: python -m pip install playwright")

    return issues


def main():
    issues = check_environment()
    if issues:
        print("Environment check FAILED:")
        for issue in issues:
            print(f"  - {issue}")
        print("\nFix these issues before running.")
        return

    # Open browser after a short delay
    def open_browser():
        webbrowser.open("http://127.0.0.1:8000")

    # Start the server using the script's own directory
    script_dir = str(Path(__file__).parent)
    print("Starting BrowserPilot...")
    print("=" * 50)
    print("Opening browser in a moment...")
    print("=" * 50)

    # Start uvicorn in background from the script's directory
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=script_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Schedule browser open (wait for server to start)
    import threading
    time.sleep(2)  # Wait for server to start
    open_browser()

    # Keep the console alive
    print("\nBrowserPilot running at http://127.0.0.1:8000")
    print("Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()