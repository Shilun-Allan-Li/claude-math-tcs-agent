"""``math-tcs/manifest.json``: declaration ids → artifact paths, revisions, status, locks.

The manifest is the only registry of what the plugin wrote. Writes are atomic. Human
edits are detected by comparing the recorded ``block_sha256`` with the block on disk;
a mismatch flags ``human_edited`` and invalidates verify/prove results rather than
overwriting anything.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import blocks as bl
from .util import MathTcsError, read_json, sha256_text, write_json_atomic

__all__ = ["MANIFEST_VERSION", "STATUSES", "load", "save", "get", "entries", "ensure",
           "set_status", "set_field", "history", "lock", "unlock", "lock_state", "stale", "approve"]

MANIFEST_VERSION = "manifest/v1"
STATUSES = ("translated", "scaffolded", "blocked", "scaffold_failed", "verified",
            "needs_statement_review", "proved", "unfinished", "failed", "deferred")


def _path(root: Path, cfg: dict) -> Path:
    return root / cfg["paths"]["dir"] / "manifest.json"


def load(root: Path, cfg: dict) -> dict:
    p = _path(root, cfg)
    if not p.exists():
        return {"math-tcs": MANIFEST_VERSION, "declarations": {}}
    return read_json(p)


def save(root: Path, cfg: dict, data: dict) -> None:
    write_json_atomic(_path(root, cfg), data)


def get(root: Path, cfg: dict, decl_id: str) -> dict:
    data = load(root, cfg)
    if decl_id not in data["declarations"]:
        raise MathTcsError(f"unknown declaration id {decl_id}", code=1)
    return data["declarations"][decl_id]


def entries(root: Path, cfg: dict, *, status: str | None = None, slug: str | None = None,
            module: str | None = None, ids: list[str] | None = None) -> list[dict]:
    data = load(root, cfg)
    out = []
    for decl_id, e in data["declarations"].items():
        if ids and decl_id not in ids:
            continue
        if status and e.get("status") != status:
            continue
        if slug and e.get("slug") != slug:
            continue
        if module and (e.get("lean") or {}).get("module") != module:
            continue
        out.append({"id": decl_id, **e})
    return out


def _blank(decl_id: str, item: dict, *, slug: str, chapter: str) -> dict:
    return {
        "kind": item.get("kind"), "label": item.get("label"), "slug": slug, "chapter": chapter,
        "source": {}, "annotated": {}, "lean": {"representation": None, "path": None, "module": None,
                                                "name": None, "rev": 0, "statement_sha256": None,
                                                "block_sha256": None, "existing_name": None, "owner": None},
        "status": "translated", "trust": {"status": "UNKNOWN", "axioms": None, "checked_rev": None},
        "verify": {"rev": None, "report": None, "action": None},
        "prove": {"attempts": 0, "budget": None, "last_report": None},
        "helpers": [], "blockers": [], "human_edited": False,
        "human_approval": {"status": "none", "by": None, "rev": None, "at": None},
        "lock": None, "history": [],
    }


def ensure(data: dict, decl_id: str, item: dict, *, slug: str, chapter: str) -> dict:
    e = data["declarations"].get(decl_id)
    if e is None:
        e = _blank(decl_id, item, slug=slug, chapter=chapter)
        data["declarations"][decl_id] = e
    return e


def history(entry: dict, event: str, *, at: str | None, **extra) -> None:
    entry.setdefault("history", []).append({"at": at, "event": event, **extra})


def set_status(root: Path, cfg: dict, decl_id: str, status: str, *, note: str | None = None, at: str | None = None) -> dict:
    if status not in STATUSES:
        raise MathTcsError(f"unknown status {status!r}; expected one of {STATUSES}", code=1)
    data = load(root, cfg)
    e = data["declarations"].get(decl_id)
    if e is None:
        raise MathTcsError(f"unknown declaration id {decl_id}", code=1)
    e["status"] = status
    history(e, f"status:{status}", at=at, note=note)
    save(root, cfg, data)
    return e


def set_field(root: Path, cfg: dict, decl_id: str, dotted: str, value) -> dict:
    data = load(root, cfg)
    e = data["declarations"].get(decl_id)
    if e is None:
        raise MathTcsError(f"unknown declaration id {decl_id}", code=1)
    parts = dotted.split(".")
    cur = e
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    save(root, cfg, data)
    return e


# ------------------------------------------------------------------------------ locks

def _lock_path(root: Path, cfg: dict, decl_id: str) -> Path:
    return root / cfg["paths"]["locks"] / f"{decl_id}.json"


def lock_state(root: Path, cfg: dict, decl_id: str, *, now: float | None = None) -> dict | None:
    p = _lock_path(root, cfg, decl_id)
    if not p.exists():
        return None
    st = read_json(p)
    now = now if now is not None else time.time()
    expired = (st.get("epoch", 0) + 60 * st.get("ttl_min", 60)) < now
    return {**st, "expired": expired}


def lock(root: Path, cfg: dict, decl_id: str, *, stage: str, ttl_min: int = 60, at: str | None = None,
         owner: str | None = None) -> dict:
    p = _lock_path(root, cfg, decl_id)
    st = lock_state(root, cfg, decl_id)
    if st and not st["expired"]:
        raise MathTcsError(f"{decl_id} is locked by {st.get('stage')} since {st.get('at')} (owner {st.get('owner')})",
                           code=1, detail={"lock": st})
    data = {"id": decl_id, "stage": stage, "at": at, "epoch": time.time(), "ttl_min": ttl_min,
            "owner": owner or f"pid:{os.getpid()}"}
    write_json_atomic(p, data)
    m = load(root, cfg)
    if decl_id in m["declarations"]:
        m["declarations"][decl_id]["lock"] = {"stage": stage, "at": at, "owner": data["owner"]}
        save(root, cfg, m)
    return {"locked": True, **data}


def unlock(root: Path, cfg: dict, decl_id: str, *, stale_min: int | None = None) -> dict:
    p = _lock_path(root, cfg, decl_id)
    existed = p.exists()
    if existed:
        if stale_min is not None:
            st = lock_state(root, cfg, decl_id)
            if st and (time.time() - st.get("epoch", 0)) < 60 * stale_min:
                return {"unlocked": False, "reason": "lock is not stale", "lock": st}
        p.unlink()
    m = load(root, cfg)
    if decl_id in m["declarations"] and m["declarations"][decl_id].get("lock"):
        m["declarations"][decl_id]["lock"] = None
        save(root, cfg, m)
    return {"unlocked": True, "existed": existed}


# --------------------------------------------------------------------------- staleness

def _annotated_section_sha(root: Path, path: str | None, decl_id: str) -> str | None:
    if not path:
        return None
    p = root / path
    if not p.exists():
        return None
    from . import annotated_md
    try:
        doc = annotated_md.parse(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    for d in doc["declarations"]:
        if d["id"] == decl_id:
            return d["section_sha256"]
    return None


def stale(root: Path, cfg: dict, decl_id: str) -> dict:
    """Which of this declaration's recorded results are out of date, and why."""
    e = get(root, cfg, decl_id)
    reasons: list[str] = []
    src = e.get("source") or {}
    if src.get("path"):
        sp = Path(src["path"])
        if not sp.is_absolute():
            sp = root / sp
        if not sp.exists():
            reasons.append("source_missing")
        elif src.get("sha256") and sha256_text(sp.read_text(encoding="utf-8")) != src["sha256"]:
            reasons.append("source_changed")
    ann = e.get("annotated") or {}
    if ann.get("path"):
        cur = _annotated_section_sha(root, ann["path"], decl_id)
        if cur is None:
            reasons.append("annotation_missing")
        elif ann.get("section_sha256") and cur != ann["section_sha256"]:
            reasons.append("annotation_changed")
    lean = e.get("lean") or {}
    human_edited = e.get("human_edited", False)
    statement_changed = False
    if lean.get("path"):
        lp = root / lean["path"]
        if not lp.exists():
            reasons.append("lean_missing")
        else:
            b = bl.block_by_id(lp.read_text(encoding="utf-8"), decl_id)
            if b is None:
                reasons.append("block_missing")
            else:
                if lean.get("block_sha256") and b.sha != lean["block_sha256"]:
                    reasons.append("block_changed")
                    human_edited = True
                main = bl.main_declaration(b.inner)
                if main and lean.get("statement_sha256"):
                    try:
                        if bl.statement_sha(main["text"]) != lean["statement_sha256"]:
                            reasons.append("statement_changed")
                            statement_changed = True
                    except ValueError:
                        reasons.append("statement_unparseable")
    v = e.get("verify") or {}
    if v.get("rev") is not None and lean.get("rev") is not None and v["rev"] < lean["rev"]:
        reasons.append("verify_outdated")
    if statement_changed and v.get("rev") is not None:
        reasons.append("verify_stale")
    if statement_changed and e.get("status") == "proved":
        reasons.append("proof_stale")
    return {"id": decl_id, "stale": bool(reasons), "reasons": reasons, "human_edited": human_edited,
            "status": e.get("status")}


