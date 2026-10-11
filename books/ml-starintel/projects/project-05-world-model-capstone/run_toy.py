#!/usr/bin/env python3
"""Run the frozen synthetic BK10 capstone witness without external services."""
import argparse
from pathlib import Path
from capstone import run, stable_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional report.json destination")
    args = parser.parse_args()
    output = stable_json(run(Path(__file__).resolve().parent))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
