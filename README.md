# BrowserPilot

BrowserPilot is an AI-assisted browser testing platform built with FastAPI and Playwright.
It includes a demo website, deterministic test planning, real browser execution, evidence
collection, run history, and an optional LLM-assisted autonomous agent.

## Requirements

- Windows PowerShell
- Python 3.10 or newer
- Node.js and npm, only when running the separate React demo

## Setup

Run these commands from the repository root:

```powershell
cd C:\Users\CS\Downloads\browserpilot

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Create the virtual environment only once. Activate it if you prefer:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Run the complete application

```powershell
.\.venv\Scripts\python.exe app.py
```

Open:

- Application: http://127.0.0.1:8000
- API documentation: http://127.0.0.1:8000/api/docs
- API health: http://127.0.0.1:8000/api/health
- Demo login: http://127.0.0.1:8000/login
- Demo registration: http://127.0.0.1:8000/register

Press `Ctrl+C` in the terminal to stop the server.

## Run a browser test without an LLM API key

`POST /api/run-test` uses the built-in deterministic planner in
[planner/planner.py](planner/planner.py). It matches supported natural-language instructions
and converts them into navigate, input, click, assert, and screenshot steps.
Playwright executes those steps in a real Chromium browser.

No LLM API key is required for this endpoint.

Example:

```powershell
$body = @{
    goal = "navigate to /login and verify Login is present"
    target_url = "http://127.0.0.1:8000"
    timeout = 30
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/run-test" `
    -ContentType "application/json" `
    -Body $body
```

### Why it works without an API key

BrowserPilot has two planning modes:

1. **Deterministic planning:** `/api/run-test` calls `generate_plan_with_error()`. This local
   parser uses regular expressions and predefined selectors, then the Playwright engine
   executes the generated plan.
2. **LLM planning:** `/api/run-agent-test` uses `LLMPlanner` to convert goals and observations
   into autonomous browser actions. That mode requires an OpenAI-compatible API key.

The Playwright browser, FastAPI server, deterministic planner, verifier, database, and
reporting system do not call an external LLM. Chromium can therefore run and produce evidence
without `BROWSERPILOT_LLM_API_KEY` or `OPENAI_API_KEY`.

## Run the autonomous LLM agent

This mode is optional and requires an OpenAI-compatible API:

```powershell
$env:BROWSERPILOT_LLM_API_KEY = "your-api-key"
$env:BROWSERPILOT_LLM_MODEL = "gpt-4o-mini"
$env:BROWSERPILOT_LLM_BASE_URL = "https://api.openai.com/v1"
```

`OPENAI_API_KEY` is also accepted. Restart the server after setting environment variables.

`POST /api/run-agent-test` accepts `goal`, `target_url`, `timeout`, `max_actions`,
`max_duration`, and `artifact_dir`.

Example:

```powershell
$body = @{
    goal = "Navigate to /login and verify that Login is present"
    target_url = "http://127.0.0.1:8000"
    max_actions = 12
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/run-agent-test" `
    -ContentType "application/json" `
    -Body $body
```

Without a key, this endpoint returns HTTP 502 because it cannot initialize the LLM provider.
The regular browser-test endpoint continues to work.

## Run the tests

Run the complete test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Run the algorithm tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/m4/test_m4_algorithms.py tests/m4/test_m4_ml.py -q
```

Run the reproducible benchmark:

```powershell
.\.venv\Scripts\python.exe benchmarks/benchmark_m4.py
```

## Optional React demo app

The React demo is separate from the full FastAPI application:

```powershell
cd C:\Users\CS\Downloads\browserpilot\demo-app
npm install
npm run dev
```

Open http://127.0.0.1:5173.
## Milestone 4: Algorithmic testing strategies

BrowserPilot now provides modular implementations for:

- **BFS**: minimum-transition UI navigation.
- **A\***: weighted navigation with an optional admissible heuristic.
- **CSP plus backtracking/forward checking**: valid and deliberately invalid form payloads.
- **Genetic Algorithm**: seeded test-sequence evolution with measurable fitness.
- **Failure ML**: train/test supervised classification and k-means clustering over persisted records.

The implementations live in `algorithms/`, including `ui_state_graph.py`, `search_algorithms.py`,
`csp_solver.py`, `genetic_algorithm.py`, `failure_ml.py`, and `testing_strategy.py`. Algorithm actions use the
existing `BrowserTools`/Playwright layer; they cannot bypass URL allowlists or the verifier.

Run the reproducible synthetic benchmark:

```powershell
py benchmarks/benchmark_m4.py
```

Run Milestone 4 tests:

```powershell
py -m pytest tests/m4/test_m4_algorithms.py tests/m4/test_m4_ml.py -q
```