def touch(root: Path, cfg: dict, decl_id: str, *, at: str | None = None) -> dict:
    """Apply human-edit detection: bump rev, refresh shas, invalidate verify/prove."""
    st = stale(root, cfg, decl_id)
    data = load(root, cfg)
    e = data["declarations"][decl_id]
    lean = e.get("lean") or {}
    changed = False
    if "block_changed" in st["reasons"] and lean.get("path"):
        lp = root / lean["path"]
        b = bl.block_by_id(lp.read_text(encoding="utf-8"), decl_id)
        if b is not None:
            e["human_edited"] = True
            main = bl.main_declaration(b.inner)
            if "statement_changed" in st["reasons"]:
                lean["rev"] = int(lean.get("rev") or 0) + 1
                if main:
                    try:
                        lean["statement_sha256"] = bl.statement_sha(main["text"])
                    except ValueError:
                        pass
                e["verify"] = {"rev": None, "report": e.get("verify", {}).get("report"), "action": None}
                if e.get("status") in {"verified", "proved", "unfinished", "needs_statement_review"}:
                    e["status"] = "scaffolded"
            lean["block_sha256"] = b.sha
            history(e, "human_edit_detected", at=at, reasons=st["reasons"])
            changed = True
    if changed:
        save(root, cfg, data)
    return {"id": decl_id, "applied": changed, **st}


def approve(root: Path, cfg: dict, decl_id: str, *, by: str, at: str | None, rev: int | None = None) -> dict:
    data = load(root, cfg)
    e = data["declarations"].get(decl_id)
    if e is None:
        raise MathTcsError(f"unknown declaration id {decl_id}", code=1)
    e["human_approval"] = {"status": "approved", "by": by, "rev": rev if rev is not None else (e.get("lean") or {}).get("rev"), "at": at}
    history(e, "human_approved", at=at, by=by)
    save(root, cfg, data)
    return e
