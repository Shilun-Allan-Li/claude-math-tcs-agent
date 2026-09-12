"""Scripts-only end-to-end run of the demo through the CLI in a *temporary* target project
that borrows the real project's Lean environment (``lean`` marker).

A throwaway project directory is created with symlinks to the target's ``.lake``,
``lean-toolchain``, lakefile and ``lake-manifest.json``, so nothing in the real project
is touched. Every CLI stage is exercised without any model: register the expected
annotation, apply the expected proposals, snapshot, combine with fixture reviews,
promote a real proof, reject a transitive-sorry proof, and confirm rerun protection.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.lean


@pytest.fixture
def temp_target(lean_project, tmp_path):
    root = tmp_path / "target"
    root.mkdir()
    for name in (".lake", "lean-toolchain", "lake-manifest.json"):
        if (lean_project / name).exists():
            os.symlink(lean_project / name, root / name)
    for lf in ("lakefile.toml", "lakefile.lean"):
        if (lean_project / lf).exists():
            os.symlink(lean_project / lf, root / lf)
    return root


def mt(plugin_root: Path, root: Path, *argv: str) -> tuple[int, dict]:
    r = subprocess.run([sys.executable, str(plugin_root / "scripts" / "mathtcs.py"), *argv, "--root", str(root)],
                       capture_output=True, text=True, cwd=str(root))
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"non-JSON output from {argv}: {r.stdout[:500]} / {r.stderr[:500]}")


def test_scripts_only_pipeline(plugin_root, temp_target, demo_source, expected):
    root = temp_target
    code, det = mt(plugin_root, root, "project", "detect")
    lib = det["libs"][0]
    code, init = mt(plugin_root, root, "project", "init", "--lib", lib["name"], "--module-prefix", "MathTcsE2E",
                    "--src-dir", ".", "--namespace", "MathTcsE2E", "--slug", "dn")
    assert init["created"]
    now = "2026-01-01T00:00:00Z"
    code, v = mt(plugin_root, root, "annotated", "validate", str(expected / "annotated.md"), "--source", str(demo_source))
    assert code == 0 and v["ok"], v["errors"]
    code, reg = mt(plugin_root, root, "annotated", "register", str(expected / "annotated.md"), "--source", str(demo_source), "--at", now)
    assert reg["count"] == 6
    code, ap = mt(plugin_root, root, "scaffold", "apply", str(expected / "proposals.json"), "--module", "Divisibility", "--at", now)
    assert code == 0 and ap["elaboration"]["ok"], ap
    assert len(ap["written"]) == 6 and ap["path"] == "MathTcsE2E/Divisibility.lean"
    assert ap["elaboration"]["blocks"]["dn-ch1-thm-1.1"]["trust"] == "DIRECT_SORRY"
    # snapshot + fixture reviews + combine
    code, snap = mt(plugin_root, root, "snapshot", "dn-ch1-thm-1.1", "--at", now)
    assert snap["elaboration"]["ok"] and snap["elaboration"]["trust"] == "DIRECT_SORRY"
    d = root / snap["dir"]
    sha = snap["statement_sha256"]
    (d / "semantic.json").write_text(json.dumps({"statement_sha256": sha, "verdict": "faithful", "fidelity_findings": [], "degenerate_case_findings": []}))
    (d / "reuse.json").write_text(json.dumps({"statement_sha256": "deadbeef", "verdict": "not_found", "searched": [], "candidates": []}))
    code, comb = mt(plugin_root, root, "report", "combine", "dn-ch1-thm-1.1", "--at", now)
    assert comb["action"] == "prove" and comb["reuse"] == "revision_mismatch" and comb["status"] == "verified"
    verify_md = (d / "verify.md").read_text()
    assert "## 1. Elaboration (formal)" in verify_md and "## 2. Semantic review (model)" in verify_md and "## 3. Reuse review (model)" in verify_md
    assert "human approval = none" in verify_md
    # promote a real proof
    proof = root / "proof.txt"
    proof.write_text("unfold Divides at hab hbc ⊢\nobtain ⟨q, rfl⟩ := hab\nobtain ⟨r, rfl⟩ := hbc\nexact ⟨q * r, Nat.mul_assoc a q r⟩\n")
    code, pr = mt(plugin_root, root, "promote", "dn-ch1-thm-1.1", "--proof", str(proof), "--at", now)
    assert code == 0 and pr["promoted"] and pr["trust"] == "FULLY_VERIFIED", pr
    assert set(pr["axioms"]) <= {"propext", "Classical.choice", "Quot.sound"}
    # transitive sorry is rejected
    proof3 = root / "proof3.txt"
    proof3.write_text("exact divides_add a (b + b) c (divides_add a b b hab hab) hac\n")
    code, pr3 = mt(plugin_root, root, "promote", "dn-ch1-thm-1.3", "--proof", str(proof3), "--at", now)
    assert code == 1 and not pr3["promoted"] and pr3["trust"] == "TRANSITIVE_SORRY" and pr3["status"] == "unfinished"
    # rerun protection: proved block is skipped by a second apply
    code, ap2 = mt(plugin_root, root, "scaffold", "apply", str(expected / "proposals.json"), "--module", "Divisibility", "--at", now, "--no-check")
    skipped = {s["id"]: s["reason"] for s in ap2["skipped"]}
    assert skipped.get("dn-ch1-thm-1.1") == "refused_protected"
    code, m = mt(plugin_root, root, "manifest", "get", "dn-ch1-thm-1.1")
    assert m["status"] == "proved" and m["trust"]["status"] == "FULLY_VERIFIED"
    # human edit of a statement is detected and invalidates verify
    mod = root / "MathTcsE2E" / "Divisibility.lean"
    mod.write_text(mod.read_text().replace("Divides a (b + c) := by", "Divides a (c + b) := by"))
    code, st = mt(plugin_root, root, "manifest", "stale", "dn-ch1-thm-1.2")
    assert {"block_changed", "statement_changed"} <= set(st["results"][0]["reasons"])
    code, t = mt(plugin_root, root, "manifest", "touch", "dn-ch1-thm-1.2", "--at", now)
    code, m2 = mt(plugin_root, root, "manifest", "get", "dn-ch1-thm-1.2")
    assert m2["human_edited"] and m2["lean"]["rev"] == 2 and m2["verify"]["rev"] is None
    # run record with explicit statuses
    payload = root / "payload.json"
    payload.write_text(json.dumps({"stages_planned": ["translate", "scaffold"], "ids": ["dn-ch1-thm-1.1", "dn-ch1-thm-1.2"],
                                   "declarations": {"dn-ch1-thm-1.1": {"translate": {"status": "ok"}, "scaffold": {"status": "weird"}}}}))
    code, rr = mt(plugin_root, root, "runs", "record", "--payload", str(payload), "--started-at", now)
    rec = json.loads((root / rr["path"]).read_text())
    assert rec["declarations"]["dn-ch1-thm-1.2"]["translate"]["status"] == "missing"
    assert rec["declarations"]["dn-ch1-thm-1.1"]["scaffold"]["status"] == "failed"
