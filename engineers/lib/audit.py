#!/usr/bin/env python3
"""Engineer audit harness — bookkeeping for verb invocations.

Public functions (used by cli.py and verbs):

    begin_request(verb, args) -> {"request_id", "artifact_dir"}
    run_subprocess(request_id, timeout_s, cmd) -> {"exit_code", "duration_s", "timed_out"}
    finalize_report(request_id, report) -> dict

CLI subcommands (kept for debugging and direct shell use):

    audit.py begin <verb> '<json-args>'
    audit.py run <request_id> <timeout_s> -- <cmd> [<arg>...]
    audit.py finalize <request_id> '<json-report>'
"""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "engineering" / "artifacts"

KNOWN_VERBS = {
    "run-python",
    "run-cpp",
    "run-matlab",
    "web-search",
    "index-source",
    "count-tokens",
    "compute",
}

HEAD_TAIL_LINES = 40


def _new_request_id(verb: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{verb}-{secrets.token_hex(3)}"


def _head_tail(text: str, n: int = HEAD_TAIL_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= 2 * n:
        return text
    head = "\n".join(lines[:n])
    tail = "\n".join(lines[-n:])
    skipped = len(lines) - 2 * n
    return f"{head}\n... [{skipped} lines omitted] ...\n{tail}"


# ---------------------------------------------------------------------------
# Public API — called from cli.py and verb modules
# ---------------------------------------------------------------------------

def begin_request(verb: str, args: dict) -> dict:
    """Allocate request_id, create artifact dir, write request.json.

    Returns: {"request_id": str, "artifact_dir": str (relative to repo root)}
    Raises: ValueError if verb is unknown.
    """
    if verb not in KNOWN_VERBS:
        raise ValueError(f"unknown verb: {verb} (known: {sorted(KNOWN_VERBS)})")
    request_id = _new_request_id(verb)
    artifact_dir = ARTIFACTS / request_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "files_out").mkdir(exist_ok=True)
    request = {
        "request_id": request_id,
        "verb": verb,
        "args": args,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (artifact_dir / "request.json").write_text(json.dumps(request, indent=2))
    return {
        "request_id": request_id,
        "artifact_dir": str(artifact_dir.relative_to(ROOT)),
    }


def run_subprocess(request_id: str, timeout_s: float, cmd: list[str]) -> dict:
    """Run a subprocess inside the artifact dir with portable timeout enforcement.

    Captures stdout/stderr to stdout.txt/stderr.txt in the artifact dir.
    Returns: {"exit_code": int, "duration_s": float, "timed_out": bool}
    Conventions: 124 on timeout (matches GNU timeout), 127 on command-not-found.
    Raises: FileNotFoundError if request_id has no artifact dir.
    """
    artifact_dir = ARTIFACTS / request_id
    if not artifact_dir.is_dir():
        raise FileNotFoundError(f"no artifact dir for request_id {request_id}")

    stdout_path = artifact_dir / "stdout.txt"
    stderr_path = artifact_dir / "stderr.txt"
    started = time.monotonic()
    timed_out = False
    try:
        with open(stdout_path, "wb") as so, open(stderr_path, "wb") as se:
            proc = subprocess.run(
                cmd,
                cwd=artifact_dir,
                stdout=so,
                stderr=se,
                timeout=timeout_s,
            )
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        exit_code = 124
        timed_out = True
        with open(stderr_path, "ab") as se:
            se.write(f"\n[audit] killed after {timeout_s}s timeout\n".encode())
    except FileNotFoundError as e:
        exit_code = 127
        with open(stderr_path, "ab") as se:
            se.write(f"[audit] command not found: {e}\n".encode())
    duration_s = round(time.monotonic() - started, 4)
    return {"exit_code": exit_code, "duration_s": duration_s, "timed_out": timed_out}


def finalize_report(request_id: str, report: dict) -> dict:
    """Add stdout/stderr excerpts and files_out listing, write report.json, return."""
    artifact_dir = ARTIFACTS / request_id
    if not artifact_dir.is_dir():
        raise FileNotFoundError(f"no artifact dir for request_id {request_id}")

    report["request_id"] = request_id
    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    stdout_path = artifact_dir / "stdout.txt"
    stderr_path = artifact_dir / "stderr.txt"
    if stdout_path.exists():
        report["stdout_excerpt"] = _head_tail(stdout_path.read_text(errors="replace"))
    if stderr_path.exists():
        report["stderr_excerpt"] = _head_tail(stderr_path.read_text(errors="replace"))

    files_out_dir = artifact_dir / "files_out"
    if files_out_dir.exists():
        report["files_out"] = sorted(
            str(p.relative_to(ROOT)) for p in files_out_dir.rglob("*") if p.is_file()
        )

    (artifact_dir / "report.json").write_text(json.dumps(report, indent=2))
    return report


# ---------------------------------------------------------------------------
# CLI subcommands — thin wrappers around the public API
# ---------------------------------------------------------------------------

def cmd_begin(verb: str, args_json: str) -> int:
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as e:
        print(f"args is not valid JSON: {e}", file=sys.stderr)
        return 2
    try:
        info = begin_request(verb, args)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(info))
    return 0


def cmd_run(request_id: str, timeout_s_raw: str, cmd: list[str]) -> int:
    try:
        timeout_s = float(timeout_s_raw)
    except ValueError:
        print(f"timeout_s must be numeric, got {timeout_s_raw!r}", file=sys.stderr)
        return 2
    if not cmd:
        print("no command given (use: ... run <id> <timeout> -- <cmd> [<arg>...])", file=sys.stderr)
        return 2
    try:
        result = run_subprocess(request_id, timeout_s, cmd)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


def cmd_finalize(request_id: str, report_json: str) -> int:
    try:
        report = json.loads(report_json)
    except json.JSONDecodeError as e:
        print(f"report is not valid JSON: {e}", file=sys.stderr)
        return 2
    try:
        final = finalize_report(request_id, report)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(final, indent=2))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: audit.py begin <verb> '<json-args>'", file=sys.stderr)
        print("       audit.py run <request_id> <timeout_s> -- <cmd> [<arg>...]", file=sys.stderr)
        print("       audit.py finalize <request_id> '<json-report>'", file=sys.stderr)
        return 2
    sub = argv[1]
    if sub == "begin" and len(argv) == 4:
        return cmd_begin(argv[2], argv[3])
    if sub == "finalize" and len(argv) == 4:
        return cmd_finalize(argv[2], argv[3])
    if sub == "run" and len(argv) >= 5:
        if argv[4] != "--":
            print("expected '--' before command", file=sys.stderr)
            return 2
        return cmd_run(argv[2], argv[3], argv[5:])
    print(f"bad invocation: {' '.join(argv)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
