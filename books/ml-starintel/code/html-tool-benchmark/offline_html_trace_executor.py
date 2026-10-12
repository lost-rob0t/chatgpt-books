"""BK08: deterministic, bounded execution oracle for static HTML tool traces.

All pages are supplied in memory. There is no HTTP client, model, or training code.
Selectors deliberately support a documented small subset, not general CSS.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urljoin, urlsplit


ORIGIN = "https://fixture.invalid"
MAX_PAGES = 32
MAX_PAGE_BYTES = 65_536
MAX_TOTAL_PAGE_BYTES = 524_288
MAX_NODES = 2_048
MAX_DEPTH = 40
MAX_ACTIONS = 96
MAX_OUTPUTS = 24
MAX_TEXT = 2_048
MAX_SAMPLES = 128
MAX_DATASET_BYTES = 2_097_152
MAX_JSON_DEPTH = 64
VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())
NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
TAG_RE = re.compile(r"[a-z][a-z0-9-]{0,31}")
CLASS_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")


class TraceFailure(ValueError):
    """Typed evaluation error; no external action is attempted."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass
class Element:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)

    def text(self) -> str:
        parts: list[str] = []
        stack: list[Element | str] = [self]
        while stack:
            part = stack.pop()
            if isinstance(part, str):
                parts.append(part)
            else:
                if part.tag in {"script", "style"}:
                    continue
                stack.extend(reversed(part.children))
        return " ".join("".join(parts).split())


class BoundedParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("root")
        self.stack = [self.root]
        self.nodes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise TraceFailure("parse_bounds", "too many HTML nodes")
        if len(self.stack) >= MAX_DEPTH:
            raise TraceFailure("parse_bounds", "HTML nesting is too deep")
        clean: dict[str, str] = {}
        for key, value in attrs:
            if key not in clean:
                clean[key] = value or ""
        node = Element(tag, clean)
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1].children.append(data)


