"""The engine must serve a corpus it has never seen, mounted from outside the repository.

This is the acceptance test for the repository's central claim about scope: the pipeline is
public, the corpora it is pointed at need not be, and adding one is *data* -- a JSON config
and some Markdown -- rather than a change to anything under ``src/pipeline/``.

Every test here builds a corpus that exists only in ``tmp_path``: unlabelled parity
mathematics, a different slug, a different division word, and a proof typography the demo
corpus does not use. It is mounted through ``PIPELINE_CORPORA_PATH`` and never copied into
the tree. What is asserted is not that ingestion produces some output, but that the parts
which could plausibly have been tuned to the one committed corpus are in fact generic:
declaration identity, cross-reference extraction, and the graph the three consumers share.

The demo corpus cannot establish any of this on its own. Its name abbreviates to exactly
its configured slug (``demo-naturals`` -> ``dn``), so an id prefix taken from the wrong
field looks correct; and it uses one proof marker, so a pattern matching only that spelling
looks complete. Both faults were real, and both are only visible against a second corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: A corpus with nothing in common with the demo: parity rather than divisibility, the
#: slug ``xp`` (which is *not* what ``ext-parity`` abbreviates to), "unit" as the division
#: word, ``**Proof.**`` as the proof marker, and a LaTeX tombstone rather than a glyph.
EXTERNAL_SOURCE = r"""<!-- p.1 -->

# Unit 1 — Parity

## 1.1 Even integers

An integer $n$ is *even* if there is an integer $k$ with $n = 2k$.

**Theorem 1.1** If $n$ is even then $n^2$ is even.

**Proof.** Write $n = 2k$. Then $n^2 = 4k^2 = 2(2k^2)$. $\square$

<!-- p.2 -->

## 1.2 Sums

**Theorem 1.2** The sum of two even integers is even.

