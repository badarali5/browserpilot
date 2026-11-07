# BrowserPilot — Development Log

A running journal of what was built, why it was built that way, and what the
test suite looked like at each checkpoint.

* **Branch:** `feature/browser-pilot-core`
* **Stack:** Python 3.12 · FastAPI · Playwright (async) · Pydantic v2 ·
  Streamlit · SQLAlchemy/SQLite · NumPy/Pandas/Plotly/Matplotlib · pytest ·
  Docker Compose
* **Rule of the project:** Python only — no React, no Node, no Vue.

---

## Phase 0 — Repository and environment

| Item | Decision |
| --- | --- |
| Python | 3.12 via `py -3`, virtualenv at `.venv/` |
| Browser | Playwright Chromium installed system-wide (headless) |
| Dependency pins | lower-bound (`>=`) so local, CI and Docker all resolve compatible builds |
| Branch policy | work happens on `feature/browser-pilot-core`; nothing is ever pushed to `main`/`master` |

---

## Phase 1 — Hand-written algorithms (`core/algorithms/`)

Built first, because everything else depends on them being trustworthy.

* `search.py` — one shared `SuccessorFn` signature so BFS/DFS/UCS/Greedy/A\*
  are drop-in comparable; every run returns an instrumented `SearchResult`
  (cost, expanded, max_frontier, trace) rather than just a path. Two
  admissible heuristics: Levenshtein (`string_heuristic`) and set overlap.
* `csp.py` — MRV + degree + LCV + forward checking, with the solver reporting
  `backtracks`/`inferences` so the heuristics can be *shown* to pay off rather
  than just asserted.
* `optimization.py` — generic `GeneticAlgorithm` plus a domain wrapper
  (`generate_fuzz_inputs`) that evolves adversarial form inputs; Minimax and
  `alpha_beta` over a two-player `GameState` (agent vs. UI).
* `probabilistic.py` — HMM with six hidden UI health states and eight
  observables, Viterbi in log space, plus a Kalman filter wrapped by
  `LatencyTracker`.
* `ml_models.py` — Logistic Regression, CART Decision Tree, KNN, Gaussian
  Naive Bayes, K-Means (k-means++ seeding) and agglomerative clustering with
  shared evaluation helpers.
* `rl_agent.py` — tabular Q-Learning over a `GridWorldEnv` whose reward
  function rewards *progress*, not just goal arrival.

**Decision:** no ML/data framework anywhere. NumPy is allowed for vectorised
math; scikit-learn, networkx and friends are not.

---

## Phase 2 — Browser layer (`core/browser/`)

* `dom_parser.py` — stdlib `HTMLParser`-based extractor producing typed
  `InteractiveNode`s with stable `e1…en` references, plus a converter for
  Playwright accessibility snapshots. Raw HTML never leaves this module.
  `DOMAbstraction.diff()` compares structural signatures and reports
  `added / removed / changed / drift`, which is the BUG_3 detector.
* `engine.py` — the only module that touches Playwright: `goto/click/type/
  select/hover/assert_visible/wait/screenshot`, each returning an immutable
  `StepRecord` bundle (URL before/after, console, network, screenshot path,
  DOM tokens, duration).
* `vision.py` — pure-Python PNG decoder (all five filters) + MSE similarity +
  luminance-grid layout-shift scoring.

**Decision:** DOM abstraction over raw HTML everywhere, including the
`_corrective_decision` context passed to the optional LLM policy — that keeps
the prompt-injection surface and the token cost bounded by the number of
*interactive* elements rather than page size.

---

## Phase 3 — Agents (`core/agents/`)

* **Planner** — parses the goal into a target state, runs the chosen search
  algorithm over `SITE_GRAPH`, then expands the path into a topologically
  ordered DAG of intent-based `PlanStep`s.
* **Browser** — the execution loop: resolve target → capture before-state →
  execute → verify → on failure ask the optional LLM policy, otherwise walk a
  deterministic recovery ladder (wait → re-resolve → retry → give up).
