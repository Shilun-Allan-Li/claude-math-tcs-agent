"""The public demo corpus, and the engine's independence from any one corpus.

Two jobs:

* **Regression.** The committed artifacts under ``demo/artifacts/`` are a fixture. If a
  change to the engine would alter them, that shows up here rather than in a private
  repository nobody else can run.
* **Domain-coupling detection.** The demo is elementary number theory. Anything the engine
  can only do for graph theory fails here, which is the whole reason a second corpus
  exists. There is deliberately no ``SimpleGraph``, no vertex and no edge in it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.corpus.config import load_corpus
from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.store import ArtifactStore

REPO = Path(__file__).resolve().parents[2]
DEMO_ARTIFACTS = REPO / "examples" / "demo-corpus" / "artifacts"
DEMO_FIXTURES = REPO / "examples" / "demo-corpus" / "fixtures"


@pytest.fixture
def demo_registry(tmp_path) -> CorpusRegistry:
    """A pipeline run over the demo corpus, from committed fixtures. No provider."""
    from pipeline.providers import DeclarationFixtureProvider, SectionFixtureProvider
    from pipeline.stages.formalize import formalize_declaration
    from pipeline.stages.annotate import annotate_chapter
    from pipeline.stages.ingest import ingest_chapter

    registry = CorpusRegistry.load(ArtifactStore(tmp_path, corpus="dn"))
    ingest_chapter(registry, 1, corpus_name="demo-naturals")
    registry.reload()
    annotate_chapter(
        registry, 1, provider=SectionFixtureProvider(DEMO_FIXTURES / "annotate"),
        corpus_name="demo-naturals",
    )
    registry.reload()
    provider = DeclarationFixtureProvider(DEMO_FIXTURES / "formalize")
    for declaration_id in ("dn-ch1-def-1.1-1", "dn-ch1-thm-1.1",
                           "dn-ch1-thm-1.2", "dn-ch1-thm-1.3"):
        formalize_declaration(registry, declaration_id, provider=provider)
    registry.reload()
    return registry


class TestConfig:
    def test_the_demo_corpus_is_configured_and_public(self):
        config = load_corpus("demo-naturals")
        assert config.slug == "dn"
        assert config.source_type == "notes"
        assert config.divisions[0].type == "unit", "generic division type, not 'chapter'"
        assert config.divisions[0].markdown.exists()

    def test_the_demo_source_contains_no_graph_theory(self):
        text = (REPO / "examples/demo-corpus/source/01_unit-1-divisibility.md").read_text().lower()
        for word in ("graph", "vertex", "vertices", "simplegraph", "connectivity"):
            assert word not in text, f"the demo corpus must not mention {word!r}"


class TestPipeline:
    def test_ingest_extracts_the_expected_items(self, demo_registry):
        ids = sorted(r.id for r in demo_registry)
        assert "dn-ch1-thm-1.1" in ids
        assert "dn-ch1-ex-1.2.2" in ids
        assert "dn-ch1-def-1.1-1" in ids, "the prose definition must be discovered"

    def test_the_book_s_own_cross_reference_becomes_an_edge(self, demo_registry):
        assert "dn-ch1-thm-1.2" in demo_registry.dependencies("dn-ch1-thm-1.3")

    def test_formalization_produces_lean_names_in_a_non_graph_namespace(self, demo_registry):
        names = {r.lean.name for r in demo_registry if r.lean.name}
        assert "DemoNaturals.Divides" in names
        assert not any("SimpleGraph" in n for n in names)

    def test_the_engine_needed_no_domain_specific_code(self, demo_registry):
        """The same stage functions that run any other corpus ran this one."""
        from pipeline.stages.annotate import ANNOTATE_VERSION
        from pipeline.stages.formalize import FORMALIZE_VERSION

        producers = {r.annotation.provenance.producer for r in demo_registry if r.annotation}
        assert producers == {ANNOTATE_VERSION}
        proposals = demo_registry.store.read("proposals")
        assert {p.provenance.producer for p in proposals} == {FORMALIZE_VERSION}


class TestCommittedArtifacts:
    """`pipeline demo` must work from what is checked in, with no model call."""

    def test_the_artifacts_are_committed(self):
        assert (DEMO_ARTIFACTS / "dn" / "declarations.jsonl").exists()

    def test_they_load_into_a_registry(self, tmp_path):
        import shutil

        shutil.copytree(DEMO_ARTIFACTS, tmp_path / "d")
        registry = CorpusRegistry.load(ArtifactStore(tmp_path / "d", corpus="dn"))
        assert len(registry) >= 4
        assert registry.graph_stats()["edges"] > 0

    def test_they_carry_the_three_trust_states_the_engine_distinguishes(self, tmp_path):
        """The distinction the whole system exists to make, on a non-graph corpus."""
        import shutil

        shutil.copytree(DEMO_ARTIFACTS, tmp_path / "d")
        registry = CorpusRegistry.load(ArtifactStore(tmp_path / "d", corpus="dn"))
        trust = {r.id: r.trust.status.value for r in registry if r.has_lean}
        assert trust["dn-ch1-def-1.1-1"] == "FULLY_VERIFIED"
        assert trust["dn-ch1-thm-1.1"] == "FULLY_VERIFIED", (
            "the pipeline proved this one, and Lean agrees"
        )
        assert trust["dn-ch1-thm-1.3"] == "TRANSITIVE_SORRY", (
            "a body with no sorry of its own that reaches sorryAx through a dependency"
        )

    def test_every_committed_edge_carries_provenance(self):
        rows = [json.loads(x) for x in
                (DEMO_ARTIFACTS / "dn" / "edges.jsonl").read_text().splitlines() if x.strip()]
        assert rows
        for row in rows:
            prov = row["provenance"]
            assert isinstance(prov, dict), "provenance must be structured, not a bare string"
            assert prov["kind"] and prov["producer"]


class TestEngineIsCorpusAgnostic:
    """The public/private test: one engine, two corpora, no core code change."""

    def test_the_public_api_serves_this_corpus_with_no_corpus_specific_code(self, tmp_path):
        """Everything a client needs, over a corpus the engine has never seen before."""
        import shutil

        from pipeline.api import Pipeline

        target = tmp_path / "d"
        shutil.copytree(DEMO_ARTIFACTS, target)
        api = Pipeline(target, corpus="demo-naturals")

        assert api.inspect_corpus()["source_type"] == "notes"
        divisions = api.list_divisions()
        assert divisions and divisions[0]["type"] == "unit", (
            "the division label follows the source, not a hardcoded default"
        )
        did = "dn-ch1-thm-1.3"
        assert api.get_declaration(did)["id"] == did
        assert api.get_source(did)["statement"]
        assert api.dependencies(did)
        assert api.graph_stats()["edges"] > 0
        assert api.checker_status(did)["ran"]
        assert api.verification_result(did)["trust"] == "TRANSITIVE_SORRY"

    def test_no_core_module_names_a_corpus(self):
        """Corpus identity belongs in data, never in code.

        The tokens below name the private research corpus this pipeline was developed
        against. They must not appear in the engine: a corpus that the code knows by name
        is a corpus the code can special-case for.
        """
        engine = REPO / "src" / "pipeline"
        offenders = []
        for path in engine.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for token in ("bondy", "murty"):
                if token in text:
                    offenders.append(f"{path.relative_to(REPO)} mentions {token!r}")
        assert not offenders, "\n".join(offenders)
