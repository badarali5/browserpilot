# BrowserPilot — AI Algorithm Reference

Every algorithm in BrowserPilot is **hand-written** in [`core/algorithms/`](core/algorithms/)
using only the Python standard library plus NumPy for vectorised math.
No scikit-learn, no PyTorch, no `networkx`, no third-party search or
probabilistic libraries — the point of the project is that the reasoning
layer is ours end to end.

Six modules, six families:

| Family | Module | What lives there |
| --- | --- | --- |
| Search | `search.py` | BFS, DFS, Uniform-Cost, Greedy Best-First, A\* |
| Constraint satisfaction | `csp.py` | backtracking + MRV/degree/LCV/forward checking |
| Optimisation | `optimization.py` | Genetic Algorithm, Minimax + alpha–beta |
| Probabilistic | `probabilistic.py` | HMM + Viterbi, Kalman filter, latency tracker |
| Machine learning | `ml_models.py` | Logistic Regression, Decision Tree, KNN, Naive Bayes, K-Means, Hierarchical clustering |
| Reinforcement learning | `rl_agent.py` | Tabular Q-Learning + `GridWorldEnv` |

---

## 1. Search — `core/algorithms/search.py`

**Problem.** A testing goal ("register a new account") is a *state* in a UI
graph. Pages are nodes, interactions are weighted edges:

```
("/",             "click:Create an account", 1.0, "/register")
("/register",     "submit:register",         4.0, "/profile")
("/login",        "submit:login",            3.0, "/profile")
("/reset",        "submit:email",            3.0, "/reset/{token}")
("/checkout#2",   "submit:payment",          2.0, "/checkout#3")
…
```

**API.** All five algorithms share one signature and return an
instrumented `SearchResult`:

```python
bfs(successors, start, goal) -> SearchResult
dfs(successors, start, goal) -> SearchResult
ucs(successors, start, goal) -> SearchResult
greedy_best_first(successors, start, goal, heuristic=…) -> SearchResult
astar(successors, start, goal, heuristic=…) -> SearchResult
```

Each records `path`, `actions`, `cost`, `steps`, `visited`, `expanded`,
`max_frontier`, `duration_ms` and a node-by-node `trace`, which is what the
AI Lab renders.

| Algorithm | Strategy | Guarantee |
| --- | --- | --- |
| BFS | FIFO frontier, unit edge weight | optimal in *hops*, not *cost* |
| DFS | LIFO frontier | cheapest memory, no optimality |
| UCS | priority queue on `g(n)` | optimal for arbitrary positive costs |
| Greedy | priority queue on `h(n)` only | fastest, often suboptimal |
| A\* | priority queue on `g(n) + h(n)` | optimal when `h` is admissible |

**Heuristics.** Two admissible heuristics are provided:

* `string_heuristic(goal)` — normalised Levenshtein distance between the
  current state string and the goal state string (`levenshtein_distance`),
  scaled so it never over-estimates the true remaining cost (unit costs).
* `set_overlap_heuristic(goal)` — `|goal \ current|`, the number of goal
  tokens still missing. Used for token/feature-set style states.

**Where it runs.**
`PlannerAgent.find_path()` (`core/agents/planner.py`) builds the successor
function with `build_graph(SITE_GRAPH)`, runs the selected algorithm leg by
leg (waypoints are stitched into one instrumented result) and then hands the
path to `expand_path()` to become the executable DAG. The same call is made
five times by `_compare_algorithms()` to power the AI Lab comparison table.

---

## 2. Constraint satisfaction — `core/algorithms/csp.py`

**Problem.** Filling a web form *validly* is a CSP: variables are the form
fields, domains are the value sets, constraints are the HTML `required`
attributes plus cross-field rules (password confirmation, TLD validity,
uniqueness).

**Solver.** `backtracking_search(csp, *, use_mrv=True, use_lcv=True, use_forward_checking=True)`
is a recursive backtracking search with three classic enhancements:

* **MRV** (minimum remaining values) — pick the most constrained variable first;
  **degree heuristic** breaks ties by the number of constraints involved.
* **LCV** (least constraining value) — try the value that rules out the fewest
  options for the remaining variables.
* **Forward checking** — after each assignment, prune the domains of the
  remaining variables; an empty domain fails the branch immediately.

`CSPResult` records `assignments`, `backtracks`, `inferences`, `duration_ms`
so the improvement over plain backtracking is measurable.

**Built-in models.** `generate_registration_matrix()`, `generate_password_matrix()`,
`generate_card_matrix()` and `synthesize_form_inputs(kind=…)` build ready-to-solve
form CSPs.

