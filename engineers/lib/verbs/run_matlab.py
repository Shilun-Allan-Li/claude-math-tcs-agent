"""Verb: run-matlab — execute a MATLAB script via matlab -batch.

Requires `matlab` on PATH. If not installed, run_subprocess returns
exit_code 127 with a clear stderr message.
"""

from __future__ import annotations

from audit import ARTIFACTS, run_subprocess


def run(args: dict, request_id: str) -> dict:
    """args: {"script": str, "timeout_s": int}"""
    script = args.get("script")
    if not script:
        raise ValueError("missing required field: script")
    timeout_s = float(args.get("timeout_s", 60))

    artifact_dir = ARTIFACTS / request_id
    (artifact_dir / "script.m").write_text(script)

    return run_subprocess(request_id, timeout_s, ["matlab", "-batch", "script"])
