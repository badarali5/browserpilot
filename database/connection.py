from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator


SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_test_runs_started ON test_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_steps_run ON test_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
"""


def connect(database: str | Path) -> sqlite3.Connection:
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database: str | Path) -> None:
    connection = connect(database)
    try:
        for table_name in ("test_steps", "verification_results", "defects", "artifacts"):
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            if table_exists:
                foreign_tables = [
                    row["table"]
                    for row in connection.execute(
                        f"PRAGMA foreign_key_list({table_name})"
                    ).fetchall()
                ]
                if foreign_tables and "test_runs" not in foreign_tables:
                    connection.execute(
                        f"ALTER TABLE {table_name} RENAME TO {table_name}_m4_legacy"
                    )
                    connection.commit()
        test_runs_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='test_runs'"
        ).fetchone()
        if test_runs_exists:
            run_columns = {row["name"] for row in connection.execute("PRAGMA table_info(test_runs)").fetchall()}
            if "run_id" not in run_columns:
                connection.execute("ALTER TABLE test_runs RENAME TO test_runs_m4_legacy")
                test_steps_exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='test_steps'"
                ).fetchone()
                if test_steps_exists:
                    connection.execute("ALTER TABLE test_steps RENAME TO test_steps_m4_legacy")
                connection.commit()
        connection.executescript(SCHEMA)
        run_columns = {row["name"] for row in connection.execute("PRAGMA table_info(test_runs)").fetchall()}
        migrations = {
            "user_id": "ALTER TABLE test_runs ADD COLUMN user_id TEXT",
            "browser_config": "ALTER TABLE test_runs ADD COLUMN browser_config TEXT NOT NULL DEFAULT '{}'",
            "planner_config": "ALTER TABLE test_runs ADD COLUMN planner_config TEXT NOT NULL DEFAULT '{}'",
            "algorithm_config": "ALTER TABLE test_runs ADD COLUMN algorithm_config TEXT NOT NULL DEFAULT '{}'",
            "summary": "ALTER TABLE test_runs ADD COLUMN summary TEXT NOT NULL DEFAULT '{}'",
            "evidence_errors": "ALTER TABLE test_runs ADD COLUMN evidence_errors TEXT NOT NULL DEFAULT '[]'",
        }
        for name, statement in migrations.items():
            if name not in run_columns:
                connection.execute(statement)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_test_runs_user ON test_runs(user_id)")
        connection.commit()
    finally:
        connection.close()
