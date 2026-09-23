"""Verify snapshots and reports; prove reports.

``snapshot`` freezes one declaration revision under ``reports/<id>/rev<N>/`` so that
both reviewers read the same statement (``context.json`` carries ``statement_sha256``,
which they must echo). ``combine`` merges the formal check, the two model reviews and the
(always ``none`` here) human approval into one report and derives the recommended action
with fixed rules. A missing review is recorded as missing, never silently dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import annotated_md
from . import blocks as bl
from . import manifest as mf
from .lean_check import check_module
from .util import MathTcsError, read_json, write_json_atomic, write_text_atomic

__all__ = ["snapshot", "combine", "prove_report", "ACTIONS"]

ACTIONS = ("reuse", "prove", "repair_statement", "defer")
_HIGH = {"high", "critical"}


def _report_dir(root: Path, cfg: dict, decl_id: str, rev: int) -> Path:
    return root / cfg["paths"]["reports"] / decl_id / f"rev{rev}"


def snapshot(root: Path, cfg: dict, decl_id: str, *, at: str | None, timeout: float | None = None,
             check: bool = True) -> dict:
    touched = mf.touch(root, cfg, decl_id, at=at)
    entry = mf.get(root, cfg, decl_id)
    lean = entry.get("lean") or {}
    if lean.get("representation") == "existing":
        return {"id": decl_id, "skipped": True, "reason": "existing representation (maps to an existing declaration)",
                "existing_name": lean.get("existing_name")}
    if not lean.get("path"):
        raise MathTcsError(f"{decl_id} has no Lean block to verify (status {entry.get('status')})", code=1)
    mpath = root / lean["path"]
    text = mpath.read_text(encoding="utf-8")
    b = bl.block_by_id(text, decl_id)
    if b is None:
        raise MathTcsError(f"block {decl_id} missing from {lean['path']}", code=1)
    main = bl.main_declaration(b.inner)
    rev = int(lean.get("rev") or b.rev or 1)
    rdir = _report_dir(root, cfg, decl_id, rev)
    rdir.mkdir(parents=True, exist_ok=True)
    statement_sha = bl.statement_sha(main["text"]) if main else None
    write_text_atomic(rdir / "statement.lean", b.inner.rstrip("\n") + "\n")
    ann = entry.get("annotated") or {}
    section = None
    if ann.get("path") and (root / ann["path"]).exists():
        section = annotated_md.section_for((root / ann["path"]).read_text(encoding="utf-8"), decl_id)
    siblings = []
    for other in bl.parse_blocks(text):
        if other.id == decl_id:
            continue
        om = bl.main_declaration(other.inner)
        if om:
            try:
                sig, _ = bl.split_statement(om["text"])
            except ValueError:
                sig = om["text"]
            siblings.append({"id": other.id, "name": om["name"], "signature": sig})
    context = {
        "math-tcs": "verify-context/v1", "id": decl_id, "rev": rev, "at": at,
        "statement_sha256": statement_sha, "block_sha256": b.sha,
        "module": {"path": lean["path"], "name": lean.get("module"), "namespace": bl.namespace_of(text),
                   "imports": bl.module_imports(text)},
        "lean_name": lean.get("name"), "kind": entry.get("kind"), "label": entry.get("label"),
        "statement_lean": main["text"] if main else b.inner,
        "helpers": [d["name"] for d in bl.declarations_in(b.inner)[:-1]],
        "source": entry.get("source"),
        "annotation": None if section is None else {
            "meta": section.get("meta"), "source_statement": section.get("source_statement"),
            "source_proof": section.get("source_proof"), "interpretation": section.get("interpretation")},
        "siblings": siblings,
        "files": {"statement": str((rdir / "statement.lean").relative_to(root)),
                  "annotated": ann.get("path"), "module": lean["path"]},
        "human_edited": entry.get("human_edited", False),
        "stale": touched.get("reasons", []),
    }
    write_json_atomic(rdir / "context.json", context)
    elab = None
    if check:
        res = check_module(root, cfg, mpath, tag=f"verify/{decl_id}", axioms=True, timeout=timeout,
                           kinds={decl_id: entry.get("kind") or "theorem"})
        binfo = res["blocks"].get(decl_id, {})
        main_name = binfo.get("main")
        elab = {
            "math-tcs": "elaboration/v1", "kind": "formal_check", "tool": res["command"], "id": decl_id, "rev": rev,
            "statement_sha256": statement_sha, "ok": res["ok"] and not binfo.get("errors"),
            "module_ok": res["ok"], "timeout": res["timeout"], "wall_ms": res["wall_ms"],
            "trust": binfo.get("trust", "UNKNOWN"),
            "axioms": (res["declarations"].get(main_name or "", {}) or {}).get("axioms"),
            "diagnostics": binfo.get("diagnostics", []),
            "unattributed_errors": [d["message"][:300] for d in res["unattributed_errors"]],
            "scratch": res["scratch"],
        }
        write_json_atomic(rdir / "elaboration.json", elab)
        data = mf.load(root, cfg)
        e = data["declarations"][decl_id]
        e["trust"] = {"status": elab["trust"], "axioms": elab["axioms"], "checked_rev": rev}
        mf.save(root, cfg, data)
    return {"id": decl_id, "rev": rev, "dir": str(rdir.relative_to(root)),
            "context": str((rdir / "context.json").relative_to(root)),
            "statement": str((rdir / "statement.lean").relative_to(root)),
            "elaboration": None if elab is None else {k: elab[k] for k in ("ok", "trust", "axioms", "timeout", "wall_ms")},
            "statement_sha256": statement_sha, "stale": touched.get("reasons", [])}


def _load_review(rdir: Path, name: str, expect_sha: str | None) -> dict:
    p = rdir / f"{name}.json"
    if not p.exists():
        return {"kind": "model_review", "status": "missing", "reason": f"{name}.json not written", "findings": []}
    try:
        obj = read_json(p)
    except Exception as exc:
        return {"kind": "model_review", "status": "invalid", "reason": f"{name}.json unreadable: {exc}", "findings": []}
    if not isinstance(obj, dict):
        return {"kind": "model_review", "status": "invalid", "reason": f"{name}.json is not an object", "findings": []}
    got = obj.get("statement_sha256")
    obj.setdefault("kind", "model_review")
    if not isinstance(got, str) or not got or not expect_sha or got != expect_sha:
        obj["status"] = "revision_mismatch"
        obj["reason"] = "review must identify the exact nonempty snapshot hash"
    elif name == "semantic" and (
        obj.get("verdict") not in {"faithful", "divergent", "uncertain"}
        or not isinstance(obj.get("fidelity_findings"), list)
        or not isinstance(obj.get("degenerate_case_findings"), list)
    ):
        obj.update(status="invalid", reason="incomplete semantic review")
    else:
        obj.setdefault("status", "ok")
    return obj


def _decide(entry: dict, elab: dict | None, sem: dict, reuse: dict, blocked_dep_ids: list[str]) -> dict:
    evidence: list[str] = []
    if elab is None or elab.get("status") == "missing":
        return {"action": "defer", "reason": "no elaboration result", "evidence": ["elaboration.json missing"], "priority": "normal", "reuse_hint": None}
    if not elab.get("ok") or elab.get("trust") in {"COMPILE_FAILURE", "NONSTANDARD_AXIOM"}:
        errs = [d["message"].splitlines()[0][:160] for d in elab.get("diagnostics", []) if d.get("severity") == "error"]
        return {"action": "repair_statement", "reason": f"elaboration failed (trust {elab.get('trust')})",
                "evidence": errs or elab.get("unattributed_errors", []), "priority": "high", "reuse_hint": None}
    if sem.get("status") == "ok":
        for f in sem.get("fidelity_findings", []) or []:
            if f.get("status") == "fail" and str(f.get("severity", "")).lower() in _HIGH and float(f.get("confidence", 0) or 0) >= 0.6:
                evidence.append(f"fidelity {f.get('category')}: {f.get('message', '')[:200]} | source: {f.get('source_quote', '')[:120]} | lean: {f.get('lean_quote', '')[:120]}")
        for f in sem.get("degenerate_case_findings", []) or []:
            if f.get("outcome") == "false":
                evidence.append(f"degenerate {f.get('category')}: {f.get('instantiation', '')} — {f.get('message', '')[:200]}")
        if evidence:
            return {"action": "repair_statement", "reason": "semantic review found a high-severity fidelity defect or a false instantiation",
                    "evidence": evidence, "priority": "high", "reuse_hint": None}
    if entry.get("blockers"):
        return {"action": "defer", "reason": "blockers recorded at scaffold", "evidence": list(entry["blockers"]), "priority": "normal", "reuse_hint": None}
    ann_q = ((entry.get("annotated") or {}).get("blocking_questions")) or []
    if ann_q:
        return {"action": "defer", "reason": "annotation has questions that block formalization", "evidence": ann_q, "priority": "normal", "reuse_hint": None}
    if blocked_dep_ids:
        return {"action": "defer", "reason": "depends on a blocked/failed declaration", "evidence": blocked_dep_ids, "priority": "normal", "reuse_hint": None}
    if sem.get("status") != "ok":
        return {"action": "defer", "reason": f"semantic review {sem.get('status')}: {sem.get('reason', '')}",
                "evidence": [], "priority": "normal", "reuse_hint": None}
    if sem.get("verdict") != "faithful":
        return {"action": "defer", "reason": "semantic fidelity is not established", "evidence": [], "priority": "normal", "reuse_hint": None}
    if reuse.get("status") == "ok":
        verdict = reuse.get("verdict")
        cands = reuse.get("candidates", []) or []
        probed = [c for c in cands if ((c.get("evidence") or {}).get("probe") or {}).get("ok")]
        if verdict == "exists_exact" and probed:
            c = probed[0]
            term = ((c.get("evidence") or {}).get("probe") or {}).get("term") or c.get("name")
            return {"action": "reuse", "reason": f"exact existing result {c.get('name')} verified by probe",
                    "evidence": [json.dumps(c.get("evidence"), ensure_ascii=False)[:300]], "priority": "low", "reuse_hint": term}
        checked = [c for c in cands if (c.get("evidence") or {}).get("check")]
        if verdict in {"exists_exact", "exists_adaptable"} and checked:
            c = checked[0]
            return {"action": "prove", "reason": f"existing result {c.get('name')} may apply ({verdict}, adaptation: {c.get('adaptation')})",
                    "evidence": [str((c.get("evidence") or {}).get("check"))[:300]], "priority": "normal", "reuse_hint": c.get("name")}
        if verdict == "exists_exact":
            return {"action": "prove", "reason": "reuse claimed without probe/#check evidence; downgraded to prove with hint",
                    "evidence": [c.get("name") for c in cands][:5], "priority": "normal", "reuse_hint": (cands[0].get("name") if cands else None)}
    return {"action": "prove", "reason": "elaborates; no blocking findings" + ("" if reuse.get("status") == "ok" else f"; reuse review {reuse.get('status')}"),
            "evidence": [], "priority": "normal", "reuse_hint": None}


def combine(root: Path, cfg: dict, decl_id: str, *, rev: int | None, at: str | None) -> dict:
    entry = mf.get(root, cfg, decl_id)
    rev = rev if rev is not None else int((entry.get("lean") or {}).get("rev") or 1)
    rdir = _report_dir(root, cfg, decl_id, rev)
    if not (rdir / "context.json").exists():
        raise MathTcsError(f"no snapshot for {decl_id} rev {rev}; run `snapshot` first", code=1)
    ctx = read_json(rdir / "context.json")
    sha = ctx.get("statement_sha256")
    elab = read_json(rdir / "elaboration.json") if (rdir / "elaboration.json").exists() else {"status": "missing"}
    sem = _load_review(rdir, "semantic", sha)
    reuse = _load_review(rdir, "reuse", sha)
    data = mf.load(root, cfg)
    dep_ids = []
    ann_meta = ((ctx.get("annotation") or {}).get("meta") or {})
    for d in ann_meta.get("depends_on", []) or []:
        did = d.get("id") if isinstance(d, dict) else None
        if did and data["declarations"].get(did, {}).get("status") in {"blocked", "scaffold_failed"}:
            dep_ids.append(did)
    e = data["declarations"][decl_id]
    e.setdefault("annotated", {})["blocking_questions"] = [q.get("text") for q in (ann_meta.get("questions") or []) if isinstance(q, dict) and q.get("blocks_formalization")]
    decision = _decide(e, elab, sem, reuse, dep_ids)
    report = {
        "math-tcs": "verify-report/v1", "id": decl_id, "lean_rev": rev, "statement_sha256": sha, "at": at,
        "elaboration": elab, "semantic_review": sem, "reuse_review": reuse,
        "human_approval": {"kind": "human", **(e.get("human_approval") or {"status": "none"})},
        "recommended_action": decision,
        "consistency": {"same_revision": all(r.get("status") != "revision_mismatch" for r in (sem, reuse)),
                        "reviews": {"semantic": sem.get("status"), "reuse": reuse.get("status")}},
    }
    write_json_atomic(rdir / "verify.json", report)
    write_text_atomic(rdir / "verify.md", render_verify_md(report, ctx))
    e["verify"] = {"rev": rev, "report": str((rdir / "verify.json").relative_to(root)), "action": decision["action"],
                   "reviews": report["consistency"]["reviews"]}
    if decision["action"] == "repair_statement":
        e["status"] = "needs_statement_review"
    elif decision["action"] == "defer":
        e["status"] = "deferred"
    elif e.get("status") not in {"proved", "unfinished"}:
        e["status"] = "verified"
    mf.history(e, f"verify:{decision['action']}", at=at, rev=rev)
    mf.save(root, cfg, data)
    return {"id": decl_id, "rev": rev, "action": decision["action"], "reason": decision["reason"],
            "elaboration_ok": bool(elab.get("ok")), "trust": elab.get("trust"),
            "semantic": sem.get("status"), "reuse": reuse.get("status"),
            "report": e["verify"]["report"], "md": str((rdir / "verify.md").relative_to(root)), "status": e["status"]}


def render_verify_md(r: dict, ctx: dict) -> str:
    elab = r.get("elaboration") or {}
    sem = r.get("semantic_review") or {}
    reuse = r.get("reuse_review") or {}
    dec = r.get("recommended_action") or {}
    lines = [f"# Verify report — `{r['id']}` (rev {r['lean_rev']})", "",
             f"> **Provenance:** elaboration = formal check by Lean ({'ok' if elab.get('ok') else 'FAILED'}, trust `{elab.get('trust')}`); "
             f"semantic and reuse sections = model review ({sem.get('status')}, {reuse.get('status')}); "
             f"human approval = {r.get('human_approval', {}).get('status', 'none')}. A model review is not an approval and not a proof.",
             "", f"statement sha256: `{(r.get('statement_sha256') or '')[:16]}`", "",
             "```lean", (ctx.get("statement_lean") or "").rstrip(), "```", "",
             "## 1. Elaboration (formal)", "",
             f"- ok: **{elab.get('ok')}**  trust: **{elab.get('trust')}**  axioms: `{elab.get('axioms')}`  wall: {elab.get('wall_ms')} ms"]
    for d in elab.get("diagnostics", []) or []:
        lines.append(f"- {d.get('severity')} L{d.get('line')}: {str(d.get('message', '')).splitlines()[0][:200]}")
    lines += ["", "## 2. Semantic review (model)", "", f"- status: {sem.get('status')}  verdict: {sem.get('verdict')}"]
    if sem.get("reason"):
        lines.append(f"- reason: {sem['reason']}")
    for f in sem.get("fidelity_findings", []) or []:
        lines.append(f"- [{f.get('status')}/{f.get('severity')}/{f.get('confidence')}] {f.get('category')}: {f.get('message')}")
        if f.get("source_quote") or f.get("lean_quote"):
            lines.append(f"  - source: “{f.get('source_quote', '')}”  lean: `{f.get('lean_quote', '')}`")
        if f.get("suggested_repair"):
            lines.append(f"  - repair: {f['suggested_repair']}")
    for f in sem.get("degenerate_case_findings", []) or []:
        lines.append(f"- [{f.get('outcome')}] {f.get('category')} at `{f.get('instantiation')}`: {f.get('message')}")
    lines += ["", "## 3. Reuse review (model)", "", f"- status: {reuse.get('status')}  verdict: {reuse.get('verdict')}  searched: {reuse.get('searched')}"]
    if reuse.get("reason"):
        lines.append(f"- reason: {reuse['reason']}")
    for c in reuse.get("candidates", []) or []:
        ev = c.get("evidence") or {}
        lines.append(f"- `{c.get('name')}` ({c.get('owner')}) adaptation: {c.get('adaptation')}; #check: {str(ev.get('check'))[:120]}; probe: {ev.get('probe')}")
    lines += ["", "## 4. Recommended action", "", f"**{dec.get('action')}** — {dec.get('reason')} (priority {dec.get('priority')})"]
    for ev in dec.get("evidence", []) or []:
        lines.append(f"- {ev}")
    if dec.get("reuse_hint"):
        lines.append(f"- reuse hint: `{dec['reuse_hint']}`")
    lines += ["", f"consistency: same revision = {r.get('consistency', {}).get('same_revision')}", ""]
    return "\n".join(lines)


def prove_report(root: Path, cfg: dict, decl_id: str, result_path: Path, *, at: str | None) -> dict:
    result = read_json(result_path)
    if not isinstance(result, dict):
        raise MathTcsError("prove result must be a JSON object", code=1)
    data = mf.load(root, cfg)
    e = data["declarations"].get(decl_id)
    if e is None:
        raise MathTcsError(f"unknown declaration id {decl_id}", code=1)
    rev = int((e.get("lean") or {}).get("rev") or 1)
    k = int((e.get("prove") or {}).get("attempts") or 0) + 1
    rdir = root / cfg["paths"]["reports"] / decl_id
    rdir.mkdir(parents=True, exist_ok=True)
    out = rdir / f"prove-rev{rev}-{k}.json"
    report = {"math-tcs": "prove-report/v1", "id": decl_id, "lean_rev": rev, "at": at, "sequence": k,
              "statement_sha256": (e.get("lean") or {}).get("statement_sha256"), **result}
    report.setdefault("promoted", False)
    write_json_atomic(out, report)
    e["prove"] = {"attempts": k, "budget": result.get("budget"), "last_report": str(out.relative_to(root)),
                  "result": result.get("result")}
    res = result.get("result")
    if res == "statement_change_required":
        e["status"] = "needs_statement_review"
        sc = result.get("statement_change") or {}
        write_text_atomic(rdir / f"statement-change-rev{rev}.md",
                          f"# Proposed statement change — {decl_id} (rev {rev})\n\n{sc.get('reason', '')}\n\n```lean\n{sc.get('proposed_statement', '')}\n```\n")
    elif res == "unfinished":
        e["status"] = "unfinished"
    elif res in {"failed", "budget_exceeded"}:
        e["status"] = "failed"
    elif res == "proved" and not report.get("promoted"):
        pass  # promote() sets `proved`; a claimed proof is not a proof until re-checked
    e["helpers"] = result.get("helpers") or e.get("helpers") or []
    mf.history(e, f"prove:{res}", at=at, report=str(out.relative_to(root)))
    mf.save(root, cfg, data)
    return {"id": decl_id, "result": res, "report": str(out.relative_to(root)), "status": e["status"], "sequence": k}
