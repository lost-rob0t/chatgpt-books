#!/usr/bin/env python3
"""Execute the predeclared Project 1 larger-public-corpus candidate benchmark."""

from pathlib import Path

from public_candidate_benchmark import run_public_benchmark, write_result


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "artifacts" / "candidate-generation-20newsgroups.json"


def main() -> None:
    result = run_public_benchmark()
    write_result(result, OUTPUT)
    print(f"wrote {OUTPUT}")
    print(f"records={result['record_count']} all_pairs={result['all_pair_count']}")
    print(f"exact_qualifying_pairs={result['exact_qualifying_pair_count']}")
    for entry in result["grid"]:
        print(
            "num_perm={num_perm} candidates={candidate_pair_count} "
            "recall={qualifying_pair_recall:.6f} "
            "lsh_recall={minhash_lsh_qualifying_pair_recall:.6f} "
            "reduction={pair_reduction_fraction:.6f} "
            "components_equal={component_equality} "
            "seconds={candidate_seconds:.6f} peak_bytes={python_traced_peak_bytes}".format(
                **entry
            )
        )


if __name__ == "__main__":
    main()
