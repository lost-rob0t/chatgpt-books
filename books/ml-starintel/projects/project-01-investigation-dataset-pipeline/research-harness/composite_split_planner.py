from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ConstraintEdge:
    left: str
    right: str
    rule: str


class SplitInfeasible(ValueError):
    def __init__(self, diagnostics: dict):
        super().__init__("split infeasible")
        self.diagnostics = diagnostics


def _canon(value: object) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("record IDs and constraint endpoints must be non-empty")
    return text


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compile_composite_groups(record_ids: Iterable[object], edges: Iterable[ConstraintEdge]):
    ids = sorted({_canon(value) for value in record_ids})
    parent = {value: value for value in ids}
    edge_list = sorted(
        (ConstraintEdge(_canon(edge.left), _canon(edge.right), _canon(edge.rule)) for edge in edges),
        key=lambda edge: (edge.rule, edge.left, edge.right),
    )
    for edge in edge_list:
        if edge.left not in parent or edge.right not in parent:
            raise KeyError(f"constraint endpoint missing from records: {edge}")

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        parent[high] = low

    for edge in edge_list:
        union(edge.left, edge.right)

    members: dict[str, list[str]] = {}
    for record_id in ids:
        members.setdefault(find(record_id), []).append(record_id)

    groups: dict[str, str] = {}
    components = []
    for component_members in sorted(members.values(), key=lambda values: min(values)):
        component_id = min(component_members)
        for record_id in component_members:
            groups[record_id] = component_id
        member_set = set(component_members)
        used_edges = [
            edge for edge in edge_list
            if edge.left in member_set and edge.right in member_set
        ]
        components.append(
            {
                "composite_group_id": component_id,
                "record_ids": sorted(component_members),
                "constraint_edges": [
                    {"left": edge.left, "right": edge.right, "rule": edge.rule}
                    for edge in used_edges
                ],
            }
        )
    return groups, components


def diagnose_straddling(
    records: Sequence[Mapping[str, object]],
    groups: Mapping[str, str],
    cutoff: str,
    timestamp_key: str = "observed_at",
):
    cutoff_time = _parse_time(cutoff)
    sides: dict[str, set[str]] = {}
    for row in records:
        record_id = _canon(row["record_id"])
        group_id = groups[record_id]
        observed = _parse_time(str(row[timestamp_key]))
        sides.setdefault(group_id, set()).add("train" if observed < cutoff_time else "test")
    return sorted(group_id for group_id, seen in sides.items() if seen == {"train", "test"})


def validate_feature_availability(
    records: Sequence[Mapping[str, object]],
    prediction_key: str = "prediction_at",
    features_key: str = "features",
):
    violations = []
    for row in records:
        prediction = _parse_time(str(row[prediction_key]))
        for feature in row.get(features_key, []) or []:
            available = _parse_time(str(feature["available_at"]))
            if available > prediction:
                violations.append(
                    {
                        "record_id": _canon(row["record_id"]),
                        "feature": str(feature["name"]),
                        "available_at": available.isoformat(),
                        "prediction_at": prediction.isoformat(),
                    }
                )
    return violations


def audit_overlap(records, train_ids, test_ids, groups, hard_rule_fields=()):
    train_ids, test_ids = set(map(_canon, train_ids)), set(map(_canon, test_ids))
    by_id = {_canon(row["record_id"]): row for row in records}
    if train_ids & test_ids:
        raise ValueError("train/test record IDs overlap")
    missing = (train_ids | test_ids) - set(by_id)
    if missing:
        raise KeyError(f"unknown partition record IDs: {sorted(missing)}")

    def values(ids, field):
        output = set()
        for record_id in ids:
            value = by_id[record_id].get(field)
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                output.update(map(str, value))
            else:
                output.add(str(value))
        return output

    hard = {}
    for field in hard_rule_fields:
        overlap = sorted(values(train_ids, field) & values(test_ids, field))
        hard[field] = {"overlap_count": len(overlap), "overlap_values": overlap}

    composite_overlap = sorted(
        {groups[record_id] for record_id in train_ids}
        & {groups[record_id] for record_id in test_ids}
    )
    return {
        "record_overlap_count": 0,
        "composite_group_overlap_count": len(composite_overlap),
        "composite_group_overlap_ids": composite_overlap,
        "hard_rule_overlaps": hard,
    }


def plan_strict_cutoff(
    records,
    edges,
    cutoff,
    hard_rule_fields=(),
    timestamp_key="observed_at",
):
    groups, components = compile_composite_groups((row["record_id"] for row in records), edges)
    straddling = diagnose_straddling(records, groups, cutoff, timestamp_key)
    feature_violations = validate_feature_availability(records)
    diagnostics = {
        "cutoff": cutoff,
        "straddling_component_count": len(straddling),
        "straddling_component_ids": straddling,
        "future_feature_violation_count": len(feature_violations),
        "future_feature_violations": feature_violations,
    }
    if straddling or feature_violations:
        raise SplitInfeasible(diagnostics)

    cutoff_time = _parse_time(cutoff)
    train = [
        _canon(row["record_id"])
        for row in records
        if _parse_time(str(row[timestamp_key])) < cutoff_time
    ]
    test = [
        _canon(row["record_id"])
        for row in records
        if _parse_time(str(row[timestamp_key])) >= cutoff_time
    ]
    audit = audit_overlap(records, train, test, groups, hard_rule_fields)
    if audit["composite_group_overlap_count"] or any(
        result["overlap_count"] for result in audit["hard_rule_overlaps"].values()
    ):
        raise SplitInfeasible({**diagnostics, "contamination": audit})

    return {
        "train_ids": sorted(train),
        "test_ids": sorted(test),
        "groups": groups,
        "components": components,
        "diagnostics": {**diagnostics, "contamination": audit},
    }
