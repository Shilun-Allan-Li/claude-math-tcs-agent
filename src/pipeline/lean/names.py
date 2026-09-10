"""Resolve Lean names against the real environment.

Report 02 §B7 is why this exists: twelve declarations were written, proved, and later
archived as exact Mathlib duplicates, and one duplicate verdict was itself reversed after
someone finally checked whether the Mathlib lemma existed. Both directions of that mistake
— asserting a name exists when it does not, and asserting it does not when it does — cost
real work, and both are settled exactly by asking Lean.

Also used for shadowing detection: a declaration named ``SimpleGraph.dist_triangle`` shadows
the ambient ``dist_triangle`` inside ``namespace SimpleGraph`` (issue ``i-084``), and that is
decidable by asking whether the short name already resolves.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["NameResolution", "resolve_names"]

#: ``/path/NameProbe.lean:3:8: error(lean.unknownIdentifier): Unknown constant `X```
_ERROR_LINE_RE = re.compile(r":(?P<line>\d+):\d+:\s*error[^:]*:\s*(?P<message>.*)$")
#: ``@SimpleGraph.induce : {V : Type u_1} → ...``
_CHECK_RE = re.compile(r"^@(?P<name>\S+)\s*:\s*(?P<type>.*)$")


@dataclass(frozen=True)
class NameResolution:
    name: str
    exists: bool
    type_signature: str | None = None
    error: str | None = None


def resolve_names(
    names: Sequence[str],
    *,
    imports: Sequence[str] = ("Mathlib",),
    open_namespaces: Sequence[str] = (),
    cwd: str | Path | None = None,
    lake: str = "lake",
    timeout: float = 900.0,
) -> dict[str, NameResolution]:
    """Ask Lean whether each name resolves, and to what.

    One invocation for the whole batch. Successes are matched by the ``@Name`` echoed in
    the ``#check`` output; failures are matched by the line number in the error, since a
    failed check produces no echo. Both channels are needed: neither alone covers both
    outcomes.
    """
    if not names:
        return {}
    header = [f"import {i}" for i in imports]
    header += [f"open {ns}" for ns in open_namespaces]
    header.append("set_option maxHeartbeats 1000000")
    body = [f"#check @{name}" for name in names]
    source = "\n".join(header + body) + "\n"
    first_check_line = len(header) + 1  # 1-based

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "NameProbe.lean"
        path.write_text(source, encoding="utf-8")
        proc = subprocess.run(
            [lake, "env", "lean", str(path)],
            cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=timeout,
        )
    output = (proc.stdout or "") + (proc.stderr or "")

    resolved: dict[str, NameResolution] = {}
    failed: dict[int, str] = {}
    for line in output.splitlines():
        if m := _ERROR_LINE_RE.search(line):
            index = int(m.group("line")) - first_check_line
            if 0 <= index < len(names):
                failed[index] = m.group("message").strip()
        elif m := _CHECK_RE.match(line.strip()):
            resolved[m.group("name")] = NameResolution(
                name=m.group("name"), exists=True, type_signature=m.group("type").strip()
            )

    out: dict[str, NameResolution] = {}
    for i, name in enumerate(names):
        if i in failed:
            out[name] = NameResolution(name=name, exists=False, error=failed[i])
        elif name in resolved:
            out[name] = resolved[name]
        else:
            out[name] = NameResolution(
                name=name, exists=False, error="no output from #check (name did not resolve)"
            )
    return out
