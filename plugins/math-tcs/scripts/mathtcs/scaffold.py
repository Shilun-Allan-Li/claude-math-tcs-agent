"""``scaffold apply``: proposals JSON → blocks merged into the module → elaboration → manifest.

Rules enforced here (not in prompts):
* theorem-like bodies must be exactly ``sorry`` (a tactic body is rejected as
  ``scaffold_failed: proof body``); object kinds must have a real body;
* blocks that are proved, human-edited or human-approved are never rewritten without
  ``--force`` (the proposal is saved to ``reports/<id>/proposed-rev<N>.lean`` instead);
* an elaboration error inside a statement is a *blocker* (status ``blocked``), never a
  stub;
* the canonical module is written once, atomically, after all blocks are merged.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import annotated_md
from . import blocks as bl
from . import manifest as mf
from .lean_check import check_module
from .util import MathTcsError, read_json, write_text_atomic

__all__ = ["module_path", "module_name", "default_module_short", "apply", "extract"]

_OBJECT_KWS = {"def", "abbrev", "structure", "inductive", "class", "instance", "opaque"}


def default_module_short(title: str) -> str:
    words = re.sub(r"[^A-Za-z0-9]+", " ", title).split()
    words = [w for w in words if not re.fullmatch(r"(unit|chapter|section|lecture|part)\b", w, re.I)]
    name = "".join(w[:1].upper() + w[1:] for w in words if w)
    name = re.sub(r"^\d+", "", name) or "Module"
    return name[:40]


def module_name(cfg: dict, short: str) -> str:
    prefix = cfg["lean"].get("module_prefix") or ""
    return f"{prefix}.{short}" if prefix else short


def module_path(root: Path, cfg: dict, short: str) -> Path:
    prefix = cfg["lean"].get("module_prefix") or ""
    src = root / (cfg["lean"].get("src_dir") or ".")
    parts = prefix.split(".") if prefix else []
    return src.joinpath(*parts, f"{short}.lean")


def _source_ref(entry: dict) -> str:
    src = entry.get("source") or {}
    bits = [src.get("path") or "?"]
    if src.get("section"):
        bits.append(f"§{src['section']}")
    if src.get("lines"):
        a, b = src["lines"]
        bits.append(f"lines {a}–{b}")
    if src.get("page"):
        bits.append(f"p. {src['page']}")
    return " ".join(bits)


def _register_root_import(root: Path, cfg: dict, mod_name: str) -> dict:
    lean = cfg["lean"]
    if not lean.get("register_in_root") or not lean.get("root_file"):
        return {"registered": False, "reason": "register_in_root disabled or no root_file",
                "line": f"import {mod_name}"}
    rf = root / (lean.get("src_dir") or ".") / lean["root_file"]
    if not rf.exists():
        return {"registered": False, "reason": f"{rf} missing", "line": f"import {mod_name}"}
    text = rf.read_text(encoding="utf-8")
    line = f"import {mod_name}"
    if re.search(rf"^{re.escape(line)}\s*$", text, re.M):
        return {"registered": True, "changed": False, "file": str(rf)}
    write_text_atomic(rf, text.rstrip("\n") + "\n" + line + "\n")
    return {"registered": True, "changed": True, "file": str(rf)}


def apply(root: Path, cfg: dict, proposals_path: Path, *, module_short: str | None, force: bool = False,
          at: str | None = None, timeout: float | None = None, check: bool = True) -> dict:
    payload = read_json(proposals_path)
    proposals = payload.get("proposals") if isinstance(payload, dict) else payload
    if not isinstance(proposals, list):
        raise MathTcsError("proposals JSON must be {\"proposals\": [...]} or a list", code=1)
    data = mf.load(root, cfg)
    short = module_short or (payload.get("module") if isinstance(payload, dict) else None)
    if not short:
        raise MathTcsError("a module name is required (--module or proposals.module)", code=1)
    mod_name = module_name(cfg, short)
    mpath = module_path(root, cfg, short)
    namespace = cfg["lean"].get("namespace") or short
    if mpath.exists():
        text = mpath.read_text(encoding="utf-8")
        if bl.namespace_of(text) is None:
            raise MathTcsError(f"{mpath} exists but has no namespace; refusing to merge", code=1)
    else:
        title = (payload.get("title") if isinstance(payload, dict) else None) or short
        source_ref = (payload.get("source") if isinstance(payload, dict) else None) or "source"
        text = bl.render_module(module_name=mod_name, namespace=namespace, title=title, source_ref=source_ref,
                                imports=[], blocks=[])
    written: list[dict] = []
    skipped: list[dict] = []
    blocked: list[dict] = []
    failed: list[dict] = []
    all_imports: list[str] = []
    kinds: dict[str, str] = {}
    for p in proposals:
        pid = p.get("id")
        if not pid:
            failed.append({"id": None, "reason": "proposal without id"}); continue
        entry = data["declarations"].get(pid)
        if entry is None:
            failed.append({"id": pid, "reason": "not in manifest (run translate/register first)"}); continue
        kinds[pid] = entry.get("kind") or "theorem"
        lean = entry.setdefault("lean", {})
        rep = p.get("representation") or "new"
        blockers = list(p.get("blockers") or [])
        if rep == "existing":
            lean.update({"representation": "existing", "existing_name": p.get("existing_name"),
                         "owner": p.get("owner"), "path": None, "module": None, "name": p.get("existing_name")})
            entry["blockers"] = []
            entry["status"] = "scaffolded"
            mf.history(entry, "scaffold:existing", at=at, existing_name=p.get("existing_name"))
            skipped.append({"id": pid, "reason": "existing representation", "existing_name": p.get("existing_name")})
            continue
        if blockers:
            entry["blockers"] = [b if isinstance(b, str) else str(b.get("missing") or b) for b in blockers]
            entry["status"] = "blocked"
            mf.history(entry, "scaffold:blocked", at=at, blockers=entry["blockers"])
            blocked.append({"id": pid, "blockers": entry["blockers"]})
            continue
        statement = (p.get("statement") or "").strip()
        if not statement:
            failed.append({"id": pid, "reason": "empty statement"}); entry["status"] = "scaffold_failed"; continue
        clean = bl.strip_doc_comment(statement)
        decls = bl.declarations_in(clean)
        if not decls:
            failed.append({"id": pid, "reason": "no declaration found in statement"}); entry["status"] = "scaffold_failed"; continue
        main = decls[-1]
        kw = main["kw"]
        is_object_kind = kinds[pid] in {"definition", "construction", "notation"}
        cls = bl.classify_body(main["text"], kw)
        if kw in _OBJECT_KWS:
            body_norm = re.sub(r"\s+", " ", main["text"].split(":=", 1)[1]).strip() if ":=" in main["text"] else ""
            if body_norm in {"sorry", "by sorry"}:
                entry["blockers"] = ["definition body is `sorry` (an opaque object makes every statement about it vacuous)"]
                entry["status"] = "blocked"
                blocked.append({"id": pid, "blockers": entry["blockers"]})
                mf.history(entry, "scaffold:blocked", at=at, blockers=entry["blockers"])
                continue
        else:
            if cls == "proof":
                entry["status"] = "scaffold_failed"
                failed.append({"id": pid, "reason": "proof body instead of `sorry` (formalization is not proving)"})
                mf.history(entry, "scaffold:rejected_proof_body", at=at)
                continue
            if cls == "no_body":
                entry["status"] = "scaffold_failed"
                failed.append({"id": pid, "reason": "declaration has no `:=` body"})
                continue
            if cls == "structural":
                p.setdefault("deviations", []).append("body is a term over sibling declarations (structural, not a proof); trust is decided by `#print axioms`")
        protect = entry.get("status") == "proved" or entry.get("human_edited") or \
            (entry.get("human_approval") or {}).get("status") == "approved"
        existing_block = bl.block_by_id(text, pid)
        rev = int(lean.get("rev") or 0)
        new_rev = rev + 1 if (existing_block is not None) else max(rev, 1)
        spec = {
            "id": pid, "kind": kinds[pid], "label": entry.get("label"), "name": p.get("lean_name"),
            "source_ref": _source_ref(entry),
            "source_statement": (entry.get("source") or {}).get("statement") or "",
            "source_proof": (entry.get("source") or {}).get("proof"),
            "difficulty": p.get("difficulty") or {},
            "deviations": p.get("deviations") or [],
            "blockers": [],
            "extra": p.get("doc_extra"),
        }
        helpers = p.get("helpers") or []
        block_text = bl.render_block(spec, clean, rev=new_rev, helpers=helpers)
        new_text, outcome = bl.upsert_block(text, block_text, decl_id=pid, expect_sha=lean.get("block_sha256"),
                                            force=force, protect=protect)
        if outcome in {"refused_human_edit", "refused_protected"}:
            prop_path = root / cfg["paths"]["reports"] / pid / f"proposed-rev{new_rev}.lean"
            write_text_atomic(prop_path, block_text + "\n")
            skipped.append({"id": pid, "reason": outcome, "proposal_saved": str(prop_path.relative_to(root))})
            mf.history(entry, f"scaffold:{outcome}", at=at, proposal=str(prop_path.relative_to(root)))
            continue
        if outcome == "unchanged":
            skipped.append({"id": pid, "reason": "unchanged"})
            continue
        text = new_text
        all_imports.extend(p.get("imports") or [])
        short_name = main["name"] or ""
        lean.update({"representation": "new", "path": str(mpath.relative_to(root)), "module": mod_name,
                     "name": f"{namespace}.{short_name}" if short_name else None, "rev": new_rev,
                     "existing_name": None, "owner": "project"})
        entry["blockers"] = []
        entry["status"] = "scaffolded"
        entry["human_edited"] = False
        mf.history(entry, f"scaffold:{outcome}", at=at, rev=new_rev)
        written.append({"id": pid, "outcome": outcome, "rev": new_rev, "lean_name": lean["name"],
                        "difficulty": p.get("difficulty"), "opens": p.get("opens") or []})
    text = bl.merge_imports(text, sorted(set(all_imports)))
    # refresh shas from the merged text
    for w in written:
        b = bl.block_by_id(text, w["id"])
        entry = data["declarations"][w["id"]]
        main = bl.main_declaration(b.inner) if b else None
        entry["lean"]["block_sha256"] = b.sha if b else None
        try:
            entry["lean"]["statement_sha256"] = bl.statement_sha(main["text"]) if main else None
        except ValueError:
            entry["lean"]["statement_sha256"] = None
    if written or not mpath.exists():
        write_text_atomic(mpath, text)
    elaboration = None
    if check and (written or mpath.exists()):
        elaboration = check_module(root, cfg, mpath, tag=f"scaffold/{short}", axioms=True, timeout=timeout, kinds=kinds)
        for w in written:
            entry = data["declarations"][w["id"]]
            binfo = elaboration["blocks"].get(w["id"], {})
            errs = [d for d in binfo.get("diagnostics", []) if d["severity"] == "error"]
            if errs:
                entry["blockers"] = [f"L{d.get('line')}: {d['message'].splitlines()[0][:200]}" for d in errs]
                entry["status"] = "blocked"
                mf.history(entry, "scaffold:elaboration_error", at=at, errors=len(errs))
                blocked.append({"id": w["id"], "blockers": entry["blockers"], "from": "elaboration"})
            else:
                entry["trust"] = {"status": binfo.get("trust", "UNKNOWN"),
                                  "axioms": (elaboration["declarations"].get(binfo.get("main") or "", {}) or {}).get("axioms"),
                                  "checked_rev": entry["lean"]["rev"]}
        if elaboration["unattributed_errors"]:
            for w in written:
                e = data["declarations"][w["id"]]
                if e["status"] == "scaffolded":
                    e["blockers"] = [f"module-level error: {d['message'].splitlines()[0][:200]}" for d in elaboration["unattributed_errors"]]
    mf.save(root, cfg, data)
    root_reg = _register_root_import(root, cfg, mod_name) if written else {"registered": False, "reason": "nothing written"}
    blocked_ids = {b["id"] for b in blocked}
    return {
        "module": mod_name, "path": str(mpath.relative_to(root)), "namespace": namespace,
        "written": [w for w in written if w["id"] not in blocked_ids],
        "blocked": blocked, "skipped": skipped, "failed": failed,
        "root_import": root_reg,
        "elaboration": None if elaboration is None else {
            "ok": elaboration["ok"], "errors": elaboration["summary"]["errors"], "wall_ms": elaboration["wall_ms"],
            "scratch": elaboration["scratch"], "timeout": elaboration["timeout"],
            "unattributed_errors": [d["message"][:300] for d in elaboration["unattributed_errors"]],
            "blocks": {k: {"trust": v.get("trust"), "errors": v.get("errors")} for k, v in elaboration["blocks"].items()},
        },
    }


def extract(root: Path, cfg: dict, decl_id: str) -> dict:
    entry = mf.get(root, cfg, decl_id)
    lean = entry.get("lean") or {}
    if not lean.get("path"):
        raise MathTcsError(f"{decl_id} has no Lean block", code=1)
    text = (root / lean["path"]).read_text(encoding="utf-8")
    b = bl.block_by_id(text, decl_id)
    if b is None:
        raise MathTcsError(f"block {decl_id} not found in {lean['path']}", code=1)
    main = bl.main_declaration(b.inner)
    return {"id": decl_id, "path": lean["path"], "module": lean.get("module"), "rev": b.rev, "block": b.inner,
            "block_sha256": b.sha, "main": main["text"] if main else None,
            "statement_sha256": bl.statement_sha(main["text"]) if main else None,
            "recorded_block_sha256": lean.get("block_sha256"), "recorded_statement_sha256": lean.get("statement_sha256")}
