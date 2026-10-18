#!/usr/bin/env python3
"""Check structural boundaries of the Org Chapter 15 include without evaluating Babel.

This validates the heading spine only. It is not EPUBCheck, org-element, or a
claim that the prose or links are correct. Use after substantive manuscript edits.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CHAPTER_ID = 'c28dc507-faf2-4e26-b1ba-bc2b8236e7af'
ROOT = Path(__file__).resolve().parents[2] / 'manuscript' / 'search-15.org'
HEADING = re.compile(r'^(\*+)\s+(.+?)\s*$')
BEGIN = re.compile(r'^#\+begin_([a-zA-Z0-9_-]+)\b', re.IGNORECASE)
END = re.compile(r'^#\+end_([a-zA-Z0-9_-]+)\b', re.IGNORECASE)
ID = re.compile(r'^\s*:ID:\s*(\S+)\s*$', re.IGNORECASE)
EXERCISE = re.compile(r'^(?:Worked exercise\b|Exercise\b)', re.IGNORECASE)


def inspect(text: str) -> list[str]:
    """Return precise violations; do not interpret markup inside Org blocks."""
    errors: list[str] = []
    headings: list[tuple[int, int, str]] = []
    ids: list[tuple[int, str]] = []
    block: tuple[int, str] | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if block is not None:
            closing = END.match(line)
            if closing and closing.group(1).lower() == block[1]:
                block = None
            continue
        opening = BEGIN.match(line)
        if opening:
            block = (number, opening.group(1).lower())
            continue
        closing = END.match(line)
        if closing:
            errors.append(f'line {number}: unmatched Org block end')
            continue
        marker = ID.match(raw)
        if marker:
            ids.append((number, marker.group(1)))
        heading = HEADING.match(raw)
        if heading:
            headings.append((number, len(heading.group(1)), heading.group(2)))
    if block:
        errors.append(f'line {block[0]}: unclosed Org block {block[1]}')
    roots = [(line, title) for line, level, title in headings if level == 1]
    if len(roots) != 1 or not roots[0][1].startswith('Chapter 15 --'):
        errors.append(f'expected exactly one Chapter 15 top-level heading; found {roots}')
    if not headings or headings[0][1] != 1:
        errors.append('the first heading must be the Chapter 15 title')
    recorded = [value for _, value in ids]
    if recorded.count(CHAPTER_ID) != 1 or len(recorded) != len(set(recorded)):
        errors.append('expected one stable Chapter 15 Org ID and no duplicate IDs')
    previous_section: tuple[int, str] | None = None
    for line, level, title in headings:
        if level == 2:
            previous_section = (line, title)
        if EXERCISE.match(title):
            if level != 3 or previous_section is None:
                errors.append(f'line {line}: exercise must be level 3 under a level 2 section')
        if level > 3:
            errors.append(f'line {line}: unexpected heading depth {level}')
    return errors


def main(args: list[str]) -> int:
    if len(args) > 1:
        print('usage: check_search_outline.py [CHAPTER_ORG]', file=sys.stderr)
        return 2
    target = Path(args[0]) if args else ROOT
    try:
        content = target.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        print(f'Cannot read Chapter 15: {exc}', file=sys.stderr)
        return 2
    violations = inspect(content)
    for violation in violations:
        print(f'FAIL: {violation}', file=sys.stderr)
    if violations:
        return 1
    print('PASS: one Chapter 15 root, stable ID, exercise nesting, balanced Org blocks')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
