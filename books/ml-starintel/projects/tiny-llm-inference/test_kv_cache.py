"""Pure-stdlib tests for reference causal self-attention and immutable KV cache."""

import math
import unittest

from kv_cache import (KVCache, ToyCausalAttention, decode_cached,
                      decode_uncached, greedy)


class KVCacheTests(unittest.TestCase):
    def setUp(self):
        self.model = ToyCausalAttention()

    def test_single_token_parity(self):
        full = self.model.full_logits([4])
        cached, cache = self.model.step(4, self.model.empty_cache())
        for a, b in zip(full, cached, strict=True):
            self.assertAlmostEqual(a, b, places=13)
        self.assertEqual(cache.length, 1)

    def test_multi_token_prefix_parity(self):
        prefix = []
        cache = self.model.empty_cache()
        for token in [1, 3, 3, 7, 0, 10, 2, 5, 1, 8]:
            prefix.append(token)
            cached, cache = self.model.step(token, cache)
            full = self.model.full_logits(prefix)
            self.assertEqual(len(cached), self.model.vocab_size)
            for a, b in zip(cached, full, strict=True):
                self.assertAlmostEqual(a, b, places=13)
        self.assertEqual(cache.length, len(prefix))
        self.assertEqual(cache.scalar_count, len(prefix) * 2 * self.model.width)

    def test_cache_immutable_and_branchable(self):
        start = self.model.empty_cache()
        _, one = self.model.step(1, start)
        logits_a, left = self.model.step(2, one)
        logits_b, right = self.model.step(7, one)
        self.assertEqual(start.length, 0)
        self.assertEqual(one.length, 1)
        self.assertEqual(left.length, 2)
        self.assertEqual(right.length, 2)
        self.assertNotEqual(logits_a, logits_b)
        self.assertNotEqual(left.keys[-1], right.keys[-1])

    def test_greedy_prefix_decode_equivalent(self):
        for prompt in ([1], [2, 4, 6], [3, 0, 0, 7]):
            self.assertEqual(decode_uncached(self.model, prompt, 8),
                             decode_cached(self.model, prompt, 8))

    def test_zero_steps_still_validate(self):
        self.assertEqual(decode_cached(self.model, [2], 0), (2,))
        with self.assertRaises(ValueError):
            decode_cached(self.model, [999], 0)
        with self.assertRaises(ValueError):
            decode_uncached(self.model, [999], 0)

    def test_bad_token_and_prefix_rejected(self):
        for bad in [-1, 11, 1.0, True, None]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.model.step(bad, self.model.empty_cache())
        with self.assertRaises(ValueError):
            self.model.full_logits([])
        with self.assertRaises(ValueError):
            decode_cached(self.model, [], 3)
        with self.assertRaises(ValueError):
            decode_uncached(self.model, [], 3)
        with self.assertRaises(ValueError):
            decode_cached(self.model, [1], -1)

    def test_invalid_cache_rejected(self):
        with self.assertRaises(ValueError):
            KVCache(keys=((1.0,),), values=())
        with self.assertRaises(ValueError):
            KVCache(keys=((1.0,), (1.0, 2.0)), values=((1.0,), (1.0, 2.0)))
        with self.assertRaises(ValueError):
            self.model.step(1, KVCache(keys=((0.0,),), values=((0.0,),)))
        with self.assertRaises(TypeError):
            self.model.step(1, None)

    def test_tie_breaking_and_nonfinite_logits(self):
        self.assertEqual(greedy([1.0, 1.0, -2.0]), 0)
        for bad in ([], [math.nan], [math.inf], [-math.inf]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                greedy(bad)

    def test_model_parameter_validation(self):
        with self.assertRaises(ValueError):
            ToyCausalAttention(vocab_size=1)
        with self.assertRaises(ValueError):
            ToyCausalAttention(width=0)

    def test_prompt_not_mutated(self):
        original = [4, 5]
        decode_cached(self.model, original, 2)
        self.assertEqual(original, [4, 5])


if __name__ == "__main__":
    unittest.main()
