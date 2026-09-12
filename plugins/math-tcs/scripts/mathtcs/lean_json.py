"""Parsing of ``lean --json`` output and diagnostic classification.

``lake lean <file> -- --json`` (or ``lake env lean --json <file>``) prints one JSON object
per message::

    {"severity": "warning", "kind": "hasSorry", "pos": {"line": 7, "column": 8},
     "endPos": {...}, "data": "declaration uses 'sorry'", "fileName": "..."}

``#print axioms X`` arrives as an ``information`` message whose ``data`` is
``'X' depends on axioms: [propext, Quot.sound]``. Everything that is not a JSON line
(Lake's own progress output, panics) is kept as ``noise`` so it is never lost.

Classification vocabulary ported from ``b753236:src/pipeline/lean/build.py``.
"""

from __future__ import annotations

import json
import re

__all__ = ["parse_lean_json", "classify_diagnostic", "summarize"]

_SORRY_RE = re.compile(r"declaration uses .?sorry", re.I)
_CLASSIFIERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sorry", _SORRY_RE),
    ("unknown_identifier", re.compile(r"unknown (identifier|constant|namespace)|does not contain|unknown module", re.I)),
    ("invalid_field", re.compile(r"invalid field", re.I)),
    ("typeclass", re.compile(r"failed to synthesize|instance", re.I)),
    ("type_mismatch", re.compile(r"type mismatch", re.I)),
    ("unsolved_goals", re.compile(r"unsolved goals", re.I)),
    ("motive", re.compile(r"motive is not type correct", re.I)),
    ("parse", re.compile(r"unexpected token|expected", re.I)),
    ("deprecated", re.compile(r"deprecated", re.I)),
    ("linter", re.compile(r"^unused|linter", re.I)),
)


def classify_diagnostic(message: str) -> str:
    for name, pattern in _CLASSIFIERS:
        if pattern.search(message):
            return name
    return "other"


def parse_lean_json(output: str) -> tuple[list[dict], list[str]]:
    """Return ``(diagnostics, noise)``.

    Each diagnostic: ``{severity, kind, line, col, end_line, end_col, message, cls, file}``
    with 1-based lines/columns as Lean reports them (columns are 0-based in Lean; kept)."""
    diags: list[dict] = []
    noise: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            if line:
                noise.append(line)
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            noise.append(line)
            continue
        pos = obj.get("pos") or {}
        end = obj.get("endPos") or {}
        message = str(obj.get("data", ""))
        diags.append({
            "severity": obj.get("severity", "error"),
            "kind": obj.get("kind") or "",
            "line": pos.get("line"),
            "col": pos.get("column"),
            "end_line": end.get("line"),
            "end_col": end.get("column"),
            "message": message,
            "cls": "sorry" if obj.get("kind") == "hasSorry" else classify_diagnostic(message),
            "file": obj.get("fileName"),
        })
    return diags, noise


def summarize(diags: list[dict]) -> dict:
    errors = [d for d in diags if d["severity"] == "error"]
    warnings = [d for d in diags if d["severity"] == "warning"]
    return {
        "errors": len(errors),
        "warnings": len(warnings),
        "sorry_lines": sorted({d["line"] for d in diags if d["cls"] == "sorry" and d.get("line")}),
        "classes": sorted({d["cls"] for d in errors}),
    }
