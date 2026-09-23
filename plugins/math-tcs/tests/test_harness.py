import json
import subprocess
from pathlib import Path

import pytest

from mathtcs import harness as h, plain
from mathtcs.util import MathTcsError


@pytest.fixture
def project_root(tmp_path):
    root = tmp_path / "Lean project"
    root.mkdir()
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.25.0\n")
    (root / "lakefile.toml").write_text('name = "harness_test"\nversion = "0.1.0"\n')
    (root / "lake-manifest.json").write_text('{"version":"1.1.0","packages":[],"name":"harness_test","lakeDir":".lake","packagesDir":".lake/packages"}')
    (root / "Source.md").write_text("Every natural number equals itself.")
    return root


def started(root, budget=4):
    return h.begin(root, root / "Main.lean", root / "Source.md", "Demo.self_eq", start=0, end=0, budget=budget)


def proposed(root, task):
    return h.propose(root, task, "namespace Demo\ntheorem self_eq (n : Nat) : n = n := " + h.SLOT + "\nend Demo\n")


def accepted(root, task):
    state = h.status(root, task)
    return h.review(root, task, {"snapshot": state["snapshot"], "verdict": "faithful", "findings": [], "reason": "Same universally quantified equality."})


@pytest.fixture
def fake_check(monkeypatch):
    calls = []
    def run(root, text, names, timeout):
        calls.append(text)
        return {"ok": "sorry" not in text, "source_sha256": h.sha256_text(text), "declarations": {names[0]: {"axioms": []}}}
    monkeypatch.setattr(h, "check_text", run)
    return calls


def test_complete_loop_and_scoped_application(project_root, fake_check):
    task = started(project_root)["id"]
    proposed(project_root, task)
    accepted(project_root, task)
    assert h.attempt(project_root, task, "rfl")["status"] == "checked"
    assert not (project_root / "Main.lean").exists()
    state = h.apply(project_root, task)
    assert state["status"] == "applied"
    assert len(fake_check) == 2
    assert "rfl" in (project_root / "Main.lean").read_text()
    assert not (project_root / "math-tcs/tasks/active.json").exists()


@pytest.mark.parametrize("review", [{}, {"verdict": "faithful"}, {"snapshot": None}, []])
def test_missing_reviews_fail_closed(project_root, review):
    task = started(project_root)["id"]
    proposed(project_root, task)
    with pytest.raises(MathTcsError):
        h.review(project_root, task, review)
    with pytest.raises(MathTcsError, match="faithful"):
        h.attempt(project_root, task, "rfl")


def test_uncertainty_repairs_and_old_review(project_root):
    task = started(project_root)["id"]
    state = proposed(project_root, task)
    old = {"snapshot": state["snapshot"], "verdict": "uncertain", "findings": ["missing domain"], "reason": "Domain is ambiguous."}
    assert h.review(project_root, task, old)["status"] == "needs_statement_review"
    proposed(project_root, task)
    with pytest.raises(MathTcsError):
        h.review(project_root, task, {**old, "verdict": "faithful", "findings": []})
    proposed(project_root, task)
    with pytest.raises(MathTcsError, match="repair rounds"):
        proposed(project_root, task)


def test_budget_is_counted_before_checks(project_root, fake_check):
    task = started(project_root, budget=1)["id"]
    proposed(project_root, task)
    accepted(project_root, task)
    assert h.attempt(project_root, task, "sorry")["status"] == "unfinished"
    with pytest.raises(MathTcsError, match="budget exhausted"):
        h.attempt(project_root, task, "rfl")
    assert len(fake_check) == 1


def test_interrupted_check_consumes_attempt(project_root, monkeypatch):
    task = started(project_root, budget=1)["id"]
    proposed(project_root, task)
    accepted(project_root, task)
    def crash(*args):
        raise RuntimeError("checker crashed")
    monkeypatch.setattr(h, "check_text", crash)
    with pytest.raises(RuntimeError):
        h.attempt(project_root, task, "rfl")
    assert len(h.status(project_root, task)["attempts"]) == 1


@pytest.mark.parametrize("change", ["target", "definition", "dependency"])
def test_edits_during_acceptance_are_preserved(project_root, monkeypatch, change):
    task = started(project_root)["id"]
    proposed(project_root, task)
    accepted(project_root, task)
    monkeypatch.setattr(h, "check_text", lambda *args: {"ok": True})
    h.attempt(project_root, task, "rfl")
    def check(*args):
        path = {"target": "Main.lean", "definition": "Defs.lean", "dependency": "lake-manifest.json"}[change]
        (project_root / path).write_text("user edit")
        return {"ok": True}
    monkeypatch.setattr(h, "check_text", check)
    with pytest.raises(MathTcsError, match="changed"):
        h.apply(project_root, task)
    if change == "target":
        assert (project_root / "Main.lean").read_text() == "user edit"
    else:
        assert not (project_root / "Main.lean").exists()


