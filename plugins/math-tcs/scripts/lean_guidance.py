#!/usr/bin/env python3
"""Read-only, dependency-free lifecycle hook shared by Claude Code and Codex."""
import json
import os
import sys
from pathlib import Path


def response(event):
    if os.environ.get("MATH_TCS_ENABLED") == "0" or not isinstance(event, dict):
        return {}
    name = event.get("hook_event_name")
    if name not in {"SessionStart", "UserPromptSubmit"}:
        return {}
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_dir():
        return {}
    here = Path(cwd).resolve()
    root = next((p for p in (here, *here.parents) if (p / "lean-toolchain").is_file()
                 and any((p / f).is_file() for f in ("lakefile.toml", "lakefile.lean"))), None)
    if root is None:
        return {}
    guidance = (Path(__file__).resolve().parents[1] / "guidance.md").read_text(encoding="utf-8")
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": guidance}}


if __name__ == "__main__":
    try:
        print(json.dumps(response(json.load(sys.stdin))))
    except (ValueError, OSError, TypeError):
        print("{}")  # A guidance failure must not block a user's session.
