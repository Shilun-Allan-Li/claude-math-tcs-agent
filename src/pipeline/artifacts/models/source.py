"""Stage 0 artifacts: what the textbook says, and where in the textbook it says it."""

from __future__ import annotations

from pydantic import Field, model_validator

from pipeline.artifacts.models.base import Artifact, Provenance
from pipeline.artifacts.models.enums import SourceItemKind

__all__ = ["SourceDocument", "SourceChapter", "SourceItem", "SourceSpan", "NotationEntry"]


class SourceSpan(Artifact):
    """Character range inside a chapter's Markdown, plus the page it sits on.

    Report 01 §B1 measured the loss this prevents: the raw extraction carries 9-24
    ``<!-- p.NNN -->`` markers per chapter and the annotated chapters carry **zero**, so
    page provenance died at the annotation boundary. Holding the span lets ``page`` be
    *derived* from the nearest preceding marker instead of being re-typed by an agent.
    """

    start: int = Field(ge=0, description="Character offset into the chapter markdown.")
    end: int = Field(ge=0)
    printed_page: int | None = Field(
        default=None, description="Page number as printed in the book."
    )
    pdf_page: int | None = Field(default=None, description="Page number within the PDF.")

    @model_validator(mode="after")
    def _ordered(self) -> SourceSpan:
        if self.end < self.start:
            raise ValueError(f"span end {self.end} precedes start {self.start}")
        return self


class NotationEntry(Artifact):
    """One row of the source-notation table.

    Report 01 §E.4: 454 notation rows were re-derived across ten chapters, with symbols
    like nu, epsilon, delta and omega recurring in six or more. These belong in the corpus
    registry once, not per chapter -- but they are *observed* per chapter, so they are
    collected here and promoted by the registry.
    """

    symbol: str = Field(description="Source notation, verbatim, e.g. 'kappa(G)'.")
    meaning: str = Field(description="What the book says it denotes.")
    lean: str | None = Field(default=None, description="Exact Lean identifier, if resolved.")
    decided_in: str | None = Field(
        default=None, description="Declaration id where this mapping was fixed."
    )


class SourceDocument(Artifact):
    """A book. Identity is its corpus slug; ``sha256`` detects a changed source file."""

    id: str
    corpus: str = Field(description="Human name of the work, as its title page gives it.")
    title: str
    authors: list[str] = Field(default_factory=list)
    sha256: str | None = Field(default=None, description="Hash of the source PDF, if ingested.")
    page_count: int | None = None
    provenance: Provenance


class SourceChapter(Artifact):
    """One chapter of Markdown, with the page range it was merged from."""

    id: str
    document_id: str
    number: str = Field(description="Chapter number as a string: '3', or 'A1' for appendices.")
    title: str
    markdown_path: str = Field(description="Path to the chapter markdown, relative to repo root.")
    sha256: str = Field(description="Hash of the chapter markdown content.")
    pdf_page_start: int | None = None
    pdf_page_end: int | None = None
    printed_page_start: int | None = None
    printed_page_end: int | None = None
    provenance: Provenance


class SourceItem(Artifact):
    """A single mathematical item as the *book* states it.

    Deliberately free of any Lean notion. Rule 3: source terminology, notation, numbering
    and statement identity are stored, never replaced. ``statement`` is a verbatim slice of
    the chapter markdown -- not a paraphrase -- so that fidelity checking compares against
    the book rather than against an agent's summary of it (report 01 §D2).
    """

    id: str = Field(description="Stable declaration id from pipeline.corpus.ids.declaration_id.")
    document_id: str
    chapter_id: str
    chapter: str
    section: str | None = Field(default=None, description="Book section, e.g. '3.1'.")
    label: str | None = Field(default=None, description="Printed label, e.g. '3.2' or '1.2.8(b)'.")
    kind: SourceItemKind
    name: str | None = Field(
        default=None, description="Term the book introduces, for unlabelled definitions."
    )
    statement: str = Field(description="Verbatim source text of the statement.")
    proof: str | None = Field(default=None, description="Verbatim printed proof, if the book gives one.")
    span: SourceSpan | None = None
    notation: list[NotationEntry] = Field(default_factory=list)
    provenance: Provenance

    @property
    def fingerprint(self) -> str:
        """Hash of the exact source content. Computed, never stored.

        An earlier revision stored this as a field and it went stale the moment a
        statement was edited -- the same class of bug that let the summer's annotations
        keep asserting facts about a repository state they were no longer written
        against. A derived value that can disagree with its inputs is worse than no
        value, so this one cannot.

        Downstream artifacts (``AnnotatedDeclaration.source_fingerprint``,
        ``ReviewDecision.artifact_fingerprint``) *do* store a copy, deliberately: there
        it is a snapshot of what the producer or reviewer actually saw, and comparing it
        against this property is precisely the staleness check.
        """
        from pipeline.corpus.ids import content_fingerprint

        return content_fingerprint(self.statement, self.proof)

    @property
    def is_theorem_like(self) -> bool:
        from pipeline.artifacts.models.enums import THEOREM_LIKE

        return self.kind in THEOREM_LIKE
