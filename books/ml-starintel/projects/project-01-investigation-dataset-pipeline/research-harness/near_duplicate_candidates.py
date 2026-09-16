#!/usr/bin/env python3
"""Scalable near-duplicate candidate generation for Project 1 research.

Candidate generation is deliberately weaker than duplicate truth.  Exact
normalized-token Jaccard verification remains authoritative before any edge can
enter duplicate-component closure.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from importlib.metadata import version
from itertools import combinations
from typing import Any, Iterable, Mapping, Sequence

from datasketch import MinHash, MinHashLSH

from run_leakage_experiments import exact_text_hash, token_jaccard, token_set


Pair = tuple[str, str]
NORMALIZATION_VERSION = "experiment-c-nfkc-casefold-nonalnum-v1"


@dataclass(frozen=True)
class CandidateConfig:
    threshold: float = 0.80
    num_perm: int = 128
    seed: int = 1729
    scheme: str = "affine32"
    block_keys_per_record: int = 2


DEFAULT_CONFIG = CandidateConfig()


def canonical_pair(left: str, right: str) -> Pair:
    if left == right:
        raise ValueError("candidate pair requires two distinct record IDs")
    return (left, right) if left < right else (right, left)


def _validated_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        record_id = row.get("record_id")
        text = row.get("text")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("every row requires a non-empty string record_id")
        if record_id in by_id:
            raise ValueError(f"duplicate record_id: {record_id}")
        if not isinstance(text, str):
            raise ValueError(f"record {record_id} requires string text")
        by_id[record_id] = row
    return by_id


def _add_bucket_pairs(
    buckets: Mapping[str, list[str]],
    source: str,
    pair_sources: dict[Pair, set[str]],
) -> None:
    for bucket_key in sorted(buckets):
        record_ids = sorted(set(buckets[bucket_key]))
        for left, right in combinations(record_ids, 2):
            pair_sources[canonical_pair(left, right)].add(source)


def _exact_hash_candidates(
    by_id: Mapping[str, Mapping[str, Any]],
    pair_sources: dict[Pair, set[str]],
) -> None:
    buckets: dict[str, list[str]] = defaultdict(list)
    for record_id in sorted(by_id):
        buckets[exact_text_hash(str(by_id[record_id]["text"]))].append(record_id)
    _add_bucket_pairs(buckets, "exact-hash", pair_sources)


def _rare_token_block_candidates(
    by_id: Mapping[str, Mapping[str, Any]],
    pair_sources: dict[Pair, set[str]],
    *,
    keys_per_record: int,
) -> None:
    if keys_per_record < 0:
        raise ValueError("block_keys_per_record must be >= 0")
    if keys_per_record == 0:
        return

    tokens_by_id = {
        record_id: token_set(str(by_id[record_id]["text"]))
        for record_id in sorted(by_id)
    }
    document_frequency: Counter[str] = Counter()
    for tokens in tokens_by_id.values():
        document_frequency.update(tokens)

    buckets: dict[str, list[str]] = defaultdict(list)
    for record_id in sorted(tokens_by_id):
        ranked = sorted(
            tokens_by_id[record_id],
            key=lambda token: (document_frequency[token], token),
        )
        for token in ranked[:keys_per_record]:
            buckets[token].append(record_id)
    _add_bucket_pairs(buckets, "block", pair_sources)


def _minhash_lsh_candidates(
    by_id: Mapping[str, Mapping[str, Any]],
    pair_sources: dict[Pair, set[str]],
    *,
    config: CandidateConfig,
) -> dict[str, int]:
    signatures: dict[str, MinHash] = {}
    for record_id in sorted(by_id):
        signature = MinHash(
            num_perm=config.num_perm,
            seed=config.seed,
            scheme=config.scheme,
        )
        for token in sorted(token_set(str(by_id[record_id]["text"]))):
            signature.update(token.encode("utf-8"))
        signatures[record_id] = signature

    index = MinHashLSH(threshold=config.threshold, num_perm=config.num_perm)
    for record_id in sorted(signatures):
        index.insert(record_id, signatures[record_id])

    for record_id in sorted(signatures):
        for candidate_id in sorted(index.query(signatures[record_id])):
            if candidate_id == record_id:
                continue
            pair_sources[canonical_pair(record_id, str(candidate_id))].add("minhash-lsh")

    return {"bands": int(index.b), "rows_per_band": int(index.r)}


def generate_candidate_pairs(
    rows: Sequence[Mapping[str, Any]],
    *,
    config: CandidateConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Return deterministic canonical candidate pairs and source provenance."""
    if not 0.0 < config.threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    if config.num_perm <= 0:
        raise ValueError("num_perm must be positive")

    by_id = _validated_rows(rows)
    pair_sources: dict[Pair, set[str]] = defaultdict(set)
    _exact_hash_candidates(by_id, pair_sources)
    _rare_token_block_candidates(
        by_id,
        pair_sources,
        keys_per_record=config.block_keys_per_record,
    )
    lsh_parameters = _minhash_lsh_candidates(
        by_id,
        pair_sources,
        config=config,
    )

    pairs = sorted(pair_sources)
    frozen_sources = {pair: tuple(sorted(pair_sources[pair])) for pair in pairs}
    return {
        "pairs": pairs,
        "pair_sources": frozen_sources,
        "parameters": {
            "datasketch_version": version("datasketch"),
            "normalization_version": NORMALIZATION_VERSION,
            "threshold": config.threshold,
            "num_perm": config.num_perm,
            "seed": config.seed,
            "scheme": config.scheme,
            "block_keys_per_record": config.block_keys_per_record,
            "bands": lsh_parameters["bands"],
            "rows_per_band": lsh_parameters["rows_per_band"],
        },
    }


