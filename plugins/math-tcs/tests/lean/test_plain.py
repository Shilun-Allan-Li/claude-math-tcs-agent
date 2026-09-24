"""Real Lean checks in disposable projects; no tcslib sources or config are touched."""
import shutil
import json
import subprocess
import sys

import pytest

from mathtcs import harness as h, plain

pytestmark = pytest.mark.lean


@pytest.fixture
def core_project(tmp_path):
    if not shutil.which("lake"):
        pytest.skip("lake is required")
    root = tmp_path / "Lean project"
    root.mkdir()
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.25.0\n")
    (root / "lakefile.toml").write_text('name = "plain_test"\nversion = "0.1.0"\n')
    (root / "lake-manifest.json").write_text('{"version":"1.1.0","packages":[],"name":"plain_test","lakeDir":".lake","packagesDir":".lake/packages"}')
    return root


def test_plain_axioms_and_namespaces(core_project):
    text = '''namespace Demo
section
variable (n : Nat)
local notation "NN" => Nat
theorem good : n = n := by rfl
theorem pending : True := by sorry
theorem transitive : True := pending
axiom extra : False
theorem nonstandard : False := extra
end
end Demo
'''
    r = plain.check_text(core_project, text, ["Demo.good", "Demo.pending", "Demo.transitive", "Demo.nonstandard"])
    assert r["compiled"], r
    assert r["declarations"]["Demo.good"]["verified"]
    assert r["declarations"]["Demo.pending"]["axioms"] == ["sorryAx"]
    assert r["declarations"]["Demo.transitive"]["axioms"] == ["sorryAx"]
    assert not r["declarations"]["Demo.nonstandard"]["verified"]
    assert plain.check_text(core_project, text, ["Demo.good"])["ok"]


def test_plain_failure_and_missing_name(core_project):
    assert not plain.check_text(core_project, "theorem x : False := by trivial", ["x"])["ok"]
    assert not plain.check_text(core_project, "theorem x : True := by trivial", ["missing"])["ok"]
    assert plain.check_text(core_project, "theorem x : True := by trivial", ["x"], timeout=0.0001)["timeout"]


def test_real_task_through_independent_acceptance(core_project):
    source = core_project / "Source.md"
    source.write_text("Every natural number equals itself.")
    state = h.begin(core_project, core_project / "Main.lean", source, "self_eq", start=0, end=0)
    task = state["id"]
    state = h.propose(core_project, task, "theorem self_eq (n : Nat) : n = n := " + h.SLOT + "\n")
    h.review(core_project, task, {"snapshot": state["snapshot"], "verdict": "faithful", "findings": [], "reason": "Same statement."})
    assert h.attempt(core_project, task, "rfl")["status"] == "checked"
    assert h.apply(core_project, task)["status"] == "applied"
    assert plain.check_file(core_project, core_project / "Main.lean", ["self_eq"])["ok"]


@pytest.mark.parametrize("initial", ["by sorry", "by\n  have h : 0 + n = n := Nat.zero_add n\n  exact h"])
def test_real_existing_file_reuse_and_simplification(core_project, initial):
    source = core_project / "Source.md"
    source.write_text("Simplify the proof of zero plus n equals n, preserving its statement.")
    target = core_project / "Main.lean"
    prefix = "namespace Demo\ntheorem zero_add (n : Nat) : 0 + n = n := "
    suffix = "\nend Demo\n-- unrelated material stays\n"
    target.write_text(prefix + initial + suffix)
    state = h.begin(core_project, target, source, "Demo.zero_add", start=len(prefix), end=len(prefix + initial), mode="simplify")
    task = state["id"]
    state = h.propose(core_project, task, h.SLOT)
    h.review(core_project, task, {"snapshot": state["snapshot"], "verdict": "faithful", "findings": [], "reason": "Only the proof term changes."})
    assert h.attempt(core_project, task, "exact Nat.zero_add n")["status"] == "checked"
    assert h.apply(core_project, task)["status"] == "applied"
    assert target.read_text() == prefix + h.proof_term("exact Nat.zero_add n") + suffix


@pytest.mark.parametrize("mode", ["formalize", "simplify"])
def test_public_cli_complete_current_pipeline(core_project, plugin_root, mode):
    """Real CLI + Lean; reviews/tactics are fixtures, not live model judgments."""
    root = core_project
    target = root / "Main.lean"
    prefix = "theorem self_eq (n : Nat) : n = n := "
    original_proof = "by sorry" if mode == "formalize" else "by\n  have h : n = n := rfl\n  exact h"
    suffix = "\n-- preserve unrelated material\n"
    original = prefix + original_proof + suffix
    target.write_text(original)
    source = root / "Source.md"
    source.write_text("Every natural number equals itself. Preserve the statement.")

    def run(*args, code=0):
        result = subprocess.run([sys.executable, str(plugin_root / "scripts/mathtcs.py"),
                                 *args, "--root", str(root)], cwd=root, text=True,
                                capture_output=True, timeout=60)
        assert result.returncode == code, result.stdout + result.stderr
        return json.loads(result.stdout)

    state = run("task", "begin", "--file", str(target), "--source", str(source),
                "--decl", "self_eq", "--start", str(len(prefix)),
                "--end", str(len(prefix + original_proof)), "--mode", mode)
    task = state["id"]
    proposal = root / "proposal.txt"
    proposal.write_text(h.SLOT)
    state = run("task", "propose", task, "--input", str(proposal))
    review = root / "review.json"
    review.write_text(json.dumps({"snapshot": state["snapshot"], "verdict": "faithful",
                                 "findings": [], "reason": "Fixture: only the proof changes."}))
    assert run("task", "review", task, "--input", str(review))["status"] == "ready"
    tactics = root / "tactics.txt"
    tactics.write_text("sorry")
    assert run("task", "attempt", task, "--input", str(tactics), code=1)["status"] == "unfinished"
    assert target.read_text() == original
    tactics.write_text("rfl")
    assert run("task", "attempt", task, "--input", str(tactics))["status"] == "checked"
    assert target.read_text() == original
    assert run("task", "apply", task)["status"] == "applied"
    assert target.read_text() == prefix + h.proof_term("rfl") + suffix
    checked = run("check-file", str(target), "--decl", "self_eq")
    assert checked["schema"] == "plain-check/v1"
    assert checked["ok"] and checked["declarations"]["self_eq"]["verified"]
    assert run("task", "status", task)["status"] == "applied"
    report = root / "math-tcs/tasks" / task / "task.json"
    assert report.is_file()
    for retired in ("manifest.json", "config.json", "annotated", "reports", "runs", "workflows"):
        assert not (root / "math-tcs" / retired).exists()
