"""One-task-at-a-time, fail-closed formalization transactions (macOS/Linux).

This controls accepted changes, not arbitrary shell access by a host agent. Workers
return proposals to the coordinator; they do not need write tools or check tools.
"""
from __future__ import annotations

import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from .plain import check_text, declaration_name
from .util import MathTcsError, read_json, sha256_file, sha256_text, write_json_atomic, write_text_atomic

SLOT = "__MATH_TCS_PROOF__"


def _dir(root: Path) -> Path:
    return root / "math-tcs" / "tasks"


@contextmanager
def transaction(root: Path):
    directory = _dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "mutex").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MathTcsError("another harness command is active")
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _task_path(root: Path, task: str) -> Path:
    if not re_task(task):
        raise MathTcsError("invalid task id")
    return _dir(root) / task / "task.json"


def re_task(task: str) -> bool:
    return len(task) == 32 and all(c in "0123456789abcdef" for c in task)


def _save(root: Path, state: dict) -> dict:
    write_json_atomic(_task_path(root, state["id"]), state)
    return state


def _active(root: Path, task: str) -> dict:
    state = read_json(_task_path(root, task))
    owner = read_json(_dir(root) / "active.json")
    if owner.get("id") != task or state["status"] in {"applied", "aborted"}:
        raise MathTcsError("task does not own the project writer slot")
    return state


def _context(root: Path) -> dict:
    """Conservative fingerprint including local and installed package Lean sources.

    No persistent success cache. Build artifacts are excluded; source/config changes
    anywhere in the project invalidate a task, including definition-body changes.
    """
    files, visited = {}, set()
    for directory, dirs, names in os.walk(root, followlinks=True):
        real = Path(directory).resolve()
        if real in visited:
            dirs[:] = []
            continue
        visited.add(real)
        dirs[:] = sorted(d for d in dirs if d not in {".git", "math-tcs", "node_modules", "__pycache__"}
                         and not (d == "build" and Path(directory).name == ".lake"))
        for name in sorted(names):
            path = Path(directory) / name
            if name.endswith(".lean") or name in {"lean-toolchain", "lakefile.toml", "lake-manifest.json"}:
                files[str(path.relative_to(root))] = sha256_file(path)
    return files


def _fresh(root: Path, state: dict):
    if _context(root) != state["context"]:
        raise MathTcsError("project context changed; abort and start a fresh task")
    path = root / state["target"]
    actual = path.read_text(encoding="utf-8") if path.exists() else None
    if actual != state["original"]:
        raise MathTcsError("target changed; abort and start a fresh task")


def begin(root: Path, target: Path, source: Path, name: str, *, start: int, end: int,
          mode: str = "formalize", budget: int = 4) -> dict:
    if not (root / "lake-manifest.json").is_file():
        raise MathTcsError("initialize the project's Lake environment before starting (lake-manifest.json is missing)")
    target = target.resolve()
    if not target.is_relative_to(root) or target.suffix != ".lean" or "math-tcs" in target.relative_to(root).parts:
        raise MathTcsError("target must be a .lean file inside the project, outside math-tcs/")
    if mode not in {"formalize", "simplify"} or not 1 <= budget <= 20:
        raise MathTcsError("invalid mode or budget (1–20)")
    original = target.read_text(encoding="utf-8") if target.exists() else None
    text = original or ""
    if not 0 <= start <= end <= len(text):
        raise MathTcsError("start/end are zero-based Unicode character offsets in the target")
    source_text = source.read_text(encoding="utf-8")
    if not source_text.strip():
        raise MathTcsError("source must contain the informal statement or the simplification request")
    with transaction(root):
        active = _dir(root) / "active.json"
        if active.exists():
            raise MathTcsError(f"project already has an active task: {read_json(active)['id']}; inspect or abort it")
        task = uuid.uuid4().hex
        state = {"schema": "task/v1", "id": task, "mode": mode, "status": "draft",
                 "target": str(target.relative_to(root)), "original": original,
                 "source": source_text, "source_sha256": sha256_text(source_text),
                 "declaration": declaration_name(name), "start": start, "end": end,
                 "context": _context(root), "budget": budget, "attempts": [], "round": -1,
                 "reviews": [], "proposals": [], "review": None, "snapshot": None}
        _save(root, state)
        write_json_atomic(active, {"id": task})
        return state