def test_exclusive_task_and_owner_checked_abort(project_root):
    task = started(project_root)["id"]
    with pytest.raises(MathTcsError, match="active task"):
        started(project_root)
    with pytest.raises((MathTcsError, FileNotFoundError)):
        h.abort(project_root, "0" * 32)
    assert h.abort(project_root, task)["status"] == "aborted"
    assert started(project_root)["id"] != task


def test_process_mutex(project_root):
    with h.transaction(project_root):
        with pytest.raises(MathTcsError, match="command is active"):
            started(project_root)


@pytest.mark.parametrize("bad", [")\ntheorem hacked : True := by trivial\n(", "rfl /-", "rfl -/", "exact (", 'exact "oops', "`(True)", "let c := '('\n)"])
def test_proof_boundary(bad):
    with pytest.raises(MathTcsError):
        h.proof_term(bad)


def test_simplification_preserves_everything_outside_proof(project_root, fake_check):
    target = project_root / "Main.lean"
    text = "theorem t : True := by\n  exact True.intro\n\n-- keep me\n"
    target.write_text(text)
    start, end = text.index("by"), text.index("\n\n")
    state = h.begin(project_root, target, project_root / "Source.md", "t", start=start, end=end, mode="simplify")
    task = state["id"]
    with pytest.raises(MathTcsError):
        h.propose(project_root, task, "True := " + h.SLOT)
    h.propose(project_root, task, h.SLOT)
    accepted(project_root, task)
    h.attempt(project_root, task, "trivial")
    h.apply(project_root, task)
    assert target.read_text() == text[:start] + h.proof_term("trivial") + text[end:]


def test_plain_requires_probe_at_expected_line(project_root, monkeypatch):
    monkeypatch.setattr(plain, "run_lean", lambda *a, **k: {
        "exit": 0, "timeout": False, "wall_ms": 0, "noise": [], "diagnostics": [
            {"severity": "information", "line": 1, "message": "'t' does not depend on any axioms"}]})
    assert not plain.check_text(project_root, "theorem t : True := by trivial", ["t"])["ok"]


def test_legacy_workflow_success_reaches_proof_gate(plugin_root):
    script = r'''
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const rec = {declarations:{}};
eval(src.match(/^const mark = .*$/m)[0].replace('const mark =', 'globalThis.mark ='));
const id='t', cj={status:'verified', action:'prove', elaboration_ok:true};
eval(src.split('\n').find(l => l.includes("mark(id, 'verify', 'ok',")));
const v=rec.declarations[id].verify;
if (v.status !== 'ok' || v.action !== 'prove' || !v.elaboration_ok) process.exit(1);
'''
    subprocess.run(["node", "-e", script, str(plugin_root / "workflows/run.js")], check=True)


def test_legacy_empty_review_refused(tmp_path):
    from mathtcs.report import _load_review
    (tmp_path / "semantic.json").write_text("{}")
    assert _load_review(tmp_path, "semantic", "hash")["status"] != "ok"


def test_failed_independent_check_does_not_apply(project_root, fake_check, monkeypatch):
    task = started(project_root)["id"]
    proposed(project_root, task)
    accepted(project_root, task)
    h.attempt(project_root, task, "rfl")
    monkeypatch.setattr(h, "check_text", lambda *args: {"ok": False})
    with pytest.raises(MathTcsError, match="acceptance check failed"):
        h.apply(project_root, task)
    assert not (project_root / "Main.lean").exists()


def test_package_definition_changes_invalidate(project_root):
    dep = project_root / ".lake/packages/example"
    dep.mkdir(parents=True)
    file = dep / "Defs.lean"
    file.write_text("def n : Nat := 0")
    task = started(project_root)["id"]
    file.write_text("def n : Nat := 1")
    with pytest.raises(MathTcsError, match="context changed"):
        proposed(project_root, task)


def test_cli_roundtrip(project_root, plugin_root):
    import sys
    cli = [sys.executable, str(plugin_root / "scripts/mathtcs.py"), "task"]
    r = subprocess.run([*cli, "begin", "--root", str(project_root), "--file", str(project_root / "Main.lean"),
                        "--source", str(project_root / "Source.md"), "--decl", "t", "--start", "0", "--end", "0"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    task = json.loads(r.stdout)["id"]
    r = subprocess.run([*cli, "abort", task, "--root", str(project_root)], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["status"] == "aborted"


@pytest.mark.parametrize("after_write", [False, True])
def test_recover_interrupted_application(project_root, fake_check, monkeypatch, after_write):
    task = started(project_root)["id"]
    proposed(project_root, task)
    accepted(project_root, task)
    h.attempt(project_root, task, "rfl")
    write = h.write_text_atomic
    def crash(path, text):
        if after_write:
            write(path, text)
        raise RuntimeError("process interrupted")
    monkeypatch.setattr(h, "write_text_atomic", crash)
    with pytest.raises(RuntimeError):
        h.apply(project_root, task)
    state = h.status(project_root, task)
    assert state["status"] == ("applied" if after_write else "checked")
    assert (project_root / "math-tcs/tasks/active.json").exists() != after_write
