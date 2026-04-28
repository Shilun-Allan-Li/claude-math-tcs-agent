#!/usr/bin/env python3
"""Engineer CLI — dispatch a verb to its Python implementation, return audited report.

Usage:
    python3 engineers/lib/cli.py <verb> '<json-args>'

Wraps every call with audit.begin_request / audit.finalize_report so each
invocation gets a request_id, an artifact dir, persisted stdout/stderr,
and a written report.json. Prints the compact report to stdout.

Exit codes:
    0  — verb ran (the verb's own exit_code is in the report)
    2  — bad arguments (unknown verb, malformed JSON, missing field)
    3  — verb raised an exception (e.g., tool not installed)
"""

from __future__ import annotations

import json
import sys
import traceback
from importlib import import_module
from pathlib import Path

# Make audit.py and verbs/ importable when run as a script.
LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB))

import audit  # noqa: E402

VERB_MODULES = {
    "run-python": "verbs.run_python",
    "run-cpp": "verbs.run_cpp",
    "run-matlab": "verbs.run_matlab",
    "count-tokens": "verbs.count_tokens",
    "index-source": "verbs.index_source",
    "compute": "verbs.compute",
    "web-search": "verbs.web_search",
}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <verb> '<json-args>'", file=sys.stderr)
        print(f"verbs: {', '.join(sorted(VERB_MODULES))}", file=sys.stderr)
        return 2

    verb, args_json = argv[1], argv[2]
    if verb not in VERB_MODULES:
        print(f"unknown verb: {verb} (verbs: {sorted(VERB_MODULES)})", file=sys.stderr)
        return 2

    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as e:
        print(f"args is not valid JSON: {e}", file=sys.stderr)
        return 2

    try:
        info = audit.begin_request(verb, args)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    request_id = info["request_id"]

    try:
        module = import_module(VERB_MODULES[verb])
        verb_report = module.run(args, request_id)
    except (ValueError, NotImplementedError, FileNotFoundError, RuntimeError) as e:
        verb_report = {"error": type(e).__name__, "message": str(e)}
        final = audit.finalize_report(request_id, verb_report)
        print(json.dumps(final, indent=2))
        return 3
    except Exception as e:
        verb_report = {
            "error": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }
        final = audit.finalize_report(request_id, verb_report)
        print(json.dumps(final, indent=2))
        return 3

    final = audit.finalize_report(request_id, verb_report)
    print(json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
