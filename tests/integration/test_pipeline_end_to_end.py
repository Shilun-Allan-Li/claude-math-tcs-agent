"""The pipeline, end to end, on the demo corpus.

Everything here runs offline against recorded provider responses. The Lean-backed
assertions are marked ``lean`` and skip without a built toolchain, so the rest of the
suite still tells you whether the pipeline works.

The three properties under test are the ones a reviewer should not have to take on trust:

* a declaration travels source → annotation → proposal → findings → review gate;
* the graph and the run survive a **process boundary**;
* nothing in ``src/pipeline`` needs a UI, or names a specific corpus.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.api import Pipeline
from pipeline.artifacts.store import ArtifactStore
from pipeline.corpus import CorpusRegistry
from pipeline.orchestrator import DeclarationStage, PipelineOrchestrator, RunStatus, RunStore
from pipeline.providers import DeclarationFixtureProvider, SectionFixtureProvider
from pipeline.stages.ingest import ingest_chapter

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "examples/demo-corpus/fixtures"
TARGET = "dn-ch1-thm-1.3"

pytestmark = pytest.mark.integration


def _providers() -> dict:
    return {
        "annotate": SectionFixtureProvider(FIXTURES / "annotate"),
        "formalize": DeclarationFixtureProvider(FIXTURES / "formalize"),
    }


@pytest.fixture
def run_dir(tmp_path) -> Path:
    registry = CorpusRegistry.load(ArtifactStore(tmp_path / "data", corpus="dn"))
    ingest_chapter(registry, 1, corpus_name="demo-naturals")
    registry.reload()
    return tmp_path / "data"


class TestStageProgression:
    def test_a_declaration_travels_from_source_to_the_review_gate(self, run_dir):
        registry = CorpusRegistry.load(ArtifactStore(run_dir, corpus="dn"))
        orch = PipelineOrchestrator.start(
            registry, run_id="e2e", targets=[TARGET],
            stop_after=DeclarationStage.FORMALIZED, providers=_providers(),
        )
        results = orch.run_until_gate()

        assert [r.stage.value for r in results] == ["annotate", "formalize"]
        assert all(r.ok for r in results)
        assert orch.run.state_for(TARGET).stage is DeclarationStage.FORMALIZED

    def test_every_stage_boundary_left_a_persisted_artifact(self, run_dir):
        registry = CorpusRegistry.load(ArtifactStore(run_dir, corpus="dn"))
        orch = PipelineOrchestrator.start(
            registry, run_id="e2e", targets=[TARGET],
            stop_after=DeclarationStage.FORMALIZED, providers=_providers(),
        )
        orch.run_until_gate()

        api = Pipeline(run_dir, corpus="demo-naturals")
        assert api.get_source(TARGET)["statement"]
        assert api.get_annotation(TARGET)["stated_hypotheses"]
        assert api.get_proposal(TARGET)["lean_name"] == "DemoNaturals.divides_add_add"
        # Not merely present: each records the prompt and context it was produced from.
        annotation = api.get_annotation(TARGET)
        assert annotation["provenance"]["prompt_version"]
        assert annotation["provenance"]["context_package_id"]

    def test_the_context_an_agent_saw_is_recoverable(self, run_dir):
        registry = CorpusRegistry.load(ArtifactStore(run_dir, corpus="dn"))
        orch = PipelineOrchestrator.start(
            registry, run_id="e2e", targets=[TARGET],
            stop_after=DeclarationStage.FORMALIZED, providers=_providers(),
        )
        orch.run_until_gate()

        api = Pipeline(run_dir, corpus="demo-naturals")
        package_id = api.get_proposal(TARGET)["provenance"]["context_package_id"]
        package = api.context_package(package_id)
        assert package["within_budget"]
        assert package["by_role"], "a package records what it supplied and why"
        for items in package["by_role"].values():
            for item in items:
                assert item["reason"], "every retrieved item carries its retrieval reason"


class TestPersistenceAcrossProcesses:
    """Stop the process, start a fresh one, resume from disk alone."""

    def test_a_fresh_interpreter_sees_the_same_graph(self, run_dir):
        registry = CorpusRegistry.load(ArtifactStore(run_dir, corpus="dn"))
        before = {
            "nodes": sorted(registry.graph.nodes()),
            "edges": sorted(e.key for e in registry.graph.edges),
        }
        script = (
            "import json;"
            "from pipeline.corpus import CorpusRegistry;"
            "from pipeline.artifacts.store import ArtifactStore;"
            f"r=CorpusRegistry.load(ArtifactStore({str(run_dir)!r}, corpus='dn'));"
            "print(json.dumps({'nodes':sorted(r.graph.nodes()),"
            "'edges':sorted(list(e.key) for e in r.graph.edges)}))"
        )
        out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                             text=True, cwd=REPO, check=True)
        after = json.loads(out.stdout)
        assert after["nodes"] == before["nodes"]
        assert [tuple(e) for e in after["edges"]] == before["edges"]

    def test_a_run_resumes_in_a_process_that_never_called_a_model(self, run_dir):
        registry = CorpusRegistry.load(ArtifactStore(run_dir, corpus="dn"))
        orch = PipelineOrchestrator.start(
            registry, run_id="split", targets=[TARGET],
            stop_after=DeclarationStage.ANNOTATED, providers=_providers(),
        )
        orch.run_until_gate()
        assert orch.run.state_for(TARGET).stage is DeclarationStage.ANNOTATED
        del orch, registry

        resumed = PipelineOrchestrator.resume(
            run_dir, "dn", "split",
            providers={"formalize": DeclarationFixtureProvider(FIXTURES / "formalize")},
        )
        assert resumed.run.state_for(TARGET).stage is DeclarationStage.ANNOTATED
        resumed.run.stop_after = DeclarationStage.FORMALIZED
        results = resumed.run_until_gate()

        assert [r.stage.value for r in results] == ["formalize"]
        assert resumed.run.state_for(TARGET).stage is DeclarationStage.FORMALIZED

    def test_completed_stages_do_not_rerun_on_restart(self, run_dir):
        registry = CorpusRegistry.load(ArtifactStore(run_dir, corpus="dn"))
        orch = PipelineOrchestrator.start(
            registry, run_id="idem", targets=[TARGET],
            stop_after=DeclarationStage.FORMALIZED, providers=_providers(),
        )
        orch.run_until_gate()
        counts = {c: len(registry.store.read(c)) for c in ("annotations", "proposals")}

        resumed = PipelineOrchestrator.resume(run_dir, "dn", "idem", providers=_providers())
        assert resumed.run_until_gate() == []
        resumed.registry.store.invalidate()
        assert {c: len(resumed.registry.store.read(c))
                for c in ("annotations", "proposals")} == counts

    def test_a_human_decision_survives_a_restart(self, run_dir):
        api = Pipeline(run_dir, corpus="demo-naturals")
        api.apply_review("dn-ch1-thm-1.1", "APPROVED",
                         reviewer="test", rationale="statement matches the source")

        fresh = Pipeline(run_dir, corpus="demo-naturals")
        review = fresh.get_review("dn-ch1-thm-1.1")
        assert review["status"] == "APPROVED"
        assert review["human_decision"]["reviewer"] == "test"
        assert not review["stale"]


class TestNoUIDependency:
    """The boundary this repository exists to draw."""

    def test_no_module_imports_a_ui(self):
        engine = REPO / "src" / "pipeline"
        offenders = []
        for path in engine.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in ("glass", "web.server", "flask", "fastapi", "django"):
                if token in text.lower():
                    offenders.append(f"{path.relative_to(REPO)} mentions {token!r}")
        assert not offenders, "\n".join(offenders)

    def test_every_cli_command_runs_headless(self):
        """No command may require a display, a server, or a browser."""
        from pipeline.cli import build_parser

        parser = build_parser()
        actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
        names = sorted({n for a in actions for n in (a.choices or {})})
        assert names, "the parser exposes subcommands"
        for banned in ("serve", "ui", "open", "browser"):
            assert banned not in names, f"`pipeline {banned}` is a UI concern"

    def test_the_public_api_returns_only_json_safe_data(self, run_dir):
        """A client of any language must be able to consume this."""
        api = Pipeline(run_dir, corpus="demo-naturals")
        for payload in (api.inspect_corpus(), api.list_declarations(),
                        api.graph_stats(), api.list_divisions(),
                        api.proof_queue(), api.edges()):
            json.dumps(payload)  # raises if anything is not serialisable


class TestCommittedLeanVerdict:
    """The verification *artifacts* the demo ships, read back without invoking Lean.

    These assert that a real verdict was recorded and that the three trust states stay
    distinguishable. They are deliberately not marked ``lean``: they shell out to nothing,
    so marking them so would mean the suite claimed Lean coverage it did not have.
    """

    def test_the_committed_demo_records_a_real_lean_verdict(self, api):
        result = api.verification_result("dn-ch1-thm-1.1")
        assert result["compile_status"] == "ok"
        assert result["trust"] == "FULLY_VERIFIED"
        assert "sorryAx" not in result["axioms"], "a proved theorem reaches no sorry"

    def test_direct_and_transitive_sorry_are_distinguished(self, api):
        direct = api.verification_result("dn-ch1-thm-1.2")
        transitive = api.verification_result("dn-ch1-thm-1.3")
        assert direct["trust"] == "DIRECT_SORRY"
        assert direct["direct_sorry"] is True
        assert transitive["trust"] == "TRANSITIVE_SORRY"
        assert transitive["direct_sorry"] is False, (
            "no sorry of its own; it reaches sorryAx through a dependency"
        )
        assert "sorryAx" in transitive["axioms"]


@pytest.mark.lean
class TestLeanIsAuthoritative:
    """Rule 5, exercised against a real toolchain rather than a recorded verdict.

    Skips unless ``lake`` is on PATH *and* Mathlib is built (see ``lean_toolchain_ready``).
    What it checks is the claim the committed artifacts rest on: that Lean's own answer for
    the demo module agrees with what the pipeline persisted, and in particular that a body
    containing no ``sorry`` is still not trusted when it reaches ``sorryAx`` transitively.
    """

    def test_the_demo_module_builds(self, lean_toolchain, repo_root):
        from pipeline.lean.build import lake_build

        result = lake_build("DemoCorpus", cwd=repo_root)
        assert result.ok, f"the committed demo module no longer builds:\n{result.stdout[-2000:]}"
        assert not result.errors, [d.message for d in result.errors]

    def test_lean_agrees_with_the_committed_trust_states(self, lean_toolchain, repo_root, api):
        """The recorded verdict must be reproducible, or it is just a stored opinion."""
        from pipeline.lean.axioms import print_axioms

        expected = {
            "dn-ch1-thm-1.1": False,   # proved
            "dn-ch1-thm-1.2": True,    # sorry in its own body
            "dn-ch1-thm-1.3": True,    # body is clean; reaches sorryAx through thm-1.2
        }
        names = {d: api.get_declaration(d)["lean"]["name"] for d in expected}
        reports, output = print_axioms("DemoNaturals", sorted(names.values()), cwd=repo_root)
        for decl_id, expect_sorry in expected.items():
            report = reports.get(names[decl_id])
            assert report is not None, f"no axiom report for {names[decl_id]}:\n{output[-2000:]}"
            assert report.uses_sorry is expect_sorry, (
                f"{decl_id} ({names[decl_id]}): Lean says sorryAx={report.uses_sorry}, "
                f"the committed artifact says {expect_sorry}"
            )

    def test_a_clean_body_can_still_be_untrusted(self, lean_toolchain, repo_root, api):
        """The distinction the whole trust model exists for, taken from Lean directly."""
        from pipeline.lean.axioms import print_axioms

        lean = api.get_declaration("dn-ch1-thm-1.3")["lean"]
        name = lean["name"]
        reports, _ = print_axioms("DemoNaturals", [name], cwd=repo_root)
        assert "sorry" not in (lean["statement"] or ""), "fixture drifted: the body has a sorry"
        assert reports[name].uses_sorry, "a text scan would have called this proved"
        assert not reports[name].is_trusted
