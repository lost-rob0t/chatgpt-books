"""Offline, fictional enrolled-equipment zone lab; no collection or ranging.

Course DTOs are deliberately NOT canonical StarIntel documents. Registry,
receiver poses, clock bounds and coverage are trusted exercise inputs.
A radio alias is not authentication. No person is represented by this lab.
"""
from collections import Counter, defaultdict
from math import dist, isfinite
from statistics import median

MAX_AGE_S = 15
MAX_PAIR_SPAN_S = 4
MAX_CLOCK_UNCERTAINTY_S = 2
MIN_SEPARATION_M = 10
MAX_RESIDUAL_DB = 8
MIN_MARGIN_DB = 6
MAX_CONTINUITY_GAP_S = 15
FRAME_WIDTH_S = 4
LOCAL_FRAME = "fictional-workshop-grid-metres"


def number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def inside(start, end, low, high):
    """A closed uncertainty interval must fit a half-open validity interval."""
    return start <= low <= high < end


def intersects(start, end, low, high):
    """Intersection of a half-open validity interval and closed uncertainty."""
    return start <= high and low < end


def pose_for(receiver, low, high):
    matches = [p for p in receiver["poses"]
               if intersects(p["starts_s"], p["ends_s"], low, high)]
    if len(matches) != 1:
        return None
    pose = matches[0]
    return pose if inside(pose["starts_s"], pose["ends_s"], low, high) else None


def enrolled_asset(registry, alias, low, high):
    """Only explicit operator-authored bindings; never similarity matching."""
    matches = [b for b in registry["bindings"]
               if b["radio_alias"] == alias
               and intersects(b["starts_s"], b["ends_s"], low, high)]
    if len(matches) != 1:
        return None
    binding = matches[0]
    if (inside(binding["starts_s"], binding["ends_s"], low, high)
            and registry["assets"].get(binding["asset_id"], {}).get("owned") is True):
        return binding["asset_id"]
    return None


def deduplicate_frames(frames):
    """Dedup receiver/sample IDs globally; quarantine conflicting re-use.

    Changing receipt time alone is an exact replay, not a new observation.
    Different sample IDs with identical payload are NOT assumed to be the
    same transmitter event. There is no generic BLE freshness/auth claim.
    """
    frames = sorted(frames, key=lambda f: f["at_s"])
    times = [f["at_s"] for f in frames]
    if len(times) != len(set(times)):
        raise ValueError("one frame per report time")
    clean = [dict(f, samples=[]) for f in frames]
    grouped = defaultdict(list)
    audit = Counter(raw_rows=0, invalid_sample=0, conflicting_keys=0,
                    conflicting_rows=0, duplicate_replays=0,
                    normalization_rejected_unique_rows=0, accepted_unique_rows=0)
    required = {"receiver_id", "sample_id", "radio_alias", "receiver_time_s",
                "received_s", "rssi_dbm"}
    for index, frame in enumerate(frames):
        if not number(frame["at_s"]) or frame["at_s"] < 0:
            raise ValueError("report time must be nonnegative and finite")
        for row in frame["samples"]:
            audit["raw_rows"] += 1
            if (not isinstance(row, dict) or set(row) != required
                    or not all(isinstance(row[k], str) and row[k]
                               for k in ("receiver_id", "sample_id", "radio_alias"))
                    or not all(number(row[k]) for k in
                               ("receiver_time_s", "received_s", "rssi_dbm"))
                    or not -120 <= row["rssi_dbm"] <= 0):
                audit["invalid_sample"] += 1
                continue
            grouped[(row["receiver_id"], row["sample_id"])].append((index, row))
    for entries in grouped.values():
        identities = {(row["radio_alias"], row["receiver_time_s"], row["rssi_dbm"])
                      for _, row in entries}
        if len(identities) != 1:
            audit["conflicting_keys"] += 1
            audit["conflicting_rows"] += len(entries)
            continue
        audit["duplicate_replays"] += len(entries) - 1
        index, row = min(entries, key=lambda pair:
                         (pair[1]["received_s"], frames[pair[0]]["at_s"]))
        clean[index]["samples"].append(dict(row))
    return clean, audit


def normalize_sample(row, registry, receivers, *, now_s):
    receiver = receivers.get(row["receiver_id"])
    if receiver is None or receiver.get("owned") is not True:
        return None, "unknown_receiver"
    offset = receiver["clock_offset_s"]
    uncertainty = receiver["clock_uncertainty_s"]
    if (not number(offset) or not number(uncertainty)
            or not 0 <= uncertainty <= MAX_CLOCK_UNCERTAINTY_S):
        return None, "clock_uncertain"
    observed = row["receiver_time_s"] - offset
    low, high = observed - uncertainty, observed + uncertainty
    if not 0 <= low <= high <= row["received_s"] <= now_s:
        return None, "invalid_time_order"
    if now_s - low > MAX_AGE_S:
        return None, "stale"
    asset = enrolled_asset(registry, row["radio_alias"], low, high)
    if asset is None:
        return None, "unknown_identity"
    pose = pose_for(receiver, low, high)
    if pose is None:
        return None, "unknown_receiver_pose"
    return dict(row, asset_id=asset, observed_s=observed,
                observed_low_s=low, observed_high_s=high,
                pose_id=pose["pose_id"], receiver_xy_m=pose["xy_m"]), None


