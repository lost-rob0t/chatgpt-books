#!/usr/bin/env python3
"""Predeclared larger-public-corpus benchmark for Project 1 candidate generation.

The source corpus is scikit-learn 1.9.0's pinned 20 Newsgroups "by date"
archive.  Raw posts are downloaded at execution time and are never written into
the repository or benchmark artifact.  Selection is content-defined so the
benchmark does not depend on loader ordering.

The public corpus supplies realistic text.  A bounded set of deterministic
one-token variants supplies known near-duplicate stress cases.  Those variants
are controlled benchmark data, not claims about naturally occurring duplicate
labels in 20 Newsgroups.
"""

from __future__ import annotations

import hashlib
import json
import platform
import time
import tracemalloc
from dataclasses import asdict, dataclass
from importlib.metadata import version
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sklearn.datasets import fetch_20newsgroups

from near_duplicate_candidates import (
    CandidateConfig,
    generate_candidate_pairs,
    verified_duplicate_components,
)
from run_leakage_experiments import token_set


SOURCE_NAME = "20 Newsgroups by date"
SOURCE_URL = "https://ndownloader.figshare.com/files/5975967"
SOURCE_ARCHIVE_SHA256 = "8f1b2514ca22a5ade8fbb9cfa5727df95fa587f4c87b786e15c759fa66d95610"
SOURCE_TOTAL_DOCUMENTS = 18_846
SOURCE_SKLEARN_VERSION = "1.9.0"

THRESHOLD = 0.80
SEED = 1729
SCHEME = "affine32"
BLOCK_KEYS_PER_RECORD = 2
NUM_PERM_GRID = (64, 128, 256)
PUBLIC_ORIGINAL_COUNT = 1_200
CONTROLLED_VARIANT_COUNT = 200
MIN_TOKEN_COUNT = 20
VARIANT_PREFIX = "benchmarkvariant"
PROTOCOL_VERSION = "20newsgroups-content-hash-v1"


@dataclass(frozen=True)
class PublicCorpusPolicy:
    original_count: int = PUBLIC_ORIGINAL_COUNT
    controlled_variant_count: int = CONTROLLED_VARIANT_COUNT
    min_token_count: int = MIN_TOKEN_COUNT


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "record_id": str(row["record_id"]),
            "source_sha256": str(row["source_sha256"]),
            "kind": str(row["kind"]),
        }
        for row in rows
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def select_public_rows(
    texts: Iterable[str],
    *,
    policy: PublicCorpusPolicy = PublicCorpusPolicy(),
) -> list[dict[str, Any]]:
    """Select unique public texts by content hash, independent of input order."""
    if policy.original_count <= 0:
        raise ValueError("original_count must be positive")
    if not 0 <= policy.controlled_variant_count <= policy.original_count:
        raise ValueError("controlled_variant_count must be between 0 and original_count")
    if policy.min_token_count < 1:
        raise ValueError("min_token_count must be positive")

    unique: dict[str, str] = {}
    for text in texts:
        if not isinstance(text, str):
            raise ValueError("public corpus entries must be strings")
        if len(token_set(text)) < policy.min_token_count:
            continue
        digest = _text_sha256(text)
        unique.setdefault(digest, text)

    selected = sorted(unique.items())[: policy.original_count]
    if len(selected) != policy.original_count:
        raise ValueError(
            f"public corpus supplied only {len(selected)} eligible unique texts; "
            f"need {policy.original_count}"
        )

    rows: list[dict[str, Any]] = []
    for digest, text in selected:
        rows.append(
            {
                "record_id": f"public-{digest}",
                "source_sha256": digest,
                "kind": "public-original",
                "text": text,
            }
        )

    for ordinal, original in enumerate(rows[: policy.controlled_variant_count]):
        marker = f"{VARIANT_PREFIX}{ordinal:04d}"
        variant_text = f"{original['text']}\n{marker}"
        original_tokens = token_set(str(original["text"]))
        variant_tokens = token_set(variant_text)
        union = original_tokens | variant_tokens
        similarity = len(original_tokens & variant_tokens) / len(union)
        if similarity < THRESHOLD:
            raise AssertionError("controlled variant fell below frozen duplicate threshold")
        rows.append(
            {
                "record_id": f"variant-{ordinal:04d}-{original['source_sha256']}",
                "source_sha256": str(original["source_sha256"]),
                "kind": "controlled-near-duplicate",
                "text": variant_text,
                "derived_from": str(original["record_id"]),
                "control_jaccard": similarity,
            }
        )
    return rows


def exact_oracle_pairs(
    rows: Sequence[Mapping[str, Any]],
    *,
    threshold: float = THRESHOLD,
) -> list[tuple[str, str]]:
    """Exact all-pairs oracle using one precomputed token set per record."""
    prepared = [
        (str(row["record_id"]), token_set(str(row["text"])))
        for row in sorted(rows, key=lambda item: str(item["record_id"]))
    ]
    qualifying: list[tuple[str, str]] = []
    for (left_id, left_tokens), (right_id, right_tokens) in combinations(prepared, 2):
        union = left_tokens | right_tokens
        similarity = len(left_tokens & right_tokens) / len(union) if union else 1.0
        if similarity >= threshold:
            qualifying.append((left_id, right_id))
    return qualifying


