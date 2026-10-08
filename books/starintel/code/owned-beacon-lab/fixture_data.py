"""Deterministic, authored course data. Every object here is fictional.

These dictionaries are course DTOs, not StarIntel documents. Ground-truth
zones exist only in held-out test cases; the classifier never receives them.
"""
from copy import deepcopy

CART = "asset:owned-lab-cart"
LAMP = "asset:owned-lab-lamp"
REGISTRY = {
    "assets": {
        CART: {"owned": True, "label": "Fictional workshop cart"},
        LAMP: {"owned": True, "label": "Fictional work light"},
    },
    "bindings": [
        {"asset_id": CART, "radio_alias": "fictional-cart-a", "starts_s": 0, "ends_s": 150},
        {"asset_id": CART, "radio_alias": "fictional-cart-b", "starts_s": 150, "ends_s": 500},
        {"asset_id": LAMP, "radio_alias": "fictional-lamp-a", "starts_s": 0, "ends_s": 500},
    ],
}
RECEIVERS = {
    "r-west": {"owned": True, "clock_offset_s": 2, "clock_uncertainty_s": 1,
               "poses": [{"pose_id": "west-anchor", "starts_s": 0, "ends_s": 500,
                          "xy_m": [0, 0]}]},
    "r-east": {"owned": True, "clock_offset_s": -1, "clock_uncertainty_s": 1,
               "poses": [{"pose_id": "east-anchor", "starts_s": 0, "ends_s": 500,
                          "xy_m": [20, 0]}]},
    "r-rover": {"owned": True, "clock_offset_s": 3, "clock_uncertainty_s": 1,
                "poses": [{"pose_id": "rover-west", "starts_s": 0, "ends_s": 150,
                           "xy_m": [2, 0]},
                          {"pose_id": "rover-east", "starts_s": 150, "ends_s": 500,
                           "xy_m": [18, 0]}]},
}
# Hand-authored medians; deliberately simple separable fingerprints.
# Three rows per cell are supplied to teach fitting without a random seed.
CALIBRATION_CELLS = [
    ("west-bay", "r-west", "west-anchor", -41),
    ("west-bay", "r-east", "east-anchor", -75),
    ("west-bay", "r-rover", "rover-west", -43),
    ("west-bay", "r-rover", "rover-east", -73),
    ("east-bay", "r-west", "west-anchor", -74),
    ("east-bay", "r-east", "east-anchor", -41),
    ("east-bay", "r-rover", "rover-west", -73),
    ("east-bay", "r-rover", "rover-east", -42),
]
CALIBRATION = [
    {"split": "calibration", "zone": zone, "receiver_id": receiver,
     "pose_id": pose, "rssi_dbm": center + delta}
    for zone, receiver, pose, center in CALIBRATION_CELLS
    for delta in (-1, 0, 1)
]
WEST = [("r-west", -41), ("r-east", -75)]
EAST = [("r-west", -74), ("r-east", -41)]


def frame(at_s, readings=(), *, asset_id=CART, radio_alias=None,
          healthy=None, observed_s=None):
    observed_s = at_s - 2 if observed_s is None else observed_s
    if radio_alias is None:
        radio_alias = ("fictional-lamp-a" if asset_id == LAMP else
                       "fictional-cart-a" if observed_s < 150 else "fictional-cart-b")
    short = "cart" if asset_id == CART else "lamp"
    return {
        "at_s": at_s,
        "healthy_receivers": list(RECEIVERS) if healthy is None else list(healthy),
        "samples": [
            {"receiver_id": receiver, "sample_id": f"{receiver}-{short}-{at_s}",
             "radio_alias": radio_alias,
             "receiver_time_s": observed_s + RECEIVERS[receiver]["clock_offset_s"],
             "received_s": at_s, "rssi_dbm": rssi}
            for receiver, rssi in readings
        ],
    }


def test_cases():
    """A test split authored separately from calibration, not field evidence."""
    definitions = [
        ("west-static", "west-bay", frame(100, [("r-west", -42), ("r-east", -74)])),
        ("east-static", "east-bay", frame(110, EAST)),
        ("west-moving-receiver", "west-bay", frame(120, [("r-east", -75), ("r-rover", -43)])),
        ("east-moving-receiver", "east-bay", frame(170, [("r-west", -74), ("r-rover", -42)])),
        ("ambiguous", "west-bay", frame(130, [("r-west", -57), ("r-east", -58)])),
        ("out-of-calibration", "west-bay", frame(140, [("r-west", -20), ("r-east", -75)])),
        ("stale", "west-bay", frame(180, WEST, observed_s=100)),
        ("low-separation", "west-bay", frame(140, [("r-west", -41), ("r-rover", -43)])),
        ("coverage-gap", "east-bay", frame(190, healthy=[])),
        # A deliberately misleading accepted fingerprint proves that accepted
        # estimates can be wrong. Do not tune thresholds on this test case.
        ("wrong-confident-candidate", "east-bay", frame(200, WEST)),
        ("unlisted-rotation", "west-bay",
         frame(150, WEST, radio_alias="fictional-cart-unlisted")),
    ]
    return [{"case_id": name, "split": "test", "asset_id": CART,
             "truth_zone": truth, "frame": value}
            for name, truth, value in definitions]


def timeline():
    specification = [
        (100, WEST), (110, WEST), (120, EAST), (130, EAST),
        (140, ()), (150, WEST), (160, WEST), (170, WEST),
        (180, ()), (190, WEST), (200, WEST), (210, EAST), (220, EAST),
    ]
    lamp_times = {100, 110, 130, 160, 170, 200, 210, 220}
    frames = []
    for at, readings in specification:
        value = frame(at, readings,
                      radio_alias="fictional-cart-unlisted" if at == 150 else None,
                      healthy=[] if at == 140 else None)
        if at in lamp_times:
            value["samples"].extend(frame(at, EAST, asset_id=LAMP)["samples"])
        frames.append(value)
    # The same receiver/sample identity arrives in a later report: it must
    # never create another supporting sighting or activity count.
    replay = deepcopy(frames[0]["samples"][0])
    replay["received_s"] = 110
    frames[1]["samples"].append(replay)
    return frames
