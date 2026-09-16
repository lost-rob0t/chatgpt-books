#!/usr/bin/env python3
"""Verify the Project 1 direct requirements, lock file, and live environment."""

from __future__ import annotations

import importlib.metadata
import pathlib
import re
import sys
from collections.abc import Mapping

ROOT = pathlib.Path(__file__).resolve().parent
DIRECT_REQUIREMENTS = ROOT / "requirements.txt"
LOCK_REQUIREMENTS = ROOT / "requirements.lock"
PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)$")


class LockError(RuntimeError):
    """Raised when the dependency-lock contract is violated."""


def normalize_name(name: str) -> str:
    """Normalize a Python distribution name for deterministic comparison."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(path: pathlib.Path) -> dict[str, str]:
    """Parse a requirements file containing only exact ``name==version`` pins."""
    pins: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = PIN_RE.fullmatch(line)
        if match is None:
            raise LockError(f"{path.name}:{line_number}: expected an exact name==version pin: {line!r}")

        package = normalize_name(match.group(1))
        version = match.group(2)
        if package in pins:
            raise LockError(f"{path.name}:{line_number}: duplicate normalized package {package!r}")
        pins[package] = version

    if not pins:
        raise LockError(f"{path.name}: no dependency pins found")
    return pins


def installed_pins() -> dict[str, str]:
    """Return installed distributions, excluding pip itself from the research lock."""
    pins: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            raise LockError("installed distribution is missing its Name metadata")

        package = normalize_name(raw_name)
        if package == "pip":
            continue
        if package in pins:
            raise LockError(f"installed environment contains duplicate normalized package {package!r}")
        pins[package] = distribution.version
    return pins


def format_mapping(mapping: Mapping[str, str]) -> str:
    return ", ".join(f"{name}=={mapping[name]}" for name in sorted(mapping)) or "<none>"


def verify_contract(
    direct: Mapping[str, str],
    locked: Mapping[str, str],
    installed: Mapping[str, str],
) -> None:
    """Verify direct intent is contained in the lock and the live env equals it."""
    direct_mismatches = {
        name: f"direct={version}, lock={locked.get(name, '<missing>')}"
        for name, version in direct.items()
        if locked.get(name) != version
    }
    if direct_mismatches:
        raise LockError("direct requirements disagree with lock: " + format_mapping(direct_mismatches))

    missing = {name: version for name, version in locked.items() if name not in installed}
    extra = {name: version for name, version in installed.items() if name not in locked}
    drift = {
        name: f"lock={locked[name]}, installed={installed[name]}"
        for name in locked.keys() & installed.keys()
        if locked[name] != installed[name]
    }
    if missing or extra or drift:
        details = [
            f"missing: {format_mapping(missing)}",
            f"extra: {format_mapping(extra)}",
            f"version drift: {format_mapping(drift)}",
        ]
        raise LockError("installed environment disagrees with lock; " + "; ".join(details))


def main() -> int:
    try:
        direct = parse_pins(DIRECT_REQUIREMENTS)
        locked = parse_pins(LOCK_REQUIREMENTS)
        installed = installed_pins()
        verify_contract(direct, locked, installed)
    except LockError as exc:
        print(f"dependency lock verification FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        "dependency lock verification PASSED: "
        f"{len(direct)} direct pins; {len(locked)} locked distributions; "
        f"{len(installed)} installed distributions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
