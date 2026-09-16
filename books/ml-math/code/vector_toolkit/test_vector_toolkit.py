import math
import unittest

import numpy as np

from vector_toolkit import (
    VectorError,
    add,
    cosine_similarity,
    distance,
    dot,
    l2_norm,
    normalize,
    project,
    scale,
    subtract,
    vector,
)


class VectorToolkitTests(unittest.TestCase):
    def test_vector_is_immutable_float_tuple(self):
        self.assertEqual(vector([1, 2.5, -3]), (1.0, 2.5, -3.0))

    def test_invalid_components_are_rejected(self):
        for bad in ([], [True], [float("nan")], [float("inf")], ["3"]):
            with self.subTest(bad=bad):
                with self.assertRaises((TypeError, VectorError)):
                    vector(bad)

    def test_add_subtract_and_scale(self):
        self.assertEqual(add([1, 2], [3, -5]), (4.0, -3.0))
        self.assertEqual(subtract([1, 2], [3, -5]), (-2.0, 7.0))
        self.assertEqual(scale(-2, [1.5, -4]), (-3.0, 8.0))

    def test_dimension_mismatch_is_explicit(self):
        for fn in (add, subtract, dot, distance, cosine_similarity, project):
            with self.subTest(fn=fn.__name__):
                with self.assertRaises(VectorError):
                    fn([1, 2], [1])

    def test_dot_uses_accurate_summation(self):
        self.assertEqual(dot([1e16, 1, 1e16], [1, 1, -1]), 1.0)

    def test_l2_norm_and_distance(self):
        self.assertEqual(l2_norm([3, 4]), 5.0)
        self.assertEqual(distance([1, 1], [4, 5]), 5.0)

    def test_large_norm_avoids_naive_intermediate_overflow(self):
        length = l2_norm([1e308, 1e308])
        self.assertTrue(math.isfinite(length))
        self.assertAlmostEqual(length / 1e308, math.sqrt(2), places=15)

    def test_normalize_and_zero_rejection(self):
        unit = normalize([3, 4])
        self.assertAlmostEqual(l2_norm(unit), 1.0, places=15)
        with self.assertRaises(VectorError):
            normalize([0, 0])

    def test_cosine_similarity_geometry(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 2]), 0.0, places=15)
        self.assertAlmostEqual(cosine_similarity([1, 2], [2, 4]), 1.0, places=15)
        self.assertAlmostEqual(cosine_similarity([1, 2], [-2, -4]), -1.0, places=15)

    def test_projection_leaves_orthogonal_residual(self):
        v = [3, 4]
        u = [2, 0]
        projection = project(v, u)
        residual = subtract(v, projection)
        self.assertAlmostEqual(dot(residual, u), 0.0, places=15)
        self.assertEqual(projection, (3.0, 0.0))

    def test_matches_numpy_reference_operations(self):
        cases = [
            ([1.25, -2.0, 3.5], [4.0, 0.5, -1.0]),
            ([-1000.0, 1e-6, 7.0], [2.0, -3.0, 11.0]),
        ]
        for a, b in cases:
            with self.subTest(a=a, b=b):
                np.testing.assert_allclose(
                    add(a, b), np.asarray(a) + np.asarray(b), rtol=0, atol=0
                )
                np.testing.assert_allclose(
                    subtract(a, b), np.asarray(a) - np.asarray(b), rtol=0, atol=0
                )
                self.assertAlmostEqual(dot(a, b), float(np.dot(a, b)), places=12)
                self.assertAlmostEqual(
                    l2_norm(a), float(np.linalg.vector_norm(a)), places=12
                )
                self.assertAlmostEqual(
                    distance(a, b),
                    float(np.linalg.vector_norm(np.asarray(a) - np.asarray(b))),
                    places=12,
                )

    def test_projection_matches_numpy_formula(self):
        v = np.array([2.0, -1.0, 4.0])
        u = np.array([1.0, 2.0, 2.0])
        expected = (np.dot(v, u) / np.dot(u, u)) * u
        np.testing.assert_allclose(
            project(v.tolist(), u.tolist()), expected, rtol=1e-12, atol=1e-12
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
