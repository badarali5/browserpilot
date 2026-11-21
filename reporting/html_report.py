from __future__ import annotations

from html import escape

from reporting.report_models import TestRunModel


def render_html_report(run: TestRunModel) -> str:
    step_rows = []
    for step in run.steps:
        verification = ""
        if step.verification:
            verification = (
                f"<p><strong>Verification:</strong> {escape(step.verification.condition)} "
                f"= {escape(str(step.verification.status))}</p>"
            )
        step_rows.append(
            f"""
            <article class="step">
              <h3>Step {step.step_number}: {escape(step.action)}</h3>
              <p><strong>Status:</strong> {escape(step.status)}</p>
              <p><strong>Started:</strong> {escape(step.started_at.isoformat())}</p>
              <p><strong>Completed:</strong> {escape(step.completed_at.isoformat())}</p>
              <p><strong>Classification:</strong> {escape(step.error_classification)}</p>
              {verification}
              {f'<p class="error">{escape(step.error)}</p>' if step.error else ""}
            </article>
            """
        )

    artifact_rows = "".join(
        f'<li><a href="/api/artifacts/{escape(a.artifact_id)}">{escape(a.name)}</a> '
        f"({escape(a.artifact_type)}, {a.size_bytes} bytes)</li>"
        for a in run.artifacts
    )
    evidence_errors = "".join(
        f"<li>{escape(error)}</li>" for error in run.evidence_collection_errors
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>BrowserPilot report {escape(run.run_id)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #172033; }}
    .summary {{ background: #f4f7fb; padding: 1rem; border-radius: .5rem; }}
    .step {{ border: 1px solid #dce3ec; border-radius: .5rem; padding: 1rem; margin: .75rem 0; }}
    .error {{ color: #a10d24; }}
  </style>
</head>
<body>
  <h1>BrowserPilot Test Report</h1>
  <section class="summary">
    <p><strong>Run ID:</strong> {escape(run.run_id)}</p>
    <p><strong>Goal:</strong> {escape(run.goal)}</p>
    <p><strong>Target:</strong> {escape(run.target_url)}</p>
    <p><strong>Status:</strong> {escape(run.status)}</p>
    <p><strong>Duration:</strong> {run.duration_seconds:.3f} seconds</p>
  </section>
  <h2>Execution Summary</h2>
  <pre>{escape(str(run.summary))}</pre>
  <h2>Steps</h2>
  {''.join(step_rows)}
  <h2>Evidence</h2>
  <ul>{artifact_rows}</ul>
  <h2>Evidence Collection Errors</h2>
  <ul>{evidence_errors or '<li>None</li>'}</ul>
</body>
</html>
"""
