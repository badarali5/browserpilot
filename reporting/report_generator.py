from __future__ import annotations

from pathlib import Path

from reporting.html_report import render_html_report
from reporting.json_report import render_json_report
from reporting.report_models import TestRunModel


def generate_html(run: TestRunModel) -> str:
    return render_html_report(run)


def generate_json(run: TestRunModel) -> str:
    return render_json_report(run)
