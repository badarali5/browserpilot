from __future__ import annotations

import json

from reporting.report_models import TestRunModel


def render_json_report(run: TestRunModel) -> str:
    return json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=True)
