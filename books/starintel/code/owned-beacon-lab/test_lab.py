from copy import deepcopy
import unittest

from fixture_data import CALIBRATION, CART, EAST, LAMP, RECEIVERS, REGISTRY, WEST
from fixture_data import frame, test_cases, timeline
from lab import analyze_frames, enrolled_asset, evaluate, fit, normalize_sample
from lab import pose_for, summarize, transitions


class OwnedBeaconLabTests(unittest.TestCase):
    def setUp(self):
        self.registry = deepcopy(REGISTRY)
        self.receivers = deepcopy(RECEIVERS)
        self.model = fit(CALIBRATION)

    def analyze(self, frames):
        return analyze_frames(frames, self.registry, self.receivers, self.model)

    def cart_results(self, batch):
        return [r for r in batch["results"] if r["asset_id"] == CART]

    def test_corrected_clock_is_not_receipt_time(self):
        batch = self.analyze([frame(100, WEST)])
        self.assertEqual({r["observed_s"] for r in batch["observations"]}, {98})
        self.assertEqual({r["received_s"] for r in batch["observations"]}, {100})
        self.assertEqual({r["receiver_time_s"] for r in batch["observations"]}, {97, 100})
        self.assertEqual(batch["observations"][0]["observed_low_s"], 97)

    def test_stale_receipt_does_not_rejuvenate_observation(self):
        batch = self.analyze([frame(180, WEST, observed_s=100)])
        self.assertEqual(batch["audit"]["stale"], 2)
        self.assertIsNone(self.cart_results(batch)[0]["zone"])

    def test_uncertain_and_future_clocks_are_rejected(self):
        row = frame(100, WEST)["samples"][0]
        self.receivers["r-west"]["clock_uncertainty_s"] = 3
        value, reason = normalize_sample(row, self.registry, self.receivers, now_s=100)
        self.assertIsNone(value)
        self.assertEqual(reason, "clock_uncertain")
        self.receivers["r-west"]["clock_uncertainty_s"] = 1
        row["receiver_time_s"] = 104
        self.assertEqual(normalize_sample(row, self.registry, self.receivers, now_s=100)[1],
                         "invalid_time_order")

    def test_uncertainty_interval_must_fit_binding_and_pose(self):
        row = frame(151, [("r-rover", -43)])["samples"][0]
        self.assertEqual(normalize_sample(row, self.registry, self.receivers, now_s=151)[1],
                         "unknown_identity")
        self.registry["bindings"][0]["ends_s"] = 160
        self.assertEqual(normalize_sample(row, self.registry, self.receivers, now_s=151)[1],
                         "unknown_receiver_pose")
        later = frame(153, [("r-rover", -42)])["samples"][0]
        value, reason = normalize_sample(later, REGISTRY, self.receivers, now_s=153)
        self.assertIsNone(reason)
        self.assertEqual(value["pose_id"], "rover-east")

    def test_exact_replay_collapses_across_report_windows(self):
        first, second = frame(100, WEST), frame(110)
        second["samples"] = deepcopy(first["samples"])
        for row in second["samples"]:
            row["received_s"] = 110
        batch = self.analyze([first, second])
        self.assertEqual(len(batch["observations"]), 2)
        self.assertEqual(batch["audit"]["duplicate_replays"], 2)
        self.assertEqual(self.cart_results(batch)[1]["state"], "not_observed")
        self.assertEqual(summarize(batch["results"], CART)["receiver_sample_count"], 2)

    def test_conflicting_key_reuse_is_order_independently_quarantined(self):
        first, second = frame(100, WEST), frame(110)
        conflict = deepcopy(first["samples"][0])
        conflict.update(rssi_dbm=-60, received_s=110)
        second["samples"] = [conflict]
        batch = self.analyze([first, second])
        self.assertEqual(batch, self.analyze([second, first]))
        self.assertEqual(batch["audit"]["conflicting_keys"], 1)
        self.assertEqual(len(batch["observations"]), 1)

    def test_unknown_rotation_is_not_linked_by_rssi(self):
        batch = self.analyze([frame(150, WEST, radio_alias="fictional-cart-unlisted")])
        self.assertEqual(batch["audit"]["unknown_identity"], 2)
        self.assertEqual(batch["observations"], [])
        self.assertIsNone(self.cart_results(batch)[0]["zone"])

    def test_bindings_are_explicit_half_open_and_unambiguous(self):
        self.assertEqual(enrolled_asset(self.registry, "fictional-cart-a", 149, 149), CART)
        self.assertIsNone(enrolled_asset(self.registry, "fictional-cart-a", 150, 150))
        self.assertEqual(enrolled_asset(self.registry, "fictional-cart-b", 150, 150), CART)
        self.registry["bindings"].append(
            {"asset_id": LAMP, "radio_alias": "fictional-cart-b", "starts_s": 150, "ends_s": 200})
        self.assertIsNone(enrolled_asset(self.registry, "fictional-cart-b", 160, 160))

    def test_only_enrolled_owned_assets_and_receivers_are_accepted(self):
        self.receivers["r-west"]["owned"] = False
        batch = self.analyze([frame(100, WEST)])
        self.assertEqual(batch["audit"]["unknown_receiver"], 1)
        self.registry["assets"][CART]["owned"] = False
        batch = self.analyze([frame(110, WEST)])
        self.assertEqual(self.cart_results(batch), [])
        self.assertEqual(batch["observations"], [])

    def test_static_zone_fingerprint_is_a_zone_not_a_position(self):
        result = self.cart_results(self.analyze([frame(100, WEST)]))[0]
        self.assertEqual(result["zone"], "west-bay")
        self.assertEqual(result["state"], "estimated")
        self.assertNotIn("latitude", result)
        self.assertNotIn("device_xy_m", result)
        self.assertNotIn("confidence_probability", result)

    def test_moving_receiver_uses_the_time_valid_pose(self):
        frames = [frame(120, [("r-east", -75), ("r-rover", -43)]),
                  frame(170, [("r-west", -74), ("r-rover", -42)])]
        batch = self.analyze(frames)
        self.assertEqual([r["zone"] for r in self.cart_results(batch)], ["west-bay", "east-bay"])
        rover = [r for r in batch["observations"] if r["receiver_id"] == "r-rover"]
        self.assertEqual([r["pose_id"] for r in rover], ["rover-west", "rover-east"])
        self.assertEqual([r["receiver_xy_m"] for r in rover], [[2, 0], [18, 0]])

    def test_missing_or_untrained_moving_pose_abstains(self):
        value = frame(170, [("r-west", -74), ("r-rover", -42)])
        self.receivers["r-rover"]["poses"] = []
        batch = self.analyze([value])
        self.assertEqual(batch["audit"]["unknown_receiver_pose"], 1)
        self.assertEqual(self.cart_results(batch)[0]["state"], "insufficient_receivers")
        self.receivers = deepcopy(RECEIVERS)
        self.receivers["r-rover"]["poses"][1]["pose_id"] = "new-untrained-stop"
        self.assertEqual(self.cart_results(self.analyze([value]))[0]["state"], "uncalibrated_pose")

    def test_nearby_receivers_do_not_supply_adequate_separation(self):
        result = self.cart_results(self.analyze(
            [frame(140, [("r-west", -41), ("r-rover", -43)])]))[0]
        self.assertEqual(result["state"], "low_separation")
        self.assertIsNone(result["zone"])

    def test_margin_and_out_of_calibration_are_separate_abstentions(self):
        cases = {case["case_id"]: case for case in test_cases()}
        for name, state in (("ambiguous", "low_margin"), ("out-of-calibration", "out_of_calibration")):
            with self.subTest(name=name):
                result = self.cart_results(self.analyze([cases[name]["frame"]]))[0]
                self.assertEqual(result["state"], state)
                self.assertIsNone(result["zone"])

    def test_test_labels_cannot_fit_or_leak_into_predictions(self):
        contaminated = deepcopy(CALIBRATION)
        contaminated[0]["split"] = "test"
        with self.assertRaises(ValueError):
            fit(contaminated)
        cases = test_cases()
        original = evaluate(cases, self.registry, self.receivers, self.model)
        for case in cases:
            case["truth_zone"] = "changed-test-label"
        changed = evaluate(cases, self.registry, self.receivers, self.model)
        self.assertEqual([r["predicted_zone"] for r in original["cases"]],
                         [r["predicted_zone"] for r in changed["cases"]])

    def test_pairing_uses_corrected_uncertainty_span_not_receipt_span(self):
        value = frame(100, WEST)
        value["samples"][1]["receiver_time_s"] = 91  # corrected 92 +/- 1
        result = self.cart_results(self.analyze([value]))[0]
        self.assertEqual(result["state"], "unsynchronized")

    def test_coverage_gap_and_covered_nondetection_remain_distinct(self):
        unknown = self.analyze([frame(140, healthy=[])])
        covered = self.analyze([frame(180)])
        self.assertEqual(self.cart_results(unknown)[0]["state"], "coverage_unknown")
        self.assertEqual(self.cart_results(covered)[0]["state"], "not_observed")
        self.assertIsNone(summarize(unknown["results"], CART)["visibility_given_coverage"])
        self.assertEqual(summarize(covered["results"], CART)["visibility_given_coverage"], 0)
        self.assertNotIn("absent", self.cart_results(covered)[0])

    def test_single_receiver_visibility_is_not_a_zone_or_use_claim(self):
        batch = self.analyze([frame(100, [("r-west", -41)])])
        self.assertEqual(self.cart_results(batch)[0]["state"], "insufficient_receivers")
        summary = summarize(batch["results"], CART)
        self.assertEqual(summary["visible_covered_windows"], 1)
        self.assertEqual(summary["zone_available_windows"], 0)
        self.assertIn("no use", summary["interpretation"])

    def test_transition_requires_two_new_accepted_windows(self):
        first = self.analyze([frame(100, WEST)])
        self.assertEqual(transitions(first["results"], CART), [])
        batch = self.analyze([frame(100, WEST), frame(110, WEST), frame(120, EAST), frame(130, EAST)])
        events = transitions(batch["results"], CART)
        self.assertEqual([e["kind"] for e in events], ["acquired", "changed"])
        self.assertEqual(events[1]["confirmed_at_s"], 130)
        self.assertEqual(events[1]["last_from_report_s"], 110)
        self.assertEqual(events[1]["first_to_report_s"], 120)

    def test_unknown_window_and_time_gap_break_transition_continuity(self):
        for frames in (
            [frame(100, WEST), frame(110, WEST), frame(140, EAST), frame(150, EAST)],
            [frame(100, WEST), frame(110, WEST), frame(120), frame(130, EAST), frame(140, EAST)],
        ):
            with self.subTest(times=[f["at_s"] for f in frames]):
                events = transitions(self.analyze(frames)["results"], CART)
                self.assertEqual([e["kind"] for e in events], ["acquired", "acquired"])
                self.assertTrue(all("path" not in e and "speed" not in e for e in events))

    def test_repeated_result_support_cannot_confirm_a_transition(self):
        original = self.cart_results(self.analyze([frame(100, WEST)]))[0]
        repeated = dict(original, at_s=110)
        self.assertEqual(transitions([original, repeated], CART), [])

    def test_metrics_keep_abstentions_and_errors_in_honest_denominators(self):
        value = evaluate(test_cases(), self.registry, self.receivers, self.model)
        self.assertEqual(value["test_cases"], value["accepted"] + value["abstained"])
        self.assertGreater(value["wrong_accepted"], 0)
        self.assertGreater(value["abstained"], 0)
        self.assertEqual(value["availability"], value["accepted"] / value["test_cases"])
        self.assertEqual(value["conditional_error_rate"], value["wrong_accepted"] / value["accepted"])
        only_gap = [case for case in test_cases() if case["case_id"] == "coverage-gap"]
        unavailable = evaluate(only_gap, self.registry, self.receivers, self.model)
        self.assertIsNone(unavailable["conditional_error_rate"])
        self.assertIsNone(evaluate([], self.registry, self.receivers, self.model)["availability"])

    def test_per_equipment_summary_counts_unique_receiver_samples(self):
        batch = self.analyze(timeline())
        self.assertEqual(batch["audit"]["duplicate_replays"], 1)
        for asset in (CART, LAMP):
            summary = summarize(batch["results"], asset)
            self.assertEqual(summary["report_windows"], len(timeline()))
            self.assertEqual(summary["receiver_sample_count"],
                             sum(r["asset_id"] == asset for r in batch["observations"]))
            self.assertEqual(sum(summary["estimated_zone_windows"].values()),
                             summary["zone_available_windows"])
            self.assertNotIn("daily_routine", summary)


    def test_late_acquisition_cannot_become_a_current_transition(self):
        frames = [frame(100, WEST, observed_s=98), frame(110, WEST, observed_s=108),
                  frame(111, EAST, observed_s=100), frame(112, EAST, observed_s=101)]
        batch = self.analyze(frames)
        self.assertTrue(all(r["zone"] is not None for r in self.cart_results(batch)))
        events = transitions(batch["results"], CART)
        self.assertEqual([(e["kind"], e["to_zone"], e["confirmed_at_s"]) for e in events],
                         [("acquired", "west-bay", 110)])
        # Unknown coverage and further late evidence must not erase the
        # high-water mark established by the west evidence at 108 +/- 1.
        frames.extend([frame(113, healthy=[]),
                       frame(114, EAST, observed_s=102), frame(115, EAST, observed_s=103),
                       frame(120, EAST, observed_s=118), frame(130, EAST, observed_s=128)])
        events = transitions(self.analyze(frames)["results"], CART)
        self.assertEqual([(e["kind"], e["to_zone"], e["confirmed_at_s"]) for e in events],
                         [("acquired", "west-bay", 110), ("acquired", "east-bay", 130)])

    def test_overlapping_and_touching_acquisition_intervals_reset_confirmation(self):
        cases = [
            # The overlapping interval advances the high-water mark from
            # 103 to 104. The next interval starts at 104, so it still cannot
            # become the first member of a new two-report confirmation.
            ([frame(100, WEST, observed_s=98), frame(104, WEST, observed_s=102),
              frame(106, EAST, observed_s=103), frame(108, EAST, observed_s=105),
              frame(110, EAST, observed_s=108), frame(114, EAST, observed_s=112)],
             [104, 114]),
            # Closed uncertainty intervals sharing one endpoint overlap.
            ([frame(100, WEST, observed_s=98), frame(103, WEST, observed_s=100),
              frame(106, WEST, observed_s=104), frame(109, WEST, observed_s=107)],
             [109]),
        ]
        for frames, expected_times in cases:
            with self.subTest(times=[f["at_s"] for f in frames]):
                events = transitions(self.analyze(frames)["results"], CART)
                self.assertEqual([e["confirmed_at_s"] for e in events], expected_times)
                self.assertTrue(all(e["kind"] == "acquired" for e in events))

    def test_partial_binding_and_pose_overlap_is_ambiguous_at_shared_endpoints(self):
        self.registry["bindings"].append(
            {"asset_id": LAMP, "radio_alias": "fictional-cart-a", "starts_s": 149, "ends_s": 200})
        self.assertIsNone(enrolled_asset(self.registry, "fictional-cart-a", 147, 149))
        self.assertIsNone(enrolled_asset(self.registry, "fictional-cart-a", 149, 149))
        self.assertEqual(enrolled_asset(self.registry, "fictional-cart-a", 147, 148), CART)
        self.assertEqual(enrolled_asset(self.registry, "fictional-cart-a", 150, 150), LAMP)
        receiver = deepcopy(self.receivers["r-rover"])
        receiver["poses"][1]["starts_s"] = 149
        self.assertIsNone(pose_for(receiver, 147, 149))
        self.assertIsNone(pose_for(receiver, 149, 149))
        self.assertEqual(pose_for(receiver, 147, 148)["pose_id"], "rover-west")
        self.assertEqual(pose_for(receiver, 150, 150)["pose_id"], "rover-east")
        # Nonoverlapping half-open validity intervals remain unambiguous at
        # the exact handover, while uncertainty crossing it is withheld.
        self.assertEqual(pose_for(RECEIVERS["r-rover"], 150, 150)["pose_id"], "rover-east")
        self.assertIsNone(pose_for(RECEIVERS["r-rover"], 149, 150))

    def test_raw_sample_accounting_reconciles_primary_dispositions(self):
        value = frame(100, WEST)
        replay = deepcopy(value["samples"][0])
        replay["received_s"] = 101
        conflict = deepcopy(value["samples"][1])
        conflict["rssi_dbm"] = -60
        conflict_replay = deepcopy(value["samples"][1])
        unknown = deepcopy(value["samples"][0])
        unknown.update(sample_id="unknown-alias-sample", radio_alias="fictional-unlisted")
        stale = deepcopy(value["samples"][1])
        stale.update(sample_id="stale-sample", receiver_time_s=49)
        value["samples"].extend([replay, conflict, conflict_replay, {}, unknown, stale])
        audit = self.analyze([value])["audit"]
        self.assertEqual(audit["raw_rows"], 8)
        self.assertEqual(audit["accepted_unique_rows"], 1)
        self.assertEqual(audit["conflicting_keys"], 1)
        self.assertEqual(audit["conflicting_rows"], 3)
        self.assertEqual(audit["duplicate_replays"], 1)
        self.assertEqual(audit["invalid_sample"], 1)
        self.assertEqual(audit["normalization_rejected_unique_rows"], 2)
        self.assertEqual(audit["unknown_identity"] + audit["stale"],
                         audit["normalization_rejected_unique_rows"])
        self.assertEqual(audit["raw_rows"],
                         audit["accepted_unique_rows"] + audit["conflicting_rows"]
                         + audit["duplicate_replays"] + audit["invalid_sample"]
                         + audit["normalization_rejected_unique_rows"])


if __name__ == "__main__":
    unittest.main()
