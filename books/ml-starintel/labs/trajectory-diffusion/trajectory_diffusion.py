"""BK06: conditional trajectory diffusion on entirely synthetic event observations.

A fitted two-component Gaussian residual density supplies an *analytic* denoiser.
This is deliberately not a neural-network denoiser nor a validated StarIntel wire
adapter. It isolates multimodal conditional reverse diffusion from architecture.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

HISTORY = 4
HORIZON = 6


@dataclass(frozen=True)
class Episode:
    episode_id: str
    history: tuple[float, ...]
    future: tuple[float, ...]
    events: tuple[dict[str, Any], ...]


def synthetic_events(count: int = 208, seed: int = 148) -> tuple[Episode, ...]:
    """Create deterministic Tier-C records; no person/device/location provenance."""
    if count < 2:
        raise ValueError("count must support separate train/test episodes")
    rng = np.random.default_rng(seed)
    result: list[Episode] = []
    for number in range(count):
        episode_id = f"synthetic-episode-{number:04d}"
        offset = rng.uniform(-2.0, 2.0)
        drift = rng.uniform(0.08, 0.24)
        direction = -1.0 if rng.random() < 0.5 else 1.0
        observed = offset + drift * np.arange(HISTORY) + rng.normal(0, 0.015, HISTORY)
        steps = np.arange(1, HORIZON + 1, dtype=float)
        future = (offset + drift * (HISTORY - 1 + steps)
                  + direction * 0.52 * steps
                  + rng.normal(0, 0.075, HORIZON))
        readings = np.concatenate((observed, future))
        events = tuple({
            "event_id": f"{episode_id}-tick-{t:02d}",
            "episode_id": episode_id,
            "time_index": t,
            "kind": "synthetic_numeric_observation",
            "measurement": float(v),
            "provenance_tier": "C-synthetic",
        } for t, v in enumerate(readings))
        result.append(Episode(episode_id, tuple(map(float, observed)),
                              tuple(map(float, future)), events))
    return tuple(result)


def split_episodes(episodes: tuple[Episode, ...], train_count: int) -> tuple[tuple[Episode, ...], tuple[Episode, ...]]:
    if not 2 <= train_count < len(episodes):
        raise ValueError("train_count must leave independent held-out episodes")
    training, test = episodes[:train_count], episodes[train_count:]
    if {x.episode_id for x in training} & {x.episode_id for x in test}:
        raise ValueError("train/test episode overlap")
    return training, test


def _history_array(history: tuple[float, ...] | np.ndarray) -> np.ndarray:
    x = np.asarray(history, dtype=float)
    if x.shape != (HISTORY,) or not np.isfinite(x).all():
        raise ValueError(f"history must be {HISTORY} finite observations")
    return x


def observed_trend(history: tuple[float, ...] | np.ndarray) -> np.ndarray:
    x = _history_array(history)
    velocity = (x[-1] - x[0]) / (HISTORY - 1)
    return x[-1] + np.arange(1, HORIZON + 1) * velocity


@dataclass(frozen=True)
class ARBaseline:
    coefficients: np.ndarray

    @classmethod
    def fit(cls, episodes: tuple[Episode, ...]) -> "ARBaseline":
        if len(episodes) < 2:
            raise ValueError("need at least two training episodes")
        features: list[list[float]] = []
        labels: list[float] = []
        for episode in episodes:
            path = (*episode.history, *episode.future)
            for t in range(2, len(path)):
                features.append([1.0, path[t - 1], path[t - 1] - path[t - 2]])
                labels.append(path[t])
        x = np.asarray(features)
        y = np.asarray(labels)
        ridge = np.eye(3) * 1e-5
        ridge[0, 0] = 0.0
        return cls(np.linalg.solve(x.T @ x + ridge, x.T @ y))

    def forecast(self, history: tuple[float, ...]) -> np.ndarray:
        x = _history_array(history)
        prev, last = float(x[-2]), float(x[-1])
        predicted: list[float] = []
        for _ in range(HORIZON):
            value = float(self.coefficients @ np.array([1.0, last, last - prev]))
            predicted.append(value)
            prev, last = last, value
        return np.asarray(predicted)


@dataclass(frozen=True)
class FittedMixture:
    component_means: np.ndarray  # [2, horizon], standardized residuals
    weights: np.ndarray          # fitted component prevalence, [2]
    variance: float              # shared isotropic within-component variance
    scale: float                 # training-only endpoint normalization

    @classmethod
    def fit(cls, episodes: tuple[Episode, ...]) -> "FittedMixture":
        if len(episodes) < 8:
            raise ValueError("need eight or more training episodes")
        residuals = np.stack([np.asarray(ep.future) - observed_trend(ep.history) for ep in episodes])
        scale = max(float(np.std(residuals[:, -1])), 0.05)
        data = residuals / scale
        means = np.stack((data[np.argmin(data[:, -1])], data[np.argmax(data[:, -1])]))
        for _ in range(64):
            distances = np.sum((data[:, None, :] - means[None, :, :]) ** 2, axis=-1)
            labels = np.argmin(distances, axis=1)
            if not np.any(labels == 0) or not np.any(labels == 1):
                raise ValueError("training density lacks two nonempty modes")
            updated = np.stack([data[labels == i].mean(axis=0) for i in range(2)])
            if np.allclose(means, updated, rtol=0, atol=1e-12):
                means = updated
                break
            means = updated
        counts = np.bincount(labels, minlength=2)
        weights = counts / len(data)
        variance = max(float(np.mean((data - means[labels]) ** 2)), 1e-4)
        return cls(means, weights, variance, scale)


@dataclass(frozen=True)
class ConditionalDiffusion:
    density: FittedMixture
    betas: np.ndarray
    alpha_bars: np.ndarray

    @classmethod
    def fit(cls, episodes: tuple[Episode, ...], steps: int = 64) -> "ConditionalDiffusion":
        if steps < 8:
            raise ValueError("too few reverse diffusion steps")
        betas = np.linspace(0.02, 0.18, steps)
        alpha_bars = np.cumprod(1 - betas)
        return cls(FittedMixture.fit(episodes), betas, alpha_bars)

    def denoise_x0(self, x_t: np.ndarray, step_index: int) -> np.ndarray:
        """Compute E[x_0 | x_t] for a fitted Gaussian mixture (no oracle labels)."""
        if x_t.ndim != 2 or x_t.shape[1] != HORIZON:
            raise ValueError("x_t must be [samples, horizon]")
        if not 0 <= step_index < len(self.betas):
            raise ValueError("noise step out of range")
        abar = float(self.alpha_bars[step_index])
        sigma2 = self.density.variance
        variance_t = abar * sigma2 + 1 - abar
        means = self.density.component_means
        deviation = x_t[:, None, :] - np.sqrt(abar) * means[None, :, :]
        logp = (np.log(self.density.weights)[None, :]
                - 0.5 * np.sum(deviation * deviation, axis=2) / variance_t)
        logp -= np.max(logp, axis=1, keepdims=True)
        posterior_weights = np.exp(logp)
        posterior_weights /= posterior_weights.sum(axis=1, keepdims=True)
        component_posteriors = (means[None, :, :]
                                + np.sqrt(abar) * sigma2 / variance_t * deviation)
        return np.sum(posterior_weights[:, :, None] * component_posteriors, axis=1)

    def forecast(self, history: tuple[float, ...], samples: int, seed: int) -> np.ndarray:
        if not 1 <= samples <= 4096:
            raise ValueError("samples must be in [1,4096]")
        trend = observed_trend(history)  # the only per-episode conditioning input
        rng = np.random.default_rng(seed)
        x = rng.standard_normal((samples, HORIZON))
        for index in range(len(self.betas) - 1, -1, -1):
            beta = float(self.betas[index])
            alpha = 1 - beta
            abar = float(self.alpha_bars[index])
            posterior_x0 = self.denoise_x0(x, index)
            predicted_epsilon = (x - np.sqrt(abar) * posterior_x0) / np.sqrt(1 - abar)
            reverse_mean = (x - beta / np.sqrt(1 - abar) * predicted_epsilon) / np.sqrt(alpha)
            if index:
                previous_abar = float(self.alpha_bars[index - 1])
                posterior_var = beta * (1 - previous_abar) / (1 - abar)
                x = reverse_mean + np.sqrt(posterior_var) * rng.standard_normal(x.shape)
            else:
                x = reverse_mean
        return trend[None, :] + self.density.scale * x


def energy_score(samples: np.ndarray, truth: np.ndarray) -> float:
    """Finite-sample energy score; smaller is better. Deterministic K=1 is L2."""
    samples = np.asarray(samples, dtype=float)
    truth = np.asarray(truth, dtype=float)
    if samples.ndim != 2 or samples.shape[1] != HORIZON or truth.shape != (HORIZON,):
        raise ValueError("wrong forecast/truth dimensions")
    first = np.linalg.norm(samples - truth[None, :], axis=1).mean()
    # Biased but consistent fixed K Monte Carlo estimator of 0.5 E||X-X'||.
    pair = np.linalg.norm(samples[:, None, :] - samples[None, :, :], axis=2)
    return float(first - 0.5 * pair.mean())


def evaluate(train: tuple[Episode, ...], test: tuple[Episode, ...], seed: int = 148,
             draws: int = 16) -> dict[str, float | int | str]:
    if not train or not test:
        raise ValueError("need train and held-out test episodes")
    if {x.episode_id for x in train} & {x.episode_id for x in test}:
        raise ValueError("episode train/test overlap")
    baseline = ARBaseline.fit(train)
    diffusion = ConditionalDiffusion.fit(train)
    ar_ade, diff_ade, min_ade, diff_sample_ade = [], [], [], []
    ar_energy, diff_energy, diversity, coverage = [], [], [], []
    for i, episode in enumerate(test):
        y = np.asarray(episode.future)
        base = baseline.forecast(episode.history)
        forecasts = diffusion.forecast(episode.history, draws, seed + i)
        ar_ade.append(float(np.mean(np.abs(base - y))))
        diff_ade.append(float(np.mean(np.abs(forecasts.mean(axis=0) - y))))
        errors = np.mean(np.abs(forecasts - y), axis=1)
        min_ade.append(float(errors.min()))
        diff_sample_ade.append(float(errors.mean()))
        ar_energy.append(energy_score(base[None, :], y))
        diff_energy.append(energy_score(forecasts, y))
        diversity.append(float(np.mean(np.abs(forecasts[:, None, -1] - forecasts[None, :, -1]))))
        coverage.append(float(np.any(np.abs(forecasts[:, -1] - y[-1]) <= 0.5)))
    metrics = {
        "status": "TESTED_SYNTHETIC_ONLY",
        "seed": seed,
        "n_train": len(train),
        "n_test": len(test),
        "draws_per_history": draws,
        "reverse_steps": len(diffusion.betas),
        "ar_ade": np.mean(ar_ade),
        "diffusion_mean_ade": np.mean(diff_ade),
        "diffusion_one_draw_ade": np.mean(diff_sample_ade),
        "diffusion_oracle_minade_at_k": np.mean(min_ade),
        "ar_energy": np.mean(ar_energy),
        "diffusion_energy": np.mean(diff_energy),
        "diffusion_endpoint_pairwise_abs": np.mean(diversity),
        "diffusion_endpoint_coverage_0p5": np.mean(coverage),
    }
    return {key: round(float(value), 6) if isinstance(value, (float, np.floating)) else value
            for key, value in metrics.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic conditional trajectory diffusion lab")
    parser.add_argument("--seed", type=int, default=148)
    parser.add_argument("--episodes", type=int, default=208)
    parser.add_argument("--train", type=int, default=160)
    parser.add_argument("--draws", type=int, default=16)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--events-jsonl", type=Path, help="optional complete Tier-C train/test stream")
    args = parser.parse_args()
    episodes = synthetic_events(args.episodes, args.seed)
    train, test = split_episodes(episodes, args.train)
    report = evaluate(train, test, args.seed, args.draws)
    if args.events_jsonl:
        args.events_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.events_jsonl.open("w", encoding="utf-8") as stream:
            for split_name, partition in (("train", train), ("test", test)):
                for episode in partition:
                    for event in episode.events:
                        stream.write(json.dumps({"split": split_name, **event}, sort_keys=True) + "\n")
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