def _components(record_ids: Iterable[str], pairs: Iterable[tuple[str, str]]) -> dict[str, str]:
    ids = sorted(set(record_ids))
    parent = {record_id: record_id for record_id in ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        parent[high] = low

    for left, right in sorted(set(pairs)):
        union(left, right)

    groups: dict[str, list[str]] = {}
    for record_id in ids:
        groups.setdefault(find(record_id), []).append(record_id)
    result: dict[str, str] = {}
    for members in groups.values():
        component_id = min(members)
        for record_id in members:
            result[record_id] = component_id
    return result


def evaluate_grid(
    rows: Sequence[Mapping[str, Any]],
    *,
    num_perm_grid: Sequence[int] = NUM_PERM_GRID,
) -> dict[str, Any]:
    """Evaluate the frozen candidate policy without tuning after observation."""
    if tuple(num_perm_grid) != NUM_PERM_GRID:
        raise ValueError("benchmark num_perm grid is frozen by protocol")

    oracle_started = time.perf_counter()
    oracle_pairs = exact_oracle_pairs(rows)
    oracle_seconds = time.perf_counter() - oracle_started
    oracle_set = set(oracle_pairs)
    oracle_components = _components((str(row["record_id"]) for row in rows), oracle_pairs)
    all_pair_count = len(rows) * (len(rows) - 1) // 2

    results: list[dict[str, Any]] = []
    for num_perm in num_perm_grid:
        config = CandidateConfig(
            threshold=THRESHOLD,
            num_perm=int(num_perm),
            seed=SEED,
            scheme=SCHEME,
            block_keys_per_record=BLOCK_KEYS_PER_RECORD,
        )
        tracemalloc.start()
        started = time.perf_counter()
        candidate = generate_candidate_pairs(rows, config=config)
        candidate_seconds = time.perf_counter() - started
        _current, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        candidate_pairs = candidate["pairs"]
        candidate_set = set(candidate_pairs)
        components, verified_pairs = verified_duplicate_components(
            rows, candidate_pairs, threshold=THRESHOLD
        )
        source_map = candidate["pair_sources"]
        lsh_qualifying = sum(
            1
            for pair in oracle_set
            if pair in source_map and "minhash-lsh" in source_map[pair]
        )
        block_qualifying = sum(
            1 for pair in oracle_set if pair in source_map and "block" in source_map[pair]
        )
        exact_hash_qualifying = sum(
            1 for pair in oracle_set if pair in source_map and "exact-hash" in source_map[pair]
        )
        qualifying_proposed = len(oracle_set & candidate_set)
        denominator = len(oracle_set)
        results.append(
            {
                "num_perm": int(num_perm),
                "candidate_pair_count": len(candidate_pairs),
                "pair_reduction_fraction": (
                    1.0 - len(candidate_pairs) / all_pair_count if all_pair_count else 0.0
                ),
                "qualifying_pairs_proposed": qualifying_proposed,
                "qualifying_pair_recall": (
                    qualifying_proposed / denominator if denominator else 1.0
                ),
                "minhash_lsh_qualifying_pair_recall": (
                    lsh_qualifying / denominator if denominator else 1.0
                ),
                "block_qualifying_pair_recall": (
                    block_qualifying / denominator if denominator else 1.0
                ),
                "exact_hash_qualifying_pair_recall": (
                    exact_hash_qualifying / denominator if denominator else 1.0
                ),
                "false_positive_candidate_count": len(candidate_set - oracle_set),
                "verified_pair_count": len(verified_pairs),
                "component_equality": components == oracle_components,
                "candidate_seconds": candidate_seconds,
                "python_traced_peak_bytes": peak_bytes,
                "parameters": candidate["parameters"],
            }
        )

    return {
        "status": "TESTED",
        "protocol_version": PROTOCOL_VERSION,
        "record_count": len(rows),
        "all_pair_count": all_pair_count,
        "exact_qualifying_pair_count": len(oracle_pairs),
        "exact_oracle_seconds": oracle_seconds,
        "grid": results,
    }


def load_public_corpus() -> list[str]:
    """Load the exact pinned scikit-learn 1.9.0 public corpus."""
    if version("scikit-learn") != SOURCE_SKLEARN_VERSION:
        raise RuntimeError(
            f"benchmark requires scikit-learn {SOURCE_SKLEARN_VERSION}; "
            f"installed {version('scikit-learn')}"
        )
    data = fetch_20newsgroups(subset="all", shuffle=False, remove=())
    texts = list(data.data)
    if len(texts) != SOURCE_TOTAL_DOCUMENTS:
        raise RuntimeError(
            f"expected {SOURCE_TOTAL_DOCUMENTS} documents, observed {len(texts)}"
        )
    return texts


def run_public_benchmark() -> dict[str, Any]:
    policy = PublicCorpusPolicy()
    texts = load_public_corpus()
    rows = select_public_rows(texts, policy=policy)
    result = evaluate_grid(rows)
    result.update(
        {
            "source": {
                "name": SOURCE_NAME,
                "url": SOURCE_URL,
                "archive_sha256_from_sklearn_1_9_0_source": SOURCE_ARCHIVE_SHA256,
                "source_document_count": len(texts),
                "raw_corpus_committed": False,
            },
            "selection": {
                **asdict(policy),
                "selected_record_count": len(rows),
                "selected_manifest_sha256": _manifest_sha256(rows),
                "controlled_variants_are_labels_for_natural_duplicates": False,
                "selection_uses_target_labels": False,
            },
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "scikit_learn": version("scikit-learn"),
                "datasketch": version("datasketch"),
            },
        }
    )
    return result


def write_result(result: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
