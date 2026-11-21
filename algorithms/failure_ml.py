"""Classification and clustering for persisted BrowserPilot failures."""

from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def load_persisted_failures(database: str | Path) -> list[dict[str, Any]]:
    """Load real bug reports and failed steps; never creates synthetic records."""
    connection = sqlite3.connect(str(database))
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT br.category, br.title, br.summary, br.root_cause,
                   br.fingerprint, br.console_errors, br.evidence,
                   s.action, s.error, s.url_before, s.url_after
            FROM bug_reports br
            LEFT JOIN steps s ON s.run_id = br.run_id
            WHERE br.category IS NOT NULL OR s.ok = 0
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _text(record: dict[str, Any]) -> str:
    return " ".join(str(record.get(key, "") or "") for key in (
        "category", "title", "summary", "root_cause", "fingerprint",
        "console_errors", "evidence", "action", "error", "url_before", "url_after",
    ))


def _vector(text: str, vocabulary: dict[str, int]) -> list[float]:
    counts = Counter(TOKEN_PATTERN.findall(text.lower()))
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return [counts[token] / norm for token in vocabulary]


class FailureClassifier:
    """Leakage-safe hash-bag nearest centroid classifier with majority baseline."""

    def __init__(self) -> None:
        self.vocabulary: dict[str, int] = {}
        self.centroids: dict[str, list[float]] = {}
        self.baseline = ""

    def fit(self, records: Sequence[dict[str, Any]], labels: Sequence[str]) -> None:
        if len(records) != len(labels):
            raise ValueError("records and labels must have equal length.")
        if not records:
            raise ValueError("Classifier requires persisted training records.")

        token_set: set[str] = set()
        for record in records:
            token_set.update(TOKEN_PATTERN.findall(_text(record).lower()))
        self.vocabulary = {token: index for index, token in enumerate(sorted(token_set))}

        vectors = [_vector(_text(record), self.vocabulary) for record in records]
        sums: dict[str, list[float]] = {}
        counts: dict[str, int] = {}
        for label, vector in zip(labels, vectors):
            sums.setdefault(label, [0.0] * len(self.vocabulary))
            counts[label] = counts.get(label, 0) + 1
            for index, value in enumerate(vector):
                sums[label][index] += value
        self.centroids = {
            label: [value / counts[label] for value in vector]
            for label, vector in sums.items()
        }
        self.baseline = Counter(labels).most_common(1)[0][0]

    def predict(self, record: dict[str, Any]) -> str:
        if not self.centroids:
            raise RuntimeError("Classifier is not fitted.")
        vector = _vector(_text(record), self.vocabulary)

        def cosine(left: list[float], right: list[float]) -> float:
            dot = sum(a * b for a, b in zip(left, right))
            left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
            right_norm = math.sqrt(sum(a * a for a in right)) or 1.0
            return dot / (left_norm * right_norm)

        return max(self.centroids, key=lambda label: cosine(vector, self.centroids[label]))

    def evaluate(self, records: Sequence[dict[str, Any]], labels: Sequence[str]) -> dict[str, float]:
        predictions = [self.predict(record) for record in records]
        accuracy = sum(p == y for p, y in zip(predictions, labels)) / len(labels) if labels else 0.0
        baseline_accuracy = sum(self.baseline == y for y in labels) / len(labels) if labels else 0.0
        return {"accuracy": accuracy, "baseline_accuracy": baseline_accuracy,
                "test_samples": float(len(labels))}


def train_test_split(
    records: Sequence[dict[str, Any]],
    labels: Sequence[str],
    *,
    test_fraction: float = 0.25,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], list[str]]:
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1.")
    if len(records) != len(labels):
        raise ValueError("records and labels must have equal length.")
    split = max(1, int(len(records) * (1 - test_fraction)))
    return list(records[:split]), list(labels[:split]), list(records[split:]), list(labels[split:])


def kmeans_cluster(records: Sequence[dict[str, Any]], k: int = 3, iterations: int = 20,
                   seed: int = 0) -> dict[str, Any]:
    """Deterministic bag-of-tokens k-means for recurring persisted signatures."""
    if not records:
        return {"assignments": [], "centroids": [], "clusters": []}
    token_set: set[str] = set()
    for record in records:
        token_set.update(TOKEN_PATTERN.findall(_text(record).lower()))
    vocabulary = {token: index for index, token in enumerate(sorted(token_set))}
    vectors = [_vector(_text(record), vocabulary) for record in records]
    k = max(1, min(k, len(vectors)))
    import random
    randomizer = random.Random(seed)
    indices = randomizer.sample(range(len(vectors)), k)
    centroids = [vectors[index][:] for index in indices]
    assignments = [0] * len(vectors)

    def distance(left: list[float], right: list[float]) -> float:
        return sum((a - b) ** 2 for a, b in zip(left, right))

    for _ in range(iterations):
        new_assignments = [
            min(range(k), key=lambda cluster: distance(vector, centroids[cluster]))
            for vector in vectors
        ]
        if new_assignments == assignments:
            break
        assignments = new_assignments
        for cluster in range(k):
            members = [vectors[i] for i, value in enumerate(assignments) if value == cluster]
            if members:
                centroids[cluster] = [
                    sum(vector[index] for vector in members) / len(members)
                    for index in range(len(vectors[0]))
                ]

    clusters = [
        [i for i, assigned in enumerate(assignments) if assigned == cluster]
        for cluster in range(k)
    ]
    return {"assignments": assignments, "centroids": centroids, "clusters": clusters,
            "seed": seed, "k": k}
