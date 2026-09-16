from __future__ import annotations

from collections.abc import Iterable, Sequence
from math import fsum
from numbers import Integral, Real

from vector_toolkit import Vector, dot, scale, vector

Matrix = tuple[tuple[float, ...], ...]


class MatrixError(ValueError):
    """Raised when a matrix violates the toolkit's rectangular finite-real contract."""


def matrix(rows: Iterable[Iterable[Real]]) -> Matrix:
    """Return an immutable, non-empty rectangular matrix of finite reals."""
    if isinstance(rows, (str, bytes)):
        raise TypeError("matrix rows must be an iterable of row iterables")

    raw_rows = tuple(rows)
    if not raw_rows:
        raise MatrixError("matrices must have at least one row")

    converted = tuple(vector(row) for row in raw_rows)
    width = len(converted[0])
    for index, row in enumerate(converted[1:], start=1):
        if len(row) != width:
            raise MatrixError(
                f"ragged matrix: row 0 has length {width}, row {index} has length {len(row)}"
            )
    return converted


def shape(values: Iterable[Iterable[Real]]) -> tuple[int, int]:
    """Return ``(rows, columns)`` for an admitted matrix."""
    m = matrix(values)
    return len(m), len(m[0])


def column(values: Iterable[Iterable[Real]], index: int) -> Vector:
    """Return one zero-based matrix column."""
    if isinstance(index, bool) or not isinstance(index, Integral):
        raise TypeError("column index must be an integer")
    m = matrix(values)
    if index < 0 or index >= len(m[0]):
        raise MatrixError(f"column index out of range: {index}")
    return tuple(row[index] for row in m)


def transpose(values: Iterable[Iterable[Real]]) -> Matrix:
    """Swap matrix rows and columns."""
    m = matrix(values)
    return tuple(tuple(row[j] for row in m) for j in range(len(m[0])))


def _matvec_admitted(m: Matrix, v: Vector) -> Vector:
    if len(m[0]) != len(v):
        raise MatrixError(
            f"matrix-vector dimension mismatch: matrix has {len(m[0])} columns, "
            f"vector has dimension {len(v)}"
        )
    return vector(dot(row, v) for row in m)


def matvec(values: Iterable[Iterable[Real]], coefficients: Iterable[Real]) -> Vector:
    """Multiply a matrix by a column vector using row dot products."""
    return _matvec_admitted(matrix(values), vector(coefficients))


def column_combination(
    values: Iterable[Iterable[Real]], coefficients: Iterable[Real]
) -> Vector:
    """Compute the same matrix-vector product as a linear combination of columns."""
    m = matrix(values)
    coeffs = vector(coefficients)
    if len(m[0]) != len(coeffs):
        raise MatrixError(
            f"column-combination dimension mismatch: matrix has {len(m[0])} columns, "
            f"coefficient vector has dimension {len(coeffs)}"
        )

    columns = tuple(column(m, j) for j in range(len(coeffs)))
    scaled_columns = tuple(
        scale(coefficient, col)
        for coefficient, col in zip(coeffs, columns, strict=True)
    )
    try:
        return vector(
            fsum(col[i] for col in scaled_columns)
            for i in range(len(m))
        )
    except (OverflowError, ValueError) as exc:
        raise OverflowError("column combination overflowed finite float range") from exc


def matmul(
    left: Iterable[Iterable[Real]], right: Iterable[Iterable[Real]]
) -> Matrix:
    """Return the conventional matrix product ``left @ right``."""
    a = matrix(left)
    b = matrix(right)
    if len(a[0]) != len(b):
        raise MatrixError(
            f"matrix multiplication dimension mismatch: {len(a)}x{len(a[0])} cannot "
            f"multiply {len(b)}x{len(b[0])}"
        )

    b_columns = transpose(b)
    return matrix(tuple(dot(row, col) for col in b_columns) for row in a)


def identity(size: int) -> Matrix:
    """Return a square identity matrix of positive ``size``."""
    if isinstance(size, bool) or not isinstance(size, Integral):
        raise TypeError("identity size must be an integer")
    if size <= 0:
        raise MatrixError("identity size must be positive")
    return tuple(
        tuple(1.0 if row == col else 0.0 for col in range(size))
        for row in range(size)
    )


def transform_points(
    values: Iterable[Iterable[Real]], points: Iterable[Sequence[Real]]
) -> tuple[Vector, ...]:
    """Apply one matrix to a finite collection of points/vectors."""
    m = matrix(values)
    admitted_points = tuple(vector(point) for point in points)
    return tuple(_matvec_admitted(m, point) for point in admitted_points)
