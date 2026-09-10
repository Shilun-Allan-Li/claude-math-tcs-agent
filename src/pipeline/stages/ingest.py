"""Stage 0 -- source ingestion.

Two halves, deliberately separated:

* **PDF -> Markdown** is the summer's script pipeline, which the forensic pass found
  sound (report 00 §C1: "scripts, not agents, for this stage -- the evidence supports the
  memory"). The pipeline wraps it rather than rewriting it; see :mod:`pipeline.stages.pdf_adapter`.
* **Markdown -> artifacts** is this module: chapter Markdown becomes a
  :class:`SourceDocument`, a :class:`SourceChapter`, a set of :class:`SourceItem`, and the
  cross-reference edges the book itself states. All deterministic.

Nothing here calls a model. Everything a regex can decide exactly is decided here, so the
annotator downstream spends its budget on judgement instead of on transcription.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from pipeline.corpus.config import ChapterConfig, CorpusConfig, load_corpus
from pipeline.corpus import CorpusRegistry
from pipeline.corpus.ids import chapter_id as make_chapter_id
from pipeline.corpus.ids import document_id as make_document_id
from pipeline.artifacts.models import (
    DependencyEdge,
    Provenance,
    SourceChapter,
    SourceDocument,
    SourceItem,
    Stage,
    StageRun,
)
from pipeline.artifacts.records import record_from_source_item
from pipeline.stages.cross_references import extract_cross_references
from pipeline.stages.source_items import ExtractionConfig, extract_source_items

__all__ = ["ingest_chapter", "IngestResult", "INGEST_VERSION"]

INGEST_VERSION = "ingest/v1"


@dataclass
class IngestResult:
    document: SourceDocument
    chapter: SourceChapter
    items: list[SourceItem]
    edges: list[DependencyEdge]
    run: StageRun

    @property
    def summary(self) -> dict[str, object]:
        return {
            "chapter": self.chapter.number,
            "items": len(self.items),
            "cross_reference_edges": len(self.edges),
            "with_proof": sum(1 for i in self.items if i.proof),
        }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_chapter(
    registry: CorpusRegistry,
    chapter: str | int,
    *,
    corpus_name: str | None = None,
    persist: bool = True,
) -> IngestResult:
    """Ingest one chapter's Markdown into the corpus.

    Idempotent: re-running produces identical artifacts (bar the provenance timestamp,
    which the store deliberately ignores when deciding whether to rewrite a row), so a
    re-ingest converges instead of accumulating.
    """
    started = time.monotonic()
    config: CorpusConfig = load_corpus(corpus_name)
    ch: ChapterConfig = config.chapter(chapter)
    markdown = ch.markdown.read_text(encoding="utf-8")

    doc_id = make_document_id(config.slug)
    chap_id = make_chapter_id(config.slug, ch.number)
    prov = Provenance(
        producer=INGEST_VERSION,
        input_fingerprint=_sha256_text(markdown),
        corpus_version=registry.version,
    )

    document = SourceDocument(
        id=doc_id,
        corpus=config.corpus,
        title=config.title,
        authors=list(config.authors),
        provenance=prov,
    )
    source_chapter = SourceChapter(
        id=chap_id,
        document_id=doc_id,
        number=ch.number,
        title=ch.title,
        markdown_path=str(ch.markdown.relative_to(config.path.parents[1])),
        sha256=_sha256_text(markdown),
        pdf_page_start=ch.pdf_page_start,
        pdf_page_end=ch.pdf_page_end,
        printed_page_start=ch.printed_page_start,
        printed_page_end=ch.printed_page_end,
        provenance=prov,
    )

    items = extract_source_items(
        markdown,
        ExtractionConfig(
            corpus=config.corpus,
            document_id=doc_id,
            chapter_id=chap_id,
            chapter=ch.number,
            printed_page_offset=ch.printed_page_offset,
        ),
        provenance=prov,
    )
    edges, _refs = extract_cross_references(items, corpus=config.slug)

    run = StageRun(
        id=f"run-ingest-{chap_id}-{int(time.time())}",
        stage=Stage.INGEST,
        target_id=chap_id,
        status="ok",
        input_artifact_ids=[str(ch.markdown.name)],
        output_artifact_ids=[i.id for i in items],
        wall_ms=int((time.monotonic() - started) * 1000),
    )

    if persist:
        registry.store.upsert("documents", [document])
        registry.store.upsert("chapters", [source_chapter])
        registry.store.upsert("items", items)
        # Records are seeded only for items the corpus does not already hold, so that a
        # re-ingest never discards annotation, Lean or review state attached later.
        new_records = [record_from_source_item(i) for i in items if registry.get(i.id) is None]
        if new_records:
            registry.upsert_records(new_records)
        registry.add_edges(edges)
        registry.store.append("runs", run)
        registry.save()

    return IngestResult(document, source_chapter, items, edges, run)
