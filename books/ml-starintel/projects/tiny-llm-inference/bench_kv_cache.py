"""CPU-only, matched-output tiny attention KV-cache microbenchmark.

Emits actual measured observations. No model quality or production claims.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
import tracemalloc

from kv_cache import ToyCausalAttention, decode_cached, decode_uncached


def cpu_model_name() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as stream:
            for line in stream:
                if line.startswith("model name"):
                    return line.partition(":")[2].strip()
    except OSError:
        pass
    return platform.processor() or "unavailable"


def observe(fn, repeats: int, generated_tokens: int) -> dict:
    durations_ns: list[int] = []
    peak_bytes: list[int] = []
    output: tuple[int, ...] | None = None
    for _ in range(repeats):
        tracemalloc.start()
        start_ns = time.perf_counter_ns()
        produced = fn()
        elapsed_ns = time.perf_counter_ns() - start_ns
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if output is None:
            output = produced
        elif output != produced:
            raise AssertionError("repeated decode returned different tokens")
        durations_ns.append(elapsed_ns)
        peak_bytes.append(peak)
    median_s = statistics.median(durations_ns) / 1e9
    return {
        "median_elapsed_s": median_s,
        "median_generated_tokens_per_s": generated_tokens / median_s,
        "median_python_tracemalloc_peak_bytes": statistics.median(peak_bytes),
        "duration_ns_samples": durations_ns,
        "output_ids": list(output or ()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-length", type=int, default=16)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if min(args.prompt_length, args.steps, args.repeats) <= 0:
        parser.error("prompt-length, steps and repeats must be positive")
    model = ToyCausalAttention()
    prompt = tuple(i % model.vocab_size for i in range(args.prompt_length))
    original = decode_uncached(model, prompt, args.steps)
    candidate = decode_cached(model, prompt, args.steps)
    if original != candidate:
        raise AssertionError("prefix/cache token sequence mismatch")
    cached = observe(lambda: decode_cached(model, prompt, args.steps),
                     args.repeats, args.steps)
    uncached = observe(lambda: decode_uncached(model, prompt, args.steps),
                       args.repeats, args.steps)
    print(json.dumps({
        "status": "MEASURED on this process; stdlib toy one-head CPU reference",
        "utc_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "os_platform": platform.platform(),
        "python": platform.python_version(),
        "processor": cpu_model_name(),
        "logical_cpu_count_reported": os.cpu_count(),
        "model": {"kind": "ToyCausalAttention", "vocab_size": model.vocab_size,
                  "head_width": model.width, "trained": False},
        "settings": {"prompt_length": args.prompt_length,
                     "new_tokens": args.steps, "repeats": args.repeats,
                     "sampler": "greedy argmax lowest-id tie-break", "warmup": "one parity run each",
                     "timer": "perf_counter_ns", "memory": "Python traced allocations only"},
        "uncached": uncached,
        "cached": cached,
        "identical_output": True,
    }, indent=2))


if __name__ == "__main__":
    main()
