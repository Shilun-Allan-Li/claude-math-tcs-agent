"""Verb: run-cpp — compile and run a C++ source file via g++."""

from __future__ import annotations

from audit import ARTIFACTS, run_subprocess


def run(args: dict, request_id: str) -> dict:
    """args: {"source": str, "stdin": str?, "compile_flags": [str]?, "timeout_s": int}"""
    source = args.get("source")
    if not source:
        raise ValueError("missing required field: source")
    timeout_s = float(args.get("timeout_s", 30))
    flags = args.get("compile_flags") or []
    stdin_text = args.get("stdin") or ""

    artifact_dir = ARTIFACTS / request_id
    (artifact_dir / "main.cpp").write_text(source)
    if stdin_text:
        (artifact_dir / "stdin.txt").write_text(stdin_text)

    # Compile
    compile_result = run_subprocess(
        request_id, timeout_s, ["g++", *flags, "main.cpp", "-o", "prog"]
    )
    if compile_result["exit_code"] != 0:
        compile_result["phase"] = "compile"
        return compile_result

    # Run — feed stdin via shell if provided, else direct invocation.
    if stdin_text:
        cmd = ["sh", "-c", "./prog < stdin.txt"]
    else:
        cmd = ["./prog"]
    result = run_subprocess(request_id, timeout_s, cmd)
    result["phase"] = "run"
    return result
