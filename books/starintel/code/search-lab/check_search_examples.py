"""Static, non-executing syntax audit of Chapter 15 Org source examples.

Checks fenced JSON, Python, and Bash as teaching material; never runs a code
sample or treats example data as authorization, indexed coverage, or evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

BEGIN = re.compile(r'^\s*#\+begin_src\s+(\S+)(?:\s.*)?$', re.I)
END = re.compile(r'^\s*#\+end_src\s*$', re.I)
HEREDOC = re.compile(r'<<-?\s*(?:\'JSON\'|"JSON"|JSON)(?:\s|$)')
ALLOWED = {'json', 'python', 'sh', 'bash'}


class ExampleError(ValueError):
    """An Org teaching example is incomplete or syntactically invalid."""


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ExampleError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _json(source: str, line: int) -> None:
    try:
        json.loads(source, object_pairs_hook=_unique_pairs,
                   parse_constant=lambda value: (_ for _ in ()).throw(
                       ExampleError(f'non-JSON constant: {value}')))
    except (ValueError, TypeError) as exc:
        raise ExampleError(f'line {line}: invalid JSON: {exc}') from exc


def _bash(source: str, line: int) -> None:
    try:
        check = subprocess.run(['bash', '-n'], input=source, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExampleError(f'line {line}: Bash syntax check unavailable: {exc}') from exc
    if check.returncode:
        raise ExampleError(f'line {line}: invalid Bash syntax: {check.stderr.strip()}')
    lines = source.splitlines()
    for index, current in enumerate(lines):
        if not HEREDOC.search(current):
            continue
        try:
            stop = next(j for j in range(index + 1, len(lines))
                        if lines[j].strip() == 'JSON')
        except StopIteration as exc:
            raise ExampleError(f'line {line + index}: missing JSON heredoc terminator') from exc
        _json('\n'.join(lines[index + 1:stop]), line + index + 1)


def check(text: str) -> dict[str, int]:
    """Parse and syntax-check source blocks without running their contents."""
    counts = {name: 0 for name in ('json', 'python', 'sh', 'bash')}
    active = None
    body = []
    for number, line in enumerate(text.splitlines(), 1):
        beginning = BEGIN.match(line)
        closing = END.match(line)
        if active is None:
            if closing:
                raise ExampleError(f'line {number}: stray end_src')
            if beginning:
                language = beginning.group(1).lower()
                if language not in ALLOWED:
                    raise ExampleError(f'line {number}: unreviewed source language {language}')
                active = (number, language)
                body = []
            continue
        if beginning:
            raise ExampleError(f'line {number}: nested begin_src inside line {active[0]}')
        if not closing:
            body.append(line)
            continue
        start, language = active
        source = '\n'.join(body) + '\n'
        if language == 'json':
            _json(source, start)
        elif language == 'python':
            try:
                compile(source, f'chapter15:{start}', 'exec')
            except SyntaxError as exc:
                raise ExampleError(f'line {start}: invalid Python syntax: {exc}') from exc
        else:
            _bash(source, start)
        counts[language] += 1
        active = None
    if active is not None:
        raise ExampleError(f'line {active[0]}: unterminated {active[1]} block')
    if not sum(counts.values()):
        raise ExampleError('no source examples found')
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manuscript', type=Path)
    args = parser.parse_args(argv)
    try:
        result = check(args.manuscript.read_text(encoding='utf-8'))
    except (ExampleError, OSError) as exc:
        parser.exit(2, f'Chapter 15 example syntax: {exc}\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
