#!/usr/bin/env python3
"""PostToolUse hook: keep proof/OUTLINE.md ticks in sync with proof/step_*.md.

Triggered after Write/Edit. If the modified file is proof/step_NN.md, walk
the proof/ dir and re-tick OUTLINE.md so [x]/[ ] reflects which step files
exist on disk. No LLM, pure state sync.

Best-effort: any error swallowed (exit 0) so the user's workflow is never
blocked by a hook bug.
"""

import json
import re
import sys
from pathlib import Path

STEP_FILE = re.compile(r"^step_(\d+)\.md$")
STEP_LINE = re.compile(r"^(\s*-\s*\[)([ x])(\]\s*\*\*Step\s+(\d+))", re.MULTILINE)


def run() -> None:
    payload = json.load(sys.stdin)
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        return
    p = Path(file_path)
    if not STEP_FILE.match(p.name):
        return
    if p.parent.name != "proof":
        return

    proof_root = p.parent
    outline = proof_root / "OUTLINE.md"
    if not outline.exists():
        return

    step_files = {
        int(m.group(1))
        for f in proof_root.glob("step_*.md")
        if (m := STEP_FILE.match(f.name))
    }

    text = outline.read_text()

    def repl(match: re.Match) -> str:
        n = int(match.group(4))
        new_mark = "x" if n in step_files else " "
        return f"{match.group(1)}{new_mark}{match.group(3)}"

    new_text = STEP_LINE.sub(repl, text)
    if new_text != text:
        outline.write_text(new_text)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        pass
    sys.exit(0)
