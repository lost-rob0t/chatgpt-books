#!/usr/bin/env python3
import unittest

import composite_split_planner as subject


def row(record_id, observed_at, entity_id=None, features=None):
    return {
        "record_id": record_id,
        "observed_at": observed_at,
        "prediction_at": observed_at,
        "entity_id": entity_id,
        "features": features or [],
    }


class CompositePlannerTests(unittest.TestCase):
    def test_transitive_constraints_compose_with_stable_lexical_id(self):
        ids = ["c", "b", "a", "z"]
        edges = [
            subject.ConstraintEdge("b", "c", "near_duplicate"),
            subject.ConstraintEdge("a", "b", "entity"),
        ]
        groups, components = subject.compile_composite_groups(ids, edges)
        self.assertEqual(groups["a"], "a")
        self.assertEqual(groups["b"], "a")
        self.assertEqual(groups["c"], "a")
        self.assertEqual(groups["z"], "z")
        self.assertEqual(components[0]["record_ids"], ["a", "b", "c"])
        self.assertEqual(
            {edge["rule"] for edge in components[0]["constraint_edges"]},
            {"entity", "near_duplicate"},
        )

    def test_edge_order_does_not_change_component_ids(self):
        ids = ["a", "b", "c"]
        edges = [
            subject.ConstraintEdge("b", "c", "near"),
            subject.ConstraintEdge("a", "b", "entity"),
        ]
        self.assertEqual(
            subject.compile_composite_groups(ids, edges),
            subject.compile_composite_groups(reversed(ids), reversed(edges)),
        )

    def test_missing_constraint_endpoint_fails_closed(self):
        with self.assertRaises(KeyError):
            subject.compile_composite_groups(
                ["a"], [subject.ConstraintEdge("a", "b", "entity")]
            )

    def test_straddling_component_is_rejected(self):
        rows = [
            row("a", "2026-01-01T00:00:00Z", "E1"),
            row("b", "2026-03-01T00:00:00Z", "E1"),
            row("c", "2026-04-01T00:00:00Z", "E2"),
        ]
        edges = [subject.ConstraintEdge("a", "b", "entity")]
        with self.assertRaises(subject.SplitInfeasible) as caught:
            subject.plan_strict_cutoff(
                rows, edges, "2026-02-01T00:00:00Z", hard_rule_fields=("entity_id",)
            )
        self.assertEqual(caught.exception.diagnostics["straddling_component_ids"], ["a"])

    def test_future_feature_is_rejected(self):
        rows = [
            row(
                "a",
                "2026-01-01T00:00:00Z",
                features=[
                    {"name": "future", "available_at": "2026-01-02T00:00:00Z"}
                ],
            )
        ]
        with self.assertRaises(subject.SplitInfeasible) as caught:
            subject.plan_strict_cutoff(rows, [], "2026-02-01T00:00:00Z")
        self.assertEqual(
            caught.exception.diagnostics["future_feature_violation_count"], 1
        )

    def test_clean_strict_cutoff_has_zero_enabled_overlap(self):
        rows = [
            row("a", "2026-01-01T00:00:00Z", "E1"),
            row("b", "2026-01-02T00:00:00Z", "E1"),
            row("c", "2026-03-01T00:00:00Z", "E2"),
            row("d", "2026-03-02T00:00:00Z", "E2"),
        ]
        edges = [
            subject.ConstraintEdge("a", "b", "entity"),
            subject.ConstraintEdge("c", "d", "entity"),
        ]
        result = subject.plan_strict_cutoff(
            rows, edges, "2026-02-01T00:00:00Z", hard_rule_fields=("entity_id",)
        )
        self.assertEqual(result["train_ids"], ["a", "b"])
        self.assertEqual(result["test_ids"], ["c", "d"])
        contamination = result["diagnostics"]["contamination"]
        self.assertEqual(contamination["composite_group_overlap_count"], 0)
        self.assertEqual(
            contamination["hard_rule_overlaps"]["entity_id"]["overlap_count"], 0
        )


if __name__ == "__main__":
    unittest.main()