**Where it runs.**
* Runtime: `synthesize_form_inputs()` powers the **AI Lab → CSP** tab, which
  generates valid credentials/card numbers live.
* Tests: `tests/test_algorithms.py` checks that MRV+forward checking strictly
  reduces the backtrack count on the same problem.

---

## 3. Optimisation — `core/algorithms/optimization.py`

### 3.1 Genetic algorithm

`GeneticAlgorithm(fitness_fn, random_genes, *, population_size, generations,
crossover_rate, mutation_rate, tournament_size)` implements a standard GA:

1. random initial population,
2. tournament selection,
3. single-point crossover at `crossover_rate`,
4. per-gene mutation at `mutation_rate`,
5. **elitism** — the best individual survives unchanged each generation.

`evolve()` returns a `GAResult` with `best`, `best_fitness`, the fitness
history and per-generation progress callbacks.

**Where it runs.** `generate_fuzz_inputs(count, length, generations, …)`
evolves adversarial form inputs (oversized strings, control characters,
format-metacharacters, SQL/HTML fragments) scored by a fitness function that
rewards *plausible but hostile* inputs — the app's fuzz-input generator.

### 3.2 Minimax with alpha–beta pruning

`minimax_value(state, depth, evaluate, agent_actions, ui_actions, …)` plays a
two-player game between the **agent** (wants to reach the goal) and the **UI**
(wants to stall, break or loop the session). `alpha_beta(…)` prunes branches
that cannot affect the root value; `tests/test_algorithms.py` asserts the
pruned and full searches return the *identical* value.

**Where it runs.** `adversarial_ui_policy(state, depth)` is the domain wrapper
used by the AI Lab's adversarial view: it returns the best first move plus the
principal variation.

---

## 4. Probabilistic models — `core/algorithms/probabilistic.py`

### 4.1 Hidden Markov Model + Viterbi

**Problem.** You never *see* the UI's true health — you see per-step
percepts. The HMM makes that explicit:

* Hidden states (`WEB_STATES`):
  `healthy, loading, stalled, latency, render_failure, error`
* Observations (`OBSERVATIONS`):
  `dom_mutation, network_ok, network_error, spinner_on, spinner_off,
  console_error, timeout, static`

`web_health_hmm()` returns an `HMM` with hand-set start/transition/emission
distributions. `HMM.viterbi(observations)` runs the Viterbi dynamic program
(`O(T·|S|²)`, log-space for numerical stability) and returns a
`ViterbiResult` with the full state `path`, per-step `ViterbiStep` records and
`log_likelihood`. `forward_probability()` is also implemented for
likelihood-based checks.

**Where it runs.**
`VerifierAgent` (`core/agents/verifier.py`) converts each executed step into a
percept list (`percepts_from_step()`), runs Viterbi, stores the path as
`health_states`, and raises a **STATE_FLAKINESS** anomaly when the terminal
state is `stalled`, `render_failure` or `error`.

### 4.2 Kalman filter + adaptive latency tracking

`KalmanFilter(x, P, Q, R)` implements the classic predict/update pair:

```
predict:  x ← x,            P ← P + Q
update:   K ← P / (P + R),  x ← x + K(z − x),  P ← (1 − K)P
```

**Where it runs.** `LatencyTracker` wraps a Kalman filter over observed
action latencies to estimate the *true* response time while rejecting
outliers, then converts that estimate into a Playwright timeout clamped to
`[min_timeout_ms, max_timeout_ms]`. `BrowserEngine` holds one per session
(`engine.latency`), so the agent's timeouts adapt to how slow the app
actually is instead of being a hard-coded constant.

---

## 5. Machine learning — `core/algorithms/ml_models.py`

| Model | Implementation notes |
| --- | --- |
| `LogisticRegression` | batch gradient descent, sigmoid link, optional L2, `lr`/`epochs`/`l2`, keeps `loss_history` |
| `DecisionTree` | CART with Gini impurity, recursive `max_depth` / `min_samples_split` pruning, exposes `feature_importances_` |
| `KNNClassifier` | lazy learner, Euclidean distance, majority vote over `k` |
| `GaussianNaiveBayes` | per-class mean/variance with Laplace-style `epsilon` smoothing and log priors |
| `KMeans` | k-means++ seeding, `max_iter`/`tol` convergence, reports `inertia_` and `n_iter_` |
| `HierarchicalClustering` | agglomerative clustering with `single`/`complete`/`average` linkage and a `dendrogram_` |

