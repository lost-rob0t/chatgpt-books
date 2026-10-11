"""CPU-only structured policy for selecting and reading static local HTML.

No network, browser, credentials, or free-form tool-call generation. BK08 can
provide offline JSONL rows through the published row contract.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import random
import re
from pathlib import Path
from urllib.parse import urlsplit

MAX_HTML = 16_384
MAX_NODES = 128
MAX_DEPTH = 24
MAX_ROWS = 1_000
MODEL_FORMAT = "tiny-html-policy/v1"
WORDS = re.compile(r"[a-z0-9]+")
ATTRS = {"id", "class", "title", "aria-label", "data-value", "href"}


def words(value: str) -> tuple[str, ...]:
    return tuple(WORDS.findall(value.casefold())[:64])


def normalized(value: str) -> str:
    return " ".join(value.split())


def relative_href(value: str) -> bool:
    if not value or value.startswith("//") or any(ord(c) < 32 for c in value):
        return False
    parsed = urlsplit(value)
    return not parsed.scheme and not parsed.netloc


@dataclass
class Node:
    handle: str
    tag: str
    attrs: dict[str, str]
    fragments: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return normalized(" ".join(self.fragments))[:512]


class CompactDOM(HTMLParser):
    """Bounded DOM with stable preorder handles for one input document."""

    def __init__(self, html: str):
        if not isinstance(html, str) or len(html) > MAX_HTML:
            raise ValueError("HTML must be a bounded string")
        super().__init__(convert_charrefs=True)
        self.nodes: list[Node] = []
        self.stack: list[int] = []
        self.ignored = 0
        self.feed(html)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag in {"script", "style"} or self.ignored:
            self.ignored += 1
            return
        if len(self.nodes) >= MAX_NODES or len(self.stack) >= MAX_DEPTH:
            raise ValueError("DOM resource bound exceeded")
        safe_attrs = {k: (v or "")[:256] for k, v in attrs if k in ATTRS}
        index = len(self.nodes)
        self.nodes.append(Node(f"n{index}", tag, safe_attrs))
        if tag not in {"area", "base", "br", "hr", "img", "input", "link", "meta", "source", "wbr"}:
            self.stack.append(index)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self.handle_starttag(tag, attrs)
        if self.stack and self.nodes[self.stack[-1]].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag: str):
        if self.ignored:
            self.ignored -= 1
            return
        for offset in range(len(self.stack) - 1, -1, -1):
            if self.nodes[self.stack[offset]].tag == tag:
                del self.stack[offset:]
                break

    def handle_data(self, data: str):
        if self.ignored:
            return
        chunk = normalized(data)
        if not chunk:
            return
        for index in self.stack:
            node = self.nodes[index]
            if sum(map(len, node.fragments)) < 512:
                node.fragments.append(chunk[:512])

    def node(self, handle: str) -> Node:
        for node in self.nodes:
            if node.handle == handle:
                return node
        raise ValueError("unknown DOM handle")

    def compact(self) -> list[dict[str, object]]:
        return [
            {"node": n.handle, "tag": n.tag, "attrs": n.attrs, "text": n.text[:160]}
            for n in self.nodes
        ]


@dataclass(frozen=True)
class Candidate:
    node: str
    tool: str
    field: str

    def trace(self) -> list[dict[str, str]]:
        step = {"tool": self.tool, "field": self.field} if self.tool == "extract" else {"tool": "follow"}
        return [{"tool": "select", "node": self.node}, step]


def candidates(dom: CompactDOM) -> list[Candidate]:
    result: list[Candidate] = []
    for node in dom.nodes:
        if node.text:
            result.append(Candidate(node.handle, "extract", "text"))
        for key in ("title", "data-value"):
            if node.attrs.get(key):
                result.append(Candidate(node.handle, "extract", key))
        if node.tag == "a" and relative_href(node.attrs.get("href", "")):
            result.append(Candidate(node.handle, "follow", "href"))
    return result


def validate_trace(dom: CompactDOM, trace: object) -> Candidate:
    if not isinstance(trace, list) or len(trace) != 2:
        raise ValueError("a call trace must contain select then extract/follow")
    first, second = trace
    if not isinstance(first, dict) or set(first) != {"tool", "node"} or first["tool"] != "select":
        raise ValueError("invalid select call schema")
    if not isinstance(second, dict):
        raise ValueError("invalid second call schema")
    if second == {"tool": "follow"}:
        candidate = Candidate(first["node"], "follow", "href")
    elif set(second) == {"tool", "field"} and second["tool"] == "extract" and second["field"] in {"text", "title", "data-value"}:
        candidate = Candidate(first["node"], "extract", second["field"])
    else:
        raise ValueError("invalid tool or tool argument")
    if candidate not in candidates(dom):
        raise ValueError("call points outside admissible local DOM candidates")
    return candidate


def execute(dom: CompactDOM, trace: object) -> str:
    candidate = validate_trace(dom, trace)
    node = dom.node(candidate.node)
    if candidate.tool == "follow":
        return node.attrs["href"]  # local relative href ONLY; never fetches
    if candidate.field == "text":
        return node.text
    return node.attrs[candidate.field]


def feature_counts(instruction: str, node: Node, candidate: Candidate) -> Counter[str]:
    q = set(words(instruction))
    description = " ".join([node.attrs.get(k, "") for k in ("id", "class", "title", "aria-label")])
    hint = set(words(description))
    content = set(words(node.text))
    f = Counter({"bias": 1, f"tool:{candidate.tool}": 1,
                 f"field:{candidate.field}": 1, f"tag:{node.tag}|tool:{candidate.tool}": 1})
    for term in q:
        f[f"query:{term}|tool:{candidate.tool}"] = 1
        f[f"query:{term}|field:{candidate.field}"] = 1
        if term in hint:
            f[f"hint-match:{term}"] = 1
        if term in content:
            f[f"text-match:{term}"] = 1
        f[f"query:{term}|tag:{node.tag}"] = 1
    return f


class TinyPolicy:
    """Supervised structured linear sequence policy; no transformer/GPU claim."""

    def __init__(self, weights: dict[str, int] | None = None):
        self.weights = dict(weights or {})

    def predict(self, dom: CompactDOM, instruction: str) -> list[dict[str, str]]:
        pool = candidates(dom)
        if not pool:
            raise ValueError("no admissible DOM actions")
        if not isinstance(instruction, str) or len(instruction) > 512:
            raise ValueError("instruction must be a bounded string")
        selected = max(pool, key=lambda c: sum(
            self.weights.get(key, 0) * count
            for key, count in feature_counts(instruction, dom.node(c.node), c).items()
        ))
        trace = selected.trace()
        validate_trace(dom, trace)
        return trace

    def fit(self, rows: list[dict[str, object]], epochs: int = 20, seed: int = 7) -> list[int]:
        if not isinstance(epochs, int) or not 1 <= epochs <= 200:
            raise ValueError("epochs must be 1..200")
        prepared = prepare_rows(rows)
        rng = random.Random(seed)
        mistakes: list[int] = []
        for _ in range(epochs):
            indices = list(range(len(prepared)))
            rng.shuffle(indices)
            count = 0
            for idx in indices:
                dom, instruction, gold, _expected = prepared[idx]
                predicted = validate_trace(dom, self.predict(dom, instruction))
                if predicted == gold:
                    continue
                count += 1
                good = feature_counts(instruction, dom.node(gold.node), gold)
                bad = feature_counts(instruction, dom.node(predicted.node), predicted)
                for key in set(good) | set(bad):
                    value = self.weights.get(key, 0) + good[key] - bad[key]
                    if value:
                        self.weights[key] = value
                    else:
                        self.weights.pop(key, None)
            mistakes.append(count)
        return mistakes

    def to_json(self) -> str:
        return json.dumps({"format": MODEL_FORMAT, "weights": dict(sorted(self.weights.items()))}, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "TinyPolicy":
        record = json.loads(raw)
        if not isinstance(record, dict) or set(record) != {"format", "weights"} or record["format"] != MODEL_FORMAT:
            raise ValueError("unsupported model format")
        weights = record["weights"]
        if not isinstance(weights, dict) or len(weights) > 50_000 or any(not isinstance(k, str) or not isinstance(v, int) for k, v in weights.items()):
            raise ValueError("invalid weights")
        return cls(weights)


def prepare_rows(rows: list[dict[str, object]]):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("dataset must have 1..1000 rows")
    prepared = []
    for row in rows:
        if not isinstance(row, dict) or not {"html", "instruction", "gold_calls", "expected"} <= set(row):
            raise ValueError("row requires html, instruction, gold_calls, expected")
        dom = CompactDOM(row["html"])
        instruction = row["instruction"]
        if not isinstance(instruction, str) or len(instruction) > 512:
            raise ValueError("instruction must be a bounded string")
        gold = validate_trace(dom, row["gold_calls"])
        expected = row["expected"]
        if not isinstance(expected, str) or execute(dom, gold.trace()) != expected:
            raise ValueError("gold execution and expected value disagree")
        prepared.append((dom, instruction, gold, expected))
    return prepared


def evaluate(model: TinyPolicy, rows: list[dict[str, object]]) -> dict[str, float | int]:
    examples = prepare_rows(rows)
    exact = success = 0
    for dom, instruction, gold, expected in examples:
        trace = model.predict(dom, instruction)
        exact += int(trace == gold.trace())
        success += int(execute(dom, trace) == expected)
    return {"examples": len(examples), "exact_call_accuracy": exact / len(examples),
            "extraction_success": success / len(examples)}


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("JSONL exceeds input bound")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    prepare_rows(rows)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True, type=Path, help="offline JSONL training rows")
    parser.add_argument("--evaluate", required=True, type=Path, help="offline JSONL evaluation rows")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    model = TinyPolicy()
    mistakes = model.fit(read_jsonl(args.train), epochs=args.epochs, seed=args.seed)
    report = {"format": MODEL_FORMAT, "epoch_mistakes": mistakes,
              "train": evaluate(model, read_jsonl(args.train)),
              "evaluation": evaluate(model, read_jsonl(args.evaluate)),
              "weights": len(model.weights)}
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
