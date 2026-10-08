"""Book-local classifier for invented, consent-scoped location observations.

No collection, networking, identification, or StarIntel runtime is implemented.
The grant is trusted exercise input, never a claim taken from the sample itself.
All clocks are seconds on one fictional simulation clock.
"""
import math


def seconds(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def classify(sample, grant, *, now_s, audience):
    """Return a display state, not a claim about a person's present location."""
    if not seconds(now_s):
        return "unknown"
    if grant.get("active") is not True or grant.get("audience") != audience:
        return "blocked"
    start, expiry = grant.get("startsAtS"), grant.get("expiresAtS")
    if not seconds(start) or not seconds(expiry) or expiry <= start:
        return "blocked"
    if not start <= now_s < expiry:
        return "blocked"
    observed, received = sample.get("observedAtS"), sample.get("receivedAtS")
    if not seconds(observed) or not seconds(received):
        return "unknown"
    if not start <= observed <= received <= now_s:
        return "unknown"
    age_limit, accuracy_limit = grant.get("maxAgeS"), grant.get("maxAccuracyM")
    accuracy = sample.get("accuracyM")
    if not seconds(age_limit):
        return "unknown"
    for value in (accuracy, accuracy_limit):
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or value < 0):
            return "unknown"
    if now_s - observed > age_limit:
        return "stale"
    if accuracy > accuracy_limit:
        return "coarse"
    return "fresh"