def _bounded_selector(selector: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(selector, str) or len(selector) > 160 or not selector:
        raise TraceFailure("invalid_action", "selector missing or oversized")
    rest = selector
    tag = id_part = class_part = None
    match = TAG_RE.match(rest)
    if match:
        tag, rest = match.group(), rest[match.end():]
    if rest.startswith("#"):
        match = ID_RE.match(rest[1:])
        if not match:
            raise TraceFailure("invalid_action", "invalid ID selector")
        id_part, rest = match.group(), rest[match.end() + 1:]
    if rest.startswith("."):
        match = CLASS_RE.match(rest[1:])
        if not match:
            raise TraceFailure("invalid_action", "invalid class selector")
        class_part, rest = match.group(), rest[match.end() + 1:]
    if rest or not (tag or id_part or class_part):
        raise TraceFailure("invalid_action", "unsupported selector syntax")
    return tag, id_part, class_part


def select_one(root: Element, selector: Any) -> Element:
    tag, id_part, class_part = _bounded_selector(selector)
    found: Element | None = None
    stack = [root]
    while stack:
        node = stack.pop()
        if node is not root and (tag is None or node.tag == tag):
            if (id_part is None or node.attrs.get("id") == id_part) and (
                class_part is None or class_part in node.attrs.get("class", "").split()
            ):
                if found is not None:
                    raise TraceFailure("selector_ambiguous", str(selector))
                found = node
        stack.extend(reversed([x for x in node.children if isinstance(x, Element)]))
    if found is None:
        raise TraceFailure("selector_zero", str(selector))
    return found


def resolve_page(raw: Any, base: str = "/") -> str:
    if not isinstance(raw, str) or not raw or len(raw) > 512 or any(ord(c) < 33 for c in raw):
        raise TraceFailure("unsafe_navigation", "invalid page reference")
    try:
        raw.encode("utf-8")  # reject unpaired surrogates before URL normalization
        split_raw = urlsplit(raw)
        if split_raw.query or split_raw.fragment or "%" in split_raw.path or any(
            segment in {".", ".."} for segment in split_raw.path.split("/")
        ):
            raise TraceFailure("unsafe_navigation", "ambiguous or traversing page reference")
        merged = urlsplit(urljoin(ORIGIN + base, raw))
    except (ValueError, UnicodeError) as exc:
        raise TraceFailure("unsafe_navigation", "malformed page authority or Unicode") from exc
    if (merged.scheme != "https" or merged.netloc != "fixture.invalid"
            or merged.username is not None or merged.password is not None
            or merged.query or merged.fragment or "//" in merged.path):
        raise TraceFailure("unsafe_navigation", "navigation leaves the static fixture origin")
    return merged.path or "/"


def _validate_pages(pages: Any) -> dict[str, str]:
    if not isinstance(pages, dict) or not 1 <= len(pages) <= MAX_PAGES:
        raise TraceFailure("parse_bounds", "invalid page inventory")
    cleaned: dict[str, str] = {}
    total = 0
    for path, html in pages.items():
        if not isinstance(path, str) or not path.startswith("/") or resolve_page(path) != path:
            raise TraceFailure("unsafe_navigation", "invalid page path")
        if not isinstance(html, str):
            raise TraceFailure("parse_bounds", "HTML must be text")
        try:
            nbytes = len(html.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise TraceFailure("parse_bounds", "fixture HTML is not valid UTF-8") from exc
        total += nbytes
        if nbytes > MAX_PAGE_BYTES or total > MAX_TOTAL_PAGE_BYTES:
            raise TraceFailure("parse_bounds", "fixture payload exceeds budget")
        cleaned[path] = html
    return cleaned


def _preflight_parsed_pages(prepared: dict[str, str]) -> dict[str, Element]:
    """Parse and bound every supplied page, including pages no gold trace visits.

    The resulting immutable-by-convention trees are reused on revisits. A bad
    unvisited page must not be hidden by otherwise successful gold traces.
    """
    parsed: dict[str, Element] = {}
    for path, html in prepared.items():
        parser = BoundedParser()
        try:
            parser.feed(html)
            parser.close()
        except (RecursionError, OverflowError) as exc:
            raise TraceFailure("parse_bounds", f"cannot parse bounded fixture page: {path}") from exc
        parsed[path] = parser.root
    return parsed


def run_trace(pages: dict[str, str], start: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
    prepared = _validate_pages(pages)
    parsed = _preflight_parsed_pages(prepared)
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise TraceFailure("invalid_action", "trace action budget exceeded")
    current = resolve_page(start)
    outputs: dict[str, str] = {}
    visited: list[str] = []
    digests: dict[str, str] = {}
    selected: Element | None = None
    root: Element | None = None

    def load(path: str) -> Element:
        if path not in prepared:
            raise TraceFailure("missing_target", path)
        if path not in digests:
            digests[path] = hashlib.sha256(prepared[path].encode("utf-8")).hexdigest()
        visited.append(path)
        return parsed[path]

    root = load(current)
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise TraceFailure("invalid_action", f"action {index} is not an object")
        op = action.get("op")
        if op == "select" and set(action) == {"op", "selector"}:
            selected = select_one(root, action["selector"])
        elif op == "extract" and set(action) in ({"op", "field"}, {"op", "field", "attribute"}):
            key = action["field"]
            if not isinstance(key, str) or not NAME_RE.fullmatch(key) or key in outputs:
                raise TraceFailure("invalid_action", "invalid or duplicate extraction field")
            if selected is None:
                raise TraceFailure("invalid_action", "extract without selection")
            if len(outputs) >= MAX_OUTPUTS:
                raise TraceFailure("parse_bounds", "too many extracted fields")
            if "attribute" in action:
                attribute = action["attribute"]
                if not isinstance(attribute, str) or not NAME_RE.fullmatch(attribute) or attribute not in selected.attrs:
                    raise TraceFailure("invalid_action", "missing or invalid extraction attribute")
                value = selected.attrs[attribute]
            else:
                value = selected.text()
            if len(value.encode("utf-8")) > MAX_TEXT:
                raise TraceFailure("parse_bounds", "extracted text is too large")
            outputs[key] = value
        elif op == "follow" and set(action) == {"op", "kind"}:
            if (not isinstance(action["kind"], str) or action["kind"] not in {"next", "detail"}
                    or selected is None or selected.tag != "a"):
                raise TraceFailure("invalid_action", "follow requires selected anchor and typed kind")
            if "href" not in selected.attrs:
                raise TraceFailure("missing_target", "selected anchor has no href")
            current = resolve_page(selected.attrs["href"], current)
            root = load(current)
            selected = None
        else:
            raise TraceFailure("invalid_action", f"unsupported action at index {index}")
    return {"extractions": outputs, "visited": visited, "page_sha256": dict(sorted(digests.items()))}


def _valid_record(record: Any) -> tuple[str, str, dict[str, str], str, list[dict[str, Any]], list[dict[str, Any]], dict[str, str], list[str]]:
    required = {"id", "family", "pages", "start", "gold_trace", "candidate_trace", "gold_extractions", "gold_visited"}
    if not isinstance(record, dict) or set(record) != required:
        raise TraceFailure("invalid_record", "record fields do not match schema")
    id_ = record["id"]
    family = record["family"]
    if not isinstance(id_, str) or not NAME_RE.fullmatch(id_) or not isinstance(family, str) or not NAME_RE.fullmatch(family):
        raise TraceFailure("invalid_record", "invalid record identity")
    gold = record["gold_trace"]
    candidate = record["candidate_trace"]
    if not isinstance(gold, list) or not isinstance(candidate, list):
        raise TraceFailure("invalid_record", "trace is not a list")
    return (id_, family, record["pages"], record["start"], gold, candidate,
            record["gold_extractions"], record["gold_visited"])


def evaluate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_SAMPLES:
        raise TraceFailure("invalid_record", "evaluation sample limit exceeded")
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda x: x.get("id", "") if isinstance(x, dict) and isinstance(x.get("id"), str) else ""):
        id_, family, pages, start, gold, candidate, gold_extract, gold_visited = _valid_record(record)
        if id_ in seen:
            raise TraceFailure("invalid_record", "duplicate example identity")
        seen.add(id_)
        authoritative = run_trace(pages, start, gold)
        if authoritative["extractions"] != gold_extract or authoritative["visited"] != gold_visited:
            raise TraceFailure("gold_mismatch", f"example {id_}: gold disagrees with executed HTML")
        failure = None
        try:
            actual = run_trace(pages, start, candidate)
        except TraceFailure as exc:
            failure = exc.code
            actual = {"extractions": {}, "visited": [], "page_sha256": {}}
        denominator = max(len(gold), len(candidate), 1)
        exact = sum(left == right for left, right in zip(gold, candidate)) / denominator
        matching_ops = [(left, right) for left, right in zip(gold, candidate)
                        if isinstance(left, dict) and isinstance(right, dict)
                        and left.get("op") == right.get("op")]
        same_op = len(matching_ops) / denominator
        correct_arguments = sum(
            {k: v for k, v in left.items() if k != "op"} ==
            {k: v for k, v in right.items() if k != "op"}
            for left, right in matching_ops
        )
        argument_accuracy = correct_arguments / len(matching_ops) if matching_ops else 0.0
        # Partial field diagnostics: equality is a pair of (field, value),
        # never merely a matching field name. Invalid traces are fail-closed:
        # their observed extraction map has already been discarded above.
        predicted = actual["extractions"]
        correct_pairs = sum(key in gold_extract and gold_extract[key] == value
                            for key, value in predicted.items())
        field_precision = correct_pairs / len(predicted) if predicted else 0.0
        field_recall = correct_pairs / len(gold_extract) if gold_extract else 0.0
        field_f1 = (2 * correct_pairs / (len(predicted) + len(gold_extract))
                    if predicted or gold_extract else 0.0)
        extraction = int(not failure and predicted == gold_extract)
        navigation = int(not failure and actual["visited"] == gold_visited)
        sequence = int(not failure and candidate == gold)
        if not failure:
            if not extraction:
                failure = "extraction_mismatch"
            elif not navigation:
                failure = "navigation_mismatch"
            elif not sequence:
                failure = "sequence_mismatch"
        items.append({"id": id_, "family": family, "exact_call_accuracy": round(exact, 6),
                      "tool_accuracy": round(same_op, 6), "argument_accuracy": round(argument_accuracy, 6),
                      "extraction_success": extraction,
                      "field_value_precision": round(field_precision, 6),
                      "field_value_recall": round(field_recall, 6),
                      "field_value_f1": round(field_f1, 6),
                      "navigation_success": navigation, "sequence_success": sequence,
                      "failure": failure, "observed": actual})
    keys = ("exact_call_accuracy", "tool_accuracy", "argument_accuracy", "extraction_success",
            "field_value_precision", "field_value_recall", "field_value_f1",
            "navigation_success", "sequence_success")
    metrics = {key: round(sum(x[key] for x in items) / len(items), 6) for key in keys}
    return {"schema": "bk08.static-html-execution/v2", "samples": len(items),
            "metrics": metrics, "cases": items}


def demo_records() -> list[dict[str, Any]]:
    cases = [
        ("tables", {"/tables/index.html": "<table><tr><th>Name</th></tr><tr><td id='table-name'>Ada</td></tr></table>"},
         "/tables/index.html", [{"op":"select","selector":"td#table-name"},{"op":"extract","field":"name"}],
         {"name":"Ada"}, ["/tables/index.html"]),
        ("cards", {"/cards/index.html": "<section class='cards'><article><span id='card-title'>Grace</span></article></section>"},
         "/cards/index.html", [{"op":"select","selector":"#card-title"},{"op":"extract","field":"name"}],
         {"name":"Grace"}, ["/cards/index.html"]),
        ("pagination", {"/pages/one.html": "<a id='next-page' href='two.html'>Next</a>",
                        "/pages/two.html": "<div id='page-value'>Linus</div>"},
         "/pages/one.html", [{"op":"select","selector":"a#next-page"},{"op":"follow","kind":"next"},
                             {"op":"select","selector":"#page-value"},{"op":"extract","field":"name"}],
         {"name":"Linus"}, ["/pages/one.html", "/pages/two.html"]),
        ("detail", {"/details/index.html": "<a id='detail' href='item.html'>Read details</a>",
                    "/details/item.html": "<main><p class='label'>Margaret</p></main>"},
         "/details/index.html", [{"op":"select","selector":"a#detail"},{"op":"follow","kind":"detail"},
                                  {"op":"select","selector":"p.label"},{"op":"extract","field":"name"}],
         {"name":"Margaret"}, ["/details/index.html", "/details/item.html"]),
        ("malformed", {"/malformed/index.html": "<div><strong id='broken-name'>Edsger</div>"},
         "/malformed/index.html", [{"op":"select","selector":"strong#broken-name"},{"op":"extract","field":"name"}],
         {"name":"Edsger"}, ["/malformed/index.html"]),
    ]
    result = []
    for family, pages, start, gold, extraction, visits in cases:
        candidate = [dict(x) for x in gold]
        if family == "cards":
            candidate[0]["selector"] = "#missing-card"
        result.append({"id": f"{family}_01", "family": family, "pages": pages, "start": start,
                       "gold_trace": gold, "candidate_trace": candidate,
                       "gold_extractions": extraction, "gold_visited": visits})
    return result


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DATASET_BYTES:
        raise TraceFailure("invalid_record", "dataset file invalid or oversized")
    raw = path.read_bytes()
    if len(raw) > MAX_DATASET_BYTES:
        raise TraceFailure("invalid_record", "dataset file oversized")
    def bounded_nesting(line: str) -> str:
        depth = 0
        quoted = False
        escaped = False
        for char in line:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "{[":
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    raise TraceFailure("invalid_record", "JSON nesting exceeds depth limit")
            elif char in "}]":
                depth -= 1
                if depth < 0:
                    raise TraceFailure("invalid_record", "invalid JSON nesting")
        return line

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for key, value in pairs:
            if key in fields:
                raise TraceFailure("invalid_record", "duplicate JSON object key")
            fields[key] = value
        return fields

    def reject_nonfinite(token: str) -> None:
        raise TraceFailure("invalid_record", "non-standard JSON numeric constant")

    def finite_float(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise TraceFailure("invalid_record", "non-finite JSON numeric value")
        return value

    try:
        result = [
            json.loads(bounded_nesting(line), object_pairs_hook=unique_object, parse_constant=reject_nonfinite,
                       parse_float=finite_float)
            for line in raw.decode("utf-8").splitlines() if line.strip()
        ]
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise TraceFailure("invalid_record", "malformed or excessively nested JSONL") from exc
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="evaluate deterministic offline HTML family controls")
    group.add_argument("--evaluate", type=Path, metavar="DATASET.jsonl", help="evaluate local static pages and traces")
    args = p.parse_args(argv)
    try:
        result = evaluate(demo_records() if args.demo else read_jsonl(args.evaluate))
    except (TraceFailure, OSError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
