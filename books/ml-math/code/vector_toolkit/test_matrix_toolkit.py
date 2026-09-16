import unittest

import numpy as np

from vector_toolkit import add, scale
from matrix_toolkit import (
    MatrixError,
    column,
    column_combination,
    identity,
    matrix,
    matmul,
    matvec,
    shape,
    transform_points,
    transpose,
)


class MatrixToolkitTests(unittest.TestCase):
    def test_matrix_is_immutable_rectangular_float_tuple(self):
        admitted = matrix([[1, 2.5], [-3, 4]])
        self.assertEqual(admitted, ((1.0, 2.5), (-3.0, 4.0)))
        self.assertEqual(shape(admitted), (2, 2))

    def test_invalid_matrix_boundaries_are_rejected(self):
        cases = (
            [],
            [[]],
            [[1, 2], [3]],
            [[1, True]],
            [[1, float("nan")]],
            [[1, float("inf")]],
            [[1, "2"]],
        )
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises((TypeError, ValueError)):
                    matrix(bad)

    def test_column_and_transpose_make_indexing_explicit(self):
        values = [[1, 2, 3], [4, 5, 6]]
        self.assertEqual(column(values, 1), (2.0, 5.0))
        self.assertEqual(transpose(values), ((1.0, 4.0), (2.0, 5.0), (3.0, 6.0)))
        with self.assertRaises(MatrixError):
            column(values, 3)
        with self.assertRaises(TypeError):
            column(values, True)

    def test_matrix_vector_multiplication_by_row_dot_products(self):
        values = [[2, -1, 3], [0, 4, 1]]
        self.assertEqual(matvec(values, [5, 2, -1]), (5.0, 7.0))

    def test_matrix_vector_dimension_mismatch_is_explicit(self):
        with self.assertRaises(MatrixError):
            matvec([[1, 2], [3, 4]], [1, 2, 3])
        with self.assertRaises(MatrixError):
            column_combination([[1, 2], [3, 4]], [1])

    def test_matrix_vector_equals_linear_combination_of_columns(self):
        values = [[1, 4, -2], [3, 0, 5]]
        coefficients = [2, -1, 0.5]
        self.assertEqual(
            matvec(values, coefficients), column_combination(values, coefficients)
        )

    def test_matrix_multiplication_uses_row_by_column_products(self):
        left = [[1, 2, 3], [4, 5, 6]]
        right = [[7, 8], [9, 10], [11, 12]]
        self.assertEqual(matmul(left, right), ((58.0, 64.0), (139.0, 154.0)))

    def test_matrix_multiplication_dimension_mismatch_is_explicit(self):
        with self.assertRaises(MatrixError):
            matmul([[1, 2]], [[1, 2]])

    def test_matrix_multiplication_is_not_generally_commutative(self):
        a = [[1, 1], [0, 1]]
        b = [[1, 0], [1, 1]]
        self.assertNotEqual(matmul(a, b), matmul(b, a))

    def test_matrix_multiplication_matches_function_composition_order(self):
        a = [[1, 2], [0, 1]]
        b = [[2, 0], [1, 3]]
        x = [4, -2]
        self.assertEqual(matvec(matmul(a, b), x), matvec(a, matvec(b, x)))

    def test_identity_is_neutral(self):
        a = [[2, -1], [3, 4]]
        i = identity(2)
        self.assertEqual(matmul(i, a), matrix(a))
        self.assertEqual(matmul(a, i), matrix(a))
        self.assertEqual(matvec(i, [8, -3]), (8.0, -3.0))
        for bad in (0, -1):
            with self.subTest(bad=bad):
                with self.assertRaises(MatrixError):
                    identity(bad)

    def test_overflow_from_finite_inputs_fails_closed(self):
        with self.assertRaises(OverflowError):
            matvec([[1e308, 1e308]], [2, 2])
        with self.assertRaises(OverflowError):
            matmul([[1e308, 1e308]], [[2], [2]])

    def test_matches_numpy_matrix_vector_and_matrix_products(self):
        a = [[1.25, -2.0, 3.5], [0.5, 7.0, -1.0]]
        x = [4.0, 0.5, -1.0]
        b = [[2.0, -1.0], [0.25, 3.0], [4.0, 2.0]]

        np.testing.assert_allclose(matvec(a, x), np.asarray(a) @ np.asarray(x))
        np.testing.assert_allclose(matmul(a, b), np.asarray(a) @ np.asarray(b))

    def test_basis_images_are_matrix_columns(self):
        values = [[2, -1], [3, 4], [5, 0]]
        self.assertEqual(matvec(values, [1, 0]), column(values, 0))
        self.assertEqual(matvec(values, [0, 1]), column(values, 1))

    def test_matrix_map_preserves_addition_and_scaling(self):
        values = [[2, -1], [0.5, 3]]
        u = [4, -2]
        v = [-1, 5]
        scalar = -2.5
        self.assertEqual(
            matvec(values, add(u, v)),
            add(matvec(values, u), matvec(values, v)),
        )
        self.assertEqual(
            matvec(values, scale(scalar, u)),
            scale(scalar, matvec(values, u)),
        )

    def test_matrix_multiplication_is_associative_for_compatible_example(self):
        a = [[1, 2], [0, 1]]
        b = [[2, 0, -1], [1, 3, 2]]
        c = [[1, 0], [2, 1], [-1, 4]]
        self.assertEqual(matmul(matmul(a, b), c), matmul(a, matmul(b, c)))

    def test_transform_points_uses_one_linear_map_consistently(self):
        shear = [[1, 0.5], [0, 1]]
        points = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.assertEqual(
            transform_points(shear, points),
            ((0.0, 0.0), (1.0, 0.0), (1.5, 1.0), (0.5, 1.0)),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