def separated(rows):
    return any(dist(a["receiver_xy_m"], b["receiver_xy_m"]) >= MIN_SEPARATION_M
               for i, a in enumerate(rows) for b in rows[i + 1:])


def adequate_coverage(frame, receivers):
    """Health list means scheduled/healthy throughout the entire frame.

    A missing health entry means unknown coverage, not offline equipment.
    This artificial geometry gate is not a measured RF coverage guarantee.
    """
    points = []
    for receiver_id in set(frame["healthy_receivers"]):
        receiver = receivers.get(receiver_id)
        if receiver is None or receiver.get("owned") is not True:
            continue
        pose = pose_for(receiver, frame["at_s"] - FRAME_WIDTH_S, frame["at_s"])
        if pose is not None:
            points.append({"receiver_xy_m": pose["xy_m"]})
    return len(points) >= 2 and separated(points)


def fit(calibration):
    """Fit medians only from named calibration rows, never test truth."""
    grouped = defaultdict(list)
    for row in calibration:
        if row["split"] != "calibration":
            raise ValueError("test rows cannot fit the model")
        if not number(row["rssi_dbm"]) or not -120 <= row["rssi_dbm"] <= 0:
            raise ValueError("invalid calibration RSSI")
        grouped[(row["zone"], row["receiver_id"], row["pose_id"])].append(row["rssi_dbm"])
    if not grouped or any(len(values) < 2 for values in grouped.values()):
        raise ValueError("at least two calibration samples per cell")
    zones = sorted({key[0] for key in grouped})
    if len(zones) < 2:
        raise ValueError("at least two zones")
    return {"zones": zones, "fingerprints": {
        key: median(values) for key, values in grouped.items()}}


def estimate(asset_id, frame, normalized, model, receivers):
    rows = [row for row in normalized if row["asset_id"] == asset_id]
    result = {"asset_id": asset_id, "at_s": frame["at_s"], "zone": None,
              "state": "coverage_unknown", "covered": adequate_coverage(frame, receivers),
              "receiver_sample_count": len(rows), "receiver_count": 0,
              "scores_db": {}, "margin_db": None, "support_ids": [],
              "observed_start_s": min((r["observed_low_s"] for r in rows), default=None),
              "observed_end_s": max((r["observed_high_s"] for r in rows), default=None)}
    if not result["covered"]:
        return result
    if not rows:
        result["state"] = "not_observed"
        return result
    # One latest reading per distinct receiver prevents weighting a busy
    # receiver more heavily merely because it supplied more samples.
    latest = {}
    for row in sorted(rows, key=lambda r: (r["observed_s"], r["sample_id"])):
        latest[row["receiver_id"]] = row
    rows = list(latest.values())
    result["receiver_count"] = len(rows)
    result["support_ids"] = [[r["receiver_id"], r["sample_id"]] for r in rows]
    low = min(row["observed_low_s"] for row in rows)
    high = max(row["observed_high_s"] for row in rows)
    result.update(observed_start_s=low, observed_end_s=high)
    if any(row["receiver_id"] not in frame["healthy_receivers"] for row in rows):
        result["state"] = "coverage_conflict"
        return result
    if len(rows) < 2:
        result["state"] = "insufficient_receivers"
        return result
    if not separated(rows):
        result["state"] = "low_separation"
        return result
    if high - low > MAX_PAIR_SPAN_S:
        result["state"] = "unsynchronized"
        return result
    scores = {}
    for zone in model["zones"]:
        keys = [(zone, row["receiver_id"], row["pose_id"]) for row in rows]
        if any(key not in model["fingerprints"] for key in keys):
            result["state"] = "uncalibrated_pose"
            return result
        scores[zone] = sum(abs(row["rssi_dbm"] - model["fingerprints"][key])
                           for row, key in zip(rows, keys)) / len(rows)
    ranked = sorted(scores.items(), key=lambda item: (item[1], item[0]))
    margin = ranked[1][1] - ranked[0][1]
    result.update(scores_db=scores, margin_db=margin)
    if margin < MIN_MARGIN_DB:
        result["state"] = "low_margin"
    elif ranked[0][1] > MAX_RESIDUAL_DB:
        result["state"] = "out_of_calibration"
    else:
        result.update(state="estimated", zone=ranked[0][0])
    return result


