"""Print the actual run's answer key; no precomputed result is asserted here."""
import json
from fixture_data import CALIBRATION, CART, LAMP, RECEIVERS, REGISTRY, test_cases, timeline
from lab import analyze_frames, evaluate, fit, summarize, transitions


def report():
    model = fit(CALIBRATION)
    observed = analyze_frames(timeline(), REGISTRY, RECEIVERS, model)
    return {
        "schema": "owned-beacon-course-report-v1",
        "scope": "Fictional offline owned equipment; no hardware, capture, or people.",
        "metrics_unit": "zone decisions per explicitly scheduled report window",
        "held_out_evaluation": evaluate(test_cases(), REGISTRY, RECEIVERS, model),
        "timeline": observed["results"],
        "audit": observed["audit"],
        "transitions": {asset: transitions(observed["results"], asset) for asset in (CART, LAMP)},
        "equipment_summaries": [summarize(observed["results"], asset) for asset in (CART, LAMP)],
        "interpretation": [
            "Read availability together with error among accepted results.",
            "A covered window with no observation does not establish absence.",
            "Radio visibility does not establish equipment use or any person's routine.",
            "Receiver/sample IDs are trusted course metadata, not over-air authentication.",
            "Transition events describe accepted endpoints, never a path through a gap.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True, allow_nan=False))
