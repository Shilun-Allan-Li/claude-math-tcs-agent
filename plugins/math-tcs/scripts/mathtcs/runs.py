"""Run records (``math-tcs/runs/<started_at>.json``) and workflow staging.

Every declaration × planned stage gets an explicit status (``ok | failed | missing |
skipped``) with a reason; nothing is dropped silently. ``workflow stage`` copies the
plugin's ``run.js`` into the target project so the Workflow tool (which only accepts a
``scriptPath`` under the session's working directory) can load it.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import manifest as mf
from .util import MathTcsError, read_json, write_json_atomic

__all__ = ["record", "stage_workflow", "STATUS_VALUES"]

STATUS_VALUES = ("ok", "failed", "missing", "skipped")


def record(root: Path, cfg: dict, payload_path: Path, *, started_at: str, run_id: str | None = None) -> dict:
    payload = read_json(payload_path)
    if not isinstance(payload, dict):
        raise MathTcsError("run payload must be a JSON object", code=1)
    planned = list(payload.get("stages_planned") or [])
    decls = payload.get("declarations") or {}
    data = mf.load(root, cfg)
    normalised: dict[str, dict] = {}
    ids = set(decls) | {d for d in payload.get("ids", []) or []}
    for decl_id in sorted(ids):
        per = decls.get(decl_id) or {}
        entry: dict = {}
        for stage in planned:
            st = per.get(stage)
            if st is None:
                entry[stage] = {"status": "missing", "reason": "no result recorded for this stage"}
            elif isinstance(st, dict):
                status = st.get("status")
                if status not in STATUS_VALUES:
                    st = {**st, "status": "failed", "reason": f"invalid status {status!r}: " + str(st.get("reason", ""))}
                entry[stage] = st
            else:
                entry[stage] = {"status": "failed", "reason": f"malformed stage result: {st!r}"}
        m = data["declarations"].get(decl_id) or {}
        entry["manifest_status"] = m.get("status")
        entry["trust"] = (m.get("trust") or {}).get("status")
        normalised[decl_id] = entry
    counts: dict[str, dict[str, int]] = {}
    for stage in planned:
        counts[stage] = {s: 0 for s in STATUS_VALUES}
        for e in normalised.values():
            counts[stage][e[stage]["status"]] += 1
    rec = {
        "math-tcs": "run-record/v1", "started_at": started_at, "run_id": run_id,
        "args": payload.get("args"), "stages_planned": planned, "stages_run": payload.get("stages_run") or [],
        "declarations": normalised, "agents": payload.get("agents") or [], "counts": counts,
        "notes": payload.get("notes") or [], "summary": payload.get("summary"),
    }
    safe = re.sub(r"[^0-9A-Za-z_.-]", "-", started_at)
    out = root / cfg["paths"]["runs"] / f"{safe}.json"
    write_json_atomic(out, rec)
    return {"path": str(out.relative_to(root)), "counts": counts, "declarations": len(normalised)}


def stage_workflow(root: Path, cfg: dict, plugin_root: Path, *, name: str = "run.js") -> dict:
    src = plugin_root / "workflows" / name
    if not src.exists():
        raise MathTcsError(f"workflow script {src} not found", code=2)
    dst_dir = root / cfg["paths"]["dir"] / "workflows"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / name
    shutil.copyfile(src, dst)
    version = None
    pj = plugin_root / ".claude-plugin" / "plugin.json"
    if pj.exists():
        try:
            version = read_json(pj).get("version")
        except Exception:
            version = None
    return {"scriptPath": str(dst), "relative": str(dst.relative_to(root)), "plugin_version": version, "bytes": dst.stat().st_size}
