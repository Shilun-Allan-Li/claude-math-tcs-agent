#!/usr/bin/env python3
"""PostToolUse hook: detect orphaned step files when proof/OUTLINE.md changes.

Triggered after Write/Edit. If the modified file is proof/OUTLINE.md, scan
proof/step_*.md. Any step number with a file but not listed in the outline
is an orphan — record it in proof/.intern_inbox/orphans.json so the
orchestrator (or /intern reconcile) can act on it.

Never deletes or moves anything. Detection only.

Best-effort: any error swallowed (exit 0) so the user's workflow is never
blocked by a hook bug.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STEP_FILE = re.compile(r"^step_(\d+)\.md$")
STEP_LINE = re.compile(r"\*\*Step\s+(\d+)\*\*")


def run() -> None:
    payload = json.load(sys.stdin)
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    p = Path(file_path)
    if p.name != "OUTLINE.md" or p.parent.name != "proof":
        return
    proof_root = p.parent
    if not p.exists():
        return

    text = p.read_text()
    outline_steps = {int(m.group(1)) for m in STEP_LINE.finditer(text)}

    file_steps = []
    for f in sorted(proof_root.glob("step_*.md")):
        m = STEP_FILE.match(f.name)
        if m:
            file_steps.append((int(m.group(1)), f.name))

    orphans = [
        {"step": n, "file": f"proof/{name}", "reason": "step number not in outline"}
        for n, name in file_steps
        if n not in outline_steps
    ]

    inbox = proof_root / ".intern_inbox"
    orphans_path = inbox / "orphans.json"
    if orphans:
        inbox.mkdir(exist_ok=True)
        orphans_path.write_text(json.dumps({
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "orphans": orphans,
        }, indent=2))
    elif orphans_path.exists():
        # Outline was edited and now has no orphans — clear stale inbox
        orphans_path.unlink()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        pass
    sys.exit(0)
