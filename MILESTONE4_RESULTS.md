# Milestone 4 measured results

## Benchmark configuration

- Seed: `1729`
- Synthetic graph: 30 UI states
- GA: population 30, 20 generations, mutation 0.15, elitism 2
- BFS: unweighted minimum-hop search
- A*: weighted search with the explicitly zero-valued heuristic; no admissibility issue because it is admissible and weak

## Observed benchmark

| Algorithm | Nodes explored | Path length | Total cost | Runtime (s) | Goal/path result |
|---|---:|---:|---:|---:|---|
| BFS | 30 | 7 | 41.0 | 0.0000875 | reached |
| A* | 28 | 8 | 25.0 | 0.0001143 | reached |

The first run measured a GA initial best fitness of `18` and final best fitness of `20`
(new unique state discovery; higher is better). Runtime values vary by machine and were
measured once on the local run; re-run `py benchmark_m4.py` for current values.

## Persisted failure data

The database at `data/browserpilot.db` was queried directly. It contained `0` test runs,
`0` steps, `0` bug reports, and `0` search metrics at implementation time. Therefore:

- supervised classification was not reported as trained or as accurate;
- clustering returned no synthetic or invented records;
- the API exposes this fact through `GET /api/m4/failures/analysis`.

## Complexity

- BFS: `O(V + E)` time and `O(V)` space.
- A*: `O((V + E) log V)` for binary heap operations with one admissible heuristic check.
- CSP backtracking: worst-case exponential `O(d^n)`; forward checking reduces domains.
- GA: `O(g * p * (fitness + crossover + mutation))`.
- bag-of-tokens k-means: `O(iterations * k * n * v)`.
