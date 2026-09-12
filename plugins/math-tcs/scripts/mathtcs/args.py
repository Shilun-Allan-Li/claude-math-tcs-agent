"""Deterministic parsing of skill arguments.

Skills inject ``!`mathtcs.py args <stage> $ARGUMENTS``` so that flags such as
``--until verify`` are parsed by code, not by prose. The result is a JSON object the
coordinator (skill body or workflow) reads; ``stages`` is already computed.
"""

from __future__ import annotations

import os

STAGE_ORDER: tuple[str, ...] = ("translate", "scaffold", "verify", "prove")
STAGES: frozenset[str] = frozenset(STAGE_ORDER) | {"run", "ping"}

_VALUE_FLAGS = {"until", "slug", "chapter", "module", "budget", "parallel", "ids", "timeout"}
_BOOL_FLAGS = {"force", "json", "dry-run"}
_INT_FLAGS = {"budget", "parallel", "timeout"}


def parse(stage: str, tokens: list[str]) -> dict:
    result: dict = {
        "stage": stage,
        "target": None,
        "target_is_path": False,
        "target_abs": None,
        "flags": {"until": None, "slug": None, "chapter": None, "module": None,
                  "budget": None, "parallel": None, "ids": [], "timeout": None,
                  "force": False, "json": False, "dry_run": False},
        "stages": [],
        "errors": [],
        "raw": tokens,
    }
    if stage not in STAGES:
        result["errors"].append(f"unknown stage {stage!r}")
    positional: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            name, eq, inline = tok[2:].partition("=")
            key = name.replace("-", "_")
            if name in _BOOL_FLAGS:
                result["flags"][key] = True
                i += 1
                continue
            if name not in _VALUE_FLAGS:
                result["errors"].append(f"unknown flag --{name}")
                i += 1
                continue
            if eq:
                value = inline
            elif i + 1 < len(tokens):
                value = tokens[i + 1]
                i += 1
            else:
                result["errors"].append(f"--{name} needs a value")
                i += 1
                continue
            if name == "ids":
                result["flags"]["ids"].extend(v for v in value.split(",") if v)
            elif name in _INT_FLAGS:
                try:
                    result["flags"][key] = int(value)
                except ValueError:
                    result["errors"].append(f"--{name} must be an integer, got {value!r}")
            else:
                result["flags"][key] = value
            i += 1
        else:
            positional.append(tok)
            i += 1

    if positional:
        target = " ".join(positional)
        result["target"] = target
        expanded = os.path.expanduser(positional[0]) if len(positional) == 1 else os.path.expanduser(target)
        if os.path.exists(expanded):
            result["target_is_path"] = True
            result["target_abs"] = os.path.abspath(expanded)

    until = result["flags"]["until"]
    if until is not None and until not in STAGE_ORDER:
        result["errors"].append(f"--until must be one of {', '.join(STAGE_ORDER)}; got {until!r}")
        until = None
    if stage == "run":
        stop = STAGE_ORDER.index(until) if until else len(STAGE_ORDER) - 1
        result["stages"] = list(STAGE_ORDER[: stop + 1])
    elif stage in STAGE_ORDER:
        result["stages"] = [stage]
        if until is not None:
            result["errors"].append("--until is only meaningful for run")
    return result
