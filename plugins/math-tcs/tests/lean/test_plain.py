"""Real Lean checks in disposable projects; no tcslib sources or config are touched."""
import shutil

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
