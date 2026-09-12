"""Context packages: what each agent gets to read, selected by code with char budgets.

No graph machinery -- selection is by declared relations in the annotation
(``definitions_used``, ``depends_on``), the sibling blocks in the same module, the verify
report's reuse hint, and a bounded grep of the target library for the declaration's key
terms. Packages are written to ``math-tcs/context/<stage>/<id>.json`` and agents are given
the path.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import annotated_md
from . import blocks as bl
from . import manifest as mf
from .util import read_json, write_json_atomic

__all__ = ["build"]

BUDGET = {"scaffold": 24000, "verify": 16000, "prove": 30000}
_DECL_LINE_RE = re.compile(r"^\s*(?:@\[[^\]]*\]\s*)?(?:(?:private|protected|noncomputable)\s+)*(theorem|lemma|def|abbrev|structure|class|instance)\s+([A-Za-z_][A-Za-z0-9_.'!?]*)")


def _grep_project(root: Path, cfg: dict, terms: list[str], *, limit: int = 40) -> list[dict]:
    """Declarations in the target lib whose names mention one of ``terms`` (bounded)."""
    lib_dir = root / (cfg["lean"].get("src_dir") or ".") / (cfg["lean"].get("module_prefix") or "").split(".")[0]
    if not lib_dir.is_dir():
        lib_dir = root / (cfg["lean"].get("src_dir") or ".")
    words = sorted({t.lower() for t in terms if len(t) >= 4})[:8]
    if not words:
        return []
    pattern = "|".join(re.escape(w) for w in words)
    try:
        proc = subprocess.run(["grep", "-rniE", "--include=*.lean", f"^(theorem|lemma|def|abbrev|structure)\\s+[A-Za-z0-9_.']*({pattern})", str(lib_dir)],
                              capture_output=True, text=True, timeout=30)
    except Exception:
        return []
    out = []
    for line in proc.stdout.splitlines()[:limit]:
        path, _, rest = line.partition(":")
        lineno, _, code = rest.partition(":")
        out.append({"file": str(Path(path).relative_to(root)) if path.startswith(str(root)) else path,
                    "line": int(lineno) if lineno.isdigit() else None, "text": code.strip()[:200]})
    return out


def _module_blocks(root: Path, path: str | None) -> tuple[str | None, list[dict], list[str]]:
    if not path or not (root / path).exists():
        return None, [], []
    text = (root / path).read_text(encoding="utf-8")
    sibs = []
    for b in bl.parse_blocks(text):
        m = bl.main_declaration(b.inner)
        if not m:
            continue
        try:
            sig, _ = bl.split_statement(m["text"])
        except ValueError:
            sig = m["text"]
        sibs.append({"id": b.id, "name": m["name"], "kw": m["kw"], "signature": sig, "text": m["text"]})
    return bl.namespace_of(text), sibs, bl.module_imports(text)


def _trim(obj, budget: int):
    """Drop the largest optional lists until the JSON fits the budget (coarse)."""
    import json
    s = json.dumps(obj, ensure_ascii=False)
    for key in ("project_matches", "siblings", "definitions"):
        while len(s) > budget and isinstance(obj.get(key), list) and obj[key]:
            obj[key].pop()
            s = json.dumps(obj, ensure_ascii=False)
    return obj


def build(root: Path, cfg: dict, stage: str, decl_id: str, *, annotated_path: str | None = None) -> dict:
    entry = mf.get(root, cfg, decl_id)
    ann_path = annotated_path or (entry.get("annotated") or {}).get("path")
    section = None
    if ann_path and (root / ann_path).exists():
        section = annotated_md.section_for((root / ann_path).read_text(encoding="utf-8"), decl_id)
    meta = (section or {}).get("meta") or {}
    lean = entry.get("lean") or {}
    namespace, sibs, imports = _module_blocks(root, lean.get("path"))
    terms = []
    for d in meta.get("definitions_used", []) or []:
        if isinstance(d, dict) and d.get("term"):
            terms.append(str(d["term"]))
    for c in meta.get("mathlib_candidates", []) or []:
        if isinstance(c, dict) and c.get("name"):
            terms.append(str(c["name"]).split(".")[-1])
    if meta.get("name"):
        terms.extend(str(meta["name"]).split())
    pkg: dict = {
        "math-tcs": f"context/{stage}/v1", "id": decl_id, "stage": stage,
        "kind": entry.get("kind"), "label": entry.get("label"), "status": entry.get("status"),
        "source": entry.get("source"),
        "annotation": None if section is None else {"meta": meta, "source_statement": section.get("source_statement"),
                                                    "source_proof": section.get("source_proof"),
                                                    "interpretation": section.get("interpretation")},
        "module": {"path": lean.get("path"), "name": lean.get("module"), "namespace": namespace or cfg["lean"].get("namespace"),
                   "imports": imports, "prefix": cfg["lean"].get("module_prefix"), "lib": cfg["lean"].get("lib")},
        "lean_name": lean.get("name"), "rev": lean.get("rev"),
        "siblings": [{k: v for k, v in s.items() if k != "text"} for s in sibs if s["id"] != decl_id],
        "definitions": [],
        "project_matches": _grep_project(root, cfg, terms),
        "axiom_allowlist": cfg.get("axioms", {}).get("allow"),
    }
    dep_ids = {d.get("id") for d in (meta.get("definitions_used", []) or []) + (meta.get("depends_on", []) or []) if isinstance(d, dict) and d.get("id")}
    for s in sibs:
        if s["id"] in dep_ids:
            pkg["definitions"].append({"id": s["id"], "name": s["name"], "text": s["text"]})
    if stage == "prove":
        v = entry.get("verify") or {}
        if v.get("report") and (root / v["report"]).exists():
            rep = read_json(root / v["report"])
            pkg["verify"] = {"action": (rep.get("recommended_action") or {}).get("action"),
                             "reuse_hint": (rep.get("recommended_action") or {}).get("reuse_hint"),
                             "reuse_candidates": [{"name": c.get("name"), "adaptation": c.get("adaptation"), "evidence": c.get("evidence")}
                                                  for c in ((rep.get("reuse_review") or {}).get("candidates") or [])][:5],
                             "semantic_notes": [f.get("message") for f in ((rep.get("semantic_review") or {}).get("fidelity_findings") or []) if f.get("status") != "pass"][:5]}
        me = next((s for s in sibs if s["id"] == decl_id), None)
        pkg["statement_lean"] = me["text"] if me else None
        pkg["prove"] = {"budget": cfg.get("prove", {}).get("budget"), "max_helpers": cfg.get("prove", {}).get("max_helpers")}
    pkg = _trim(pkg, BUDGET.get(stage, 20000))
    out = root / cfg["paths"]["context"] / stage / f"{decl_id}.json"
    write_json_atomic(out, pkg)
    import json as _json
    return {"id": decl_id, "stage": stage, "path": str(out.relative_to(root)), "chars": len(_json.dumps(pkg, ensure_ascii=False)),
            "siblings": len(pkg["siblings"]), "definitions": len(pkg["definitions"]), "project_matches": len(pkg["project_matches"])}