def _components_from_pairs(record_ids: Iterable[str], pairs: Iterable[Pair]) -> dict[str, str]:
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
        if left not in parent or right not in parent:
            raise ValueError("candidate pair references an unknown record ID")
        union(left, right)

    members: dict[str, list[str]] = defaultdict(list)
    for record_id in ids:
        members[find(record_id)].append(record_id)

    result: dict[str, str] = {}
    for values in members.values():
        component_id = min(values)
        for record_id in values:
            result[record_id] = component_id
    return result


def verified_duplicate_components(
    rows: Sequence[Mapping[str, Any]],
    candidate_pairs: Iterable[Pair],
    *,
    threshold: float,
) -> tuple[dict[str, str], list[Pair]]:
    """Verify candidates exactly before building duplicate components."""
    by_id = _validated_rows(rows)
    verified: list[Pair] = []
    for left, right in sorted(set(candidate_pairs)):
        if left not in by_id or right not in by_id:
            raise ValueError("candidate pair references an unknown record ID")
        similarity = token_jaccard(
            str(by_id[left]["text"]),
            str(by_id[right]["text"]),
        )
        if similarity >= threshold:
            verified.append((left, right))
    return _components_from_pairs(by_id, verified), verified


def all_pairs_qualifying_pairs(
    rows: Sequence[Mapping[str, Any]],
    *,
    threshold: float,
) -> list[Pair]:
    """Small-corpus oracle only; deliberately quadratic."""
    by_id = _validated_rows(rows)
    record_ids = sorted(by_id)
    qualifying: list[Pair] = []
    for left, right in combinations(record_ids, 2):
        if token_jaccard(
            str(by_id[left]["text"]),
            str(by_id[right]["text"]),
        ) >= threshold:
            qualifying.append((left, right))
    return qualifying


def evaluate_candidate_contract(
    rows: Sequence[Mapping[str, Any]],
    *,
    config: CandidateConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Evaluate the frozen candidate contract against a small exact oracle."""
    by_id = _validated_rows(rows)
    candidate = generate_candidate_pairs(rows, config=config)
    candidate_pairs = candidate["pairs"]
    components, verified_pairs = verified_duplicate_components(
        rows,
        candidate_pairs,
        threshold=config.threshold,
    )
    oracle_pairs = all_pairs_qualifying_pairs(rows, threshold=config.threshold)
    oracle_components = _components_from_pairs(by_id, oracle_pairs)
    oracle_set = set(oracle_pairs)
    candidate_set = set(candidate_pairs)
    qualifying_proposed = len(oracle_set & candidate_set)
    recall = qualifying_proposed / len(oracle_set) if oracle_set else 1.0

    reversed_candidate = generate_candidate_pairs(
        list(reversed(rows)),
        config=config,
    )
    total_pairs = len(by_id) * (len(by_id) - 1) // 2
    source_counts: Counter[str] = Counter()
    for sources in candidate["pair_sources"].values():
        source_counts.update(sources)

    return {
        "status": "TESTED",
        "record_count": len(by_id),
        "all_pair_count": total_pairs,
        "candidate_pair_count": len(candidate_pairs),
        "pair_reduction_fraction": (
            1.0 - (len(candidate_pairs) / total_pairs) if total_pairs else 0.0
        ),
        "exact_qualifying_pair_count": len(oracle_pairs),
        "qualifying_pairs_proposed": qualifying_proposed,
        "qualifying_pair_recall": recall,
        "false_positive_candidate_count": len(candidate_set - oracle_set),
        "verified_pair_count": len(verified_pairs),
        "component_equality": components == oracle_components,
        "input_permutation_equal": (
            candidate["pairs"] == reversed_candidate["pairs"]
            and candidate["pair_sources"] == reversed_candidate["pair_sources"]
        ),
        "candidate_source_pair_counts": dict(sorted(source_counts.items())),
        "parameters": candidate["parameters"],
    }
