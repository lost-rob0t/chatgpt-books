#!/usr/bin/env python3
"""Validate the Chapter 15 reader map and its stable Org export landmarks.

This checks source structure, not link resolution in a complete EPUB or
runtime search correctness. Org is canonical; no Babel blocks are executed.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys

MANUSCRIPT = Path(__file__).resolve().parents[2] / 'manuscript/search-15.org'
MAP_HEADING = 'Reader map -- eight search evidence boundaries'
LANDMARKS = (
    ('search15-version', 'Evidence and version map'),
    ('search15-scope', 'Choose the search surface deliberately'),
    ('search15-index', 'Stored documents become selected index fields'),
    ('search15-page', 'Interpret a page as retrieval evidence'),
    ('search15-bookmark', 'Pagination needs a bounded client'),
    ('search15-debug', 'The visibility ladder is a debugging method'),
    ('search15-lab', 'Run the reproducible lab'),
    ('search15-project4', 'Project 4 integration -- A search hit is a claim to investigate'),
)
HEADING = re.compile(r'^(\*+) +(.+?)\s*$')
BEGIN = re.compile(r'^#\+begin_([\w-]+)\b', re.IGNORECASE)
END = re.compile(r'^#\+end_([\w-]+)\b', re.IGNORECASE)
LINK = re.compile(r'\[\[#([a-z0-9-]+)\]\[([^\]]+)\]\]')
CUSTOM = re.compile(r'^\s*:CUSTOM_ID:\s*(\S+)\s*$', re.IGNORECASE)


def inspect(text: str) -> list[str]:
    errors: list[str] = []
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    anchors: list[tuple[int, str, str]] = []
    block: str | None = None
    non_source_lines = list(lines)
    owner: tuple[int, int, str] | None = None
    drawer = False
    map_start: int | None = None
    map_end: int | None = None
    for line_no, raw in enumerate(lines, 1):
        line = raw.strip()
        if block is not None:
            non_source_lines[line_no - 1] = ''
            closing = END.match(line)
            if closing and closing.group(1).lower() == block:
                block = None
            continue
        opening = BEGIN.match(line)
        if opening:
            non_source_lines[line_no - 1] = ''
            block = opening.group(1).lower()
            continue
        match = HEADING.match(raw)
        if match:
            depth, name = len(match.group(1)), match.group(2)
            headings.append((line_no, depth, name))
            if map_start is not None and map_end is None and depth <= 2:
                map_end = line_no - 1
            if name == MAP_HEADING and depth == 2:
                if map_start is not None:
                    errors.append('duplicate reader map heading')
                map_start = line_no
            owner = (line_no, depth, name)
            drawer = False
            continue
        if line.upper() == ':PROPERTIES:' and owner is not None:
            drawer = True
            continue
        if line.upper() == ':END:' and drawer:
            drawer = False
            continue
        marker = CUSTOM.match(raw)
        if marker:
            if not drawer or owner is None:
                errors.append(f'line {line_no}: CUSTOM_ID outside a heading property drawer')
            else:
                anchors.append((owner[1], owner[2], marker.group(1)))
    if block:
        errors.append('unclosed Org block')
    if map_start is None:
        errors.append('missing reader map heading')
    if map_start is not None and map_end is None:
        map_end = len(lines)
    ids = [anchor for _, _, anchor in anchors]
    dupes = sorted(x for x, n in Counter(ids).items() if n != 1)
    if dupes:
        errors.append('duplicate CUSTOM_ID: ' + ', '.join(dupes))
    expected = dict(LANDMARKS)
    for ident, heading in LANDMARKS:
        owners = [(depth, title) for depth, title, value in anchors if value == ident]
        if owners != [(2, heading)]:
            errors.append(f'landmark {ident} must belong to ** {heading}')
        if sum(depth == 2 and title == heading for _, depth, title in headings) != 1:
            errors.append(f'expected one destination section: {heading}')
    if map_start is not None and map_end is not None:
        page = '\n'.join(non_source_lines[map_start:map_end])
        links = LINK.findall(page)
        found = Counter(ident for ident, _ in links)
        if any(ident not in expected for ident in found):
            errors.append('reader map links to an unregistered fragment')
        for ident in expected:
            if found[ident] != 1:
                errors.append(f'reader map needs exactly one link to {ident}')
        if len(links) != len(LANDMARKS):
            errors.append('reader map must contain exactly eight navigable links')
    return errors


def main(args: list[str]) -> int:
    if len(args) > 1:
        print('usage: check_search_navigation.py [CHAPTER_ORG]', file=sys.stderr)
        return 2
    path = Path(args[0]) if args else MANUSCRIPT
    try:
        content = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        print(f'cannot read chapter: {exc}', file=sys.stderr)
        return 2
    problems = inspect(content)
    for problem in problems:
        print('FAIL:', problem, file=sys.stderr)
    if problems:
        return 1
    print('PASS: eight unique reader-map anchors and destination headings')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
