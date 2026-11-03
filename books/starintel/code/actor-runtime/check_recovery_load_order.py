#!/usr/bin/env python3
"""Audit the exact StarIntel startup/recovery source boundary.

This is deliberately a source-evidence guard, not a process-restart simulator.
It fails closed if the serial ASDF order or either START-ACTORS definition stops
matching the boundary researched by the book.
"""

from __future__ import annotations

import argparse
from pathlib import Path

RECOVERY_COMPONENT = '(:file "target-recovery")'
LIFECYCLE_COMPONENT = '(:file "runtime-lifecycle")'
START_FORM = "(defun start-actors"
RECOVERY_CALL = "recover-persisted-targets"


def extract_list_form(text: str, marker: str) -> str:
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"missing form marker: {marker}")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise RuntimeError(f"unterminated list form starting at: {marker}")


def audit(server_root: Path) -> dict[str, bool]:
    asd_text = (server_root / "source/starintel-gserver.asd").read_text(
        encoding="utf-8"
    )
    recovery_text = (server_root / "source/target-recovery.lisp").read_text(
        encoding="utf-8"
    )
    lifecycle_text = (server_root / "source/runtime-lifecycle.lisp").read_text(
        encoding="utf-8"
    )

    recovery_index = asd_text.find(RECOVERY_COMPONENT)
    lifecycle_index = asd_text.find(LIFECYCLE_COMPONENT)
    if recovery_index < 0 or lifecycle_index < 0:
        raise RuntimeError("missing target-recovery/runtime-lifecycle ASDF component")
    if recovery_index >= lifecycle_index:
        raise RuntimeError("runtime-lifecycle no longer loads after target-recovery")

    recovery_start = extract_list_form(recovery_text, START_FORM)
    lifecycle_start = extract_list_form(lifecycle_text, START_FORM)
    if RECOVERY_CALL not in recovery_start:
        raise RuntimeError("target-recovery START-ACTORS no longer calls recovery")
    if RECOVERY_CALL in lifecycle_start:
        raise RuntimeError(
            "runtime-lifecycle START-ACTORS now calls recovery; book evidence is stale"
        )

    return {
        "target_recovery_loaded_first": True,
        "early_start_calls_recovery": True,
        "final_start_omits_recovery": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("server_root", type=Path)
    args = parser.parse_args()
    result = audit(args.server_root.resolve())
    for key, value in result.items():
        print(f"{key}={str(value).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
