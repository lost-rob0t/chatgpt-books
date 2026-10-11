"""Single-layer causal attention reference with exact-prefix KV-cache equivalence.

This is a deterministic educational oracle, not an optimized production transformer.
BK03 can implement PrefixModel and CachedModel to reuse the harness without sharing
training code. No NumPy, pretrained weights, GPU, or network are needed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, Sequence


Vector = tuple[float, ...]


class PrefixModel(Protocol):
    """Return next-token logits for a nonempty prefix."""

    vocab_size: int

    def full_logits(self, prefix: Sequence[int]) -> Vector: ...


class CachedModel(PrefixModel, Protocol):
    """Cache is immutable; step consumes exactly one new token."""

    def empty_cache(self) -> "KVCache": ...

    def step(self, token: int, cache: "KVCache") -> tuple[Vector, "KVCache"]: ...


@dataclass(frozen=True, slots=True)
class KVCache:
    keys: tuple[Vector, ...] = ()
    values: tuple[Vector, ...] = ()

    def __post_init__(self) -> None:
        if len(self.keys) != len(self.values):
            raise ValueError("keys and values must have equal sequence length")
        if self.keys:
            width = len(self.keys[0])
            if width == 0 or any(len(x) != width for x in self.keys + self.values):
                raise ValueError("all cache vectors must have the same nonzero width")

    @property
    def length(self) -> int:
        return len(self.keys)

    @property
    def scalar_count(self) -> int:
        """Theoretical scalar count; not an actual Python memory measurement."""
        return sum(map(len, self.keys)) + sum(map(len, self.values))


def _dot(a: Vector, b: Vector) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def _softmax(logits: Sequence[float]) -> Vector:
    if not logits:
        raise ValueError("attention must have at least one key")
    m = max(logits)
    exps = tuple(math.exp(x - m) for x in logits)
    z = math.fsum(exps)
    return tuple(x / z for x in exps)


@dataclass(frozen=True, slots=True)
class ToyCausalAttention:
    """One causal self-attention head plus a deterministic output projection.

    No token-position dependence and no learned weights. This is intentional: the
    only changing state is the prefix and its key/value projections, so the
    reference makes caching behavior independently verifiable.
    """

    vocab_size: int = 11
    width: int = 4

    def __post_init__(self) -> None:
        if self.vocab_size < 2 or self.width < 1:
            raise ValueError("vocab_size >= 2 and width >= 1 required")

    def empty_cache(self) -> KVCache:
        return KVCache()

    def _validate(self, token: int) -> None:
        if type(token) is not int or not 0 <= token < self.vocab_size:
            raise ValueError("token must be an in-vocabulary integer")

    def _embed(self, token: int) -> Vector:
        return tuple(math.sin((token + 1) * (i + 1) * 0.37) for i in range(self.width))

    def _project(self, embedding: Vector, role: int) -> Vector:
        # Three distinct deterministic projections; deliberately nonidentity.
        return tuple(
            math.fsum(embedding[j] * math.cos((j + 1) * (i + 1 + role) * 0.31)
                      for j in range(self.width)) / self.width
            for i in range(self.width)
        )

    def _qkv(self, token: int) -> tuple[Vector, Vector, Vector]:
        self._validate(token)
        emb = self._embed(token)
        return (self._project(emb, 1), self._project(emb, 2),
                self._project(emb, 3))

    def _attend(self, query: Vector, keys: tuple[Vector, ...],
                values: tuple[Vector, ...]) -> Vector:
        scale = 1.0 / math.sqrt(self.width)
        weights = _softmax(tuple(_dot(query, key) * scale for key in keys))
        return tuple(math.fsum(weight * value[i] for weight, value
                               in zip(weights, values, strict=True))
                     for i in range(self.width))

    def _logits(self, hidden: Vector) -> Vector:
        return tuple(math.fsum(hidden[i] * math.sin((token + 1) * (i + 1) * 0.29)
                               for i in range(self.width))
                     for token in range(self.vocab_size))

    def full_logits(self, prefix: Sequence[int]) -> Vector:
        if not prefix:
            raise ValueError("prefix must not be empty")
        # Real quadratic reference: compute all causal positions from scratch.
        qkv = tuple(self._qkv(token) for token in prefix)
        outputs = tuple(
            self._attend(qkv[j][0], tuple(t[1] for t in qkv[:j + 1]),
                         tuple(t[2] for t in qkv[:j + 1]))
            for j in range(len(qkv))
        )
        return self._logits(outputs[-1])

    def step(self, token: int, cache: KVCache) -> tuple[Vector, KVCache]:
        if not isinstance(cache, KVCache):
            raise TypeError("cache must be KVCache")
        if cache.length and len(cache.keys[0]) != self.width:
            raise ValueError("cache width does not match model")
        query, key, value = self._qkv(token)
        next_cache = KVCache(cache.keys + (key,), cache.values + (value,))
        hidden = self._attend(query, next_cache.keys, next_cache.values)
        return self._logits(hidden), next_cache


def greedy(logits: Sequence[float]) -> int:
    """Argmax with smallest-token tie breaking; reject nonfinite scores."""
    if not logits or any(not math.isfinite(x) for x in logits):
        raise ValueError("logits must be nonempty and finite")
    return max(range(len(logits)), key=lambda i: (logits[i], -i))


def decode_uncached(model: PrefixModel, prompt: Sequence[int], steps: int) -> tuple[int, ...]:
    if not prompt or steps < 0:
        raise ValueError("nonempty prompt and steps >= 0 required")
    tokens = tuple(prompt)
    if steps == 0:
        model.full_logits(tokens)  # Validate the prompt through the model.
    for _ in range(steps):
        tokens += (greedy(model.full_logits(tokens)),)
    return tokens


def decode_cached(model: CachedModel, prompt: Sequence[int], steps: int) -> tuple[int, ...]:
    if not prompt or steps < 0:
        raise ValueError("nonempty prompt and steps >= 0 required")
    tokens = tuple(prompt)
    cache = model.empty_cache()
    for token in prompt:
        logits, cache = model.step(token, cache)
    for index in range(steps):
        new_token = greedy(logits)
        tokens += (new_token,)
        if index + 1 < steps:
            logits, cache = model.step(new_token, cache)
    return tokens
