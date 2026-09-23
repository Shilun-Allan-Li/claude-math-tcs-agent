"""Check explicit declarations in ordinary Lean files without a manifest."""
from __future__ import annotations

import math
import re
import tempfile
from pathlib import Path

from .axioms import DEFAULT_ALLOWLIST, parse_axiom_messages, verdict
from .lean_check import run_lean
from .util import MathTcsError, sha256_text


def declaration_name(name: str) -> str:
    # Deliberately exclude command injection; quoted/unusual names need future support.
    if not re.fullmatch(r"[^\W\d][\w']*(?:\.[^\W\d][\w']*)*", name, re.UNICODE):
        raise MathTcsError("use an explicit qualified Lean identifier (no quoted names)")
    return name


def check_text(root: Path, text: str, names: list[str], timeout: float = 120) -> dict:
    if not names or not math.isfinite(timeout) or timeout <= 0:
        raise MathTcsError("provide declarations and a finite positive timeout", code=2)
    names = list(dict.fromkeys(declaration_name(n) for n in names))
    # Exact probe positions prevent earlier user-generated messages being mistaken for probes.
    body = text.rstrip("\n") + "\n\n"
    first_line = body.count("\n") + 1
    body += "\n".join(f"#print axioms _root_.{n}" for n in names) + "\n"
    scratch = root / "math-tcs" / "scratch" / "plain"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="check-", dir=scratch) as directory:
        path = Path(directory) / "Candidate.lean"
        path.write_text(body, encoding="utf-8")
        result = run_lean(root, path, mode="lake env lean", timeout=timeout)
    compiled = result["exit"] == 0 and not result["timeout"] and not any(
        d["severity"] == "error" for d in result["diagnostics"])
    declarations = {}
    for offset, name in enumerate(names):
        messages = [d for d in result["diagnostics"] if d.get("line") == first_line + offset]
        axioms = parse_axiom_messages(messages).get(name)
        trusted = compiled and axioms is not None and verdict(axioms)["trusted"]
        declarations[name] = {"axioms": axioms, "verified": trusted}
    return {"schema": "plain-check/v1", "ok": all(d["verified"] for d in declarations.values()),
            "compiled": compiled, "source_sha256": sha256_text(text), "declarations": declarations,
            "allowlist": list(DEFAULT_ALLOWLIST), "diagnostics": result["diagnostics"],
            "timeout": result["timeout"], "wall_ms": result["wall_ms"], "exit": result["exit"],
            "noise": result["noise"], "sorry_warnings": sum(
                d.get("cls") == "sorry" for d in result["diagnostics"])}


def check_file(root: Path, path: Path, names: list[str], timeout: float = 120) -> dict:
    text = path.read_text(encoding="utf-8")
    result = check_text(root, text, names, timeout)
    result["file"] = str(path)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        result.update(ok=False, reason="source changed during checking")
    return result
