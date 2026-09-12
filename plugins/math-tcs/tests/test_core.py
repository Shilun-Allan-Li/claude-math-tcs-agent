"""Unit tests for the deterministic scripts (no Lean)."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mathtcs import args as args_mod
from mathtcs import annotated_md, axioms, blocks, ids, lean_json, manifest as mf, project, source_items
from mathtcs.report import _decide


# ------------------------------------------------------------------ args
def test_args_until_computes_stages():
    r = args_mod.parse("run", ["src.md", "--until", "verify", "--budget", "3", "--ids", "a,b"])
    assert r["stages"] == ["translate", "scaffold", "verify"]
    assert r["flags"]["budget"] == 3 and r["flags"]["ids"] == ["a", "b"]
    assert r["errors"] == []


@pytest.mark.parametrize("until,stages", [(None, 4), ("translate", 1), ("scaffold", 2), ("prove", 4)])
def test_args_until_values(until, stages):
    tokens = ["x.md"] + (["--until", until] if until else [])
    assert len(args_mod.parse("run", tokens)["stages"]) == stages


def test_args_rejects_unknown_until_and_flags():
    r = args_mod.parse("run", ["x.md", "--until", "nope", "--bogus"])
    assert any("--until" in e for e in r["errors"]) and any("--bogus" in e for e in r["errors"])
    assert r["stages"] == ["translate", "scaffold", "verify", "prove"]  # falls back to all


def test_args_path_vs_excerpt(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("x")
    assert args_mod.parse("translate", [str(f)])["target_is_path"] is True
    r = args_mod.parse("translate", ["Theorem", "1.1", "If", "a", "divides", "b"])
    assert r["target_is_path"] is False and r["target"] == "Theorem 1.1 If a divides b"


# ------------------------------------------------------------------ ids
def test_ids_labelled_and_unlabelled():
    assert ids.declaration_id("dn", "1", "theorem", label="Theorem 1.1") == "dn-ch1-thm-1.1"
    assert ids.declaration_id("dn", "1", "definition", section="1.1", ordinal=1) == "dn-ch1-def-1.1-1"
    assert ids.normalize_label("1.2.8(b)") == "1.2.8b" and ids.normalize_label("8.5.2 (a)*") == "8.5.2a"
    with pytest.raises(ids.IdentityError):
        ids.declaration_id("dn", "1", "theorem")
    assert ids.parse_declaration_id("dn-ch1-ex-1.2.1")["kind_name"] == "exercise"


def test_ids_slug_and_chapter_precedence():
    assert ids.derive_slug(explicit=None, configured=None, filename_stem="01_unit-1-divisibility") == ("ud", "filename")
    assert ids.derive_slug(explicit=None, configured="dn", filename_stem="whatever")[0] == "dn"
    assert ids.derive_chapter(explicit=None, configured=None, filename_stem="03_connectivity", text="") == ("3", "filename")
    assert ids.derive_chapter(explicit=None, configured=None, filename_stem="notes", text="# Chapter 7 — Flows\n") == ("7", "heading")
    assert ids.derive_chapter(explicit=None, configured=None, filename_stem="notes", text="**Theorem 4.2** x") == ("4", "first_label")
    assert ids.derive_chapter(explicit=None, configured=None, filename_stem="notes", text="nothing")[0] == "0"


def test_fingerprint_distinguishes_absent_and_empty():
    assert ids.content_fingerprint("s", None) != ids.content_fingerprint("s", "")


# ------------------------------------------------------------------ source items
def test_source_items_demo(demo_source):
    text = demo_source.read_text()
    items = source_items.extract(text, slug="dn", chapter="1")
    got = {i["id"]: i for i in items}
    assert list(got) == ["dn-ch1-thm-1.1", "dn-ch1-thm-1.2", "dn-ch1-thm-1.3", "dn-ch1-ex-1.2.1", "dn-ch1-ex-1.2.2"]
    assert got["dn-ch1-thm-1.1"]["lines"] == [11, 13] and got["dn-ch1-thm-1.1"]["proof"].endswith("□")
    assert got["dn-ch1-thm-1.3"]["section"] == "1.2" and got["dn-ch1-thm-1.3"]["page"] == 2
    assert got["dn-ch1-ex-1.2.1"]["proof"] is None


def test_source_items_multiline_proof_and_variants():
    text = "## 2.1 Things\n\n*Theorem 2.1* Claim.\n\n**Proof.** First line\nsecond line. ∎\n\n**Lemma 2.2** Other.\n"
    items = source_items.extract(text, slug="x", chapter="2")
    assert [i["id"] for i in items] == ["x-ch2-thm-2.1", "x-ch2-lem-2.2"]
    assert items[0]["proof"] == "First line\nsecond line. ∎" and items[0]["lines"] == [3, 6]


# ------------------------------------------------------------------ annotated IR
def test_annotated_expected_validates(expected, demo_source):
    text = (expected / "annotated.md").read_text()
    res = annotated_md.validate(text, source_text=demo_source.read_text(), slug=None, chapter=None)
    assert res["ok"], res["errors"]
    by = {d["id"]: d for d in res["declarations"]}
    assert by["dn-ch1-def-1.1-1"]["located"] == {"lines": [9, 9], "section": "1.1"}
    assert by["dn-ch1-thm-1.3"]["located"]["section"] == "1.2"


def test_annotated_tbd_assignment_and_rejections(expected, demo_source):
    text = (expected / "annotated.md").read_text()
    tbd = text.replace("## dn-ch1-def-1.1-1", "## TBD").replace('"id": "dn-ch1-def-1.1-1"', '"id": "TBD"', 1)
    new, assignments, errors = annotated_md.assign_ids(tbd, source_text=demo_source.read_text(), slug="dn", chapter="1")
    assert errors == [] and assignments == [{"heading": "TBD", "id": "dn-ch1-def-1.1-1", "section": "1.1", "line": 9}]
    assert "## dn-ch1-def-1.1-1" in new and '"id": "dn-ch1-def-1.1-1"' in new
    # paraphrased quote is rejected
    bad = text.replace("> If $a \\mid b$ and $b \\mid c$, then $a \\mid c$.", "> If a divides b and b divides c then a divides c.")
    res = annotated_md.validate(bad, source_text=demo_source.read_text(), slug=None, chapter=None)
    assert not res["ok"] and any("verbatim statement not found" in e for e in res["errors"])
    # proof flag inconsistent
    bad2 = text.replace('"has_source_proof": true,\n  "mathlib_candidates": [{"name": "dvd_trans"', '"has_source_proof": false,\n  "mathlib_candidates": [{"name": "dvd_trans"')
    res2 = annotated_md.validate(bad2, source_text=None, slug=None, chapter=None)
    assert any("has_source_proof is false" in e for e in res2["errors"])


def test_annotated_skeleton_roundtrip(expected):
    items = json.loads((expected / "items.json").read_text())
    text = annotated_md.render_skeleton(slug="dn", chapter="1", title="T", source_path="s.md", source_sha256="x", items=items["items"])
    doc = annotated_md.parse(text)
    assert [d["id"] for d in doc["declarations"]] == [i["id"] for i in items["items"]]


# ------------------------------------------------------------------ blocks
MODULE = """import Mathlib.Data.Nat.Basic

