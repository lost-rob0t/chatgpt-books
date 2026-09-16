from __future__ import annotations

from collections.abc import Iterable
from math import fsum, hypot, isfinite
from numbers import Real

Vector = tuple[float, ...]


class VectorError(ValueError):
    """Raised when a vector violates the toolkit's finite-real contract."""


def vector(values: Iterable[Real]) -> Vector:
    """Return an immutable finite, non-empty real vector."""
    if isinstance(values, (str, bytes)):
        raise TypeError("vector values must be an iterable of real numbers")

    items = tuple(values)
    if not items:
        raise VectorError("vectors must have at least one component")

    result: list[float] = []
    for index, value in enumerate(items):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"component {index} is not a real number")
        component = float(value)
        if not isfinite(component):
            raise VectorError(f"component {index} must be finite")
        result.append(component)
    return tuple(result)


def _finite_vector_result(values: Iterable[float], operation: str) -> Vector:
    result = tuple(values)
    if not all(isfinite(component) for component in result):
        raise OverflowError(f"{operation} produced a non-finite component")
    return result


def _pair(left: Iterable[Real], right: Iterable[Real]) -> tuple[Vector, Vector]:
    a = vector(left)
    b = vector(right)
    if len(a) != len(b):
        raise VectorError(f"dimension mismatch: {len(a)} != {len(b)}")
    return a, b


def add(left: Iterable[Real], right: Iterable[Real]) -> Vector:
    a, b = _pair(left, right)
    return _finite_vector_result(
        (x + y for x, y in zip(a, b, strict=True)), "vector addition"
    )


def subtract(left: Iterable[Real], right: Iterable[Real]) -> Vector:
    a, b = _pair(left, right)
    return _finite_vector_result(
        (x - y for x, y in zip(a, b, strict=True)), "vector subtraction"
    )


def scale(scalar: Real, values: Iterable[Real]) -> Vector:
    if isinstance(scalar, bool) or not isinstance(scalar, Real):
        raise TypeError("scalar must be a real number")
    scalar_float = float(scalar)
    if not isfinite(scalar_float):
        raise VectorError("scalar must be finite")

    return _finite_vector_result(
        (scalar_float * x for x in vector(values)), "scalar multiplication"
    )


def dot(left: Iterable[Real], right: Iterable[Real]) -> float:
    a, b = _pair(left, right)
    products = (x * y for x, y in zip(a, b, strict=True))
    try:
        result = fsum(products)
    except (OverflowError, ValueError) as exc:
        raise OverflowError("dot product overflowed finite float range") from exc
    if not isfinite(result):
        raise OverflowError("dot product is not finite")
    return result


def l2_norm(values: Iterable[Real]) -> float:
    result = hypot(*vector(values))
    if not isfinite(result):
        raise OverflowError("Euclidean norm exceeds finite float range")
    return result


def distance(left: Iterable[Real], right: Iterable[Real]) -> float:
    return l2_norm(subtract(left, right))


def normalize(values: Iterable[Real]) -> Vector:
    v = vector(values)
    length = l2_norm(v)
    if length == 0.0:
        raise VectorError("zero vector has no direction to normalize")
    return _finite_vector_result((x / length for x in v), "normalization")


def cosine_similarity(left: Iterable[Real], right: Iterable[Real]) -> float:
    a, b = _pair(left, right)
    value = dot(normalize(a), normalize(b))
    return max(-1.0, min(1.0, value))


def project(values: Iterable[Real], onto: Iterable[Real]) -> Vector:
    v, u = _pair(values, onto)
    direction = normalize(u)
    return scale(dot(v, direction), direction)
