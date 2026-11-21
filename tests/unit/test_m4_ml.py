from algorithms.failure_ml import (
    FailureClassifier,
    kmeans_cluster,
    train_test_split,
)


def test_classifier_has_train_test_split_and_baseline_comparison():
    records = [
        {"title": "Timeout waiting for submit", "summary": "timeout", "category": "timeout"},
        {"title": "Selector missing submit", "summary": "element not found", "category": "element_not_found"},
        {"title": "Another timeout", "summary": "navigation timeout", "category": "timeout"},
        {"title": "Button missing", "summary": "element not found", "category": "element_not_found"},
    ]
    labels = [record["category"] for record in records]
    train_records, train_labels, test_records, test_labels = train_test_split(
        records, labels, test_fraction=0.5
    )
    classifier = FailureClassifier()
    classifier.fit(train_records, train_labels)
    metrics = classifier.evaluate(test_records, test_labels)
    assert 0 <= metrics["accuracy"] <= 1
    assert 0 <= metrics["baseline_accuracy"] <= 1
    assert metrics["test_samples"] == 2


def test_clustering_groups_persisted_failure_signatures():
    records = [
        {"title": "Element not found", "summary": "missing submit button"},
        {"title": "Element missing", "summary": "missing login button"},
        {"title": "Timeout", "summary": "page navigation timeout"},
        {"title": "Request timeout", "summary": "network timeout"},
    ]
    result = kmeans_cluster(records, k=2, seed=5)
    assert result["k"] == 2
    assert len(result["assignments"]) == len(records)
