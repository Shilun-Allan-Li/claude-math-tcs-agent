"""Lean-backed tests: run against a target project with Mathlib built (``lean`` marker).

They write only under ``<target>/math-tcs-test/`` and ``<target>/math-tcs/scratch/`` and remove
the module they create. Each Lean run costs ~15–40 s.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mathtcs import blocks, project
from mathtcs.lean_check import check_module

pytestmark = pytest.mark.lean

FIXTURE = """import Mathlib.Data.Nat.Basic

namespace MathTcsTest

-- math-tcs:begin id=t-ch1-def-1.1-1 rev=1
/-- divides -/
def Divides (a b : ℕ) : Prop :=
  ∃ q : ℕ, b = a * q
-- math-tcs:end id=t-ch1-def-1.1-1

-- math-tcs:begin id=t-ch1-thm-1.1 rev=1
/-- 1.1 -/
theorem divides_trans (a b c : ℕ) (hab : Divides a b) (hbc : Divides b c) : Divides a c := by
  unfold Divides at hab hbc ⊢
  obtain ⟨q, rfl⟩ := hab
  obtain ⟨r, rfl⟩ := hbc
  exact ⟨q * r, Nat.mul_assoc a q r⟩
-- math-tcs:end id=t-ch1-thm-1.1

-- math-tcs:begin id=t-ch1-thm-1.2 rev=1
/-- 1.2 -/
theorem divides_add (a b c : ℕ) (hab : Divides a b) (hac : Divides a c) : Divides a (b + c) := by
  sorry
-- math-tcs:end id=t-ch1-thm-1.2

-- math-tcs:begin id=t-ch1-thm-1.3 rev=1
/-- 1.3: no textual sorry, but depends on divides_add -/
theorem divides_add_add (a b c : ℕ) (hab : Divides a b) (hac : Divides a c) : Divides a (b + b + c) :=
  divides_add a (b + b) c (divides_add a b b hab hab) hac
-- math-tcs:end id=t-ch1-thm-1.3

end MathTcsTest
"""


@pytest.fixture
def cfg(lean_project):
    if not (lean_project / "math-tcs" / "config.json").exists():
        det = project.detect(lean_project)
        lib = det["libs"][0]
        project.init(lean_project, lib=lib["name"], module_prefix=(lib["module_prefix_guess"] or lib["name"]) + ".MathTcs",
                     src_dir=lib["src_dir"], namespace="MathTcs")
    return project.load_config(lean_project)


@pytest.fixture
def module_file(lean_project):
    d = lean_project / "math-tcs-test"
    d.mkdir(exist_ok=True)
    f = d / "Fixture.lean"
    f.write_text(FIXTURE)
    yield f
    shutil.rmtree(d, ignore_errors=True)


def test_check_trust_vocabulary_on_fixture(lean_project, cfg, module_file):
    res = check_module(lean_project, cfg, module_file, tag="test/fixture", axioms=True,
                       kinds={"t-ch1-def-1.1-1": "definition"})
    assert res["ok"], res["unattributed_errors"] or res["summary"]
    trust = {k: v["trust"] for k, v in res["blocks"].items()}
    assert trust == {"t-ch1-def-1.1-1": "FULLY_VERIFIED", "t-ch1-thm-1.1": "FULLY_VERIFIED",
                     "t-ch1-thm-1.2": "DIRECT_SORRY", "t-ch1-thm-1.3": "TRANSITIVE_SORRY"}
    assert res["declarations"]["MathTcsTest.divides_add_add"]["axioms"] == ["sorryAx"]
    assert set(res["declarations"]["MathTcsTest.divides_trans"]["axioms"]) <= {"propext", "Classical.choice", "Quot.sound"}


def test_check_substitute_and_compile_error(lean_project, cfg, module_file):
    res = check_module(lean_project, cfg, module_file, tag="test/subst", axioms=True,
                       substitute={"id": "t-ch1-thm-1.2", "proof": "obtain ⟨q, rfl⟩ := hab\nobtain ⟨r, rfl⟩ := hac\nexact ⟨q + r, (Nat.mul_add a q r).symm⟩"})
    assert res["ok"] and res["blocks"]["t-ch1-thm-1.2"]["trust"] == "FULLY_VERIFIED"
    assert res["blocks"]["t-ch1-thm-1.3"]["trust"] == "FULLY_VERIFIED"  # the transitive dependency is now proved
    bad = check_module(lean_project, cfg, module_file, tag="test/bad", axioms=True,
                       substitute={"id": "t-ch1-thm-1.2", "proof": "exact nonsense_name hab"})
    assert not bad["ok"] and bad["blocks"]["t-ch1-thm-1.2"]["errors"] >= 1
    assert bad["blocks"]["t-ch1-thm-1.2"]["trust"] == "COMPILE_FAILURE"


def test_probe_check_names(lean_project, cfg):
    from mathtcs.probe import check_names
    res = check_names(lean_project, cfg, ["Nat.mul_assoc", "Nat.dvd_antisymm", "totally_bogus_name_xyz"], imports=["Mathlib.Data.Nat.Basic"])
    r = res["results"]
    assert r["Nat.mul_assoc"]["exists"] and "*" in r["Nat.mul_assoc"]["type"]
    assert r["Nat.dvd_antisymm"]["exists"] and "∣" in r["Nat.dvd_antisymm"]["type"]
    assert not r["totally_bogus_name_xyz"]["exists"] and "Unknown identifier" in r["totally_bogus_name_xyz"]["message"]
