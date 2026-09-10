"""``#print axioms`` -- the authoritative trust verdict.

A declaration is trustworthy exactly when its axiom set contains no ``sorryAx``. This is
decided by the kernel, over the whole transitive closure, and it cannot be wrong.

The alternative, which the summer used twice, is to look for the token ``sorry`` in some
range of source text. Report 05 §3.4 measured that: the blueprint's detector read `.ilean`
reference ranges that stop before a `sorry` body, so it emitted `\\leanok` for 33 of 33
chapter-1 declarations. And no text heuristic can ever see a *transitive* `sorry` --
`whitney_inequalities` has none of its own and is unproved.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["AxiomReport", "print_axioms", "SORRY_AXIOM"]

SORRY_AXIOM = "sorryAx"

#: ``'Name' depends on axioms: [a, b, c]`` -- the list may wrap across lines.
_HEADER_RE = re.compile(r"^'(?P<name>[^']+)' depends on axioms: \[(?P<rest>.*)$")
_NO_AXIOMS_RE = re.compile(r"^'(?P<name>[^']+)' does not depend on any axioms")


@dataclass(frozen=True)
class AxiomReport:
    name: str
    axioms: tuple[str, ...]

    @property
    def uses_sorry(self) -> bool:
        return SORRY_AXIOM in self.axioms

    @property
    def is_trusted(self) -> bool:
        """No ``sorryAx``. Standard axioms (propext, Classical.choice, Quot.sound) are fine.

        Those three are the ordinary foundation of classical mathematics in Lean and every
        Mathlib theorem uses them; treating them as untrusted would mark the entire library
        suspect.
        """
        return not self.uses_sorry


def print_axioms(
    module: str,
    names: Sequence[str],
    *,
    cwd: str | Path | None = None,
    lake: str = "lake",
    timeout: float = 900.0,
) -> tuple[dict[str, AxiomReport], str]:
    """Report the axiom set of each name. Returns (reports, raw_output).

    One Lean invocation for all names: the module is already built, so this is an
    environment load plus a lookup per name.
    """
    if not names:
        return {}, ""
    source = f"import {module}\n" + "".join(f"#print axioms {n}\n" for n in names)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "AxiomProbe.lean"
        path.write_text(source, encoding="utf-8")
        proc = subprocess.run(
            [lake, "env", "lean", str(path)],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout,
        )
    output = (proc.stdout or "") + (proc.stderr or "")

    reports: dict[str, AxiomReport] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current, buffer
        if current is not None:
            axioms = tuple(
                a.strip() for a in "".join(buffer).rstrip("]").split(",") if a.strip()
            )
            reports[current] = AxiomReport(name=current, axioms=axioms)
        current, buffer = None, []

    for raw in output.splitlines():
        line = raw.rstrip()
        if m := _NO_AXIOMS_RE.match(line.strip()):
            flush()
            reports[m.group("name")] = AxiomReport(name=m.group("name"), axioms=())
            continue
        if m := _HEADER_RE.match(line.strip()):
            flush()
            current = m.group("name")
            buffer = [m.group("rest")]
            if "]" in m.group("rest"):
                flush()
            continue
        if current is not None:
            buffer.append(line.strip())
            if "]" in line:
                flush()
    flush()
    return reports, output
