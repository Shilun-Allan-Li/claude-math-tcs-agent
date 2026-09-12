"""Axiom reports from ``#print axioms`` and the allowlist verdict.

Ported from ``b753236:src/pipeline/lean/axioms.py`` (regexes and the line-wrap tolerant
parser) with one addition the old engine did not have: an *allowlist*. The old
``is_trusted`` was merely ``not uses_sorry``; here a proof is trusted only if every axiom
it depends on is in the documented allowlist, and ``sorryAx`` is rejected even if a config
lists it.

Trust vocabulary ported from ``checkers/lean_integrity.py::_compute_trust``.
"""

from __future__ import annotations

import re

__all__ = [
    "SORRY_AXIOM",
    "DEFAULT_ALLOWLIST",
    "parse_axiom_messages",
    "parse_axiom_text",
    "verdict",
    "compute_trust",
]

SORRY_AXIOM = "sorryAx"
#: Lean's standard logical axioms -- the ordinary foundation of classical mathematics.
DEFAULT_ALLOWLIST: tuple[str, ...] = ("propext", "Classical.choice", "Quot.sound")

_HEADER_RE = re.compile(r"^'(?P<name>[^']+)' depends on axioms: \[(?P<rest>.*)$", re.S)
_NO_AXIOMS_RE = re.compile(r"^'(?P<name>[^']+)' does not depend on any axioms")


def parse_axiom_text(text: str) -> dict[str, list[str]]:
    """Parse plain ``#print axioms`` output (possibly line-wrapped) -> {name: [axioms]}."""
    reports: dict[str, list[str]] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current, buffer
        if current is not None:
            joined = "".join(buffer)
            joined = joined.split("]", 1)[0]
            reports[current] = [a.strip() for a in joined.split(",") if a.strip()]
        current, buffer = None, []

    for raw in text.splitlines():
        line = raw.strip()
        if m := _NO_AXIOMS_RE.match(line):
            flush()
            reports[m.group("name")] = []
            continue
        if m := _HEADER_RE.match(line):
            flush()
            current = m.group("name")
            buffer = [m.group("rest")]
            if "]" in m.group("rest"):
                flush()
            continue
        if current is not None:
            buffer.append(line)
            if "]" in line:
                flush()
    flush()
    return reports


def parse_axiom_messages(diags: list[dict]) -> dict[str, list[str]]:
    """Extract axiom reports from parsed ``--json`` diagnostics (``information`` messages)."""
    reports: dict[str, list[str]] = {}
    for d in diags:
        if d.get("severity") != "information":
            continue
        msg = d.get("message", "")
        if "depends on axioms" in msg or "does not depend on any axioms" in msg:
            reports.update(parse_axiom_text(msg))
    return reports


def verdict(axioms: list[str], allow: list[str] | tuple[str, ...] | None = None) -> dict:
    """``{trusted, uses_sorry, disallowed}`` for one declaration's axiom set."""
    allowed = set(allow if allow is not None else DEFAULT_ALLOWLIST) - {SORRY_AXIOM}
    uses_sorry = SORRY_AXIOM in axioms
    disallowed = sorted(a for a in axioms if a not in allowed and a != SORRY_AXIOM)
    return {"trusted": not uses_sorry and not disallowed, "uses_sorry": uses_sorry, "disallowed": disallowed}


def compute_trust(
    *,
    compiled: bool,
    axioms: list[str] | None,
    allow: list[str] | tuple[str, ...] | None,
    is_object: bool,
    direct_sorry: bool,
    blocked_by: list[str] | None = None,
) -> str:
    """The trust status vocabulary (humans read it, hence uppercase).

    ``COMPILE_FAILURE`` > ``UNKNOWN`` (no axiom report) > ``NONSTANDARD_AXIOM`` >
    ``FULLY_VERIFIED`` > ``UNFINISHED_CONSTRUCTION`` (object with its own sorry) >
    ``BLOCKED_BY_UNTRUSTED_DEPENDENCY`` > ``DIRECT_SORRY`` > ``TRANSITIVE_SORRY``."""
    if not compiled:
        return "COMPILE_FAILURE"
    if axioms is None:
        return "UNKNOWN"
    v = verdict(axioms, allow)
    if not v["uses_sorry"]:
        return "FULLY_VERIFIED" if not v["disallowed"] else "NONSTANDARD_AXIOM"
    if is_object and direct_sorry:
        return "UNFINISHED_CONSTRUCTION"
    if blocked_by:
        return "BLOCKED_BY_UNTRUSTED_DEPENDENCY"
    if direct_sorry:
        return "DIRECT_SORRY"
    return "TRANSITIVE_SORRY"