def propose(root: Path, task: str, replacement: str) -> dict:
    with transaction(root):
        state = _active(root, task)
        _fresh(root, state)
        if state["round"] >= 2:
            raise MathTcsError("two statement-repair rounds exhausted")
        if replacement.count(SLOT) != 1:
            raise MathTcsError(f"replacement must contain exactly one {SLOT} proof slot")
        if state["mode"] == "simplify" and replacement.strip() != SLOT:
            raise MathTcsError("simplify may replace only the selected proof term")
        text = state["original"] or ""
        template = text[:state["start"]] + replacement + text[state["end"]:]
        if template.count(SLOT) != 1:
            raise MathTcsError("proof slot must be unique in the complete file")
        state["round"] += 1
        # Per-proposal nonce prevents an old review from authorizing an identical resubmission.
        snapshot = sha256_text(json.dumps([task, state["round"], template, state["source"], state["context"]], sort_keys=True))
        state.update(template=template, snapshot=snapshot, review=None, status="awaiting_review")
        state["proposals"].append({"round": state["round"], "snapshot": snapshot, "template": template})
        return _save(root, state)


def review(root: Path, task: str, result: dict) -> dict:
    with transaction(root):
        state = _active(root, task)
        _fresh(root, state)
        if state["status"] != "awaiting_review":
            raise MathTcsError("task is not awaiting review")
        if (not isinstance(result, dict) or result.get("snapshot") != state["snapshot"]
                or result.get("verdict") not in {"faithful", "divergent", "uncertain"}
                or not isinstance(result.get("findings"), list)
                or not all(isinstance(f, str) for f in result["findings"])
                or not isinstance(result.get("reason"), str) or not result["reason"].strip()):
            raise MathTcsError("review requires exact snapshot, verdict, string findings, and a nonempty reason")
        # A faithful verdict with unresolved findings is contradictory: require a fresh review.
        accepted = result["verdict"] == "faithful" and not result["findings"]
        state["reviews"].append(result)
        state.update(review=result, status="ready" if accepted else "needs_statement_review")
        return _save(root, state)


def proof_term(tactics: str) -> str:
    """Contain ordinary tactic proofs in a balanced term. Helpers use local have/let.

    Unsupported lexical constructs fail closed rather than attempting Lean parsing.
    This is an edit-boundary guard, not a sandbox against executable Lean metaprograms.
    """
    if not tactics.strip():
        raise MathTcsError("empty tactics")
    stack, i = [], 0
    pairs = {"(": ")", "[": "]", "{": "}", "⟨": "⟩", "⦃": "⦄"}
    while i < len(tactics):
        if tactics.startswith("--", i):
            newline = tactics.find("\n", i)
            i = len(tactics) if newline == -1 else newline + 1
            continue
        if tactics.startswith("/-", i):
            depth = 1
            i += 2
            while i < len(tactics) and depth:
                if tactics.startswith("/-", i):
                    depth += 1; i += 2
                elif tactics.startswith("-/", i):
                    depth -= 1; i += 2
                else:
                    i += 1
            if depth:
                raise MathTcsError("unterminated proof comment")
            continue
        if tactics.startswith("-/", i):
            raise MathTcsError("unmatched proof comment terminator")
        c = tactics[i]
        if c in {'"', '«'}:
            closing = '"' if c == '"' else '»'
            i += 1
            while i < len(tactics) and tactics[i] != closing:
                i += 2 if tactics[i] == "\\" and closing == '"' else 1
            if i >= len(tactics):
                raise MathTcsError("unterminated string/identifier")
        elif c == '`':
            raise MathTcsError("syntax quotations are unsupported in proof slots")
        elif c == "'" and (i == 0 or not (tactics[i - 1].isalnum() or tactics[i - 1] in "_'")):
            raise MathTcsError("character literals are unsupported in proof slots")
        elif c in pairs:
            stack.append(pairs[c])
        elif c in pairs.values():
            if not stack or stack.pop() != c:
                raise MathTcsError("proof escapes its term boundary")
        i += 1
    if stack:
        raise MathTcsError("unbalanced proof delimiters")
    return "(by\n" + "\n".join("  " + line for line in tactics.splitlines()) + "\n)"


