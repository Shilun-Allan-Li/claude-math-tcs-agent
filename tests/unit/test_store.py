"""Serialization round-trips and store semantics."""

from __future__ import annotations

import pytest

from pipeline.artifacts.models import EdgeProvenanceKind, DependencyEdge, EdgeProvenance, EdgeType
from pipeline.artifacts.records import record_from_source_item
from pipeline.artifacts.store import ArtifactStore, StoreError


def test_round_trip_preserves_every_field(store, source_items):
    records = [record_from_source_item(i) for i in source_items]
    store.write_all("declarations", records)
    store.invalidate()
    reloaded = store.read("declarations")
    assert len(reloaded) == len(records)
    for before, after in zip(records, reloaded, strict=True):
        assert before.model_dump(mode="json") == after.model_dump(mode="json")


def test_upsert_converges_instead_of_accumulating(store, source_items):
    """Re-running a stage must not duplicate rows (report 00 §B5)."""
    records = [record_from_source_item(i) for i in source_items]
    store.upsert("declarations", records)
    store.upsert("declarations", records)
    assert len(store.read("declarations")) == len(records)


def test_upsert_replaces_by_key_and_keeps_order(store, source_items):
    records = [record_from_source_item(i) for i in source_items]
    store.upsert("declarations", records)
    changed = records[0].model_copy(deep=True)
    changed.lean.name = "SimpleGraph.whitney_inequalities"
    store.upsert("declarations", [changed])
    reloaded = store.read("declarations")
    assert len(reloaded) == len(records)
    assert reloaded[0].id == records[0].id
    assert reloaded[0].lean.name == "SimpleGraph.whitney_inequalities"


def test_edges_are_keyed_on_the_full_triple(store):
    a = DependencyEdge(
        source_id="x", target_id="y", edge_type=EdgeType.INFORMAL_DEPENDENCY,
        provenance=EdgeProvenanceKind.AGENT_INFERRED,
    )
    b = DependencyEdge(
        source_id="x", target_id="y", edge_type=EdgeType.LEAN_LOCAL_DEPENDENCY,
        provenance=EdgeProvenanceKind.LEAN_EXTRACTED,
    )
    store.upsert("edges", [a, b, a])
    assert len(store.read("edges")) == 2


def test_a_corrupt_line_fails_loudly_rather_than_loading(store, source_items):
    """These files are meant to be hand-inspectable, so hand-edits must be caught."""
    store.write_all("declarations", [record_from_source_item(source_items[0])])
    path = store.path("declarations")
    path.write_text('{"id": "broken"}\n', encoding="utf-8")
    store.invalidate()
    with pytest.raises(StoreError, match="not a valid DeclarationRecord"):
        store.read("declarations")


def test_writing_the_wrong_type_into_a_collection_is_rejected(store, source_items):
    with pytest.raises(StoreError, match="holds"):
        store.write_all("findings", [record_from_source_item(source_items[0])])


def test_unknown_collections_are_rejected(store):
    with pytest.raises(StoreError, match="unknown collection"):
        store.path("nonsense")


def test_serialized_lines_are_deterministic(tmp_path, source_items):
    """Byte-stable output keeps artifact diffs meaningful in git."""
    a = ArtifactStore(tmp_path / "a", corpus="bm")
    b = ArtifactStore(tmp_path / "b", corpus="bm")
    records = [record_from_source_item(i) for i in source_items]
    a.write_all("declarations", records)
    b.write_all("declarations", records)
    assert a.path("declarations").read_bytes() == b.path("declarations").read_bytes()


def test_missing_collection_reads_as_empty(store):
    assert store.read("findings") == []


def test_reruns_do_not_churn_artifact_files(store, demo_markdown, demo_config):
    """A deterministic re-run must be a no-op on disk, so diffs stay meaningful."""
    from pipeline.artifacts.records import record_from_source_item
    from pipeline.stages.source_items import extract_source_items

    first = [record_from_source_item(i) for i in extract_source_items(demo_markdown, demo_config)]
    store.upsert("declarations", first)
    before = store.path("declarations").read_bytes()

    # A second extraction produces fresh provenance timestamps but identical content.
    second = [record_from_source_item(i) for i in extract_source_items(demo_markdown, demo_config)]
    assert second[0].source.provenance.created_at != first[0].source.provenance.created_at
    store.invalidate()
    store.upsert("declarations", second)
    assert store.path("declarations").read_bytes() == before


def test_a_real_content_change_is_written(store, source_items):
    from pipeline.artifacts.records import record_from_source_item

    records = [record_from_source_item(i) for i in source_items]
    store.upsert("declarations", records)
    before = store.path("declarations").read_bytes()
    changed = records[0].model_copy(deep=True)
    changed.lean.name = "SimpleGraph.whitney_inequalities"
    store.upsert("declarations", [changed])
    assert store.path("declarations").read_bytes() != before


def test_mutating_a_loaded_record_and_writing_it_back_persists(tmp_path, source_items):
    """A cached object mutated in place must still be detected as changed.

    Regression: the no-churn optimisation originally compared the incoming artifact
    against the *live* cached object, which is the same object after an in-place edit,
    so the write was silently skipped.
    """
    from pipeline.artifacts.records import record_from_source_item

    store = ArtifactStore(tmp_path / "data", corpus="bm")
    store.upsert("declarations", [record_from_source_item(i) for i in source_items])

    loaded = store.read("declarations")[0]
    loaded.lean.name = "SimpleGraph.whitney_inequalities"
    store.upsert("declarations", [loaded])

    fresh = ArtifactStore(tmp_path / "data", corpus="bm")
    assert fresh.read("declarations")[0].lean.name == "SimpleGraph.whitney_inequalities"