namespace MathTcs

-- math-tcs:begin id=x-ch1-def-1.1-1 rev=1
/-- doc -/
def Divides (a b : ℕ) : Prop :=
  ∃ q : ℕ, b = a * q
-- math-tcs:end id=x-ch1-def-1.1-1

-- math-tcs:begin id=x-ch1-thm-1.1 rev=2
/-- doc -/
theorem divides_trans (a b c : ℕ) (hab : Divides a b) (hbc : Divides b c) : Divides a c := by
  sorry
-- math-tcs:end id=x-ch1-thm-1.1

end MathTcs
"""


def test_blocks_parse_and_declarations():
    bs = blocks.parse_blocks(MODULE)
    assert [b.id for b in bs] == ["x-ch1-def-1.1-1", "x-ch1-thm-1.1"] and bs[1].rev == 2
    main = blocks.main_declaration(bs[1].inner)
    assert main["kw"] == "theorem" and main["name"] == "divides_trans"
    sig, body = blocks.split_statement(main["text"])
    assert sig.endswith(": Divides a c") and body.startswith(":= by")
    assert blocks.namespace_of(MODULE) == "MathTcs" and blocks.module_imports(MODULE) == ["Mathlib.Data.Nat.Basic"]


def test_split_statement_ignores_binder_defaults_and_strings():
    decl = 'theorem t (h : a := by simp) (s : String := ":=") : P := by\n  exact ":="'
    sig, body = blocks.split_statement(decl)
    assert sig == 'theorem t (h : a := by simp) (s : String := ":=") : P' and body.startswith(":= by")
    assert blocks.split_statement("structure S where\n  x : Nat")[1].startswith("where")


def test_replace_proof_and_classify():
    decl = "theorem t (a : ℕ) : a = a := by\n  sorry"
    assert blocks.replace_proof(decl, "by\nrfl").endswith(":= by\n  rfl")
    assert blocks.classify_body(decl, "theorem") == "sorry"
    assert blocks.classify_body("theorem t : True := by\n  trivial", "theorem") == "proof"
    assert blocks.classify_body("theorem t : True := foo bar", "theorem") == "structural"
    assert blocks.classify_body("def f : Nat := 1", "def") == "definition"
    assert blocks.statement_sha(decl) == blocks.statement_sha("theorem t (a : ℕ) : a = a := by\n  rfl")


def test_upsert_insert_replace_refuse():
    spec = {"id": "x-ch1-thm-1.2", "kind": "theorem", "label": "1.2", "source_ref": "s", "source_statement": "S", "source_proof": None}
    block = blocks.render_block(spec, "theorem divides_add (a : ℕ) : True := by\n  sorry", rev=1)
    text, outcome = blocks.upsert_block(MODULE, block, decl_id="x-ch1-thm-1.2")
    assert outcome == "inserted" and text.rstrip().endswith("end MathTcs")
    assert [b.id for b in blocks.parse_blocks(text)][-1] == "x-ch1-thm-1.2"
    # replace with matching expected sha
    cur = blocks.block_by_id(text, "x-ch1-thm-1.2")
    block2 = blocks.render_block(spec, "theorem divides_add (a : ℕ) : 1 = 1 := by\n  sorry", rev=2)
    text2, outcome2 = blocks.upsert_block(text, block2, decl_id="x-ch1-thm-1.2", expect_sha=cur.sha)
    assert outcome2 == "replaced" and blocks.block_by_id(text2, "x-ch1-thm-1.2").rev == 2
    # human edit refused
    edited = text2.replace("1 = 1", "2 = 2")
    _, outcome3 = blocks.upsert_block(edited, block2, decl_id="x-ch1-thm-1.2", expect_sha=cur.sha)
    assert outcome3 == "refused_human_edit"
    _, outcome4 = blocks.upsert_block(edited, block2, decl_id="x-ch1-thm-1.2", expect_sha=cur.sha, force=True)
    assert outcome4 == "replaced"
    _, outcome5 = blocks.upsert_block(text2, block2, decl_id="x-ch1-thm-1.2", protect=True)
    assert outcome5 == "unchanged"
    _, outcome6 = blocks.upsert_block(edited, block2, decl_id="x-ch1-thm-1.2", protect=True)
    assert outcome6 == "refused_protected"


def test_modifiers_and_doc_comment_and_imports():
    mods, body = blocks.split_modifiers("open scoped Classical in\n@[simp]\ntheorem t : True := by\n  sorry")
    assert mods == ["open scoped Classical in", "@[simp]"] and body.startswith("theorem")
    assert blocks.strip_doc_comment("/-- a /- nested -/ b -/\ntheorem t : True := by sorry").startswith("theorem")
    merged = blocks.merge_imports(MODULE, ["Mathlib.Tactic", "Mathlib.Data.Nat.Basic"])
    assert merged.splitlines()[:2] == ["import Mathlib.Data.Nat.Basic", "import Mathlib.Tactic"]


# ------------------------------------------------------------------ lean json + axioms
LEAN_JSON = """\
{"caption":"","data":"declaration uses 'sorry'","endPos":{"column":17,"line":7},"fileName":"P.lean","isSilent":false,"keepFullRange":false,"kind":"hasSorry","pos":{"column":8,"line":7},"severity":"warning"}
{"caption":"","data":"Tactic `rfl` failed","endPos":{"column":48,"line":12},"fileName":"P.lean","kind":"[anonymous]","pos":{"column":45,"line":12},"severity":"error"}
{"caption":"","data":"'MathTcsProbe.ok_thm' depends on axioms: [propext, Quot.sound]","endPos":{"column":6,"line":16},"fileName":"P.lean","kind":"[anonymous]","pos":{"column":0,"line":16},"severity":"information"}
{"caption":"","data":"'MathTcsProbe.transitive_thm' depends on axioms: [sorryAx]","pos":{"column":0,"line":17},"severity":"information"}
{"caption":"","data":"'X.y' does not depend on any axioms","pos":{"column":0,"line":18},"severity":"information"}
some lake noise line
"""


def test_lean_json_parse_and_axioms():
    diags, noise = lean_json.parse_lean_json(LEAN_JSON)
    assert len(diags) == 5 and noise == ["some lake noise line"]
    assert diags[0]["cls"] == "sorry" and diags[0]["line"] == 7 and diags[1]["severity"] == "error"
    reports = axioms.parse_axiom_messages(diags)
    assert reports == {"MathTcsProbe.ok_thm": ["propext", "Quot.sound"], "MathTcsProbe.transitive_thm": ["sorryAx"], "X.y": []}
    assert axioms.verdict(["propext", "Quot.sound"]) == {"trusted": True, "uses_sorry": False, "disallowed": []}
    assert axioms.verdict(["sorryAx"])["uses_sorry"] is True
    assert axioms.verdict(["propext", "Lean.ofReduceBool"])["disallowed"] == ["Lean.ofReduceBool"]
    assert axioms.verdict(["sorryAx"], allow=["sorryAx"])["trusted"] is False  # sorryAx cannot be allowlisted


def test_compute_trust_vocabulary():
    ct = axioms.compute_trust
    assert ct(compiled=False, axioms=None, allow=None, is_object=False, direct_sorry=False) == "COMPILE_FAILURE"
    assert ct(compiled=True, axioms=None, allow=None, is_object=False, direct_sorry=False) == "UNKNOWN"
    assert ct(compiled=True, axioms=["propext"], allow=None, is_object=False, direct_sorry=False) == "FULLY_VERIFIED"
    assert ct(compiled=True, axioms=["Lean.trustCompiler"], allow=None, is_object=False, direct_sorry=False) == "NONSTANDARD_AXIOM"
    assert ct(compiled=True, axioms=["sorryAx"], allow=None, is_object=True, direct_sorry=True) == "UNFINISHED_CONSTRUCTION"
    assert ct(compiled=True, axioms=["sorryAx"], allow=None, is_object=False, direct_sorry=True) == "DIRECT_SORRY"
    assert ct(compiled=True, axioms=["sorryAx"], allow=None, is_object=False, direct_sorry=False) == "TRANSITIVE_SORRY"


def test_axiom_text_linewrap():
    text = "'A.b' depends on axioms: [propext,\n Classical.choice, Quot.sound]\n'C' does not depend on any axioms\n"
    assert axioms.parse_axiom_text(text) == {"A.b": ["propext", "Classical.choice", "Quot.sound"], "C": []}


# ------------------------------------------------------------------ project + manifest
def test_project_detect_toml_and_lean(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.32.0\n")
    (root / "lakefile.toml").write_text('name = "glass"\n[[lean_lib]]\nname = "GlassFixtures"\nsrcDir = "fixtures/lean"\nroots = ["A", "B"]\n')
    d = project.detect(root)
    assert d["libs"][0] == {"name": "GlassFixtures", "src_dir": "fixtures/lean", "roots": ["A", "B"], "globs": [], "module_prefix_guess": "", "root_file": None}
    (root / "lakefile.toml").unlink()
    (root / "lakefile.lean").write_text('import Lake\nopen Lake DSL\npackage «t»\nlean_lib «TCSlib» {\n  srcDir := "src"\n}\n')
    (root / "src" / "TCSlib").mkdir(parents=True)
    d2 = project.detect(root)
    assert d2["libs"][0]["name"] == "TCSlib" and d2["libs"][0]["src_dir"] == "src" and d2["libs"][0]["module_prefix_guess"] == "TCSlib"


def test_manifest_lock_unlock_and_stale(fake_project):
    cfg = project.load_config(fake_project)
    data = mf.load(fake_project, cfg)
    mf.ensure(data, "dn-ch1-thm-1.1", {"kind": "theorem", "label": "1.1"}, slug="dn", chapter="1")
    mf.save(fake_project, cfg, data)
    lk = mf.lock(fake_project, cfg, "dn-ch1-thm-1.1", stage="prove", at="t0")
    assert lk["locked"]
    with pytest.raises(Exception):
        mf.lock(fake_project, cfg, "dn-ch1-thm-1.1", stage="prove", at="t1")
    assert mf.unlock(fake_project, cfg, "dn-ch1-thm-1.1")["unlocked"]
    assert mf.get(fake_project, cfg, "dn-ch1-thm-1.1")["lock"] is None
    # stale: block changed + statement changed
    mod = fake_project / "Proj" / "MathTcs" / "M.lean"
    mod.parent.mkdir(parents=True)
    mod.write_text(MODULE.replace("x-ch1", "dn-ch1"))
    b = blocks.block_by_id(mod.read_text(), "dn-ch1-thm-1.1")
    mf.set_field(fake_project, cfg, "dn-ch1-thm-1.1", "lean.path", "Proj/MathTcs/M.lean")
    mf.set_field(fake_project, cfg, "dn-ch1-thm-1.1", "lean.rev", 2)
    mf.set_field(fake_project, cfg, "dn-ch1-thm-1.1", "lean.block_sha256", b.sha)
    mf.set_field(fake_project, cfg, "dn-ch1-thm-1.1", "lean.statement_sha256", blocks.statement_sha(blocks.main_declaration(b.inner)["text"]))
    assert mf.stale(fake_project, cfg, "dn-ch1-thm-1.1")["stale"] is False
    mod.write_text(mod.read_text().replace("Divides a c := by", "Divides c a := by"))
    st = mf.stale(fake_project, cfg, "dn-ch1-thm-1.1")
    assert {"block_changed", "statement_changed"} <= set(st["reasons"]) and st["human_edited"]
    t = mf.touch(fake_project, cfg, "dn-ch1-thm-1.1", at="t2")
    e = mf.get(fake_project, cfg, "dn-ch1-thm-1.1")
    assert t["applied"] and e["human_edited"] and e["lean"]["rev"] == 3


# ------------------------------------------------------------------ recommended action rules
def _entry(**kw):
    e = {"blockers": [], "annotated": {}, "human_approval": {"status": "none"}}
    e.update(kw)
    return e


OK_ELAB = {"ok": True, "trust": "DIRECT_SORRY", "diagnostics": []}
SEM_OK = {"status": "ok", "fidelity_findings": [], "degenerate_case_findings": []}
REUSE_NF = {"status": "ok", "verdict": "not_found", "candidates": []}


def test_decide_rules():
    assert _decide(_entry(), {"ok": False, "trust": "COMPILE_FAILURE", "diagnostics": [{"severity": "error", "message": "boom"}]}, SEM_OK, REUSE_NF, [])["action"] == "repair_statement"
    assert _decide(_entry(), {"ok": True, "trust": "NONSTANDARD_AXIOM", "diagnostics": []}, SEM_OK, REUSE_NF, [])["action"] == "repair_statement"
    sem_fail = {"status": "ok", "fidelity_findings": [{"status": "fail", "severity": "high", "confidence": 0.9, "category": "MISSING_ASSUMPTION", "message": "m"}], "degenerate_case_findings": []}
    assert _decide(_entry(), OK_ELAB, sem_fail, REUSE_NF, [])["action"] == "repair_statement"
    sem_low = {"status": "ok", "fidelity_findings": [{"status": "fail", "severity": "high", "confidence": 0.3}], "degenerate_case_findings": []}
    assert _decide(_entry(), OK_ELAB, sem_low, REUSE_NF, [])["action"] == "prove"
    sem_false = {"status": "ok", "fidelity_findings": [], "degenerate_case_findings": [{"outcome": "false", "category": "ZERO_PARAMETER"}]}
    assert _decide(_entry(), OK_ELAB, sem_false, REUSE_NF, [])["action"] == "repair_statement"
    assert _decide(_entry(blockers=["x"]), OK_ELAB, SEM_OK, REUSE_NF, [])["action"] == "defer"
    assert _decide(_entry(), OK_ELAB, SEM_OK, REUSE_NF, ["dn-ch1-thm-1.2"])["action"] == "defer"
    assert _decide(_entry(), OK_ELAB, {"status": "missing"}, REUSE_NF, [])["action"] == "defer"
    reuse_exact = {"status": "ok", "verdict": "exists_exact", "candidates": [{"name": "dvd_add", "evidence": {"check": "t", "probe": {"ok": True, "term": "dvd_add h1 h2"}}}]}
    d = _decide(_entry(), OK_ELAB, SEM_OK, reuse_exact, [])
    assert d["action"] == "reuse" and d["reuse_hint"] == "dvd_add h1 h2"
    reuse_claim = {"status": "ok", "verdict": "exists_exact", "candidates": [{"name": "dvd_add", "evidence": {"check": None, "probe": None}}]}
    assert _decide(_entry(), OK_ELAB, SEM_OK, reuse_claim, [])["action"] == "prove"
    reuse_adapt = {"status": "ok", "verdict": "exists_adaptable", "candidates": [{"name": "dvd_trans", "adaptation": "small", "evidence": {"check": "@dvd_trans : …", "probe": None}}]}
    d2 = _decide(_entry(), OK_ELAB, SEM_OK, reuse_adapt, [])
    assert d2["action"] == "prove" and d2["reuse_hint"] == "dvd_trans"
    assert _decide(_entry(), OK_ELAB, SEM_OK, REUSE_NF, [])["priority"] == "normal"  # not_found never raises priority


# ------------------------------------------------------------------ run.js static
def test_runjs_static(plugin_root):
    s = (plugin_root / "workflows" / "run.js").read_text()
    m = re.match(r"\s*export const meta = (\{.*?\n\})\n", s, re.S)
    assert m, "meta literal must open the file"
    meta, body = m.group(1), s[m.end():]
    assert "${" not in meta and "Date.now" not in body and "Math.random" not in body and "new Date()" not in body
    titles = set(re.findall(r"phase\('([^']+)'\)", body))
    assert titles <= set(re.findall(r"title: '([^']+)'", meta))
    assert "agentType: T(" in body and "'tool-runner'" in body
    import shutil
    if shutil.which("node"):
        wrapped = "const meta = " + meta + ";\n(async (args, agent, parallel, pipeline, phase, log, budget, workflow) => {\n" + body + "\n});\n"
        p = plugin_root / "tests" / "_run_check.mjs"
        p.write_text(wrapped)
        try:
            r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
        finally:
            p.unlink(missing_ok=True)


def test_cli_smoke(plugin_root):
    r = subprocess.run([sys.executable, str(plugin_root / "scripts" / "mathtcs.py"), "args", "run", "x.md", "--until", "scaffold"], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["stages"] == ["translate", "scaffold"]
    r2 = subprocess.run([sys.executable, str(plugin_root / "scripts" / "mathtcs.py"), "nope"], capture_output=True, text=True)
    assert r2.returncode == 2 and "unknown command" in json.loads(r2.stdout)["error"]