* **Verifier** — dual channel per step: DOM/console/network/diff checks and a
  vision check, chained through Viterbi into an anomaly taxonomy
  (`UI_STATE_FAILURE`, `API_FAILURE`, `SELECTOR_RESILIENCE`,
  `LATENCY_FLAKINESS`, `VISUAL_REGRESSION`, `STATE_FLAKINESS`).
* **BugAnalyst** — turns anomalies into deduplicated, severity-ranked reports
  with `steps_to_reproduce` and a root-cause classification.
* **Orchestrator** — plans, runs, verifies, analyses, persists; also owns the
  fixed-script benchmark.

---

## Phase 4 — Target application, API, dashboard, tests

* `target_app/` — FastAPI + Jinja2 app with register / login / profile /
  password reset / shop / multi-step checkout, and a `POST /api/bugs` bug
  injector for four runtime-toggleable defects.
* `backend/` — FastAPI orchestration API (runs, jobs, metrics, search
  benchmark, bug toggles, markdown reports).
* `dashboard/` — Streamlit with Overview / Live Run / Bugs / AI Lab /
  Benchmark views over `components/`.
* `tests/` — algorithm unit suite, target-app suite (TestClient), agent suite
  (no browser), and a Playwright integration suite that boots the target app
  on a free port.

---

## Phase 5 — Fix wave (the "make it actually pass" round)

The first end-to-end integration run was a failure:

```
1 failed, 2 passed in 684.74s
test_registration_flow_passes_when_clean — task_completion_rate: 0.1
```

Two root causes were measured, then fixed together.

### 5.1 Vision was 100× slower than it needed to be

`compare_images` cost **≈9 s per step** on 1440×900 screenshots
(decode 1.7 s ×2, MSE 2.0 s, layout shift 2.3 s; PNG filters alone 0.8 s and
RGB conversion 0.4 s). With ~35 s per agent step, a 12-step run could not
finish inside any reasonable budget.

Fix: a NumPy fast path in `vision.py`.

* filters 0/1/2 vectorised (Sub via per-lane `np.cumsum & 0xFF`, Up via
  uint8 wrap-add); only Average/Paeth rows keep a Python loop;
* RGB conversion via `reshape`, MSE in float32 with a float64 mean, and
  block-means for the luminance grid;
* tuple `pixels` exposed through a lazy `_LazyPixelList` so the pure-Python
  kernels and the unit tests keep working unchanged;
* a bounded decode memo, because consecutive verification frames are
  frequently byte-identical.

**Result: 9 s → 0.09 s per comparison.** The integration suite went from
684.74 s to 52.69 s.

### 5.2 The plan had no navigation steps

`expand_path` produced recipes only: the plan said `fill #email` while the
browser was still sitting on `/`, so the first action timed out and the whole
run collapsed.

Fixes in `core/agents/planner.py`:

* **Explicit `navigate` steps** for every hop onto a plain route (states
  containing `{` or `#` are side effects of the previous recipe and are
  skipped). The verification text is deliberately navigation-free
  (`"page /register rendered"`) so landing on a page we were *already* on
  never trips `route_changed`.
* **Pass-through suppression.** A\* legitimately routes *through* pages it has
  no business acting on (`/ → /login → /reset` walks over `/login`). A recipe
  now runs only at a page's **last** occurrence, so the login form is not
  submitted on the way to the reset form.
* **Two credential identities.** Registration mints a unique
  `pilot+<hex>@browserpilot.test` per plan so back-to-back runs never collide;
  login and password-reset use the seeded baseline `pilot@browserpilot.test`,
  because the app only confirms a reset for an account that *exists*.
* `required_waypoints()` gained `register` and `login` as independent
  waypoints instead of an either/or, so "register, log in and update the
  profile" actually exercises all three pages.

### 5.3 Target-app state

`POST /api/reset-state` emptied `USERS`, which left the login/reset flows
with no account to operate on. It now clears everything and re-seeds the
baseline accounts (`demo@` and `pilot@`). `test_reset_state_clears_users`
was updated to assert that ad-hoc registrations are wiped *and* the baseline
survives.

### 5.4 Agent robustness