Shared evaluation helpers: `accuracy_score`, `confusion_matrix`,
`precision_recall_f1`, `classification_report`.

**Where it runs.** `BugAnalyst` (`core/agents/analyst.py`) is a genuine
supervised pipeline:

* feature vectors are built from each anomaly (action kind, DOM-diff shape,
  network status, console errors, health states, …);
* a `DecisionTree(max_depth=6)` is fit on the labelled feature matrix to
  predict **severity** (`CRITICAL/HIGH/MEDIUM/LOW`);
* a `GaussianNaiveBayes` predicts the **root-cause class**
  (`NETWORK_API / FRONTEND_DOM / UI_STATE / LATENCY / STATE_FLAKINESS`);
* `KMeans(k=2…5)` clusters bug **fingerprints** for report deduplication, and
  the best `k` (by silhouette-style inertia elbow) is chosen automatically.

`LogisticRegression`, `KNNClassifier` and `HierarchicalClustering` are fully
implemented and covered by `tests/test_algorithms.py`; they are available to
the AI Lab for side-by-side comparison on the same datasets.

---

## 6. Reinforcement learning — `core/algorithms/rl_agent.py`

`GridWorldEnv` is a small deterministic MDP (default 5×5 with walls) exposing
`reset()`, `step(action)` and `observed_states`. Rewards are configurable
(`REWARDS`) and reward *progress*, not just the goal:

```
goal +100 · progress +10 · new_state +2 · repeat −5 · broken −25 · loop −15 · step −1
```

`QLearningAgent(actions, alpha, gamma, epsilon, epsilon_decay, epsilon_min, seed)`
is tabular Q-learning:

```
Q(s,a) ← Q(s,a) + α [ r + γ·max_a' Q(s',a') − Q(s,a) ]
```

with ε-greedy exploration decaying to `epsilon_min`, and `EpisodeStats`
tracking reward/length history per episode.

**Where it runs.** **AI Lab → RL** trains the agent live in the browser and
plots the reward curve; the same class backs the Q-policy experiments in
`tests/test_algorithms.py`.

---

## Where each algorithm sits in the pipeline

```
goal
 │
 ▼
PlannerAgent ──────────── search.py: A*, BFS, DFS, UCS, Greedy   (path discovery)
   │                      csp.py: synthesize_form_inputs         (valid form values)
   │                      optimization.py: GA fuzz inputs        (hostile inputs)
   ▼
BrowserAgent ──────────── probabilistic.py: LatencyTracker/Kalman (adaptive timeouts)
   │                      optimization.py: alpha-beta             (adversarial decisions)
   ▼
VerifierAgent ─────────── probabilistic.py: HMM + Viterbi         (hidden UI health)
   │                      vision.py (own PNG decode + MSE)        (pixel channel)
   ▼
BugAnalyst ────────────── ml_models.py: DecisionTree, NaiveBayes, KMeans
   ▼
SQLite / dashboard ────── rl_agent.py + all of the above in the AI Lab tab
```

## Runtime usage map

| Algorithm | Runtime consumer | Test coverage |
| --- | --- | --- |
| A\* / BFS / DFS / UCS / Greedy | `PlannerAgent.find_path`, AI Lab search tab | `test_algorithms.py::TestSearch*` |
| CSP backtracking + MRV/LCV/FC | AI Lab CSP tab (`synthesize_form_inputs`) | `test_algorithms.py::TestCSP*` |
| Genetic algorithm (`generate_fuzz_inputs`) | fuzz-input generator | `test_algorithms.py::TestGeneticAlgorithm` |
| Minimax + alpha–beta | `adversarial_ui_policy` | `test_algorithms.py::TestMinimax*` |
| HMM + Viterbi | `VerifierAgent.verify_step` (STATE_FLAKINESS) | `test_algorithms.py::TestHMM*` |
| Kalman / LatencyTracker | `BrowserEngine.latency` → Playwright timeouts | `test_algorithms.py::TestKalman*` |
| DecisionTree / NaiveBayes / KMeans | `BugAnalyst` (severity, root cause, dedupe) | `test_algorithms.py::TestMLModels` |
| LogisticRegression / KNN / Hierarchical | AI Lab comparisons | `test_algorithms.py::TestMLModels` |
| Q-Learning + GridWorldEnv | AI Lab RL tab | `test_algorithms.py::TestQLearning*` |

Every algorithm above is exercised by `tests/test_algorithms.py`
(58 assertions) and, for the ones on the critical path, by the live
Playwright integration suite as well.
