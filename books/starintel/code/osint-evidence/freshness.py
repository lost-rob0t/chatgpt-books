"""Book-local classifier for invented, consent-scoped location observations.

No collection, networking, identification, or StarIntel runtime is implemented.
The grant is trusted exercise input, never a claim taken from the sample itself.
All clocks are seconds on one fictional simulation clock.
"""
import math


def seconds(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def finite_nonnegative(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def classify(sample, grant, *, now_s, audience):
    """Return a display state, not a claim about a person's present location."""
    if not seconds(now_s):
        return "unknown"
    target_audience = grant.get("audience")
    if (not isinstance(audience, str) or not audience.strip()
            or not isinstance(target_audience, str) or not target_audience.strip()
            or grant.get("active") is not True or target_audience != audience):
        return "blocked"
    start, expiry = grant.get("startsAtS"), grant.get("expiresAtS")
    if not seconds(start) or not seconds(expiry) or expiry <= start:
        return "blocked"
    if not start <= now_s < expiry:
        return "blocked"
    age_limit, accuracy_limit = grant.get("maxAgeS"), grant.get("maxAccuracyM")
    if not seconds(age_limit) or not finite_nonnegative(accuracy_limit):
        return "blocked"
    observed, received = sample.get("observedAtS"), sample.get("receivedAtS")
    if not seconds(observed) or not seconds(received):
        return "unknown"
    if not start <= observed <= received <= now_s:
        return "unknown"
    accuracy = sample.get("accuracyM")
    if not finite_nonnegative(accuracy):
        return "unknown"
    if now_s - observed > age_limit:
        return "stale"
    if accuracy > accuracy_limit:
        return "coarse"
    return "fresh"
