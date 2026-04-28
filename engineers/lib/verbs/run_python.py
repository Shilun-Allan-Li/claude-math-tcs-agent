"""Verb: run-python — execute a Python script in the artifact sandbox."""

from __future__ import annotations

import shutil
from pathlib import Path

from audit import ARTIFACTS, run_subprocess


def run(args: dict, request_id: str) -> dict:
    """args: {"code": str, "files_in": [path,...]?, "timeout_s": int}"""
    code = args.get("code")
    if not code:
        raise ValueError("missing required field: code")
    timeout_s = float(args.get("timeout_s", 30))

    artifact_dir = ARTIFACTS / request_id
    (artifact_dir / "script.py").write_text(code)

    for src in args.get("files_in") or []:
        src_path = Path(src)
        if not src_path.is_absolute():
            src_path = (artifact_dir.parent.parent.parent / src).resolve()
        if src_path.is_file():
            shutil.copy2(src_path, artifact_dir / src_path.name)

    return run_subprocess(request_id, timeout_s, ["python3", "script.py"])