def attempt(root: Path, task: str, tactics: str, timeout: float = 120) -> dict:
    with transaction(root):
        state = _active(root, task)
        _fresh(root, state)
        if state["status"] not in {"ready", "unfinished", "checked"}:
            raise MathTcsError("a faithful review is required before proof attempts")
        if len(state["attempts"]) >= state["budget"]:
            raise MathTcsError("proof-check budget exhausted; report unfinished or abort")
        candidate = state["template"].replace(SLOT, proof_term(tactics))
        entry = {"n": len(state["attempts"]) + 1, "snapshot": state["snapshot"],
                 "candidate": candidate, "status": "running"}
        state["attempts"].append(entry)
        state["status"] = "unfinished"
        _save(root, state)  # interrupted checks still consume an attempt
        result = check_text(root, candidate, [state["declaration"]], timeout)
        entry.update(status="finished", check=result)
        state["status"] = "checked" if result["ok"] else "unfinished"
        _save(root, state)
        _fresh(root, state)
        return state


def apply(root: Path, task: str, timeout: float = 120) -> dict:
    with transaction(root):
        state = _active(root, task)
        _fresh(root, state)
        if state["status"] != "checked":
            raise MathTcsError("no checked candidate to apply")
        entry = state["attempts"][-1]
        if entry["snapshot"] != state["snapshot"]:
            raise MathTcsError("candidate belongs to an obsolete statement")
        # Independent final check is outside the worker's attempt budget.
        result = check_text(root, entry["candidate"], [state["declaration"]], timeout)
        state["acceptance_check"] = result
        _save(root, state)
        if not result["ok"]:
            state["status"] = "unfinished"
            _save(root, state)
            raise MathTcsError("independent acceptance check failed")
        _fresh(root, state)
        target = root / state["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        # Cooperative writers are serialized. External editors cannot honor this lock;
        # the last-moment freshness check minimizes, but cannot eliminate, that race.
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        state["status"] = "applying"
        _save(root, state)
        write_text_atomic(target, entry["candidate"])
        target.chmod(mode)
        state["status"] = "applied"
        _save(root, state)
        (_dir(root) / "active.json").unlink()
        return state


def abort(root: Path, task: str) -> dict:
    with transaction(root):
        state = _active(root, task)
        state["status"] = "aborted"
        _save(root, state)
        (_dir(root) / "active.json").unlink()
        return state


def status(root: Path, task: str) -> dict:
    with transaction(root):
        state = read_json(_task_path(root, task))
        if state["status"] == "applying":
            target = root / state["target"]
            actual = target.read_text(encoding="utf-8") if target.exists() else None
            candidate = state["attempts"][-1]["candidate"]
            if actual == candidate:
                state["status"] = "applied"
                _save(root, state)
            elif actual == state["original"]:
                state["status"] = "checked"
                _save(root, state)
            else:
                return {**state, "recovery": "target changed during interrupted application; inspect and abort"}
        if state["status"] in {"applied", "aborted"}:
            active = _dir(root) / "active.json"
            if active.exists() and read_json(active).get("id") == task:
                active.unlink()
        return state
