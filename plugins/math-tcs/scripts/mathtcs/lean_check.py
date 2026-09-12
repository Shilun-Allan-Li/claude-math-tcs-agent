"""Lean elaboration + axiom check of a generated module, on a scratch copy.

One process per check: copy the module to ``math-tcs/scratch/<tag>/attempt-<n>.lean``,
optionally substitute one proof, append ``#print axioms <Full.Name>`` for every
declaration in every block, run ``lake lean <scratch> -- --json`` (fallback
``lake env lean --json``), and read elaboration diagnostics and axiom verdicts from the
same run. The canonical module is never touched here.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from . import axioms as ax
from . import blocks as bl
from .lean_json import parse_lean_json, summarize
from .util import MathTcsError, write_text_atomic

__all__ = ["run_lean", "check_module", "scratch_path"]


def scratch_path(root: Path, cfg: dict, tag: str, attempt: int | None = None) -> Path:
    d = root / cfg["paths"]["scratch"] / tag
    d.mkdir(parents=True, exist_ok=True)
    if attempt is None:
        n = 1
        while (d / f"attempt-{n}.lean").exists():
            n += 1
        attempt = n
    return d / f"attempt-{attempt}.lean"


def run_lean(root: Path, file: Path, *, mode: str = "lake lean", timeout: float = 600.0) -> dict:
    if mode == "lake lean":
        cmd = ["lake", "lean", str(file), "--", "--json"]
    else:
        cmd = ["lake", "env", "lean", "--json", str(file)]
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {"exit": None, "timeout": True, "command": cmd, "wall_ms": int((time.monotonic() - started) * 1000),
                "diagnostics": [], "noise": [f"timeout after {timeout}s"], "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else ""}
    except FileNotFoundError as exc:
        raise MathTcsError(f"lake not found on PATH ({exc})", code=2)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    diags, noise = parse_lean_json(output)
    if mode == "lake lean" and proc.returncode != 0 and not diags and any("unknown" in n.lower() or "error" in n.lower() for n in noise):
        # Lake refused the invocation itself (e.g. no `lake lean` support): fall back once.
        return run_lean(root, file, mode="lake env lean", timeout=timeout)
    return {"exit": proc.returncode, "timeout": False, "command": cmd,
            "wall_ms": int((time.monotonic() - started) * 1000), "diagnostics": diags, "noise": noise}


def _full_name(namespace: str | None, name: str) -> str:
    if not name:
        return name
    if namespace and not name.startswith(namespace + ".") and name != namespace:
        return f"{namespace}.{name}"
    return name


def _line_to_block(blocks: list[bl.Block], line: int) -> bl.Block | None:
    for b in blocks:
        if b.start + 1 <= line <= b.end + 1:  # 1-based lines
            return b
    return None


def check_module(root: Path, cfg: dict, module_file: Path, *, tag: str, attempt: int | None = None,
                 substitute: dict | None = None, axioms: bool = True, timeout: float | None = None,
                 kinds: dict[str, str] | None = None) -> dict:
    """Check ``module_file`` on a scratch copy.

    ``substitute`` = ``{"id": decl_id, "proof": tactic_text}`` replaces the main declaration's
    body of that block before checking. ``kinds`` maps decl id -> source kind (to decide
    ``is_object``)."""
    text = module_file.read_text(encoding="utf-8")
    blocks = bl.parse_blocks(text)
    if substitute:
        b = bl.block_by_id(text, substitute["id"])
        if b is None:
            raise MathTcsError(f"no block {substitute['id']} in {module_file}", code=1)
        main = bl.main_declaration(b.inner)
        if main is None:
            raise MathTcsError(f"block {substitute['id']} has no declaration", code=1)
        new_decl = bl.replace_proof(main["text"], substitute["proof"])
        inner_lines = b.inner.splitlines()
        inner_lines[main["start"]:main["end"]] = new_decl.splitlines()
        new_block = "\n".join([f"-- math-tcs:begin id={b.id} rev={b.rev}", *inner_lines, f"-- math-tcs:end id={b.id}"])
        text, _ = bl.upsert_block(text, new_block, decl_id=b.id, force=True)
        blocks = bl.parse_blocks(text)
    namespace = bl.namespace_of(text)
    names: dict[str, list[dict]] = {}
    probe_lines: list[str] = []
    if axioms:
        for b in blocks:
            decls = bl.declarations_in(b.inner)
            names[b.id] = [{"kw": d["kw"], "name": d["name"], "full": _full_name(namespace, d["name"] or ""),
                            "start": b.start + 1 + d["start"] + 1, "end": b.start + 1 + d["end"]} for d in decls if d["name"]]
            for d in names[b.id]:
                if d["kw"] not in {"example", "instance"} or d["name"]:
                    probe_lines.append(f"#print axioms {d['full']}")
    scratch_text = text.rstrip("\n") + "\n"
    if probe_lines:
        scratch_text += "\n-- math-tcs axiom probe (appended on the scratch copy only)\n" + "\n".join(probe_lines) + "\n"
    spath = scratch_path(root, cfg, tag, attempt)
    write_text_atomic(spath, scratch_text)
    result = run_lean(root, spath, mode=cfg.get("lean", {}).get("check", "lake lean"),
                      timeout=timeout or cfg.get("lean", {}).get("timeout_s", 600))
    diags = result["diagnostics"]
    errors = [d for d in diags if d["severity"] == "error"]
    ok = result["exit"] == 0 and not errors and not result["timeout"]
    reports = ax.parse_axiom_messages(diags) if axioms else {}
    allow = cfg.get("axioms", {}).get("allow")
    sorry_lines = {d["line"] for d in diags if d["cls"] == "sorry" and d.get("line")}
    per_decl: dict[str, dict] = {}
    per_block: dict[str, dict] = {}
    for b in blocks:
        b_diags = [d for d in diags if d.get("line") and b.start + 1 <= d["line"] <= b.end + 1]
        b_errors = [d for d in b_diags if d["severity"] == "error"]
        per_block[b.id] = {"errors": len(b_errors), "warnings": len([d for d in b_diags if d["severity"] == "warning"]),
                           "diagnostics": b_diags, "declarations": []}
        kind = (kinds or {}).get(b.id, "theorem")
        is_object = kind in {"definition", "construction", "notation"}
        for d in names.get(b.id, []):
            direct = any(d["start"] <= ln <= d["end"] for ln in sorry_lines)
            compiled = not any(d["start"] <= e.get("line", -1) <= d["end"] for e in errors) and not result["timeout"]
            report = reports.get(d["full"])
            trust = ax.compute_trust(compiled=compiled and result["exit"] is not None, axioms=report, allow=allow,
                                     is_object=is_object and d["kw"] in {"def", "abbrev", "structure", "inductive", "instance", "opaque"},
                                     direct_sorry=direct)
            entry = {"block": b.id, "kw": d["kw"], "name": d["full"], "lines": [d["start"], d["end"]],
                     "direct_sorry": direct, "axioms": report, "trust": trust,
                     "verdict": ax.verdict(report, allow) if report is not None else None}
            per_decl[d["full"]] = entry
            per_block[b.id]["declarations"].append(d["full"])
        mains = per_block[b.id]["declarations"]
        per_block[b.id]["main"] = mains[-1] if mains else None
        per_block[b.id]["trust"] = per_decl[mains[-1]]["trust"] if mains else ("COMPILE_FAILURE" if b_errors else "UNKNOWN")
    unattributed = [d for d in diags if d["severity"] == "error" and (not d.get("line") or _line_to_block(blocks, d["line"]) is None)]
    return {
        "ok": ok,
        "exit": result["exit"],
        "timeout": result["timeout"],
        "command": " ".join(result["command"]),
        "wall_ms": result["wall_ms"],
        "scratch": os.path.relpath(spath, root),
        "summary": summarize(diags),
        "diagnostics": diags,
        "noise": result["noise"][:50],
        "unattributed_errors": unattributed,
        "blocks": per_block,
        "declarations": per_decl,
    }