* `resolve_target` verifies an explicit `#css` selector still exists in the
  live DOM before returning it. If it does not (BUG_3 drift) the element is
  recovered from its **stable** attributes — `name`, id prefix
  (`reset-link-a1b2c3` still starts with `reset-link`) or even its tag encoded
  in the class token (`orders-table` → `table`) — before falling through to
  the text/ref ladder.
* `_corrective_decision` now checks selector presence *first*. A missing
  selector is a resolution problem, not a timing problem, so it re-resolves
  immediately and fails fast when nothing can be recovered, instead of
  burning three retry cycles on waits that can never succeed.
* **Goal-visitation tracking.** A password reset ends at `/login?reset=1` and
  then signs in, moving on to `/profile` — rewarding only the final URL would
  have reported a fully successful flow as a failure. `goal_seen` records
  whether the goal state was ever observed. BUG_1 still fails, because it
  never reaches `/profile` at all.
* `RunOutcome.passed` now also requires **no anomalies**: a run that detected
  a UI/API failure did not pass.

### 5.5 Verifier correctness

* **Navigate steps assert their destination.** A silent redirect
  (unauthenticated `/profile` → `/login`) is exactly the failure the planner
  cannot see; it now raises `UI_STATE_FAILURE` on the navigate step itself.
* **Visual comparison is skipped when the route changed.** Comparing two
  *different* pages reports every successful navigation as a visual
  regression; that channel is meaningful for in-place updates only.

### 5.6 Performance and structure clean-ups

* `vision.py` decode memo, `_unfilter_numpy` row extraction, lazy pixel list.
* Fixed a pre-existing `SyntaxWarning` (`css_tokens` needed a raw string).
* Cosmetic: `visual_stable` check detail no longer prints `similarity=0.000`
  for a skipped comparison.

---

## Test history

| Checkpoint | Result | Wall time |
| --- | --- | --- |
| Algorithms only | 58 passed | < 1 s |
| + target app + agents | 131 passed | 6.7 s |
| **First integration attempt** | **1 failed, 2 passed** | **684.74 s** |
| Integration after fix wave | 9 passed | 52.69 s |
| **Full suite (final)** | **140 passed** | **57.04 s** |

### Live run quality (real Chromium, persisted to SQLite)

| Scenario | Status | Completion | Bugs | Anomalies |
| --- | --- | --- | --- | --- |
| clean / register | passed | 1.00 | 0 | none |
| clean / login | passed | 1.00 | 0 | none |
| clean / reset | passed | 1.00 | 0 | none |
| BUG_1 / register | failed | 0.58 | **2** | `UI_STATE_FAILURE`, `LATENCY_FLAKINESS` |
| BUG_2 / reset | failed | 0.33 | **4** | `API_FAILURE`, `UI_STATE_FAILURE`, `STATE_FLAKINESS` |

Zero false positives on clean runs; both injected defects detected with the
correct primary class.

---

## Decisions worth remembering

1. **Skip the visual channel on route change.** It was the single largest
   source of false `VISUAL_REGRESSION` anomalies and therefore of false bug
   reports.
2. **Never trust an explicit selector blindly.** Fall back to stable
   attributes, then to text, then to the raw string — in that order.
3. **Fail fast on missing selectors.** Waiting cannot conjure an element that
   a fresh post-load snapshot says is not there.
4. **Track goal *visitation*, not just goal *arrival*.** Flows that end by
   signing in legitimately leave the goal state behind.
5. **Two identities per plan.** Throwaway registration addresses, stable
   login/reset addresses.
6. **Measure before optimising.** The 100× vision speed-up came from a
   profiler run, not from guesswork.

---

## Known limitations / future work

* Docker image could not be built locally (no Docker daemon in this
  environment); `Dockerfile` and `docker-compose.yml` are written and
  reviewed but unbuilt.
* `LatencyTracker`'s Kalman prior is hand-tuned rather than learned.
* The optional LLM planner/policy hooks are implemented and covered by
  fallback tests but are disabled by default (`BROWSERPILOT_LLM=0`).
* The AI Lab exposes Search, CSP, HMM and RL interactively; the ML and
  optimisation families are exercised by the test suite and the agents.