def analyze_frames(frames, registry, receivers, model):
    frames, audit = deduplicate_frames(frames)
    results, observations = [], []
    for frame in frames:
        normalized = []
        for row in frame["samples"]:
            value, reason = normalize_sample(row, registry, receivers, now_s=frame["at_s"])
            if reason:
                audit["normalization_rejected_unique_rows"] += 1
                audit[reason] += 1
            else:
                audit["accepted_unique_rows"] += 1
                normalized.append(value)
        observations.extend(normalized)
        for asset_id, asset in sorted(registry["assets"].items()):
            if asset.get("owned") is True:
                results.append(estimate(asset_id, frame, normalized, model, receivers))
    return {"results": results, "observations": observations, "audit": dict(audit)}


def transitions(results, asset_id):
    """Confirm endpoints after two consecutive accepted zone results.

    Every selected support ID must be new. The complete acquisition interval
    must also lie strictly after every earlier valid interval's high bound.
    Unknown, late and overlapping results erase confirmation continuity but
    never erase the acquisition high-water mark. A change describes endpoints
    only; it contains no route, path, velocity or visit claim.
    """
    selected = sorted((r for r in results if r["asset_id"] == asset_id),
                      key=lambda r: r["at_s"])
    confirmed = candidate = previous_at = last_confirmed_at = None
    candidate_first = None
    count = 0
    events = []
    seen_support = set()
    acquisition_high_water = None
    for row in selected:
        at = row["at_s"]
        if previous_at is not None and at - previous_at > MAX_CONTINUITY_GAP_S:
            confirmed = candidate = last_confirmed_at = None
            count = 0
        previous_at = at
        support = {tuple(pair) for pair in row.get("support_ids", [])}
        reused = bool(support & seen_support)
        seen_support.update(support)
        low, high = row.get("observed_start_s"), row.get("observed_end_s")
        valid_interval = number(low) and number(high) and 0 <= low <= high <= at
        advances = valid_interval and (acquisition_high_water is None
                                       or low > acquisition_high_water)
        if valid_interval:
            # Keep this even when coverage, zone, novelty or chronology fails.
            acquisition_high_water = (high if acquisition_high_water is None
                                      else max(acquisition_high_water, high))
        if row["zone"] is None or not support or reused or not advances:
            confirmed = candidate = last_confirmed_at = None
            count = 0
            continue
        if row["zone"] == confirmed:
            candidate, count, last_confirmed_at = None, 0, at
            continue
        if row["zone"] != candidate:
            candidate, count, candidate_first = row["zone"], 1, at
        else:
            count += 1
        if count < 2:
            continue
        events.append({"kind": "acquired" if confirmed is None else "changed",
                       "from_zone": confirmed, "to_zone": candidate,
                       "last_from_report_s": last_confirmed_at,
                       "first_to_report_s": candidate_first, "confirmed_at_s": at})
        confirmed, last_confirmed_at = candidate, at
        candidate, count = None, 0
    return events


def summarize(results, asset_id):
    rows = [r for r in results if r["asset_id"] == asset_id]
    covered = [r for r in rows if r["covered"]]
    visible = [r for r in covered if r["receiver_sample_count"] > 0]
    estimated = [r for r in rows if r["zone"] is not None]
    return {"asset_id": asset_id, "report_windows": len(rows),
            "adequately_covered_windows": len(covered),
            "visible_covered_windows": len(visible),
            "not_observed_covered_windows": len(covered) - len(visible),
            "unknown_coverage_windows": len(rows) - len(covered),
            "visibility_given_coverage": ratio(len(visible), len(covered)),
            "zone_available_windows": len(estimated),
            "zone_availability": ratio(len(estimated), len(rows)),
            "receiver_sample_count": sum(r["receiver_sample_count"] for r in rows),
            "estimated_zone_windows": dict(Counter(r["zone"] for r in estimated)),
            "interpretation": "Receiver visibility only; no use, sleep, person, or routine inference."}


def evaluate(cases, registry, receivers, model):
    scored = []
    for case in cases:
        if case["split"] != "test":
            raise ValueError("evaluation requires held-out test cases")
        batch = analyze_frames([case["frame"]], registry, receivers, model)
        result = next(r for r in batch["results"] if r["asset_id"] == case["asset_id"])
        scored.append({"case_id": case["case_id"], "truth_zone": case["truth_zone"],
                       "predicted_zone": result["zone"], "state": result["state"],
                       "covered": result["covered"], "audit": batch["audit"]})
    accepted = [r for r in scored if r["predicted_zone"] is not None]
    errors = sum(r["predicted_zone"] != r["truth_zone"] for r in accepted)
    return {"cases": scored, "test_cases": len(scored), "accepted": len(accepted),
            "abstained": len(scored) - len(accepted), "wrong_accepted": errors,
            "availability": ratio(len(accepted), len(scored)),
            "conditional_error_rate": ratio(errors, len(accepted)),
            "correct_over_all_cases": ratio(len(accepted) - errors, len(scored)),
            "adequate_coverage_rate": ratio(sum(r["covered"] for r in scored), len(scored)),
            "warning": "Hand-authored synthetic held-out cases are not field validation."}