**Proof.** By theorem 1.1 the squares are even. Write $m = 2j$ and $n = 2k$; then
$m + n = 2(j + k)$. $\square$
"""

EXTERNAL_CONFIG = {
    "corpus": "ext-parity",
    "slug": "xp",
    "title": "Parity (mounted from outside the repository)",
    "authors": ["another researcher"],
    "source_type": "notes",
    "divisions": [
        {
            "number": "1",
            "type": "unit",
            "title": "Parity",
            "markdown": "source/01.md",
            "printed_page_offset": 0,
        }
    ],
}


@pytest.fixture
def external_corpus(tmp_path, monkeypatch) -> Path:
    """A corpus mounted from outside the repository, with repo-relative paths unused.

    ``markdown`` is written relative to the *config's own* directory, which is the only
    thing an external corpus can rely on: it has no reason to know where the engine is
    installed, and requiring a repo-relative path would mean it is not really external.
    """
    root = tmp_path / "somewhere-else" / "parity"
    (root / "source").mkdir(parents=True)
    (root / "source" / "01.md").write_text(EXTERNAL_SOURCE, encoding="utf-8")
    (root / "ext-parity.json").write_text(json.dumps(EXTERNAL_CONFIG, indent=2), encoding="utf-8")
    monkeypatch.setenv("PIPELINE_CORPORA_PATH", str(root))
    assert REPO not in root.parents, "the fixture must live outside the repository"
    return root


@pytest.fixture
def external_registry(external_corpus, tmp_path):
    """The external corpus, ingested into its own store outside the repository."""
    from pipeline.artifacts.store import ArtifactStore
    from pipeline.corpus import CorpusRegistry
    from pipeline.stages.ingest import ingest_chapter

    registry = CorpusRegistry.load(ArtifactStore(tmp_path / "extdata", corpus="xp"))
    ingest_chapter(registry, 1, corpus_name="ext-parity")
    registry.reload()
    return registry


class TestMounting:
    """Discovery and loading of a corpus the repository does not contain."""

    def test_a_corpus_outside_the_repository_is_discovered(self, external_corpus):
        from pipeline.corpus.config import available_corpora, corpora_dirs

        assert external_corpus in corpora_dirs()
        assert "ext-parity" in available_corpora()
        # The committed demo is still there: mounting adds, it does not replace.
        assert "demo-naturals" in available_corpora()

    def test_its_paths_resolve_relative_to_its_own_directory(self, external_corpus):
        from pipeline.corpus.config import load_corpus

        config = load_corpus("ext-parity")
        assert config.chapters[0].markdown == external_corpus / "source" / "01.md"
        assert config.chapters[0].markdown.exists()

    def test_the_sources_config_and_data_all_stay_out_of_the_tree(
        self, external_corpus, external_registry
    ):
        from pipeline.corpus.config import load_corpus

        config = load_corpus("ext-parity")
        for path in (config.path, config.chapters[0].markdown, external_registry.store.root):
            assert REPO not in Path(path).parents, f"{path} leaked into the repository"

    def test_an_unmounted_corpus_reports_where_it_looked(self):
        from pipeline.corpus.config import ConfigError, load_corpus

        with pytest.raises(ConfigError) as exc:
            load_corpus("no-such-corpus")
        message = str(exc.value)
        assert "PIPELINE_CORPORA_PATH" in message, "the error should say how to mount one"
        assert "corpora" in message, "and where it already looked"

    def test_the_division_word_is_carried_not_interpreted(self, external_corpus):
        from pipeline.corpus.config import load_corpus

        # The source calls its divisions "unit"; nothing downstream may branch on that.
        assert load_corpus("ext-parity").chapters[0].type == "unit"


class TestIdentityComesFromTheConfig:
    """Declaration ids must use the slug the corpus config sets, verbatim."""

    def test_the_configured_slug_is_the_id_prefix(self, external_registry):
        ids = sorted(r.id for r in external_registry)
        assert ids == ["xp-ch1-thm-1.1", "xp-ch1-thm-1.2"]

    def test_the_prefix_is_not_re_derived_from_the_corpus_name(self, external_registry):
        """``ext-parity`` abbreviates to ``ep``; the config says ``xp``, so ``xp`` wins.

        A configured slug that the engine quietly overrode would break the join key a
        human uses, and the demo corpus could never reveal it.
        """
        for record in external_registry:
            assert record.id.startswith("xp-")
            assert not record.id.startswith("ep-")

    def test_a_short_single_word_slug_survives_intact(self):
        from pipeline.artifacts.models import SourceItemKind
        from pipeline.corpus.ids import declaration_id

        # Abbreviating a deliberate one-token slug to its first letter would be silent
        # data loss; only a multi-word corpus *name* is abbreviated.
        assert declaration_id("parity", "1", SourceItemKind.THEOREM, label="Theorem 1.1") == (
            "parity-ch1-thm-1.1"
        )
        assert declaration_id("euler-analysis", "3", SourceItemKind.THEOREM, label="3.2") == (
            "ea-ch3-thm-3.2"
        )


class TestExtractionIsNotTunedToOneBook:
    """The committed corpus uses one typography; a second corpus uses another."""

    def test_a_proof_marker_the_demo_never_uses_is_still_found(self, external_registry):
        records = {r.id: r for r in external_registry}
        assert records, "sanity: the corpus produced declarations"
        for decl_id in ("xp-ch1-thm-1.1", "xp-ch1-thm-1.2"):
            proof = external_registry.require(decl_id).source.proof
            assert proof, f"{decl_id} lost its `**Proof.**` block"

    @pytest.mark.parametrize(
        "marker",
        ["*Proof*", "*Proof.*", "**Proof.**", "**Proof**", "_Proof._", "*Proof:*",
         "*Proof of Theorem 1.1.*"],
    )
    def test_every_common_proof_opener_is_recognised(self, marker):
        from pipeline.stages.source_items import PROOF_RE

        assert PROOF_RE.match(marker), f"{marker!r} would silently drop a proof"

    @pytest.mark.parametrize("line", ["*Proofs are omitted*", "**Theorem 1.1** If x then y."])
    def test_near_misses_do_not_open_a_proof(self, line):
        from pipeline.stages.source_items import PROOF_RE

        assert not PROOF_RE.match(line)

    def test_a_cross_reference_inside_that_proof_becomes_an_edge(self, external_registry):
        """Losing the proof would lose the citation in it, and the graph would say nothing."""
        assert external_registry.dependencies("xp-ch1-thm-1.2") == ["xp-ch1-thm-1.1"]


class TestTheGraphIsTheSameGraph:
    """One CorpusGraph implementation, two unrelated corpora, no special cases."""

    def test_edges_from_an_external_corpus_carry_provenance(self, external_registry):
        edges = external_registry.graph.edges
        assert edges, "the external corpus produced no edges"
        for edge in edges:
            assert edge.provenance.kind, f"{edge.key} does not say what kind of evidence it is"
            assert edge.provenance.producer, f"{edge.key} does not say who asserted it"
            assert edge.provenance.evidence, f"{edge.key} does not say why it exists"

    def test_the_graph_survives_a_fresh_process(self, external_registry, tmp_path):
        """Restart is the point of persistence: a new registry, no prior state, same graph."""
        from pipeline.artifacts.store import ArtifactStore
        from pipeline.corpus import CorpusRegistry

        before = external_registry.graph.dependencies("xp-ch1-thm-1.2")
        fresh = CorpusRegistry.load(ArtifactStore(tmp_path / "extdata", corpus="xp"))
        assert fresh.graph.dependencies("xp-ch1-thm-1.2") == before

    def test_scheduling_is_deterministic_for_a_corpus_it_has_never_seen(self, external_registry):
        eligible = external_registry.eligible_nodes()
        assert "xp-ch1-thm-1.1" in eligible
        # thm-1.2 cites thm-1.1, so it waits — decided by graph logic, with no model.
        assert "xp-ch1-thm-1.2" not in eligible
        assert "xp-ch1-thm-1.2" in external_registry.eligible_nodes({"xp-ch1-thm-1.1"})

    def test_the_context_builder_queries_the_same_graph(self, external_registry):
        from pipeline.context.builders import build_formalization_context

        pkg = build_formalization_context(external_registry, "xp-ch1-thm-1.2")
        assert pkg.target_id == "xp-ch1-thm-1.2"
        assert pkg.corpus_version == external_registry.version

    def test_the_public_api_serves_it_with_no_corpus_specific_code(
        self, external_corpus, external_registry
    ):
        from pipeline.api import Pipeline

        api = Pipeline(external_registry.store.root, corpus="ext-parity")
        assert api.dependencies("xp-ch1-thm-1.2") == ["xp-ch1-thm-1.1"]
        assert {d["id"] for d in api.list_declarations()} == {
            "xp-ch1-thm-1.1",
            "xp-ch1-thm-1.2",
        }


class TestNoCorpusIsNamedInTheEngine:
    """The boundary that makes all of the above possible."""

    def test_no_core_module_names_a_corpus(self):
        """Documented in the README; asserted here so it cannot quietly stop being true."""
        from pipeline.corpus.config import available_corpora

        names = {n for n in available_corpora()} | {"demo-naturals", "ext-parity"}
        offenders = []
        for path in (REPO / "src" / "pipeline").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name in names:
                # The demo is legitimately named in the CLI's `demo` command, whose whole
                # job is to open the committed fixture, and in docstring examples.
                if name in text and path.name not in {"cli.py", "ids.py"}:
                    offenders.append(f"{path.relative_to(REPO)} names {name!r}")
        assert not offenders, "\n".join(offenders)

    def test_no_core_module_uses_graph_theory_vocabulary(self):
        """The first corpus was graph theory; those words must not have leaked into types.

        ``graph``, ``node`` and ``edge`` are excluded: they are CorpusGraph's own
        vocabulary, about dependencies between declarations, not about the mathematics of
        any corpus.
        """
        domain_words = (
            "vertex", "vertices", "bipartite", "chromatic", "hamiltonian", "eulerian",
            "subgraph", "clique", "digraph", "spanning tree", "planar",
        )
        offenders = []
        for path in (REPO / "src" / "pipeline").rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            offenders += [
                f"{path.relative_to(REPO)} mentions {word!r}"
                for word in domain_words
                if word in text
            ]
        assert not offenders, "\n".join(offenders)
