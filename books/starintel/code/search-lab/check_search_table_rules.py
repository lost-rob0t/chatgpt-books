"""Source-level table shape guard for Chapter 15 Org evidence matrices.

This checks readability and consistent column boundaries. Pandoc accepts some
abbreviated Org separators; a passing check is NOT an EPUBCheck substitute.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

PIPE = re.compile(r"(?<!\\)\|")
BEGIN = re.compile(r"^\s*#\+begin_(src|example|export|comment|verse)\b", re.I)
END = re.compile(r"^\s*#\+end_(src|example|export|comment|verse)\b", re.I)
SEPARATOR = re.compile(r"^\|[-+]+\|?$")


def _columns(row: str) -> int:
    parts = PIPE.split(row)
    if not row.startswith('|') or not row.endswith('|'):
        return -1
    return len(parts) - 2


def table_issues(text: str) -> list[str]:
    """Report exact source lines, without rewriting Org or guessing EPUB output."""
    issues: list[str] = []
    active_block = False
    group: list[tuple[int, str]] = []

    def flush() -> None:
        if not group:
            return
        regular = [(line, row) for line, row in group if not SEPARATOR.fullmatch(row)]
        if not regular:
            issues.append(f"line {group[0][0]}: table has no data/header row")
            return
        expected = _columns(regular[0][1])
        if expected < 1:
            issues.append(f"line {regular[0][0]}: invalid table row")
            return
        for line, row in regular:
            if _columns(row) != expected:
                issues.append(f"line {line}: expected {expected} cells")
        for line, row in group:
            if not SEPARATOR.fullmatch(row):
                continue
            segments = row[1:-1].split('+')
            if (not row.endswith('|') or len(segments) != expected or
                    any(not segment or any(char != '-' for char in segment)
                        for segment in segments)):
                issues.append(f"line {line}: separator must cover {expected} columns")

    for number, source in enumerate(text.splitlines(), 1):
        stripped = source.strip()
        if BEGIN.match(source):
            flush()
            group = []
            active_block = True
            continue
        if END.match(source):
            active_block = False
            continue
        if active_block:
            continue
        if stripped.startswith('|'):
            group.append((number, stripped))
        else:
            flush()
            group = []
    flush()
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manuscript', type=Path)
    args = parser.parse_args()
    issues = table_issues(args.manuscript.read_text(encoding='utf-8'))
    for issue in issues:
        print(issue)
    if issues:
        return 1
    print('Org table column/separator source check passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
