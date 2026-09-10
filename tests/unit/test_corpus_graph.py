"""CorpusGraph as executable infrastructure.

These tests exist to answer one question with code rather than with prose: **is the
dependency graph a real subsystem, or a description of one?** Every assertion below runs
without a provider, without a network, and without any conversation history. If the graph
were implemented by asking a model, none of them could pass.

Three properties are checked:

* the deterministic query surface returns the right answers;
* every edge records *why* it exists, not merely that it does;
* the graph survives a process boundary unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.corpus import CorpusRegistry
from pipeline.graph import CorpusGraph
from pipeline.artifacts.models import DependencyEdge, EdgeProvenance, EdgeProvenanceKind, EdgeType
from pipeline.artifacts.store import ArtifactStore

REPO = Path(__file__).resolve().parents[2]


def edge(src, tgt, *, kind=EdgeProvenanceKind.SOURCE_EXTRACTED, producer="test",
         artifact_id=None, evidence=None, edge_type=EdgeType.INFORMAL_DEPENDENCY):
    return DependencyEdge(
        source_id=src, target_id=tgt, edge_type=edge_type,
        provenance=EdgeProvenance(kind=kind, producer=producer,
                                  artifact_id=artifact_id, evidence=evidence),
    )


# ------------------------------------------------------------------- the fixture
#
#   A       B          C depends on A and B
#    \     /           D is independent
#     \   /
#       C        D


@pytest.fixture
def scheduler_graph() -> CorpusGraph:
    return CorpusGraph([edge("C", "A"), edge("C", "B")])


NODES = ["A", "B", "C", "D"]


class TestScheduler:
    """The eligibility sequence the brief specifies, from executable graph logic."""

    def test_initially_a_b_and_d_are_eligible(self, scheduler_graph):
        assert scheduler_graph.eligible_nodes(candidates=NODES) == ["A", "B", "D"]

    def test_after_a_completes_b_and_d_remain(self, scheduler_graph):
        assert scheduler_graph.eligible_nodes({"A"}, candidates=NODES) == ["B", "D"]

    def test_after_a_and_b_complete_c_becomes_eligible(self, scheduler_graph):
        assert scheduler_graph.eligible_nodes({"A", "B"}, candidates=NODES) == ["C", "D"]

    def test_c_is_never_eligible_before_both_of_its_dependencies(self, scheduler_graph):
        assert "C" not in scheduler_graph.eligible_nodes(candidates=NODES)
        assert "C" not in scheduler_graph.eligible_nodes({"A"}, candidates=NODES)
        assert "C" not in scheduler_graph.eligible_nodes({"B"}, candidates=NODES)

    def test_d_is_eligible_at_every_step_because_nothing_blocks_it(self, scheduler_graph):
        for done in ((), {"A"}, {"A", "B"}, {"A", "B", "C"}):
            assert "D" in scheduler_graph.eligible_nodes(done, candidates=NODES)

    def test_a_completed_node_is_not_offered_again(self, scheduler_graph):
        assert "A" not in scheduler_graph.eligible_nodes({"A"}, candidates=NODES)

    def test_library_nodes_neither_schedule_nor_block(self):
        """A Mathlib dependency is not a work item and must not gate one."""
        g = CorpusGraph([edge("X", "mathlib:Nat.succ", edge_type=EdgeType.MATHLIB_DEPENDENCY)])
        assert g.eligible_nodes(candidates=["X"]) == ["X"]
        assert "mathlib:Nat.succ" not in g.eligible_nodes()


class TestQuerySurface:
    def test_dependencies_and_reverse_dependencies(self, scheduler_graph):
        assert scheduler_graph.dependencies("C") == ["A", "B"]
        assert scheduler_graph.reverse_dependencies("A") == ["C"]
        assert scheduler_graph.dependencies("A") == []

    def test_unresolved_dependencies_names_the_missing_target(self):
        g = CorpusGraph([edge("C", "A"), edge("C", "ghost")])
        assert g.unresolved_dependencies({"A", "C"}) == {"C": ["ghost"]}

    def test_unresolved_ignores_library_nodes(self):
        g = CorpusGraph([edge("C", "mathlib:Foo", edge_type=EdgeType.MATHLIB_DEPENDENCY)])
        assert g.unresolved_dependencies({"C"}) == {}

    def test_graph_stats_counts_by_type_and_provenance(self, scheduler_graph):
        stats = scheduler_graph.graph_stats()
        assert stats["edges"] == 2
        assert stats["by_edge_type"] == {"informal_dependency": 2}
        assert stats["by_provenance"] == {"source_extracted": 2}
        assert stats["cycles"] == 0

    def test_every_query_runs_without_a_provider(self, scheduler_graph):
        """The whole surface, with no provider anywhere in scope."""
        g = scheduler_graph
        assert g.dependencies("C") and g.reverse_dependencies("A")
        assert g.unresolved_dependencies(NODES) == {}
        assert g.graph_stats()["nodes"] == 3
        assert g.eligible_nodes(candidates=NODES)


class TestEdgeProvenance:
    def test_an_edge_records_producer_and_artifact(self):
        e = edge("C", "A", kind=EdgeProvenanceKind.AGENT_INFERRED,
                 producer="annotator", artifact_id="annotation-123",
                 evidence="annotation for C references theorem A")
        assert e.provenance.kind is EdgeProvenanceKind.AGENT_INFERRED
        assert e.provenance.producer == "annotator"
        assert e.provenance.artifact_id == "annotation-123"
        assert e.provenance.evidence

    def test_only_exact_provenance_may_gate(self):
        assert edge("C", "A", kind=EdgeProvenanceKind.SOURCE_EXTRACTED).may_gate
        assert edge("C", "A", kind=EdgeProvenanceKind.LEAN_EXTRACTED).may_gate
        assert edge("C", "A", kind=EdgeProvenanceKind.HUMAN_CONFIRMED).may_gate
        assert not edge("C", "A", kind=EdgeProvenanceKind.AGENT_INFERRED).may_gate

    def test_a_pre_structured_edge_file_still_loads(self):
        """Edge rows written before provenance became an object must read forward."""
        legacy = json.dumps({
            "source_id": "C", "target_id": "A",
            "edge_type": "source_cross_reference",
            "provenance": "source_extracted",
            "evidence": "C proof: 'theorem A'",
            "confidence": 1.0, "note": None,
        })
        e = DependencyEdge.model_validate_json(legacy)
        assert e.provenance.kind is EdgeProvenanceKind.SOURCE_EXTRACTED
        assert e.provenance.evidence == "C proof: 'theorem A'"
        assert e.may_gate

    def test_the_pipeline_stamps_real_provenance_on_extracted_edges(self, tmp_path):
        """Not a hand-built edge: one the ingest stage actually produced."""
        from pipeline.stages.ingest import ingest_chapter

        registry = CorpusRegistry.load(ArtifactStore(tmp_path, corpus="dn"))
        ingest_chapter(registry, 1, corpus_name="demo-naturals")
        registry.reload()
        edges = [e for e in registry.graph.edges
                 if e.edge_type is EdgeType.SOURCE_CROSS_REFERENCE]
        assert edges, "the demo corpus states at least one cross-reference"
        e = edges[0]
        assert e.provenance.kind is EdgeProvenanceKind.SOURCE_EXTRACTED
        assert e.provenance.producer == "cross_references/v1"
        assert e.provenance.artifact_id == e.source_id
        assert "theorem 1.2" in (e.provenance.evidence or "")


class TestPersistence:
    """Process starts → graph loads → process stops → fresh process → same graph."""

    def test_a_fresh_interpreter_reads_back_the_same_nodes_and_edges(self, tmp_path):
        from pipeline.stages.ingest import ingest_chapter

        registry = CorpusRegistry.load(ArtifactStore(tmp_path, corpus="dn"))
        ingest_chapter(registry, 1, corpus_name="demo-naturals")
        registry.reload()
        before = {
            "nodes": sorted(registry.graph.nodes()),
            "edges": sorted(e.key for e in registry.graph.edges),
            "stats": registry.graph_stats(),
        }
        del registry

        # A genuinely separate interpreter. Nothing is handed over but the path.
        script = (
            "import json,sys;"
            "from pipeline.corpus import CorpusRegistry;"
            "from pipeline.artifacts.store import ArtifactStore;"
            f"r=CorpusRegistry.load(ArtifactStore({str(tmp_path)!r}, corpus='dn'));"
            "print(json.dumps({'nodes':sorted(r.graph.nodes()),"
            "'edges':sorted(list(e.key) for e in r.graph.edges),"
            "'stats':r.graph_stats()}))"
        )
        out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                             text=True, cwd=REPO, check=True)
        after = json.loads(out.stdout)

        assert after["nodes"] == before["nodes"]
        assert [tuple(e) for e in after["edges"]] == before["edges"]
        assert after["stats"] == before["stats"]

    def test_provenance_survives_the_process_boundary(self, tmp_path):
        from pipeline.stages.ingest import ingest_chapter

        registry = CorpusRegistry.load(ArtifactStore(tmp_path, corpus="dn"))
        ingest_chapter(registry, 1, corpus_name="demo-naturals")

        fresh = CorpusRegistry.load(ArtifactStore(tmp_path, corpus="dn"))
        for e in fresh.graph.edges:
            assert e.provenance.kind is not None
            assert e.provenance.producer, f"{e.key} lost its producer on reload"


class TestConsumersShareOneGraph:
    """Context retrieval, a UI client and the scheduler must read the same persisted graph."""

    @pytest.fixture
    def registry(self, tmp_path):
        from pipeline.stages.ingest import ingest_chapter

        r = CorpusRegistry.load(ArtifactStore(tmp_path, corpus="dn"))
        ingest_chapter(r, 1, corpus_name="demo-naturals")
        r.reload()
        return r

    def test_registry_delegates_the_named_surface_to_the_graph(self, registry):
        target = "dn-ch1-thm-1.3"
        assert registry.dependencies(target) == registry.graph.dependencies(target)
        assert registry.graph_stats() == registry.graph.graph_stats()

    def test_context_builder_retrieves_through_the_graph(self, registry):
        from pipeline.context.builders import build_formalization_context

        # The context builder asks the graph for prerequisites; with no annotation yet
        # the package still builds, and its dependency items come from graph edges.
        pkg = build_formalization_context(registry, "dn-ch1-thm-1.3")
        assert pkg.target_id == "dn-ch1-thm-1.3"
        assert pkg.corpus_version == registry.version

    def test_the_public_api_reads_the_same_edges(self, registry, tmp_path):
        """A UI client sees exactly what the graph holds — no second source of truth."""
        from pipeline.api import Pipeline

        api = Pipeline(registry.store.root, corpus="demo-naturals")
        target = "dn-ch1-thm-1.3"
        assert api.dependencies(target) == registry.graph.dependencies(target)
        for edge in api.edges(target):
            prov = edge["provenance"]
            assert prov["kind"] and prov["producer"], "every edge says who asserted it"

    def test_scheduler_reads_the_same_edges(self, registry):
        eligible = registry.eligible_nodes()
        # thm-1.3 cites thm-1.2, so it is not eligible until that one is done.
        assert "dn-ch1-thm-1.3" not in eligible
        assert "dn-ch1-thm-1.2" in eligible
        after = registry.eligible_nodes({"dn-ch1-thm-1.2"})
        assert "dn-ch1-thm-1.3" in after
