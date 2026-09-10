"""Run ``lake build`` and parse its diagnostics."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Diagnostic", "BuildResult", "lake_build", "classify_diagnostic"]

#: ``warning: fixtures/lean/Connectivity.lean:100:8: declaration uses 'sorry'``
_DIAGNOSTIC_RE = re.compile(
    r"^(?P<severity>error|warning|info):\s+(?P<file>[^:\s][^:]*):(?P<line>\d+):(?P<col>\d+):\s*(?P<message>.*)$"
)
_BARE_RE = re.compile(r"^(?P<severity>error|warning):\s+(?P<message>.*)$")

_SORRY_RE = re.compile(r"declaration uses .?sorry", re.I)

#: Diagnostic classification. The vocabulary is the one report 04 §B7 measured: nine of
#: fifteen build cycles in the summer's one instrumented session were Lean-surface
#: friction of exactly these kinds, and none were mathematical.
_CLASSIFIERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sorry", _SORRY_RE),
    ("unknown_identifier", re.compile(r"unknown (identifier|constant)|does not contain", re.I)),
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


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    message: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    kind: str = "other"

    @property
    def is_sorry_warning(self) -> bool:
        return self.kind == "sorry"


@dataclass
class BuildResult:
    module: str
    ok: bool
    diagnostics: list[Diagnostic] = field(default_factory=list)
    stdout: str = ""
    wall_ms: int = 0
    command: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def sorry_lines(self) -> set[int]:
        """Lines Lean itself reported as using ``sorry``.

        Used to attribute a `sorry` to a declaration by position. It is a cross-check on
        the axiom report, never a substitute: a declaration can depend on ``sorryAx``
        without Lean warning at its own line, which is precisely the transitive case.
        """
        return {d.line for d in self.diagnostics if d.is_sorry_warning and d.line}


def lake_build(
    module: str,
    *,
    cwd: str | Path | None = None,
    lake: str = "lake",
    timeout: float = 900.0,
) -> BuildResult:
    """Build one module and return its diagnostics.

    Targeted at a single module deliberately. Report 04 measured the summer's incremental
    build at roughly one to two seconds against a pre-built Mathlib, and that speed is
    what made the typechecker usable as the checker rather than as a nightly job.
    """
    command = [lake, "build", module]
    started = time.monotonic()
    proc = subprocess.run(
        command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    diagnostics: list[Diagnostic] = []
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("trace:"):
            continue
        if m := _DIAGNOSTIC_RE.match(line):
            diagnostics.append(
                Diagnostic(
                    severity=m.group("severity"),
                    message=m.group("message").strip(),
                    file=m.group("file"),
                    line=int(m.group("line")),
                    column=int(m.group("col")),
                    kind=classify_diagnostic(m.group("message")),
                )
            )
        elif m := _BARE_RE.match(line):
            message = m.group("message").strip()
            if message.startswith(("Lean exited", "build failed", "Some required targets")):
                continue
            diagnostics.append(
                Diagnostic(severity=m.group("severity"), message=message,
                           kind=classify_diagnostic(message))
            )
    return BuildResult(
        module=module,
        ok=proc.returncode == 0,
        diagnostics=diagnostics,
        stdout=output,
        wall_ms=int((time.monotonic() - started) * 1000),
        command=command,
    )
