"""``promote``: move a proof from a scratch attempt into the canonical module.

Promotion re-verifies against the *current* canonical module (not the copy the prover
started from): the attempt's block is merged into an in-memory copy of the canonical
text, checked on a scratch file with ``#print axioms``, and written back only if the main
declaration is ``FULLY_VERIFIED`` (no ``sorryAx``, only allowlisted axioms) and its
statement signature is unchanged. Helper obligations are recorded from the same run.
"""

from __future__ import annotations

from pathlib import Path

from . import blocks as bl
from . import manifest as mf
from .lean_check import check_module
from .util import MathTcsError, write_text_atomic

__all__ = ["promote"]


def promote(root: Path, cfg: dict, decl_id: str, *, attempt_file: Path | None, proof_file: Path | None,
            at: str | None, timeout: float | None = None, force: bool = False) -> dict:
    entry = mf.get(root, cfg, decl_id)
    lean = entry.get("lean") or {}
    if not lean.get("path"):
        raise MathTcsError(f"{decl_id} has no Lean block", code=1)
    mpath = root / lean["path"]
    canonical = mpath.read_text(encoding="utf-8")
    cur = bl.block_by_id(canonical, decl_id)
    if cur is None:
        raise MathTcsError(f"block {decl_id} missing from {lean['path']}", code=1)
    if lean.get("block_sha256") and cur.sha != lean["block_sha256"] and not force:
        return {"id": decl_id, "promoted": False, "reason": "canonical block changed since it was recorded (human edit?); run snapshot/touch first"}
    cur_main = bl.main_declaration(cur.inner)
    if cur_main is None:
        raise MathTcsError(f"block {decl_id} has no declaration", code=1)
    expected_sig_sha = bl.statement_sha(cur_main["text"])

    if attempt_file is not None:
        att_text = attempt_file.read_text(encoding="utf-8")
        att_block = bl.block_by_id(att_text, decl_id)
        if att_block is None:
            raise MathTcsError(f"attempt file has no block {decl_id}", code=1)
        new_inner = att_block.inner
    elif proof_file is not None:
        proof = proof_file.read_text(encoding="utf-8")
        new_decl = bl.replace_proof(cur_main["text"], proof)
        inner_lines = cur.inner.splitlines()
        inner_lines[cur_main["start"]:cur_main["end"]] = new_decl.splitlines()
        new_inner = "\n".join(inner_lines)
    else:
        raise MathTcsError("promote needs --attempt <file> or --proof <file>", code=1)

    new_main = bl.main_declaration(new_inner)
    if new_main is None:
        return {"id": decl_id, "promoted": False, "reason": "attempt block has no declaration"}
    try:
        new_sig_sha = bl.statement_sha(new_main["text"])
    except ValueError as exc:
        return {"id": decl_id, "promoted": False, "reason": f"attempt declaration unparseable: {exc}"}
    if new_sig_sha != expected_sig_sha:
        return {"id": decl_id, "promoted": False, "reason": "statement signature changed in the attempt; a proof of a different statement is not accepted",
                "expected_statement_sha256": expected_sig_sha, "attempt_statement_sha256": new_sig_sha}
    if new_main["name"] != cur_main["name"]:
        return {"id": decl_id, "promoted": False, "reason": f"declaration renamed ({cur_main['name']} → {new_main['name']})"}

    rev = int(lean.get("rev") or cur.rev)
    new_block = "\n".join([f"-- math-tcs:begin id={decl_id} rev={rev}", new_inner.rstrip("\n"), f"-- math-tcs:end id={decl_id}"])
    merged, outcome = bl.upsert_block(canonical, new_block, decl_id=decl_id, force=True)
    if outcome == "unchanged":
        merged = canonical
    tmp_dir = root / cfg["paths"]["scratch"] / "promote" / decl_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    candidate = tmp_dir / "candidate.lean"
    write_text_atomic(candidate, merged)
    res = check_module(root, cfg, candidate, tag=f"promote/{decl_id}", axioms=True, timeout=timeout,
                       kinds={decl_id: entry.get("kind") or "theorem"})
    binfo = res["blocks"].get(decl_id, {})
    main_full = binfo.get("main")
    main_info = res["declarations"].get(main_full or "", {}) or {}
    helpers = []
    for name in binfo.get("declarations", [])[:-1]:
        h = res["declarations"].get(name, {})
        helpers.append({"name": name, "trust": h.get("trust"), "axioms": h.get("axioms")})
    trust = main_info.get("trust") or binfo.get("trust") or "UNKNOWN"
    result = {"id": decl_id, "rev": rev, "trust": trust, "axioms": main_info.get("axioms"), "helpers": helpers,
              "module_ok": res["ok"], "timeout": res["timeout"], "wall_ms": res["wall_ms"], "scratch": res["scratch"],
              "errors": [d["message"].splitlines()[0][:200] for d in binfo.get("diagnostics", []) if d["severity"] == "error"],
              "unattributed_errors": [d["message"][:200] for d in res["unattributed_errors"]]}
    data = mf.load(root, cfg)
    e = data["declarations"][decl_id]
    if trust != "FULLY_VERIFIED" or not res["ok"]:
        e["helpers"] = helpers
        e["trust"] = {"status": trust, "axioms": main_info.get("axioms"), "checked_rev": rev}
        e["status"] = "unfinished" if trust in {"TRANSITIVE_SORRY", "DIRECT_SORRY", "BLOCKED_BY_UNTRUSTED_DEPENDENCY"} else "failed"
        mf.history(e, "promote:rejected", at=at, trust=trust)
        mf.save(root, cfg, data)
        return {**result, "promoted": False, "reason": f"candidate is {trust}" + ("" if res["ok"] else " (module has errors)"), "status": e["status"]}
    write_text_atomic(mpath, merged)
    nb = bl.block_by_id(merged, decl_id)
    e["lean"]["block_sha256"] = nb.sha if nb else None
    e["lean"]["statement_sha256"] = expected_sig_sha
    e["trust"] = {"status": trust, "axioms": main_info.get("axioms"), "checked_rev": rev}
    e["helpers"] = helpers
    e["status"] = "proved"
    e["human_edited"] = False
    mf.history(e, "promote:accepted", at=at, axioms=main_info.get("axioms"))
    mf.save(root, cfg, data)
    return {**result, "promoted": True, "status": "proved", "path": lean["path"]}
