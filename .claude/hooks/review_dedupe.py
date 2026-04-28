#!/usr/bin/env python3
"""PostToolUse hook: dedupe accumulated review files per step.

Triggered after Write to proof/review_*.md. If multiple review files exist
for the same step (e.g., timestamped variants like review_step03_20260427.md),
keep the most recent and move older ones to proof/archive/reviews/.
Never deletes.

Best-effort: any error swallowed (exit 0) so the user's workflow is never
blocked by a hook bug.
"""

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REVIEW_FILE = re.compile(r"^review_step(\d+)(.*)\.md$")


def run() -> None:
    payload = json.load(sys.stdin)
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    p = Path(file_path)
    if not p.name.startswith("review_step") or p.parent.name != "proof":
        return
    proof_root = p.parent

    by_step: dict[int, list[Path]] = {}
    for f in proof_root.glob("review_step*.md"):
        m = REVIEW_FILE.match(f.name)
        if not m:
            continue
        n = int(m.group(1))
        by_step.setdefault(n, []).append(f)

    archive = proof_root / "archive" / "reviews"
    for files in by_step.values():
        if len(files) <= 1:
            continue
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        for old in files[1:]:
            archive.mkdir(parents=True, exist_ok=True)
            ts = datetime.fromtimestamp(
                old.stat().st_mtime, tz=timezone.utc
            ).strftime("%Y%m%dT%H%M%SZ")
            dest = archive / f"{old.stem}_{ts}.md"
            shutil.move(str(old), str(dest))


if __name__ == "__main__":
    try:
        run()
    except Exception:
        pass
    sys.exit(0)
