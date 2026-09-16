#!/usr/bin/env python3
"""Tier C synthetic leakage Experiments A--C for Book 1 Project 1.

The protocol is predeclared in research/foundations-pass-08.org. Experimental
scores are outputs, never pass/fail thresholds. Tests cover split/availability/
deduplication invariants so the implementation cannot satisfy the hypotheses by
quietly changing the protocol after observing results.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline

SEED = 1729
NEAR_DUPLICATE_THRESHOLD = 0.80
HERE = Path(__file__).resolve().parent
PLOT_NAMES = {
    "A": "leakage-a-entity-split.svg",
    "B": "leakage-b-temporal-availability.svg",
    "C": "leakage-c-duplicates.svg",
}
NON_ALNUM = re.compile(r"[^0-9a-z]+")
WHITESPACE = re.compile(r"\s+")


def fit_text_classifier(texts: list[str], labels: list[int]) -> Pipeline:
    model = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1),
            ),
            (
                "classifier",
                LogisticRegression(
                    C=1.0,
                    max_iter=1000,
                    solver="liblinear",
                    random_state=SEED,
                ),
            ),
        ]
    )
    model.fit(texts, labels)
    return model


def class_balance(rows: list[dict[str, Any]], indices: Iterable[int]) -> dict[str, int]:
    values = [rows[index]["label"] for index in indices]
    return {"0": values.count(0), "1": values.count(1)}


def evaluate_text_split(
    rows: list[dict[str, Any]],
    train: list[int],
    test: list[int],
    *,
    text_fn,
) -> dict[str, Any]:
    train_texts = [text_fn(rows[index]) for index in train]
    test_texts = [text_fn(rows[index]) for index in test]
    train_labels = [rows[index]["label"] for index in train]
    test_labels = [rows[index]["label"] for index in test]
    model = fit_text_classifier(train_texts, train_labels)
    predictions = model.predict(test_texts)
    return {
        "balanced_accuracy": float(balanced_accuracy_score(test_labels, predictions)),
        "accuracy": float(accuracy_score(test_labels, predictions)),
        "train_size": len(train),
        "test_size": len(test),
        "train_class_balance": class_balance(rows, train),
        "test_class_balance": class_balance(rows, test),
        "vocabulary_size": len(model.named_steps["tfidf"].vocabulary_),
    }


# Experiment A -----------------------------------------------------------------

def generate_entity_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity_index in range(160):
        entity_id = f"entity-{entity_index:03d}"
        label = entity_index % 2
        signature = f"entity_signature_{entity_index:03d}"
        for observation in range(4):
            rows.append(
                {
                    "record_id": f"entity-{entity_index:03d}-obs-{observation}",
                    "entity_id": entity_id,
                    "label": label,
                    "text": (
                        f"investigation record {signature} neutral observation_{observation} "
                        "public source routine note"
                    ),
                }
            )
    return rows


def row_random_split(rows: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    indices = list(range(len(rows)))
    labels = [row["label"] for row in rows]
    train, test = train_test_split(
        indices,
        test_size=0.25,
        random_state=SEED,
        stratify=labels,
    )
    return sorted(map(int, train)), sorted(map(int, test))


def entity_group_split(rows: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    indices = list(range(len(rows)))
    groups = [row["entity_id"] for row in rows]
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED)
    train, test = next(splitter.split(indices, [row["label"] for row in rows], groups))
    return sorted(map(int, train)), sorted(map(int, test))


def entity_contamination(
    rows: list[dict[str, Any]], train: list[int], test: list[int]
) -> dict[str, Any]:
    train_entities = {rows[index]["entity_id"] for index in train}
    test_entities = {rows[index]["entity_id"] for index in test}
    overlap = train_entities & test_entities
    contaminated_test_rows = sum(
        1 for index in test if rows[index]["entity_id"] in train_entities
    )
    return {
        "overlap_entity_count": len(overlap),
        "test_entity_contamination_rate": contaminated_test_rows / len(test),
    }


def run_experiment_a() -> dict[str, Any]:
    rows = generate_entity_fixture()
    random_train, random_test = row_random_split(rows)
    group_train, group_test = entity_group_split(rows)
    return {
        "status": "TESTED",
        "protocol": "row-random versus entity-group split",
        "row_random": {
            **evaluate_text_split(
                rows, random_train, random_test, text_fn=lambda row: row["text"]
            ),
            "contamination": entity_contamination(rows, random_train, random_test),
        },
        "entity_group": {
            **evaluate_text_split(
                rows, group_train, group_test, text_fn=lambda row: row["text"]
            ),
            "contamination": entity_contamination(rows, group_train, group_test),
        },
    }


# Experiment B -----------------------------------------------------------------

def generate_temporal_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for month in range(1, 25):
        observed_at = f"2024-{month:02d}-01T00:00:00Z" if month <= 12 else f"2025-{month - 12:02d}-01T00:00:00Z"
        # Lexicographically sortable YYYY-MM-DD timestamps are enough for this frozen fixture.
        year = 2024 if month <= 12 else 2025
        real_month = month if month <= 12 else month - 12
        available_day = 8
        future_available = f"{year:04d}-{real_month:02d}-{available_day:02d}T00:00:00Z"
        for item in range(24):
            label = item % 2
            ordinal = (month - 1) * 24 + item
            stable = label if ordinal % 4 != 0 else 1 - label
            rows.append(
                {
                    "record_id": f"time-{month:02d}-{item:02d}",
                    "month": month,
                    "observed_at": observed_at,
                    "prediction_at": observed_at,
                    "label": label,
                    "stable_signal": stable,
                    "future_resolution": label,
                    "future_resolution_available_at": future_available,
                }
            )
    return rows


def temporal_split(rows: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    train = [index for index, row in enumerate(rows) if row["month"] <= 18]
    test = [index for index, row in enumerate(rows) if row["month"] >= 19]
    return train, test


def temporal_text(row: dict[str, Any], *, point_in_time: bool) -> str:
    parts = ["investigation temporal record", f"stable_signal_{row['stable_signal']}"]
    if not point_in_time or row["future_resolution_available_at"] <= row["prediction_at"]:
        parts.append(f"future_resolution_{row['future_resolution']}")
    return " ".join(parts)


def run_experiment_b() -> dict[str, Any]:
    rows = generate_temporal_fixture()
    random_train, random_test = row_random_split(rows)
    temporal_train, temporal_test = temporal_split(rows)
    temporal_invariant = max(rows[index]["observed_at"] for index in temporal_train) < min(
        rows[index]["observed_at"] for index in temporal_test
    )
    return {
        "status": "TESTED",
        "protocol": "finalized random/temporal baselines versus temporal point-in-time features",
        "temporal_train_before_test": temporal_invariant,
        "random_finalized": evaluate_text_split(
            rows,
            random_train,
            random_test,
            text_fn=lambda row: temporal_text(row, point_in_time=False),
        ),
        "temporal_finalized": evaluate_text_split(
            rows,
            temporal_train,
            temporal_test,
            text_fn=lambda row: temporal_text(row, point_in_time=False),
        ),
        "temporal_point_in_time": evaluate_text_split(
            rows,
            temporal_train,
            temporal_test,
            text_fn=lambda row: temporal_text(row, point_in_time=True),
        ),
        "future_resolution_emitted_point_in_time": any(
            "future_resolution_" in temporal_text(row, point_in_time=True) for row in rows
        ),
    }


# Experiment C -----------------------------------------------------------------

def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = NON_ALNUM.sub(" ", normalized)
    return WHITESPACE.sub(" ", normalized).strip()


def exact_text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def token_set(text: str) -> set[str]:
    normalized = normalize_text(text)
    return set(normalized.split()) if normalized else set()


def token_jaccard(left: str, right: str) -> float:
    a = token_set(left)
    b = token_set(right)
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def is_near_duplicate(left: str, right: str) -> bool:
    return token_jaccard(left, right) >= NEAR_DUPLICATE_THRESHOLD


def duplicate_base_text(base_index: int, marker: str) -> str:
    unique = " ".join(f"b{base_index:03d}{suffix}" for suffix in "abcde")
    return (
        "investigation report public record source neutral evidence observation stable "
        f"{unique} {marker}"
    )


def generate_duplicate_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for base_index in range(160):
        label = base_index % 2
        original = duplicate_base_text(base_index, "markerone")
        near = duplicate_base_text(base_index, "markertwo")
        for variant, text in (
            ("original", original),
            ("exact", original),
            ("near", near),
        ):
            rows.append(
                {
                    "record_id": f"dup-{base_index:03d}-{variant}",
                    "base_id": f"base-{base_index:03d}",
                    "variant": variant,
                    "label": label,
                    "text": text,
                }
            )
    return rows


def near_duplicate_components(rows: list[dict[str, Any]]) -> dict[str, str]:
    ids = [row["record_id"] for row in rows]
    parent = {record_id: record_id for record_id in ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        a = find(left)
        b = find(right)
        if a == b:
            return
        low, high = sorted((a, b))
        parent[high] = low

    token_sets = [token_set(row["text"]) for row in rows]
    for left_index in range(len(rows)):
        left_tokens = token_sets[left_index]
        for right_index in range(left_index + 1, len(rows)):
            right_tokens = token_sets[right_index]
            union_tokens = left_tokens | right_tokens
            similarity = (
                len(left_tokens & right_tokens) / len(union_tokens)
                if union_tokens
                else 1.0
            )
            if similarity >= NEAR_DUPLICATE_THRESHOLD:
                union(ids[left_index], ids[right_index])

    members: dict[str, list[str]] = {}
    for record_id in ids:
        members.setdefault(find(record_id), []).append(record_id)
    canonical: dict[str, str] = {}
    for values in members.values():
        component_id = min(values)
        for record_id in values:
            canonical[record_id] = component_id
    return canonical


def duplicate_cluster_split(
    rows: list[dict[str, Any]],
) -> tuple[list[int], list[int], dict[str, str]]:
    components = near_duplicate_components(rows)
    indices = list(range(len(rows)))
    groups = [components[row["record_id"]] for row in rows]
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED)
    train, test = next(splitter.split(indices, [row["label"] for row in rows], groups))
    return sorted(map(int, train)), sorted(map(int, test)), components


def duplicate_contamination(
    rows: list[dict[str, Any]],
    train: list[int],
    test: list[int],
    components: dict[str, str],
) -> dict[str, Any]:
    train_hashes = {exact_text_hash(rows[index]["text"]) for index in train}
    test_hashes = {exact_text_hash(rows[index]["text"]) for index in test}
    train_components = {components[rows[index]["record_id"]] for index in train}
    test_components = {components[rows[index]["record_id"]] for index in test}
    exact_contaminated = sum(
        1 for index in test if exact_text_hash(rows[index]["text"]) in train_hashes
    )
    near_contaminated = sum(
        1
        for index in test
        if components[rows[index]["record_id"]] in train_components
    )
    return {
        "exact_hash_overlap_count": len(train_hashes & test_hashes),
        "near_component_overlap_count": len(train_components & test_components),
        "exact_test_contamination_rate": exact_contaminated / len(test),
        "near_test_contamination_rate": near_contaminated / len(test),
    }


def run_experiment_c() -> dict[str, Any]:
    rows = generate_duplicate_fixture()
    components = near_duplicate_components(rows)
    random_train, random_test = row_random_split(rows)
    clean_train, clean_test, clean_components = duplicate_cluster_split(rows)
    return {
        "status": "TESTED",
        "protocol": "row-random versus frozen near-duplicate-component split",
        "near_duplicate_threshold": NEAR_DUPLICATE_THRESHOLD,
        "row_random": {
            **evaluate_text_split(
                rows, random_train, random_test, text_fn=lambda row: row["text"]
            ),
            "contamination": duplicate_contamination(
                rows, random_train, random_test, components
            ),
        },
        "duplicate_cluster": {
            **evaluate_text_split(
                rows, clean_train, clean_test, text_fn=lambda row: row["text"]
            ),
            "contamination": duplicate_contamination(
                rows, clean_train, clean_test, clean_components
            ),
        },
        "component_count": len(set(components.values())),
    }


def plot_scores(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    definitions = {
        "A": [
            ("row random", result["experiments"]["A"]["row_random"]["balanced_accuracy"]),
            ("entity group", result["experiments"]["A"]["entity_group"]["balanced_accuracy"]),
        ],
        "B": [
            ("random finalized", result["experiments"]["B"]["random_finalized"]["balanced_accuracy"]),
            ("temporal finalized", result["experiments"]["B"]["temporal_finalized"]["balanced_accuracy"]),
            ("temporal point-in-time", result["experiments"]["B"]["temporal_point_in_time"]["balanced_accuracy"]),
        ],
        "C": [
            ("row random", result["experiments"]["C"]["row_random"]["balanced_accuracy"]),
            ("duplicate cluster", result["experiments"]["C"]["duplicate_cluster"]["balanced_accuracy"]),
        ],
    }
    titles = {
        "A": "Experiment A: repeated-entity leakage",
        "B": "Experiment B: temporal feature availability",
        "C": "Experiment C: duplicate leakage",
    }
    for name, values in definitions.items():
        labels = [label for label, _ in values]
        scores = [score for _, score in values]
        fig, axis = plt.subplots(figsize=(7.5, 4.5))
        bars = axis.bar(labels, scores)
        axis.set_ylim(0.0, 1.05)
        axis.set_ylabel("Balanced accuracy")
        axis.set_title(titles[name])
        axis.bar_label(bars, fmt="%.3f", padding=3)
        fig.tight_layout()
        fig.savefig(output_dir / PLOT_NAMES[name], format="svg", metadata={"Date": None})
        plt.close(fig)


def run_all(output_dir: Path, *, render_plots: bool = True) -> dict[str, Any]:
    result = {
        "protocol_version": "leakage-v1",
        "status": "TESTED",
        "seed": SEED,
        "versions": {
            "scikit_learn": sklearn.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "experiments": {
            "A": run_experiment_a(),
            "B": run_experiment_b(),
            "C": run_experiment_c(),
        },
        "plot_paths": dict(PLOT_NAMES),
        "interpretation_guard": (
            "Scores are measurements on deterministic synthetic controls, not estimates of production StarIntel model quality."
        ),
    }
    if render_plots:
        plot_scores(result, output_dir)
    return result


def main() -> int:
    output_dir = HERE / "artifacts" / "leakage"
    result = run_all(output_dir, render_plots=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.joinpath("results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
