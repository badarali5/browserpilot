# BrowserPilot

BrowserPilot is an AI-assisted software-testing product. The Week 1 foundation contains:

- A small demo application with registration, login, profile editing, and password reset flows.
- A FastAPI health endpoint.
- Fixed Playwright tests that establish a deterministic baseline.

## Setup

From PowerShell:

```powershell
cd C:\Users\CS\Downloads\browserpilot
py -3 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m playwright install chromium
cd demo-app
npm install
cd ..
```

## Run the demo app

```powershell
npm run dev
```

Open <http://127.0.0.1:5173>.

## Run the API

```powershell
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open <http://127.0.0.1:8000/health>.

## Run baseline browser tests

Start the demo app first, then run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests
```

## Milestone 3: Autonomous agent

Set the replaceable OpenAI-compatible provider variables:

```powershell
$env:BROWSERPILOT_LLM_API_KEY = "..."
$env:BROWSERPILOT_LLM_MODEL = "gpt-4o-mini"
$env:BROWSERPILOT_LLM_BASE_URL = "https://api.openai.com/v1"
```

The agent is also available through `POST /api/run-agent-test`. It accepts `goal`, `target_url`,
`timeout`, `max_actions`, `max_duration`, and `artifact_dir`.

Example:

```powershell
curl -Method POST http://127.0.0.1:8000/api/run-agent-test `
  -ContentType "application/json" `
  -Body '{"goal":"Navigate to /login and verify that Log In is present","target_url":"http://127.0.0.1:8000","max_actions":12}'
```
