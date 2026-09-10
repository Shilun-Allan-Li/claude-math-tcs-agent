"""Shared fixtures.

The public demo corpus is the only corpus this repository ships, so everything here is
written against it. Nothing in the suite needs a network, a provider key, or a private
corpus; the Lean-backed tests are marked ``lean`` and skip when ``lake`` is absent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SOURCE = REPO_ROOT / "examples/demo-corpus/source/01_unit-1-divisibility.md"
DEMO_FIXTURES = REPO_ROOT / "examples/demo-corpus/fixtures"
DEMO_ARTIFACTS = REPO_ROOT / "examples/demo-corpus/artifacts"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


def lean_toolchain_ready() -> bool:
    """Whether a real ``lake build`` against Mathlib can run here.

    Both halves matter. ``lake`` on PATH is not enough -- without a fetched and built
    Mathlib a build fails for reasons that have nothing to do with the corpus, and a test
    that reported that as a Lean verdict would be worse than one that skipped.
    """
    if shutil.which("lake") is None:
        return False
    return (REPO_ROOT / ".lake" / "packages" / "mathlib").exists()


@pytest.fixture
def lean_toolchain():
    """Requested by any test that shells out to Lean; skips when it cannot.

    A fixture rather than a module-level ``skipif`` so the check is evaluated at run time
    and needs no cross-module import. Tests that merely read a committed verification
    artifact must *not* request it -- they are not Lean-backed, and saying they are would
    overstate what the suite covers.
    """
    if not lean_toolchain_ready():
        pytest.skip("needs lake on PATH and a built Mathlib under .lake/packages")


@pytest.fixture
def store(tmp_path):
    """An empty artifact store for the demo corpus slug."""
    from pipeline.artifacts.store import ArtifactStore

    return ArtifactStore(tmp_path / "data", corpus="dn")


@pytest.fixture
def demo_artifacts(tmp_path) -> Path:
    """A writable copy of the committed demo artifacts."""
    target = tmp_path / "demo"
    shutil.copytree(DEMO_ARTIFACTS, target)
    return target


@pytest.fixture
def api(demo_artifacts):
    """The public API over the committed demo artifacts."""
    from pipeline.api import Pipeline

    return Pipeline(demo_artifacts, corpus="demo-naturals")


@pytest.fixture
def ingested(tmp_path):
    """A freshly ingested demo corpus: source items and cross-reference edges only."""
    from pipeline.artifacts.store import ArtifactStore
    from pipeline.corpus import CorpusRegistry
    from pipeline.stages.ingest import ingest_chapter

    registry = CorpusRegistry.load(ArtifactStore(tmp_path / "data", corpus="dn"))
    ingest_chapter(registry, 1, corpus_name="demo-naturals")
    registry.reload()
    return registry


@pytest.fixture
def demo_markdown() -> str:
    return DEMO_SOURCE.read_text(encoding="utf-8")


@pytest.fixture
def demo_config():
    from pipeline.stages.source_items import ExtractionConfig

    return ExtractionConfig(
        corpus="demo-naturals", document_id="dn", chapter_id="dn-ch1",
        chapter="1", printed_page_offset=0,
    )


@pytest.fixture
def source_items(demo_markdown, demo_config):
    """The demo corpus's source items, extracted deterministically."""
    from pipeline.stages.source_items import extract_source_items

    return extract_source_items(demo_markdown, demo_config)
