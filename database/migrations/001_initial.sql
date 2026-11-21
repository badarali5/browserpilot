CREATE TABLE IF NOT EXISTS test_runs (
    run_id TEXT PRIMARY KEY,
    user_id TEXT,
    goal TEXT NOT NULL,
    target_url TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    status TEXT NOT NULL,
    browser_config TEXT NOT NULL DEFAULT '{}',
    planner_config TEXT NOT NULL DEFAULT '{}',
    algorithm_config TEXT NOT NULL DEFAULT '{}',
    summary TEXT NOT NULL DEFAULT '{}',
    evidence_errors TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS test_steps (
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    action TEXT NOT NULL,
    action_arguments TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    observation TEXT NOT NULL DEFAULT '{}',
    verification_id TEXT,
    error_classification TEXT NOT NULL DEFAULT 'uncertain',
    error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, step_number),
    FOREIGN KEY (run_id) REFERENCES test_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verification_results (
    verification_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER,
    condition TEXT NOT NULL DEFAULT '',
    expected TEXT,
    actual TEXT,
    status TEXT NOT NULL,
    failure_type TEXT,
    error TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES test_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS defects (
    defect_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER,
    classification TEXT NOT NULL DEFAULT 'uncertain',
    observed_evidence TEXT NOT NULL DEFAULT '',
    inferred_cause TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT 'uncertain',
    FOREIGN KEY (run_id) REFERENCES test_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER,
    artifact_type TEXT NOT NULL,
    name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    collection_error TEXT,
    FOREIGN KEY (run_id) REFERENCES test_runs(run_id) ON DELETE CASCADE
);
