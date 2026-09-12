"""Lean probes used by the scaffolder, the reuse reviewer and the prover.

* ``check``: does ``@Name`` exist, and what is its type? (one ``lake env lean`` run for a
  batch of names; failures are correlated by line because a failed ``#check`` prints only
  an error at its line)
* ``tactic``: try a tactic (``exact?``, ``apply?``, ``simp?``, ``exact <term>``) as the body of
  a block's main declaration on a scratch copy and return Lean's messages, including
  ``Try this:`` suggestions.

Everything is written under ``math-tcs/scratch/probe/`` -- never in the lib.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import blocks as bl
from .lean_check import check_module, run_lean
from .util import MathTcsError, write_text_atomic

__all__ = ["check_names", "try_tactic"]

_CHECK_LINE_RE = re.compile(r"^@?(?P<name>[^\s:]+)\s*:\s*(?P<type>.*)$", re.S)


def check_names(root: Path, cfg: dict, names: list[str], *, imports: list[str] | None = None,
                opens: list[str] | None = None, timeout: float | None = None) -> dict:
    if not names:
        return {"results": {}, "wall_ms": 0}
    header = [f"import {i}" for i in (imports or ["Mathlib"])]
    if opens:
        header.append("open " + " ".join(opens))
    first = len(header) + 1
    lines = header + [f"#check @{n}" for n in names]
    d = root / cfg["paths"]["scratch"] / "probe"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "NameProbe.lean"
    write_text_atomic(path, "\n".join(lines) + "\n")
    res = run_lean(root, path, mode="lake env lean", timeout=timeout or cfg["lean"].get("timeout_s", 600))
    results: dict[str, dict] = {n: {"exists": False, "type": None, "message": None} for n in names}
    for dg in res["diagnostics"]:
        ln = dg.get("line")
        if not ln or ln < first or ln - first >= len(names):
            continue
        name = names[ln - first]
        if dg["severity"] == "information":
            m = _CHECK_LINE_RE.match(dg["message"].strip())
            results[name] = {"exists": True, "type": (m.group("type").strip() if m else dg["message"].strip()), "message": None}
        elif dg["severity"] == "error":
            results[name] = {"exists": False, "type": None, "message": dg["message"].strip()[:400]}
    return {"results": results, "wall_ms": res["wall_ms"], "exit": res["exit"], "timeout": res["timeout"],
            "noise": res["noise"][:10]}


def try_tactic(root: Path, cfg: dict, module_file: Path, decl_id: str, tactic: str, *, timeout: float | None = None) -> dict:
    """Substitute ``tactic`` as the proof of the block's main declaration and report."""
    text = module_file.read_text(encoding="utf-8")
    if bl.block_by_id(text, decl_id) is None:
        raise MathTcsError(f"no block {decl_id} in {module_file}", code=1)
    res = check_module(root, cfg, module_file, tag=f"probe/{decl_id}", substitute={"id": decl_id, "proof": tactic},
                       axioms=False, timeout=timeout)
    blk = res["blocks"].get(decl_id, {})
    suggestions = [d["message"] for d in blk.get("diagnostics", []) if "Try this" in d.get("message", "")]
    errors = [d["message"][:600] for d in blk.get("diagnostics", []) if d["severity"] == "error"]
    ok = res["ok"] and not errors
    return {"ok": ok, "tactic": tactic, "suggestions": suggestions, "errors": errors,
            "wall_ms": res["wall_ms"], "scratch": res["scratch"], "timeout": res["timeout"]}
